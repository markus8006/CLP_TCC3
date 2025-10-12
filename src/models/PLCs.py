from src.app import db
from datetime import datetime

class Organization(db.Model):
    """Estrutura organizacional/pastas para PLCs"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('organization.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PLC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Informações de Rede
    ip_address = db.Column(db.String(15), nullable=False)
    mac_address = db.Column(db.String(17))
    subnet_mask = db.Column(db.String(15))
    vlan_id = db.Column(db.Integer)
    gateway = db.Column(db.String(15))
    
    # Configuração de Comunicação
    protocol = db.Column(db.String(20), nullable=False)  # modbus, s7, ethernet_ip
    port = db.Column(db.Integer, nullable=False)
    unit_id = db.Column(db.Integer)  # Para Modbus
    rack_slot = db.Column(db.String(10))  # Para S7 (rack.slot)
    
    # Informações do Equipamento
    manufacturer = db.Column(db.String(50))
    model = db.Column(db.String(50))
    firmware_version = db.Column(db.String(20))
    serial_number = db.Column(db.String(50))
    
    # Manutenção
    last_maintenance = db.Column(db.DateTime)
    maintenance_by = db.Column(db.String(100))
    maintenance_notes = db.Column(db.Text)
    next_maintenance = db.Column(db.DateTime)
    
    # Organização
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'))
    tags = db.Column(db.Text)  # JSON array de tags para busca
    
    # Status e Configuração
    is_active = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)
    polling_interval = db.Column(db.Integer, default=1000)  # ms
    timeout = db.Column(db.Integer, default=5000)  # ms
    retry_count = db.Column(db.Integer, default=3)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    registers = db.relationship('Register', backref='plc', cascade='all, delete-orphan')
    data_logs = db.relationship('DataLog', backref='plc')
    alarms = db.relationship('Alarm', backref='plc')
