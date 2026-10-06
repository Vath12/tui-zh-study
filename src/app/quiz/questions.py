import random
from pathlib import Path

from src.stroke.stroke import HanziStroke
from src.vocabulary.hsk import HSKDictionary
from ..wordlists import VOCAB_DIR, words_in

MAX_CHARS = 4  # longest question, in characters
BUILT_LEVELS = {'1', '2', '3'}  # HSK levels of the extra words built from your vocab


def question_pool(source : Path = VOCAB_DIR) -> list[str]:
    '''The words questions are made from: your vocab (a vocab file, or a
    directory of them; see wordlists.words_in), plus the HSK words (up to
    MAX_CHARS long, from BUILT_LEVELS) made only of characters in your vocab,
    like 爸爸 from 爸. Words with a character that has no stroke data or no
    pinyin are left out.'''
    vocab = words_in(source)
    known = set(''.join(vocab))
    HSKDictionary._load_lazy()
    HanziStroke._load_lazy()
    built = [w for w, entries in HSKDictionary.by_word.items()
             if 1 < len(w) <= MAX_CHARS and set(w) <= known and entries[0].level in BUILT_LEVELS]
    usable = lambda w: all(c in HanziStroke.stroke_data for c in w) and all(p for _, p in HSKDictionary.words_pinyin([w]))
    return [w for w in dict.fromkeys(vocab + built) if len(w) <= MAX_CHARS and usable(w)]


class CharWeights:
    '''How likely each character is to come up: the number of questions
    since it was last asked, halved for every time you've got it right. So
    characters you haven't seen in a while come back, and ones you know come
    back less. A word's weight is the mean of its characters'.'''

    def __init__(self):
        self.turn = 0
        self.last_asked : dict[str, int] = {}  # character -> turn; never asked counts as turn -1
        self.right : dict[str, int] = {}       # character -> times got right

    def char(self, c : str) -> float:
        return (self.turn - self.last_asked.get(c, -1)) * 0.5 ** self.right.get(c, 0)

    def word(self, w : str) -> float:
        return sum(map(self.char, w)) / len(w)

    def asked(self, chars : str):
        '''A new question with these characters.'''
        self.turn += 1
        for c in chars:
            self.last_asked[c] = self.turn

    def got_right(self, chars : str):
        for c in chars:
            self.right[c] = self.right.get(c, 0) + 1


def make_question(pool : list[str], rng : random.Random, weights : CharWeights, max_chars : int = MAX_CHARS) -> list[str]:
    '''A question: a few whole words from the pool, 1 to max_chars characters
    in all, picked by their weights (anything with a word(w) method), without
    repeating a word if there's anything else that fits.'''
    target = rng.randint(1, max_chars)
    words = []
    while (room := target - sum(map(len, words))) > 0:
        fits = [w for w in pool if len(w) <= room]
        options = [w for w in fits if w not in words] or fits
        words.append(rng.choices(options, weights=list(map(weights.word, options)))[0])
    return words
