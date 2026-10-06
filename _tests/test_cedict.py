import unittest

from src.vocabulary.cedict import Reference, parse_definitions, references, sense


class TestSense(unittest.TestCase):

    def test_glosses(self):
        self.assertEqual(sense('appropriate; proper').glosses, ['appropriate', 'proper'])

    def test_labels(self):
        s = sense('(bound form) (literary) clear in one\'s mind; to understand clearly')
        self.assertEqual(s.labels, ['bound form', 'literary'])
        self.assertEqual(s.glosses, ['clear in one\'s mind', 'to understand clearly'])

    def test_all_in_parentheses_is_a_gloss(self):
        s = sense('(completed action marker)')
        self.assertEqual(s.labels, [])
        self.assertEqual(s.glosses, ['(completed action marker)'])

    def test_semicolon_in_brackets_doesnt_split(self):
        self.assertEqual(sense('a thing (lit. one; two) here').glosses, ['a thing (lit. one; two) here'])

    def test_str(self):
        self.assertEqual(str(sense('(of two people) close; on intimate terms')), '(of two people) close; on intimate terms')


class TestReferences(unittest.TestCase):

    def test_traditional_and_simplified(self):
        self.assertEqual(references('as in 打電話|打电话[da3 dian4 hua4]'), [Reference('打电话', '打電話', 'da3 dian4 hua4')])

    def test_same_form(self):
        self.assertEqual(references('used in 道行[dao4 heng2]'), [Reference('道行', '道行', 'dao4 heng2')])

    def test_classifiers(self):
        refs = references('CL:個|个[ge4],張|张[zhang1]')
        self.assertEqual([(r.simplified, r.pinyin) for r in refs], [('个', 'ge4'), ('张', 'zhang1')])


class TestParseDefinitions(unittest.TestCase):

    def test_senses_and_notes(self):
        senses, notes = parse_definitions('book; volume/CL:本[ben3]/see also 書本|书本[shu1 ben3]/surname Shu')
        self.assertEqual([s.glosses for s in senses], [['book', 'volume']])
        self.assertEqual([n.kind for n in notes], ['classifier', 'see', 'surname'])

    def test_note_kinds(self):
        for text, kind in [('variant of 瞭[liao4]', 'variant'), ('old variant of 個|个[ge4]', 'variant'),
                           ('unofficial variant of 瞭[liao4]', 'variant'), ('used in 道行[dao4 heng2]', 'used_in'),
                           ('abbr. for 的士[di1 shi4]', 'abbreviation'), ('Taiwan pr. [da3]', 'pronunciation'),
                           ('also pr. [di4] or [di5] in poetry and songs', 'pronunciation')]:
            with self.subTest(text):
                senses, notes = parse_definitions(text)
                self.assertEqual((senses, [n.kind for n in notes]), ([], [kind]))

    def test_used_in_needs_a_word(self):
        self.assertEqual([n.kind for n in parse_definitions('used in 道行[dao4 heng2]')[1]], ['used_in'])
        senses, notes = parse_definitions('used in place names/used in transliteration')
        self.assertEqual(([s.glosses for s in senses], notes), ([['used in place names'], ['used in transliteration']], []))

    def test_inline_abbreviation_stays_a_sense(self):
        senses, notes = parse_definitions('(bound form) a taxi; a cab (abbr. for 的士[di1 shi4])')
        self.assertEqual(len(senses), 1)
        self.assertEqual(notes, [])
        self.assertEqual(senses[0].references[0].simplified, '的士')


if __name__ == '__main__':
    unittest.main()
