import argparse
import random
import time
from pathlib import Path

from .blessed_ctx import BlessedStrokeApp, PROMPT
from .menu import MenuItem
from .stroke_session import GAP, RENDERING_MODES, SIZE
from .strokes.render import GLYPHS
from .strokes.stroke import HanziStroke
from .vocabulary.hsk import HSKDictionary
from .vocabulary.vocab import VOCAB_DIR, load_vocab

MAX_CHARS = 4  # longest question, in characters
BUILT_LEVELS = {'1', '2', '3'}  # HSK levels of the extra words built from your vocab

# mode name -> what you do in it
MODES = {
    'read': 'see the strokes, type the characters',
    'write': 'see the pinyin, write the characters, then check',
}


def question_pool(source : Path = VOCAB_DIR) -> list[str]:
    '''The words questions are made from: your vocab (a vocab file, or a
    directory of them; see load_vocab), plus the HSK words (up to
    MAX_CHARS long, from BUILT_LEVELS) made only of characters in your vocab,
    like 爸爸 from 爸. Words with a character that has no stroke data or no
    pinyin are left out.'''
    vocab = load_vocab(source)
    known = set(''.join(vocab))
    HSKDictionary._load_lazy()
    HanziStroke._load_lazy()
    built = [w for w, entries in HSKDictionary.by_word.items()
             if 1 < len(w) <= MAX_CHARS and set(w) <= known and entries[0].level in BUILT_LEVELS]
    usable = lambda w: all(c in HanziStroke.stroke_data for c in w) and all(p for _, p in HSKDictionary.words_pinyin([w]))
    return [w for w in dict.fromkeys(vocab + built) if len(w) <= MAX_CHARS and usable(w)]


class CharWeights:
    '''How likely each character is to come up: the number of questions
    since it was last asked, halved for every time you've got it right. So
    characters you haven't seen in a while come back, and ones you know come
    back less. A word's weight is the mean of its characters'.'''

    def __init__(self):
        self.turn = 0
        self.last_asked : dict[str, int] = {}  # character -> turn; never asked counts as turn -1
        self.right : dict[str, int] = {}       # character -> times got right

    def char(self, c : str) -> float:
        return (self.turn - self.last_asked.get(c, -1)) * 0.5 ** self.right.get(c, 0)

    def word(self, w : str) -> float:
        return sum(map(self.char, w)) / len(w)

    def asked(self, chars : str):
        '''A new question with these characters.'''
        self.turn += 1
        for c in chars:
            self.last_asked[c] = self.turn

    def got_right(self, chars : str):
        for c in chars:
            self.right[c] = self.right.get(c, 0) + 1


def make_question(pool : list[str], rng : random.Random, weights : CharWeights) -> list[str]:
    '''A question: a few whole words from the pool, 1 to MAX_CHARS characters
    in all, picked by their weights, without repeating a word if there's
    anything else that fits.'''
    target = rng.randint(1, MAX_CHARS)
    words = []
    while (room := target - sum(map(len, words))) > 0:
        fits = [w for w in pool if len(w) <= room]
        options = [w for w in fits if w not in words] or fits
        words.append(rng.choices(options, weights=list(map(weights.word, options)))[0])
    return words


