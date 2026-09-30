from dataclasses import dataclass

import numpy as np

# A few colors as (r, g, b, a).
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
GRAY = (128, 128, 128, 255)
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
YELLOW = (255, 255, 0, 255)
CYAN = (0, 255, 255, 255)
MAGENTA = (255, 0, 255, 255)

# Each glyph set covers a terminal cell with a grid of `width` x `height` pixels,
# and `chars[mask]` is the character showing the pixels in `mask`: bit
# y * width + x is the pixel at (x, y) in the cell.
@dataclass(frozen=True)
class Glyphs:
    width : int
    height : int
    chars : tuple[str, ...]


def _braille() -> Glyphs:
    # U+2800 plus one bit per dot. The dot bits aren't in row order, so map them.
    dot_bits = [0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80]  # (0,0) (1,0) (0,1) ...
    chars = [chr(0x2800 + sum(b for i, b in enumerate(dot_bits) if mask >> i & 1)) for mask in range(256)]
    chars[0] = ' '
    return Glyphs(2, 4, tuple(chars))


def _octant() -> Glyphs:
    # Unicode 16 encodes the octants at U+1CD00-1CDE5 in mask order, except the
    # 26 patterns that already had a character (blocks, halves, quadrants, ...).
    existing = {
        0: ' ', 1: '\U0001CEA8', 2: '\U0001CEAB', 3: '\U0001FB82', 5: '▘', 10: '▝', 15: '▀',
        20: '\U0001FBE6', 40: '\U0001FBE7', 63: '\U0001FB85', 64: '\U0001CEA3', 80: '▖',
        85: '▌', 90: '▞', 95: '▛', 128: '\U0001CEA0', 160: '▗', 165: '▚', 170: '▐', 175: '▜',
        192: '▂', 240: '▄', 245: '▙', 250: '▟', 252: '▆', 255: '█',
    }
    chars, next_octant = [], 0x1CD00
    for mask in range(256):
        if mask in existing:
            chars.append(existing[mask])
        else:
            chars.append(chr(next_octant))
            next_octant += 1
    return Glyphs(2, 4, tuple(chars))


GLYPHS = {
    'braille': _braille(),    # 2 x 4 separate dots; supported by nearly every font
    'quadrant': Glyphs(2, 2, tuple(' ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█')),  # 2 x 2 solid blocks; widely supported
    'octant': _octant(),      # 2 x 4 solid blocks; needs a font with Unicode 16 octants
}


