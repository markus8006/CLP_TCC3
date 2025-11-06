"""Serviços de importação/exportação de registradores."""

from __future__ import annotations

import io
from typing import Iterable, List, Tuple

try:  # pragma: no cover - import opcional
    import pandas as pd
except ImportError:  # pragma: no cover - ambiente de teste sem pandas
    pd = None  # type: ignore

from src.app.extensions import db
from src.models.Registers import Register
from src.services.address_mapping import AddressMappingEngine


class RegisterImportExportService:
    """Responsável por importar e exportar registradores em massa."""

    def __init__(self) -> None:
        self._engine = AddressMappingEngine()

    def import_dataframe(self, frame: pd.DataFrame, *, plc, protocol: str) -> Tuple[int, List[str]]:
        self._ensure_pandas()
        created = 0
        errors: List[str] = []

        for index, row in frame.iterrows():
            tag = str(row.get("Tag") or row.get("tag") or "").strip()
            address = str(row.get("Endereço") or row.get("endereco") or row.get("address") or "").strip()
            data_type = str(row.get("Tipo") or row.get("tipo") or "").strip()
            unit = (row.get("Unidade") or row.get("unidade") or "").strip() or None
            description = row.get("Descrição") or row.get("descricao") or None

            if not address:
                errors.append(f"Linha {index + 2}: endereço em branco")
                continue

            try:
                normalized = self._engine.normalize(protocol, address)
            except ValueError as exc:
                errors.append(f"Linha {index + 2}: {exc}")
                continue

            register = Register(
                plc_id=plc.id,
                name=tag or address,
                tag_name=tag or None,
                address=address,
                register_type="analogue",
                data_type=data_type or "desconhecido",
                unit=unit,
                description=description,
                protocol=protocol,
                normalized_address=normalized,
            )

            db.session.add(register)
            created += 1

        db.session.commit()
        return created, errors

    def export_dataframe(self, registers: Iterable[Register], *, include_plc: bool = False) -> pd.DataFrame:
        self._ensure_pandas()
        rows = []
        for register in registers:
            row = {
                "Tag": register.tag_name or register.name,
                "Endereço": register.address,
                "Tipo": register.data_type,
                "Unidade": register.unit or "",
                "Descrição": register.description or "",
            }

            if include_plc:
                plc = getattr(register, "plc", None)
                row = {
                    "Controlador": plc.name if plc else f"# {register.plc_id}",
                    "Protocolo": (register.protocol or (plc.protocol if plc else "")) or "",
                    "IP": plc.ip_address if plc and plc.ip_address else "",
                    "VLAN": plc.vlan_id if plc and plc.vlan_id is not None else "",
                    **row,
                }

            rows.append(row)

        if include_plc:
            columns = [
                "Controlador",
                "Protocolo",
                "IP",
                "VLAN",
                "Tag",
                "Endereço",
                "Tipo",
                "Unidade",
                "Descrição",
            ]
            return pd.DataFrame(rows, columns=columns)

        return pd.DataFrame(rows)

    def dataframe_from_file(self, stream, filename: str) -> pd.DataFrame:
        self._ensure_pandas()
        if hasattr(stream, "seek"):
            stream.seek(0)
        if filename.lower().endswith((".xls", ".xlsx", ".xlsm")):
            return pd.read_excel(stream)
        return pd.read_csv(stream)

    def export_to_bytes(self, frame: pd.DataFrame, *, file_format: str) -> Tuple[bytes, str]:
        file_format = file_format.lower()
        buffer = io.BytesIO()
        if file_format == "xlsx":
            frame.to_excel(buffer, index=False)
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            frame.to_csv(buffer, index=False)
            mime = "text/csv"
        buffer.seek(0)
        return buffer.read(), mime

    @staticmethod
    def _ensure_pandas() -> None:
        if pd is None:  # pragma: no cover - depende de instalação externa
            raise RuntimeError(
                "A biblioteca pandas é necessária para importar/exportar registradores. Instale 'pandas' e 'openpyxl'."
            )


__all__ = ["RegisterImportExportService"]
