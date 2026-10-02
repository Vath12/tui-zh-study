import asyncio
import threading
from .model import Model, ModelContext, ModelOutputClass
from .registry import MODELS
from queue import Queue
import logging
import traceback

_STOP = object()

class _Job():
    def __init__(self, ctx, prompt, kwargs, loop, future, on_output=None):
        self.ctx = ctx
        self.prompt = prompt
        self.kwargs = kwargs
        self.loop = loop
        self.future = future
        self.on_output = on_output

    def _call(self, fn, *args):
        try:
            self.loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass # event loop already closed

    def emit(self, content, ttype):
        if self.on_output is not None:
            self._call(self.on_output, content, ttype)

    def resolve(self, result):
        self._call(lambda: self.future.done() or self.future.set_result(result))

    def fail(self, e):
        self._call(lambda: self.future.done() or self.future.set_exception(e))


class ModelServer():
    """Owns a Model and the single core thread that runs it.
    All sessions on this server share the thread, so requests run one at a time."""

    def __init__(self, model : str | Model):
        if type(model) is str:
            self.model_name = model
            self.host = Model(MODELS[model])
        elif type(model) is Model:
            self.host = model
        else:
            raise Exception('invalid model type. supply Model or str identifier')

        self._jobs = Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def session(self, **kwargs):
        return ModelSession(self, ModelContext(self.host, **kwargs))

    def submit(self, ctx, prompt, on_output=None, **kwargs) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._jobs.put(_Job(ctx, prompt, kwargs, loop, future, on_output))
        return future

    def stop(self):
        self._jobs.put(_STOP)
        self._thread.join()

    def _loop(self):
        while (job := self._jobs.get()) is not _STOP:
            if job.future.cancelled():
                continue
            try:
                result = job.ctx(job.prompt, stream_callback=job.emit, **job.kwargs)
                job.resolve(result)
            except Exception as e:
                logging.error(f'model error: {traceback.format_exc()}')
                job.fail(e)


class ModelSession():
    """Async handle to one ModelContext (system prompt, tools, history) on a ModelServer."""

    def __init__(self, server : ModelServer, ctx : ModelContext):
        self.server = server
        self.ctx = ctx

    @property
    def cache_size(self):
        return self.ctx.cache.size

    async def prompt(self, prompt, thinking=True, seed=42, on_output=None, **kwargs) -> str:
        """Run a prompt and return the full response.
        on_output(content, ModelOutputClass) is called on the event loop as tokens arrive.
        allowed_chars restricts output to those characters plus spaces, commas, periods."""
        return await self.server.submit(
            self.ctx, prompt, on_output=on_output,
            thinking=thinking, seed=seed, **kwargs
        )

    async def stream(self, prompt, thinking=True, seed=42, **kwargs):
        """Async iterator over (content, ModelOutputClass) as the model generates."""
        queue = asyncio.Queue()
        done = self.server.submit(
            self.ctx, prompt,
            on_output=lambda c, t: queue.put_nowait((c, t)),
            thinking=thinking, seed=seed, **kwargs
        )
        done.add_done_callback(lambda _: queue.put_nowait(None))

        while (item := await queue.get()) is not None:
            yield item
        done.result() # re-raise model errors
