import time
from dataclasses import dataclass
from typing import Callable

from v2.stroke.render import GLYPHS, RED, WHITE, TerminalCanvas
from v2.stroke.stroke import HanziStroke
from v2.stroke.stroke_render import ZiAnimation

from .tui import PLAIN, FILL, Region, Setting, Style, Widget

MAX_SIZE = 80   # canvas size in pixels, per character, when there's room
MIN_SIZE = 8
GAP = 2         # columns between characters

# rendering mode name -> the canvas glyphs it uses.
RENDERING_MODES = {'dots': 'braille', 'squares': 'octant'}
BLEND_MODES = ['majority', 'blend']
# color mode name -> ZiAnimation options. mono: strokes white, the one being drawn red.
COLOR_MODES = {
    'multicolor': {'colored': True},
    'mono': {'colored': False, 'color': WHITE, 'drawing_color': RED},
}
# speed name -> seconds per stroke: 80% drawing it, 20% pause before the next.
SPEEDS = {'0.1s': 0.1, '0.25s': 0.25, '0.5s': 0.5, '0.75s': 0.75, '1s': 1}


class StrokeLook:
    '''How strokes are drawn, shared by every CharacterStrip: the rendering
    mode, how cells pick a color, the stroke colors and the speed. settings()
    gives them as Settings for the app's menu and /commands.'''

    def __init__(self):
        self.rendering_mode = 'squares'
        self.blend_mode = 'majority'
        self.color_mode = 'multicolor'
        self.speed = '0.5s'

    @property
    def glyphs(self) -> str:
        return RENDERING_MODES[self.rendering_mode]

    def settings(self) -> list[Setting]:
        def setter(field):
            return lambda value: setattr(self, field, value)
        return [
            Setting('render', 'Render', list(RENDERING_MODES), lambda: self.rendering_mode, setter('rendering_mode'),
                    f'how characters are drawn: {", ".join(RENDERING_MODES)}'),
            Setting('blend', 'Blend', BLEND_MODES, lambda: self.blend_mode, setter('blend_mode'),
                    f'how a cell picks its color: {", ".join(BLEND_MODES)}'),
            Setting('color', 'Colors', list(COLOR_MODES), lambda: self.color_mode, setter('color_mode'),
                    f'stroke colors: {", ".join(COLOR_MODES)}'),
            Setting('speed', 'Speed', list(SPEEDS), lambda: self.speed, setter('speed'),
                    f'time per stroke: {", ".join(SPEEDS)}'),
        ]

    def animation(self, char : str, canvas : TerminalCanvas) -> ZiAnimation:
        per_stroke = SPEEDS[self.speed]
        return ZiAnimation(HanziStroke.get_strokes(char), canvas, **COLOR_MODES[self.color_mode],
                           stroke_time=per_stroke * 0.8, pause=per_stroke * 0.2)


@dataclass
class Slot:
    '''One character on screen, with its own canvas and animation.'''
    char : str
    pinyin : list[str]          # its reading(s) where it was typed
    started : float
    canvas : TerminalCanvas | None = None
    animation : ZiAnimation | None = None
    built : tuple = ()          # (size, color mode, speed) the animation was made for

    def elapsed(self) -> float:
        return time.monotonic() - self.started


def has_strokes(char : str) -> bool:
    HanziStroke._load_lazy()
    return char in HanziStroke.stroke_data


class CharacterStrip(Widget):
    '''Characters side by side, each writing itself stroke by stroke, with its
    pinyin underneath. They're as big as fits (up to max_size pixels, or
    without limit if it's None) and centered in the area.

    show() sets the characters; one that's already there keeps its animation
    and where it's got to. pinyin can be a bool or a function returning one.
    pinyin_styles, if set, styles each character's pinyin (e.g. green/red).'''

    def __init__(self, look : StrokeLook, pinyin : bool | Callable[[], bool] = True, max_size : int | None = MAX_SIZE,
                 **kwargs):
        kwargs.setdefault('height', FILL)
        super().__init__(**kwargs)
        self.look = look
        self.pinyin = pinyin
        self.max_size = max_size
        self.slots : list[Slot] = []
        self.pinyin_styles : list[Style] | None = None

    @property
    def chars(self) -> str:
        return ''.join(s.char for s in self.slots)

    def show(self, chars : list[tuple[str, list[str]]]):
        '''Show these (character, pinyin); ones without stroke data are skipped.'''
        old, self.slots = self.slots, []
        for char, pinyin in chars:
            if not has_strokes(char):
                continue
            same = next((s for s in old if s.char == char), None)
            if same:
                old.remove(same)
                same.pinyin = pinyin
                self.slots.append(same)
            else:
                self.slots.append(Slot(char, pinyin, time.monotonic()))
        self.pinyin_styles = None
        self.invalidate()

    def restart(self):
        '''Start every animation over.'''
        for slot in self.slots:
            slot.started = time.monotonic()
        self.invalidate()

    def animating(self) -> bool:
        return bool(self.slots)

    @property
    def show_pinyin(self) -> bool:
        return self.pinyin() if callable(self.pinyin) else self.pinyin

    def fit(self, width : int, height : int) -> int:
        '''The canvas size (pixels) that fits all the characters in width x height cells.'''
        n = max(1, len(self.slots))
        g = GLYPHS[self.look.glyphs]
        cols = (width - GAP * (n - 1)) // n
        rows = height - (1 if self.show_pinyin else 0)
        size = min(cols * g.width, rows * g.height)
        if self.max_size is not None:
            size = min(size, self.max_size)
        return max(MIN_SIZE, size - size % 4)

    def _prepare(self, slot : Slot, size : int):
        '''Make sure the slot's canvas and animation match the size and the look.'''
        look = self.look
        built = (size, look.color_mode, look.speed)
        if slot.built != built:
            if slot.canvas is None or slot.built[0] != size:
                slot.canvas = TerminalCanvas(size, size)
            if slot.animation is not None and slot.built[2] != look.speed:
                # Carry on from the same point in the animation, at the new speed.
                done = (slot.elapsed() % slot.animation.duration) / slot.animation.duration
                slot.animation = look.animation(slot.char, slot.canvas)
                slot.started = time.monotonic() - done * slot.animation.duration
            else:
                slot.animation = look.animation(slot.char, slot.canvas)
            slot.built = built
        slot.canvas.glyphs = look.glyphs
        slot.canvas.cell_color = look.blend_mode

    def draw(self, region : Region):
        if not self.slots:
            return
        size = self.fit(region.width, region.height)
        for slot in self.slots:
            self._prepare(slot, size)
            slot.animation.draw(slot.elapsed())
        cols, rows = self.slots[0].canvas.cols, self.slots[0].canvas.rows
        total = len(self.slots) * cols + GAP * (len(self.slots) - 1)
        x = max(0, (region.width - total) // 2)
        y = max(0, (region.height - rows - (1 if self.show_pinyin else 0)) // 2)
        for i, slot in enumerate(self.slots):
            sx = x + i * (cols + GAP)
            region.put_ansi(sx, y, slot.canvas.render())
            if self.show_pinyin:
                style = self.pinyin_styles[i] if self.pinyin_styles and i < len(self.pinyin_styles) else PLAIN
                region.put(sx, y + rows, ' / '.join(slot.pinyin).center(cols), style)
