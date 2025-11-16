"""Helpers for ensuring local gRPC stubs are available at runtime."""

from __future__ import annotations

from pathlib import Path
import logging

LOGGER = logging.getLogger(__name__)


def _generated_files() -> tuple[Path, Path]:
    pkg_dir = Path(__file__).resolve().parent
    return (
        pkg_dir / "polling_pb2.py",
        pkg_dir / "polling_pb2_grpc.py",
    )


def ensure_generated(*, force: bool = False) -> None:
    """Compile the polling proto if the generated files are missing."""

    generated = _generated_files()
    if not force and all(path.exists() for path in generated):
        return

    proto_path = Path(__file__).resolve().parents[2] / "go" / "polling" / "polling.proto"
    if not proto_path.exists():
        raise FileNotFoundError(
            f"Arquivo polling.proto não encontrado em {proto_path}."
        )

    try:
        from grpc_tools import protoc
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "Dependência grpcio-tools não instalada; não é possível gerar stubs gRPC."
        ) from exc

    args = (
        "",  # placeholder para o nome do programa esperado por protoc.main
        f"-I{proto_path.parent}",
        f"--python_out={generated[0].parent}",
        f"--grpc_python_out={generated[0].parent}",
        str(proto_path),
    )
    LOGGER.info("Gerando stubs gRPC Python a partir de %s", proto_path)
    result = protoc.main(args)
    if result != 0:
        raise RuntimeError(
            f"Falha ao gerar arquivos gRPC (código de saída {result})."
        )


# Garante que os módulos estejam disponíveis assim que o pacote for importado.
ensure_generated()

from . import polling_pb2, polling_pb2_grpc  # noqa: E402  (importa após geração)

__all__ = ["ensure_generated", "polling_pb2", "polling_pb2_grpc"]
