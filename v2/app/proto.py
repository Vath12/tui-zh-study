'''A testing ground for the TUI: an output area and a command line at the
bottom. Tab pops a menu (just Quit) out on the left; Tab or Esc puts it
away, and so does typing anything else, which goes to the command line.
Drag files onto the terminal and their names show up (see on_files).

    uv run python -m v2.app.proto
'''
from pathlib import Path

from .tui import BOLD, DIM, FILL, App, Column, CommandInput, Key, Row, Rule, Screen, SettingsPanel, Spacer, Text

MENU_WIDTH = 16


class ProtoScreen(Screen):

    def __init__(self):
        self.log : list[str] = []
        self.menu = SettingsPanel(None, hints=None)   # settings are filled in on_enter, once there's an app
        self.input = CommandInput(on_enter=self.entered, hint='Tab: menu')
        menu_open = lambda: self.focused is self.menu
        menu = Column(Text(' Menu', BOLD, height=1), Rule(), self.menu, Spacer(), width=MENU_WIDTH, visible=menu_open)
        output = Text(lambda: '\n'.join(self.log[-200:]) or 'type something, or /help', wrap=True)
        status = Text(lambda: self.app.message, DIM, wrap=False, height=1, priority=1)
        super().__init__(Column(
            Row(menu, Rule(vertical=True, visible=menu_open), Column(output, Spacer()), height=FILL, gap=1),
            Rule(),
            status,
            self.input,
        ), bindings={'tab': self.open_menu})

    def on_enter(self):
        app = self.app
        self.menu.settings = app.settings
        self.menu.on_message = app.notify
        self.menu.on_close = self.focus_input
        self.focus_input()

    def open_menu(self):
        self.focus(self.menu)

    def focus_input(self):
        '''Back to the command line, which also puts the menu away.'''
        self.focus(self.input)

    def handle_key(self, key : Key) -> bool:
        # Only reached for keys nothing else used: with the menu out, put it
        # away and give the key to the command line.
        if self.focused is self.menu:
            self.focus_input()
            return self.input.handle_key(key)
        return False

    def entered(self, text : str):
        self.log.append(f'> {text}')

    def handle_drop(self, paths : list[Path]) -> bool:
        self.on_files([p.name for p in paths], paths)
        return True

    def on_files(self, names : list[str], paths : list[Path]):
        '''Files were dragged onto the terminal.'''
        for name, path in zip(names, paths):
            self.log.append(f'dropped: {name}  ({path.parent})')
        self.app.notify(f'{len(names)} file{"s" if len(names) > 1 else ""} dropped')


def main():
    App().main(ProtoScreen())


if __name__ == '__main__':
    main()
