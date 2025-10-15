import threading
import ctypes
import time
from typing import Dict, Optional

import snap7
from snap7.types import WordLen
from snap7 import types as s7types

from src.utils.log.log import setup_logger
import logging

logger = setup_logger()
# reduzir verbosidade do snap7
logging.getLogger("snap7").setLevel(logging.WARNING)


class S7Simulator:
    """
    Simulador S7 baseado na API python-snap7 Server.
    Controle de ciclo de vida do servidor, gerenciamento de DBs simulados e leitura/escrita.
    """

    def __init__(self, tcp_port: int = 102, init_standard_values: bool = False):
        self.tcp_port = tcp_port
        self.init_standard_values = init_standard_values
        self._server: Optional[snap7.server.Server] = None
        self._db_buffers: Dict[int, ctypes.Array] = {}  # db_number -> ctypes buffer
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    def _create_server(self):
        logger.info("Criando servidor S7 (python-snap7)...")
        self._server = snap7.server.Server()

    def register_db(self, db_number: int, size: int = 100):
        """
        Registra ou atualiza um DB com buffer mutável de tamanho 'size'.
        Deve ser chamado apenas após servidor estar iniciado.
        """
        if self._server is None:
            raise RuntimeError("Servidor não iniciado. Chame start() antes de registrar DBs.")

        # Criar buffer ctypes para bytes
        buf_type = (s7types.wordlen_to_ctypes[WordLen.Byte.value] * size)
        buf = buf_type()

        # Registrar área DB no servidor - lança erro se DB já registrado
        self._server.register_area(s7types.srvAreaDB, db_number, buf)

        # Armazenar para referência e leitura/escrita futura
        self._db_buffers[db_number] = buf
        logger.info("DB %d registrado com tamanho %d bytes", db_number, size)

    def write_db(self, db_number: int, offset: int, data: bytes):
        """
        Escreve bytes no buffer do DB registrado.
        """
        if db_number not in self._db_buffers:
            raise ValueError(f"DB {db_number} não registrado")

        buf = self._db_buffers[db_number]
        buf_size = ctypes.sizeof(buf)
        end = offset + len(data)
        if offset < 0 or end > buf_size:
            raise ValueError(f"Escrita fora do range do DB (0..{buf_size - 1})")

        # Copia byte-a-byte para o buffer ctypes
        for i, b in enumerate(data):
            buf[offset + i] = b
        logger.debug("Escritos %d bytes em DB %d offset %d", len(data), db_number, offset)

    def read_db(self, db_number: int, offset: int, size: int) -> bytes:
        """
        Lê bytes do DB registrado.
        """
        if db_number not in self._db_buffers:
            raise ValueError(f"DB {db_number} não registrado")

        buf = self._db_buffers[db_number]
        buf_size = ctypes.sizeof(buf)
        end = offset + size
        if offset < 0 or end > buf_size:
            raise ValueError(f"Leitura fora do range do DB (0..{buf_size - 1})")

        raw = bytes(buf[offset:end])
        logger.debug("Lidos %d bytes de DB %d offset %d", len(raw), db_number, offset)
        return raw

    def start(self, host: str = "127.0.0.2"):
        """
        Inicia o servidor S7 em thread daemon, para rodar assíncrono.
        """
        if self._server is not None:
            logger.warning("Servidor S7 já iniciado")
            return

        self._create_server()

        def run_loop():
            assert self._server is not None

            # Garante DB 1 registrado para evitar problemas
            if 1 not in self._db_buffers:
                try:
                    self.register_db(1, 100)
                except Exception as e:
                    logger.exception(f"Erro ao registrar DB1 na inicialização: {e}")

            try:
                self._server.start(tcpport=self.tcp_port)
                logger.info("Servidor S7 iniciado em %s:%d", host, self.tcp_port)
            except Exception:
                logger.exception("Erro ao iniciar servidor S7")
                return

            while not self._stop_flag.is_set():
                try:
                    event = self._server.pick_event()
                    if event:
                        logger.info("S7 event: %s", self._server.event_text(event))
                    else:
                        time.sleep(0.5)
                except Exception:
                    logger.exception("Erro no loop do servidor S7")
                    break

            try:
                self._server.stop()
                logger.info("Servidor S7 parado")
            except Exception:
                logger.exception("Erro parando servidor S7")

        self._thread = threading.Thread(target=run_loop, name="S7SimulatorThread", daemon=True)
        self._stop_flag.clear()
        self._thread.start()

    def stop(self):
        """
        Solicita parada do servidor e aguarda thread encerrar.
        """
        if self._server is None:
            logger.warning("Servidor S7 não está rodando")
            return

        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=5.0)

        try:
            self._server.destroy()
        except Exception:
            logger.exception("Erro destruindo servidor")

        self._server = None
        self._db_buffers.clear()
        logger.info("Simulador S7 finalizado")


# Utilitários para facilitar testes

def add_db_test_value(sim: S7Simulator, db_number: int = 1, address: int = 0, value: int = 123, size: int = 2):
    """
    Exemplo para escrever int16 ou int32 big-endian no DB.
    """
    import struct

    if size == 2:
        packed = struct.pack(">h", int(value))  # int16 big-endian
    elif size == 4:
        packed = struct.pack(">i", int(value))  # int32 big-endian
    else:
        raise ValueError("size só suportado 2 ou 4 neste utilitário")

    sim.write_db(db_number, address, packed)
    logger.info(f"Valor de teste gravado em DB {db_number}@{address} -> {packed.hex()}")


def initialize_s7_test_dbs(sim: S7Simulator):
    """
    Inicializa DBs padrão para testes com valores simulados:
    - DB1: Temperatura (int16)
    - DB2: Pressão (int16)
    - DB3: Status da bomba (bool)
    """
    if 1 not in sim._db_buffers:
        sim.register_db(1, 2)
    add_db_test_value(sim, db_number=1, address=0, value=25, size=2)

    if 2 not in sim._db_buffers:
        sim.register_db(2, 2)
    add_db_test_value(sim, db_number=2, address=0, value=96, size=2)

    if 3 not in sim._db_buffers:
        sim.register_db(3, 1)
    sim.write_db(3, 0, b'\x01')

    logger.info("DBs de teste inicializados: Temperatura@DB1, Pressão@DB2, Bomba@DB3")
