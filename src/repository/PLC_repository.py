from typing import List, Optional, Dict
from src.models.PLCs import PLC

    
class PLCRepo():
    
    def __init__(self, db):
        self.db = db
        
        
    
    def buscar_por_ip(self, ip_address: str) -> str:
        return self.db.session.query(PLC).filter(
            PLC.ip_address == ip_address
        ).first()
    
    def listar_todos_clps(self) -> List[PLC]:
        return self.db.session.query(PLC).filter().all()