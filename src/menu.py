from dataclasses import dataclass
from typing import Callable

from blessed import Terminal
from blessed.keyboard import Keystroke

from .stroke_session import BLEND_MODES, COLOR_MODES, PINYIN_MODES, RENDERING_MODES, SPEEDS, StrokeSession


@dataclass
class MenuItem:
    '''One row of the menu. Choosing an option runs "/command option" on the
    session, so the menu does exactly what typing the command would. An item
    with no options is an action: Enter runs "/command".'''
    label : str
    command : str
    options : list[str]
    current : Callable[[], str] = lambda: ''


class Menu:
    '''A visual menu for the session's settings, drawn with blessed.

    Focus it (Tab in the app), then: up/down picks a row, left/right changes
    its value right away, Enter runs an action row. Tab or Esc goes back to
    typing, and so does typing a character. It's only drawn while focused.'''

    def __init__(self, session : StrokeSession):
        s = session
        self.session = session
        self.items = [
            MenuItem('Render', 'render', list(RENDERING_MODES), lambda: s.rendering_mode),
            MenuItem('Blend', 'blend', BLEND_MODES, lambda: s.blend_mode),
            MenuItem('Colors', 'color', list(COLOR_MODES), lambda: s.color_mode),
            MenuItem('Speed', 'speed', list(SPEEDS), lambda: s.speed),
            MenuItem('Pinyin', 'pinyin', PINYIN_MODES, lambda: s.pinyin_mode),
            MenuItem('Quit', 'quit', []),
        ]
        self.selected = 0
        self.focused = False

    HINT = 'Tab: menu'  # for the app to show somewhere while the menu is hidden

    @property
    def height(self) -> int:
        return len(self.items) + 1 if self.focused else 0  # rows plus the key hints

    def choose(self, item : MenuItem, option : str | None = None):
        self.session.message = self.session.run_command(f'{item.command} {option or ""}') or ''

    def step(self, item : MenuItem, by : int):
        '''Move an item's value by one option (wrapping round).'''
        if not item.options:
            return
        i = item.options.index(item.current()) if item.current() in item.options else 0
        self.choose(item, item.options[(i + by) % len(item.options)])

    def handle_key(self, key : Keystroke) -> bool:
        '''Handle a key while focused. Returns False for keys the menu doesn't
        use (it unfocuses on those, so the app can treat them as typing).'''
        name = key.name if key.is_sequence else None
        item = self.items[self.selected]
        if name == 'KEY_UP':
            self.selected = (self.selected - 1) % len(self.items)
        elif name == 'KEY_DOWN':
            self.selected = (self.selected + 1) % len(self.items)
        elif name == 'KEY_LEFT':
            self.step(item, -1)
        elif name == 'KEY_RIGHT':
            self.step(item, 1)
        elif name == 'KEY_ENTER' or key in ('\r', '\n', ' '):
            if item.options:
                self.step(item, 1)
            else:
                self.choose(item)
        elif name in ('KEY_TAB', 'KEY_ESCAPE') or key in ('\t', '\x1b'):
            self.focused = False
        else:
            self.focused = False
            return False
        return True

    def lines(self, term : Terminal) -> list[str]:
        '''The menu's rows plus a line of key hints, or nothing while it isn't focused.'''
        if not self.focused:
            return []
        out = []
        width = max(len(item.label) for item in self.items)
        for i, item in enumerate(self.items):
            here = i == self.selected and self.focused
            label = f'{"›" if here else " "} {item.label:<{width}}  '
            label = term.bold(label) if here else term.dim(label)
            options = []
            for option in item.options:
                if option == item.current():
                    # The current value: highlighted, and reversed on the row you're on.
                    options.append(term.reverse(f' {option} ') if here else term.bold_cyan(f' {option} '))
                else:
                    options.append(f' {option} ' if here else term.dim(f' {option} '))
            out.append(label + ' '.join(options))
        out.append(term.dim('  ↑↓ choose  ←→ change  Enter select  Tab back to typing'))
        return out
