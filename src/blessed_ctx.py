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
        elif name == 'KEY_BACKSPACE' or key in ('\x7f', '\x08'):
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
        if self.text != before:
            self.session.input_changed(self.text)

    # Output

    def frame(self) -> str:
        '''The whole screen as one string, written in one go to avoid flicker.'''
        t, s = self.term, self.session
        menu = self.menu.lines(t)   # empty unless the menu is focused
        # From the bottom: the menu, then the input line just above it, then
        # the characters and pinyin (unless hidden) filling the rest, with the
        # status line last. If the characters are too tall, they're cut off at
        # the bottom, so the pinyin and status lines always show.
        input_row = max(0, t.height - len(menu) - 1)
        under = [s.pinyin()] if s.show_pinyin else []
        chars = s.characters().split('\n') if s.slots else []
        lines = chars[:max(0, input_row - 1 - len(under))] + under
        lines += [''] * (input_row - len(lines))
        lines = lines[:input_row]
        if lines:
            lines[-1] = t.dim(s.status())
        lines += [self.input_line()] + menu

        out = [t.home]
        for y, line in enumerate(lines[:t.height]):
            out.append(t.move_xy(0, y) + t.truncate(line, t.width) + t.normal + t.clear_eol)
        if self.menu.focused:
            out.append(t.hide_cursor)
        else:
            # The cursor goes where you're typing.
            x = min(t.length(PROMPT + self.text[:self.cursor]), t.width - 1)
            out.append(t.normal_cursor + t.move_xy(x, input_row))
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
        # Show as many characters as fit the width (which depends on the rendering mode too).
        self.session.set_n_chars(self.session.fit_chars(self.term.width))
        frame = self.frame()
        if frame != self.last_frame:
            print(frame, end='', flush=True)
            self.last_frame = frame

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
