"""Estruturas utilitárias para coordenar o serviço de polling assíncrono."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from flask import Flask

from src.services.client_polling_service import StateCache

if TYPE_CHECKING:  # pragma: no cover - apenas para linting
    from src.manager.client_polling_manager import SimpleManager


@dataclass
class PollingRuntime:
    """Guarda o estado partilhado do serviço de polling."""

    manager: "SimpleManager"
    loop: Optional[asyncio.AbstractEventLoop] = None
    trigger: Optional[asyncio.Event] = None
    cache: StateCache = field(default_factory=dict)
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
                # Loop pode ter sido encerrado — ignore silenciosamente
                pass

    def ensure_trigger(self) -> asyncio.Event:
        if not self.trigger:
            self.trigger = asyncio.Event()
        return self.trigger


def register_runtime(app: Flask, runtime: PollingRuntime) -> None:
    app.extensions["polling_runtime"] = runtime


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
