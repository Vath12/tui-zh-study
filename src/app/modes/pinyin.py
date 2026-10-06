from src.vocabulary.pinyin import check
from ..tui import DIM, FILL, Column, Text, Widget
from .questions import QuestionMode


class Pinyin(QuestionMode):
    '''See a word or a character written stroke by stroke, type its pinyin.

    Tone marks or numbers both work, with or without spaces: wǒ or wo3,
    nǐhǎo or ni3 hao3 (see vocabulary.pinyin.check). The right pinyin is the HSK
    word's; a character on its own can be any of its readings (好 hǎo or
    hào). Each syllable is marked right or wrong, with the right pinyin shown
    green or red. Each result also has 'guess': the syllable typed for that
    character, in tone marks ('' if you typed fewer).'''

    name = 'pinyin'
    label = 'Pinyin'
    one_word = True

    def entered(self, text : str) -> bool:
        if self.phase != 'answering':
            self.next_question()
            return True
        if not text.strip():
            return True
        checked = check(text, [p for _, p in self.readings])
        if checked is None:
            self.ctx.notify(f'"{text.strip()}" isn\'t pinyin: type it like wo3 or wǒ')
            return True
        self.record([{'guess': guess, 'correct': right} for guess, right in checked])
        return True

    def view(self) -> Widget:
        return Column(self.strip, Text(self.line, height=2), height=FILL)

    def line(self):
        if self.phase == 'empty':
            return self.EMPTY
        if self.phase == 'answering':
            return ['What\'s the pinyin? Type it (wo3 or wǒ), then Enter.\n', (self.score(), DIM)]
        typed = ' '.join(r['guess'] or '·' for r in self.answered)
        return [self.verdict(), f'   {self.answer} is {self.prompt()}, you typed {typed}\n',
                (f'{self.score()}   Enter: next', DIM)]