class TestApp(BlessedStrokeApp):
    '''The blessed stroke app as a quiz. You don't choose the characters, the
    test does, from your vocab (see question_pool). Two modes:

      read   The characters are shown as animated strokes. Type them (the
             exact sequence) and press Enter; you're told if you were right,
             with the pinyin. Enter again for the next one.
      write  You're given pinyin, whole words at a time (bàba māma, not
             bà ba mā ma). Write the characters down, then press Space to
             reveal the strokes and check. Mark yourself right (y) or wrong
             (n), then Enter to submit and get the next one.

    `state` is where you are in a question: 'answering' or 'result' in read
    mode, 'writing' in write mode (with `revealed` and `marked`). Tab opens
    the menu as usual, with a Mode row; Ctrl-C or Ctrl-D quits.'''

    def __init__(self, mode : str = 'read', source : Path = VOCAB_DIR):
        super().__init__()
        self.rng = random.Random()
        self.weights = CharWeights()
        self.pool = question_pool(source)
        if not self.pool:
            raise SystemExit(f'no usable words in {source}')
        self.correct = 0
        self.answered = 0

        # A /mode command and a Mode row in the menu; the test decides when
        # pinyin shows, so drop the Pinyin row.
        self.session.commands['mode'] = (self.cmd_mode, f'test mode: {", ".join(MODES)}')
        self.menu.items = [MenuItem('Mode', 'mode', list(MODES), lambda: self.mode)] + \
            [item for item in self.menu.items if item.command != 'pinyin']
        self.session.set_n_chars(MAX_CHARS)

        self.mode = mode
        self.next_question()

    # Questions

    def next_question(self):
        self.words = make_question(self.pool, self.rng, self.weights)
        self.answer = ''.join(self.words)
        self.weights.asked(self.answer)
        self.readings = HSKDictionary.words_pinyin(self.words)
        self.session.present(self.readings)
        self.state = 'answering' if self.mode == 'read' else 'writing'
        self.revealed = False
        self.marked : bool | None = None   # write mode: did you get it right?
        self.result = ''                   # read mode: what you typed, once answered
        self.text, self.cursor = '', 0
        self.session.message = ''

    def prompt(self) -> str:
        '''The question as pinyin, a word at a time: "bàba hǎo".'''
        out, i = [], 0
        for word in self.words:
            out.append(''.join(p[0] for _, p in self.readings[i:i + len(word)]))
            i += len(word)
        return ' '.join(out)

    def record(self, right : bool, chars_right : str = ''):
        '''Score a question, and the characters in it you got right.'''
        self.answered += 1
        self.correct += right
        self.weights.got_right(chars_right)

    def restart_animations(self):
        for slot in self.session.slots:
            slot.started = time.monotonic()

    def cmd_mode(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in MODES:
            return f'usage: /mode {"|".join(MODES)}  (now {self.mode})'
        self.mode = args[0]
        self.next_question()
        return f'mode: {args[0]} ({MODES[args[0]]})'

    # Input

    def handle_key(self, key):
        name = key.name if key.is_sequence else None
        enter = name == 'KEY_ENTER' or key in ('\r', '\n')
        if key == '\x04':                                  # Ctrl-D
            self.quit()
        elif self.menu.focused and self.menu.handle_key(key):
            pass
        elif name == 'KEY_TAB' or key == '\t':
            self.menu.focused = True
        elif self.state == 'answering':
            if enter and self.text.startswith('/'):
                self.session.submit(self.text)
                self.text, self.cursor = '', 0
            elif enter and self.text.strip():
                self.result = self.text
                typed = ''.join(self.text.split())
                # A character counts as right if it's in the right place,
                # as long as you typed the right number of them.
                chars_right = ''.join(a for a, b in zip(self.answer, typed) if a == b) \
                    if len(typed) == len(self.answer) else ''
                self.record(typed == self.answer, chars_right)
                self.state = 'result'
            elif not enter:
                self.edit_text(key)
        elif self.state == 'result':
            if enter:
                self.next_question()
        elif self.state == 'writing':
            if key == ' ':
                self.revealed = not self.revealed
                if self.revealed:
                    self.restart_animations()
            elif key in ('y', 'Y'):
                self.marked = True
            elif key in ('n', 'N'):
                self.marked = False
            elif enter:
                if self.marked is None:
                    self.session.message = 'mark yourself first: y if you got it right, n if not'
                else:
                    self.record(self.marked, self.answer if self.marked else '')
                    self.next_question()

    # Output

    def score(self) -> str:
        return f'score {self.correct}/{self.answered}'

    def frame(self) -> str:
        t, s = self.term, self.session
        chars = s.characters().split('\n') if s.slots else []
        pinyin = [s.pinyin()]
        message = s.message
        if self.state == 'answering':
            # Strokes only: the pinyin would give it away.
            return self.compose(chars, [], message or f'What are these characters? Type them.   {self.score()}',
                                PROMPT + self.text,
                                None if self.menu.focused else t.length(PROMPT + self.text[:self.cursor]))
        if self.state == 'result':
            if ''.join(self.result.split()) == self.answer:
                verdict = t.green(f'✓ Right: {self.answer}')
            else:
                verdict = t.red(f'✗ You typed {self.result}, it was {self.answer}')
            return self.compose(chars, pinyin, message or f'{verdict}  {self.prompt()}   {self.score()}',
                                t.dim('Enter: next question'), None)
        # writing: just the pinyin until you reveal the strokes.
        mark = {True: t.green('✓ right'), False: t.red('✗ wrong'), None: t.dim('not marked')}[self.marked]
        controls = (f'Space: {"hide" if self.revealed else "show"} strokes   '
                    f'y/n: I got it right/wrong ({mark})   Enter: submit')
        if self.revealed:
            top, under = chars, pinyin
        else:
            # The prompt, big-ish: in the middle of where the characters go.
            top = [''] * (s.rows // 2) + [t.bold(self.prompt().center(t.width))]
            under = []
        status = message or f'Write this: {t.bold(self.prompt())}   {self.score()}'
        return self.compose(top, under, status, controls, None)

    def fit(self):
        '''Fit up to MAX_CHARS characters in the window by shrinking them.'''
        t, s = self.term, self.session
        n = max(1, len(self.answer))
        glyphs = GLYPHS[RENDERING_MODES[s.rendering_mode]]
        cols = (t.width - len(GAP) * (n - 1)) // n          # per character
        rows = t.height - 4                                  # minus pinyin, status, input, a spare
        size = min(SIZE, cols * glyphs.width, rows * glyphs.height)
        size = max(8, size - size % 4)
        s.set_char_size(size)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Quiz yourself on your vocab.')
    parser.add_argument('mode', nargs='?', choices=list(MODES), default='read')
    parser.add_argument('-s', '--source', type=Path, default=VOCAB_DIR,
                        help='vocab .txt file, or a directory of them (default: all of resources/vocab)')
    args = parser.parse_args()
    TestApp(args.mode, args.source).run()
