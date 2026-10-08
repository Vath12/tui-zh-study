import functools
import hashlib
from pathlib import Path

import polars as pl

from ..util import load_hashed_tsv
from .cedict import NOTE_PATTERN, Entry, Reading, Sense, parse_definitions
from .pinyin import numbers_to_marks

RESOURCE_DIR = Path(__file__).parent.parent.parent / 'resources'
CEDICT_PATH = RESOURCE_DIR / 'cc-cedict.tsv'
FREQUENCY_PATH = RESOURCE_DIR / 'jun-da_frequency.tsv'

MAX_SEGMENT = 8   # longest word segment() tries (CEDICT has some very long idioms)

# The TSVs install.py writes.
CEDICT_SCHEMA = {'simplified': pl.String, 'traditional': pl.String, 'pinyin': pl.String, 'definitions': pl.String}
JUNDA_SCHEMA = {'char': pl.String, 'count': pl.Int64, 'pinyin': pl.String, 'english': pl.String}


def charset_key(text : str) -> str:
    '''The unique characters of text, sorted: 你好你 and 好你 both give 你好.'''
    return ''.join(sorted(set(text)))


def charset_hash(text : str) -> str:
    '''A stable hash of the unique characters of text, whatever their order
    or how often they repeat (md5 of charset_key, so it's the same every run).'''
    return hashlib.md5(charset_key(text).encode('utf-8')).hexdigest()


def has_meaning(definitions : pl.Expr) -> pl.Expr:
    '''Whether a CEDICT definitions string has at least one sense: a /-separated
    part that isn't a note (see cedict.NOTE_KINDS).'''
    return (definitions.str.split('/').list.eval(
        (pl.element().str.strip_chars() != '') & ~pl.element().str.strip_chars().str.contains(NOTE_PATTERN))
        .list.any())


def loaded(fn):
    '''For Dictionary's methods: load the resources first (only the first
    time; see Dictionary.init). Goes under @classmethod.'''
    @functools.wraps(fn)
    def run(cls, *args, **kwargs):
        cls.init()
        return fn(cls, *args, **kwargs)
    return run


