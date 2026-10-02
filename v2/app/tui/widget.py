from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, NamedTuple

from .cells import Region
from .keys import Key
from .style import Style

if TYPE_CHECKING:
    from .app import App
    from .commands import Action, Setting


class Rect(NamedTuple):
    x : int
    y : int
    width : int
    height : int


@dataclass(frozen=True)
class Fill:
    '''A size that takes a share of the space left over: Fill(2) gets twice
    what Fill(1) does.'''
    weight : float = 1


FILL = Fill()

# A size in a Column (height) or Row (width): a fixed number of cells, None for
# "as much as it needs" (measure()), or a Fill.
Size = int | None | Fill


class Widget:
    '''Something on screen. Subclasses override draw(), and as needed
    measure() / measure_width() (how big they'd like to be), handle_key(),
    cursor() and animating().

    `height` and `width` say how big it is in a Column or Row (see Size).
    `visible` can be a bool or a function returning one, checked every frame.
    `bindings` maps key names to functions, run when a key reaches this widget
    (it or something inside it is focused) and nothing handled it first.
    With a `background` style, its whole area is filled before it draws (so
    nothing underneath shows through, e.g. in an overlay). When a Column or
    Row is short of space, children with a higher `priority` get theirs first.'''

    focusable = False

    def __init__(self, *, height : Size = None, width : Size = None,
                 visible : bool | Callable[[], bool] = True, bindings : dict[str, Callable] | None = None,
                 background : Style | None = None, priority : int = 0):
        self.height = height
        self.width = width
        self.visible = visible
        self.bindings : dict[str, Callable] = dict(bindings or {})
        self.background = background
        self.priority = priority
        self.parent : Widget | None = None
        self.rect = Rect(0, 0, 0, 0)   # where it was last drawn, in screen coordinates

    # Tree

    def children(self) -> list['Widget']:
        return []

    def walk(self) -> Iterator['Widget']:
        '''This widget and everything inside it that's visible, in drawing order.'''
        if not self.shown:
            return
        yield self
        for child in self.children():
            yield from child.walk()

    @property
    def shown(self) -> bool:
        return self.visible() if callable(self.visible) else self.visible

    @property
    def screen(self) -> 'Screen | None':
        w = self
        while w is not None and not isinstance(w, Screen):
            w = w.parent
        return w

    @property
    def app(self) -> 'App | None':
        screen = self.screen
        return screen.app if screen else None

    def invalidate(self):
        '''Ask for a redraw.'''
        if self.app:
            self.app.invalidate()

    def bind(self, key : str, fn : Callable) -> 'Widget':
        self.bindings[key] = fn
        return self

    # Size

    def measure(self, width : int) -> int:
        '''The height it would like at this width.'''
        return self.height if isinstance(self.height, int) else 0

    def measure_width(self) -> int:
        '''The width it would like.'''
        return self.width if isinstance(self.width, int) else 0

    # Drawing

    def render(self, region : Region):
        '''Draw into `region` (called by the parent; widgets override draw).'''
        self.rect = Rect(region.origin[0], region.origin[1], region.width, region.height)
        if self.background is not None:
            region.fill(self.background)
        self.draw(region)

    def draw(self, region : Region):
        pass

    def animating(self) -> bool:
        '''Whether it changes on its own, so the app keeps drawing frames.'''
        return False

    # Input

    def handle_key(self, key : Key) -> bool:
        '''Handle a key; return True if it was used. Called on the focused
        widget, then each parent in turn until one returns True.'''
        return False

    def handle_drop(self, paths : list[Path]) -> bool:
        '''Files dragged onto the terminal; return True if they were used.
        Called like handle_key: the focused widget, then its parents.'''
        return False

    def cursor(self) -> tuple[int, int] | None:
        '''Where the cursor goes while this is focused (relative to rect), or None.'''
        return None


class Container(Widget):
    def __init__(self, *children : Widget, gap : int = 0, **kwargs):
        super().__init__(**kwargs)
        self.gap = gap
        self._children : list[Widget] = []
        for child in children:
            self.add(child)

    def add(self, child : Widget, index : int | None = None) -> Widget:
        child.parent = self
        self._children.insert(len(self._children) if index is None else index, child)
        self.invalidate()
        return child

    def remove(self, child : Widget):
        self._children.remove(child)
        child.parent = None
        self.invalidate()

    def children(self) -> list[Widget]:
        return [c for c in self._children if c.shown]


def allocate(total : int, sizes : list[Size], measure : Callable[[int], int], gap : int = 0,
             priorities : list[int] | None = None) -> list[int]:
    '''Split `total` cells between items: fixed sizes and measured ones
    (None) first, then the rest shared out by Fill weight. If they don't all
    fit, higher priority items get theirs first, then earlier ones.'''
    total = max(0, total - gap * max(0, len(sizes) - 1))
    out = [0] * len(sizes)
    left = total
    priorities = priorities or [0] * len(sizes)
    for i in sorted(range(len(sizes)), key=lambda i: -priorities[i]):
        size = sizes[i]
        if isinstance(size, int) or size is None:
            out[i] = min(size if isinstance(size, int) else measure(i), left)
            left -= out[i]
    fills = [(i, s.weight) for i, s in enumerate(sizes) if isinstance(s, Fill)]
    weight = sum(w for _, w in fills)
    if fills and weight > 0:
        given = 0
        for n, (i, w) in enumerate(fills):
            share = left - given if n == len(fills) - 1 else int(left * w / weight)
            out[i] = max(0, share)
            given += out[i]
    return out


