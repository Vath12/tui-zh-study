from typing import TextIO

from .cells import BLANK, WIDE, Buffer, Cell
from .style import sgr

# Terminals that support it hold the screen until the end of a frame, so it
# never shows half drawn; the rest ignore these.
SYNC_START = '\x1b[?2026h'
SYNC_END = '\x1b[?2026l'


def move(x : int, y : int) -> str:
    return f'\x1b[{y + 1};{x + 1}H'


class Renderer:
    '''Writes Buffers to the terminal, sending only what changed since the
    last one: for each row that differs, the span from its first to its last
    changed cell.

    depth is the terminal's colors, 'truecolor' or '256'; styles are converted
    when they're written, so widgets can always use rgb.'''

    def __init__(self, out : TextIO, depth : str = 'truecolor'):
        self.out = out
        self.depth = depth
        self.previous : list[list[Cell]] | None = None

    def reset(self):
        '''Forget what's on screen (e.g. after a resize): the next frame is drawn in full.'''
        self.previous = None

    def frame(self, buffer : Buffer, cursor : tuple[int, int] | None) -> str:
        '''The output that turns the last frame into this one. cursor is where
        to show the cursor, or None to hide it.'''
        out = [SYNC_START]
        prev = self.previous
        if prev is None or len(prev) != buffer.height or (prev and len(prev[0]) != buffer.width):
            out.append('\x1b[0m\x1b[2J')
            prev = [[BLANK] * buffer.width for _ in range(buffer.height)]

        for y, row in enumerate(buffer.rows):
            old = prev[y]
            if row == old:
                continue
            start = next(x for x in range(len(row)) if row[x] != old[x])
            end = next(x for x in range(len(row) - 1, -1, -1) if row[x] != old[x]) + 1
            # Don't start or end in the middle of a wide character.
            if row[start][0] == WIDE and start > 0:
                start -= 1
            if end < len(row) and row[end][0] == WIDE:
                end += 1
            out.append(move(start, y))
            style = None
            for x in range(start, end):
                c, s = row[x]
                if c == WIDE:
                    continue
                if s is not style:
                    out.append(sgr(s, self.depth))
                    style = s
                out.append(c)
            out.append('\x1b[0m')

        if cursor is None:
            out.append('\x1b[?25l')
        else:
            x, y = cursor
            out.append(move(max(0, min(x, buffer.width - 1)), max(0, min(y, buffer.height - 1))) + '\x1b[?25h')
        out.append(SYNC_END)
        self.previous = [row[:] for row in buffer.rows]
        return ''.join(out)

    def draw(self, buffer : Buffer, cursor : tuple[int, int] | None):
        self.out.write(self.frame(buffer, cursor))
        self.out.flush()