class TerminalCanvas:
    '''An RGBA pixel buffer that's shown in the terminal as text.

    Drawing only writes pixels: `pixels` is a (height, width, 4) uint8 array of
    r, g, b, a with (0, 0) at the top left. Turning that into text happens in
    render(), which caches its output until something marks the canvas dirty.
    set(), fill() and clear() do that; if you write to `pixels` directly, set
    `dirty = True` yourself.

    `glyphs` picks the characters, and so how many pixels each terminal cell
    shows (see GLYPHS): 'braille' (2 x 4 dots), 'quadrant' (2 x 2 blocks) or
    'octant' (2 x 4 blocks). Changing it changes the canvas's size in terminal
    cells, not in pixels.

    A pixel shows if its alpha is at least `threshold`. A cell can only be one
    color, picked from its pixels by `cell_color`:
      'blend'     the alpha-weighted average of the dots' colors
      'majority'  the exact color most of the dots have (ties go to the first
                  such dot, reading top to bottom, left to right)'''

    def __init__(self, width : int, height : int, glyphs : str = 'braille', color_mode : str = 'truecolor',
                 cell_color : str = 'majority', threshold : int = 128):
        self.width = width
        self.height = height
        self.glyphs = glyphs          # a key of GLYPHS
        self.color_mode = color_mode  # 'truecolor', '256' (e.g. macOS Terminal) or 'none'
        self.cell_color = cell_color  # 'blend' or 'majority'
        self.threshold = threshold
        self.pixels = np.zeros((height, width, 4), dtype=np.uint8)
        self.dirty = True
        self._cache : str | None = None
        self._cache_settings : tuple | None = None

    @property
    def _glyphs(self) -> Glyphs:
        if self.glyphs not in GLYPHS:
            raise ValueError(f'unknown glyphs {self.glyphs!r}, expected one of {list(GLYPHS)}')
        return GLYPHS[self.glyphs]

    @property
    def cols(self) -> int:
        '''Width in terminal columns.'''
        return -(-self.width // self._glyphs.width)

    @property
    def rows(self) -> int:
        '''Height in terminal rows.'''
        return -(-self.height // self._glyphs.height)

    def set(self, x : int, y : int, rgba : tuple[int, ...]):
        '''Write one pixel. rgba can leave out alpha (then it's opaque).
        Pixels outside the canvas are ignored.'''
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y, x, :len(rgba)] = rgba
            if len(rgba) == 3:
                self.pixels[y, x, 3] = 255
            self.dirty = True

    def get(self, x : int, y : int) -> tuple[int, int, int, int]:
        return tuple(int(v) for v in self.pixels[y, x])

    def fill(self, rgba : tuple[int, ...]):
        self.pixels[..., :len(rgba)] = rgba
        if len(rgba) == 3:
            self.pixels[..., 3] = 255
        self.dirty = True

    def clear(self):
        self.pixels[:] = 0
        self.dirty = True

    def _cells(self) -> tuple[np.ndarray, np.ndarray]:
        '''For each terminal cell, the mask of pixels that are on (rows, cols)
        and its color (rows, cols, 3).'''
        g = self._glyphs
        padded = np.zeros((self.rows * g.height, self.cols * g.width, 4), dtype=np.float32)
        padded[:self.height, :self.width] = self.pixels
        # (rows, h, cols, w, 4) -> (rows, cols, h * w, 4): each cell's pixels, in row order.
        cells = (padded.reshape(self.rows, g.height, self.cols, g.width, 4)
                 .transpose(0, 2, 1, 3, 4).reshape(self.rows, self.cols, g.height * g.width, 4))
        alpha = cells[..., 3]
        on = alpha >= self.threshold
        mask = (on << np.arange(g.height * g.width)).sum(axis=-1)
        if self.cell_color == 'majority':
            return mask, self._majority(cells[..., :3], on)
        if self.cell_color != 'blend':
            raise ValueError(f'unknown cell_color {self.cell_color!r}')
        weight = alpha * on
        total = weight.sum(axis=-1)
        rgb = (cells[..., :3] * weight[..., None]).sum(axis=-2) / np.maximum(total, 1)[..., None]
        return mask, rgb.round().astype(np.uint8)

    @staticmethod
    def _majority(rgb : np.ndarray, on : np.ndarray) -> np.ndarray:
        '''For each cell's pixels (rows, cols, n, 3) and which are on (rows, cols, n),
        the most common color among the pixels that are on.'''
        key = rgb.astype(np.int32) @ np.array([1 << 16, 1 << 8, 1])  # one int per color
        # same[..., i, j]: dots i and j are both on and the same color.
        same = (key[..., :, None] == key[..., None, :]) & on[..., :, None] & on[..., None, :]
        votes = same.sum(axis=-1)                     # how many dots share each dot's color
        winner = votes.argmax(axis=-1)                # first dot with the most votes
        return np.take_along_axis(rgb, winner[..., None, None], axis=2)[..., 0, :].astype(np.uint8)

    def _escape(self, r : int, g : int, b : int) -> str:
        if self.color_mode == '256':
            # Nearest color in the 6x6x6 cube of the 256-color palette.
            r6, g6, b6 = (round(v / 255 * 5) for v in (r, g, b))
            return f'\x1b[38;5;{16 + 36 * r6 + 6 * g6 + b6}m'
        return f'\x1b[38;2;{r};{g};{b}m'

    def render(self) -> str:
        '''The canvas as text, rebuilt only if the pixels or settings have
        changed since last time.'''
        settings = (self.glyphs, self.color_mode, self.cell_color, self.threshold)
        if not self.dirty and self._cache is not None and settings == self._cache_settings:
            return self._cache
        mask, rgb = self._cells()
        chars = self._glyphs.chars
        color = self.color_mode != 'none'
        lines = []
        for row in range(self.rows):
            line, current = '', None
            for col in range(self.cols):
                m = int(mask[row, col])
                if not m:
                    line += ' '
                    continue
                c = tuple(int(v) for v in rgb[row, col])
                if color and c != current:
                    # Only switch colors when it changes, not on every cell.
                    line += self._escape(*c)
                    current = c
                line += chars[m]
            if current is not None:
                line += '\x1b[0m'
            lines.append(line)
        self._cache = '\n'.join(lines)
        self._cache_settings = settings
        self.dirty = False
        return self._cache

    def __str__(self) -> str:
        return self.render()


if __name__ == '__main__':
    import time
    # A small demo: a circle fading from cyan to magenta, with a line through it.
    t0 = time.time()
    import sys
    canvas = TerminalCanvas(
        80, 
        80, 
        glyphs=sys.argv[1] if len(sys.argv) > 1 else 'octant',
        cell_color='blend'
        )
    y, x = np.mgrid[:80, :80]
    ring = np.abs(np.hypot(x - 39.5, y - 39.5) - 33) <= 3
    canvas.pixels[ring] = np.stack([y[ring] * 255 // 79, 255 - y[ring] * 255 // 79,
                                    np.full(ring.sum(), 255), np.full(ring.sum(), 255)], axis=-1)
    canvas.dirty = True
    for i in range(80):
        canvas.set(i, i, YELLOW)
    t1 = time.time()
    print(canvas)
    t2 = time.time()
    print(canvas)  # cached
    t3 = time.time()
    print(f'draw {t1 - t0:.4f}s, render {t2 - t1:.4f}s, cached render {t3 - t2:.6f}s')
