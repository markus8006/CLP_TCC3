import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Optional

import grpc

from src.grpc_generated import polling_pb2, polling_pb2_grpc
from src.utils.logs import logger


def is_go_available() -> bool:
    """Returns True if a Go toolchain is available on PATH."""

    return shutil.which("go") is not None


class GoPollingManager:
    """Manage the lifecycle of the Go polling runtime via gRPC."""

    def __init__(
        self,
        data_queue: Queue,
        *,
        binary_path: Optional[Path] = None,
        build_binary: bool = True,
        go_command: Optional[list[str]] = None,
    ) -> None:
        self.data_queue = data_queue
        self._go_command = go_command
        self._build_binary = build_binary
        self._binary_path = self._resolve_binary_path(binary_path)
        self._process: Optional[subprocess.Popen[str]] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[polling_pb2_grpc.PollingServiceStub] = None

    def _resolve_binary_path(self, explicit: Optional[Path]) -> Path:
        if explicit:
            return Path(explicit)
        base_dir = Path(__file__).resolve().parents[2]
        default_name = (
            "go_polling_service.exe" if os.name == "nt" else "go_polling_service"
        )
        target = base_dir / "bin" / default_name
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _ensure_binary(self) -> list[str]:
        if self._go_command is not None:
            return self._go_command
        if self._binary_path.exists():
            return [str(self._binary_path)]
        if not self._build_binary:
            raise RuntimeError("Go polling binary not found and build disabled.")
        if not is_go_available():
            raise RuntimeError(
                "Go toolchain is not available to build polling runtime."
            )

        source_dir = Path(__file__).resolve().parents[2] / "go" / "polling"
        cmd = ["go", "build", "-o", str(self._binary_path), "./cmd/poller"]
        logger.info("Compilando serviço de polling Go em %s", self._binary_path)
        subprocess.run(cmd, cwd=source_dir, check=True)
        return [str(self._binary_path)]

    def start(self, initial_config: Dict[str, Any]) -> None:
        if self._process is not None:
            raise RuntimeError("Go polling manager already started.")

        command = self._ensure_binary()
        self._process = subprocess.Popen(
            command,
            stdin=None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._stop_event.clear()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

        time.sleep(1.5)

        self.channel = grpc.insecure_channel("localhost:50051")
        try:
            grpc.channel_ready_future(self.channel).result(timeout=5.0)
        except grpc.FutureTimeoutError as exc:
            logger.exception("Canal gRPC não ficou pronto a tempo.")
            self.stop()
            raise RuntimeError("Falha ao conectar ao poller Go via gRPC") from exc

        self.stub = polling_pb2_grpc.PollingServiceStub(self.channel)
        try:
            self.update_config(initial_config)
        except Exception:
            self.stop()
            raise

        self._stream_thread = threading.Thread(target=self._read_stream, daemon=True)
        self._stream_thread.start()

    def _read_stream(self) -> None:
        assert self.stub is not None
        while not self._stop_event.is_set():
            try:
                response_stream = self.stub.StreamData(polling_pb2.Empty())
                for data_payload in response_stream:
                    self.data_queue.put(data_payload.json_data)
                if self._stop_event.is_set():
                    break
            except grpc.RpcError as exc:
                if exc.code() == grpc.StatusCode.UNAVAILABLE:
                    if not self._stop_event.is_set():
                        logger.error(
                            "Conexão gRPC indisponível; aguardando processo Go reiniciar."
                        )
                        time.sleep(1.0)
                    continue
                logger.exception(
                    "Erro ao consumir stream de dados do poller Go: %s", exc
                )
                time.sleep(1.0)
            except Exception:
                logger.exception(
                    "Falha inesperada ao consumir stream gRPC do poller Go."
                )
                time.sleep(1.0)

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            logger.error("[go-polling] %s", line.rstrip())
            if self._stop_event.is_set():
                break

    def update_config(self, new_config_data: Dict[str, Any]) -> None:
        if self.stub is None:
            raise RuntimeError("gRPC client not initialised.")
        try:
            json_payload = json.dumps(new_config_data)
        except (TypeError, ValueError) as exc:
            raise ValueError("Configuração inválida para o poller Go") from exc

        try:
            response = self.stub.UpdateConfig(
                polling_pb2.ConfigPayload(json_config=json_payload)
            )
        except grpc.RpcError as exc:
            logger.exception("Falha ao enviar configuração ao poller Go: %s", exc)
            raise

        if not response.success:
            raise RuntimeError(f"Poller Go rejeitou configuração: {response.message}")

    def stop(self) -> None:
        self._stop_event.set()

        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None

        if self._process and self._process.poll() is None:
            try:
                self._process.send_signal(signal.SIGTERM)
            except Exception:
                logger.exception("Falha ao enviar SIGTERM para poller Go.")
        if self._stream_thread:
            self._stream_thread.join(timeout=5)
            self._stream_thread = None
        if self._stderr_thread:
            self._stderr_thread.join(timeout=5)
            self._stderr_thread = None
        if self._process:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
