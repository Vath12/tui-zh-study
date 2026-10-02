from dataclasses import dataclass, field
from typing import Callable, Iterator

# What a command or setting change says back, for the status line (None: nothing).
Message = str | None


@dataclass
class Command:
    '''"/name arg ...": run gets the arguments as a list of strings.'''
    name : str
    run : Callable[[list[str]], Message]
    help : str = ''


class Commands:
    '''The /commands, by name.'''

    def __init__(self):
        self._commands : dict[str, Command] = {}

    def add(self, name : str, run : Callable[[list[str]], Message], help : str = '') -> Command:
        command = self._commands[name] = Command(name, run, help)
        return command

    def remove(self, name : str):
        self._commands.pop(name, None)

    def __contains__(self, name : str) -> bool:
        return name in self._commands

    def __iter__(self) -> Iterator[Command]:
        return iter(self._commands.values())

    def matching(self, prefix : str) -> list[Command]:
        return [c for c in self if c.name.startswith(prefix)]

    def run(self, line : str) -> Message:
        '''Run "name arg ..." (with or without the leading /).'''
        name, *args = line.removeprefix('/').split() or ['']
        if name not in self._commands:
            return f'unknown command /{name}, try /help'
        return self._commands[name].run(args)

    def help(self) -> str:
        return '   '.join(f'/{c.name}: {c.help}' for c in self)


@dataclass
class Setting:
    '''A value picked from a list of options, like the rendering mode. It's a
    row in the settings menu and a command, "/name option".

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
        if option not in choices:
            return f'usage: /{self.name} {"|".join(choices)}  (now {self.get()})'
        return self.set(option) or f'{self.label.lower()}: {option}'

    def step(self, by : int) -> Message:
        '''Move to the next (by=1) or previous (by=-1) option, wrapping round.'''
        choices = self.choices()
        if not choices:
            return None
        i = choices.index(self.get()) if self.get() in choices else 0
        return self.choose(choices[(i + by) % len(choices)])

    def command(self, args : list[str]) -> Message:
        return self.choose(args[0] if len(args) == 1 else '')


@dataclass
class Action:
    '''Something to do, like quitting: a menu row you press Enter on, and "/name".'''
    name : str
    label : str
    run : Callable[[], Message]
    help : str = ''


@dataclass
class Settings:
    '''The settings and actions, in menu order, each also a command.'''
    commands : Commands
    items : list[Setting | Action] = field(default_factory=list)

    def add(self, item : Setting | Action) -> Setting | Action:
        self.remove(item.name)
        self.items.append(item)
        if isinstance(item, Setting):
            choices = '|'.join(item.choices()) if not callable(item.options) else 'option'
            self.commands.add(item.name, item.command, item.help or f'{item.label.lower()}: {choices}')
        else:
            self.commands.add(item.name, lambda args: item.run(), item.help or item.label.lower())
        return item

    def remove(self, name : str):
        if any(i.name == name for i in self.items):
            self.items = [i for i in self.items if i.name != name]
            self.commands.remove(name)

    def menu_items(self) -> list[Setting | Action]:
        '''Settings, then actions.'''
        return [i for i in self.items if isinstance(i, Setting)] + [i for i in self.items if isinstance(i, Action)]

    def get(self, name : str) -> Setting | Action | None:
        return next((i for i in self.items if i.name == name), None)
