import random
from pathlib import Path

from src.vocabulary.hsk import HSKDictionary
from ..wordlists import VOCAB_DIR

from ..strokes import CharacterStrip, StrokeLook
from src.tui import (BOLD, DIM, FILL, GREEN, RED, Align, Column, CommandInput, Key, Layers, Screen, Setting, Text,
                   fg)
from src.tui.screens import SettingsMenu
from .questions import CharWeights, make_question, question_pool

# mode name -> what you do in it
MODES = {
    'read': 'see the strokes, type the characters',
    'write': 'see the pinyin, write the characters, then check',
}


class QuizScreen(Screen):
    '''A quiz on your vocab. The quiz picks the characters (see question_pool),
    weighted towards ones you haven't seen in a while or keep getting wrong.

      read   The characters are shown as animated strokes. Type them (the
             exact sequence) and press Enter; you're told how many you got
             right, with the pinyin colored to match. Enter again for the next.
      write  You're given pinyin, whole words at a time (bàba māma, not
             bà ba mā ma). Write the characters down, then press Space to
             reveal the strokes and check. Mark yourself right (y) or wrong
             (n), then Enter to submit and get the next one.

    `state` is where you are in a question: 'answering' or 'result' in read
    mode, 'writing' in write mode (with `revealed` and `marked`). Tab opens
    the settings menu, which has a Mode row.'''

    def __init__(self, look : StrokeLook, mode : str = 'read', source : Path = VOCAB_DIR):
        self.rng = random.Random()
        self.weights = CharWeights()
        self.pool = question_pool(source)
        if not self.pool:
            raise SystemExit(f'no usable words in {source}')
        self.mode = mode
        self.correct = 0
        self.answered = 0
        self.state = ''

        self.strip = CharacterStrip(look, pinyin=lambda: self.state != 'answering',
                                    visible=lambda: self.state != 'writing' or self.revealed)
        big_prompt = Align(Text(self.prompt, BOLD, wrap=False), visible=lambda: self.state == 'writing' and not self.revealed)
        self.input = CommandInput(on_enter=self.answer_typed, hint='Tab: menu', visible=lambda: self.state == 'answering')
        controls = Text(self.controls, DIM, wrap=False, visible=lambda: self.state != 'answering')
        status = Text(self.status, DIM, wrap=False, height=1, priority=1)
        super().__init__(Column(Layers(self.strip, big_prompt, height=FILL), status,
                                Layers(self.input, controls, height=1, priority=1)),
                         bindings={'tab': lambda: self.app.push(SettingsMenu())})

        self.settings = [Setting('mode', 'Mode', list(MODES), lambda: self.mode, self.set_mode,
                                 f'quiz mode: {", ".join(MODES)}')]
        self.next_question()

    # Questions

    def next_question(self):
        self.words = make_question(self.pool, self.rng, self.weights)
        self.answer = ''.join(self.words)
        self.weights.asked(self.answer)
        self.readings = HSKDictionary.words_pinyin(self.words)
        self.strip.show(self.readings)
        self.state = 'answering' if self.mode == 'read' else 'writing'
        self.revealed = False
        self.marked : bool | None = None   # write mode: did you get it right?
        self.result = ''                   # read mode: what you typed, once answered
        self.focused = self.input if self.state == 'answering' else None
        if self.app:
            self.app.notify('')

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

    def set_mode(self, mode : str) -> str:
        self.mode = mode
        self.next_question()
        return f'mode: {mode} ({MODES[mode]})'

    # Input

    def answer_typed(self, text : str):
        '''Enter in read mode: check what you typed.'''
        if not text.strip():
            return False
        typed = ''.join(text.split())
        self.result = typed
        # A character counts as right if it's in the right place,
        # as long as you typed the right number of them.
        chars_right = ''.join(a for a, b in zip(self.answer, typed) if a == b) if len(typed) == len(self.answer) else ''
        self.record(typed == self.answer, chars_right)
        self.strip.pinyin_styles = [fg(GREEN) if i < len(typed) and typed[i] == c else fg(RED)
                                    for i, c in enumerate(self.answer)]
        self.state = 'result'
        self.focused = None
        return None

    def handle_key(self, key : Key) -> bool:
        name = key.name
        if self.state == 'result' and name == 'enter':
            self.next_question()
        elif self.state == 'writing' and name == 'space':
            self.revealed = not self.revealed
            if self.revealed:
                self.strip.restart()
        elif self.state == 'writing' and name in ('y', 'Y', 'n', 'N'):
            self.marked = name in ('y', 'Y')
        elif self.state == 'writing' and name == 'enter':
            if self.marked is None:
                self.app.notify('mark yourself first: y if you got it right, n if not')
            else:
                self.record(self.marked, self.answer if self.marked else '')
                self.next_question()
        else:
            return False
        return True

    # Output

    def score(self) -> str:
        return f'score {self.correct}/{self.answered}'

    def status(self):
        if self.app.message:
            return self.app.message
        if self.state == 'answering':
            return f'What are these characters? Type them.   {self.score()}'
        if self.state == 'result':
            n = sum(i < len(self.result) and self.result[i] == c for i, c in enumerate(self.answer))
            color = GREEN if n == len(self.answer) else RED
            return [(f'You got {n}/{len(self.answer)}  "{self.result}" vs "{self.answer}"', fg(color)),
                    f'  {self.prompt()}   {self.score()}']
        return ['Write this: ', (self.prompt(), BOLD), f'   {self.score()}']

    def controls(self):
        if self.state == 'result':
            return 'Enter: next question   Tab: menu'
        mark = {True: ('✓ right', fg(GREEN)), False: ('✗ wrong', fg(RED)), None: ('not marked', DIM)}[self.marked]
        return [f'Space: {"hide" if self.revealed else "show"} strokes   y/n: I got it right/wrong (', mark,
                ')   Enter: submit   Tab: menu']
