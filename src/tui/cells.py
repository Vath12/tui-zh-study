import re
from functools import lru_cache
from typing import Iterable

from wcwidth import wcwidth

from .style import PLAIN, Style

# A cell is (text, style). A double-width character (most Chinese) takes two
# cells: its own, then a WIDE placeholder that the renderer skips.
Cell = tuple[str, Style]
WIDE = ''
BLANK : Cell = (' ', PLAIN)

# Rich text: a str, one (str, Style) span, or a sequence of spans, each a str or (str, Style).
Span = str | tuple[str, Style]
Rich = str | Iterable[Span]


@lru_cache(maxsize=4096)
def char_width(c : str) -> int:
    '''Columns a character takes: 2 for wide (我), 1 for most, 0 for combining
    marks and control characters (which are dropped).'''
    return max(0, wcwidth(c))


def text_width(text : str) -> int:
    return sum(map(char_width, text))


def spans(rich : Rich, style : Style = PLAIN) -> list[tuple[str, Style]]:
    '''Rich text as (text, style) spans, each style drawn over `style`.'''
    if isinstance(rich, str):
        return [(rich, style)]
    if isinstance(rich, tuple) and len(rich) == 2 and isinstance(rich[1], Style):
        rich = [rich]   # one span on its own
    out = []
    for span in rich:
        if isinstance(span, str):
            out.append((span, style))
        else:
            out.append((span[0], span[1].over(style)))
    return out


def rich_width(rich : Rich) -> int:
    return sum(text_width(t) for t, _ in spans(rich))


def split_lines(rich : Rich) -> list[list[tuple[str, Style]]]:
    '''Rich text split at newlines, one list of spans per line.'''
    lines = [[]]
    for text, style in spans(rich):
        parts = text.split('\n')
        for i, part in enumerate(parts):
            if i:
                lines.append([])
            if part:
                lines[-1].append((part, style))
    return lines


def wrap(line : list[tuple[str, Style]], width : int) -> list[list[tuple[str, Style]]]:
    '''One line of spans wrapped to `width` columns, breaking at spaces where it
    can (and anywhere for long words, and between Chinese characters).'''
    if width <= 0:
        return [line]
    cells = [(c, s) for text, s in line for c in text]
    out, start = [], 0
    while start < len(cells):
        used, end, last_break = 0, start, None
        while end < len(cells) and used + char_width(cells[end][0]) <= width:
            if cells[end][0] == ' ':
                last_break = end
            used += char_width(cells[end][0])
            end += 1
        if end < len(cells) and last_break is not None and last_break > start:
            end = last_break
        if end == start:
            end += 1     # a wide char in a 1-column line: it goes alone (and gets clipped)
        out.append(_merge(cells[start:end]))
        start = end
        while start < len(cells) and cells[start][0] == ' ' and end != len(cells):
            start += 1   # drop the spaces the line broke at
    return out or [[]]


def _merge(cells : list[tuple[str, Style]]) -> list[tuple[str, Style]]:
    out = []
    for c, s in cells:
        if out and out[-1][1] is s:
            out[-1] = (out[-1][0] + c, s)
        else:
            out.append((c, s))
    return out


# ANSI text (e.g. a TerminalCanvas render, or blessed's term.green('x')): SGR
# sequences set the style, anything else is dropped.
_ESCAPE = re.compile(r'\x1b\[([0-9;:]*)([@-~])|\x1b[()][0-9A-Za-z]|\x1b.')


def _sgr_codes(params : str) -> list[int]:
    return [int(p) if p else 0 for p in params.replace(':', ';').split(';')] if params else [0]


def apply_sgr(style : Style, params : str, base : Style = PLAIN) -> Style:
    '''`style` after an SGR sequence with these parameters. A reset goes back to `base`.'''
    codes, i = _sgr_codes(params), 0
    fields = dict(fg=style.fg, bg=style.bg, bold=style.bold, dim=style.dim, italic=style.italic,
                  underline=style.underline, reverse=style.reverse)
    while i < len(codes):
        c = codes[i]
        if c == 0:
            fields = dict(fg=base.fg, bg=base.bg, bold=base.bold, dim=base.dim, italic=base.italic,
                          underline=base.underline, reverse=base.reverse)
        elif c == 1: fields['bold'] = True
        elif c == 2: fields['dim'] = True
        elif c == 3: fields['italic'] = True
        elif c == 4: fields['underline'] = True
        elif c == 7: fields['reverse'] = True
        elif c == 22: fields['bold'] = fields['dim'] = False
        elif c == 23: fields['italic'] = False
        elif c == 24: fields['underline'] = False
        elif c == 27: fields['reverse'] = False
        elif c in (38, 48) and i + 1 < len(codes):
            key = 'fg' if c == 38 else 'bg'
            if codes[i + 1] == 5 and i + 2 < len(codes):
                fields[key] = codes[i + 2]
                i += 2
            elif codes[i + 1] == 2 and i + 4 < len(codes):
                fields[key] = tuple(codes[i + 2:i + 5])
                i += 4
        elif c == 39: fields['fg'] = base.fg
        elif c == 49: fields['bg'] = base.bg
        elif 30 <= c <= 37: fields['fg'] = c - 30
        elif 90 <= c <= 97: fields['fg'] = c - 90 + 8
        elif 40 <= c <= 47: fields['bg'] = c - 40
        elif 100 <= c <= 107: fields['bg'] = c - 100 + 8
        i += 1
    return Style.of(**fields)


