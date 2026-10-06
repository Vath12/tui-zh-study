'''Reading CC-CEDICT definitions.

An entry's definitions are separated by /. Most are meanings (senses), but
some are notes about the word, in set forms: "CL:個|个[ge4]" (its measure
words), "variant of 瞭[liao4]", "see ...", "used in 道行[dao4 heng2]" (a
reading that's only found in that word; "used in place names" is a
meaning), "abbr. for ...", "surname Hao", "also pr. [di4]". Within a meaning, "; " separates
near-synonyms (appropriate; proper), and a leading "(...)" says how it's
used: (bound form), (literary), (Tw), (before a verb)... Other words are
referred to as traditional|simplified[pinyin], or simplified[pinyin] when
the two are the same.'''
import re
from dataclasses import dataclass, field

NOTE_KINDS = {
    'classifier': re.compile(r'^CL:'),
    'variant': re.compile(r'^(?:[\w-]+ )*variant of ', re.I),
    'see': re.compile(r'^see(?: also)? ', re.I),
    'used_in': re.compile(r'^used in [^\s\[]+\[', re.I),   # used in 道行[...]; not "used in place names
    'abbreviation': re.compile(r'^abbr\. (?:for|of|to) ', re.I),
    'surname': re.compile(r'^surname ', re.I),
    'pronunciation': re.compile(r'^(?:also|Taiwan|old) pr\. ', re.I),
}
# All the note kinds as one pattern (for Polars, which uses Rust's regex syntax): a
# /-separated part matching it is a note, anything else is a sense.
NOTE_PATTERN = '^(?:' + '|'.join(
    f'(?i:{p.pattern[1:]})' if p.flags & re.I else p.pattern[1:] for p in NOTE_KINDS.values()) + ')'
REFERENCE = re.compile(r'(?:([^\s|\[\],;:()]+)\|)?([^\s|\[\],;:()]+)\[([^\]]+)\]')


@dataclass
class Reference:
    '''Another word, as definitions refer to them: 打電話|打电话[da3 dian4 hua4].'''
    simplified : str
    traditional : str
    pinyin : str


@dataclass
class Sense:
    '''One meaning: its glosses (near-synonyms: ['appropriate', 'proper']),
    and the labels before it ('bound form', 'literary', 'before a verb', ...).'''
    glosses : list[str]
    labels : list[str] = field(default_factory=list)
    references : list[Reference] = field(default_factory=list)

    def __str__(self) -> str:
        return ''.join(f'({l}) ' for l in self.labels) + '; '.join(self.glosses)


@dataclass
class Note:
    '''Something about the word that isn't a meaning. kind is a key of NOTE_KINDS.'''
    kind : str
    text : str
    references : list[Reference] = field(default_factory=list)


@dataclass
class Reading:
    '''One pronunciation of a word (with one traditional form), and what it means.'''
    pinyin : str          # tone numbers, as in CEDICT: hao3
    pinyin_marked : str   # tone marks: hǎo
    traditional : str
    senses : list[Sense]
    notes : list[Note]


@dataclass
class Entry:
    '''A word and its readings, in dictionary order.'''
    word : str
    readings : list[Reading]

    @property
    def senses(self) -> list[Sense]:
        return [s for r in self.readings for s in r.senses]


def references(text : str) -> list[Reference]:
    return [Reference(simp, trad or simp, pinyin) for trad, simp, pinyin in REFERENCE.findall(text)]


def _split_outside_brackets(text : str, sep : str) -> list[str]:
    '''text split at sep, except inside (...) or [...].'''
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        c = text[i]
        if c in '([':
            depth += 1
        elif c in ')]':
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(sep, i):
            parts.append(text[start:i])
            i += len(sep)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def sense(text : str) -> Sense:
    '''One meaning: leading "(...)" labels, then its glosses split at "; ".
    A meaning that's all in parentheses, like (completed action marker),
    is its own gloss rather than a label.'''
    labels, rest = [], text.strip()
    while (m := re.match(r'^\(([^()]*)\)\s*', rest)) and rest[m.end():].strip():
        labels.append(m.group(1))
        rest = rest[m.end():]
    return Sense(_split_outside_brackets(rest, '; '), labels, references(text))


def parse_definitions(definitions : str) -> tuple[list[Sense], list[Note]]:
    '''A CEDICT definitions string (the part between the outer /s, split at
    /) as its senses and its notes.'''
    senses, notes = [], []
    for part in definitions.split('/'):
        part = part.strip()
        if not part:
            continue
        kind = next((k for k, pattern in NOTE_KINDS.items() if pattern.match(part)), None)
        if kind:
            notes.append(Note(kind, part, references(part)))
        else:
            senses.append(sense(part))
    return senses, notes
