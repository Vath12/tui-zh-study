"""Numbers written in Chinese characters: 1005 -> 一千零五."""

DIGITS = "零一二三四五六七八九"
UNITS = ["", "十", "百", "千"]           # within a group of four digits
GROUPS = ["", "万", "亿", "万亿"]         # each group of four digits up
PINYIN = {"零": "líng", "一": "yī", "二": "èr", "三": "sān", "四": "sì", "五": "wǔ", "六": "liù", "七": "qī",
          "八": "bā", "九": "jiǔ", "十": "shí", "百": "bǎi", "千": "qiān", "万": "wàn", "亿": "yì", "两": "liǎng"}
LIMIT = 10 ** 16                          # to_chinese handles numbers below this


def _group(n: int) -> str:
    """0 < n < 10000 in characters, with 零 for each run of zeros between digits (1005 一千零五)."""
    out, zero = "", False
    for place in (3, 2, 1, 0):
        digit = n // 10 ** place % 10
        if digit == 0:
            zero = bool(out)       # a zero only counts once something comes before it
            continue
        if zero:
            out += "零"
            zero = False
        out += DIGITS[digit] + UNITS[place]
    return out


def to_chinese(n: int) -> str:
    """A whole number in Chinese characters, as it's written and read:

      groups of four digits, with 万 and 亿:   12345 一万二千三百四十五
      one 零 for a run of zeros inside:          1005 一千零五, 10050 一万零五十
      and before a group under 1000:             100500 十万零五百
      none at the end:                           1500 一千五百, 100000000 一亿
      十, not 一十, at the start:                 15 十五 (but 115 一百一十五)

    It uses 二 throughout (二千), as for reading a number out; 两千 is also
    common in speech. Negative numbers get 负."""
    if n < 0:
        return "负" + to_chinese(-n)
    if n == 0:
        return "零"
    if n >= LIMIT:
        raise ValueError(f"{n} is too big (to_chinese goes up to {LIMIT - 1})")
    groups = []                    # four digits at a time, lowest first
    while n:
        groups.append(n % 10000)
        n //= 10000
    out, gap = "", False
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            gap = bool(out)        # a whole group of zeros between two that aren't
            continue
        if out and (gap or g < 1000):
            out += "零"
        out += _group(g) + GROUPS[i]
        gap = False
    return out[1:] if out.startswith("一十") else out

def random_number(rng, maximum: int, max_chars: int, avoid: int | None = None) -> int:
    """A random number from 0 to maximum, written in at most max_chars
    characters (to_chinese), and not `avoid` if there's anything else.

    It picks a number, then zeroes digits after the leading one, at random,
    until it's short enough: 7,394,021 -> 7,090,001 (七百零九万零一) -> ...
    The leading digit stays, so the number keeps its size. If that still
    isn't short enough (only possible with a very small max_chars), it
    picks again; after many tries it settles for a single digit."""
    for _ in range(1000):
        digits = list(str(rng.randint(0, maximum)))
        lower = [i for i in range(1, len(digits)) if digits[i] != "0"]   # the ones after the leading digit
        rng.shuffle(lower)
        while len(to_chinese(int("".join(digits)))) > max_chars and lower:
            digits[lower.pop()] = "0"
        n = int("".join(digits))
        if len(to_chinese(n)) <= max_chars and n != avoid:
            return n
    return next((d for d in range(min(9, maximum), -1, -1) if d != avoid), 0)



if __name__ == '__main__':
    import random
    print(random_number(random,100000,4))