class Dictionary():
    '''CC-CEDICT and Jun Da's character frequency list. They're loaded by
    init(), or else by the first lookup (every lookup is @loaded).

      cedict     one row per word: simplified, then a list per reading (in
                 dictionary order, the same length): traditional, pinyin
                 (tone numbers, CEDICT style), pinyin_marked (tone marks, as
                 one word: ni3 hao3 -> nǐhǎo) and definitions (CEDICT's, split
                 by /; see entry() for them read); and charset_hash (see
                 charset_hash). 好 is one row with two readings, hao3 and hao4.
      frequency  one row per character: char, count, pinyin, english, and
                 rank (1 is the most common).'''

    cedict : pl.DataFrame | None = None
    frequency : pl.DataFrame | None = None
    words : frozenset[str] = frozenset()   # every simplified word, for segment()
    longest : int = 1                      # characters in the longest word segment() looks for

    # When loading: leave out readings with no meaning, only notes (variant of ...,
    # see ..., used in ...), which have nothing to show, and words left with none.
    # Set it before the first lookup (or init()) to keep them.
    drop_undefined : bool = True

    @classmethod
    def init(cls):
        '''Load the resources now, rather than on the first lookup (to
        control when the wait is). Does nothing if they're already loaded.'''
        cls._l_load_dict()
        cls._l_load_char_frequency()

    @classmethod
    def _l_load_dict(cls):
        if cls.cedict is not None:
            return
        cls.cedict = load_hashed_tsv(CEDICT_PATH, CEDICT_SCHEMA)
        if cls.drop_undefined:
            cls.cedict = cls.cedict.filter(has_meaning(pl.col('definitions')))
        cls._precompute_marked_pinyin()
        # One row per word, its readings as lists, in the order they're in the dictionary.
        cls.cedict = cls.cedict.group_by('simplified', maintain_order=True).agg(
            'traditional', 'pinyin', 'pinyin_marked', 'definitions')
        cls._precompute_charset_hash()
        cls.words = frozenset(cls.cedict['simplified'].to_list())
        cls.longest = min(MAX_SEGMENT, max(map(len, cls.words)))

    @classmethod
    def _l_load_char_frequency(cls):
        if cls.frequency is not None:
            return
        df = load_hashed_tsv(FREQUENCY_PATH, JUNDA_SCHEMA)
        cls.frequency = df.with_row_index('rank', offset=1)   # the file is in frequency order

    @classmethod
    #precompute stable order hash of unique chars IE 你好你 and 好你 should resolve to the same hash
    def _precompute_charset_hash(cls):
        cls.cedict = cls.cedict.with_columns(
            pl.col('simplified').map_elements(charset_hash, return_dtype=pl.String).alias('charset_hash'))

    @classmethod
    def _precompute_marked_pinyin(cls):
        # Convert each distinct pinyin once, then join back.
        readings = cls.cedict.select(pl.col('pinyin').unique())
        marked = readings.with_columns(
            pl.col('pinyin').map_elements(numbers_to_marks, return_dtype=pl.String).alias('pinyin_marked'))
        cls.cedict = cls.cedict.join(marked, on='pinyin', how='left', maintain_order='left')

    # Lookups

    @classmethod
    @loaded
    def lookup(cls, word : str) -> pl.DataFrame:
        '''The word's row (in simplified characters), or no rows if it isn't in the dictionary.'''
        return cls.cedict.filter(pl.col('simplified') == word)

    @classmethod
    @loaded
    def entry(cls, word : str) -> Entry | None:
        '''The word with its readings, each with its senses and notes (see
        cedict.py), or None if it isn't in the dictionary.'''
        rows = cls.lookup(word).rows(named=True)
        if not rows:
            return None
        row = rows[0]
        readings = []
        for trad, pinyin, marked, definitions in zip(row['traditional'], row['pinyin'], row['pinyin_marked'],
                                                     row['definitions']):
            senses, notes = parse_definitions(definitions)
            readings.append(Reading(pinyin, marked, trad, senses, notes))
        return Entry(word, readings)

    @classmethod
    @loaded
    def pinyin(cls, word : str, marked : bool = False) -> list[str]:
        '''The word's readings, in tone numbers (好 -> ['hao3', 'hao4']), or
        with marked, in tone marks (['hǎo', 'hào']), each once.'''
        rows = cls.lookup(word)['pinyin_marked' if marked else 'pinyin'].to_list()
        return list(dict.fromkeys(rows[0])) if rows else []

    @classmethod
    @loaded
    def senses(cls, word : str) -> list[Sense]:
        '''Every meaning of the word, from all its readings (not the notes:
        classifiers, variants, cross-references; see entry() for those).'''
        entry = cls.entry(word)
        return entry.senses if entry else []

    @classmethod
    @loaded
    def definitions(cls, word : str) -> list[str]:
        '''Every meaning of the word as text: (bound form) row; line.'''
        return [str(s) for s in cls.senses(word)]

    @classmethod
    @loaded
    def char_readings(cls, word : str) -> list[tuple[str, list[str]]]:
        '''Each character of a word with its readings there, in tone marks:
        你好 -> [('你', ['nǐ']), ('好', ['hǎo'])], 好 -> [('好', ['hǎo', 'hào'])].
        A word with several readings gives each character every one that
        lines up with it. Text that isn't one word (我们的爸爸) is split into
        words first (我们 的 爸爸), and a piece whose pinyin doesn't line up
        (3D) gives each character its own readings. Readings are lowercase (中 Zhōng, as in China, is zhōng),
        each once. Tones are as CEDICT gives them, with no sandhi (不客气 is
        bù kè qi).'''
        rows = cls.lookup(word).rows(named=True)
        if rows:
            options = [dict() for _ in word]
            for pinyin in rows[0]['pinyin']:
                syllables = pinyin.split()
                if len(syllables) == len(word):
                    for i, syl in enumerate(syllables):
                        options[i][numbers_to_marks(syl).lower()] = None
            if all(options):
                return [(c, list(o)) for c, o in zip(word, options)]
        if len(word) == 1:
            return [(word, [])]
        # Not a word (or no lined-up reading): split it into words if it can be, else characters.
        pieces = cls.segment(word)
        if len(pieces) == 1:
            pieces = list(word)
        return [pair for piece in pieces for pair in cls.char_readings(piece)]

    @classmethod
    @loaded
    def words_pinyin(cls, words : list[str]) -> list[tuple[str, list[str]]]:
        '''char_readings for each word, one after another.'''
        return [pair for w in words for pair in cls.char_readings(w)]

    @classmethod
    @loaded
    def segment(cls, text : str) -> list[str]:
        '''Split text into dictionary words, in as few pieces as possible (so
        longer words win). Anything that isn't part of a word is a piece of
        its own, one character long.'''
        # best[i]: (fewest pieces for text[:i], length of the last piece)
        best = [(0, 0)] + [(len(text) + 1, 1)] * len(text)
        for end in range(1, len(text) + 1):
            for size in range(1, min(cls.longest, end) + 1):
                if size > 1 and text[end - size:end] not in cls.words:
                    continue
                if best[end - size][0] + 1 < best[end][0]:
                    best[end] = (best[end - size][0] + 1, size)
        pieces, end = [], len(text)
        while end:
            size = best[end][1]
            pieces.append(text[end - size:end])
            end -= size
        return pieces[::-1]

    @classmethod
    @loaded
    def text_pinyin(cls, text : str) -> list[tuple[str, list[str]]]:
        '''Each character of text with its readings in context: segment(), then
        char_readings() for each piece (谢谢你 -> xiè, xie, nǐ).'''
        return cls.words_pinyin(cls.segment(text))

    @classmethod
    @loaded
    def with_charset(cls, chars : str) -> pl.DataFrame:
        '''Words made of exactly these characters, in any order and any
        number of times (你好 finds 你好 and 好你, not 你 or 你们).'''
        return cls.cedict.filter(pl.col('charset_hash') == charset_hash(chars))

    @classmethod
    @loaded
    def made_of(cls, chars : str, max_len : int | None = None) -> pl.DataFrame:
        '''Words made only of these characters (any of them, any order),
        e.g. the words you can read if you know chars.'''
        known = list(set(chars))
        df = cls.cedict
        if max_len is not None:
            df = df.filter(pl.col('simplified').str.len_chars() <= max_len)
        return df.filter(pl.col('simplified').str.split('').list.eval(pl.element().is_in(known)).list.all())

    @classmethod
    @loaded
    def char_frequency(cls, char : str) -> dict | None:
        '''A character's row in the frequency list (rank, count, pinyin,
        english), or None if it isn't in it.'''
        rows = cls.frequency.filter(pl.col('char') == char).to_dicts()
        return rows[0] if rows else None

    @classmethod
    @loaded
    def most_common(cls, n : int) -> list[str]:
        '''The n most common characters, most common first.'''
        return cls.frequency.head(n)['char'].to_list()


