import random

from src.tui import BOLD, DIM, FILL, GREEN, RED, Align, Column, Key, Layers, Text, Widget, fg
from src.vocabulary.numbers import PINYIN, random_number, to_chinese

from ..strokes import CharacterStrip
from .base import StudyMode

# difficulty -> (biggest number, most characters it's written with)
DIFFICULTIES = {
    1: (10,4), 
    2: (99,4), 
    3: (999,4), 
    4: (9_999,4), 
    5: (99_999,4), 
    6: (999_999,5),
    7: (999_999_999_999,5), 
    8: (999_999_999_999,6), 
    9: (999_999_999_999,7), 
    10:(999_999_999_999,8),
}

MAX_STROKES = 10   # longer numbers are shown as text: too many characters to draw


class Numeracy(StudyMode):
    '''See a number in Chinese characters (一千零五), type it in digits (1005).

    Up and down (with the command line empty) change the difficulty, 1 to
    10, and ask a new question. Each difficulty is a biggest number and the
    most characters it can take to write (see DIFFICULTIES): 1 is up to 10
    in at most 4 characters; 7 is up to the hundreds of billions, but only
    ones written in 5 characters or fewer (五千万, 三亿零五). Commas and
    spaces in the answer are ignored (1,005). After answering, the pinyin
    is shown under each character, green if you were right.

    State, in the session under 'numeracy': difficulty, results (one per
    question: {'number', 'guess', 'correct', 'difficulty'}), and question
    (the one on screen, if it isn't answered yet: {'number', 'difficulty'}).'''

    name = 'numeracy'
    label = 'Numeracy'
    ready = True

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rng = random.Random()
        self.phase = 'answering'          # or 'result'
        self.number = 0
        self.chinese = ''
        self.last : dict | None = None    # the result just given
        self.strip = CharacterStrip(ctx.look, pinyin=lambda: self.phase == 'result', max_size=None)

    def initial_state(self) -> dict:
        return {'difficulty': 1, 'results': [], 'question': None}

    @property
    def difficulty(self) -> int:
        return self.state['difficulty']

    # Questions

    def start(self):
        question = self.state['question']
        if question and question['difficulty'] == self.difficulty:
            self.show(question)
        else:
            self.next_question()

    def next_question(self):
        maximum, max_chars = DIFFICULTIES[self.difficulty]
        number = random_number(self.rng, maximum, max_chars, avoid=self.number)   # not the same twice in a row
        self.state['question'] = {'number': number, 'difficulty': self.difficulty}
        self.save()
        self.show(self.state['question'])

    def show(self, question : dict):
        self.number = question['number']
        self.chinese = to_chinese(self.number)
        long = len(self.chinese) > MAX_STROKES
        self.strip.show([] if long else [(c, [PINYIN[c]]) for c in self.chinese])
        self.phase = 'answering'
        self.ctx.notify(None)

    # Input

    def handle_key(self, key : Key) -> bool:
        if key.name not in ('up', 'down'):
            if key.name == 'enter' and self.phase == 'result':
                self.next_question()
                return True
            return False
        new = max(1, min(10, self.difficulty + (1 if key.name == 'up' else -1)))
        if new != self.difficulty:
            self.state['difficulty'] = new
            self.next_question()
        maximum, max_chars = DIFFICULTIES[new]
        self.ctx.notify(f'difficulty {new}: up to {maximum:,}, at most {max_chars} characters')
        return True

    def entered(self, text : str) -> bool:
        if self.phase == 'result':
            self.next_question()
            return True
        typed = text.replace(',', '').replace(' ', '').replace('_', '')
        if not typed:
            return True
        if not typed.isdigit():
            self.ctx.notify(f'type the number in digits, like {self.number if self.number < 10 else 42}')
            return True
        guess = int(typed)
        self.last = {'number': self.number, 'guess': guess, 'correct': guess == self.number,
                     'difficulty': self.difficulty}
        self.state['results'].append(self.last)
        self.state['question'] = None
        self.save()
        self.strip.pinyin_styles = [fg(GREEN if self.last['correct'] else RED)] * len(self.chinese)
        self.phase = 'result'
        self.ctx.notify(None)
        return True

    # Drawing

    def view(self) -> Widget:
        text = Align(Text(lambda: ' '.join(self.chinese), BOLD, wrap=True), visible=lambda: not self.strip.slots)
        return Column(Layers(self.strip, text, height=FILL), Text(self.line, height=2), height=FILL)

    def score(self) -> str:
        results = self.state['results']
        return f'difficulty {self.difficulty}/10 (↑↓)   {sum(r["correct"] for r in results)}/{len(results)} right'

    def line(self):
        if self.phase == 'answering':
            return ['What number is this? Type it in digits, then Enter.\n', (self.score(), DIM)]
        r = self.last
        reading = ' '.join(PINYIN[c] for c in self.chinese)
        if r['correct']:
            verdict = [(f'✓ {r["number"]:,}', fg(GREEN, bold=True)), f'   {reading}\n']
        else:
            verdict = [(f'✗ it was {r["number"]:,}', fg(RED, bold=True)), f', you typed {r["guess"]:,}   {reading}\n']
        return verdict + [(f'{self.score()}   Enter: next', DIM)]
