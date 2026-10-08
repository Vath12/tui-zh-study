'''Text to speech with Qwen3-TTS, through mlx-audio's MLX port of it.

    tts = TTS()                                   # loads the model on first use
    tts.speak('你好，我是你的老师。')                # play it (from the cache, or as it's made)
    speech = tts.say('谢谢')                      # or just get the audio
    speech.save('xiexie.wav')

The models are downloaded from Hugging Face the first time they're used.
Clips are kept in an AudioCache (see utils), so saying something again is instant.'''
import time

import numpy as np

from .utils import AudioCache, Player, Speech

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
DEFAULT_VOICE = 'ryan'   # see TTS.speakers()
STREAM_INTERVAL = 0.32     # seconds of audio per streamed chunk (about 4 of the model's 12.5 Hz tokens)
_DEFAULT_CACHE = object()


class TTS:
    '''One Qwen3-TTS model (a key of MODELS, or any Hugging Face repo id),
    loaded the first time it's needed and kept, with the default speaker
    and language. `cache` keeps what's been said: by default an AudioCache
    in .tts_cache/, or pass your own, or None for no cache.'''

    def __init__(self, model : str = DEFAULT_MODEL, voice : str = DEFAULT_VOICE, language : str = 'chinese',
                 cache : AudioCache | None = _DEFAULT_CACHE):
        self.repo = MODELS.get(model, model)
        self.voice = voice
        self.language = language
        self.cache = AudioCache() if cache is _DEFAULT_CACHE else cache
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

    def _generate(self, text, voice, instruct, language, options, **stream):
        if self.kind == 'custom_voice':
            options = {'voice': voice, **options}
        for result in self.model.generate(text=text, instruct=instruct, lang_code=language or self.language,
                                          **stream, **options):
            yield np.asarray(result.audio, dtype=np.float32).reshape(-1)

    def say(self, text : str, voice : str | None = None, instruct : str | None = None, language : str | None = None,
            **options) -> Speech:
        '''The audio for `text`, from the cache if it's there. voice is a
        speaker (CustomVoice models; see speakers()), instruct the speech
        prompt: a style ("speak slowly") or, for VoiceDesign, the voice to
        make. Other options go to the model's generate() (temperature,
        ref_audio and ref_text for Base, ...).'''
        voice = voice or self.voice
        if self.cache is not None and (hit := self.cache.get(text, voice, instruct)):
            return hit
        started = time.perf_counter()
        parts = list(self._generate(text, voice, instruct, language, options))
        speech = Speech(np.concatenate(parts) if parts else np.zeros(0, np.float32), self.model.sample_rate,
                        time.perf_counter() - started)
        if self.cache is not None and len(speech.samples):
            self.cache.put(text, voice, instruct, speech)
        return speech

    def speak(self, text : str, voice : str | None = None, instruct : str | None = None, language : str | None = None,
              wait : bool = True, **options) -> Speech:
        '''Play the audio for `text` (as say()), and return it. If it isn't
        cached, it plays as it's made, so it starts in about a quarter of a
        second, then goes in the cache. This blocks while it's being made;
        wait=False returns once it's all made rather than once it's all played.'''
        voice = voice or self.voice
        if self.cache is not None and (hit := self.cache.get(text, voice, instruct)):
            hit.play(wait)
            return hit
        started = time.perf_counter()
        parts = []
        player = Player(self.model.sample_rate)
        try:
            for chunk in self._generate(text, voice, instruct, language, options,
                                        stream=True, streaming_interval=STREAM_INTERVAL):
                player.feed(chunk)
                parts.append(chunk)
        except BaseException:
            player.stop()
            raise
        player.finish()
        speech = Speech(np.concatenate(parts) if parts else np.zeros(0, np.float32), self.model.sample_rate,
                        time.perf_counter() - started)
        if self.cache is not None and len(speech.samples):
            self.cache.put(text, voice, instruct, speech)
        if wait:
            player.wait()
        return speech
