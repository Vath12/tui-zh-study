import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .wordlists import DATA_DIR

MAX_NAME = 40
NONE_NAME = 'None'


class SessionError(Exception):
    '''Something you asked for that can't be done (a name that's taken, ...);
    the message says why.'''


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _write_json(path : Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)   # all or nothing, so a crash can't leave half a file


@dataclass
class Session:
    '''One session: the program's state, by key, as JSON values. Features
    keep what they need under their own keys (session.get('mode')), and set()
    saves straight away, unless the session has no path (the None session),
    when the state is only kept in memory.'''
    id : str
    name : str
    created : str
    updated : str
    state : dict = field(default_factory=dict)
    path : Path | None = field(default=None, repr=False, compare=False)

    def get(self, key : str, default=None):
        return self.state.get(key, default)

    def set(self, key : str, value):
        self.state[key] = value
        self.save()

    def update(self, **values):
        self.state.update(values)
        self.save()

    @property
    def saved(self) -> bool:
        return self.path is not None

    def save(self):
        self.updated = _now()
        if self.path is None:
            return
        _write_json(self.path, {'id': self.id, 'name': self.name, 'created': self.created,
                                'updated': self.updated, 'state': self.state})

    @classmethod
    def load(cls, path : Path) -> 'Session':
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls(data['id'], data['name'], data['created'], data['updated'], dict(data.get('state', {})), path)


class Sessions:
    '''Your sessions, one JSON file each in .data/sessions/, and which one is
    current (in .data/state.json). There's also `none`, the None session,
    which is never saved: while it's current, the program's state lasts only
    until you quit. It's current the first time, and after the last saved
    session is deleted. Which session is current (None included) is remembered.

    Session files that can't be read are left alone (and listed in `skipped`).'''

    def __init__(self, data_dir : Path = DATA_DIR):
        self.dir = Path(data_dir) / 'sessions'
        self.state_file = Path(data_dir) / 'state.json'
        self.sessions : dict[str, Session] = {}   # the saved ones
        self.skipped : list[Path] = []
        now = _now()
        self.none = Session('', NONE_NAME, now, now)
        for path in sorted(self.dir.glob('*.json')) if self.dir.exists() else []:
            try:
                s = Session.load(path)
                self.sessions[s.id] = s
            except (ValueError, KeyError, TypeError, OSError):
                self.skipped.append(path)
        current = self._read_current()
        if current is None or current in self.sessions:
            self._current = current
        else:
            # The current one is gone (or this is the first time).
            self._current = max(self.sessions.values(), key=lambda s: s.updated).id if self.sessions else None
            self._write_current()

    # Current session

    def _read_current(self) -> str | None:
        '''The current session's id, None for the None session, or '' if not known.'''
        try:
            return json.loads(self.state_file.read_text(encoding='utf-8')).get('current', '')
        except (OSError, ValueError, AttributeError):
            return ''

    def _write_current(self):
        _write_json(self.state_file, {'current': self._current})

    @property
    def current(self) -> Session:
        return self.none if self._current is None else self.sessions[self._current]

    def switch(self, session : Session) -> Session:
        self._current = None if session is self.none else session.id
        self._write_current()
        return session

    # Finding and naming

    def list(self) -> list[Session]:
        '''The saved sessions, oldest first (not None).'''
        return sorted(self.sessions.values(), key=lambda s: s.created)

    def find(self, ref : str) -> Session | None:
        '''A session by id or name (names ignore case), None included.'''
        if ref.strip().casefold() == NONE_NAME.casefold():
            return self.none
        if ref in self.sessions:
            return self.sessions[ref]
        return next((s for s in self.sessions.values() if s.name.casefold() == ref.strip().casefold()), None)

    def check_name(self, name : str, renaming : Session | None = None) -> str:
        '''The name, tidied, if it can be used; else SessionError saying why.'''
        name = ' '.join(name.split())
        if not name:
            raise SessionError('a session needs a name')
        if len(name) > MAX_NAME:
            raise SessionError(f'names can be up to {MAX_NAME} characters')
        if name.casefold() == NONE_NAME.casefold():
            raise SessionError(f'"{NONE_NAME}" is taken: it\'s the session that isn\'t saved')
        taken = self.find(name)
        if taken is not None and taken is not renaming:
            raise SessionError(f'there\'s already a session called {taken.name}')
        return name

    def _default_name(self) -> str:
        n = len(self.sessions) + 1
        while self.find(f'Session {n}'):
            n += 1
        return f'Session {n}'

    # Changes

    def new(self, name : str | None = None) -> Session:
        '''Make a session (named "Session N" if no name is given) and switch to it.'''
        name = self.check_name(name) if name else self._default_name()
        now = _now()
        sid = uuid.uuid4().hex[:12]
        session = Session(sid, name, now, now, {}, self.dir / f'{sid}.json')
        session.save()
        self.sessions[sid] = session
        return self.switch(session)

    def rename(self, session : Session, name : str) -> Session:
        if session is self.none:
            raise SessionError(f'{NONE_NAME} can\'t be renamed')
        session.name = self.check_name(name, renaming=session)
        session.save()
        return session

    def delete(self, session : Session, confirm : str) -> Session:
        '''Delete a session, if `confirm` is its name exactly. Returns the
        current session afterwards (another one, if it was the current one).'''
        if session is self.none:
            raise SessionError(f'{NONE_NAME} can\'t be deleted')
        if confirm != session.name:
            raise SessionError(f'that isn\'t "{session.name}", so it wasn\'t deleted')
        if session.path and session.path.exists():
            session.path.unlink()
        del self.sessions[session.id]
        if session.id == self._current:
            others = sorted(self.sessions.values(), key=lambda s: s.updated)
            self.switch(others[-1] if others else self.none)
        return self.current
