from dataclasses import dataclass, replace
from functools import lru_cache

# A color is an (r, g, b) tuple, or an int 0-255 from the terminal's palette.
Color = tuple[int, int, int] | int

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
RED = (255, 80, 80)
GREEN = (80, 220, 80)
BLUE = (90, 140, 255)
YELLOW = (240, 220, 80)
CYAN = (80, 220, 220)
MAGENTA = (220, 90, 220)


@dataclass(frozen=True, slots=True)
class Style:
    '''How a cell looks. Styles are compared a lot (every cell, every frame), so
    build them with Style.of() or the helpers below, which hand back the same
    object for the same style.'''
    fg : Color | None = None
    bg : Color | None = None
    bold : bool = False
    dim : bool = False
    italic : bool = False
    underline : bool = False
    reverse : bool = False

    @staticmethod
    def of(fg : Color | None = None, bg : Color | None = None, bold : bool = False, dim : bool = False,
           italic : bool = False, underline : bool = False, reverse : bool = False) -> 'Style':
        key = (fg, bg, bool(bold), bool(dim), bool(italic), bool(underline), bool(reverse))
        style = _INTERNED.get(key)
        if style is None:
            style = _INTERNED[key] = Style(*key)
        return style

    def but(self, **changes) -> 'Style':
        '''This style with some fields changed: DIM.but(fg=RED).'''
        s = replace(self, **changes)
        return Style.of(s.fg, s.bg, s.bold, s.dim, s.italic, s.underline, s.reverse)

    def over(self, base : 'Style') -> 'Style':
        '''This style drawn on top of `base`: colors this one leaves unset come
        from base, and attributes are combined.'''
        return Style.of(self.fg if self.fg is not None else base.fg,
                        self.bg if self.bg is not None else base.bg,
                        self.bold or base.bold, self.dim or base.dim, self.italic or base.italic,
                        self.underline or base.underline, self.reverse or base.reverse)


_INTERNED : dict[tuple, Style] = {}

PLAIN = Style.of()
BOLD = Style.of(bold=True)
DIM = Style.of(dim=True)
REVERSE = Style.of(reverse=True)
UNDERLINE = Style.of(underline=True)


def fg(color : Color, **attrs) -> Style:
    return Style.of(fg=color, **attrs)


def to_256(color : Color) -> int:
    '''Nearest color in the 6x6x6 cube of the 256-color palette.'''
    if isinstance(color, int):
        return color
    r, g, b = (round(v / 255 * 5) for v in color)
    return 16 + 36 * r + 6 * g + b


def _color_sgr(color : Color, base : int, depth : str) -> str:
    if isinstance(color, int):
        return f'{base + 8};5;{color}'
    if depth == '256':
        return f'{base + 8};5;{to_256(color)}'
    return f'{base + 8};2;{color[0]};{color[1]};{color[2]}'


@lru_cache(maxsize=None)
def sgr(style : Style, depth : str = 'truecolor') -> str:
    '''The escape sequence that sets exactly this style, from a reset.
    depth: 'truecolor' or '256' (colors are converted to the palette).'''
    codes = ['0']
    if style.bold: codes.append('1')
    if style.dim: codes.append('2')
    if style.italic: codes.append('3')
    if style.underline: codes.append('4')
    if style.reverse: codes.append('7')
    if style.fg is not None: codes.append(_color_sgr(style.fg, 30, depth))
    if style.bg is not None: codes.append(_color_sgr(style.bg, 40, depth))
    return f'\x1b[{";".join(codes)}m'
