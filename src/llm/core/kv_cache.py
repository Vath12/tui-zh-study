from mlx_lm.models.cache import make_prompt_cache, trim_prompt_cache, can_trim_prompt_cache
import mlx.core as mx
import copy

PREFILL_CHUNK = 2048

class ModelCache():
    """KV cache that reuses the longest shared token prefix between calls.

    Trimmable caches (plain attention) are rewound in place. Caches with recurrent
    state (e.g. Qwen3.5's linear attention layers) can't be rewound, so the prompt
    is prefilled here and a checkpoint is saved at `checkpoint` tokens (default: the
    end of the prompt); the next call restores that checkpoint if it still shares
    the prefix, otherwise it starts over.
    """

    def __init__(self, model):
        self.model = model
        self.reset()

    def reset(self):
        self._cache = make_prompt_cache(self.model)
        self._cached_tokens = []
        self._checkpoint = None # (n_tokens, cache) saved during the last prompt

    @property
    def size(self):
        return len(self._cached_tokens)

    @property
    def cache(self):
        return self._cache

    @property
    def cached_tokens(self):
        return self._cached_tokens

    @property
    def trimmable(self):
        return can_trim_prompt_cache(self._cache)

    def _shared_prefix_len(self, old_ids, new_ids):
        n = min(len(old_ids), len(new_ids))
        i = 0
        while i < n and old_ids[i] == new_ids[i]:
            i += 1
        return i

    def _rewind(self, n_tokens):
        """Rewind the cache to its first n_tokens. Returns how many tokens are kept."""
        n_to_trim = len(self._cached_tokens) - n_tokens
        if n_to_trim == 0:
            return n_tokens

        if self.trimmable and trim_prompt_cache(self._cache, n_to_trim) == n_to_trim:
            return n_tokens

        if self._checkpoint is not None and self._checkpoint[0] <= n_tokens:
            kept, self._cache = self._checkpoint
            self._checkpoint = None
            return kept

        self.reset()
        return 0

    def _prefill(self, ids):
        for i in range(0, len(ids), PREFILL_CHUNK):
            self.model(mx.array(ids[i:i + PREFILL_CHUNK])[None], cache=self._cache)
            mx.eval([c.state for c in self._cache])

    def update(self, tokens, checkpoint=None):
        """Sync the cache to `tokens` and return the ids generate_step still has to feed.
        checkpoint: token count to snapshot at for untrimmable caches. Pick a point the
        next prompt will still share, e.g. the end of the history before the generation prompt."""
        tokens = list(tokens)
        last = len(tokens) - 1 # generate_step needs at least one new token to produce logits from

        shared = min(self._shared_prefix_len(self._cached_tokens, tokens), last)
        shared = self._rewind(shared)

        new_ids = tokens[shared:]
        if not self.trimmable:
            checkpoint = last if checkpoint is None else min(checkpoint, last)
            if checkpoint >= shared:
                self._prefill(tokens[shared:checkpoint])
                self._checkpoint = (checkpoint, copy.deepcopy(self._cache))
                shared = checkpoint
            self._prefill(tokens[shared:last])
            new_ids = tokens[last:]

        self._cached_tokens = tokens
        return mx.array(new_ids)

    def add(self, token, **kwargs):
        self._cached_tokens.append(token)
