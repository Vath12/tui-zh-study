import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

# Stroke data from Make Me a Hanzi, packaged per character as hanzi-writer-data
# (Arphic Public License). Downloaded on first use and cached here.
STROKE_URL = "https://cdn.jsdelivr.net/npm/hanzi-writer-data@2.0.1/{}.json"
STROKE_CACHE = Path(__file__).parent.parent / "resources" / "strokes"

# The data uses a 1024x1024 box with y pointing up; the baseline sits at y=900.
BOX = 1024
TOP = 900

# 256-color ANSI codes (plain Terminal.app doesn't do truecolor).
STROKE_COLORS = [196, 208, 226, 46, 51, 33, 129, 201]
DONE, CURRENT, TODO = 250, 196, 238

# Each braille character is a 2-wide, 4-tall grid of dots; this is the bit for
# the dot at [y][x] within the cell. Characters are U+2800 + the bits that are on.
BRAILLE_BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def load_character(char: str) -> dict:
    """Stroke data for `char`: "strokes" (SVG outlines) and "medians" (each
    stroke's centerline), both in stroke order."""
    path = STROKE_CACHE / f"{char}.json"
    if not path.exists():
        url = STROKE_URL.format(urllib.parse.quote(char))
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            raise KeyError(f"no stroke data for {char!r}") from e
        STROKE_CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_path(d: str, steps: int = 8) -> list[list[tuple[float, float]]]:
    """Turn an SVG path (M/L/Q/C/Z, absolute) into polygons, one per subpath."""
    tokens = re.findall(r"[MLQCZ]|-?[\d.]+", d)
    polys, poly, pos, i = [], [], (0.0, 0.0), 0
    while i < len(tokens):
        cmd = tokens[i]
        n = {"M": 2, "L": 2, "Q": 4, "C": 6, "Z": 0}[cmd]
        args = [float(t) for t in tokens[i + 1:i + 1 + n]]
        i += 1 + n
        if cmd == "M":
            if poly:
                polys.append(poly)
            pos = (args[0], args[1])
            poly = [pos]
        elif cmd == "L":
            pos = (args[0], args[1])
            poly.append(pos)
        elif cmd == "Q":
            (x0, y0), (x1, y1, x, y) = pos, args
            for k in range(1, steps + 1):
                t = k / steps
                poly.append(((1-t)**2*x0 + 2*(1-t)*t*x1 + t*t*x,
                             (1-t)**2*y0 + 2*(1-t)*t*y1 + t*t*y))
            pos = (x, y)
        elif cmd == "C":
            (x0, y0), (x1, y1, x2, y2, x, y) = pos, args
            for k in range(1, steps + 1):
                t = k / steps
                poly.append(((1-t)**3*x0 + 3*(1-t)**2*t*x1 + 3*(1-t)*t*t*x2 + t**3*x,
                             (1-t)**3*y0 + 3*(1-t)**2*t*y1 + 3*(1-t)*t*t*y2 + t**3*y))
            pos = (x, y)
        elif cmd == "Z" and poly:
            polys.append(poly)
            poly = []
    if poly:
        polys.append(poly)
    return polys


def inside(x: float, y: float, polys: list[list[tuple[float, float]]]) -> bool:
    """Even-odd point-in-polygon test."""
    hit = False
    for poly in polys:
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def rasterize(strokes: list[str], width: int, height: int) -> list[list[int | None]]:
    """A height x width grid of dots holding the index of the stroke covering
    each dot (the later stroke where they overlap), or None."""
    polys = [flatten_path(d) for d in strokes]
    boxes = [(min(x for p in ps for x, _ in p), max(x for p in ps for x, _ in p),
              min(y for p in ps for _, y in p), max(y for p in ps for _, y in p)) for ps in polys]
    grid = [[None] * width for _ in range(height)]
    for py in range(height):
        y = TOP - (py + 0.5) * BOX / height
        for px in range(width):
            x = (px + 0.5) * BOX / width
            for i, (ps, (x0, x1, y0, y1)) in enumerate(zip(polys, boxes)):
                if x0 <= x <= x1 and y0 <= y <= y1 and inside(x, y, ps):
                    grid[py][px] = i
    return grid


def to_braille(grid: list[list[int | None]], color_of, pick=None) -> list[str]:
    """Pack a grid of stroke indices into lines of braille characters.

    All the dots in a cell share one color, color_of(stroke). The stroke is
    the one covering most of the cell's dots, unless pick(strokes) says otherwise."""
    lines = []
    for row in range(0, len(grid), 4):
        line = ""
        for col in range(0, len(grid[0]), 2):
            bits, strokes = 0, []
            for dy in range(4):
                for dx in range(2):
                    if row + dy < len(grid) and col + dx < len(grid[0]):
                        s = grid[row + dy][col + dx]
                        if s is not None:
                            bits |= BRAILLE_BITS[dy][dx]
                            strokes.append(s)
            if not bits:
                line += " "
                continue
            s = pick(strokes) if pick else Counter(strokes).most_common(1)[0][0]
            line += f"\x1b[38;5;{color_of(s)}m{chr(0x2800 + bits)}\x1b[0m"
        lines.append(line)
    return lines


def dots(char: str, size: int) -> list[list[int | None]]:
    """Rasterize `char` for a canvas `size` terminal columns wide (2 dots per
    column) and size / 2 rows tall (4 dots per row), so the dots are square."""
    return rasterize(load_character(char)["strokes"], size * 2, size * 2)


def render_character(char: str, size: int = 40) -> str:
    """The whole character, each stroke colored by its position in stroke order."""
    grid = dots(char, size)
    return "\n".join(to_braille(grid, lambda s: STROKE_COLORS[s % len(STROKE_COLORS)]))


def render_stroke_order(char: str, size: int = 24, per_row: int | None = None) -> str:
    """One panel per stroke: earlier strokes in gray, the new stroke in red,
    and the strokes still to come faintly. Any cell touching the new stroke is
    drawn red, so it shows in full."""
    grid = dots(char, size)
    n = len(load_character(char)["strokes"])
    if per_row is None:
        per_row = max(1, shutil.get_terminal_size().columns // (size + 2))
    panels = []
    for k in range(n):
        color = lambda s, k=k: DONE if s < k else CURRENT if s == k else TODO
        pick = lambda strokes, k=k: k if k in strokes else min(strokes)
        panels.append([f"{k + 1:<{size}}", *to_braille(grid, color, pick)])
    rows = []
    for start in range(0, len(panels), per_row):
        group = panels[start:start + per_row]
        rows.append("\n".join("  ".join(lines) for lines in zip(*group)))
    return "\n\n".join(rows)


if __name__ == "__main__":
    for char in "".join(sys.argv[1:]) or "我":
        print(render_character(char))
        print()
        print(render_stroke_order(char))
        print()
