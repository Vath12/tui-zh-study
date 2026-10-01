import time

from blessed import Terminal

from .menu import Menu
from .stroke_session import StrokeSession

FPS = 30
PROMPT = '> '


class BlessedStrokeApp:
    '''A full-screen blessed app for StrokeSession: the animated characters,
    their pinyin and a status line at the top, then the input line, and the
    menu (see Menu) at the bottom. Enter clears the input (running it first if
    it's a /command); Tab switches between typing and the menu; Ctrl-C or
    Ctrl-D quits. The input line edits like a basic prompt: left/right,
    home/end, backspace and delete.'''

    def __init__(self):
        self.term = Terminal()
        self.running = True
        self.session = StrokeSession(on_quit=self.quit)
        self.menu = Menu(self.session)
        # blessed passes colors through as they are, so match the terminal.
        if self.term.number_of_colors < 1 << 24:
            self.session.terminal_colors = '256'
        self.text = ''
        self.cursor = 0          # position in self.text
        self.last_frame = ''
        self.last_size = (0, 0)

    def quit(self):
        self.running = False

    # Input

    def handle_key(self, key):
        name = key.name if key.is_sequence else None
        before = self.text
        if key == '\x04':                                  # Ctrl-D
            self.quit()
            return
        if self.menu.focused and self.menu.handle_key(key):
            return
        if name == 'KEY_TAB' or key == '\t':
            self.menu.focused = True
        elif name == 'KEY_ENTER' or key in ('\r', '\n'):
            self.session.submit(self.text)
            self.text, self.cursor = '', 0
        else:
            self.edit_text(key)
        if self.text != before:
            self.session.input_changed(self.text)

    def edit_text(self, key) -> bool:
        '''Line editing for the input: typing, backspace/delete, left/right,
        home/end. Returns whether the key was one of those.'''
        name = key.name if key.is_sequence else None
        if name == 'KEY_BACKSPACE' or key in ('\x7f', '\x08'):
            if self.cursor:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif name == 'KEY_DELETE':
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif name == 'KEY_LEFT':
            self.cursor = max(0, self.cursor - 1)
        elif name == 'KEY_RIGHT':
            self.cursor = min(len(self.text), self.cursor + 1)
        elif name == 'KEY_HOME' or key == '\x01':          # Ctrl-A
            self.cursor = 0
        elif name == 'KEY_END' or key == '\x05':           # Ctrl-E
            self.cursor = len(self.text)
        elif not key.is_sequence and key.isprintable() and key:
            self.text = self.text[:self.cursor] + key + self.text[self.cursor:]
            self.cursor += len(key)
        else:
            return False
        return True

    # Output

    def frame(self) -> str:
        '''The whole screen as one string, written in one go to avoid flicker.'''
        s = self.session
        chars = s.characters().split('\n') if s.slots else []
        under = [s.pinyin()] if s.show_pinyin else []
        cursor = None if self.menu.focused else self.term.length(PROMPT + self.text[:self.cursor])
        return self.compose(chars, under, s.status(), self.input_line(), cursor)

    def compose(self, top : list[str], under : list[str], status : str, bottom : str, cursor : int | None) -> str:
        '''Lay out a screen. From the bottom: the menu (if focused), then
        `bottom` (the input line) just above it, then `top` (the characters)
        and `under` (their pinyin) filling the rest, with `status` last. If
        `top` is too tall it's cut off at the bottom, so `under` and the status
        line always show. `cursor` is the column for the cursor on the bottom
        line, or None to hide it.'''
        t = self.term
        menu = self.menu.lines(t)   # empty unless the menu is focused
        bottom_row = max(0, t.height - len(menu) - 1)
        lines = top[:max(0, bottom_row - 1 - len(under))] + under
        lines += [''] * (bottom_row - len(lines))
        lines = lines[:bottom_row]
        if lines:
            lines[-1] = t.dim(status)
        lines += [bottom] + menu

        out = [t.home]
        for y, line in enumerate(lines[:t.height]):
            out.append(t.move_xy(0, y) + t.truncate(line, t.width) + t.normal + t.clear_eol)
        if cursor is None:
            out.append(t.hide_cursor)
        else:
            out.append(t.normal_cursor + t.move_xy(min(cursor, t.width - 1), bottom_row))
        return ''.join(out)

    def input_line(self) -> str:
        '''The prompt and what you've typed, with a hint for the menu at the
        right while it's hidden (if there's room).'''
        t = self.term
        line = PROMPT + self.text
        if not self.menu.focused:
            room = t.width - t.length(line) - len(Menu.HINT) - 1
            if room >= 2:
                line += ' ' * room + t.dim(Menu.HINT)
        return line

    def draw(self):
        size = (self.term.width, self.term.height)
        if size != self.last_size:
            print(self.term.clear, end='')
            self.last_size, self.last_frame = size, ''
        self.fit()
        frame = self.frame()
        if frame != self.last_frame:
            print(frame, end='', flush=True)
            self.last_frame = frame

    def fit(self):
        '''Size what's shown to the window, before each frame.'''
        # Show as many characters as fit the width (which depends on the rendering mode too).
        self.session.set_n_chars(self.session.fit_chars(self.term.width))

    def run(self):
        t = self.term
        with t.fullscreen(), t.cbreak():
            try:
                while self.running:
                    started = time.monotonic()
                    self.session.tick()
                    self.draw()
                    # Wait for a key until the next frame is due, then take any others already typed.
                    key = t.inkey(timeout=max(0, 1 / FPS - (time.monotonic() - started)))
                    while key and self.running:
                        self.handle_key(key)
                        key = t.inkey(timeout=0)
            except KeyboardInterrupt:  # Ctrl-C
                pass


if __name__ == '__main__':
    BlessedStrokeApp().run()