class Column(Container):
    '''Children top to bottom, sized by their `height`.'''

    def _heights(self, width : int, height : int) -> list[int]:
        kids = self.children()
        return allocate(height, [c.height for c in kids], lambda i: kids[i].measure(width), self.gap,
                        [c.priority for c in kids])

    def measure(self, width : int) -> int:
        if isinstance(self.height, int):
            return self.height
        kids = self.children()
        return sum(c.measure(width) for c in kids) + self.gap * max(0, len(kids) - 1)

    def measure_width(self) -> int:
        return max((c.measure_width() for c in self.children()), default=0)

    def draw(self, region : Region):
        y = 0
        for child, h in zip(self.children(), self._heights(region.width, region.height)):
            child.render(region.sub(0, y, region.width, h))
            y += h + self.gap


class Row(Container):
    '''Children left to right, sized by their `width`.'''

    def _widths(self, width : int) -> list[int]:
        kids = self.children()
        return allocate(width, [c.width for c in kids], lambda i: kids[i].measure_width(), self.gap,
                        [c.priority for c in kids])

    def measure(self, width : int) -> int:
        if isinstance(self.height, int):
            return self.height
        return max((c.measure(w) for c, w in zip(self.children(), self._widths(width))), default=0)

    def measure_width(self) -> int:
        kids = self.children()
        return sum(c.measure_width() for c in kids) + self.gap * max(0, len(kids) - 1)

    def draw(self, region : Region):
        x = 0
        for child, w in zip(self.children(), self._widths(region.width)):
            child.render(region.sub(x, 0, w, region.height))
            x += w + self.gap


class Layers(Container):
    '''Children drawn on top of each other, each over the whole area.'''

    def measure(self, width : int) -> int:
        return max((c.measure(width) for c in self.children()), default=0)

    def measure_width(self) -> int:
        return max((c.measure_width() for c in self.children()), default=0)

    def draw(self, region : Region):
        for child in self.children():
            child.render(region.sub(0, 0, region.width, region.height))


class Align(Container):
    '''One child at its own size (measure / measure_width, or its fixed
    width and height), placed in the area: h is 'left', 'center' or 'right',
    v is 'top', 'middle' or 'bottom'.'''

    def __init__(self, child : Widget, h : str = 'center', v : str = 'middle', **kwargs):
        super().__init__(child, **kwargs)
        self.h, self.v = h, v

    def measure(self, width : int) -> int:
        return sum(c.measure(width) for c in self.children())

    def measure_width(self) -> int:
        return max((c.measure_width() for c in self.children()), default=0)

    def draw(self, region : Region):
        for child in self.children():
            w = child.width if isinstance(child.width, int) else min(child.measure_width() or region.width, region.width)
            h = child.height if isinstance(child.height, int) else min(child.measure(w), region.height)
            x = {'left': 0, 'center': (region.width - w) // 2, 'right': region.width - w}[self.h]
            y = {'top': 0, 'middle': (region.height - h) // 2, 'bottom': region.height - h}[self.v]
            child.render(region.sub(x, y, w, h))


class Pad(Container):
    '''One child with space around it.'''

    def __init__(self, child : Widget, left : int = 0, right : int = 0, top : int = 0, bottom : int = 0, **kwargs):
        super().__init__(child, **kwargs)
        self.pad = (left, right, top, bottom)

    def measure(self, width : int) -> int:
        l, r, t, b = self.pad
        return t + b + sum(c.measure(width - l - r) for c in self.children())

    def measure_width(self) -> int:
        l, r, _, _ = self.pad
        return l + r + max((c.measure_width() for c in self.children()), default=0)

    def draw(self, region : Region):
        l, r, t, b = self.pad
        for child in self.children():
            child.render(region.sub(l, t, region.width - l - r, region.height - t - b))


class Screen(Container):
    '''A whole view of the app, pushed onto App.screens. Only the top screen
    gets keys. An `opaque = False` screen (a menu, a dialog) is drawn over
    the ones below it instead of hiding them.

    A screen remembers what's focused in it. While it's on the stack, the
    `settings` and `actions` it lists are in the app's settings (and so the
    menu and /commands).'''

    opaque = True

    def __init__(self, *children : Widget, **kwargs):
        self._app : 'App | None' = None
        self.focused : Widget | None = None
        self.settings : list['Setting | Action'] = []
        super().__init__(*children, **kwargs)

    @property
    def app(self) -> 'App | None':
        return self._app

    def focus(self, widget : Widget | None):
        self.focused = widget
        self.invalidate()

    def focus_first(self):
        self.focused = next((w for w in self.walk() if w.focusable), None)

    def on_enter(self):
        '''Called when pushed onto the app.'''

    def on_exit(self):
        '''Called when popped off.'''

    def on_resume(self):
        '''Called when it's the top screen again (the one above was popped).'''

    def draw(self, region : Region):
        for child in self.children():
            child.render(region.sub(0, 0, region.width, region.height))
