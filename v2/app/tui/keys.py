import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

# blessed key names (without KEY_) that read better under another name.
_RENAMES = {
    'btab': 'shift+tab',
    'pgup': 'pageup',
    'pgdown': 'pagedown',
    'ppage': 'pageup',
    'npage': 'pagedown',
    'dc': 'delete',
    'ic': 'insert',
}


@dataclass(frozen=True)
class Key:
    '''A key press. `name` is what to match on: a printable key is itself
    ('a', 'A', '我'), space is 'space', and the rest are lowercase names with
    modifiers first: 'enter', 'tab', 'shift+tab', 'escape', 'backspace',
    'delete', 'up', 'ctrl+a', 'alt+b', 'ctrl+right', 'f1'. `text` is what it
    types: the character for printable keys (' ' for space), else ''.

    A paste (with bracketed paste on, which App turns on) is one Key named
    'paste' whose text is everything pasted.'''
    name : str
    text : str = ''

    @property
    def printable(self) -> bool:
        return bool(self.text) and self.name != 'paste'

    def __str__(self) -> str:
        return self.name


def from_blessed(ks) -> Key:
    '''A Key from a blessed Keystroke.'''
    raw = str(ks)
    if ks.name == 'BRACKETED_PASTE':
        return Key('paste', ks.text or '')
    if ks.name:
        name = ks.name.removeprefix('KEY_').lower()
        for mod in ('ctrl', 'alt', 'shift'):
            name = name.replace(f'{mod}_', f'{mod}+')
        return Key(_RENAMES.get(name, name))
    if raw == ' ':
        return Key('space', ' ')
    if len(raw) == 1 and ord(raw) < 32:
        return Key(f'ctrl+{chr(ord(raw) + 96)}')
    if raw.isprintable():
        return Key(raw, raw)
    return Key(repr(raw))


def dropped_paths(text : str) -> list[Path] | None:
    '''The files in pasted text, if that's all it is: what a terminal pastes
    when you drag files onto it. Terminals write the paths shell-escaped
    (/a/My\\ File.txt), quoted ('/a/My File.txt') or as file:// URLs,
    separated by spaces or newlines. Only absolute (or ~) paths to things that
    exist count, so ordinary pasted text isn't mistaken for a drop. None if
    it isn't a drop.'''
    try:
        words = shlex.split(text.strip())
    except ValueError:
        return None
    paths = []
    for word in words:
        if word.startswith('file://'):
            word = unquote(urlparse(word).path)
        if not (word.startswith('/') or word.startswith('~')):
            return None
        path = Path(os.path.expanduser(word))
        if not path.exists():
            return None
        paths.append(path)
    return paths or None
