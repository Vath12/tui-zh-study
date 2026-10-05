'''Audio utilities for the text to speech: Speech (audio and its sample
rate), Player (plays audio through PortAudio, as it arrives), and
AudioCache (the last 128 clips, kept in .tts_cache/).'''
import hashlib
import os
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent.parent
CACHE_DIR = ROOT / '.tts_cache'
CACHE_FILES = 128


@dataclass
class Speech:
    '''Audio: mono float32 samples in -1..1.'''
    samples : np.ndarray
    sample_rate : int
    seconds_to_make : float = 0.0   # how long generating it took (0 if it came from the cache)
    cached : bool = False           # whether it came from the cache

    @property
    def duration(self) -> float:
        '''Length in seconds.'''
        return len(self.samples) / self.sample_rate

    @property
    def real_time_factor(self) -> float:
        '''Time to make it / its length: below 1 is faster than real time.'''
        return self.seconds_to_make / self.duration if self.duration else float('inf')

    def save(self, path : str | Path) -> Path:
        '''Write it as a WAV file (16-bit PCM).'''
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_wav(path, self.samples, self.sample_rate)
        return path

    def play(self, wait : bool = True) -> 'Player':
        player = Player(self.sample_rate)
        player.feed(self.samples)
        player.finish()
        if wait:
            player.wait()
        return player


def write_wav(path : Path, samples : np.ndarray, sample_rate : int):
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm.tobytes())


def read_wav(path : Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), 'rb') as f:
        if f.getsampwidth() != 2:
            raise ValueError(f'{path}: only 16-bit WAV files are read')
        pcm = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2')
        if f.getnchannels() > 1:
            pcm = pcm.reshape(-1, f.getnchannels()).mean(axis=1)
        return (pcm / 32768).astype(np.float32), f.getframerate()


class Player:
    '''Plays audio through PortAudio (sounddevice), as it arrives: feed()
    chunks as they're made and they play back to back, finish() once there
    are no more, wait() until it's all been heard. stop() cuts it off.

    It plays from PortAudio's callback, so feed() never blocks; if the next
    chunk is late there's silence until it comes. Use it as a context
    manager to finish() and wait() at the end.'''

    def __init__(self, sample_rate : int):
        self.sample_rate = sample_rate
        self._chunks : deque[np.ndarray] = deque()
        self._pos = 0              # how far into the first chunk playback has got
        self._finished = False
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._stream = None

    def feed(self, samples : np.ndarray):
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        if not len(samples):
            return
        with self._lock:
            self._chunks.append(samples)
        if self._stream is None:
            import sounddevice
            self._stream = sounddevice.OutputStream(samplerate=self.sample_rate, channels=1, dtype='float32',
                                                    callback=self._callback, finished_callback=self._done.set)
            self._stream.start()

    def finish(self):
        '''No more audio is coming: stop once what's there has played.'''
        with self._lock:
            self._finished = True
        if self._stream is None:
            self._done.set()      # nothing was ever fed

    def wait(self, timeout : float | None = None) -> bool:
        '''Wait until it's all played (finish() first). Returns False on timeout.'''
        done = self._done.wait(timeout)
        if done and self._stream is not None:
            self._stream.close()
        return done

    def stop(self):
        with self._lock:
            self._chunks.clear()
            self._finished = True
        if self._stream is not None:
            self._stream.abort()
            self._stream.close()
        self._done.set()

    def _callback(self, outdata, frames, time_info, status):
        import sounddevice
        filled = 0
        with self._lock:
            while filled < frames and self._chunks:
                chunk = self._chunks[0]
                take = min(frames - filled, len(chunk) - self._pos)
                outdata[filled:filled + take, 0] = chunk[self._pos:self._pos + take]
                filled += take
                self._pos += take
                if self._pos == len(chunk):
                    self._chunks.popleft()
                    self._pos = 0
            finished = self._finished and not self._chunks
        outdata[filled:] = 0
        if finished:
            raise sounddevice.CallbackStop

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.finish()
            self.wait()
        else:
            self.stop()


class AudioCache:
    '''The most recently used clips (at most max_files), as WAV files in
    `dir`. A clip is named by the md5 of its text, speaker and speech prompt
    (the style instruction), so the same request finds the same file.
    "Most recently used" is the file's modification time, which a hit
    updates, so the order lasts between runs; adding a clip past max_files
    deletes the least recently used.'''

    def __init__(self, dir : Path = CACHE_DIR, max_files : int = CACHE_FILES):
        self.dir = Path(dir)
        self.max_files = max_files

    @staticmethod
    def key(text : str, speaker : str | None, prompt : str | None) -> str:
        '''The md5 of the text, speaker and prompt (with a separator, so
        ("ab", "c") and ("a", "bc") don't clash).'''
        return hashlib.md5('\0'.join([text, speaker or '', prompt or '']).encode('utf-8')).hexdigest()

    def path(self, text : str, speaker : str | None, prompt : str | None) -> Path:
        return self.dir / f'{self.key(text, speaker, prompt)}.wav'

    def get(self, text : str, speaker : str | None, prompt : str | None) -> Speech | None:
        path = self.path(text, speaker, prompt)
        try:
            samples, rate = read_wav(path)
        except (OSError, EOFError, wave.Error, ValueError):
            return None
        os.utime(path)   # now the most recently used
        return Speech(samples, rate, cached=True)

    def put(self, text : str, speaker : str | None, prompt : str | None, speech : Speech) -> Path:
        path = self.path(text, speaker, prompt)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.wav.tmp')
        write_wav(tmp, speech.samples, speech.sample_rate)
        tmp.replace(path)   # all or nothing, so a crash can't leave half a clip
        self.evict()
        return path

    def files(self) -> list[Path]:
        '''The cached clips, least recently used first.'''
        if not self.dir.exists():
            return []
        return sorted(self.dir.glob('*.wav'), key=lambda p: p.stat().st_mtime_ns)

    def evict(self):
        files = self.files()
        for path in files[:max(0, len(files) - self.max_files)]:
            path.unlink(missing_ok=True)

    def clear(self):
        for path in self.files():
            path.unlink(missing_ok=True)

    def __len__(self) -> int:
        return len(self.files())
