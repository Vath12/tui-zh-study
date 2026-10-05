from dataclasses import dataclass
from .tools.parsers import ModelParser, QwenParser, GemmaParser

@dataclass
class ModelSpec():
    id : str
    parser_cls : None

    def __post_init__(self):
        if not issubclass(self.parser_cls,ModelParser):
            raise Exception("ModelSpec parser must inherit from ModelParser")

MODELS = {
    "Gemma4-12B" : ModelSpec(
        'mlx-community/gemma-4-12B-it-qat-4bit',
        GemmaParser
    ),
    "Gemma4-4B" : ModelSpec(
        'mlx-community/gemma-4-e4b-it-4bit',
        GemmaParser
    ),
    'Qwen3.5-9B':ModelSpec(
        'mlx-community/Qwen3.5-9B-MLX-4bit',
        QwenParser
    ),
    'Qwen3.5-4B':ModelSpec(
        'mlx-community/Qwen3.5-4B-MLX-4bit',
        QwenParser
    ),
    'Phi4-3B':ModelSpec(
        'mlx-community/Phi-4-mini-instruct-4bit',
        QwenParser
    ),
}
