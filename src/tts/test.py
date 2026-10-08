'''Try the text to speech: type a line, hear it, and see whether the audio
is sound (not silent or clipped, and a length that fits the text) and
whether it came from the cache. Ctrl-C to stop.

    uv run python -m src.tts.test
    uv run python -m src.tts.test --model custom-1.7b --voice serena --no-play

The first run downloads the model (see tts.MODELS).'''
import argparse
import sys

import numpy as np

from .tts import DEFAULT_MODEL, DEFAULT_VOICE, MODELS, TTS
from .utils import Speech

SECONDS_PER_CHAR = (0.1, 1.5)

STRESS_SENTENCES = '''你好，很高兴认识你。
你叫什么名字？
请问，您贵姓？
我是美国人，但是我正在学习中文。
今天天气怎么样？
你吃饭了吗？
这个东西多少钱？
太贵了，可以便宜一点吗？
我不知道他说的是什么意思。
你能再说一遍吗？
我学会写中文了，但是我不会说中文。
你看，那个人是不是老师？
如果明天下雨，我们就不去了。
虽然很累，但是我还是想继续学习。
我觉得学习语言最重要的是坚持。
他昨天晚上十一点半才回家。
请把这本书放在桌子上。
别着急，慢慢说就可以了。
这件衣服是红色的，那件是蓝色的。
我喜欢喝咖啡，不太喜欢喝茶。
北京、上海和广州都是中国的大城市。
现在是下午三点十五分。
我的电话号码是八八八八，一二三四。
第一百零五页有一个很有意思的故事。
你觉得“你好”和“您好”有什么区别？
他怎么还没来？我们已经等了半个小时了。
妈妈说：“早点儿回家，别玩得太晚。”
这个问题看起来很简单，其实并没有那么容易。
如果你真的想学好中文，就每天练习一点儿。
请问，您叫什么名字？您来自哪里？为什么学习中文？'''.split('\n')

def problems(speech : Speech, text : str) -> list[str]:
    '''What's wrong with the audio for `text`, if anything.'''
    out = []
    samples = speech.samples
    if not len(samples) or not np.isfinite(samples).all():
        return ['no audio, or audio with NaN/inf in it']
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < 1e-3:
        out.append(f'silent (rms {rms:.5f})')
    if np.mean(np.abs(samples) >= 0.999) > 0.01:
        out.append('clipped')
    chars = sum(c.strip() != '' and not c in '，。！？,.!?' for c in text)
    low, high = SECONDS_PER_CHAR
    if not low * chars <= speech.duration <= high * chars + 1:
        out.append(f'{speech.duration:.1f}s is an odd length for {chars} characters')
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description='Try the Qwen3-TTS text to speech.')
    parser.add_argument('--model', default=DEFAULT_MODEL, help=f'one of {", ".join(MODELS)}, or a Hugging Face repo')
    parser.add_argument('--voice', default=DEFAULT_VOICE, help='speaker, for CustomVoice models')
    parser.add_argument('--instruct', default='speak clearly', help='style ("speak slowly"), or the voice for VoiceDesign')
    parser.add_argument('--no-play', action='store_true', help='don\'t play the audio')
    parser.add_argument('--st', action='store_true', help='stress test')
    args = parser.parse_args()

    tts = TTS(args.model, voice=args.voice)
    print(f'loading {tts.repo} (downloads it the first time)...', flush=True)

    try:
        while True:
            if args.st and STRESS_SENTENCES:
                text = STRESS_SENTENCES.pop(0)
            else:
                text = input()
            if not text.strip():
                continue
            print(text)
            if args.no_play:
                speech = tts.say(text, instruct=args.instruct)
            else:
                speech = tts.speak(text, instruct=args.instruct)
            found = problems(speech, text)
            made = 'from the cache' if speech.cached else \
                f'in {speech.seconds_to_make:.1f}s (x{speech.real_time_factor:.2f} real time)'
            print(f'{"FAIL" if found else "ok  "} {speech.duration:.1f}s of audio {made}'
                  f'   cache: {len(tts.cache)} clips' + (f'  {"; ".join(found)}' if found else ''))
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(e)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
