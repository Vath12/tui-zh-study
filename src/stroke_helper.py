import asyncio
import time

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from .strokes.render import RED, WHITE, TerminalCanvas
from .strokes.stroke import HanziStroke
from .strokes.stroke_render import ZiAnimation

SIZE = 80   # canvas size in pixels
FPS = 30

# rendering_mode name -> the canvas glyphs it uses.
RENDERING_MODES = {'dots': 'braille', 'quadrants': 'quadrant', 'octants': 'octant'}
BLEND_MODES = ['majority', 'blend']
# color_mode name -> ZiAnimation options. mono: strokes white, the one being drawn red.
COLOR_MODES = {
    'multicolor': {'colored': True},
    'mono': {'colored': False, 'color': WHITE, 'drawing_color': RED},
}


class StrokeApp:
    '''An inline terminal app: type characters in the input line and the window
    above animates the strokes of the last one you typed. Enter clears the
    input; Ctrl-C or Ctrl-D quits.

    Input starting with / is a command, run on Enter: "/name arg ...". Commands
    live in self.commands as name -> (callback, help). A callback gets the
    arguments as a list of strings and returns a message for the status line
    (or None).'''

    def __init__(self):
        HanziStroke._load_lazy()
        self.canvas = TerminalCanvas(SIZE, SIZE)
        self.animation : ZiAnimation | None = None
        self.started = 0.0
        self.message = ''

        self.blend_mode = 'majority'
        self.rendering_mode = 'dots'
        self.color_mode = 'multicolor'
        self.apply_modes()

        self.commands = {
            'help': (self.cmd_help, 'list commands'),
            'render': (self.cmd_render, f'set how the character is drawn: {", ".join(RENDERING_MODES)}'),
            'blend': (self.cmd_blend, f'set how a cell picks its color: {", ".join(BLEND_MODES)}'),
            'color': (self.cmd_color, f'set the stroke colors: {", ".join(COLOR_MODES)}'),
            'quit': (self.cmd_quit, 'exit'),
        }

        self.input = TextArea(prompt='> ', multiline=False, accept_handler=self.on_accept)
        self.input.buffer.on_text_changed += self.on_text_changed

        keys = KeyBindings()
        @keys.add('c-c')
        @keys.add('c-d')
        def _(event):
            event.app.exit()

        self.app = Application(
            layout=Layout(HSplit([
                # Height is a callable so the window follows the canvas when the rendering mode changes.
                Window(FormattedTextControl(lambda: ANSI(self.canvas.render())), height=lambda: self.canvas.rows),
                Window(FormattedTextControl(self.status), height=1),
                self.input,
            ]), focused_element=self.input),
            key_bindings=keys,
            full_screen=False,
        )

    def apply_modes(self):
        self.canvas.glyphs = RENDERING_MODES[self.rendering_mode]
        self.canvas.cell_color = self.blend_mode

    def on_accept(self, buffer) -> bool:
        '''Enter: run the command if it's one, then clear the input.'''
        if buffer.text.startswith('/'):
            self.message = self.run_command(buffer.text[1:]) or ''
        return False

    def run_command(self, line : str) -> str | None:
        name, *args = line.split() or ['']
        if name not in self.commands:
            return f'unknown command /{name}, try /help'
        callback, _ = self.commands[name]
        return callback(args)

    def cmd_help(self, args : list[str]) -> str:
        return '   '.join(f'/{name}: {help}' for name, (_, help) in self.commands.items())

    def cmd_render(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in RENDERING_MODES:
            return f'usage: /render {"|".join(RENDERING_MODES)}  (now {self.rendering_mode})'
        self.rendering_mode = args[0]
        self.apply_modes()
        return f'rendering with {args[0]}'

    def cmd_blend(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in BLEND_MODES:
            return f'usage: /blend {"|".join(BLEND_MODES)}  (now {self.blend_mode})'
        self.blend_mode = args[0]
        self.apply_modes()
        return f'cell colors by {args[0]}'

    def cmd_color(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in COLOR_MODES:
            return f'usage: /color {"|".join(COLOR_MODES)}  (now {self.color_mode})'
        self.color_mode = args[0]
        if self.animation:
            # Same character, new colors; keep the timing so it carries on where it was.
            self.animation = self.new_animation(self.animation.zi)
        return f'colors: {args[0]}'

    def new_animation(self, zi) -> ZiAnimation:
        return ZiAnimation(zi, self.canvas, **COLOR_MODES[self.color_mode])

    def cmd_quit(self, args : list[str]) -> None:
        self.app.exit()

    def on_text_changed(self, buffer):
        if buffer.text.startswith('/'):
            # Typing a command: show the commands it could be.
            typed = buffer.text[1:].split(' ')[0]
            matches = [f'/{name}' for name in self.commands if name.startswith(typed)]
            self.message = '  '.join(matches) if matches else f'unknown command /{typed}'
            return
        # Animate the last character that has stroke data; leave the current
        # animation up if there isn't one (e.g. the input was just cleared).
        for char in reversed(buffer.text):
            if char in HanziStroke.stroke_data:
                if not self.animation or self.animation.zi.unicode != char:
                    self.animation = self.new_animation(HanziStroke.get_strokes(char))
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
