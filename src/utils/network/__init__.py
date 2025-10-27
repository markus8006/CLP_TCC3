"""Utilidades para descoberta de rede."""

from .enhanced_discovery import (
    DISCOVERY_DIR,
    DISCOVERY_FILE,
    DISCOVERY_SUMMARY_FILE,
    has_network_privileges,
    run_enhanced_discovery,
    run_full_discovery,
)

__all__ = [
    "DISCOVERY_DIR",
    "DISCOVERY_FILE",
    "DISCOVERY_SUMMARY_FILE",
    "has_network_privileges",
    "run_enhanced_discovery",
    "run_full_discovery",
]
