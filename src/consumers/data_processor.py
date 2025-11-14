"""Consumidor responsável por processar medições publicadas pelo serviço Go.

A arquitetura desacoplada envia leituras de CLPs para uma fila de mensagens.
Este serviço inscreve-se no tópico de telemetria, executa a lógica de
negócio (alarmes/MQTT) e realiza gravações em lote no banco de dados.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:  # pragma: no cover - dependência opcional
    import redis.asyncio as aioredis
except Exception:  # pragma: no cover - fallback quando Redis não está disponível
    aioredis = None  # type: ignore

from src.app import create_app
from src.app.settings import get_app_settings
from src.repository.Data_repository import DataRepo
from src.repository.PLC_repository import Plcrepo
from src.services.Alarms_service import AlarmService
from src.services.mqtt_service import get_mqtt_publisher
from src.utils.logs import logger

QUEUE_TOPIC = "plc.data"
REDIS_URL_ENV = "PLC_DATA_REDIS_URL"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class RedisSubscriber:
    """Assinante Redis Pub/Sub simples com modo *dry-run* para desenvolvimento."""

    def __init__(self, topic: str, url: Optional[str] = None) -> None:
        self.topic = topic
        self.url = url or DEFAULT_REDIS_URL
        self._client = None
        self._pubsub = None
        self._stop_event = asyncio.Event()

    async def connect(self) -> None:
        if aioredis is None:
            logger.warning(
                "redis.asyncio não está disponível; consumidor rodará em modo simulado sem consumir mensagens."
            )
            return
        self._client = aioredis.from_url(self.url, decode_responses=True)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self.topic)
        logger.info("Assinado tópico Redis %s em %s", self.topic, self.url)

    async def listen(self, handler) -> None:
        if self._pubsub is None:
            await self._listen_dry_run()
            return

        try:
            async for message in self._pubsub.listen():
                if self._stop_event.is_set():
                    break
                if message is None or message.get("type") != "message":
                    continue
                payload = message.get("data")
                await handler(payload)
        finally:
            await self.close()

    async def _listen_dry_run(self) -> None:
        logger.info("Modo dry-run: aguardando mensagens simuladas para o tópico %s", self.topic)
        while not self._stop_event.is_set():
            await asyncio.sleep(1.0)

    async def close(self) -> None:
        self._stop_event.set()
        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.unsubscribe(self.topic)
                await self._pubsub.close()
        if self._client is not None:
            with suppress(Exception):
                await self._client.close()

    def stop(self) -> None:
        self._stop_event.set()


class PLCDataProcessor:
    """Processa mensagens de telemetria e grava dados em lote."""

    def __init__(
        self,
        *,
        batch_size: int = 1000,
        flush_interval: float = 2.0,
        topic: str = QUEUE_TOPIC,
        redis_url: Optional[str] = None,
    ) -> None:
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._batch: List[Dict[str, Any]] = []
        self._batch_lock = asyncio.Lock()
        self._last_flush = time.monotonic()
        self._subscriber = RedisSubscriber(topic=topic, url=redis_url or os.getenv(REDIS_URL_ENV))

        self._app = create_app()
        self._settings = get_app_settings(self._app)
        self._app_ctx = self._app.app_context()
        self._app_ctx.push()

        self._alarm_service = AlarmService()
        self._mqtt = get_mqtt_publisher()
        self._plc_cache: Dict[str, Optional[int]] = {}
        self._allow_persistence = self._settings.features.enable_polling and not (
            self._settings.demo.enabled and self._settings.demo.read_only
        )

    async def start(self) -> None:
        await self._subscriber.connect()
        periodic_task = asyncio.create_task(self._periodic_flush())
        try:
            await self._subscriber.listen(self._on_message)
        except asyncio.CancelledError:  # pragma: no cover - cancelamento esperado
            raise
        finally:
            periodic_task.cancel()
            with suppress(asyncio.CancelledError):
                await periodic_task
            await self.flush(force=True)
            await self._subscriber.close()

    async def _periodic_flush(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.flush_interval)
                await self.flush(force=True)
        except asyncio.CancelledError:  # pragma: no cover - cancelamento esperado
            return

    async def _on_message(self, raw_message: Any) -> None:
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        if not raw_message:
            return
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.error("Mensagem inválida recebida da fila: %s", raw_message)
            return

        records = self._process_payload(payload)
        if not records:
            return

        async with self._batch_lock:
            self._batch.extend(records)
        await self.flush()

    def _process_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        key = payload.get("key")
        timestamp = self._parse_timestamp(payload.get("timestamp"))
        values = payload.get("values")
        if not isinstance(values, Iterable):
            logger.debug("Payload sem lista de valores: %s", payload)
            return []

        processed: List[Dict[str, Any]] = []
        publish_payloads: List[Dict[str, Any]] = []

        for item in values:
            if not isinstance(item, dict):
                continue

            plc_id = item.get("plc_id")
            if plc_id is None:
                plc_id = self._resolve_plc_id(key)
            register_id = item.get("register_id")
            if plc_id is None or register_id is None:
                logger.debug(
                    "Descartando leitura sem identificação completa (plc_id=%s, register_id=%s)",
                    plc_id,
                    register_id,
                )
                continue

            record_ts = self._parse_timestamp(item.get("timestamp")) if item.get("timestamp") else timestamp
            value_float = self._extract_value(item)

            triggered = False
            try:
                triggered = self._alarm_service.check_and_handle(plc_id, register_id, value_float)
            except Exception:
                logger.exception(
                    "Erro ao processar AlarmService para plc=%s register=%s",
                    plc_id,
                    register_id,
                )

            record: Dict[str, Any] = {
                "plc_id": plc_id,
                "register_id": register_id,
                "timestamp": record_ts,
                "raw_value": item.get("raw_value"),
                "value_float": value_float,
                "value_int": item.get("value_int"),
                "quality": item.get("quality"),
                "unit": item.get("unit"),
                "tags": item.get("tags"),
            }
            if triggered:
                record["is_alarm"] = True
                item["is_alarm"] = True

            publish_payloads.append(
                {
                    "plc_id": plc_id,
                    "register_id": register_id,
                    "value": value_float,
                    "timestamp": record_ts.isoformat() if isinstance(record_ts, datetime) else record_ts,
                    "quality": item.get("quality"),
                    "unit": item.get("unit"),
                    "tags": item.get("tags"),
                    "is_alarm": item.get("is_alarm"),
                }
            )
            processed.append(record)

        if publish_payloads:
            try:
                self._mqtt.publish_measurements(publish_payloads)
            except Exception:
                logger.exception("Erro ao publicar medições no MQTT")

        return processed

    async def flush(self, *, force: bool = False) -> None:
        async with self._batch_lock:
            if not self._batch:
                return
            should_flush = force or len(self._batch) >= self.batch_size or (
                time.monotonic() - self._last_flush
            ) >= self.flush_interval
            if not should_flush:
                return
            batch = self._batch
            self._batch = []

        if not self._allow_persistence:
            logger.debug(
                "Persistência de DataLog desativada; descartando %d registros",
                len(batch),
            )
            return

        try:
            DataRepo.bulk_insert(batch)
        except Exception:
            logger.exception("Erro ao executar bulk_insert no DataLogRepo")
            # Reinsere o batch para tentativa futura
            async with self._batch_lock:
                batch.extend(self._batch)
                self._batch = batch
            await asyncio.sleep(0)
            return
        finally:
            self._last_flush = time.monotonic()

    def shutdown(self) -> None:
        self._subscriber.stop()
        if self._app_ctx is not None:
            self._app_ctx.pop()

    def _resolve_plc_id(self, key: Optional[str]) -> Optional[int]:
        if not key:
            return None
        cached = self._plc_cache.get(key)
        if cached is not None:
            return cached

        ip, _, vlan_raw = key.partition("|")
        try:
            vlan_id = int(vlan_raw) if vlan_raw else None
        except ValueError:
            vlan_id = None
        if vlan_id == 0:
            vlan_id = None

        plc = Plcrepo.get_by_ip(ip, vlan_id)
        plc_id = getattr(plc, "id", None)
        self._plc_cache[key] = plc_id
        return plc_id

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            cleaned = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                return datetime.now(timezone.utc)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_value(item: Dict[str, Any]) -> Optional[float]:
        value = item.get("value_float")
        if value is not None:
            return value
        raw_value = item.get("value")
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        return None


async def main() -> None:
    processor = PLCDataProcessor()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_stop() -> None:
        stop_event.set()
        processor.shutdown()

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _handle_stop)
        except NotImplementedError:  # pragma: no cover - Windows
            pass

    worker = asyncio.create_task(processor.start())

    await stop_event.wait()
    if not worker.done():
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


if __name__ == "__main__":  # pragma: no cover - ponto de entrada do serviço
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
