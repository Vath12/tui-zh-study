import hashlib
import tempfile
import unittest
from pathlib import Path

import polars as pl

from src.util import load_hashed_tsv


def write_hashed(path : Path, rows : list[str]):
    body = '\n'.join(rows)
    path.write_text(hashlib.md5(body.encode('utf-8')).hexdigest() + '\n' + body, encoding='utf-8')


class TestLoadHashedTsv(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / 'data.tsv'
        write_hashed(self.path, ['的\t7922684\tde\tof', '一\t3050722\tyi1\tone', '鴒\t1\tling2\t'])

    def tearDown(self):
        self.dir.cleanup()

    def test_schema_names_and_types(self):
        df = load_hashed_tsv(self.path, {'char': pl.String, 'count': pl.Int64, 'pinyin': pl.String, 'english': pl.String})
        self.assertEqual(df.columns, ['char', 'count', 'pinyin', 'english'])
        self.assertEqual(df.schema['count'], pl.Int64)
        self.assertEqual(df.height, 3)
        self.assertIsNone(df['english'][2])      # an empty field is null

    def test_names_only_are_strings(self):
        df = load_hashed_tsv(self.path, ['char', 'count', 'pinyin', 'english'])
        self.assertEqual(df.dtypes, [pl.String] * 4)

    def test_no_schema(self):
        df = load_hashed_tsv(self.path)
        self.assertEqual(df.columns, ['column_1', 'column_2', 'column_3', 'column_4'])

    def test_quotes_kept(self):
        write_hashed(self.path, ['了\tliao3\tas in 忘不了 "cannot forget"'])
        df = load_hashed_tsv(self.path, ['word', 'pinyin', 'definitions'])
        self.assertEqual(df['definitions'][0], 'as in 忘不了 "cannot forget"')

    def test_hash_mismatch(self):
        text = self.path.read_text(encoding='utf-8')
        self.path.write_text(text.replace('one', 'two'), encoding='utf-8')
        with self.assertRaisesRegex(Exception, 'checkhash mismatch'):
            load_hashed_tsv(self.path)


if __name__ == '__main__':
    unittest.main()
