from typing import Callable

from .cells import Region, Rich, char_width, parse_ansi, rich_width, spans, split_lines, text_width, wrap
from .commands import Action, Setting, Settings
from .keys import Key
from .style import BOLD, DIM, PLAIN, REVERSE, CYAN, Style, fg
from .widget import FILL, Widget

# Content can be given as a value, or a function called every frame.
Dynamic = Rich | Callable[[], Rich]


def _get(content : Dynamic) -> Rich:
    return content() if callable(content) else content


def _aligned(line_width : int, width : int, align : str) -> int:
    return {'left': 0, 'center': (width - line_width) // 2, 'right': width - line_width}[align]


class Text(Widget):
    '''Rich text (see cells.Rich), wrapped to the width unless wrap=False.
    align: 'left', 'center' or 'right', per line.'''

    def __init__(self, content : Dynamic = '', style : Style = PLAIN, align : str = 'left', wrap : bool = True, **kwargs):
        super().__init__(**kwargs)
        self.content = content
        self.style = style
        self.align = align
        self.wrap = wrap

    def lines(self, width : int):
        lines = split_lines(spans(_get(self.content), self.style))
        if self.wrap:
            lines = [part for line in lines for part in wrap(line, width)]
        return lines

    def measure(self, width : int) -> int:
        if isinstance(self.height, int):
            return self.height
        return len(self.lines(width))

    def measure_width(self) -> int:
        if isinstance(self.width, int):
            return self.width
        return max((rich_width(line) for line in split_lines(_get(self.content))), default=0)

    def draw(self, region : Region):
        for y, line in enumerate(self.lines(region.width)[:region.height]):
            region.put(_aligned(rich_width(line), region.width, self.align), y, line)


class Ansi(Widget):
    '''Text with ANSI escape codes in it (like a TerminalCanvas render), as is.'''

    def __init__(self, content : str | Callable[[], str] = '', align : str = 'left', **kwargs):
        super().__init__(**kwargs)
        self.content = content
        self.align = align

    def lines(self):
        return parse_ansi(_get(self.content))

    def measure(self, width : int) -> int:
        return self.height if isinstance(self.height, int) else len(self.lines())

    def measure_width(self) -> int:
        if isinstance(self.width, int):
            return self.width
        return max((rich_width(line) for line in self.lines()), default=0)

    def draw(self, region : Region):
        lines = self.lines()
        width = max((rich_width(line) for line in lines), default=0)
        x = _aligned(width, region.width, self.align)
        region.put_lines(x, 0, lines[:region.height])


class Spacer(Widget):
    '''Empty space; takes whatever's left by default.'''

    def __init__(self, height=FILL, **kwargs):
        super().__init__(height=height, **kwargs)


class Input(Widget):
    '''A one-line text field: typing, backspace/delete, left/right, home/end
    (and Ctrl-A/E), Ctrl-U to clear, up/down through what was entered before.
    It scrolls sideways when the text is wider than the field.

    on_change(text) runs whenever the text changes, on_submit(text) on Enter;
    the field is cleared after on_submit unless it returns False. `hint` is
    shown dim at the right while there's room.'''

    focusable = True

    def __init__(self, prompt : Rich = '> ', on_submit : Callable[[str], bool | None] | None = None,
                 on_change : Callable[[str], None] | None = None, hint : Dynamic = '', **kwargs):
        kwargs.setdefault('height', 1)
        kwargs.setdefault('priority', 1)
        super().__init__(**kwargs)
        self.prompt = prompt
        self.on_submit = on_submit
        self.on_change = on_change
        self.hint = hint
        self.text = ''
        self.pos = 0           # cursor, as an index into text
        self.history : list[str] = []
        self._browsing = None  # index into history while going through it with up/down
        self._scroll = 0       # columns of text scrolled off the left

    def set_text(self, text : str, pos : int | None = None):
        changed = text != self.text
        self.text = text
        self.pos = len(text) if pos is None else max(0, min(pos, len(text)))
        if changed and self.on_change:
            self.on_change(text)
        self.invalidate()

    def clear(self):
        self.set_text('')

    def handle_key(self, key : Key) -> bool:
        t, p = self.text, self.pos
        name = key.name
        if name == 'enter':
            if t:
                self.history.append(t)
            self._browsing = None
            keep = self.on_submit(t) is False if self.on_submit else False
            if not keep:
                self.clear()
        elif name == 'backspace':
            if p:
                self.set_text(t[:p - 1] + t[p:], p - 1)
        elif name == 'delete' and p < len(t):
            self.set_text(t[:p] + t[p + 1:], p)
        elif name == 'left':
            self.pos = max(0, p - 1)
        elif name == 'right':
            self.pos = min(len(t), p + 1)
        elif name in ('home', 'ctrl+a'):
            self.pos = 0
        elif name in ('end', 'ctrl+e'):
            self.pos = len(t)
        elif name == 'ctrl+u':
            self.set_text('')
        elif name in ('up', 'down') and self.history:
            i = len(self.history) if self._browsing is None else self._browsing
            i = max(0, i - 1) if name == 'up' else i + 1
            self._browsing = i if i < len(self.history) else None
            self.set_text(self.history[i] if self._browsing is not None else '')
        elif name == 'paste':
            pasted = ' '.join(key.text.splitlines())   # one line
            self.set_text(t[:p] + pasted + t[p:], p + len(pasted))
        elif key.printable:
            self.set_text(t[:p] + key.text + t[p:], p + len(key.text))
        else:
            return False
        self.invalidate()
        return True

    def _layout(self, width : int) -> tuple[int, int]:
        '''(columns for the text, where the cursor is in them), scrolling so the cursor shows.'''
        room = max(1, width - rich_width(self.prompt))
        before = text_width(self.text[:self.pos])
        if before - self._scroll >= room:
            self._scroll = before - room + 1
        elif before < self._scroll:
            self._scroll = before
        # Scroll by whole characters, not half of a wide one.
        col = 0
        for c in self.text:
            if col >= self._scroll:
                break
            col += char_width(c)
        self._scroll = col
        return room, before - self._scroll

    def draw(self, region : Region):
        x = region.put(0, 0, self.prompt)
        room, _ = self._layout(region.width)
        # The text from the scroll position, as many columns as fit.
        skipped, shown, cols = 0, '', 0
        for c in self.text:
            w = char_width(c)
            if skipped < self._scroll:
                skipped += w
                continue
            if cols + w > room:
                break
            shown += c
            cols += w
        region.put(x, 0, shown)
        hint = _get(self.hint)
        if hint and region.width - x - cols - rich_width(hint) >= 2:
            region.put(region.width - rich_width(hint), 0, hint, DIM)

    def cursor(self) -> tuple[int, int] | None:
        _, col = self._layout(self.rect.width)
        return rich_width(self.prompt) + col, 0


class SettingsPanel(Widget):
    '''The settings menu: one row per Setting (its options, the current one
    highlighted) or Action, and a line of key hints. Up/down picks a row,
    left/right changes a setting, Enter or Space steps a setting or runs an
    action, and an action's `extra` rows run on their keys (rename on 'r',
    delete on Delete, ...). An action with `children` and no `run` opens its
    page: the rows are then its children, with a Back row, and its `hints`
    replace the panel's. Esc goes back a page, or calls on_close at the top;
    Tab always calls on_close.

    `settings` is where the top level comes from: a Settings (its
    menu_items()), or a function returning the rows. `hints` can be a
    function too, or None for no hints at the top.'''

    focusable = True
    HINTS = '  ↑↓ choose  ←→ change  Enter select  Tab/Esc close'
    BACK = Action('back', '‹ Back')

    def __init__(self, settings : 'Settings | Callable[[], list[Setting | Action]] | None',
                 on_message : Callable[[str | None], None] = lambda m: None,
                 on_close : Callable[[], None] = lambda: None, hints : Dynamic | None = HINTS, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings
        self.hints = hints
        self.on_message = on_message
        self.on_close = on_close
        self.selected = 0
        self.path : list[Action] = []        # the pages open, from the top
        self._came_from : list[int] = []     # the row selected on each page before it

    # Pages

    @property
    def page(self) -> Action | None:
        return self.path[-1] if self.path else None

    @property
    def title(self) -> str | None:
        return self.page.label if self.page else None

    def open(self, path : list[Action] = ()):
        '''Show this page (the Actions to it from the top; empty for the top).'''
        self.path, self._came_from, self.selected = list(path), [0] * len(path), 0
        self.invalidate()

    def back(self) -> bool:
        '''Up a page; False if already at the top.'''
        if not self.path:
            return False
        self.path.pop()
        self.selected = self._came_from.pop()
        self.invalidate()
        return True

    @property
    def items(self) -> list[Setting | Action]:
        if self.page:
            return [*self.page.children(), self.BACK]
        if self.settings is None:
            return []
        return self.settings() if callable(self.settings) else self.settings.menu_items()

    def hint_lines(self) -> list:
        hints = _get(self.page.hints if self.page else self.hints)
        return split_lines(hints) if hints else []

    # Size

    def measure(self, width : int) -> int:
        return len(self.items) + len(self.hint_lines())

    def measure_width(self) -> int:
        items = self.items
        label = max((len(i.label) for i in items), default=0)
        detail = max((rich_width(d) for i in items if isinstance(i, Action) and (d := i.get_detail())), default=0)
        options = max((sum(len(o) + 3 for o in i.choices()) for i in items if isinstance(i, Setting)), default=0)
        hints = max((rich_width(line) for line in self.hint_lines()), default=0)
        return max(5 + label + max(detail, options), hints)

    # Keys

    def select(self, item : Setting | Action):
        '''Enter on a row.'''
        if isinstance(item, Setting):
            self.on_message(item.step(1))
        elif item is self.BACK:
            self.back()
        elif item.run:
            self.on_message(item.run())
        elif item.children:
            self._came_from.append(self.selected)
            self.path.append(item)
            self.selected = 0

    def handle_key(self, key : Key) -> bool:
        items = self.items
        if not items:
            return False
        self.selected %= len(items)
        item = items[self.selected]
        name = key.name
        extra = next((e for e in item.extra if name in e.keys), None) if isinstance(item, Action) else None
        if name == 'up':
            self.selected = (self.selected - 1) % len(items)
        elif name == 'down':
            self.selected = (self.selected + 1) % len(items)
        elif name in ('left', 'right') and isinstance(item, Setting):
            self.on_message(item.step(-1 if name == 'left' else 1))
        elif name in ('enter', 'space'):
            self.select(item)
        elif extra is not None:
            self.on_message(extra.run())
        elif name == 'escape' and self.back():
            pass
        elif name in ('tab', 'escape'):
            self.on_close()
        else:
            return False
        self.invalidate()
        return True

    # Drawing

    def draw(self, region : Region):
        items = self.items
        width = max((len(i.label) for i in items), default=0)
        focused = self.screen is not None and self.screen.focused is self
        for y, item in enumerate(items):
            here = focused and y == self.selected % len(items)
            active = isinstance(item, Action) and item.is_active()
            label = f'{"›" if here else " "} {item.label:<{width}} {"•" if active else " "} '
            style = fg(CYAN, bold=True) if active else BOLD if here else DIM
            line = [(label, style)]
            if isinstance(item, Setting):
                current = item.get()
                for option in item.choices():
                    if option == current:
                        line.append((f' {option} ', REVERSE if here else fg(CYAN, bold=True)))
                    else:
                        line.append((f' {option} ', PLAIN if here else DIM))
                    line.append(' ')
            elif detail := item.get_detail():
                line += [(t, s.over(DIM if not here else PLAIN)) for t, s in spans(detail)]
            region.put(0, y, line)
        region.put_lines(0, len(items), self.hint_lines(), DIM)


class CommandInput(Input):
    '''An Input that's also the app's command line. Text starting with / is
    a command (see Commands: the menu's rows, by name): while you type it the
    status shows what it could be or go on to, and Enter runs it.
    Anything else goes to on_text(text) as it changes and on_enter(text) on
    Enter (return False from on_enter to keep the text). While the line is
    empty, keys go to on_key(key) first (single-key controls); if it returns
    True the line doesn't get them.'''

    def __init__(self, on_text : Callable[[str], None] | None = None,
                 on_enter : Callable[[str], bool | None] | None = None,
                 on_key : Callable[[Key], bool] | None = None, **kwargs):
        super().__init__(on_change=self._changed, on_submit=self._submitted, **kwargs)
        self.on_text = on_text
        self.on_enter = on_enter
        self.on_key = on_key

    def handle_key(self, key : Key) -> bool:
        if not self.text and self.on_key and self.on_key(key):
            self.invalidate()
            return True
        return super().handle_key(key)

    def _changed(self, text : str):
        app = self.app
        if text.startswith('/'):
            if app:
                app.notify(app.commands.hint(text))
        elif self.on_text:
            self.on_text(text)

    def _submitted(self, text : str) -> bool | None:
        if text.startswith('/'):
            if self.app:
                self.app.run_command(text)
            return None
        return self.on_enter(text) if self.on_enter else None


class Rule(Widget):
    '''A line across its area (or down it, with vertical=True).'''

    def __init__(self, vertical : bool = False, style : Style = DIM, **kwargs):
        kwargs.setdefault('width' if vertical else 'height', 1)
        super().__init__(**kwargs)
        self.vertical = vertical
        self.style = style

    def draw(self, region : Region):
        if self.vertical:
            for y in range(region.height):
                region.put(0, y, '│', self.style)
        else:
            region.put(0, 0, '─' * region.width, self.style)
