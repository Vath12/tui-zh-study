import asyncio
import time
from dataclasses import dataclass

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from .strokes.render import RED, WHITE, TerminalCanvas
from .strokes.stroke import HanziStroke
from .strokes.stroke_render import ZiAnimation
from .vocabulary.hsk import HSKDictionary

SIZE = 80   # canvas size in pixels, per character
FPS = 30
GAP = '  '  # between characters
MAX_CHARS = 8

# rendering_mode name -> the canvas glyphs it uses.
RENDERING_MODES = {'dots': 'braille', 'quadrants': 'quadrant', 'octants': 'octant'}
BLEND_MODES = ['majority', 'blend']
# color_mode name -> ZiAnimation options. mono: strokes white, the one being drawn red.
COLOR_MODES = {
    'multicolor': {'colored': True},
    'mono': {'colored': False, 'color': WHITE, 'drawing_color': RED},
}


@dataclass
class Slot:
    '''One character on screen, with its own canvas and animation.'''
    canvas : TerminalCanvas
    animation : ZiAnimation
    started : float
    pinyin : list[str]   # its reading(s) in the word it was typed in

    @property
    def char(self) -> str:
        return self.animation.zi.unicode

    def elapsed(self) -> float:
        return time.monotonic() - self.started


class StrokeApp:
    '''An inline terminal app: type characters in the input line and the window
    above animates the strokes of the last `n_chars` you typed, side by side,
    with their pinyin underneath. Enter clears the input; Ctrl-C or Ctrl-D quits.

    Input starting with / is a command, run on Enter: "/name arg ...". Commands
    live in self.commands as name -> (callback, help). A callback gets the
    arguments as a list of strings and returns a message for the status line
    (or None).'''

    def __init__(self):
        HanziStroke._load_lazy()
        HSKDictionary._load_lazy()
        self.slots : list[Slot] = []
        # The characters (with stroke data) in the last non-empty input, each
        # with its pinyin in context.
        self.typed : list[tuple[str, list[str]]] = []
        self.message = ''

        self.n_chars = 2
        self.blend_mode = 'majority'
        self.rendering_mode = 'dots'
        self.color_mode = 'multicolor'

        self.commands = {
            'help': (self.cmd_help, 'list commands'),
            'render': (self.cmd_render, f'set how the character is drawn: {", ".join(RENDERING_MODES)}'),
            'blend': (self.cmd_blend, f'set how a cell picks its color: {", ".join(BLEND_MODES)}'),
            'color': (self.cmd_color, f'set the stroke colors: {", ".join(COLOR_MODES)}'),
            'chars': (self.cmd_chars, f'how many characters to show side by side (1-{MAX_CHARS})'),
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
                Window(FormattedTextControl(lambda: ANSI(self.characters())), height=lambda: self.rows),
                Window(FormattedTextControl(self.pinyin), height=1),
                Window(FormattedTextControl(self.status), height=1),
                self.input,
            ]), focused_element=self.input),
            key_bindings=keys,
            full_screen=False,
        )

    def new_canvas(self) -> TerminalCanvas:
        canvas = TerminalCanvas(SIZE, SIZE)
        self.apply_modes(canvas)
        return canvas

    def apply_modes(self, canvas : TerminalCanvas):
        canvas.glyphs = RENDERING_MODES[self.rendering_mode]
        canvas.cell_color = self.blend_mode

    def new_animation(self, char : str, canvas : TerminalCanvas) -> ZiAnimation:
        return ZiAnimation(HanziStroke.get_strokes(char), canvas, **COLOR_MODES[self.color_mode])

    def show(self, chars : list[tuple[str, list[str]]]):
        '''Show the last n_chars of `chars` (character, pinyin). A character
        that's already on screen keeps its animation (and where it's got to),
        even if it moves.'''
        old, self.slots = self.slots, []
        for char, pinyin in chars[-self.n_chars:]:
            same = next((s for s in old if s.char == char), None)
            if same:
                old.remove(same)
                same.pinyin = pinyin
                self.slots.append(same)
            else:
                canvas = self.new_canvas()
                self.slots.append(Slot(canvas, self.new_animation(char, canvas), time.monotonic(), pinyin))

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
        for slot in self.slots:
            self.apply_modes(slot.canvas)
        return f'rendering with {args[0]}'

    def cmd_blend(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in BLEND_MODES:
            return f'usage: /blend {"|".join(BLEND_MODES)}  (now {self.blend_mode})'
        self.blend_mode = args[0]
        for slot in self.slots:
            self.apply_modes(slot.canvas)
        return f'cell colors by {args[0]}'

    def cmd_color(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in COLOR_MODES:
            return f'usage: /color {"|".join(COLOR_MODES)}  (now {self.color_mode})'
        self.color_mode = args[0]
        for slot in self.slots:
            # Same character, new colors; keep the timing so it carries on where it was.
            slot.animation = self.new_animation(slot.char, slot.canvas)
        return f'colors: {args[0]}'

    def cmd_chars(self, args : list[str]) -> str:
        if len(args) != 1 or not args[0].isdigit() or not 1 <= int(args[0]) <= MAX_CHARS:
            return f'usage: /chars 1-{MAX_CHARS}  (now {self.n_chars})'
        self.n_chars = int(args[0])
        self.show(self.typed)
        return f'showing {self.n_chars} character{"s" if self.n_chars > 1 else ""}'

    def cmd_quit(self, args : list[str]) -> None:
        self.app.exit()

    def on_text_changed(self, buffer):
        if buffer.text.startswith('/'):
            # Typing a command: show the commands it could be.
            typed = buffer.text[1:].split(' ')[0]
            matches = [f'/{name}' for name in self.commands if name.startswith(typed)]
            self.message = '  '.join(matches) if matches else f'unknown command /{typed}'
            return
        # Animate the last characters that have stroke data; leave the current
        # ones up if there aren't any (e.g. the input was just cleared). The
        # pinyin comes from the whole input, so characters in a word get the
        # word's reading (谢谢 xièxie, 银行 yínháng).
        chars = [(c, p) for c, p in HSKDictionary.text_pinyin(buffer.text) if c in HanziStroke.stroke_data]
        if chars:
            self.typed = chars
            self.show(chars)
            self.message = ''
        elif buffer.text.strip():
            self.message = 'no stroke data for that'

    @property
    def rows(self) -> int:
        return max((s.canvas.rows for s in self.slots), default=0)

    def characters(self) -> str:
        '''The characters' canvases side by side.'''
        columns = [s.canvas.render().split('\n') for s in self.slots]
        return '\n'.join(GAP.join(line) for line in zip(*columns))

    def pinyin(self) -> str:
        '''Each character's pinyin, centered under its canvas.'''
        return GAP.join(' / '.join(s.pinyin).center(s.canvas.cols) for s in self.slots)

    def status(self) -> str:
        if self.message:
            return self.message
        if not self.slots:
            return 'type a character'
        strokes = []
        for s in self.slots:
            zi = s.animation.zi
            stroke = min(s.animation.stroke_at(s.elapsed()) + 1, zi.n_strokes)
            strokes.append(f'{zi.unicode} {stroke}/{zi.n_strokes}')
        return '   '.join(strokes)

    async def animate(self):
        while True:
            for slot in self.slots:
                slot.animation.draw(slot.elapsed())
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
