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
    parser.add_argument('--instruct', default=None, help='style ("speak slowly"), or the voice for VoiceDesign')
    parser.add_argument('--no-play', action='store_true', help='don\'t play the audio')
    args = parser.parse_args()

    tts = TTS(args.model, voice=args.voice)
    print(f'loading {tts.repo} (downloads it the first time)...', flush=True)

    try:
        while True:
            text = input()
            if not text.strip():
                continue
            if args.no_play:
                speech = tts.say(text, instruct=args.instruct)
            else:
                speech = tts.speak(text, instruct=args.instruct)
            found = problems(speech, text)
            made = 'from the cache' if speech.cached else \
                f'in {speech.seconds_to_make:.1f}s (x{speech.real_time_factor:.2f} real time)'
            print(f'{"FAIL" if found else "ok  "} {text}  {speech.duration:.1f}s of audio {made}'
                  f'   cache: {len(tts.cache)} clips' + (f'  {"; ".join(found)}' if found else ''))
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(e)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
