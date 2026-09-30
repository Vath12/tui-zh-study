import re
from dataclasses import dataclass
from pathlib import Path

HSK_DIR = Path(__file__).parent.parent / "resources" / "hsk"
VOCAB = Path(__file__).parent.parent / "resources" / "vocab"
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


def parse_hsk_pinyin(pinyin_dir: Path = HSK_DIR / "pinyin") -> dict[str, list[HSKEntry]]:
    """Parse HSK_Level_N_pinyin.txt files into {level: [HSKEntry, ...]}.

    A word with senses at several levels (level field "1（2）（4）") appears in
    each of those levels' files, with the same id."""
    by_level = {}
    for level in LEVELS:
        entries = []
        path = pinyin_dir / f"HSK_Level_{level}_pinyin.txt"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            id_, lvl, word, pinyin, pos = line.split("\t")
            m = re.fullmatch(r"(.+?)(\d+)", word)
            levels = re.findall(r"[\d-]+", lvl)
            entries.append(HSKEntry(
                id=int(id_),
                level=levels[0],
                levels=levels,
                word=m.group(1) if m else word,
                pinyin=pinyin,
                pos=[p.strip("（）") for p in pos.split("、") if p],
                sense=int(m.group(2)) if m else None,
            ))
        by_level[level] = entries
    return by_level


def word_lists(by_level: dict[str, list[HSKEntry]], cumulative: bool = False) -> dict[str, list[str]]:
    """Unique words per level, in source order. With cumulative=True, each
    level also includes the words from all lower levels."""
    lists = {}
    seen = []
    for level in LEVELS:
        words = list(dict.fromkeys(e.word for e in by_level[level]))
        if cumulative:
            seen = list(dict.fromkeys(seen + words))
            words = seen
        lists[level] = words
    return lists


INITIALS = ["zh", "ch", "sh", *"bpmfdtnlgkhjqxrzcsyw"]
FINALS = """a o e ai ei ao ou an en ang eng ong er i ia ie iao iu ian in iang ing
    iong u ua uo uai ui uan un uang ueng ü üe üan ün ue""".split()
SYLLABLES = {i + f for i in INITIALS for f in FINALS}
# Syllables with no initial. Mid-word these always follow an apostrophe (可爱 kě'ài),
# so they're only allowed at the start of a chunk; otherwise 可能 kěnéng -> kěn|éng.
BARE = set("a o e ai ei ao ou an en ang eng er".split())
TONELESS = str.maketrans("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ", "aaaaeeeeiiiioooouuuuüüüü")


def split_pinyin(pinyin: str) -> list[str] | None:
    """Split a word's pinyin into syllables, e.g. "xièxie" -> ["xiè", "xie"].
    Returns None if it can't be split cleanly."""
    syllables = []
    for chunk in re.split(r"[\s'’-]+", pinyin):
        # Toneless copy with the same length, so we can match on it and slice the original.
        plain = chunk.lower().translate(TONELESS)

        def split(start: int) -> list[str] | None:
            if start == len(plain):
                return []
            for end in range(min(len(plain), start + 6), start, -1):  # longest first
                if (plain[start:end] in SYLLABLES or start == 0 and plain[:end] in BARE) and (rest := split(end)) is not None:
                    return [chunk[start:end], *rest]
            return None

        parts = split(0)
        if parts is None:
            return None
        syllables += parts
    return syllables


def has_tone(syllable: str) -> bool:
    return syllable.translate(TONELESS) != syllable


def pinyin_from_words(char: str, entries: list[HSKEntry]) -> tuple[str, HSKEntry] | None:
    """Take a character's pinyin from the earliest HSK word containing it.
    Prefers an occurrence with a tone mark (e.g. 谢 from 谢谢 xièxie gives "xiè",
    not the neutral second "xie"), falling back to a neutral-tone one."""
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


@dataclass
class VocabMatch:
    vocab: str
    exact: list[HSKEntry]         # HSK entries whose word is exactly this vocab item
    containing: list[HSKEntry]    # other HSK entries whose word contains it
    pinyin: str | None            # from the earliest exact entry, else from pinyin_from
    pinyin_from: HSKEntry | None  # the word the pinyin was taken from, if not exact


def load_vocab(vocab_dir: Path = VOCAB) -> list[str]:
    """Read every .txt file in vocab_dir, taking the first token of each line
    (so lines can be "字" or "字 pinyin"). Duplicates are dropped."""
    items = []
    for path in sorted(vocab_dir.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.split():
                items.append(line.split()[0])
    return list(dict.fromkeys(items))


def find_vocab_matches(vocab: list[str], by_level: dict[str, list[HSKEntry]]) -> dict[str, VocabMatch]:
    """For each vocab item, find the HSK entries that are exactly that word
    and the entries whose word contains it, both ordered by level. If there's
    no exact entry, a single character's pinyin is taken from the earliest word
    containing it."""
    entries = list({e.id: e for level in LEVELS for e in by_level[level]}.values())
    matches = {}
    for item in vocab:
        exact = [e for e in entries if e.word == item]
        containing = [e for e in entries if item in e.word and e.word != item]
        pinyin, pinyin_from = (exact[0].pinyin, None) if exact else (None, None)
        if not exact and len(item) == 1:
            pinyin, pinyin_from = pinyin_from_words(item, containing) or (None, None)
        matches[item] = VocabMatch(item, exact, containing, pinyin, pinyin_from)
    return matches
