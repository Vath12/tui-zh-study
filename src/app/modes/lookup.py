from src.tui import BOLD, DIM, Column, Fill, Text, Widget, fg, CYAN
from src.vocabulary.cedict import REFERENCE
from src.vocabulary.dictionary import Dictionary
from src.vocabulary.pinyin import numbers_to_marks

from ..strokes import CharacterStrip, has_strokes
from .base import StudyMode

RECENT = 20        # lookups kept in the session


def readable(text : str) -> str:
    '''CEDICT's references made readable: 冊|册[ce4] -> 册 (cè), 忘不了[wang4 bu5 liao3] -> 忘不了 (wàngbuliǎo).'''
    return REFERENCE.sub(lambda m: f'{m.group(2)} ({numbers_to_marks(m.group(3))})', text)


class Lookup(StudyMode):
    '''Look up a character or word: type it on the command line and press
    Enter. Its strokes are drawn, with each character's reading in the word
    underneath, and below them what it means: each reading (pinyin, and the
    traditional form if it's different), its meanings, numbered, and notes
    like its measure words. Something that isn't in the dictionary just
    gets its strokes.

    State, in the session under 'dictionary': current (what's shown) and
    recent (the last RECENT lookups, newest last).'''

    name = 'dictionary'
    label = 'Dictionary'
    ready = True

    def __init__(self, ctx):
        super().__init__(ctx)
        self.word = ''
        self.entry = None
        self.strip = CharacterStrip(ctx.look, pinyin=True, max_size=None, height=Fill(1))

    def initial_state(self) -> dict:
        return {'current': '', 'recent': []}

    def start(self):
        self.look_up(self.state['current'], remember=False)

    def entered(self, text : str) -> bool:
        word = ''.join(text.split())
        if word:
            self.look_up(word)
        return True

    def look_up(self, word : str, remember : bool = True):
        self.word = word
        self.entry = Dictionary.entry(word) if word else None
        self.strip.show([(c, ['/'.join(p)] if p else []) for c, p in Dictionary.char_readings(word)] if word else [])
        if remember and word and (self.entry or self.strip.slots):   # not ones that found nothing
            recent = [w for w in self.state['recent'] if w != word] + [word]
            self.state.update(current=word, recent=recent[-RECENT:])
            self.save()
        missing = [c for c in word if not has_strokes(c)]
        if word and not self.strip.slots:
            self.ctx.notify(f'no strokes for {word}' + ('' if self.entry else ', and it isn\'t in the dictionary'))
        elif missing:
            self.ctx.notify(f'no strokes for {"".join(missing)}')
        else:
            self.ctx.notify(None)

    # Drawing

    def view(self) -> Widget:
        definition = Text(self.definition, wrap=True, height=Fill(1), visible=lambda: self.entry is not None)
        hint = Text(self.hint, DIM, height=1)
        return Column(self.strip, definition, hint, height=Fill(1))

    def hint(self):
        if not self.word:
            return 'Type a character or word, then Enter, to look it up.'
        recent = [w for w in self.state['recent'] if w != self.word][-6:]
        return f'{self.word}: {"not in the dictionary, " if not self.entry else ""}' + \
               (f'recent: {" ".join(reversed(recent))}' if recent else 'type another to look it up')

    def definition(self):
        out = []
        for reading in self.entry.readings:
            out.append((reading.pinyin_marked, fg(CYAN, bold=True)))
            if reading.traditional != self.entry.word:
                out.append((f'  {reading.traditional}', DIM))
            out.append('\n')
            for i, sense in enumerate(reading.senses, 1):
                out.append((f'{i:>3}. ', DIM))
                for label in sense.labels:
                    out.append((f'({readable(label)}) ', DIM))
                out.append(readable('; '.join(sense.glosses)) + '\n')
            for note in reading.notes:
                if note.kind == 'classifier':
                    text = 'measure words: ' + ', '.join(f'{r.simplified} ({numbers_to_marks(r.pinyin)})' for r in note.references)
                else:
                    text = readable(note.text)
                out.append((f'     {text}\n', DIM))
        return out
