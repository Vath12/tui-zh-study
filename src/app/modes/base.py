from dataclasses import dataclass
from typing import Callable

from ..sessions import Session
from ..strokes import StrokeLook
from src.tui import DIM, Key, Message, Text, Widget
from ..wordlists import Wordlists


@dataclass
class StudyContext:
    '''What a study mode gets to work with.'''
    session : Callable[[], Session]          # the current session (it changes when you switch)
    wordlists : Wordlists                    # the vocab sets; .words() is what's switched on
    look : StrokeLook                        # how strokes are drawn
    notify : Callable[[Message], None]       # a message for the status line


class StudyMode:
    '''A way of studying, shown in the main window. Subclasses set name and
    label, build their widget in view(), and take answers in entered().

    A mode's state lives in the session, under its name, as JSON values
    (`state`, a dict, created by initial_state()); call save() after changing
    it. start() is called when the mode is picked and when the session
    changes (so the state is different), and only for the current mode, so
    a mode that isn't showing doesn't do anything.'''

    name = ''
    label = ''
    ready = False       # modes that aren't ready yet just say so

    def __init__(self, ctx : StudyContext):
        self.ctx = ctx
        self._view : Widget | None = None

    @property
    def state(self) -> dict:
        return self.ctx.session().state.setdefault(self.name, self.initial_state())

    def initial_state(self) -> dict:
        return {}

    def save(self):
        self.ctx.session().save()

    @property
    def widget(self) -> Widget:
        '''The mode's part of the main window (built once).'''
        if self._view is None:
            self._view = self.view()
        return self._view

    def view(self) -> Widget:
        return Text(f'{self.label} isn\'t ready yet.', DIM)

    def start(self):
        '''The mode was picked, or the session changed: pick up from the state.'''

    def entered(self, text : str) -> bool:
        '''Enter on the command line (with anything but a /command). Return
        True if the mode used it.'''
        return False

    def handle_key(self, key : Key) -> bool:
        '''A key pressed while the command line is empty, before it gets it
        (for single-key controls). Return True if the mode used it.'''
        return False
