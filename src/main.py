import asyncio
import time

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from .strokes.render import TerminalCanvas
from .strokes.stroke import HanziStroke
from .strokes.stroke_render import ZiAnimation

SIZE = 80   # canvas size in pixels
FPS = 30


class StrokeApp:
    '''An inline terminal app: type characters in the input line and the window
    above animates the strokes of the last one you typed. Enter clears the
    input; Ctrl-C or Ctrl-D quits.'''

    def __init__(self):
        HanziStroke._load_lazy()
        self.canvas = TerminalCanvas(SIZE, SIZE)
        self.animation : ZiAnimation | None = None
        self.started = 0.0
        self.message = ''

        self.input = TextArea(prompt='> ', multiline=False, accept_handler=lambda buffer: False)
        self.input.buffer.on_text_changed += self.on_text_changed

        keys = KeyBindings()
        @keys.add('c-c')
        @keys.add('c-d')
        def _(event):
            event.app.exit()

        self.app = Application(
            layout=Layout(HSplit([
                Window(FormattedTextControl(lambda: ANSI(self.canvas.render())), height=self.canvas.rows),
                Window(FormattedTextControl(self.status), height=1),
                self.input,
            ]), focused_element=self.input),
            key_bindings=keys,
            full_screen=False,
        )

    def on_text_changed(self, buffer):
        # Animate the last character that has stroke data; leave the current
        # animation up if there isn't one (e.g. the input was just cleared).
        for char in reversed(buffer.text):
            if char in HanziStroke.stroke_data:
                if not self.animation or self.animation.zi.unicode != char:
                    self.animation = ZiAnimation(HanziStroke.get_strokes(char), self.canvas)
                    self.started = time.monotonic()
                self.message = ''
                return
        if buffer.text.strip():
            self.message = 'no stroke data for that'

    def status(self) -> str:
        if self.message:
            return self.message
        if not self.animation:
            return 'type a character'
        zi = self.animation.zi
        stroke = self.animation.stroke_at(time.monotonic() - self.started)
        return f'{zi.unicode}  stroke {min(stroke + 1, zi.n_strokes)}/{zi.n_strokes}'

    async def animate(self):
        while True:
            if self.animation:
                self.animation.draw(time.monotonic() - self.started)
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
