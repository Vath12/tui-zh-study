import unittest
import unicodedata

from src.vocabulary.pinyin import check, mark_syllable, numbers_to_marks, parse


class TestNumbersToMarks(unittest.TestCase):

    CASES = {
        # the placement rule: a/e, then the o of ou, else the last vowel
        'hao3': 'hǎo', 'xie4 xie5': 'xièxie', 'lou2': 'lóu', 'gui4': 'guì', 'liu2': 'liú',
        'zhong1': 'zhōng', 'er2': 'ér', 'yuan2': 'yuán', 'xiong2': 'xióng',
        # joining syllables, and the apostrophe before a/o/e
        'ni3 hao3': 'nǐhǎo', 'ke3 ai4': "kě'ài", 'Xi1 an1': "Xī'ān",
        # ü written u: or v
        'lu:4': 'lǜ', 'nu:3': 'nǚ', 'lu:e4': 'lüè', 'lv4': 'lǜ',
        # capitals kept
        'An1 hui1': 'Ānhuī', 'Ou1 zhou1': 'Ōuzhōu',
        # erhua, citation tones (no sandhi)
        'yi1 dian3 r5': 'yīdiǎnr', 'bu4 ke4 qi5': 'bùkèqi',
        # no vowel, ê
        'm2': 'ḿ', 'ng2': 'ńg', 'n3': 'ň', 'hm5': 'hm', 'e^4': 'ề',
        # not pinyin: kept as it is
        'san1 D da3 yin4': 'sānDdǎyìn', 'xx5': 'xx5',
    }

    def test_cases(self):
        for numbered, want in self.CASES.items():
            with self.subTest(numbered):
                self.assertEqual(numbers_to_marks(numbered), want)

    def test_unjoined(self):
        self.assertEqual(numbers_to_marks('ni3 hao3', join=False), 'nǐ hǎo')

    def test_composed_where_possible(self):
        self.assertEqual(numbers_to_marks('m2'), unicodedata.normalize('NFC', 'ḿ'))
        self.assertEqual(len(numbers_to_marks('m2')), 1)          # ḿ is one character
        self.assertEqual(numbers_to_marks('m3'), 'm̌')        # m̌ has no single character

    def test_tone_of_a_capital(self):
        from src.vocabulary.pinyin import syllable, tone
        self.assertEqual(tone('Ǎi'), 3)
        self.assertEqual(syllable('Ān'), ('an', 1))

    def test_mark_syllable_neutral(self):
        self.assertEqual(mark_syllable('xie', 5), 'xie')


class TestAnswers(unittest.TestCase):
    '''What someone types in the Pinyin mode (pinyin.check / parse).'''

    def readings(self, *syllables):
        return [[s] for s in syllables]

    def test_numbers_and_marks(self):
        for typed in ['ni3hao3', 'nǐ hǎo', 'nǐhǎo', 'ni3 hǎo']:
            with self.subTest(typed):
                self.assertEqual(check(typed, self.readings('nǐ', 'hǎo')), [('nǐ', True), ('hǎo', True)])

    def test_neutral_tone(self):
        for typed in ['xie4xie', 'xie4xie5', 'xie4xie0', 'xièxie']:
            with self.subTest(typed):
                self.assertEqual(check(typed, self.readings('xiè', 'xie')), [('xiè', True), ('xie', True)])

    def test_u_umlaut(self):
        for typed in ['nv3', 'nu:3', 'nǚ']:
            with self.subTest(typed):
                self.assertEqual(check(typed, self.readings('nǚ')), [('nǚ', True)])

    def test_erhua(self):
        for typed in ['yi4dian3r', 'yìdiǎnr', 'yi4dianr3']:
            with self.subTest(typed):
                self.assertTrue(all(ok for _, ok in check(typed, self.readings('yì', 'diǎn', 'r'))))
        for typed in ['zhèr', 'zhe4r', 'zher4']:
            with self.subTest(typed):
                self.assertTrue(all(ok for _, ok in check(typed, self.readings('zhè', 'r'))))
        self.assertTrue(all(ok for _, ok in check('nar3', self.readings('nǎ', 'r'))))

    def test_any_reading(self):
        self.assertEqual(check('hao4', [['hǎo', 'hào']]), [('hào', True)])

    def test_wrong_and_short(self):
        self.assertEqual(check('wo4', self.readings('wǒ')), [('wò', False)])
        self.assertEqual(check('ni3', self.readings('nǐ', 'hǎo')), [('nǐ', True), ('', False)])

    def test_not_pinyin(self):
        for typed in ['hello', 'wo9', '']:
            with self.subTest(typed):
                self.assertIsNone(parse(typed))


if __name__ == '__main__':
    unittest.main()
