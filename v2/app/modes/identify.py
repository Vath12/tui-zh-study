from ..tui import DIM, FILL, Column, Text, Widget
from .questions import QuestionMode


class Identify(QuestionMode):
    '''See characters written stroke by stroke, type what they are.

    Type the characters on the command line and press Enter; each one is
    marked right or wrong by position, with the pinyin shown green or red.
    Enter again for the next question. Each result also has 'guess': the
    character typed for it ('' if you typed fewer).'''

    name = 'identify'
    label = 'Identify'

    def entered(self, text : str) -> bool:
        if self.phase != 'answering':
            self.next_question()
            return True
        typed = ''.join(text.split())
        if typed:
            self.record([{'guess': typed[i] if i < len(typed) else '', 'correct': i < len(typed) and typed[i] == c}
                         for i, c in enumerate(self.answer)])
        return True

    def view(self) -> Widget:
        return Column(self.strip, Text(self.line, height=2), height=FILL)

    def line(self):
        if self.phase == 'empty':
            return self.EMPTY
        if self.phase == 'answering':
            return ['What are these characters? Type them, then Enter.\n', (self.score(), DIM)]
        typed = ''.join(r['guess'] or '·' for r in self.answered)
        return [self.verdict(), f'   it was {self.answer}, you typed {typed}\n', (f'{self.score()}   Enter: next', DIM)]
