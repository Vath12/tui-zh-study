import time
from dataclasses import dataclass
from typing import Callable

from .strokes.render import GLYPHS, RED, WHITE, TerminalCanvas
from .strokes.stroke import HanziStroke
from .strokes.stroke_render import ZiAnimation
from .vocabulary.hsk import HSKDictionary

SIZE = 80   # canvas size in pixels, per character
GAP = '  '  # between characters
MAX_CHARS = 8

# rendering_mode name -> the canvas glyphs it uses.
RENDERING_MODES = {'dots': 'braille', 'squares': 'octant'}
BLEND_MODES = ['majority', 'blend']
# color_mode name -> ZiAnimation options. mono: strokes white, the one being drawn red.
COLOR_MODES = {
    'multicolor': {'colored': True},
    'mono': {'colored': False, 'color': WHITE, 'drawing_color': RED},
}
# speed name -> seconds per stroke: 80% drawing it, 20% pause before the next.
SPEEDS = {'0.1s': 0.1, '0.25s': 0.25, '0.5s': 0.5, '0.75s': 0.75, '1s': 1}
PINYIN_MODES = ['show', 'hide']


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


class StrokeSession:
    '''Everything the stroke apps show, without any UI: feed it the input line
    with input_changed() and submit(), call tick() every frame, and draw
    characters(), pinyin() and status().

    It animates the strokes of the last `n_chars` characters typed, side by
    side, with their pinyin. Input starting with / is a command, run on
    submit: "/name arg ...". Commands live in self.commands as
    name -> (callback, help). A callback gets the arguments as a list of
    strings and returns a message for the status line (or None).'''

    def __init__(self, on_quit : Callable[[], None]):
        HanziStroke._load_lazy()
        HSKDictionary._load_lazy()
        self.on_quit = on_quit
        self.slots : list[Slot] = []
        # The characters (with stroke data) in the last non-empty input, each
        # with its pinyin in context.
        self.typed : list[tuple[str, list[str]]] = []
        self.message = ''
        self.char_size = SIZE   # canvas size in pixels, per character

        self.n_chars = 4
        self.blend_mode = 'majority'
        self.rendering_mode = 'squares'
        self.color_mode = 'multicolor'
        self.speed = '0.5s'
        self.pinyin_mode = 'show'
        # The terminal's colors, for TerminalCanvas: 'truecolor' or '256'. A UI
        # that converts colors itself (prompt_toolkit does) can leave it.
        self.terminal_colors = 'truecolor'

        self.commands = {
            'help': (self.cmd_help, 'list commands'),
            'render': (self.cmd_render, f'set how the character is drawn: {", ".join(RENDERING_MODES)}'),
            'blend': (self.cmd_blend, f'set how a cell picks its color: {", ".join(BLEND_MODES)}'),
            'color': (self.cmd_color, f'set the stroke colors: {", ".join(COLOR_MODES)}'),
            'speed': (self.cmd_speed, f'time per stroke: {", ".join(SPEEDS)}'),
            'pinyin': (self.cmd_pinyin, f'show or hide the pinyin: {", ".join(PINYIN_MODES)}'),
            'chars': (self.cmd_chars, f'how many characters to show side by side (1-{MAX_CHARS})'),
            'quit': (self.cmd_quit, 'exit'),
        }

    def new_canvas(self) -> TerminalCanvas:
        canvas = TerminalCanvas(self.char_size, self.char_size)
        self.apply_modes(canvas)
        return canvas

    def apply_modes(self, canvas : TerminalCanvas):
        canvas.glyphs = RENDERING_MODES[self.rendering_mode]
        canvas.cell_color = self.blend_mode
        canvas.color_mode = self.terminal_colors

    def new_animation(self, char : str, canvas : TerminalCanvas) -> ZiAnimation:
        per_stroke = SPEEDS[self.speed]
        return ZiAnimation(HanziStroke.get_strokes(char), canvas, **COLOR_MODES[self.color_mode],
                           stroke_time=per_stroke * 0.8, pause=per_stroke * 0.2)

    def present(self, chars : list[tuple[str, list[str]]]):
        '''Show these characters (character, pinyin), as if they'd been typed.
        For UIs that pick the characters themselves rather than from input.'''
        self.typed = chars
        self.show(chars)

    def set_char_size(self, size : int):
        '''Change the canvas size (pixels per character), redrawing what's shown
        at the new size. The animations start over.'''
        if size != self.char_size:
            self.char_size = size
            self.slots = []
            self.show(self.typed)

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

    # Input

    def input_changed(self, text : str):
        if text.startswith('/'):
            # Typing a command: show the commands it could be.
            typed = text[1:].split(' ')[0]
            matches = [f'/{name}' for name in self.commands if name.startswith(typed)]
            self.message = '  '.join(matches) if matches else f'unknown command /{typed}'
            return
        # Animate the last characters that have stroke data; leave the current
        # ones up if there aren't any (e.g. the input was just cleared). The
        # pinyin comes from the whole input, so characters in a word get the
        # word's reading (谢谢 xièxie, 银行 yínháng).
        chars = [(c, p) for c, p in HSKDictionary.text_pinyin(text) if c in HanziStroke.stroke_data]
        if chars:
            self.typed = chars
            self.show(chars)
            self.message = ''
        elif text.strip():
            self.message = 'no stroke data for that'

    def submit(self, text : str):
        '''Enter: run the command if it's one. The UI then clears the input.'''
        if text.startswith('/'):
            self.message = self.run_command(text[1:]) or ''

    def run_command(self, line : str) -> str | None:
        name, *args = line.split() or ['']
        if name not in self.commands:
            return f'unknown command /{name}, try /help'
        callback, _ = self.commands[name]
        return callback(args)

    # Commands

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

    def cmd_speed(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in SPEEDS:
            return f'usage: /speed {"|".join(SPEEDS)}  (now {self.speed})'
        self.speed = args[0]
        for slot in self.slots:
            # Carry on from the same point in the animation, at the new speed.
            done = (slot.elapsed() % slot.animation.duration) / slot.animation.duration
            slot.animation = self.new_animation(slot.char, slot.canvas)
            slot.started = time.monotonic() - done * slot.animation.duration
        return f'speed: {args[0]} per stroke'

    def cmd_pinyin(self, args : list[str]) -> str:
        if len(args) != 1 or args[0] not in PINYIN_MODES:
            return f'usage: /pinyin {"|".join(PINYIN_MODES)}  (now {self.pinyin_mode})'
        self.pinyin_mode = args[0]
        return f'pinyin: {args[0]}'

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
        self.set_n_chars(int(args[0]))
        return f'showing {self.n_chars} character{"s" if self.n_chars > 1 else ""}'

    def set_n_chars(self, n : int) -> int:
        '''Show up to n characters side by side (clamped to 1-MAX_CHARS),
        updating what's on screen now. Returns the new n_chars.'''
        n = max(1, min(n, MAX_CHARS))
        if n != self.n_chars:
            self.n_chars = n
            self.show(self.typed)
        return n

    @property
    def char_cols(self) -> int:
        '''Terminal columns one character takes with the current rendering mode.'''
        return -(-self.char_size // GLYPHS[RENDERING_MODES[self.rendering_mode]].width)

    def fit_chars(self, width : int) -> int:
        '''How many characters fit side by side in `width` columns (at least 1).'''
        return max(1, (width + len(GAP)) // (self.char_cols + len(GAP)))

    def cmd_quit(self, args : list[str]) -> None:
        self.on_quit()

    # Output

    def tick(self):
        '''Advance the animations to now. Call once per frame.'''
        for slot in self.slots:
            slot.animation.draw(slot.elapsed())

    @property
    def rows(self) -> int:
        return max((s.canvas.rows for s in self.slots), default=0)

    def characters(self) -> str:
        '''The characters' canvases side by side.'''
        columns = [s.canvas.render().split('\n') for s in self.slots]
        return '\n'.join(GAP.join(line) for line in zip(*columns))

    @property
    def show_pinyin(self) -> bool:
        '''Whether the UI should show the pinyin line at all.'''
        return self.pinyin_mode == 'show'

    def pinyin(self) -> str:
        '''Each character's pinyin, centered under its canvas ('' if hidden).'''
        if not self.show_pinyin:
            return ''
        return GAP.join(' / '.join(s.pinyin).center(s.canvas.cols) for s in self.slots)

    def status(self) -> str:
        if self.message:
            return self.message
        if not self.slots:
            return 'type a character'

        return ''