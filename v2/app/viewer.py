from src.vocabulary.hsk import HSKDictionary

from .strokes import CharacterStrip, StrokeLook, has_strokes
from .tui import DIM, Column, CommandInput, Screen, Setting, Text
from .tui.screens import SettingsMenu

MAX_CHARS = 8
PINYIN_MODES = ['show', 'hide']


class ViewerScreen(Screen):
    '''Type characters and watch them written stroke by stroke, with their
    pinyin: the last `n_chars` characters you typed, as big as fits. The
    pinyin comes from the whole input, so characters in a word get the word's
    reading (谢谢 xièxie, 银行 yínháng). Tab opens the settings menu, and
    /commands work in the input.'''

    def __init__(self, look : StrokeLook):
        self.n_chars = 4
        self.pinyin_mode = 'show'
        self.typed : list[tuple[str, list[str]]] = []   # the characters (with strokes) last typed

        self.strip = CharacterStrip(look, pinyin=lambda: self.pinyin_mode == 'show')
        self.input = CommandInput(on_text=self.text_changed, hint='Tab: menu')
        status = Text(self.status, DIM, height=1, wrap=False, priority=1)
        super().__init__(Column(self.strip, status, self.input), bindings={'tab': self.open_menu})

        self.settings = [
            Setting('chars', 'Chars', [str(n) for n in range(1, MAX_CHARS + 1)], lambda: str(self.n_chars),
                    self.set_n_chars, f'how many characters to show side by side (1-{MAX_CHARS})'),
            Setting('pinyin', 'Pinyin', PINYIN_MODES, lambda: self.pinyin_mode,
                    lambda mode: setattr(self, 'pinyin_mode', mode), 'show or hide the pinyin'),
        ]

    def open_menu(self):
        self.app.push(SettingsMenu())

    def status(self):
        return self.app.message or ('' if self.strip.slots else 'type a character')

    def text_changed(self, text : str):
        # Animate the last characters that have stroke data; leave the current
        # ones up if there aren't any (e.g. the input was just cleared).
        chars = [(c, p) for c, p in HSKDictionary.text_pinyin(text) if has_strokes(c)]
        if chars:
            self.typed = chars
            self.strip.show(chars[-self.n_chars:])
            self.app.notify('')
        elif text.strip():
            self.app.notify('no stroke data for that')

    def set_n_chars(self, n : str):
        self.n_chars = int(n)
        self.strip.show(self.typed[-self.n_chars:])
        return f'showing {self.n_chars} character{"s" if self.n_chars > 1 else ""}'
