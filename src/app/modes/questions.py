import random

from v2.vocabulary.hsk import HSKDictionary

from ..quiz.questions import make_question
from ..strokes import CharacterStrip, has_strokes
from ..tui import DIM, GREEN, RED, fg
from .base import StudyMode

MAX_SHOWN = 6   # most characters in one question


class HistoryWeights:
    '''How likely each character is to come up, from a mode's results: how
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


class QuestionMode(StudyMode):
    '''A mode that asks questions made of words from the wordlists that are
    on in Vocabulary, weighted by HistoryWeights: a few whole words, 1 to
    max_chars characters in all, or one word if one_word is set. Words with
    a character that has no strokes or no pinyin are left out.

    `strip` shows the question's characters (as big as the window allows);
    subclasses decide when, and what an answer is, and pass record() a result
    for each character.

    State, in the session under the mode's name:
      shown     how many characters have been shown in all. Each character
                gets the next index as it's shown, so a question showing
                A B C uses 0, 1, 2 and leaves shown at 3.
      results   one per character answered: {'index', 'char', 'correct', ...}
                plus whatever else the mode records (Identify: 'guess').
      question  the question on screen and not answered yet, if any:
                {'words', 'start'} (the index of its first character), so
                it's still there after a restart.'''

    max_chars = MAX_SHOWN
    one_word = False
    ready = True

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rng = random.Random()
        self.phase = 'answering'          # 'answering', 'result' (just answered), or 'empty' (no words)
        self.answered : list[dict] = []   # the results of the question just answered
        self.words : list[str] = []       # the question's words
        self.readings : list[tuple[str, list[str]]] = []   # its characters and their pinyin
        self._usable : dict[str, bool] = {}
        self.strip = CharacterStrip(ctx.look, pinyin=self.pinyin_shown, max_size=None)

    def initial_state(self) -> dict:
        return {'shown': 0, 'results': [], 'question': None}

    def pinyin_shown(self) -> bool:
        '''Whether the strip shows the pinyin under the characters.'''
        return self.phase == 'result'

    # Questions

    def usable(self, word : str) -> bool:
        if word not in self._usable:
            self._usable[word] = (len(word) <= self.max_chars and all(map(has_strokes, word))
                                  and all(p for _, p in HSKDictionary.words_pinyin([word])))
        return self._usable[word]

    def pool(self) -> list[str]:
        return [w for w in self.ctx.wordlists.words() if self.usable(w)]

    def pick(self, pool : list[str]) -> list[str]:
        weights = HistoryWeights(self.state)
        if self.one_word:
            return [self.rng.choices(pool, weights=list(map(weights.word, pool)))[0]]
        return make_question(pool, self.rng, weights, self.max_chars)

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
            self.words, self.readings = [], []
            self.strip.show([])
            return
        self.ctx.notify(None)   # whatever the last question said is old news
        state = self.state
        words = self.pick(pool)
        state['question'] = {'words': words, 'start': state['shown']}
        state['shown'] += sum(map(len, words))
        self.save()
        self.show(state['question'])

    def show(self, question : dict):
        self.words = question['words']
        self.readings = HSKDictionary.words_pinyin(self.words)
        self.strip.show(self.readings)
        self.phase = 'answering'

    @property
    def answer(self) -> str:
        return ''.join(self.words)

    def record(self, results : list[dict]):
        '''Save the results of the question on screen, one per character
        ({'correct', ...}; 'index' and 'char' are filled in), and show them.'''
        state = self.state
        start = state['question']['start']
        self.answered = [{'index': start + i, 'char': c, **r} for i, (c, r) in enumerate(zip(self.answer, results))]
        state['results'] += self.answered
        state['question'] = None
        self.save()
        self.strip.pinyin_styles = [fg(GREEN) if r['correct'] else fg(RED) for r in self.answered]
        self.phase = 'result'
        self.ctx.notify(None)

    # Text

    def prompt(self) -> str:
        '''The question as pinyin, a word at a time: "bàba hǎo".'''
        out, i = [], 0
        for word in self.words:
            out.append(''.join(p[0] for _, p in self.readings[i:i + len(word)]))
            i += len(word)
        return ' '.join(out)

    def score(self) -> str:
        results = self.state['results']
        right = sum(r['correct'] for r in results)
        return f'{right}/{len(results)} right   {self.state["shown"]} shown'

    def verdict(self):
        '''How the question just answered went, as rich text.'''
        n = sum(r['correct'] for r in self.answered)
        return (f'{n}/{len(self.answered)} right', fg(GREEN if n == len(self.answered) else RED, bold=True))

    EMPTY = [('No words to show: turn a wordlist on in Vocabulary (Tab), then press Enter.', DIM)]
