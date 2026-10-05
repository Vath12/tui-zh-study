from dataclasses import dataclass, field
from typing import Callable, Iterator

# What a command or setting change says back, for the status line (None: nothing).
Message = str | None


@dataclass
class Command:
    '''A /command that isn't in the menu (like /help): run gets everything
    after the name, as one string.'''
    name : str
    run : Callable[[str], Message]
    help : str = ''


@dataclass
class Setting:
    '''A value picked from a list of options, like the rendering mode: a menu
    row you change with left/right, and "/name option".

    get returns the current option; set changes it (it's only given one of
    `options`) and can return a message. options can be a function, for lists
    that change.'''
    name : str
    label : str
    options : list[str] | Callable[[], list[str]]
    get : Callable[[], str]
    set : Callable[[str], Message]
    help : str = ''

    def choices(self) -> list[str]:
        return self.options() if callable(self.options) else list(self.options)

    def choose(self, option : str) -> Message:
        choices = self.choices()
        match = next((c for c in choices if c.casefold() == option.strip().casefold()), None)
        if match is None:
            return f'options: {" | ".join(choices)}  (now {self.get()})'
        return self.set(match) or f'{self.label.lower()}: {match}'

    def step(self, by : int) -> Message:
        '''Move to the next (by=1) or previous (by=-1) option, wrapping round.'''
        choices = self.choices()
        if not choices:
            return None
        i = choices.index(self.get()) if self.get() in choices else 0
        return self.choose(choices[(i + by) % len(choices)])

    def items(self) -> list:
        return []


@dataclass
class Action:
    '''A menu row you press Enter on. Every row is also a command, named by
    the path of names to it: "/quit", "/session new", "/session Notes rename".

      run       what Enter (or the bare command) does
      arg, run_arg
                if the command can take an argument: what it's called (shown
                in hints, e.g. 'NAME') and what runs with it. Typically run
                asks for it and run_arg is the answer, so "/session new Drill"
                skips the question.
      children  a page of rows under this one (a function, so it can change).
                With no `run`, Enter opens the page in the menu.
      extra     other things to do with this row, each an Action with `keys`
                that run it while the row is selected (rename on 'r', ...)
                and a name for its command ("/session Notes rename").
      keys      (for extra rows) the keys that run it
      active    the menu marks the row while this returns True
      detail    rich text (or a function giving it) shown right of the label
      hints     key hints shown under the rows while this row's page is open
      last      rows that go at the bottom of the menu (Quit)'''
    name : str
    label : str
    run : Callable[[], Message] | None = None
    help : str = ''
    arg : str | None = None
    run_arg : Callable[[str], Message] | None = None
    children : Callable[[], list['Item']] | None = None
    extra : list['Action'] = field(default_factory=list)
    keys : tuple[str, ...] = ()
    active : Callable[[], bool] | None = None
    detail : object = None
    hints : object = None
    last : bool = False

    def is_active(self) -> bool:
        return bool(self.active and self.active())

    def get_detail(self):
        return self.detail() if callable(self.detail) else self.detail

    def items(self) -> list['Item']:
        '''What a command can go on to after this row: its page, then its extras.'''
        return [*(self.children() if self.children else []), *self.extra]


Item = Setting | Action


@dataclass
class Settings:
    '''The menu's top level, in order (actions marked `last` go at the end).'''
    items : list[Item] = field(default_factory=list)

    def add(self, item : Item) -> Item:
        self.remove(item.name)
        self.items.append(item)
        return item

    def remove(self, name : str):
        self.items = [i for i in self.items if i.name != name]

    def menu_items(self) -> list[Item]:
        last = [i for i in self.items if isinstance(i, Action) and i.last]
        return [i for i in self.items if i not in last] + last

    def get(self, name : str) -> Item | None:
        return next((i for i in self.items if i.name == name), None)


def _match(items : list[Item], text : str) -> Item | None:
    '''The item whose name `text` starts with (as whole words, ignoring
    case), the longest if several do: names can have spaces ("Tones practice").'''
    folded = text.casefold()
    best = None
    for item in items:
        name = item.name.casefold()
        if folded.startswith(name) and (len(folded) == len(name) or folded[len(name)] == ' '):
            if best is None or len(name) > len(best.name):
                best = item
    return best


class Commands:
    '''The /commands: everything in the menu, by its path of names (see
    Action), plus a few that aren't menu rows (add()).

    `on_open(path)` is called for a command naming a page with nothing to run
    (like "/session"), so whatever shows the menu can open it there; path is
    the Actions from the top down.'''

    def __init__(self, menu : Callable[[], list[Item]] = lambda: []):
        self.menu = menu
        self.on_open : Callable[[list[Action]], Message] | None = None
        self._commands : dict[str, Command] = {}

    def add(self, name : str, run : Callable[[str], Message], help : str = '') -> Command:
        command = self._commands[name] = Command(name, run, help)
        return command

    def remove(self, name : str):
        self._commands.pop(name, None)

    def __iter__(self) -> Iterator[Command]:
        return iter(self._commands.values())

    def resolve(self, line : str) -> tuple[list[Item], str]:
        '''Follow a command through the menu: (the items it names, from the
        top, and the text left over).'''
        path, rest = [], line.removeprefix('/').strip()
        items = self.menu()
        while rest and (item := _match(items, rest)):
            path.append(item)
            rest = rest[len(item.name):].strip()
            items = item.items()
        return path, rest

    def run(self, line : str) -> Message:
        '''Run a command line (with or without the leading /).'''
        line = line.removeprefix('/').strip()
        name, _, rest = line.partition(' ')
        if name in self._commands:
            return self._commands[name].run(rest.strip())
        path, rest = self.resolve(line)
        if not path:
            return f'unknown command /{name}, try /help'
        item, where = path[-1], '/' + ' '.join(i.name for i in path)
        if isinstance(item, Setting):
            return item.choose(rest)
        if rest:
            if item.run_arg:
                return item.run_arg(rest)
            names = ', '.join(i.name for i in item.items())
            return f'{where} has no {rest.split()[0]}' + (f' (it has: {names})' if names else '')
        if item.run:
            return item.run()
        if item.children and self.on_open:
            return self.on_open(path)
        names = ', '.join(i.name for i in item.items())
        return f'{where}: {names}' if names else None

    def hint(self, line : str) -> str:
        '''What a partly typed command could go on to, for the status line.'''
        line = line.removeprefix('/')
        path, rest = self.resolve(line)
        last = path[-1] if path else None
        where = '/' + ' '.join(i.name for i in path)
        if isinstance(last, Setting):
            return f'{where} {" | ".join(last.choices())}  (now {last.get()})'
        items = last.items() if last is not None else [*self.menu(), *self._commands.values()]
        if last is not None and not rest and not line.endswith(' '):
            more = '   then: ' + ', '.join(i.name for i in items) if items else ''
            arg = f' [{last.arg}]' if last.arg else ''
            return f'{where}{arg}: {last.help or last.label}{more}'
        options = [i.name for i in items if i.name.casefold().startswith(rest.casefold())]
        if options:
            return '  '.join(options)
        if last is not None and last.arg:
            return f'{where} {last.arg}'
        return f'unknown command /{line.strip()}'

    def help(self) -> str:
        top = [*self.menu(), *self._commands.values()]
        return '   '.join(f'/{i.name}' + (f': {i.help}' if i.help else '') for i in top)
