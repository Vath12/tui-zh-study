import unittest

import random

from src.vocabulary.numbers import PINYIN, random_number, to_chinese


class TestToChinese(unittest.TestCase):

    CASES = {
        0: '零', 1: '一', 9: '九', 10: '十', 11: '十一', 15: '十五', 20: '二十', 99: '九十九',
        100: '一百', 101: '一百零一', 110: '一百一十', 115: '一百一十五', 999: '九百九十九',
        1000: '一千', 1005: '一千零五', 1050: '一千零五十', 1500: '一千五百', 2008: '二千零八',
        10000: '一万', 10050: '一万零五十', 12345: '一万二千三百四十五', 100500: '十万零五百',
        100010: '十万零一十', 1000000: '一百万', 10000000: '一千万', 100000000: '一亿',
        100000005: '一亿零五', 2000001000: '二十亿零一千', 123456789: '一亿二千三百四十五万六千七百八十九',
        10 ** 12: '一万亿', -5: '负五',
    }

    def test_cases(self):
        for n, want in self.CASES.items():
            with self.subTest(n):
                self.assertEqual(to_chinese(n), want)

    def test_every_character_has_pinyin(self):
        for n in [0, 7, 1005, 123456789, 10 ** 12 - 1, 2000001000]:
            with self.subTest(n):
                self.assertTrue(all(c in PINYIN for c in to_chinese(n).removeprefix('负')))

    def test_too_big(self):
        with self.assertRaises(ValueError):
            to_chinese(10 ** 16)


class TestRandomNumber(unittest.TestCase):

    def test_within_limits(self):
        from src.app.modes.numeracy import DIFFICULTIES
        rng = random.Random(0)
        for level, (maximum, max_chars) in DIFFICULTIES.items():
            with self.subTest(level):
                for _ in range(300):
                    n = random_number(rng, maximum, max_chars)
                    self.assertLessEqual(n, maximum)
                    self.assertLessEqual(len(to_chinese(n)), max_chars)

    def test_avoid(self):
        rng = random.Random(1)
        self.assertTrue(all(random_number(rng, 10, 4, avoid=7) != 7 for _ in range(200)))

    def test_varied(self):
        rng = random.Random(2)
        # Draws this big almost always have 12 digits, so 5 characters leaves forms
        # like 六千零一亿: fewer kinds of number, but still plenty.
        seen = {random_number(rng, 999_999_999_999, 5) for _ in range(300)}
        self.assertGreater(len(seen), 50)

    def test_keeps_the_leading_digit(self):
        # The number drawn first, then zeroed below its leading digit: same length, same first digit.
        for seed in range(200):
            drawn = str(random.Random(seed).randint(0, 999_999_999))
            n = str(random_number(random.Random(seed), 999_999_999, 6))
            with self.subTest(drawn=drawn, n=n):
                self.assertEqual((len(n), n[0]), (len(drawn), drawn[0]))
                self.assertTrue(all(a == b or b == '0' for a, b in zip(drawn, n)))   # only zeroed, never changed


if __name__ == '__main__':
    unittest.main()
