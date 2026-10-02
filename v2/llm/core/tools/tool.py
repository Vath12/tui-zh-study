import inspect
from typing import (
    Annotated,
    Any,
    Callable,
    get_args,
    get_type_hints,
)
from dataclasses import dataclass
from typing import Any, Callable, get_origin
from pydantic import BaseModel, create_model, Field
from .util import clean_schema

@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    py_callable: Callable

    def to_dict(self) -> dict[str, Any]:
        parameters = clean_schema(
            self.args_model.model_json_schema()
        )

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    def call(self, arguments: dict[str, Any]) -> Any:
        # Validate/coerce the LLM's arguments
        args = self.args_model.model_validate(arguments)

        # Call the actual Python function
        return self.py_callable(**args.model_dump())

    def __call__(self, *args, **kwargs):
        return self.py_callable(*args, **kwargs)


def tool(func: Callable) -> Tool:
    description = inspect.getdoc(func)

    if not description:
        raise ValueError(
            f"{func.__name__} requires a docstring"
        )

    signature = inspect.signature(func)
    hints = get_type_hints(func, include_extras=True)

    fields = {}

    for name, parameter in signature.parameters.items():
        annotation = hints.get(name)

        if annotation is None:
            raise TypeError(
                f"Parameter '{name}' of {func.__name__} "
                "must have a type annotation"
            )

        # Extract Annotated[T, ...]
        if get_origin(annotation) is Annotated:
            base_type, *metadata = get_args(annotation)

            description = (
                metadata[0]
                if metadata and isinstance(metadata[0], str)
                else None
            )
        else:
            base_type = annotation
            description = None

        # Required vs optional
        if parameter.default is inspect.Parameter.empty:
            default = ...
        else:
            default = parameter.default

        fields[name] = (
            base_type,
            Field(
                default,
                description=description,
            ),
        )

    args_model = create_model(
        f"{func.__name__.title()}Args",
        **fields,
    )

    return Tool(
        name=func.__name__,
        description=inspect.getdoc(func) or "",
        args_model=args_model,
        py_callable=func,
    )