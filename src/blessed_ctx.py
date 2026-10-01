import time

from blessed import Terminal

from .stroke_session import StrokeSession

FPS = 30
PROMPT = '> '


class BlessedStrokeApp:
    '''A full-screen blessed app for StrokeSession: the animated characters,
    their pinyin and a status line at the top, and an input line at the bottom.
    Enter clears the input (running it first if it's a /command); Ctrl-C or
    Ctrl-D quits. The input line edits like a basic prompt: left/right,
    home/end, backspace and delete.'''

    def __init__(self):
        self.term = Terminal()
        self.running = True
        self.session = StrokeSession(on_quit=self.quit)
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
        lines = (s.characters().split('\n') if s.slots else []) + [s.pinyin()]
        lines += ['']*(t.height-1-len(lines))
        lines[-1] = t.dim(s.status())
        out = [t.home]

        for y, line in enumerate(lines[:t.height - 1]):
            out.append(t.move_xy(0, y) + t.truncate(line, t.width) + t.normal + t.clear_eol)

        out.append(t.move_xy(0, len(lines)) + t.clear_eos)
        # The input line sits at the bottom, with the cursor where you're typing.
        bottom = t.height - 1
        out.append(t.move_xy(0, bottom) + t.truncate(PROMPT + self.text, t.width) + t.clear_eol)
        out.append(t.move_xy(min(t.length(PROMPT + self.text[:self.cursor]), t.width - 1), bottom))
        return ''.join(out)

    def draw(self):
        size = (self.term.width, self.term.height)
        if size != self.last_size:
            # Show as many characters as fit the new width, and redraw from scratch.
            self.session.set_n_chars(self.session.fit_chars(self.term.width))
            print(self.term.clear, end='')
            self.last_size, self.last_frame = size, ''
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
