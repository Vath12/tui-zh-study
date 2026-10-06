import unittest

import polars as pl

from src.vocabulary.dictionary import CEDICT_PATH, FREQUENCY_PATH, Dictionary, charset_hash, charset_key

INSTALLED = CEDICT_PATH.exists() and FREQUENCY_PATH.exists()


class TestCharsetHash(unittest.TestCase):

    def test_order_and_repeats_dont_matter(self):
        self.assertEqual(charset_key('你好你'), '你好')
        self.assertEqual(charset_hash('你好你'), charset_hash('好你'))
        self.assertEqual(charset_hash('好你'), charset_hash('你好'))

    def test_different_characters_differ(self):
        self.assertNotEqual(charset_hash('你好'), charset_hash('你'))


@unittest.skipUnless(INSTALLED, 'run install.py first (needs resources/cc-cedict.tsv, jun-da_frequency.tsv)')
class TestDictionary(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Dictionary.init()

    def test_init_twice_keeps_the_data(self):
        cedict = Dictionary.cedict
        Dictionary.init()
        self.assertIs(Dictionary.cedict, cedict)

    def test_charset_hash_column(self):
        row = Dictionary.cedict.filter(pl.col('simplified') == '你好')
        self.assertEqual(row['charset_hash'][0], charset_hash('好你'))

    def test_pinyin(self):
        self.assertEqual(Dictionary.pinyin('好'), ['hao3', 'hao4'])
        self.assertEqual(Dictionary.pinyin('你好'), ['ni3 hao3'])

    def test_pinyin_marked(self):
        self.assertEqual(Dictionary.pinyin('你好', marked=True), ['nǐhǎo'])
        self.assertEqual(Dictionary.pinyin('好', marked=True), ['hǎo', 'hào'])
        self.assertEqual(Dictionary.pinyin('绿', marked=True), ['lù', 'lǜ'])

    def test_definitions(self):
        self.assertIn('hello; hi', Dictionary.definitions('你好'))

    def test_unknown_word(self):
        self.assertTrue(Dictionary.lookup('不是一个词').is_empty())
        self.assertEqual(Dictionary.pinyin('不是一个词'), [])

    def test_with_charset(self):
        same = Dictionary.with_charset('好你')['simplified'].unique().to_list()
        self.assertIn('你好', same)
        self.assertNotIn('你', same)

    def test_made_of(self):
        vocab = '我你好他她是不很学中国人们的了吗'
        readable = Dictionary.made_of(vocab, max_len=4)['simplified'].unique().to_list()
        self.assertIn('中国人', readable)
        self.assertTrue(all(set(w) <= set(vocab) for w in readable))
        self.assertTrue(all(len(w) <= 4 for w in readable))

    def test_char_frequency(self):
        top = Dictionary.char_frequency('的')
        self.assertEqual(top['rank'], 1)
        self.assertGreater(top['count'], 0)
        self.assertIsNone(Dictionary.char_frequency('A'))

    def test_most_common(self):
        self.assertEqual(Dictionary.most_common(3), ['的', '一', '是'])

    def test_lookups_load_lazily(self):
        cedict, frequency = Dictionary.cedict, Dictionary.frequency
        try:
            Dictionary.cedict = Dictionary.frequency = None
            self.assertEqual(Dictionary.pinyin('你好'), ['ni3 hao3'])   # loads, with no init()
            self.assertIsNotNone(Dictionary.cedict)
            self.assertIsNotNone(Dictionary.frequency)
        finally:
            Dictionary.cedict, Dictionary.frequency = cedict, frequency

    def test_every_lookup_is_loaded(self):
        for name in ['lookup', 'pinyin', 'definitions', 'with_charset', 'made_of', 'char_frequency', 'most_common']:
            with self.subTest(name):
                self.assertTrue(hasattr(getattr(Dictionary, name).__func__, '__wrapped__'), f'{name} isn\'t @loaded')


if __name__ == '__main__':
    unittest.main()