def parse_ansi(text : str, base : Style = PLAIN) -> list[list[tuple[str, Style]]]:
    '''ANSI text as lines of spans. The style carries on across lines, as it
    would in a terminal.'''
    lines, line, style, pos = [], [], base, 0
    for m in _ESCAPE.finditer(text + '\x1b[0m'):    # the reset flushes the last chunk
        chunk = text[pos:m.start()]
        for i, part in enumerate(chunk.split('\n')):
            if i:
                lines.append(line)
                line = []
            if part:
                line.append((part, style))
        if m.group(2) == 'm':
            style = apply_sgr(style, m.group(1), base)
        pos = m.end()
    lines.append(line)
    return lines


class Buffer:
    '''A screen's worth of cells: `rows[y][x]`.'''

    def __init__(self, width : int, height : int):
        self.width = width
        self.height = height
        self.rows = [[BLANK] * width for _ in range(height)]

    def region(self) -> 'Region':
        return Region(self, 0, 0, self.width, self.height)

    def text(self) -> str:
        '''The characters without styles, one line per row (for tests and debugging).'''
        return '\n'.join(''.join(c for c, _ in row).rstrip() for row in self.rows)


class Region:
    '''A rectangle of a Buffer to draw in. Coordinates are relative to its top
    left, and drawing outside it is clipped.'''

    def __init__(self, buffer : Buffer, x : int, y : int, width : int, height : int):
        # Clip to the buffer.
        x2, y2 = min(x + max(width, 0), buffer.width), min(y + max(height, 0), buffer.height)
        self.buffer = buffer
        self.x, self.y = max(x, 0), max(y, 0)
        self.width, self.height = max(0, x2 - self.x), max(0, y2 - self.y)
        # Where this region's (0, 0) is, which can be outside the clip.
        self.origin = (x, y)

    def sub(self, x : int, y : int, width : int, height : int) -> 'Region':
        '''A region inside this one (clipped to it).'''
        ox, oy = self.origin
        r = Region(self.buffer, ox + x, oy + y, width, height)
        # Clip to this region as well as the buffer.
        x1, y1 = max(r.x, self.x), max(r.y, self.y)
        x2 = min(r.x + r.width, self.x + self.width)
        y2 = min(r.y + r.height, self.y + self.height)
        r.x, r.y, r.width, r.height = x1, y1, max(0, x2 - x1), max(0, y2 - y1)
        return r

    def _set(self, ax : int, ay : int, cell : Cell):
        '''Write one cell at absolute (ax, ay), keeping wide characters whole.'''
        row = self.buffer.rows[ay]
        if row[ax][0] == WIDE and ax > 0:
            row[ax - 1] = BLANK          # overwriting the right half of a wide char
        if ax + 1 < len(row) and row[ax + 1][0] == WIDE:
            row[ax + 1] = BLANK          # overwriting the left half
        row[ax] = cell

    def put(self, x : int, y : int, rich : Rich, style : Style = PLAIN) -> int:
        '''Draw rich text on one line from (x, y); newlines aren't special, use
        put_lines. Returns the column after the text.'''
        ox, oy = self.origin
        ay = oy + y
        if not self.y <= ay < self.y + self.height:
            return x + rich_width(rich)
        left, right = self.x, self.x + self.width
        ax = ox + x
        for text, s in spans(rich, style):
            for c in text:
                w = char_width(c)
                if w == 0:
                    continue
                if ax >= left and ax + w <= right:
                    self._set(ax, ay, (c, s))
                    if w == 2:
                        self._set(ax + 1, ay, (WIDE, s))
                elif ax < right and ax + w > left:
                    # Half a wide char sticks out of the region: pad instead.
                    for i in range(w):
                        if left <= ax + i < right:
                            self._set(ax + i, ay, (' ', s))
                ax += w
        return ax - ox

    def put_lines(self, x : int, y : int, lines : list[list[tuple[str, Style]]] | Rich, style : Style = PLAIN):
        '''Draw several lines (from split_lines or parse_ansi, or rich text with newlines).'''
        if isinstance(lines, str) or (lines and not isinstance(lines[0], list)):
            lines = split_lines(lines)
        for i, line in enumerate(lines):
            self.put(x, y + i, line, style)

    def put_ansi(self, x : int, y : int, text : str, base : Style = PLAIN):
        self.put_lines(x, y, parse_ansi(text, base))

    def fill(self, style : Style = PLAIN, char : str = ' '):
        if not self.width:
            return
        cell = (char, style)
        for ay in range(self.y, self.y + self.height):
            row = self.buffer.rows[ay]
            if self.x > 0 and row[self.x][0] == WIDE:
                row[self.x - 1] = BLANK
            end = self.x + self.width
            if end < len(row) and row[end][0] == WIDE:
                row[end] = BLANK
            row[self.x:end] = [cell] * self.width

    def clear(self):
        self.fill()
