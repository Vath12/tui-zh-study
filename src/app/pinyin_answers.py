'''Reading pinyin that someone typed, in tone marks (wǒ, nǐhǎo), tone
numbers (wo3, ni3hao3, ni3 hao3) or a mix, and checking it against the
right readings.'''
import re

from v2.vocabulary.pinyin import TONELESS, split_pinyin, tone

# A syllable as (letters without tone marks, tone 1-5), 5 being the neutral tone.
Syllable = tuple[str, int]

_MARKS = {v: m for v, m in zip('aeiouü', ['āáǎà', 'ēéěè', 'īíǐì', 'ōóǒò', 'ūúǔù', 'ǖǘǚǜ'])}


def syllable(marked : str) -> Syllable:
    '''A syllable written with a tone mark (or none) as (letters, tone): "hǎo" -> ("hao", 3).'''
    return marked.lower().translate(TONELESS), tone(marked)


def marked(s : Syllable) -> str:
    '''A syllable with its tone mark: ("hao", 3) -> "hǎo". The mark goes on
    a or e if there is one, the o of ou, else the last vowel.'''
    letters, t = s
    if t == 5:
        return letters
    for i in ([letters.find('a'), letters.find('e')] if 'a' in letters or 'e' in letters
              else [letters.find('o') if 'ou' in letters else max(letters.rfind(v) for v in 'iouü')]):
        if i >= 0:
            return letters[:i] + _MARKS[letters[i]][t - 1] + letters[i + 1:]
    return letters


def parse(typed : str) -> list[Syllable] | None:
    '''What someone typed, as syllables, or None if it isn't pinyin.

    Tone numbers go after their syllable (wo3) and a syllable with no number
    or mark is the neutral tone (xie4xie, or xie4xie5; 0 works for 5 too).
    v and u: are ü. Spaces and apostrophes between syllables are optional.'''
    text = typed.strip().lower().replace('u:', 'ü').replace('v', 'ü')
    text = re.sub(r"[\s'’-]+", '', text)
    if not text:
        return None
    out = []
    # Chunks of letters, each with the tone number after it if there is one.
    for letters, digit in re.findall(r'([^\d]+)(\d?)', text):
        if not re.fullmatch(r'[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]+', letters):
            return None
        parts = _split(letters)
        if parts is None:
            return None
        syllables = [syllable(p) for p in parts]
        if digit:
            t = 5 if digit == '0' else int(digit)
            if not 1 <= t <= 5:
                return None
            # The number is the last syllable's tone, or the one before erhua's r (nar3).
            i = -2 if len(syllables) > 1 and syllables[-1][0] == 'r' else -1
            syllables[i] = (syllables[i][0], t)
        out += syllables
    return out


def _split(letters : str) -> list[str] | None:
    '''Letters as syllables, with erhua's r as a syllable of its own (the
    儿 of 一点儿, yìdiǎnr or yi4dian3r) when that's the only way they split.'''
    if letters == 'r':
        return ['r']
    parts = split_pinyin(letters)
    if parts is None and letters.endswith('r') and (rest := split_pinyin(letters[:-1])):
        parts = [*rest, 'r']
    return parts


def check(typed : str, readings : list[list[str]]) -> list[tuple[str, bool]] | None:
    '''Check typed pinyin against the readings of each character (from
    HSKDictionary.words_pinyin: the HSK word's syllable for each character,
    or every reading a character has on its own). Returns, per character,
    (what was typed for it, in tone marks, '' if nothing, and whether it's
    one of its readings), or None if what was typed isn't pinyin.'''
    syllables = parse(typed)
    if syllables is None:
        return None
    # Erhua again: zhèr reads as one syllable, but 这儿 wants zhè + r.
    if len(syllables) == len(readings) - 1 and readings[-1] == ['r'] and syllables[-1][0].endswith('r'):
        letters, t = syllables[-1]
        syllables[-1:] = [(letters[:-1], t), ('r', 5)]
    out = []
    for i, options in enumerate(readings):
        if i >= len(syllables):
            out.append(('', False))
            continue
        guess = syllables[i]
        out.append((marked(guess), any(syllable(o) == guess for o in options)))
    return out
