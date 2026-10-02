from abc import ABC, abstractmethod
from typing import Optional, Tuple
from .call import ToolCall
import re
from enum import Enum


class BufferState(int, Enum):
    NORMAL = 0
    STARTED = 1
    ACCUMULATING = 2
    ENDED = 3

class _Buffer:
    def __init__(self, start: str, end: str):
        self.start = start
        self.end = end
        self.reset()

    def reset(self):
        self.state = BufferState.NORMAL
        self.accumulating = False
        self.buffer = ""

    def feed(self, token: str) -> Optional[str]:
        self.buffer += token

        if not self.accumulating:
            idx = self.buffer.find(self.start)

            if idx == -1:
                lookback = len(self.start) - 1
                self.buffer = self.buffer[-lookback:] if lookback > 0 else ""
                self.state = BufferState.NORMAL
                return None

            self.accumulating = True
            self.buffer = self.buffer[idx + len(self.start):]

            # Don't return the payload yet, but tell the caller
            # that this input crossed the start delimiter.
            self.state = BufferState.STARTED
        else:
            self.state = BufferState.ACCUMULATING

        idx = self.buffer.find(self.end)

        if idx == -1:
            return None

        payload = self.buffer[:idx]
        self.reset()
        
        self.state = BufferState.ENDED
        return payload


class ModelParser(ABC):
    TOOL_START: str
    TOOL_END: str
    THINK_START: Optional[str] = None
    THINK_END: Optional[str] = None

    def __init__(self):
        self.tool_buffer = _Buffer(self.TOOL_START, self.TOOL_END)
        self.think_buffer = _Buffer(self.THINK_START, self.THINK_END) if self.THINK_START else None

    def reset(self):
        self.tool_buffer.reset()
        if self.think_buffer:
            self.think_buffer.reset()

    def _think(self, token: str) -> str:
        """'' while inside a think region (tags included), else token unchanged."""
        if self.think_buffer is None:
            return token
        payload = self.think_buffer.feed(token)
        return "" if payload is not None or self.think_buffer.accumulating else token

    @abstractmethod
    def _tool(self, token: str) -> Optional[ToolCall]:
        raise NotImplementedError

    def __call__(self, token: str) -> Tuple[str, Optional[ToolCall]]:
        tool_call = self._tool(token)
        context_token = self._think(token)
        return context_token, tool_call


class QwenParser(ModelParser):
    TOOL_START = "<tool_call>"
    TOOL_END = "</tool_call>"
    THINK_START = "<think>"
    THINK_END = "</think>"

    FUNCTION_RE = re.compile(r"<function=(?P<name>[^>]+)>(?P<body>.*?)</function>", re.DOTALL)
    PARAM_RE = re.compile(r"<parameter=(?P<name>[^>]+)>(?P<value>.*?)</parameter>", re.DOTALL)

    def _tool(self, token: str) -> Optional[ToolCall]:
        payload = self.tool_buffer.feed(token)
        if payload is None:
            return None

        fn_match = self.FUNCTION_RE.search(payload)
        if fn_match is None:
            return None

        name = fn_match.group("name").strip()
        arguments = {
            m.group("name").strip(): m.group("value").strip()
            for m in self.PARAM_RE.finditer(fn_match.group("body"))
        }
        return ToolCall(name=name, arguments=arguments)


class GemmaParser(ModelParser):
    TOOL_START = "<start_function_call>"
    TOOL_END = "<end_function_call>"
    # payload format still needs validation against a real sample

    def _tool(self, token: str) -> Optional[ToolCall]:
        self.tool_buffer.feed(token)
        return None