from typing import List
from .tool import Tool
from .call import ToolCall, ToolResult

def call_tool(tools : List[Tool], call : ToolCall):
    func = None
    for t in tools:
        if t.name == call.name:
            func = t.py_callable

    if func is None:
        return ToolResult(
            call.name,
            None,
            f"InvalidToolError: \"{t.name}\" is not a provided tool",
            call.id
        )

    try:
        result = func(**call.arguments)
        return ToolResult(
            call.name,
            result,
            None,
            call.id
        )
    except Exception as e:
        return ToolResult(
            call.name,
            None,
            str(e),
            call.id
        )