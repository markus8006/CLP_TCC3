# models/organization.py
from src.app import db
from datetime import datetime, timezone
from sqlalchemy.orm import relationship, backref

class Organization(db.Model):
    __tablename__ = "organization"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    children = relationship(
        "Organization",
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Organization id={self.id} name={self.name}>"


# models/plc.py
import json
from typing import Iterable, List

from src.app import db
from datetime import datetime
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.ext.mutable import MutableList
from src.utils.tags import parse_tags

class PLC(db.Model):
    __tablename__ = "plc"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    ip_address = db.Column(db.String(45), nullable=False)  # ipv6-safe
    mac_address = db.Column(db.String(17))
    subnet_mask = db.Column(db.String(45))
    vlan_id = db.Column(db.Integer)  # importante para diferenciar IPs por VLAN
    gateway = db.Column(db.String(45))

    protocol = db.Column(db.String(20), nullable=False)  # modbus, s7, ethernet_ip
    port = db.Column(db.Integer, nullable=False)
    unit_id = db.Column(db.Integer)  # Para Modbus
    rack_slot = db.Column(db.String(10))  # Para S7 (rack.slot)

    manufacturer = db.Column(db.String(50))
    model = db.Column(db.String(50))
    firmware_version = db.Column(db.String(20))
    serial_number = db.Column(db.String(50))

    last_maintenance = db.Column(db.DateTime)
    maintenance_by = db.Column(db.String(100))
    maintenance_notes = db.Column(db.Text)
    next_maintenance = db.Column(db.DateTime)

    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'))
    organization = db.relationship("Organization", backref="plcs")

    # use JSON se seu DB suportar (Postgres). Caso contrário Text.
    try:
        tags = db.Column(MutableList.as_mutable(db.JSON), default=list)
    except Exception:
        # SQLite anterior e alguns bancos não suportam JSON nativamente.
        # Mantemos Text mas garantimos serialização consistente.
        tags = db.Column(db.Text, default="[]")

    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)
    polling_interval = db.Column(db.Integer, default=1000)  # ms
    timeout = db.Column(db.Integer, default=5000)  # ms
    retry_count = db.Column(db.Integer, default=3)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    registers = db.relationship('Register', backref='plc', cascade='all, delete-orphan')
    data_logs = db.relationship('DataLog', backref='plc')
    alarms = db.relationship('Alarm', backref='plc')

    __table_args__ = (
        # Se existir mesma IP em VLANs diferentes, precisa diferenciar:
        UniqueConstraint('ip_address', 'vlan_id', name='uq_plc_ip_vlan'),
        Index('ix_plc_ip_vlan', 'ip_address', 'vlan_id'),
    )

    def __repr__(self):
        return f"<PLC id={self.id} name={self.name} ip={self.ip_address} vlan={self.vlan_id}>"

    # --- Utilidades para Tags -------------------------------------------------
    def tags_as_list(self) -> List[str]:
        """Retorna as tags como lista normalizada."""
        value = getattr(self, "tags", None)
        if not value:
            return []
        if isinstance(value, list):
            return [str(tag).strip() for tag in value if str(tag).strip()]
        if isinstance(value, (set, tuple)):
            return [str(tag).strip() for tag in value if str(tag).strip()]

        # Se for texto (fallback de coluna Text), tentar desserializar JSON
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(tag).strip() for tag in parsed if str(tag).strip()]
            except (TypeError, ValueError):
                pass
            return [str(tag).strip() for tag in value.split(',') if str(tag).strip()]

        return [str(value).strip()] if str(value).strip() else []

    def set_tags(self, tags: Iterable[str]) -> None:
        """Normaliza e define as tags do CLP."""
        if tags is None:
            normalized: List[str] = []
        else:
            normalized = parse_tags(tags)

    # Remove duplicados mantendo a ordem
        seen = set()
        unique = []
        for tag in normalized:
            if tag not in seen:
                unique.append(tag)
                seen.add(tag)

    # --- Ajuste principal ---
    # Se a coluna for JSON (como em Postgres), ou se já for lista no ORM, manter lista.
        if isinstance(self.tags, list) or isinstance(self.__table__.c.tags.type, db.JSON):
            self.tags = unique
        else:
        # Fallback para bancos que usam Text (ex: SQLite sem JSON nativo)
            self.tags = json.dumps(unique, ensure_ascii=False)

