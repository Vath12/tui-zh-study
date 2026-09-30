from .parse import parse_hsk_pinyin, word_lists, LEVELS, find_vocab_matches, load_vocab
import random

if __name__ == "__main__":
    hsk = parse_hsk_pinyin()
    words = word_lists(hsk)

    test_set = []
    for item, m in find_vocab_matches(load_vocab(), hsk).items():
        test_set.append((item, m.pinyin))

    next_set = list(test_set)
    random.shuffle(next_set)
    while next_set:
        i,pinyin = next_set.pop(0)
        print(f'{i}')
        r = input().strip()
        if (r == i):
            print('correct')
        else:
            print(f'incorrect {pinyin}')