if __name__ == "__main__":

    import wcwidth

    def c_ljust(text, width, fillchar=" "):
        # Calculate visual width
        display_width = wcwidth.wcswidth(text)
        # Add extra padding needed
        padding_needed = max(0, width - display_width)
        return text + (fillchar * padding_needed)

    # A look at the data (the tests are in _tests/test_dictionary.py).
    import time

    t = time.perf_counter()
    Dictionary.init()
    print(f'loaded {Dictionary.cedict.height:,} words and {Dictionary.frequency.height:,} characters '
          f'in {time.perf_counter() - t:.2f}s')

    for c in Dictionary.most_common(10):
        pron = Dictionary.pinyin(c,True)
        print(c,pron[0] + (f' +{len(pron)-1}' if len(pron)>1 else ''))

    # Words made of the 200 most common characters, sorted by their characters in
    # frequency order: the 的 words first, then 一, 是, ... (then by the 2nd character, and so on).
    rank = {c: i for i, c in enumerate(Dictionary.frequency['char'])}
    n_words = Dictionary.made_of(Dictionary.most_common(20))
    for w in sorted(n_words['simplified'], key=lambda w: [-rank.get(c, len(rank)) for c in w]):
        entry = Dictionary.entry(w)
        for reading in entry.readings:
            print(c_ljust(w,8), reading.pinyin_marked.lstrip().ljust(20), (' / '.join(map(str, reading.senses))))