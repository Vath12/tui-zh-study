from mlx_lm import load
from mlx_lm.sample_utils import make_sampler
from mlx.core.random import seed as set_mlx_seed
from mlx.core.random import key as get_mlx_key
from mlx_lm.generate import generate_step, Sampler
from mlx_lm.models.cache import make_prompt_cache, trim_prompt_cache

from .registry import ModelSpec
from .tools.parsers import BufferState
from .tools import call_tool, generate_callid
import uuid
from enum import Enum

from .kv_cache import ModelCache
from .logit_mask import LogitMask

class ModelOutputClass(Enum):
    NORMAL = 0
    THINK = 1
    TOOL_CALL = 2
    TOOL_RESPONSE = 3
    TOOL_ERROR = 4

class Model():
    def __init__(self, model: ModelSpec):
        self.model, self.tokenizer = load(model.id)
        self.parser_cls = model.parser_cls
        self._logit_masks = {}

    def logit_mask(self, chars, bias=-float('inf')):
        key = (frozenset(chars), bias)
        if key not in self._logit_masks:
            self._logit_masks[key] = LogitMask(self.tokenizer, key[0], bias=bias)
        return self._logit_masks[key]

    def format_prompt(self, messages, tools=None, thinking=False):
        tool_dicts = []
        if tools is not None:
            tool_dicts = [x.to_dict() for x in self.tools]
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=thinking,
            tools=tool_dicts,
        )
 
    def __call__(self, text : str, cache : ModelCache, history_text : str = None, **kwargs):
        """history_text: the prompt without the generation prompt, used as the cache checkpoint."""

        tokens = self.tokenizer.encode(text)
        checkpoint = None
        if history_text is not None:
            checkpoint = cache._shared_prefix_len(self.tokenizer.encode(history_text), tokens)
        input_tokens = cache.update(tokens, checkpoint)

        for token, logprobs in generate_step(
            input_tokens, 
            self.model,
            prompt_cache=cache.cache, 
            max_tokens=8192,
            **kwargs
        ):
            cache.add(token)
            
            eos_ids = getattr(self.tokenizer, "eos_token_ids", None) \
                      or {self.tokenizer.eos_token_id}

            if token in eos_ids:
                break

            yield self.tokenizer.decode(token)

class ModelContext:
    def __init__(self, model : Model, tools=None, system_prompt="You are a helpful assistant."):
        self.model = model

        if tools is None:
            tools = []

        self.system_instruction = {
            "role": "system",
            "content": system_prompt,
        }
        self.tools = tools
        self.max_toolcalls = 100
        self.context = []
        self.cache = ModelCache(self.model.model)

    @property
    def tokenizer(self):
        return self.model.tokenizer

    def append_context(self, role, content, tools={}, **kwargs):
        message = {
            "role": role,
            "content": content,
        }
        message.update(kwargs)
        self.context.append(message)

    def format_prompt(self, thinking, add_generation_prompt=True):
        messages = [
            self.system_instruction,
            *self.context,
        ]
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=thinking,
            tools=[x.to_dict() for x in self.tools],
        )

    def generate(self, prompt, thinking, stream_callback : callable, seed, allowed_chars=None, logit_bias=-float('inf')):

        if allowed_chars is not None and thinking:
            raise ValueError('allowed_chars blocks think tokens; use thinking=False')

        self.append_context('user', prompt)
        
        called = 0
        set_mlx_seed(seed)

        sampler = make_sampler(
            temp = 0.9,
            top_p = 0.9,
            top_k = 20,
        )

        logits_processors = None
        if allowed_chars is not None:
            logits_processors = [self.model.logit_mask(allowed_chars, bias=logit_bias)]

        while called < self.max_toolcalls:
            formatted_prompt = self.format_prompt(thinking)
            history = self.format_prompt(thinking, add_generation_prompt=False)
            parser = self.model.parser_cls()
            toolcall = None
            
            response = ""

            for x in self.model(formatted_prompt, self.cache, history_text=history,
                                sampler=sampler, logits_processors=logits_processors):
                tok = str(x)

                r_append, toolcall = parser(tok)

                response += r_append
                
                if parser.tool_buffer.state != BufferState.NORMAL:
                    pass # don't stream incomplete tool calls
                elif parser.think_buffer.state != BufferState.NORMAL:
                    stream_callback(tok,ModelOutputClass.THINK)
                else:
                    stream_callback(tok,ModelOutputClass.NORMAL)

                if toolcall is not None:
                    toolcall.id = generate_callid()
                    break

            if toolcall is not None:
                stream_callback(toolcall, ModelOutputClass.TOOL_CALL)
                called += 1
                resp = call_tool(self.tools, toolcall)
                if resp.error is None:
                    stream_callback(resp.result,ModelOutputClass.TOOL_RESPONSE)
                else:
                    stream_callback(resp.error,ModelOutputClass.TOOL_ERROR)

                self.append_context('assistant', response)
                self.context.append(resp.to_dict())

                continue

            self.append_context('assistant', response)
            return response

    def __call__(self, prompt, stream_callback : callable, thinking=False, seed=42, allowed_chars=None, logit_bias=-float('inf')):
        return self.generate(prompt, thinking, stream_callback, seed, allowed_chars, logit_bias)