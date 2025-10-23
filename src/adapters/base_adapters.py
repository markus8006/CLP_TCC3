from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.repository.Alarms_repository import AlarmDefinitionRepo




class BaseAdapter(ABC):
    def __inti__(self):
        AlarmRepo = AlarmDefinitionRepo()
    
    @abstractmethod
    async def connect(self) -> bool:
        """Conecta ao dispositivo"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Desconecta do dispositivo"""
        pass
    
    @abstractmethod
    async def read_registers(self, registers: List[Dict]) -> List[Dict]:
        """Lê múltiplos registradores"""
        pass
    
    @abstractmethod
    async def write_register(self, address: int, value: Any) -> bool:
        """Escreve em um registrador"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Verifica se está conectado"""
        pass

    def _verify_alarm(self, id):
        return AlarmRepo.alarm_by_register_id(id)


