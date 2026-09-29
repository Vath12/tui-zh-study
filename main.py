import re
from dataclasses import dataclass
from pathlib import Path

HSK_DIR = Path(__file__).parent / "HSK"
LEVELS = ["1", "2", "3", "4", "5", "6", "7-9"]


@dataclass
class HSKEntry:
    id: int
    level: str
    word: str          # homograph number stripped, e.g. "本1" -> "本"
    pinyin: str        # tone marks, as in the source, e.g. "bàba"
    pos: list[str]     # parts of speech, e.g. ["动", "名"]
    sense: int | None  # homograph number from the source, if any


def parse_hsk_pinyin(pinyin_dir: Path = HSK_DIR / "pinyin") -> dict[str, list[HSKEntry]]:
    """Parse HSK_Level_N_pinyin.txt files into {level: [HSKEntry, ...]}."""
    by_level = {}
    for level in LEVELS:
        entries = []
        path = pinyin_dir / f"HSK_Level_{level}_pinyin.txt"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            id_, lvl, word, pinyin, pos = line.split("\t")
            m = re.fullmatch(r"(.+?)(\d+)", word)
            entries.append(HSKEntry(
                id=int(id_),
                level=lvl,
                word=m.group(1) if m else word,
                pinyin=pinyin,
                pos=[p for p in pos.split("、") if p],
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


if __name__ == "__main__":
    hsk = parse_hsk_pinyin()
    words = word_lists(hsk)
    totals = word_lists(hsk, cumulative=True)
    for level in LEVELS:
        print(f"HSK {level}: {len(hsk[level])} entries, {len(words[level])} words, {len(totals[level])} cumulative")
    print(hsk["1"][:3])
