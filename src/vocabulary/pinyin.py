import re

INITIALS = ["zh", "ch", "sh", *"bpmfdtnlgkhjqxrzcsyw"]
FINALS = """a o e ai ei ao ou an en ang eng ong er i ia ie iao iu ian in iang ing
    iong u ua uo uai ui uan un uang ueng ü üe üan ün ue""".split()
SYLLABLES = {i + f for i in INITIALS for f in FINALS}
# Syllables with no initial. Mid-word these always follow an apostrophe (可爱 kě'ài),
# so they're only allowed at the start of a chunk; otherwise 可能 kěnéng -> kěn|éng.
BARE = set("a o e ai ei ao ou an en ang eng er".split())
TONELESS = str.maketrans("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ", "aaaaeeeeiiiioooouuuuüüüü")
LONGEST = 6  # letters in the longest syllable (zhuang)


def split_pinyin(pinyin: str) -> list[str] | None:
    """Split a word's pinyin into syllables, e.g. "xièxie" -> ["xiè", "xie"].
    Returns None if it can't be split cleanly."""
    syllables = []
    for chunk in re.split(r"[\s'’-]+", pinyin):
        parts = _split_chunk(chunk)
        if parts is None:
            return None
        syllables += parts
    return syllables


def _split_chunk(chunk: str) -> list[str] | None:
    # Match on a toneless copy (same length) and slice the original, longest syllable first.
    plain = chunk.lower().translate(TONELESS)

    def split(start: int) -> list[str] | None:
        if start == len(plain):
            return []
        for end in range(min(len(plain), start + LONGEST), start, -1):
            syllable = plain[start:end]
            if syllable in SYLLABLES or (start == 0 and syllable in BARE):
                if (rest := split(end)) is not None:
                    return [chunk[start:end], *rest]
        return None

    return split(0)


def has_tone(syllable: str) -> bool:
    return syllable.translate(TONELESS) != syllable
