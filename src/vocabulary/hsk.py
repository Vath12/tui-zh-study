import re
from dataclasses import dataclass
from pathlib import Path

from .pinyin import has_tone, split_pinyin, yi_bu_sandhi

HSK_DIR = Path(__file__).parent.parent.parent / "resources" / "hsk"
LEVELS = ["1", "2", "3", "4", "5", "6", "7-9"]


@dataclass
class HSKEntry:
    id: int
    level: str         # level the word is introduced at, e.g. "1"
    levels: list[str]  # all levels it's listed under, e.g. ["1", "2", "4"]
    word: str          # homograph number stripped, e.g. "本1" -> "本"
    pinyin: str        # tone marks, as in the source, e.g. "bàba"
    pos: list[str]     # parts of speech, e.g. ["动", "名"]; later-level senses are
                       # bracketed in the source ("形、（副）") but unwrapped here
    sense: int | None  # homograph number from the source, if any


def parse_line(line: str) -> HSKEntry:
    """One tab-separated line of an HSK_Level_N_pinyin.txt file."""
    id_, lvl, word, pinyin, pos = line.split("\t")
    homograph = re.fullmatch(r"(.+?)(\d+)", word)
    levels = re.findall(r"[\d-]+", lvl)
    return HSKEntry(
        id=int(id_),
        level=levels[0],
        levels=levels,
        word=homograph.group(1) if homograph else word,
        pinyin=pinyin,
        pos=[p.strip("（）") for p in pos.split("、") if p],
        sense=int(homograph.group(2)) if homograph else None,
    )


def parse_hsk_pinyin(pinyin_dir: Path = HSK_DIR / "pinyin") -> dict[str, list[HSKEntry]]:
    """Parse HSK_Level_N_pinyin.txt files into {level: [HSKEntry, ...]}.

    A word with senses at several levels (level field "1（2）（4）") appears in
    each of those levels' files, with the same id."""
    by_level = {}
    for level in LEVELS:
        lines = (pinyin_dir / f"HSK_Level_{level}_pinyin.txt").read_text(encoding="utf-8").splitlines()
        by_level[level] = [parse_line(line) for line in lines if line.strip()]
    return by_level


def unique_entries(by_level: dict[str, list[HSKEntry]]) -> list[HSKEntry]:
    """Every entry once (they repeat across levels), in id order, which is level order."""
    return list({e.id: e for level in LEVELS for e in by_level[level]}.values())


def word_lists(by_level: dict[str, list[HSKEntry]], cumulative: bool = False) -> dict[str, list[str]]:
    """Unique words per level, in source order. With cumulative=True, each
    level also includes the words from all lower levels."""
    lists, seen = {}, {}
    for level in LEVELS:
        words = dict.fromkeys(e.word for e in by_level[level])
        if cumulative:
            seen |= words
            words = seen
        lists[level] = list(words)
    return lists


def pinyin_from_words(char: str, entries: list[HSKEntry]) -> tuple[str, HSKEntry] | None:
    """Take a character's pinyin from the earliest of `entries` whose word
    contains it. Prefers an occurrence with a tone mark (e.g. 谢 from 谢谢
    xièxie gives "xiè", not the neutral second "xie"), falling back to a
    neutral-tone one."""
    neutral = None
    for e in entries:
        syllables = split_pinyin(e.pinyin)
        if syllables is None or len(syllables) != len(e.word):
            continue  # skips erhua (一点儿 yìdiǎnr), optional parts, alternatives
        for c, s in zip(e.word, syllables):
            if c == char:
                if has_tone(s):
                    return s.lower(), e
                neutral = neutral or (s.lower(), e)
    return neutral


