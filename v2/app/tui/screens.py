from .keys import Key
from .style import DIM, PLAIN
from .widget import Column, Screen
from .widgets import SettingsPanel, Spacer, Text


class SettingsMenu(Screen):
    '''The app's settings (App.settings) as a menu over the bottom of the
    screen, with the result of the last change above it. Tab or Esc closes
    it; any other key it doesn't use closes it and goes to the screen below
    (so you can just start typing).'''

    opaque = False

    def on_enter(self):
        app = self.app
        self.panel = SettingsPanel(app.settings, on_message=app.notify, on_close=lambda: app.pop(self))
        rule = Text(lambda: '─' * max(0, self.rect.width), DIM, wrap=False, height=1)
        message = Text(lambda: app.message, DIM, wrap=False, height=1)
        self.add(Column(Spacer(), Column(rule, message, self.panel, background=PLAIN)))
        self.focused = self.panel

    def handle_key(self, key : Key) -> bool:
        # Reached only for keys the panel didn't use.
        app = self.app
        app.pop(self)
        app.dispatch(key)
        return True
