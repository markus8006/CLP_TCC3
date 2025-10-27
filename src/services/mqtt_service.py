"""Serviço de publicação MQTT para convergência IT/OT.

Este módulo encapsula toda a lógica necessária para publicar dados de
processo, alarmes e eventos de conectividade em um *broker* MQTT.  A
implementação foi desenhada para operar de forma resiliente em ambientes
industriais: utiliza uma fila interna com *backoff* exponencial em caso de
falhas de rede, reconecta automaticamente ao *broker* e garante que chamadas
de alto nível nunca bloqueiem o ciclo de polling do SCADA.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

_PAHO_SPEC = importlib.util.find_spec("paho")
_MQTT_SPEC = importlib.util.find_spec("paho.mqtt.client") if _PAHO_SPEC else None
if TYPE_CHECKING and _MQTT_SPEC:
    from paho.mqtt.client import Client as MqttClient  # type: ignore
else:  # pragma: no cover - fallback para tempo de execução
    MqttClient = Any  # type: ignore

mqtt = importlib.import_module("paho.mqtt.client") if _MQTT_SPEC else None
MQTT_ERR_SUCCESS = getattr(mqtt, "MQTT_ERR_SUCCESS", 0)

from src.utils.logs import logger

if TYPE_CHECKING:  # pragma: no cover - apenas para *type checkers*
    from src.models.Alarms import Alarm, AlarmDefinition
    from src.models.PLCs import PLC


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MqttSettings:
    enabled: bool
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    use_tls: bool
    base_topic: str
    data_topic: str
    alarm_topic: str
    status_topic: str
    client_id: str
    keepalive: int
    qos: int
    retain: bool


def load_mqtt_settings() -> MqttSettings:
    """Lê variáveis de ambiente e devolve as configurações consolidadas."""

    client_id = os.getenv("MQTT_CLIENT_ID") or f"clp-tcc3-{os.getpid()}"
    return MqttSettings(
        enabled=_env_bool("MQTT_ENABLED", default=False),
        host=os.getenv("MQTT_HOST", "localhost"),
        port=_env_int("MQTT_PORT", 1883),
        username=os.getenv("MQTT_USERNAME"),
        password=os.getenv("MQTT_PASSWORD"),
        use_tls=_env_bool("MQTT_TLS", default=False),
        base_topic=os.getenv("MQTT_BASE_TOPIC", "clp_tcc3"),
        data_topic=os.getenv("MQTT_DATA_TOPIC", "telemetry/process"),
        alarm_topic=os.getenv("MQTT_ALARM_TOPIC", "telemetry/alarms"),
        status_topic=os.getenv("MQTT_STATUS_TOPIC", "telemetry/status"),
        client_id=client_id,
        keepalive=_env_int("MQTT_KEEPALIVE", 60),
        qos=_env_int("MQTT_QOS", 1),
        retain=_env_bool("MQTT_RETAIN", default=False),
    )


class MqttPublisherService:
    """Gerencia a publicação assíncrona de mensagens em um broker MQTT."""

    def __init__(self, settings: Optional[MqttSettings] = None):
        self.settings = settings or load_mqtt_settings()
        self._queue: "queue.Queue[Tuple[str, Dict[str, Any]]]" = queue.Queue(
            maxsize=10000
        )
        self._client: Optional[MqttClient] = None
        self._connected = False
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._library_available = mqtt is not None
        self._active = self.settings.enabled and self._library_available

        if self.settings.enabled and not self._library_available:
            logger.warning(
                "Publicação MQTT habilitada mas a biblioteca paho-mqtt não está instalada; recurso será desativado."
            )

        if self._active:
            self._initialise_client()

    # ------------------------------------------------------------------
    # Ciclo de vida do cliente MQTT
    # ------------------------------------------------------------------
    def _initialise_client(self) -> None:
        if mqtt is None:
            self._active = False
            return

        self._client = mqtt.Client(client_id=self.settings.client_id, clean_session=True)
        if self.settings.username:
            self._client.username_pw_set(
                username=self.settings.username, password=self.settings.password
            )
        if self.settings.use_tls:
            self._client.tls_set()

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        self._worker = threading.Thread(
            target=self._run_loop, name="mqtt-publisher", daemon=True
        )
        self._worker.start()

    def _on_connect(self, client: Any, userdata, flags, rc) -> None:  # noqa: D401
        """Callback padrão do Paho MQTT."""

        if rc == MQTT_ERR_SUCCESS:
            logger.info(
                "Conectado ao broker MQTT %s:%s (client_id=%s)",
                self.settings.host,
                self.settings.port,
                self.settings.client_id,
            )
            self._connected = True
        else:
            logger.error("Conexão MQTT retornou código %s", rc)
            self._connected = False

    def _on_disconnect(self, client: Any, userdata, rc) -> None:  # noqa: D401
        """Callback de desconexão do cliente MQTT."""

        self._connected = False
        if rc != MQTT_ERR_SUCCESS and not self._stop_event.is_set():
            logger.warning("Desconexão inesperada do broker MQTT (rc=%s)", rc)

    def _run_loop(self) -> None:
        if self._client is None:
            return

        backoff = 1.0
        while not self._stop_event.is_set():
            if not self._connected:
                try:
                    self._client.connect(
                        host=self.settings.host,
                        port=self.settings.port,
                        keepalive=self.settings.keepalive,
                    )
                    self._client.loop_start()
                    backoff = 1.0
                except Exception:
                    logger.exception(
                        "Falha ao conectar ao broker MQTT %s:%s",
                        self.settings.host,
                        self.settings.port,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
                    continue

            try:
                topic_suffix, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._publish_now(topic_suffix, payload)
            except Exception:
                logger.exception("Erro ao publicar mensagem MQTT; tentativa será repetida")
                self._safe_requeue(topic_suffix, payload)
                self._reset_connection()
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _reset_connection(self) -> None:
        if not self._client:
            return
        with self._lock:
            try:
                if self._connected:
                    self._client.loop_stop()
                    self._client.disconnect()
            except Exception:
                logger.exception("Erro ao finalizar conexão MQTT")
            finally:
                self._connected = False

    def shutdown(self) -> None:
        """Encerra o *worker* e encerra a conexão com o broker."""

        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                logger.exception("Erro ao encerrar cliente MQTT")
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Publicação de alto nível
    # ------------------------------------------------------------------
    def publish_measurements(self, measurements: Iterable[Dict[str, Any]]) -> None:
        if not self._active:
            return

        prepared: List[Dict[str, Any]] = []
        for measurement in measurements:
            if not measurement:
                continue
            prepared.append(self._prepare_measurement(measurement))

        if not prepared:
            return

        payload = {
            "type": "measurement_batch",
            "sent_at": self._now_iso(),
            "source": self.settings.client_id,
            "measurements": prepared,
        }
        self._enqueue(self.settings.data_topic, payload)

    def publish_alarm_event(
        self,
        definition: "AlarmDefinition",
        alarm: "Alarm",
        *,
        state: str,
    ) -> None:
        if not self._active:
            return

        payload = {
            "type": "alarm_event",
            "sent_at": self._now_iso(),
            "source": self.settings.client_id,
            "state": state,
            "alarm": {
                "id": getattr(alarm, "id", None),
                "definition_id": getattr(definition, "id", None),
                "name": getattr(definition, "name", None),
                "message": getattr(alarm, "message", None),
                "priority": getattr(alarm, "priority", None),
                "severity": getattr(definition, "severity", None),
                "trigger_value": getattr(alarm, "trigger_value", None),
                "current_value": getattr(alarm, "current_value", None),
                "triggered_at": self._to_iso(getattr(alarm, "triggered_at", None)),
                "cleared_at": self._to_iso(getattr(alarm, "cleared_at", None)),
            },
            "asset": {
                "plc_id": getattr(alarm, "plc_id", None),
                "register_id": getattr(alarm, "register_id", None),
                "plc_name": self._safe_attr(definition, "plc", "name"),
                "register_name": self._safe_attr(definition, "register", "name"),
                "register_tag": self._safe_attr(definition, "register", "tag"),
            },
        }
        self._enqueue(self.settings.alarm_topic, payload)

    def publish_connectivity_event(self, plc: "PLC", state: str) -> None:
        if not self._active or plc is None:
            return

        payload = {
            "type": "connectivity_event",
            "sent_at": self._now_iso(),
            "source": self.settings.client_id,
            "state": state,
            "plc": {
                "id": getattr(plc, "id", None),
                "name": getattr(plc, "name", None),
                "protocol": getattr(plc, "protocol", None),
                "ip_address": getattr(plc, "ip_address", None),
                "vlan_id": getattr(plc, "vlan_id", None),
                "tags": self._plc_tags(plc),
            },
        }
        self._enqueue(self.settings.status_topic, payload)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _prepare_measurement(self, measurement: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "plc_id": measurement.get("plc_id"),
            "plc_name": measurement.get("plc_name"),
            "protocol": measurement.get("protocol"),
            "plc_tags": measurement.get("plc_tags"),
            "register_id": measurement.get("register_id"),
            "register_name": measurement.get("register_name"),
            "register_tag": measurement.get("register_tag"),
            "register_address": measurement.get("register_address"),
            "poll_rate": measurement.get("poll_rate"),
            "timestamp": self._to_iso(measurement.get("timestamp")),
            "raw_value": measurement.get("raw_value"),
            "value_float": measurement.get("value_float"),
            "value_int": measurement.get("value_int"),
            "unit": measurement.get("unit"),
            "quality": measurement.get("quality"),
            "is_alarm": measurement.get("is_alarm", False),
        }

    def _enqueue(self, topic_suffix: str, payload: Dict[str, Any]) -> None:
        if not self._active:
            return

        item = (topic_suffix, payload)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.warning(
                "Fila de publicação MQTT cheia; descartando mensagem mais antiga"
            )
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(item)

    def _safe_requeue(self, topic_suffix: str, payload: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((topic_suffix, payload))
        except queue.Full:
            logger.warning("Fila MQTT cheia; mensagem descartada após falha de publicação")

    def _publish_now(self, topic_suffix: str, payload: Dict[str, Any]) -> None:
        if not self._active or self._client is None or mqtt is None:
            return
        if not self._connected:
            raise RuntimeError("Cliente MQTT não está conectado")

        topic = self._build_topic(topic_suffix)
        payload_str = json.dumps(payload, default=self._json_default)
        result = self._client.publish(
            topic,
            payload=payload_str,
            qos=self.settings.qos,
            retain=self.settings.retain,
        )
        if result.rc != MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publicação MQTT falhou com código {result.rc}")

    def _build_topic(self, suffix: str) -> str:
        base = (self.settings.base_topic or "").strip("/")
        suffix = (suffix or "").strip("/")
        if base and suffix:
            return f"{base}/{suffix}"
        if base:
            return base
        return suffix

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        raise TypeError(f"Valor {value!r} não serializável em JSON")

    @staticmethod
    def _to_iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return str(value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_attr(obj: Any, relation: str, attr: str) -> Optional[Any]:
        related = getattr(obj, relation, None)
        if related is None:
            return None
        return getattr(related, attr, None)

    @staticmethod
    def _plc_tags(plc: "PLC") -> Optional[List[str]]:
        if plc is None:
            return None
        try:
            if hasattr(plc, "tags_as_list"):
                tags = plc.tags_as_list()
            else:
                tags = getattr(plc, "tags", None)
            if not tags:
                return None
            if isinstance(tags, list):
                return tags
            return list(tags) if isinstance(tags, (set, tuple)) else [str(tags)]
        except Exception:
            logger.exception("Erro ao obter tags do PLC para publicação MQTT")
            return None

    # ------------------------------------------------------------------
    # Propriedades utilitárias
    # ------------------------------------------------------------------
    @property
    def is_enabled(self) -> bool:
        return self._active


_singleton: Optional[MqttPublisherService] = None
_singleton_lock = threading.Lock()


def get_mqtt_publisher() -> MqttPublisherService:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = MqttPublisherService()
    return _singleton


__all__ = [
    "MqttPublisherService",
    "MqttSettings",
    "get_mqtt_publisher",
    "load_mqtt_settings",
]