class HSKDictionary:
    """The HSK word list, loaded on first use, with lookups by word and character."""

    entries: list[HSKEntry] | None = None
    by_word: dict[str, list[HSKEntry]] = {}
    by_char: dict[str, list[HSKEntry]] = {}  # entries whose word contains the character
    longest: int = 1                         # characters in the longest word
    _syllables: dict[str, list[str] | None] = {}  # word_syllables cache

    @classmethod
    def _load_lazy(cls):
        if cls.entries is not None:
            return
        cls.entries = unique_entries(parse_hsk_pinyin())
        for e in cls.entries:
            cls.by_word.setdefault(e.word, []).append(e)
            for c in dict.fromkeys(e.word):
                cls.by_char.setdefault(c, []).append(e)
        cls.longest = max(map(len, cls.by_word))

    @classmethod
    def lookup(cls, word: str) -> list[HSKEntry]:
        """Entries that are exactly `word`, earliest level first."""
        cls._load_lazy()
        return cls.by_word.get(word, [])

    @classmethod
    def containing(cls, word: str) -> list[HSKEntry]:
        """Other entries whose word contains `word`, earliest level first."""
        cls._load_lazy()
        candidates = cls.by_char.get(word[0], []) if word else []
        return [e for e in candidates if word in e.word and e.word != word]

    @classmethod
    def readings(cls, char: str) -> list[str]:
        """A character's pinyin: each distinct reading it has as an HSK word,
        or, if it isn't one, the reading from the earliest word containing it."""
        if exact := cls.lookup(char):
            return list(dict.fromkeys(e.pinyin for e in exact))
        found = pinyin_from_words(char, cls.containing(char)) if len(char) == 1 else None
        return [found[0]] if found else []

    @classmethod
    def word_syllables(cls, word: str) -> list[str] | None:
        """One syllable per character of an HSK word, from the earliest entry
        whose pinyin lines up with it (e.g. 银行 -> ["yín", "háng"]). An erhua
        word's final r goes to its 儿 (一点儿 yìdiǎnr -> ["yì", "diǎn", "r"]).
        None if `word` isn't an HSK word or its pinyin doesn't line up."""
        if word not in cls._syllables:
            cls._syllables[word] = cls._find_syllables(word)
        return cls._syllables[word]

    @classmethod
    def _find_syllables(cls, word: str) -> list[str] | None:
        for e in cls.lookup(word):
            pinyin = e.pinyin.lower()
            syllables = split_pinyin(pinyin)
            if syllables is not None and len(syllables) == len(word):
                return syllables
            # Erhua: the 儿 is just an r on the syllable before (这儿 zhèr).
            if word.endswith("儿") and pinyin.endswith("r"):
                syllables = split_pinyin(pinyin[:-1])
                if syllables is not None and len(syllables) == len(word) - 1:
                    return [*syllables, "r"]
        return None

    @classmethod
    def segment(cls, text: str) -> list[str]:
        """Split text into HSK words, using as few pieces as possible (so
        longer words win). Anything that isn't part of a word is its own
        one-character piece."""
        cls._load_lazy()
        # best[i]: fewest pieces for text[:i], and the length of the last piece.
        best = [(0, 0)] + [(len(text) + 1, 1)] * len(text)
        for end in range(1, len(text) + 1):
            for size in range(1, min(cls.longest, end) + 1):
                if size > 1 and cls.word_syllables(text[end - size:end]) is None:
                    continue
                pieces = best[end - size][0] + 1
                if pieces < best[end][0]:
                    best[end] = (pieces, size)
        words, end = [], len(text)
        while end:
            size = best[end][1]
            words.append(text[end - size:end])
            end -= size
        return words[::-1]

    @classmethod
    def text_pinyin(cls, text: str) -> list[tuple[str, list[str]]]:
        """Each character of `text` with its pinyin in context: the syllable
        from the HSK word it's part of (谢谢 -> xiè, xie), or else its own
        readings (好 -> hǎo, hào), with 一 and 不 changing tone to fit the
        next syllable (一个 -> yí gè). Characters with no pinyin get []."""
        return cls.words_pinyin(cls.segment(text))

    @classmethod
    def words_pinyin(cls, words: list[str]) -> list[tuple[str, list[str]]]:
        """Like text_pinyin, for text that's already split into words. A word
        that isn't in HSK (a name like 玛丽) gets each character's own readings."""
        result, alone = [], []  # alone[i]: result[i] isn't part of a word
        for word in words:
            syllables = cls.word_syllables(word) if len(word) > 1 else None
            if syllables:
                result += [(c, [s]) for c, s in zip(word, syllables)]
                alone += [False] * len(word)
            else:
                result += [(c, cls.readings(c)) for c in word]
                alone += [True] * len(word)
        # Words already have 一 and 不 in the right tone (一点儿 yìdiǎnr), so
        # only change the ones standing alone, from the next syllable.
        for i, (char, readings) in enumerate(result):
            if alone[i] and char in "一不" and len(readings) == 1 and i + 1 < len(result) and result[i + 1][1]:
                prev = result[i - 1][0] if i else None
                result[i] = (char, [yi_bu_sandhi(char, readings[0], result[i + 1][1][0], prev)])
        return result
