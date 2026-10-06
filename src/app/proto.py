'''A testing ground for the TUI: an output area and a command line at the
bottom. Tab pops a menu out on the left:

  Identify, Writing, Translation, Pinyin, Mixture
             the study modes (see modes/; the current one is marked).
             Translation and Mixture aren't ready yet: they say so and just
             log what you type.
  Session    your sessions (see sessions.Sessions, saved in .data/): each one
             keeps the program's state (the mode, the options, what's in the
             output), so switching session switches all of that. None is a
             session that isn't saved. Enter switches, r renames, Delete
             deletes (you type the name to confirm), + New session makes one.
  Vocabulary your wordlists (see wordlists.Wordlists, saved in .data/): Enter
             turns one on or off, Delete removes it, + Add by path adds one,
             and so does dragging .txt files onto the terminal while it's
             open. Files are checked when added and whenever they're shown.
  Options    the stroke drawing options, in the main window, with a preview
  Quit

Enter picks a row and leaves the menu out; Esc goes back a page, Tab puts
the menu away, and so does typing anything else, which goes to the command
line. Every row is also a command, by its names: /writing, /session new,
/session Notes rename, /vocabulary add PATH, /options speed 1s (see Commands).

    uv run python -m src.app.proto
'''
import shlex
from datetime import datetime
from pathlib import Path
from typing import Callable

from .modes import MODES, StudyContext, StudyMode
from .sessions import Session, SessionError, Sessions
from .strokes import CharacterStrip, StrokeLook
from src.tui import (BOLD, DIM, FILL, RED, YELLOW, Action, App, Column, CommandInput, Input, Key, Layers, Row, Rule,
                  Screen, Setting, SettingsPanel, Spacer, Text, fg)
from .wordlists import InvalidWordlist, Wordlist, Wordlists

MENU_WIDTH = 16
LOG_LINES = 200      # output lines kept in the session
PREVIEW = [('你', ['nǐ']), ('好', ['hǎo'])]   # shown under the options


def when(stamp : str) -> str:
    '''An ISO timestamp, short: "14:03" today, "Oct 2" otherwise.'''
    t = datetime.fromisoformat(stamp)
    return t.strftime('%H:%M') if t.date() == datetime.now().date() else f'{t:%b} {t.day}'


def unescape(path : str) -> str:
    '''A path as typed or pasted: shell-style escapes and quotes undone
    (/a/My\\ File.txt, '/a/My File.txt'), file:// dropped.'''
    path = path.strip().removeprefix('file://')
    try:
        words = shlex.split(path)
        return words[0] if len(words) == 1 else path
    except ValueError:
        return path


def refusals_said(fn : Callable[..., str]) -> Callable[..., str]:
    '''fn, but a SessionError or InvalidWordlist (a name that's taken, a
    confirmation that doesn't match, ...) comes back as its message.'''
    def run(*args):
        try:
            return fn(*args)
        except (SessionError, InvalidWordlist) as e:
            return str(e)
    return run


