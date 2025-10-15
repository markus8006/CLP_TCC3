# run_mini_simple.py
import asyncio
import time
import socket
import logging
from typing import Dict, List, Any, Optional
from src.utils.logs import logger
from src.adapters.modbus_adapter import ModbusAdapter


# ---------- util: espera porta tcp abrir ----------
def wait_for_port(host: str, port: int, timeout: float = 8.0, interval: float = 0.2) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except Exception:
            time.sleep(interval)
    return False


# ---------- Active client (async) que mantém uma conexão por PLC ----------
class ActivePLCPoller:
    def __init__(self, plc_cfg: Any, registers_provider : Any):
        """
        plc_cfg: {'ip','port','unit','vlan','poll_interval','plc_id'}
        registers_provider: callable (sync or async) -> list of register dicts
        """
        self.plc_cfg = plc_cfg
        self.registers_provider = registers_provider
        self._task: Optional[asyncio.Task] = None
        self._stop = False
        self._backoff = 1.0

    def _key(self) -> str:
        return f"{self.plc_cfg['ip']}|{self.plc_cfg.get('vlan') or 0}"

    async def start(self):
        self._stop = False
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._stop = True
        if self._task:
            await self._task
            self._task = None

    async def _run_loop(self):
        ip = getattr(self.plc_cfg, "ip_address")
        port = int(getattr(self.plc_cfg, "port", 5020))
        unit = int(getattr(self.plc_cfg, "unit", 1))
        poll_interval = float(getattr(self.registers_provider, "poll_rate", 1000))
        logger.info("PLCPoller starting for %s:%s (unit=%s)", ip, port, unit)

        loop = asyncio.get_running_loop()
        self._wrapper = ModbusSyncWrapper(ip, port=port, unit=unit, timeout=3.0)

        while not self._stop:
            try:
                # connect (in executor)
                ok = await loop.run_in_executor(None, self._wrapper.connect)
                if not ok:
                    logger.warning("Unable to connect to %s:%s -- retrying in %.1fs", ip, port, self._backoff)
                    await asyncio.sleep(self._backoff)
                    self._backoff = min(self._backoff * 2, 30.0)
                    continue
                # connected - reset backoff
                self._backoff = 1.0

                # get registers (support sync/async provider)
                if asyncio.iscoroutinefunction(self.registers_provider):
                    regs = await self.registers_provider()
                else:
                    regs = self.registers_provider()

                if not regs:
                    logger.debug("No registers for plc %s", self._key())
                    await asyncio.sleep(poll_interval)
                    continue

                batch = []
                now_ts = time.time()
                # read registers sequentially (you can optimize grouping later)
                for r in regs:
                    try:
                        # perform blocking read in executor
                        resp = await loop.run_in_executor(None, self._wrapper.read_register, r)
                        rec = {
                            "plc_id": self.plc_cfg.get("plc_id"),
                            "register_id": r.get("id"),
                            "timestamp": now_ts,
                            "raw_value": resp.get("raw"),
                            "value": resp.get("value"),
                            "quality": resp.get("quality")
                        }
                        batch.append(rec)
                    except Exception:
                        logger.exception("Error reading register %s for plc %s", r, self._key())

                # persist batch (repo likely sync) -> run in executor
                if batch:
                    await loop.run_in_executor(None, self.repo.bulk_insert, batch)

                # sleep poll interval (cooperative)
                await asyncio.sleep(poll_interval)

            except Exception:
                logger.exception("Unexpected error in poll loop for %s", self._key())
                # close client and backoff
                try:
                    await loop.run_in_executor(None, self._wrapper.close)
                except Exception:
                    pass
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)

        # cleanup
        try:
            await loop.run_in_executor(None, self._wrapper.close)
        except Exception:
            pass
        logger.info("PLCPoller stopped for %s", self._key())

# ---------- Simple manager that keeps pollers by key (ip|vlan) ----------
class SimpleManager:
    def __init__(self):
        self._pollers: Dict[str, ActivePLCPoller] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def make_key(ip: str, vlan: Optional[int]) -> str:
        return f"{ip}|{vlan or 0}"

    async def add_plc(self, plc_cfg: Dict[str, Any], registers_provider, datalog_repo: DummyDataLogRepo):
        key = self.make_key(plc_cfg["ip"], plc_cfg.get("vlan"))
        async with self._lock:
            if key in self._pollers:
                logger.info("PLC already managed: %s", key)
                return self._pollers[key]
            poller = ActivePLCPoller(plc_cfg, registers_provider, datalog_repo)
            self._pollers[key] = poller
            await poller.start()
            logger.info("Added plc poller %s", key)
            return poller

    async def remove_plc(self, ip: str, vlan: Optional[int] = None):
        key = self.make_key(ip, vlan)
        async with self._lock:
            p = self._pollers.pop(key, None)
        if p:
            await p.stop()
            logger.info("Removed plc poller %s", key)
            return True
        return False

    async def shutdown(self):
        async with self._lock:
            pollers = list(self._pollers.values())
            self._pollers.clear()
        await asyncio.gather(*(p.stop() for p in pollers), return_exceptions=True)
        logger.info("Manager shutdown complete")

# ---------- example registers provider (replace by DB repo call) ----------
def example_registers_provider() -> List[Dict[str, Any]]:
    # returns minimal register definitions for reading
    return [
        {"id": 1, "address": 0, "register_type": "holding", "data_type": "int16"},
        {"id": 2, "address": 1, "register_type": "holding", "data_type": "int16"},
    ]

# ---------- main example ----------
async def main():
    mgr = SimpleManager()
    repo = DummyDataLogRepo()

    plc_cfg = {
        "ip": "127.0.0.1",
        "port": 5020,
        "unit": 1,
        "vlan": None,
        "poll_interval": 1.0,
        "plc_id": 1,
    }

    # wait for simulator (optional)
    if not wait_for_port(plc_cfg["ip"], plc_cfg["port"], timeout=6.0):
        logger.warning("Modbus server not listening yet at %s:%s - continuing (you may start simulator)", plc_cfg["ip"], plc_cfg["port"])

    # add PLC (starts polling task)
    await mgr.add_plc(plc_cfg, example_registers_provider, repo)

    # let it run for some seconds
    await asyncio.sleep(8)

    # shutdown
    await mgr.shutdown()
    logger.info("Stored datalogs: %s", repo.rows)

if __name__ == "__main__":
    asyncio.run(main())
