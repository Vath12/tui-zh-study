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

    def test_one_row_per_word(self):
        self.assertEqual(Dictionary.cedict['simplified'].is_duplicated().sum(), 0)
        self.assertEqual(Dictionary.lookup('好').height, 1)

    def test_entry_readings(self):
        entry = Dictionary.entry('好')
        self.assertEqual([r.pinyin for r in entry.readings], ['hao3', 'hao4'])
        self.assertEqual(entry.readings[0].pinyin_marked, 'hǎo')
        self.assertEqual(entry.readings[0].senses[1].glosses, ['appropriate', 'proper'])
        self.assertIsNone(Dictionary.entry('不是一个词'))

    def test_readings_keep_their_traditional_form(self):
        entry = Dictionary.entry('了')   # 了 le5, liao3, and 瞭 liao3 (瞭 liao4 is only a variant note)
        self.assertEqual([(r.traditional, r.pinyin) for r in entry.readings],
                         [('了', 'le5'), ('了', 'liao3'), ('瞭', 'liao3')])

    def test_undefined_readings_dropped(self):
        self.assertTrue(Dictionary.drop_undefined)
        for word in Dictionary.cedict['simplified'].sample(2000, seed=1).to_list():
            with self.subTest(word):
                self.assertTrue(all(r.senses for r in Dictionary.entry(word).readings))
        self.assertNotIn('箇', [r.traditional for r in Dictionary.entry('个').readings])   # variant of 個
        self.assertNotIn('heng2', Dictionary.pinyin('行'))                                   # used in 道行

    def test_undefined_readings_kept_if_asked(self):
        cedict = Dictionary.cedict
        try:
            Dictionary.cedict, Dictionary.drop_undefined = None, False
            Dictionary.init()
            variant = next(r for r in Dictionary.entry('个').readings if r.traditional == '箇')
            self.assertEqual(variant.senses, [])
            self.assertEqual([n.kind for n in variant.notes], ['variant'])
            self.assertEqual(variant.notes[0].references[0].simplified, '个')
            heng = next(r for r in Dictionary.entry('行').readings if r.pinyin == 'heng2')
            self.assertEqual([n.kind for n in heng.notes], ['used_in'])
            # The load-time check agrees with the parser on every entry.
            from src.vocabulary.cedict import parse_definitions
            from src.vocabulary.dictionary import has_meaning
            flat = Dictionary.cedict.explode('definitions').with_columns(fast=has_meaning(pl.col('definitions')))
            slow = [bool(parse_definitions(d)[0]) for d in flat['definitions'].to_list()]
            self.assertEqual(flat['fast'].to_list(), slow)
        finally:
            Dictionary.cedict, Dictionary.drop_undefined = cedict, True

    def test_senses(self):
        senses = Dictionary.senses('长')
        self.assertEqual(senses[0].glosses, ['long'])
        self.assertIn('bound form', senses[1].labels)

    def test_pinyin(self):
        self.assertEqual(Dictionary.pinyin('好'), ['hao3', 'hao4'])
        self.assertEqual(Dictionary.pinyin('你好'), ['ni3 hao3'])

    def test_pinyin_marked(self):
        self.assertEqual(Dictionary.pinyin('你好', marked=True), ['nǐhǎo'])
        self.assertEqual(Dictionary.pinyin('好', marked=True), ['hǎo', 'hào'])
        self.assertEqual(Dictionary.pinyin('绿', marked=True), ['lù', 'lǜ'])

    def test_definitions(self):
        self.assertEqual(Dictionary.definitions('你好'), ['hello; hi'])
        self.assertIn('(bound form) row; line', Dictionary.definitions('行'))

    def test_unknown_word(self):
        self.assertTrue(Dictionary.lookup('不是一个词').is_empty())
        self.assertEqual(Dictionary.pinyin('不是一个词'), [])
        self.assertEqual(Dictionary.senses('不是一个词'), [])

    def test_with_charset(self):
        same = Dictionary.with_charset('好你')['simplified'].unique().to_list()
        self.assertIn('你好', same)
        self.assertNotIn('你', same)

    def test_made_of(self):
        vocab = '我你好他她是不很学中国人们的了吗'
        readable = Dictionary.made_of(vocab, max_len=4)['simplified'].to_list()
        self.assertEqual(len(readable), len(set(readable)))   # each word once
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
        for name in ['lookup', 'entry', 'pinyin', 'senses', 'definitions', 'with_charset', 'made_of', 'char_frequency',
                     'most_common']:
            with self.subTest(name):
                self.assertTrue(hasattr(getattr(Dictionary, name).__func__, '__wrapped__'), f'{name} isn\'t @loaded')


if __name__ == '__main__':
    unittest.main()
