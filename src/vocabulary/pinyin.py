import re
import unicodedata

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


TONE_MARKS = {c: i % 4 + 1 for i, c in enumerate("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")}


def tone(syllable: str) -> int:
    """A syllable's tone, 1-4, or 5 for the neutral tone (no mark)."""
    return next((TONE_MARKS[c] for c in syllable if c in TONE_MARKS), 5)


def set_tone(syllable: str, new: int) -> str:
    """The syllable with its tone mark changed to tone `new` (1-4)."""
    for i, c in enumerate(syllable):
        if c in TONE_MARKS:
            base = "aaaaeeeeiiiioooouuuuüüüü"["āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ".index(c)]
            marked = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ"["aeiouü".index(base) * 4 + new - 1]
            return syllable[:i] + marked + syllable[i + 1:]
    return syllable


NUMBERS = set("零一二三四五六七八九十百千万亿两第")


def yi_bu_sandhi(char: str, syllable: str, next_syllable: str | None, prev_char: str | None = None) -> str:
    """The tone changes of 一 and 不 that pinyin writes, from the syllable after:
    不 bù -> bú before a 4th tone; 一 yī -> yí before a 4th tone and yì before
    any other tone. At the end (no next syllable) they keep their own tone, and
    so does 一 in ordinals and numbers (第一 dìyī, 十一 shíyī). This doesn't know
    about dates and counting in general, where 一 also stays yī (一月 yīyuè)."""
    if next_syllable is None or tone(next_syllable) == 5:
        return syllable
    if char == "一" and prev_char in NUMBERS:
        return syllable
    if char == "不" and syllable == "bù" and tone(next_syllable) == 4:
        return "bú"
    if char == "一" and syllable == "yī":
        return set_tone(syllable, 2 if tone(next_syllable) == 4 else 4)
    return syllable


# Tone numbers -> tone marks

_MARKED = {v: m for v, m in zip("aeiouü", ["āáǎà", "ēéěè", "īíǐì", "ōóǒò", "ūúǔù", "ǖǘǚǜ"])}
# Combining marks, for letters with no precomposed marked form (ê, and m n ng hm hng).
_COMBINING = {1: "̄", 2: "́", 3: "̌", 4: "̀"}
_VOWELS = "aeiouüê"


def mark_syllable(letters: str, tone: int) -> str:
    """One syllable with its tone mark: ("hao", 3) -> "hǎo". The mark goes on
    a or e if there is one, on the o of ou, else on the last vowel (the
    rule in GB/T 16159, which has no exceptions). Syllables with no vowel
    (the interjections m, n, ng, hm, hng) take it on their m or n. Tone 5
    (neutral) has no mark. Capitals are kept (An -> Ān)."""
    if tone not in _COMBINING:
        return letters
    low = letters.lower()
    if "a" in low:
        i = low.index("a")
    elif "e" in low:
        i = low.index("e")
    elif "ou" in low:
        i = low.index("o")
    elif any(v in low for v in _VOWELS):
        i = max(low.rfind(v) for v in _VOWELS)
    elif low in ("m", "n", "ng", "hm", "hng"):
        i = low.index("m") if "m" in low else low.index("n")
    else:
        return letters  # not a syllable (erhua's r, letters like the D of 3D)
    c = letters[i]
    if c.lower() in _MARKED:
        marked = _MARKED[c.lower()][tone - 1]
        marked = marked.upper() if c.isupper() else marked
    else:
        marked = c + _COMBINING[tone]  # ê, m, n: a combining mark
    # Composed where Unicode has a single character for it (ḿ, ń, ế), so it compares equal.
    return unicodedata.normalize("NFC", letters[:i] + marked + letters[i + 1:])


def numbers_to_marks(pinyin: str, join: bool = True) -> str:
    """Pinyin written with tone numbers, as in CC-CEDICT ("ni3 hao3", "lu:4",
    "Xi1 an1"), in tone marks: "nǐhǎo", "lǜ", "Xī'ān".

    u: and v are ü, e^ is ê; 5 (or no number) is the neutral tone. With
    join, the syllables are written as one word, with an apostrophe before
    one that starts with a, o or e (kě'ài); otherwise they stay apart
    (nǐ hǎo). Anything that isn't a syllable with a tone (r, x, the D of
    "san1 D", CEDICT's "xx5" for an unknown reading) is kept as it is.
    Nothing is changed for tone sandhi: CEDICT gives each syllable's own
    tone (不客气 bu4 ke4 qi5 -> bùkèqi)."""
    out = []
    for word in pinyin.split():
        m = re.fullmatch(r"([A-Za-zü:^]+?)([0-5]?)", word)
        if m is None or m.group(1).lower() == "xx":
            out.append(word)
            continue
        letters = m.group(1).replace("u:", "ü").replace("U:", "Ü").replace("v", "ü").replace("V", "Ü")
        letters = letters.replace("e^", "ê").replace("E^", "Ê")
        syllable = mark_syllable(letters, int(m.group(2)) if m.group(2) else 5)
        if join and out and syllable[:1].lower() in "aoeāáǎàōóǒòēéěè":
            syllable = "'" + syllable
        out.append(syllable)
    return ("" if join else " ").join(out)
