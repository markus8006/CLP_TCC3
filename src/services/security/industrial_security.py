"""Avaliações de segurança para dispositivos industriais."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class SecurityInsight:
    title: str
    description: str
    severity: str


@dataclass
class SecurityAssessment:
    score: int
    level: str
    highlights: List[SecurityInsight]
    recommendations: List[str]


def _normalize_tags(tags: Iterable[str] | None) -> List[str]:
    normalized: List[str] = []
    if not tags:
        return normalized
    for tag in tags:
        if tag is None:
            continue
        cleaned = str(tag).strip().lower()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def assess_plc_security(plc) -> SecurityAssessment:
    """Gera um relatório simples de segurança industrial para um PLC."""
    score = 100
    highlights: List[SecurityInsight] = []
    recommendations: List[str] = []

    protocol = (plc.protocol or "").lower()
    port = plc.port or 0
    firmware = (plc.firmware_version or "").strip()
    tags = _normalize_tags(getattr(plc, "tags_as_list", lambda: [])()) if hasattr(plc, "tags_as_list") else _normalize_tags(getattr(plc, "tags", []))

    if protocol in {"modbus", "dnp3"}:
        score -= 25
        highlights.append(
            SecurityInsight(
                title="Protocolo sem segurança nativa",
                description="Protocolos como Modbus e DNP3 não implementam autenticação ou criptografia.",
                severity="alto",
            )
        )
        recommendations.append(
            "Coloque o CLP atrás de uma zona DMZ e utilize firewalls industriais para filtrar comandos Modbus." \
            " Considere encapsular o tráfego em túneis VPN."
        )

    if port in {502, 20000, 44818}:
        score -= 10
        highlights.append(
            SecurityInsight(
                title="Porta padrão exposta",
                description="O dispositivo utiliza uma porta padrão conhecida por scanners industriais.",
                severity="médio",
            )
        )
        recommendations.append(
            "Implemente listas de controlo de acesso (ACL) e segmentação de rede para limitar o acesso à porta exposta."
        )

    if not firmware:
        score -= 15
        highlights.append(
            SecurityInsight(
                title="Firmware desconhecido",
                description="Sem versão de firmware registada torna-se difícil avaliar vulnerabilidades conhecidas.",
                severity="médio",
            )
        )
        recommendations.append(
            "Registe a versão de firmware e mantenha inventário actualizado para acompanhar boletins de segurança do fabricante."
        )

    if "critico" in tags or "seguranca" in tags:
        score -= 5
        highlights.append(
            SecurityInsight(
                title="Activo crítico",
                description="Tags indicam que o CLP pertence a um activo crítico da produção.",
                severity="alto",
            )
        )
        recommendations.append(
            "Implemente monitoração contínua (IDS/IPS industrial) e políticas de dupla autenticação para acessos de manutenção."
        )

    if not getattr(plc, "is_online", False):
        score -= 5
        highlights.append(
            SecurityInsight(
                title="Dispositivo offline",
                description="Sem telemetria em tempo real é difícil detectar incidentes ou tampering.",
                severity="médio",
            )
        )
        recommendations.append(
            "Implemente rotinas de teste de comunicação e mantenha evidências de disponibilidade para auditorias."
        )

    score = max(0, min(100, score))
    if score >= 75:
        level = "Baixo"
    elif score >= 50:
        level = "Moderado"
    else:
        level = "Crítico"

    if not recommendations:
        recommendations.append(
            "Realize avaliação periódica de segurança industrial e revise regras de firewall da célula de produção."
        )

    return SecurityAssessment(
        score=score,
        level=level,
        highlights=highlights,
        recommendations=recommendations,
    )
