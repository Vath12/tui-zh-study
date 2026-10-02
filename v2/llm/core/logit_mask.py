import mlx.core as mx

PUNCTUATION = ' ，,'
TERMINATORS = '。.？?！!'

class LogitMask():
    """mlx_lm logits processor that only allows tokens made of the given
    characters, spaces, commas, terminators, and the end-of-sequence token.
    Once a terminator is generated, only the end-of-sequence token is allowed.

    bias is added to the logits of disallowed tokens. The default -inf blocks them;
    a finite value (e.g. -5.0) only makes them less likely.

    Usage: generate_step(..., logits_processors=[LogitMask(tokenizer, chars)])
    """

    def __init__(self, tokenizer, chars, terminators=TERMINATORS, bias=-float('inf')):
        self.bias = bias
        self.terminators = set(terminators)
        self.allowed_chars = set(chars) | set(PUNCTUATION) | self.terminators

        vocab_size = len(tokenizer)
        texts = tokenizer.batch_decode([[i] for i in range(vocab_size)])
        special = set(getattr(tokenizer, 'all_special_ids', []))

        allowed = [
            i for i, text in enumerate(texts)
            if i not in special
            and text
            and '�' not in text # partial utf-8 byte token
            and all(c in self.allowed_chars for c in text)
            and not any(c in self.terminators for c in text[:-1]) # terminator only at the end
        ]
        self.terminal_ids = {i for i in allowed if texts[i][-1] in self.terminators}

        eos_ids = getattr(tokenizer, 'eos_token_ids', None) or tokenizer.eos_token_id
        self.eos_ids = sorted([eos_ids] if isinstance(eos_ids, int) else eos_ids)
        allowed.extend(self.eos_ids)

        # chars the tokenizer can't produce as a single token are allowed as their
        # exact multi-token encoding, enforced step by step
        self.sequences = []
        self.terminal_sequences = []
        for c in self.allowed_chars:
            ids = tokenizer.encode(c, add_special_tokens=False)
            if len(ids) > 1:
                self.sequences.append(ids)
                allowed.append(ids[0])
                if c in self.terminators:
                    self.terminal_sequences.append(ids)

        self.allowed = sorted(set(allowed))
        self._mask = None
        self._eos_mask = None

    @staticmethod
    def _make_mask(ids, size):
        return mx.zeros((size,), dtype=mx.bool_).at[mx.array(list(ids))].add(True)

    def _base_mask(self, size):
        if self._mask is None or self._mask.shape[-1] != size:
            self._mask = self._make_mask(self.allowed, size)
        return self._mask

    def _end_mask(self, size):
        if self._eos_mask is None or self._eos_mask.shape[-1] != size:
            self._eos_mask = self._make_mask(self.eos_ids, size)
        return self._eos_mask

    def _terminated(self, tokens):
        """True if the last generated token(s) completed a terminator."""
        if tokens is None or len(tokens) == 0:
            return False
        if tokens[-1].item() in self.terminal_ids:
            return True
        for seq in self.terminal_sequences:
            if len(tokens) >= len(seq) and tokens[-len(seq):].tolist() == seq:
                return True
        return False

    def _continuations(self, tokens):
        """Next token ids if we're partway through a multi-token char, else None."""
        if not self.sequences or tokens is None:
            return None
        longest = max(len(s) for s in self.sequences) - 1
        tail = tokens[-longest:].tolist()
        nexts = set()
        for seq in self.sequences:
            for k in range(1, len(seq)):
                if tail[-k:] == seq[:k]:
                    nexts.add(seq[k])
        return nexts or None

    def __call__(self, tokens, logits):
        size = logits.shape[-1]
        if self._terminated(tokens):
            mask = self._end_mask(size)
        elif (nexts := self._continuations(tokens)) is not None:
            mask = self._make_mask(nexts, size)
        else:
            mask = self._base_mask(size)
        return mx.where(mask, logits, logits + mx.array(self.bias, logits.dtype))
