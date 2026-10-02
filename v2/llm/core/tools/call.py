from dataclasses import dataclass
from typing import Any, List
from .tool import Tool
import json

@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str | None = None

@dataclass
class ToolResult:
    name: str
    result: Any
    error: str | None = None
    id: str | None = None

    def to_dict(self, style: str = "openai") -> dict:
        content = self.error if self.error is not None else self.result
        if not isinstance(content, str):
            content = json.dumps(content)

        if style == "openai":
            return {
                "role": "tool",
                "tool_call_id": self.id,
                "name": self.name,
                "content": content,
            }
        elif style == "anthropic":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": self.id,
                    "content": content,
                    "is_error": self.error is not None,
                }],
            }