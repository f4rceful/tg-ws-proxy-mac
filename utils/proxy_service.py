"""Serialized proxy lifecycle work that never waits on the AppKit thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading

from proxy.tg_ws_proxy import _run
from utils.macos_common import apply_proxy_config, log


class ProxyService:
    def __init__(self, notify):
        self._notify = notify
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='proxy-control')
        self._thread = None
        self._loop = None
        self._stop = None
        self._ready = threading.Event()
        self._generation = 0
        self._closed = False
        self._gate = threading.Lock()

    def restart(self, config):
        with self._gate:
            if self._closed:
                return None
            return self._executor.submit(self._replace, deepcopy(config))

    def _stop_current(self):
        if self._thread is None:
            return
        if self._thread.is_alive():
            if not self._ready.wait(timeout=3):
                raise RuntimeError('Не удалось остановить запуск прокси. Попробуйте ещё раз.')
            if self._loop is not None and not self._loop.is_closed():
                try:
                    self._loop.call_soon_threadsafe(self._stop.set)
                except RuntimeError:
                    pass
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError('Прокси ещё завершает соединения. Повторите перезапуск позже.')
        self._thread = None
        self._loop = self._stop = None

    def _replace(self, config):
        if self._closed:
            return
        self._generation += 1
        generation = self._generation
        self._notify('starting', '')
        try:
            self._stop_current()
            if not apply_proxy_config(config):
                raise ValueError('Проверьте адреса дата-центров в настройках.')
            self._ready = threading.Event()
            self._thread = threading.Thread(target=self._serve, args=(generation,), daemon=True, name='proxy-network')
            self._thread.start()
        except Exception as exc:
            log.exception('Proxy restart failed')
            self._notify('error', str(exc))

    def _serve(self, generation):
        async def run():
            self._loop = asyncio.get_running_loop()
            self._stop = asyncio.Event()
            self._ready.set()
            def on_ready():
                if generation == self._generation:
                    self._notify('running', '')
            await _run(stop_event=self._stop, on_ready=on_ready)
        try:
            asyncio.run(run())
        except Exception as exc:
            log.exception('Proxy failed')
            if generation == self._generation:
                message = 'Порт занят. Измените порт в настройках.' if 'Address already in use' in str(exc) else str(exc)
                self._notify('error', message)

    def close(self):
        with self._gate:
            self._closed = True
            self._generation += 1
            future = self._executor.submit(self._stop_current)
            self._executor.shutdown(wait=False)
            return future
