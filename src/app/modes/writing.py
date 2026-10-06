from src.tui import BOLD, DIM, FILL, GREEN, RED, Align, Column, Key, Layers, Text, Widget, fg
from .questions import QuestionMode


class Writing(QuestionMode):
    '''See the pinyin, write the characters (on paper), then check.

    The pinyin is shown a whole word at a time (bàba māma, not bà ba mā ma).
    Space shows the strokes so you can check what you wrote (and hides them
    again), y or n marks yourself right or wrong, and Enter goes on to the
    next question. Every character in the question gets the mark. These keys
    work while the command line is empty.'''

    name = 'writing'
    label = 'Writing'

    def __init__(self, ctx):
        super().__init__(ctx)
        self.revealed = False
        self.marked : bool | None = None

    def pinyin_shown(self) -> bool:
        return True

    def show(self, question : dict):
        super().show(question)
        self.revealed = False
        self.marked = None

    def handle_key(self, key : Key) -> bool:
        name = key.name
        if self.phase != 'answering':
            if name == 'enter':
                self.next_question()
                return True
            return False
        if name == 'space':
            self.revealed = not self.revealed
            if self.revealed:
                self.strip.restart()
        elif name in ('y', 'Y', 'n', 'N'):
            self.marked = name in ('y', 'Y')
        elif name == 'enter':
            if self.marked is None:
                self.ctx.notify('mark yourself first: y if you got it right, n if not')
            else:
                self.record([{'correct': self.marked} for _ in self.answer])
                self.revealed = True
        else:
            return False
        return True

    def view(self) -> Widget:
        prompt = Align(Text(self.prompt, BOLD, wrap=False), visible=lambda: self.phase == 'answering' and not self.revealed)
        strokes = Column(self.strip, visible=lambda: self.revealed or self.phase == 'result', height=FILL)
        return Column(Layers(prompt, strokes, height=FILL), Text(self.line, height=2), height=FILL)

    def line(self):
        if self.phase == 'empty':
            return self.EMPTY
        if self.phase == 'result':
            return [self.verdict(), f'   {self.prompt()} is {self.answer}\n', (f'{self.score()}   Enter: next', DIM)]
        mark = {True: ('✓ right', fg(GREEN)), False: ('✗ wrong', fg(RED)), None: ('not marked', DIM)}[self.marked]
        return ['Write ', (self.prompt(), BOLD), ' down, then check it.\n',
                (f'Space {"hides" if self.revealed else "shows"} strokes · y/n right or wrong (', DIM), mark,
                (f') · Enter submits   {self.score()}', DIM)]
