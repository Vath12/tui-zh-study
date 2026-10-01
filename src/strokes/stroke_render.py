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


def stroke_progress(d : str, median : list, width : int, height : int) -> np.ndarray:
    '''For each pixel inside a stroke, how far along the stroke it is, from 0
    at the start of the brush movement to 1 at the end (NaN outside the
    stroke). Found by projecting each pixel onto the nearest segment of the
    stroke's median, so revealing pixels up to t draws the stroke like a brush.'''
    mask = stroke_mask(d, width, height)
    progress = np.full((height, width), np.nan)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return progress
    points = np.stack([(xs + 0.5) * BOX / width, TOP - (ys + 0.5) * BOX / height], axis=-1)
    m = np.array(median, dtype=float)
    if len(m) < 2:
        progress[mask] = 0
        return progress
    a, v = m[:-1], m[1:] - m[:-1]                 # segment starts and directions
    lengths = np.hypot(*v.T)
    before = np.concatenate([[0], np.cumsum(lengths)[:-1]])
    # Position along each segment (0-1) of each pixel's closest point on it.
    u = ((points[:, None] - a) * v).sum(-1) / np.maximum(lengths ** 2, 1e-9)
    u = u.clip(0, 1)
    dist = np.hypot(*(points[:, None] - (a + u[..., None] * v)).transpose(2, 0, 1))
    nearest = dist.argmin(axis=1)
    along = before[nearest] + u[np.arange(len(u)), nearest] * lengths[nearest]
    progress[ys, xs] = along / max(lengths.sum(), 1e-9)
    return progress


class ZiAnimation:
    '''Animates a character being written onto a canvas, one stroke at a time.

    Every frame, draw(elapsed) redraws the canvas for `elapsed` seconds into
    the animation: the whole character faintly in `ghost`, the finished strokes,
    and the current stroke up to how far the brush has got. Each stroke takes
    `stroke_time` seconds, with `pause` between strokes; after the last one the
    finished character stays up for `hold` seconds, then it starts over.'''

    def __init__(self, zi : Zi, canvas : TerminalCanvas, colored : bool = True, color : tuple[int, ...] = WHITE,
                 stroke_time : float = 0.5, pause : float = 0.15, hold : float = 1.5,
                 ghost : tuple[int, ...] | None = (70, 70, 70, 255)):
        self.zi = zi
        self.canvas = canvas
        self.colors = stroke_colors(zi.n_strokes) if colored else [color] * zi.n_strokes
        self.stroke_time, self.pause, self.hold = stroke_time, pause, hold
        self.ghost = ghost
        self.progress = [stroke_progress(d, m, canvas.width, canvas.height) for d, m in zip(zi.strokes, zi.medians)]
        self.duration = zi.n_strokes * (stroke_time + pause) + hold

    def stroke_at(self, elapsed : float) -> int:
        '''Index of the stroke being drawn at `elapsed` (n_strokes once it's all drawn).'''
        return min(int((elapsed % self.duration) // (self.stroke_time + self.pause)), self.zi.n_strokes)

    def draw(self, elapsed : float):
        t = elapsed % self.duration
        pixels = self.canvas.pixels
        pixels[:] = 0
        if self.ghost:
            for p in self.progress:
                pixels[~np.isnan(p), :len(self.ghost)] = self.ghost
        for i, (p, c) in enumerate(zip(self.progress, self.colors)):
            done = (t - i * (self.stroke_time + self.pause)) / self.stroke_time
            if done <= 0:
                break
            shown = p <= min(done, 1)          # NaN (outside the stroke) compares False
            pixels[shown, :len(c)] = c
            if len(c) == 3:
                pixels[shown, 3] = 255
        self.canvas.dirty = True


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