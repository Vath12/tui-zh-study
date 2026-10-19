from src.tui import DIM, FILL, Column, Key, Text, Widget
from .questions import QuestionMode


class Identify(QuestionMode):
    '''See characters written stroke by stroke, type what they are.

    Type the characters on the command line and press Enter; each one is
    marked right or wrong by position, with the pinyin shown green or red.
    Enter again for the next question. Each result also has 'guess': the
    character typed for it ('' if you typed fewer).

    Up and down (with the command line empty) change the difficulty and ask
    a new question: 1 is one word (or character) at a time, 2 is a few words
    together, up to MAX_SHOWN characters. It's kept in the state as
    'difficulty'.'''

    name = 'identify'
    label = 'Identify'

    @property
    def difficulty(self) -> int:
        return self.state.get('difficulty', 1)

    @property
    def one_word(self) -> bool:
        return self.difficulty == 1

    def handle_key(self, key : Key) -> bool:
        if key.name not in ('up', 'down'):
            return False
        new = 2 if key.name == 'up' else 1
        if new != self.difficulty:
            self.state['difficulty'] = new
            self.next_question()
        self.ctx.notify(f'difficulty {new}: ' + ('one word at a time' if new == 1 else 'a few words together'))
        return True

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
            return ['What are these characters? Type them, then Enter.\n', (f'{self.score()}   {self.level()}', DIM)]
        typed = ''.join(r['guess'] or '·' for r in self.answered)
        return [self.verdict(), f'   it was {self.answer}, you typed {typed}\n', (f'{self.score()}   {self.level()}   Enter: next', DIM)]

    def level(self) -> str:
        return f'difficulty {self.difficulty}/2 (↑↓)'