class ProtoScreen(Screen):

    def __init__(self, wordlists : Wordlists | None = None, sessions : Sessions | None = None):
        self.wordlists = wordlists if wordlists is not None else Wordlists()
        self.sessions = sessions if sessions is not None else Sessions()
        self.look = StrokeLook()
        self.options = [self.remembered(s) for s in self.look.settings()]
        ctx = StudyContext(session=lambda: self.sessions.current, wordlists=self.wordlists, look=self.look,
                           notify=self.notify)
        self.modes : dict[str, StudyMode] = {cls.name: cls(ctx) for cls in MODES}
        self.load_session()

        self.menu = SettingsPanel(None, hints=None, on_close=self.focus_input)
        self.input = CommandInput(on_enter=self.entered, on_key=lambda key: self.study.handle_key(key), hint='Tab: menu',
                                  visible=lambda: self.focused is not self.asker)
        # For questions (a new name, a confirmation): see ask().
        self.asker = Input(prompt='? ', visible=lambda: self.focused is self.asker,
                           bindings={'escape': self.cancel_ask, 'tab': self.cancel_ask})
        self._answer : Callable[[str], str] | None = None
        self._asked_from = None
        self._asking_wordlist = False      # the question is a wordlist path (so a dropped file answers it)
        self.options_panel = SettingsPanel(lambda: self.options, hints='←→ change   Esc back',
                                           on_close=lambda: self.focus(self.menu))
        self.preview = CharacterStrip(self.look, max_size=40)
        self.preview.show(PREVIEW)
        menu_open = lambda: self.focused in (self.menu, self.asker, self.options_panel)   # out while you use it
        options_open = lambda: self.focused is self.options_panel

        menu = Column(
            Text(lambda: f' {self.menu.title or "Menu"}', BOLD, height=1),
            Rule(),
            self.menu,
            Spacer(height=0, width=MENU_WIDTH),    # at least this wide
            visible=menu_open,
        )
        title = Text(lambda: [(f'{self.study.label} mode', BOLD),
                              (f'   {self.session.name}{"" if self.session.saved else " (not saved)"}', DIM)], height=1)
        log = Text(lambda: '\n'.join(self.log), wrap=True)
        study = Layers(*(Column(m.widget, *([] if m.ready else [Spacer(height=1), log]), height=FILL,
                                visible=lambda m=m: m is self.study) for m in self.modes.values()), height=FILL)
        output = Column(title, Spacer(height=1), study, visible=lambda: not options_open())
        options = Column(Text('Options', BOLD, height=1), Rule(), self.options_panel, Spacer(height=1), self.preview,
                         visible=options_open)
        status = Text(lambda: self.app.message, DIM, wrap=False, height=1, priority=1)
        super().__init__(Column(
            Row(menu, Rule(vertical=True, visible=menu_open), Layers(output, options, width=FILL), height=FILL, gap=1),
            Rule(),
            status,
            self.input,
            self.asker,
        ), bindings={'tab': self.open_menu})

        self.settings = [
            *(Action(name, m.label, lambda name=name: self.set_mode(name),
                     f'study {name}' + ('' if m.ready else ' (not ready yet)'), active=lambda name=name: self.mode == name)
              for name, m in self.modes.items()),
            Action('session', 'Session', help='your sessions', children=self.session_rows,
                   detail=lambda: self.session.name, hints='Enter  switch to\nr      rename\nDel    delete\nEsc    back'),
            Action('vocabulary', 'Vocabulary', help='your wordlists', children=self.wordlist_rows,
                   detail=lambda: f'{sum(w.enabled for w in self.wordlists.lists)} on',
                   hints='Enter  on / off\nDel    remove\nEsc    back\ndrop .txt files\nhere to add them'),
            Action('options', 'Options', self.open_options, 'stroke drawing options', children=lambda: self.options),
        ]

    def on_enter(self):
        self.menu.settings = self.app.settings
        self.menu.on_message = self.app.notify
        self.options_panel.on_message = self.app.notify
        self.app.commands.on_open = self.open_page
        self.focus_input()

    def on_exit(self):
        self.app.commands.on_open = None

    def notify(self, message):
        '''A message for the status line; ignored while the screen is still
        being built (the session's mode starts before there's an app).'''
        app = getattr(self, '_app', None)
        if app is not None:
            app.notify(message)

    # Session state

    @property
    def session(self) -> Session:
        return self.sessions.current

    def load_session(self):
        '''Take the program's state from the current session.'''
        s = self.session
        self.mode = s.get('mode') if s.get('mode') in self.modes else 'identify'
        self.log : list[str] = list(s.get('log', []))
        saved = s.get('options', {})
        for setting, default in zip(self.look.settings(), StrokeLook().settings()):
            value = saved.get(setting.name)
            setting.set(value if value in setting.choices() else default.get())
        self.study.start()

    @property
    def study(self) -> StudyMode:
        return self.modes[self.mode]

    def remembered(self, setting : Setting) -> Setting:
        '''The setting, saving its value in the session when it changes.'''
        def set(value):
            message = setting.set(value)
            self.session.set('options', {o.name: o.get() for o in self.options})
            return message
        return Setting(setting.name, setting.label, setting.options, setting.get, set, setting.help)

    def add_log(self, *lines : str):
        self.log = (self.log + list(lines))[-LOG_LINES:]
        self.session.set('log', self.log)

    def set_mode(self, mode : str) -> str:
        if mode == self.mode:
            return f'already in {self.study.label.lower()} mode'
        self.mode = mode
        self.session.set('mode', mode)
        self.study.start()
        return f'mode: {self.study.label.lower()}' + ('' if self.study.ready else ' (not ready yet)')

    # Menu

    def open_menu(self):
        self.focus(self.menu)

    def open_page(self, path : list[Action]) -> None:
        '''A command naming a page (/session): show it in the menu.'''
        self.menu.open(path)
        self.focus(self.menu)

    def focus_input(self):
        '''Back to the command line, which also puts the menu away (at its top page).'''
        self.menu.open()
        self.focus(self.input)

    def open_options(self) -> str:
        self.focus(self.options_panel)
        return 'options: ←→ to change, Esc to go back'

    # Questions on the bottom line

    def ask(self, prompt : str, answer : Callable[[str], str], initial : str = ''):
        '''Ask something on the bottom line. answer(text) runs on Enter and
        returns a message; if it raises SessionError or InvalidWordlist, the
        message is shown and the question stays up. Esc or Tab cancels.
        Either way you go back to where you asked from (the menu or the
        command line).'''
        self._answer = answer
        self._asked_from = self.focused
        self.asker.prompt = [(prompt, fg(YELLOW, bold=True)), ' ']
        self.asker.on_submit = self._answered
        self.asker.set_text(initial)
        self.focus(self.asker)

    def _answered(self, text : str):
        try:
            message = self._answer(text)
        except (SessionError, InvalidWordlist) as e:
            self.app.notify(str(e))
            return False          # keep the question (and the text) up
        self._end_ask(message)
        return None

    def cancel_ask(self):
        self._end_ask('cancelled')

    def _end_ask(self, message):
        self._answer = None
        self._asking_wordlist = False
        self.app.notify(message)
        self.focus(self._asked_from if self._asked_from is not None else self.menu)

    # Sessions

    def session_rows(self) -> list[Action]:
        return [*map(self.session_row, [self.sessions.none, *self.sessions.list()]),
                Action('new', '+ New session', self.new_session, 'make a session (r renames it)', arg='NAME',
                       run_arg=self.new_session)]

    def session_row(self, s : Session) -> Action:
        switch = lambda: self.switch_session(s)
        current = lambda: s is self.session
        if not s.saved:
            cant = lambda what: lambda *_: f'{s.name} can\'t be {what}: it\'s the session that isn\'t saved'
            return Action(s.name, s.name, switch, 'nothing is saved while you\'re in it', active=current,
                          detail='not saved', extra=[
                              Action('rename', 'Rename', cant('renamed'), keys=('r',), run_arg=cant('renamed')),
                              Action('delete', 'Delete', cant('deleted'), keys=('delete', 'backspace'),
                                     run_arg=cant('deleted'))])
        return Action(s.name, s.name, switch, f'switch to {s.name}', active=current, detail=lambda: when(s.updated),
                      extra=[
                          Action('rename', 'Rename', lambda: self.ask_rename(s), 'rename it', keys=('r',),
                                 arg='NAME', run_arg=refusals_said(lambda name: self.rename_session(s, name))),
                          Action('delete', 'Delete', lambda: self.ask_delete(s), 'delete it (type its name to confirm)',
                                 keys=('delete', 'backspace'), arg='NAME',
                                 run_arg=refusals_said(lambda typed: self.delete_session(s, typed))),
                      ])

    def switch_session(self, s : Session) -> str:
        if s is self.session:
            return f'already in {s.name}'
        self.sessions.switch(s)
        self.load_session()
        return f'switched to {s.name}' + ('' if s.saved else ' (nothing is saved while you\'re in it)')

    def new_session(self, name : str | None = None) -> str:
        try:
            s = self.sessions.new(name)
        except SessionError as e:
            return str(e)
        self.load_session()
        self.menu.selected = len(self.sessions.sessions)    # its row: after None and the older ones
        return f'made {s.name}; it\'s the current session (r renames it)'

    def rename_session(self, s : Session, name : str) -> str:
        old = s.name
        self.sessions.rename(s, name)   # raises SessionError if the name can't be used
        return f'renamed {old} to {s.name}'

    def ask_rename(self, s : Session) -> None:
        self.ask(f'New name for {s.name}:', lambda name: self.rename_session(s, name), initial=s.name)

    def ask_delete(self, s : Session) -> None:
        self.ask(f'Type "{s.name}" to delete it (Esc cancels):', lambda typed: self.delete_session(s, typed))

    def delete_session(self, s : Session, confirm : str) -> str:
        was_current = s is self.session
        self.sessions.delete(s, confirm)   # raises SessionError unless confirm is the name
        if not was_current:
            return f'deleted {s.name}'
        self.load_session()
        now = self.session
        return f'deleted {s.name}; now in {now.name}' + ('' if now.saved else ' (not saved)')

    # Wordlists

    def wordlist_rows(self) -> list[Action]:
        return [*map(self.wordlist_row, self.wordlists.lists),
                Action('add', '+ Add by path', self.ask_wordlist, 'add a .txt wordlist', arg='PATH',
                       run_arg=lambda path: self.add_wordlists([path]))]

    def wordlist_row(self, w : Wordlist) -> Action:
        def detail():
            words, error = w.check()
            if words is not None:
                return f'{len(words)} words'
            return ('missing' if not w.path.exists() else 'invalid', fg(RED))

        def toggle():
            words, error = w.check()
            return error if error else self.wordlists.toggle(w)

        same_name = sum(other.name == w.name for other in self.wordlists.lists) > 1
        label = f'{w.path.parent.name}/{w.name}' if same_name else w.name
        return Action(label, label, toggle, f'turn {label} on or off', active=lambda: w.enabled, detail=detail,
                      extra=[Action('remove', 'Remove', lambda: self.wordlists.remove(w.path), 'remove it',
                                    keys=('delete', 'backspace'))])

    def ask_wordlist(self) -> None:
        self._asking_wordlist = True
        self.ask('Path of a .txt wordlist (or drop the file here):', lambda path: self.add_wordlists([path]))

    def add_wordlists(self, paths : list[str | Path]) -> str:
        messages = []
        for path in paths:
            try:
                messages.append(self.wordlists.add(unescape(str(path))))
            except InvalidWordlist as e:
                messages.append(str(e))
        return ';  '.join(messages)

    def handle_drop(self, paths : list[Path]) -> bool:
        on_vocab_page = self.focused is self.menu and self.menu.page is not None and self.menu.page.name == 'vocabulary'
        if self.focused is self.asker and self._asking_wordlist:
            self._end_ask(self.add_wordlists(paths))
        elif on_vocab_page:
            self.app.notify(self.add_wordlists(paths))
        else:
            self.on_files([p.name for p in paths], paths)
        return True

    # Other input

    def handle_key(self, key : Key) -> bool:
        # Only reached for keys nothing else used: with the menu out, put it
        # away and give the key to the command line.
        if self.focused is self.menu:
            self.focus_input()
            return self.input.handle_key(key)
        return False

    def entered(self, text : str):
        '''Enter on the command line: an answer, if the mode takes it, else just logged.'''
        if not self.study.entered(text) and text.strip():
            self.add_log(f'> {text}')

    def on_files(self, names : list[str], paths : list[Path]):
        '''Files were dragged onto the terminal (outside the vocabulary menu).'''
        self.add_log(*(f'dropped: {name}  ({path.parent})' for name, path in zip(names, paths)))
        self.app.notify(f'{len(names)} file{"s" if len(names) > 1 else ""} dropped')


def main():
    App().main(ProtoScreen())


if __name__ == '__main__':
    main()
