import re
from dataclasses import dataclass
from pathlib import Path

from .pinyin import has_tone, split_pinyin

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

    @classmethod
    def _load_lazy(cls):
        if cls.entries is not None:
            return
        cls.entries = unique_entries(parse_hsk_pinyin())
        for e in cls.entries:
            cls.by_word.setdefault(e.word, []).append(e)
            for c in dict.fromkeys(e.word):
                cls.by_char.setdefault(c, []).append(e)

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
