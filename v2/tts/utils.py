'''Text to speech with Qwen3-TTS, through mlx-audio's MLX port of it.

    tts = TTS()                                   # loads on first use
    speech = tts.say('你好，我是你的老师。')
    speech.play()
    speech.save('hello.wav')

The models are downloaded from Hugging Face the first time they're used.'''
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# name -> Hugging Face repo. CustomVoice has preset speakers (and takes a
# style instruction); VoiceDesign makes a voice from a description; Base
# clones a voice from a recording of it.
MODELS = {
    'custom-0.6b': 'mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16',
    'custom-0.6b-6bit': 'mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-6bit',
    'custom-1.7b': 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16',
    'custom-1.7b-6bit': 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-6bit',
    'design-1.7b': 'mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16',
    'base-0.6b': 'mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16',
}
DEFAULT_MODEL = 'custom-0.6b'
DEFAULT_VOICE = 'vivian'   # see TTS.speakers()


@dataclass
class Speech:
    '''Generated audio: mono float32 samples in -1..1.'''
    samples : np.ndarray
    sample_rate : int
    seconds_to_make : float = 0.0   # how long generating it took

    @property
    def duration(self) -> float:
        '''Length in seconds.'''
        return len(self.samples) / self.sample_rate

    @property
    def real_time_factor(self) -> float:
        '''Time to make it / its length: below 1 is faster than real time.'''
        return self.seconds_to_make / self.duration if self.duration else float('inf')

    def save(self, path : str | Path) -> Path:
        '''Write it as audio (the format follows the extension: .wav, .flac, .mp3, ...).'''
        from mlx_audio.audio_io import write
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write(str(path), self.samples, self.sample_rate)
        return path

    def play(self, wait : bool = True):
        '''Play it on the default output device; wait=False returns straight away.'''
        import sounddevice
        sounddevice.play(self.samples, self.sample_rate)
        if wait:
            sounddevice.wait()


class TTS:
    '''One Qwen3-TTS model (a key of MODELS, or any Hugging Face repo id),
    loaded the first time it's needed and kept.'''

    def __init__(self, model : str = DEFAULT_MODEL, voice : str = DEFAULT_VOICE, language : str = 'chinese'):
        self.repo = MODELS.get(model, model)
        self.voice = voice
        self.language = language
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from mlx_audio.tts.utils import load_model
            self._model = load_model(self.repo)
        return self._model

    @property
    def kind(self) -> str:
        '''custom_voice, voice_design or base.'''
        return getattr(self.model.config, 'tts_model_type', 'base')

    def speakers(self) -> list[str]:
        return list(self.model.get_supported_speakers() or [])

    def languages(self) -> list[str]:
        return list(self.model.get_supported_languages() or [])

    def say(self, text : str, voice : str | None = None, instruct : str | None = None, language : str | None = None,
            **options) -> Speech:
        '''Speak `text`. voice is a speaker (CustomVoice models; see
        speakers()), instruct a style ("speak slowly") or, for VoiceDesign,
        the voice to make. Other options go to the model's generate()
        (temperature, ref_audio and ref_text for Base, ...).'''
        model = self.model
        if self.kind == 'custom_voice':
            options['voice'] = voice or self.voice
        started = time.perf_counter()
        parts = [np.asarray(r.audio, dtype=np.float32).reshape(-1)
                 for r in model.generate(text=text, instruct=instruct, lang_code=language or self.language, **options)]
        samples = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return Speech(samples, model.sample_rate, time.perf_counter() - started)
