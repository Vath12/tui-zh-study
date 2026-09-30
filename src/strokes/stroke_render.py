import colorsys
import re

import numpy as np

from .render import TerminalCanvas, WHITE
from .stroke import HanziStroke, Zi

# Stroke data uses a 1024 x 1024 box with y pointing up; the top of the box is y=900.
BOX = 1024
TOP = 900


def flatten_path(d : str, steps : int = 8) -> list[np.ndarray]:
    '''Turn a stroke's SVG path (M/L/Q/C/Z, absolute) into polygons, one
    (n, 2) array of points per subpath, with curves split into `steps` lines.'''
    tokens = re.findall(r'[MLQCZ]|-?[\d.]+', d)
    polys, poly, pos, i = [], [], (0.0, 0.0), 0
    t = np.linspace(0, 1, steps + 1)[1:, None]
    while i < len(tokens):
        cmd = tokens[i]
        n = {'M': 2, 'L': 2, 'Q': 4, 'C': 6, 'Z': 0}[cmd]
        args = np.array([float(v) for v in tokens[i + 1:i + 1 + n]]).reshape(-1, 2)
        i += 1 + n
        if cmd == 'M':
            if poly:
                polys.append(np.array(poly))
            poly = [tuple(args[0])]
        elif cmd == 'L':
            poly.append(tuple(args[0]))
        elif cmd == 'Q':
            p0, (p1, p2) = np.array(pos), args
            poly += [tuple(p) for p in (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2]
        elif cmd == 'C':
            p0, (p1, p2, p3) = np.array(pos), args
            poly += [tuple(p) for p in (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
                     + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3]
        elif cmd == 'Z' and poly:
            polys.append(np.array(poly))
            poly = []
        if poly:
            pos = poly[-1]
    if poly:
        polys.append(np.array(poly))
    return polys


def stroke_mask(d : str, width : int, height : int) -> np.ndarray:
    '''A (height, width) bool array of the pixels inside one stroke's outline,
    with the stroke box scaled to fill the whole array.'''
    # Pixel centers, in the stroke data's coordinates.
    x = (np.arange(width) + 0.5) * BOX / width
    y = TOP - (np.arange(height) + 0.5) * BOX / height
    X, Y = np.meshgrid(x, y)
    inside = np.zeros((height, width), dtype=bool)
    # Even-odd rule: a pixel is inside if a ray to its right crosses the outline an odd number of times.
    for poly in flatten_path(d):
        for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0)):
            if y1 == y2:
                continue
            crosses = (y1 > Y) != (y2 > Y)
            inside ^= crosses & (X < x1 + (Y - y1) * (x2 - x1) / (y2 - y1))
    return inside


def stroke_colors(n : int) -> list[tuple[int, int, int, int]]:
    '''n distinct colors, going round the color wheel in stroke order.'''
    return [tuple(round(c * 255) for c in colorsys.hsv_to_rgb(i / n, 1.0, 1.0)) + (255,) for i in range(n)]

def draw_zi(canvas : TerminalCanvas, zi : Zi, colored : bool = True,
            color : tuple[int, ...] = WHITE) -> TerminalCanvas:
    '''Draw a character onto the whole canvas. With colored, each stroke gets
    its own color (see stroke_colors); otherwise the character is drawn
    normally, all in `color`. Where strokes overlap, the later one is on top.'''
    colors = stroke_colors(zi.n_strokes) if colored else [color] * zi.n_strokes
    for d, c in zip(zi.strokes, colors):
        mask = stroke_mask(d, canvas.width, canvas.height)
        canvas.pixels[mask, :len(c)] = c
        if len(c) == 3:
            canvas.pixels[mask, 3] = 255
    canvas.dirty = True
    return canvas


def render_zi(zi : Zi | str, size : int = 80, colored : bool = True, color : tuple[int, ...] = WHITE,
              glyphs : str = 'braille', **canvas_options) -> str:
    '''A character as terminal text, `size` x `size` pixels. `zi` can be a Zi
    or the character itself. Other options go to TerminalCanvas.'''
    if isinstance(zi, str):
        zi = HanziStroke.get_strokes(zi)
    canvas = TerminalCanvas(size, size, glyphs=glyphs, **canvas_options)
    return draw_zi(canvas, zi, colored, color).render()


if __name__ == '__main__':
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    glyphs = next((a[len('--glyphs='):] for a in sys.argv[1:] if a.startswith('--glyphs=')), 'braille')
    for char in ''.join(args) or '我':
        print(render_zi(char, size=90, cell_color='majority', colored='--plain' not in sys.argv, glyphs=glyphs))