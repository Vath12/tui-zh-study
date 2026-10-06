"""Pinyin: splitting it into syllables, tone marks and tone numbers, and
reading what someone typed (wǒ, wo3, ni3 hao3, nǐhǎo) to check it."""
import re
import unicodedata

# The tone marks: vowel -> its marks for tones 1-4.
MARKS = {v: m for v, m in zip("aeiouü", ["āáǎà", "ēéěè", "īíǐì", "ōóǒò", "ūúǔù", "ǖǘǚǜ"])}
TONE_MARKS = {m: t for marks in MARKS.values() for t, m in enumerate(marks, 1)}   # ǎ -> 3
TONELESS = str.maketrans({m: v for v, marks in MARKS.items() for m in marks})   # ǎ -> a

INITIALS = ["zh", "ch", "sh", *"bpmfdtnlgkhjqxrzcsyw"]
FINALS = """a o e ai ei ao ou an en ang eng ong er i ia ie iao iu ian in iang ing
    iong u ua uo uai ui uan un uang ueng ü üe üan ün ue""".split()
SYLLABLES = {i + f for i in INITIALS for f in FINALS}
# Syllables with no initial. Mid-word these always follow an apostrophe (可爱 kě'ài),
# so they're only allowed at the start of a chunk; otherwise 可能 kěnéng -> kěn|éng.
BARE = set("a o e ai ei ao ou an en ang eng er".split())
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


def tone(syllable: str) -> int:
    """A syllable's tone, 1-4, or 5 for the neutral tone (no mark). Ǎi is 3 too."""
    return next((TONE_MARKS[c] for c in syllable.lower() if c in TONE_MARKS), 5)


# Tone numbers -> tone marks

# Combining marks, for letters with no precomposed marked form (ê, and m n ng hm hng).
_COMBINING = {1: "\u0304", 2: "\u0301", 3: "\u030c", 4: "\u0300"}
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
    if c.lower() in MARKS:
        marked = MARKS[c.lower()][tone - 1]
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


# What someone typed

# A syllable as (letters without tone marks, tone 1-5), 5 being the neutral tone.
Syllable = tuple[str, int]


def syllable(marked: str) -> Syllable:
    """A syllable written with a tone mark (or none) as (letters, tone): "hǎo" -> ("hao", 3)."""
    return marked.lower().translate(TONELESS), tone(marked)


def parse(typed: str) -> list[Syllable] | None:
    """What someone typed, as syllables, or None if it isn't pinyin.

    Tone marks or numbers (wǒ, wo3) or a mix; a number goes after its
    syllable, and a syllable with no number or mark is the neutral tone
    (xie4xie, or xie4xie5; 0 works for 5 too). v and u: are ü. Spaces and
    apostrophes between syllables are optional."""
    text = typed.strip().lower().replace("u:", "ü").replace("v", "ü")
    text = re.sub(r"[\s'’-]+", "", text)
    if not text:
        return None
    out = []
    # Chunks of letters, each with the tone number after it if there is one.
    for letters, digit in re.findall(r"([^\d]+)(\d?)", text):
        if not re.fullmatch(r"[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]+", letters):
            return None
        parts = _split_erhua(letters)
        if parts is None:
            return None
        syllables = [syllable(p) for p in parts]
        if digit:
            t = 5 if digit == "0" else int(digit)
            if not 1 <= t <= 5:
                return None
            # The number is the last syllable's tone, or the one before erhua's r (nar3).
            i = -2 if len(syllables) > 1 and syllables[-1][0] == "r" else -1
            syllables[i] = (syllables[i][0], t)
        out += syllables
    return out


def _split_erhua(letters: str) -> list[str] | None:
    """Letters as syllables, with erhua's r as a syllable of its own (the
    儿 of 一点儿, yìdiǎnr or yi4dian3r) when that's the only way they split."""
    if letters == "r":
        return ["r"]
    parts = split_pinyin(letters)
    if parts is None and letters.endswith("r") and (rest := split_pinyin(letters[:-1])):
        parts = [*rest, "r"]
    return parts


def check(typed: str, readings: list[list[str]]) -> list[tuple[str, bool]] | None:
    """Check typed pinyin against the readings of each character (a list
    per character of the tone-marked readings that count as right).
    Returns, per character, (what was typed for it, in tone marks, '' if
    nothing, and whether it's one of its readings), or None if what was
    typed isn't pinyin."""
    syllables = parse(typed)
    if syllables is None:
        return None
    # Erhua again: zhèr reads as one syllable, but 这儿 wants zhè + r.
    if len(syllables) == len(readings) - 1 and readings[-1] == ["r"] and syllables[-1][0].endswith("r"):
        letters, t = syllables[-1]
        syllables[-1:] = [(letters[:-1], t), ("r", 5)]
    out = []
    for i, options in enumerate(readings):
        if i >= len(syllables):
            out.append(("", False))
            continue
        guess = syllables[i]
        out.append((mark_syllable(*guess), any(syllable(o) == guess for o in options)))
    return out
