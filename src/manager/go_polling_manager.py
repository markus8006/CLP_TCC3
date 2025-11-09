import asyncio
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.manager.client_polling_manager import ActivePLCPoller
from src.models.PLCs import PLC
from src.utils.logs import logger


def is_go_available() -> bool:
    """Returns True if a Go toolchain is available on PATH."""

    return shutil.which("go") is not None


class GoPollingManager:
    """Polling manager that delegates scheduling to a Go runtime."""

    def __init__(
        self,
        flask_app,
        *,
        binary_path: Optional[Path] = None,
        build_binary: bool = True,
        poller_factory=ActivePLCPoller,
        go_command: Optional[List[str]] = None,
    ) -> None:
        self.flask_app = flask_app
        self._poller_factory = poller_factory
        self._pollers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._pending: Dict[Tuple[str, Optional[str]], List[Tuple[asyncio.AbstractEventLoop, asyncio.Future]]] = {}
        self._pending_lock = threading.Lock()
        self._writer_lock = threading.Lock()
        self._ready = threading.Event()
        self._closed = False

        base_dir = Path(__file__).resolve().parents[2]
        default_bin = "go_polling_service.exe" if os.name == "nt" else "go_polling_service"
        self._binary_path = Path(binary_path) if binary_path else base_dir / "bin" / default_bin
        self._binary_path.parent.mkdir(parents=True, exist_ok=True)
        self._go_command = go_command

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        if go_command is None:
            if not self._binary_path.exists() and not build_binary:
                raise RuntimeError("Go polling binary not found and build disabled.")
            if not self._binary_path.exists():
                self._build_binary()
            command = [str(self._binary_path)]
        else:
            command = go_command

        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

        if not self._ready.wait(timeout=10):
            raise RuntimeError("Go polling runtime did not signal readiness in time.")

    def _build_binary(self) -> None:
        if not is_go_available():
            raise RuntimeError("Go toolchain is not available to build polling runtime.")

        source_dir = Path(__file__).resolve().parents[2] / "go" / "polling"
        cmd = ["go", "build", "-o", str(self._binary_path), "./cmd/poller"]
        logger.info("Compilando serviço de polling Go em %s", self._binary_path)
        subprocess.run(cmd, cwd=source_dir, check=True)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    @staticmethod
    def make_key(ip: str, vlan: Optional[int]) -> str:
        return f"{ip}|{vlan or 0}"

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.error("Resposta inválida do runtime Go: %s", line)
                continue
            self._handle_event(payload)

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for line in self._process.stderr:
            logger.error("[go-polling] %s", line.rstrip())

    def _handle_event(self, payload: Dict[str, Any]) -> None:
        event = payload.get("event")
        key = payload.get("key")
        if event == "ready":
            self._ready.set()
            self._resolve_waiters("ready", None, payload)
            return
        if event in {"added", "removed", "updated", "shutdown"}:
            self._resolve_waiters(event, key, payload)
            return
        if event == "error":
            logger.error("Runtime Go reportou erro: %s", payload.get("message"))
            self._resolve_waiters("error", key, payload)
            return
        logger.warning("Evento desconhecido do runtime Go: %s", payload)

    def _resolve_waiters(self, event: str, key: Optional[str], payload: Dict[str, Any]) -> None:
        with self._pending_lock:
            waiters = self._pending.pop((event, key), [])
        for loop, fut in waiters:
            loop.call_soon_threadsafe(fut.set_result, payload)

    async def _wait_for(self, event: str, key: Optional[str]) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        with self._pending_lock:
            self._pending.setdefault((event, key), []).append((loop, fut))
        return await fut

    def _send_command(self, payload: Dict[str, Any]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("Runtime Go não possui stdin disponível.")
        line = json.dumps(payload)
        with self._writer_lock:
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()

    async def _await_threadsafe(self, coro):
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(future, loop=loop)

    async def add_plc(self, plc_orm: PLC, registers_provider):
        key = self.make_key(plc_orm.ip_address, plc_orm.vlan_id)
        async with self._lock:
            if key in self._pollers:
                self._pollers[key]["poller"].registers_provider = registers_provider
                interval = getattr(plc_orm, "polling_interval", 1000)
                self._send_command({"cmd": "update", "key": key, "interval": interval})
                await self._wait_for("updated", key)
                return self._pollers[key]["poller"]
            poller = self._poller_factory(plc_orm, registers_provider, flask_app=self.flask_app)
            self._pollers[key] = {"poller": poller, "plc": plc_orm, "stopping": False}
        interval = getattr(plc_orm, "polling_interval", 1000)
        self._send_command({"cmd": "add", "key": key, "interval": interval})
        await self._wait_for("added", key)
        return poller

    async def remove_plc(self, ip: str, vlan: Optional[int] = None):
        key = self.make_key(ip, vlan)
        async with self._lock:
            info = self._pollers.get(key)
            if info is None:
                self._send_command({"cmd": "remove", "key": key})
                await self._wait_for("removed", key)
                return False
            info["stopping"] = True
        self._send_command({"cmd": "remove", "key": key})
        await self._wait_for("removed", key)
        await self._await_threadsafe(info["poller"].stop())
        async with self._lock:
            self._pollers.pop(key, None)
        return True

    async def shutdown(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._process.poll() is None:
                self._send_command({"cmd": "shutdown"})
                await self._wait_for("shutdown", None)
        except Exception:
            logger.exception("Falha ao enviar comando de shutdown para runtime Go.")
        async with self._lock:
            pollers = list(self._pollers.values())
            self._pollers.clear()
        for info in pollers:
            try:
                await self._await_threadsafe(info["poller"].stop())
            except Exception:
                logger.exception("Erro ao finalizar poller %s", info["plc"].id)
        if self._process.stdin:
            try:
                self._process.stdin.close()
            except Exception:
                pass
        if self._process.poll() is None:
            self._process.terminate()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=5)

    def __del__(self):  # pragma: no cover - limpeza defensiva
        try:
            if not self._closed and self._process.poll() is None:
                self._process.kill()
        except Exception:
            pass
