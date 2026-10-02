from .core.model import Model, ModelContext, ModelOutputClass
from .core.server import ModelServer, ModelSession
from .core.logit_mask import PUNCTUATION, TERMINATORS
import random

import asyncio

SYSTEM_PROMPT_SENTENCE_GENERATOR = (
    "You write one natural Chinese sentence for a beginner learner to practice reading.\n"
    "The user gives you a list of characters. Use ONLY characters from that list, plus the punctuation ，。？！. "
    "Any other character is forbidden, even very common ones. "
    "You may repeat characters and do not need to use all of them.\n"
    "Write a complete sentence of 6 to 15 characters with a subject and a verb. Do not just write a greeting.\n"
    "Before you start, choose words that can be built entirely from the list.\n"
    "Do not put spaces between characters.\n"
    "Output only the sentence: no pinyin, translation, quotes, or explanation."
)
SYSTEM_PROMPT_TRANSLATOR = "Translate the user's Chinese sentence into natural English. Output only the translation."
TRANSLATION_GRADER = (
    "You grade English translations of Chinese sentences. The user gives you the Chinese source and the English translation.\n"
    "Score from 1 to 5 how natural and grammatical the Chinese source is ('source_score'), "
    "and from 1 to 5 how accurately the English translates it ('score'). "
    "Do not penalize the translation for problems that come from the source.\n"
    "Respond only with JSON with the fields 'source_score', 'score', and 'comment' (one short sentence)."
)

MIN_CHARS = 10
SENTENCE_PUNCTUATION = ['，', '。', '？', '！']

def validate_chars(s, chars):
    allowed = set(chars) | set(PUNCTUATION) | set(TERMINATORS)
    return all(c in allowed for c in s)

def prompt_chars(chars):
    return ' '.join(random.sample(chars, len(chars)))


async def main():
    server = ModelServer('Qwen3.5-4B')

    try:
        charset = "我 你 好 他 她 是 不 很 您 谢 学 字 名 姓 会 看 了 个 也 爸 妈 可 爱 叫 中 国 美 云 说 的 们".split()
        for i in range(5):
            # fresh sessions so earlier sentences don't leak into the next run
            generator = server.session(system_prompt=SYSTEM_PROMPT_SENTENCE_GENERATOR)
            translator = server.session(system_prompt=SYSTEM_PROMPT_TRANSLATOR)
            judge = server.session(system_prompt=TRANSLATION_GRADER)

            chars = random.sample(charset, random.randint(MIN_CHARS, len(charset)))
            s = random.randint(0,65536)
            print(s)
            r1 = await generator.prompt(prompt_chars(chars), False, seed=s, allowed_chars=chars + SENTENCE_PUNCTUATION)
            print(validate_chars(r1, chars))
            print(r1)
            r2 = await translator.prompt(r1, False)
            print(r2)
            r3 = await judge.prompt(f'Chinese: {r1}\nEnglish: {r2}', False)
            print(r3)


    finally:
        server.stop()


if __name__ == "__main__":
    asyncio.run(main())
