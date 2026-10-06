import asyncio
import signal
import sys
import traceback
from pathlib import Path
from typing import Awaitable, Callable

from blessed import Terminal

from .cells import Buffer, Rich
from .commands import Action, Commands, Message, Settings
from .keys import Key, dropped_paths, from_blessed
from .render import Renderer
from .widget import Rect, Screen, Widget

ESC_DELAY = 0.05   # seconds to wait after Escape for the rest of a key sequence


class App:
    '''A full-screen terminal app: a stack of Screens, drawn with a Renderer.

    It runs on asyncio. Keys are read as they arrive (no polling) and go to
    the top screen's focused widget, then up through its parents. The screen
    is redrawn after every key, after invalidate(), and `fps` times a second
    while anything on screen is animating(). Background work goes through
    spawn(), which redraws when it finishes and reports errors in the status.

    `global_bindings` are checked before anything else (Ctrl-C and Ctrl-D quit).
    `commands` and `settings` are the /commands and the settings menu.

    Files dragged onto the terminal (which pastes their paths) go to
    handle_drop(paths) on the focused widget and its parents, then to
    `on_drop(paths)` if it's set; if nothing takes them they're an ordinary paste.'''

    def __init__(self, fps : int = 30):
        self.fps = fps
        self.term : Terminal | None = None
        self.screens : list[Screen] = []
        self.settings = Settings()
        self.commands = Commands(menu=self.settings.menu_items)
        self.message : Rich = ''
        self.errors : list[str] = []   # tracebacks of errors caught in handlers and tasks
        self.global_bindings : dict[str, Callable] = {'ctrl+c': self.quit, 'ctrl+d': self.quit}
        self.on_drop : Callable[[list[Path]], object] | None = None
        self.running = False
        self._wake : asyncio.Event | None = None
        self._tasks : set[asyncio.Task] = set()

        self.commands.add('help', lambda rest: self.commands.help(), 'list commands')
        self.commands.add('error', lambda rest: self.errors[-1].strip().splitlines()[-1] if self.errors else 'no errors',
                          'the last error')
        self.settings.add(Action('quit', 'Quit', self.quit, 'exit', last=True))

    # Screens

    @property
    def screen(self) -> Screen | None:
        return self.screens[-1] if self.screens else None

    def push(self, screen : Screen) -> Screen:
        screen._app = self
        self.screens.append(screen)
        for item in screen.settings:
            self.settings.add(item)
        screen.on_enter()
        if screen.focused is None:
            screen.focus_first()
        self.invalidate()
        return screen

    def pop(self, screen : Screen | None = None, quit_if_empty : bool = True) -> Screen | None:
        '''Take a screen (the top one by default) off the stack. With none left, the app quits.'''
        screen = screen or self.screen
        if screen not in self.screens:
            return None
        top = screen is self.screen
        self.screens.remove(screen)
        for item in screen.settings:
            self.settings.remove(item.name)
        screen.on_exit()
        screen._app = None
        if not self.screens:
            if quit_if_empty:
                self.quit()
        elif top:
            self.screen.on_resume()
        self.invalidate()
        return screen

    def replace(self, screen : Screen) -> Screen:
        '''Swap the top screen for another.'''
        if self.screen:
            self.pop(quit_if_empty=False)
        return self.push(screen)

    @property
    def focused(self) -> Widget | None:
        return self.screen.focused if self.screen else None

    def focus(self, widget : Widget | None):
        if self.screen:
            self.screen.focus(widget)

    # Messages and commands

    def notify(self, message : Message | Rich):
        '''Show a message in the status line (screens decide where that is).'''
        self.message = message or ''
        self.invalidate()

    def run_command(self, line : str) -> Message:
        message = self.commands.run(line)
        self.notify(message)
        return message

    # Background work

    def spawn(self, work : Awaitable, on_done : Callable[[object], None] | None = None) -> asyncio.Task:
        '''Run a coroutine alongside the UI. on_done(result) runs when it
        finishes; if it raises, the error goes to the status line instead.'''
        async def run():
            try:
                result = await work
                if on_done:
                    on_done(result)
                return result
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._error(e)
            finally:
                self.invalidate()
        task = asyncio.get_running_loop().create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _error(self, e : Exception):
        self.errors.append(traceback.format_exc())
        self.notify(f'error: {e!r}  (/error for more)')

    # Running

    def invalidate(self):
        '''Ask for a redraw. Safe to call from anything on the event loop.'''
        if self._wake is not None:
            self._wake.set()

    def quit(self):
        self.running = False
        self.invalidate()

    def dispatch(self, key : Key) -> bool:
        '''Send a key through the app: global bindings, then the focused
        widget and its parents (each one's handle_key, then its bindings).'''
        try:
            if key.name == 'paste' and (paths := dropped_paths(key.text)) and self.drop(paths):
                return True
            if key.name in self.global_bindings:
                self.global_bindings[key.name]()
                return True
            screen = self.screen
            if screen is None:
                return False
            widget = screen.focused if screen.focused is not None else screen
            while widget is not None:
                if widget.handle_key(key):
                    return True
                if key.name in widget.bindings:
                    widget.bindings[key.name]()
                    return True
                widget = widget.parent
            return False
        except Exception as e:
            self._error(e)
            return True
        finally:
            self.invalidate()

    def drop(self, paths : list[Path]) -> bool:
        '''Hand dropped files to the focused widget and up, then on_drop. Returns whether anything took them.'''
        screen = self.screen
        widget = screen.focused if screen and screen.focused is not None else screen
        while widget is not None:
            if widget.handle_drop(paths):
                return True
            widget = widget.parent
        if self.on_drop is not None:
            self.on_drop(paths)
            return True
        return False

    def visible_screens(self) -> list[Screen]:
        '''The screens that show: the top one, and those under it down to the first opaque one.'''
        shown = []
        for screen in reversed(self.screens):
            shown.append(screen)
            if screen.opaque:
                break
        return shown[::-1]

    def animating(self) -> bool:
        return any(w.animating() for screen in self.visible_screens() for w in screen.walk())

    def render(self, width : int, height : int) -> tuple[Buffer, tuple[int, int] | None]:
        '''Draw the screens into a new Buffer: (buffer, cursor position or None).
        Doesn't need a terminal, so it also works for tests.'''
        buffer = Buffer(width, height)
        screens = self.visible_screens()
        for screen in screens:
            for w in screen.walk():
                w.rect = Rect(0, 0, 0, 0)   # so anything not drawn this frame has no area
        for screen in screens:
            screen.render(buffer.region())
        cursor = None
        focused = self.focused
        if focused is not None and focused.rect.width and focused.rect.height \
                and (pos := focused.cursor()) is not None:
            cursor = (focused.rect.x + pos[0], focused.rect.y + pos[1])
        return buffer, cursor

    def _draw(self, renderer : Renderer):
        width, height = self.term.width, self.term.height
        try:
            buffer, cursor = self.render(width, height)
        except Exception as e:
            self._error(e)
            buffer, cursor = Buffer(width, height), None
            buffer.region().put(0, 0, f'error while drawing: {e!r}  (Ctrl-C quits)')
        renderer.draw(buffer, cursor)

    def _read_keys(self):
        # Take everything that's been typed, without waiting for more.
        while self.running and (ks := self.term.inkey(timeout=0, esc_delay=ESC_DELAY)):
            self.dispatch(from_blessed(ks))

    async def run(self, screen : Screen | None = None):
        '''Run until quit() (or Ctrl-C), taking over the terminal.'''
        if screen is not None:
            self.push(screen)
        self.term = term = Terminal()
        if term._keyboard_fd is None:
            raise SystemExit('needs an interactive terminal')
        loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        renderer = Renderer(sys.stdout, 'truecolor' if term.number_of_colors >= 1 << 24 else '256')

        def resized():
            renderer.reset()
            self.invalidate()

        self.running = True
        with term.fullscreen(), term.cbreak(), _bracketed_paste(term):
            loop.add_reader(term._keyboard_fd, self._read_keys)
            loop.add_signal_handler(signal.SIGWINCH, resized)
            loop.add_signal_handler(signal.SIGINT, self.quit)
            try:
                while self.running:
                    self._wake.clear()
                    self._draw(renderer)
                    timeout = 1 / self.fps if self.animating() else None
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout)
                    except TimeoutError:
                        pass
            finally:
                loop.remove_reader(term._keyboard_fd)
                loop.remove_signal_handler(signal.SIGWINCH)
                loop.remove_signal_handler(signal.SIGINT)
                for task in list(self._tasks):
                    task.cancel()
                sys.stdout.write('\x1b[0m\x1b[?25h')
                sys.stdout.flush()

    def main(self, screen : Screen | None = None):
        '''Run from synchronous code.'''
        asyncio.run(self.run(screen))


class _bracketed_paste:
    '''Turn on bracketed paste (pastes, including dragged files, arrive as one
    event). blessed's own term.bracketed_paste() asks the terminal first and
    gives up if it doesn't answer, which some that support it don't, so set
    it directly.'''

    def __init__(self, term : Terminal):
        self.term = term

    def __enter__(self):
        set_enabled = getattr(self.term, '_dec_mode_set_enabled', None)
        if set_enabled:
            set_enabled(2004)

    def __exit__(self, *exc):
        set_disabled = getattr(self.term, '_dec_mode_set_disabled', None)
        if set_disabled:
            set_disabled(2004)
