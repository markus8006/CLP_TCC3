from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from queue import Queue
from typing import Optional

from flask import Flask

from src.app.settings import get_app_settings


@dataclass
class PollingRuntime:
    """Guarda o estado partilhado do serviço de polling baseado em Go."""

    manager: "GoPollingManager"
    data_queue: Queue[str]
    loop: Optional[asyncio.AbstractEventLoop] = None
    trigger: Optional[asyncio.Event] = None
    consumer_thread: Optional[threading.Thread] = None
    consumer_stop_event: threading.Event = field(default_factory=threading.Event)
    _enabled: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, state: bool) -> None:
        with self._lock:
            self._enabled = state

    def notify(self) -> None:
        if self.loop and self.trigger:
            try:
                self.loop.call_soon_threadsafe(self.trigger.set)
            except RuntimeError:
                pass

    def ensure_trigger(self) -> asyncio.Event:
        if not self.trigger:
            self.trigger = asyncio.Event()
        return self.trigger


def register_runtime(app: Flask, runtime: PollingRuntime) -> None:
    app.extensions["polling_runtime"] = runtime

    try:
        settings = get_app_settings(app)
    except RuntimeError:
        return

    enabled = settings.features.enable_polling
    if not enabled and settings.demo.enabled and settings.demo.disable_polling:
        enabled = True
    runtime.set_enabled(enabled)
    if not enabled:
        runtime.notify()


def get_runtime(app: Flask) -> Optional[PollingRuntime]:
    runtime = app.extensions.get("polling_runtime")
    return runtime if isinstance(runtime, PollingRuntime) else None


def trigger_polling_refresh(app: Flask) -> None:
    runtime = get_runtime(app)
    if runtime:
        runtime.notify()


def set_runtime_enabled(app: Flask, enabled: bool) -> None:
    runtime = get_runtime(app)
    if runtime:
        runtime.set_enabled(enabled)
        runtime.notify()
