import asyncio

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from .stroke_session import StrokeSession

FPS = 30


class StrokeApp:
    '''An inline prompt_toolkit app for StrokeSession: the animated characters,
    their pinyin and a status line, above a normal input line. Enter clears
    the input (running it first if it's a /command); Ctrl-C or Ctrl-D quits.'''

    def __init__(self):
        self.session = StrokeSession(on_quit=lambda: self.app.exit())

        self.input = TextArea(prompt='> ', multiline=False, accept_handler=self.on_accept)
        self.input.buffer.on_text_changed += lambda buffer: self.session.input_changed(buffer.text)

        keys = KeyBindings()
        @keys.add('c-c')
        @keys.add('c-d')
        def _(event):
            event.app.exit()

        s = self.session
        self.app = Application(
            layout=Layout(HSplit([
                # Height is a callable so the window follows the canvas when the rendering mode changes.
                Window(FormattedTextControl(lambda: ANSI(s.characters())), height=lambda: s.rows),
                Window(FormattedTextControl(s.pinyin), height=1),
                Window(FormattedTextControl(s.status), height=1),
                self.input,
            ]), focused_element=self.input),
            key_bindings=keys,
            full_screen=False,
        )

    def on_accept(self, buffer) -> bool:
        self.session.submit(buffer.text)
        return False  # clear the input

    async def animate(self):
        while True:
            self.session.tick()
            self.app.invalidate()
            await asyncio.sleep(1 / FPS)

    async def run(self):
        task = asyncio.create_task(self.animate())
        try:
            await self.app.run_async()
        finally:
            task.cancel()


if __name__ == '__main__':
    asyncio.run(StrokeApp().run())
