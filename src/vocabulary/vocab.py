from dataclasses import dataclass
from pathlib import Path

from .hsk import HSKDictionary, HSKEntry, pinyin_from_words

VOCAB_DIR = Path(__file__).parent.parent.parent / "resources" / "vocab"

@dataclass
class VocabMatch:
    vocab: str
    exact: list[HSKEntry]         # HSK entries whose word is exactly this vocab item
    containing: list[HSKEntry]    # other HSK entries whose word contains it
    pinyin: str | None            # from the earliest exact entry, else from pinyin_from
    pinyin_from: HSKEntry | None  # the word the pinyin was taken from, if not exact


def load_vocab(source: Path = VOCAB_DIR) -> list[str]:
    """Read a vocab .txt file, or every .txt file in a directory, taking the
    first token of each line (so lines can be "字" or "字 pinyin"). Lines
    starting with # are comments. Duplicates are dropped."""
    source = Path(source)
    items = []
    for path in [source] if source.is_file() else sorted(source.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.split() and not line.lstrip().startswith("#"):
                items.append(line.split()[0])
    return list(dict.fromkeys(items))


def find_vocab_matches(vocab: list[str]) -> dict[str, VocabMatch]:
    """For each vocab item, the HSK entries that are exactly that word and the
    entries whose word contains it, both ordered by level. If there's no exact
    entry, a single character's pinyin is taken from the earliest word
    containing it."""
    matches = {}
    for item in vocab:
        exact = HSKDictionary.lookup(item)
        containing = HSKDictionary.containing(item)
        pinyin, pinyin_from = (exact[0].pinyin, None) if exact else (None, None)
        if not exact and len(item) == 1:
            pinyin, pinyin_from = pinyin_from_words(item, containing) or (None, None)
        matches[item] = VocabMatch(item, exact, containing, pinyin, pinyin_from)
    return matches
