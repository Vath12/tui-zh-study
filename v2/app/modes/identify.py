import random

from src.vocabulary.hsk import HSKDictionary

from ..quiz.questions import make_question
from ..strokes import CharacterStrip, has_strokes
from ..tui import DIM, FILL, GREEN, RED, Column, Text, Widget, fg
from .base import StudyMode

MAX_SHOWN = 6   # most characters in one question


class HistoryWeights:
    '''How likely each character is to come up, from the results so far: how
    many characters have been shown since it was last shown, halved for every
    time it was got right. So characters you haven't seen in a while come
    back, and ones you know come back less. A word's weight is the mean of
    its characters'.'''

    def __init__(self, state : dict):
        self.shown = state['shown']
        self.last : dict[str, int] = {}
        self.right : dict[str, int] = {}
        for r in state['results']:
            self.last[r['char']] = max(self.last.get(r['char'], -1), r['index'])
            self.right[r['char']] = self.right.get(r['char'], 0) + r['correct']

    def char(self, c : str) -> float:
        return (self.shown - self.last.get(c, -1)) * 0.5 ** self.right.get(c, 0)

    def word(self, w : str) -> float:
        return sum(map(self.char, w)) / len(w)


class Identify(StudyMode):
    '''See characters written stroke by stroke, type what they are.

    Questions are a few whole words (1 to MAX_SHOWN characters in all) from
    the wordlists that are on in Vocabulary, weighted by HistoryWeights.
    Type the characters on the command line and press Enter; each one is
    marked right or wrong by position, with the pinyin shown green or red.
    Enter again for the next question. The characters are as big as the
    window lets them be.

    State, in the session under 'identify':
      shown     how many characters have been shown in all. Each character
                gets the next index as it's shown, so one question showing
                A B C uses 0, 1, 2 and leaves shown at 3.
      results   one per character answered: {'index', 'char', 'guess',
                'correct'}; guess is '' if you typed fewer characters.
      question  the question on screen and not answered yet, if any:
                {'words', 'start'} (the index of its first character), so
                it's still there after a restart.'''

    name = 'identify'
    label = 'Identify'
    ready = True

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rng = random.Random()
        self.phase = 'answering'          # 'answering', 'result' (just answered), or 'empty' (no words)
        self.answered : list[dict] = []   # the results of the question just answered
        self._usable : dict[str, bool] = {}
        self.strip = CharacterStrip(ctx.look, pinyin=lambda: self.phase == 'result', max_size=None)

    def initial_state(self) -> dict:
        return {'shown': 0, 'results': [], 'question': None}

    # Questions

    def usable(self, word : str) -> bool:
        '''Whether a word can be a question: short enough, with strokes and pinyin for every character.'''
        if word not in self._usable:
            self._usable[word] = (len(word) <= MAX_SHOWN and all(map(has_strokes, word))
                                  and all(p for _, p in HSKDictionary.words_pinyin([word])))
        return self._usable[word]

    def pool(self) -> list[str]:
        return [w for w in self.ctx.wordlists.words() if self.usable(w)]

    def start(self):
        question = self.state['question']
        if question:
            self.show(question)
        else:
            self.next_question()

    def next_question(self):
        pool = self.pool()
        if not pool:
            self.phase = 'empty'
            self.strip.show([])
            return
        state = self.state
        words = make_question(pool, self.rng, HistoryWeights(state), MAX_SHOWN)
        state['question'] = {'words': words, 'start': state['shown']}
        state['shown'] += sum(map(len, words))
        self.save()
        self.show(state['question'])

    def show(self, question : dict):
        self.strip.show(HSKDictionary.words_pinyin(question['words']))
        self.phase = 'answering'

    # Answers

    def entered(self, text : str) -> bool:
        if self.phase != 'answering':
            self.next_question()
            return True
        typed = ''.join(text.split())
        if not typed:
            return True
        state = self.state
        question = state['question']
        answer = ''.join(question['words'])
        self.answered = [{'index': question['start'] + i, 'char': c, 'guess': typed[i] if i < len(typed) else '',
                          'correct': i < len(typed) and typed[i] == c}
                         for i, c in enumerate(answer)]
        state['results'] += self.answered
        state['question'] = None
        self.save()
        self.strip.pinyin_styles = [fg(GREEN) if r['correct'] else fg(RED) for r in self.answered]
        self.phase = 'result'
        return True

    # Drawing

    def view(self) -> Widget:
        return Column(self.strip, Text(self.line, height=2), height=FILL)

    def score(self) -> str:
        results = self.state['results']
        right = sum(r['correct'] for r in results)
        return f'{right}/{len(results)} right   {self.state["shown"]} shown'

    def line(self):
        if self.phase == 'empty':
            return [('No words to show: turn a wordlist on in Vocabulary (Tab), then press Enter.', DIM)]
        if self.phase == 'answering':
            return ['What are these characters? Type them, then Enter.\n', (self.score(), DIM)]
        n = sum(r['correct'] for r in self.answered)
        answer = ''.join(r['char'] for r in self.answered)
        typed = ''.join(r['guess'] or '·' for r in self.answered)
        color = GREEN if n == len(self.answered) else RED
        return [(f'{n}/{len(self.answered)} right', fg(color, bold=True)), f'   it was {answer}, you typed {typed}\n',
                (f'{self.score()}   Enter: next', DIM)]
