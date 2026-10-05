import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from v2.vocabulary.vocab import VOCAB_DIR

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / '.data'
WORDLISTS_FILE = DATA_DIR / 'wordlists.json'

_HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134F]+')


class InvalidWordlist(Exception):
    '''Why a file can't be used as a wordlist; the message says what's wrong.'''


def read_wordlist(path : Path) -> list[str]:
    '''The words in a wordlist file, read the way load_vocab does (the first
    token of each line; # starts a comment). Raises InvalidWordlist if it
    isn't a readable UTF-8 .txt file with at least one word, all of them
    Chinese characters.'''
    path = Path(path)
    if not path.exists():
        raise InvalidWordlist(f'no such file: {path}')
    if not path.is_file():
        raise InvalidWordlist(f'not a file: {path}')
    if path.suffix.lower() != '.txt':
        raise InvalidWordlist(f'not a .txt file: {path.name}')
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        raise InvalidWordlist(f'{path.name} isn\'t UTF-8 text')
    except OSError as e:
        raise InvalidWordlist(f'can\'t read {path.name}: {e.strerror}')
    words = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.split() or line.lstrip().startswith('#'):
            continue
        word = line.split()[0]
        if not _HAN.fullmatch(word):
            raise InvalidWordlist(f'{path.name} line {n}: "{word}" isn\'t Chinese characters')
        words.append(word)
    if not words:
        raise InvalidWordlist(f'no words in {path.name}')
    return list(dict.fromkeys(words))


@dataclass
class Wordlist:
    path : Path
    enabled : bool = True
    _checked : tuple = field(default=(), repr=False, compare=False)   # (file stamp, result)

    @property
    def name(self) -> str:
        return self.path.stem

    def check(self) -> tuple[list[str] | None, str | None]:
        '''(words, None) if the file is fine now, else (None, what's wrong).
        Only rereads the file when it's changed.'''
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if self._checked and self._checked[0] == stamp:
            return self._checked[1]
        try:
            result = read_wordlist(self.path), None
        except InvalidWordlist as e:
            result = None, str(e)
        self._checked = (stamp, result)
        return result


def _key(path : Path) -> str:
    '''For telling whether two paths are the same file.'''
    return os.path.normcase(str(Path(path).expanduser().resolve()))


class Wordlists:
    '''The wordlists you've added, and which are switched on, saved in
    `file` (.data/wordlists.json) so they're still there next time. Only
    where each file is gets recorded, not a copy, so editing a file changes
    the list. The first time, it starts with the files in resources/vocab.'''

    def __init__(self, file : Path = WORDLISTS_FILE):
        self.file = Path(file)
        self.lists : list[Wordlist] = []
        self.load()

    def load(self):
        if not self.file.exists():
            self.lists = [Wordlist(p) for p in sorted(VOCAB_DIR.glob('*.txt'))]
            self.save()
            return
        try:
            data = json.loads(self.file.read_text(encoding='utf-8'))
            self.lists = [Wordlist(Path(e['path']), bool(e.get('enabled', True))) for e in data['wordlists']]
        except (ValueError, KeyError, TypeError):
            # Unreadable: keep it for reference and start over.
            self.file.replace(self.file.with_suffix('.json.bak'))
            self.lists = []
            self.save()

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        data = {'wordlists': [{'path': str(w.path), 'enabled': w.enabled} for w in self.lists]}
        tmp = self.file.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp.replace(self.file)   # all or nothing, so a crash can't leave half a file

    def find(self, ref : str | Path) -> Wordlist | None:
        '''A list by path, or by name (the file name without .txt) if that's unambiguous.'''
        key = _key(ref)
        for w in self.lists:
            if _key(w.path) == key:
                return w
        named = [w for w in self.lists if w.name == str(ref) or w.path.name == str(ref)]
        return named[0] if len(named) == 1 else None

    def add(self, path : str | Path) -> str:
        '''Add a file (after checking it). Returns what happened, for the status line.'''
        path = Path(path).expanduser()
        words = read_wordlist(path)   # raises InvalidWordlist
        path = path.resolve()
        if existing := self.find(path):
            return f'{existing.name} is already in your wordlists'
        self.lists.append(Wordlist(path))
        self.save()
        return f'added {path.stem} ({len(words)} words)'

    def remove(self, ref : str | Path) -> str:
        w = self.find(ref)
        if w is None:
            return f'no wordlist {ref}'
        self.lists.remove(w)
        self.save()
        return f'removed {w.name}'

    def toggle(self, w : Wordlist) -> str:
        w.enabled = not w.enabled
        self.save()
        return f'{w.name} {"on" if w.enabled else "off"}'

    def words(self) -> list[str]:
        '''Every word in the lists that are on and readable, without repeats.'''
        out = []
        for w in self.lists:
            if w.enabled and (words := w.check()[0]):
                out += words
        return list(dict.fromkeys(out))
