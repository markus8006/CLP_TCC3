"""Ferramentas de descoberta de rede com foco em dispositivos industriais."""

from __future__ import annotations

import os
import ipaddress
import json
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    import netifaces
except Exception:  # pragma: no cover - dependente de ambiente
    netifaces = None

import psutil
from scapy.all import (
    sniff,
    srp,
    sr,
    Ether,
    ARP,
    IP,
    ICMP,
    conf,
    get_if_list,
    get_if_addr,
)

from src.utils.logs import logger

# ---------------------------------------------------------------------------
# Caminhos de saída e configuração base
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DISCOVERY_DIR = PROJECT_ROOT / "data" / "discovery"
DISCOVERY_FILE = DISCOVERY_DIR / "enhanced_discovery.json"
DISCOVERY_SUMMARY_FILE = DISCOVERY_DIR / "enhanced_discovery_summary.json"


def has_network_privileges() -> bool:
    """Avalia se o processo possui privilégios administrativos para sniffing/ARP."""
    try:
        return os.geteuid() == 0
    except AttributeError:  # pragma: no cover - ambientes sem geteuid
        if os.name == "nt":
            try:
                import ctypes

                return bool(ctypes.windll.shell32.IsUserAnAdmin())
            except Exception:
                return False
        return True


@dataclass
class DiscoveryConfig:
    """Configuração centralizada para descoberta de rede"""

    MODBUS_PORTS: Optional[List[int]] = None
    SIEMENS_PORTS: Optional[List[int]] = None
    ROCKWELL_PORTS: Optional[List[int]] = None
    SCHNEIDER_PORTS: Optional[List[int]] = None
    OPCUA_PORTS: Optional[List[int]] = None
    COMMON_INDUSTRIAL_PORTS: Optional[List[int]] = None

    BASE_PASSIVE_TIMEOUT: int = 30
    BASE_ARP_TIMEOUT: int = 3
    BASE_ICMP_TIMEOUT: int = 2
    BASE_TCP_TIMEOUT: float = 1.0

    MAX_WORKERS_PER_INTERFACE: int = 8
    MAX_TOTAL_WORKERS: int = 32

    USE_NMAP: bool = True
    NMAP_TIMEOUT_BASE: int = 300
    NMAP_INTENSITY: int = 0

    CACHE_DURATION_SECONDS: int = 300
    ENABLE_CACHE: bool = True

    def __post_init__(self) -> None:
        if self.MODBUS_PORTS is None:
            self.MODBUS_PORTS = [502, 1502]
        if self.SIEMENS_PORTS is None:
            self.SIEMENS_PORTS = [102, 135, 161, 80, 443, 8080]
        if self.ROCKWELL_PORTS is None:
            self.ROCKWELL_PORTS = [44818, 2222, 5555, 1911]
        if self.SCHNEIDER_PORTS is None:
            self.SCHNEIDER_PORTS = [502, 80, 443, 161, 1024, 1025]
        if self.OPCUA_PORTS is None:
            self.OPCUA_PORTS = [4840, 48400, 48401, 48402]
        if self.COMMON_INDUSTRIAL_PORTS is None:
            self.COMMON_INDUSTRIAL_PORTS = list(
                set(
                    self.MODBUS_PORTS
                    + self.SIEMENS_PORTS
                    + self.ROCKWELL_PORTS
                    + self.SCHNEIDER_PORTS
                    + self.OPCUA_PORTS
                    + [20000, 20001, 20002, 161, 162, 23, 21, 80, 443]
                )
            )


CONFIG = DiscoveryConfig()


@dataclass
class NetworkInterface:
    """Representa uma interface de rede com suas propriedades."""

    name: str
    ip: str
    netmask: str
    network: str
    broadcast: Optional[str]
    mac: Optional[str]
    is_up: bool
    is_physical: bool
    interface_type: str
    mtu: Optional[int]


# ---------------------------------------------------------------------------
# Detecção de interfaces
# ---------------------------------------------------------------------------
def get_all_network_interfaces() -> List[NetworkInterface]:
    """Detecta todas as interfaces de rede activas."""

    interfaces: List[NetworkInterface] = []
    try:
        if netifaces:
            for iface_name in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(iface_name)
                    if netifaces.AF_INET not in addrs:
                        continue

                    ipv4_info = addrs[netifaces.AF_INET][0]
                    ip = ipv4_info.get("addr")
                    netmask = ipv4_info.get("netmask")
                    if not ip or not netmask:
                        continue

                    if ip.startswith("127.") or ip == "0.0.0.0":
                        continue

                    try:
                        network_obj = ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
                        network = str(network_obj)
                    except ValueError:
                        continue

                    mac = None
                    if netifaces.AF_LINK in addrs:
                        mac = addrs[netifaces.AF_LINK][0].get("addr")

                    is_physical = not any(
                        marker in iface_name.lower()
                        for marker in ["virt", "docker", "br-", "veth", "lo", "tun", "tap"]
                    )
                    interface_type = _determine_interface_type(iface_name)

                    is_up = True
                    try:
                        stats = psutil.net_if_stats().get(iface_name)
                        if stats:
                            is_up = stats.isup
                    except Exception:
                        pass

                    interfaces.append(
                        NetworkInterface(
                            name=iface_name,
                            ip=ip,
                            netmask=netmask,
                            network=network,
                            broadcast=ipv4_info.get("broadcast"),
                            mac=mac,
                            is_up=is_up,
                            is_physical=is_physical,
                            interface_type=interface_type,
                            mtu=None,
                        )
                    )

                    logger.debug(
                        "Interface detectada: %s - %s/%s (%s)",
                        iface_name,
                        ip,
                        netmask,
                        network,
                    )
                except Exception as exc:  # pragma: no cover - defensivo
                    logger.debug("Erro processando interface %s: %s", iface_name, exc)
                    continue
        else:
            interfaces = _fallback_interface_detection()
    except Exception as exc:  # pragma: no cover - defensivo
        logger.error("Erro na detecção de interfaces: %s", exc)
        interfaces = _fallback_interface_detection()

    logger.info("Total de interfaces detectadas: %d", len(interfaces))
    return interfaces


def _determine_interface_type(iface_name: str) -> str:
    name_lower = iface_name.lower()
    if any(token in name_lower for token in ["eth", "ens", "enp"]):
        return "ethernet"
    if any(token in name_lower for token in ["wifi", "wlan", "wireless"]):
        return "wireless"
    if any(token in name_lower for token in ["docker", "br-"]):
        return "bridge"
    if any(token in name_lower for token in ["veth", "virt"]):
        return "virtual"
    if any(token in name_lower for token in ["tun", "tap"]):
        return "tunnel"
    if any(token in name_lower for token in ["lo", "loopback"]):
        return "loopback"
    return "unknown"


def _fallback_interface_detection() -> List[NetworkInterface]:
    interfaces: List[NetworkInterface] = []
    try:
        for iface in get_if_list():
            try:
                ip = get_if_addr(iface)
                if not ip or ip.startswith("127.") or ip == "0.0.0.0":
                    continue
                network = str(ipaddress.ip_network(f"{ip}/24", strict=False))
                interfaces.append(
                    NetworkInterface(
                        name=iface,
                        ip=ip,
                        netmask="255.255.255.0",
                        network=network,
                        broadcast=None,
                        mac=None,
                        is_up=True,
                        is_physical=True,
                        interface_type="unknown",
                        mtu=None,
                    )
                )
            except Exception:
                continue
    except Exception:  # pragma: no cover - defensivo
        pass
    return interfaces


# ---------------------------------------------------------------------------
# Timeouts adaptativos
# ---------------------------------------------------------------------------
def calculate_adaptive_timeouts(network_size: int) -> Dict[str, Union[int, float]]:
    size_multiplier = max(1.0, network_size / 256)
    return {
        "passive": min(CONFIG.BASE_PASSIVE_TIMEOUT * size_multiplier, 120),
        "arp": min(CONFIG.BASE_ARP_TIMEOUT * size_multiplier, 10),
        "icmp": min(CONFIG.BASE_ICMP_TIMEOUT * size_multiplier, 5),
        "tcp": min(CONFIG.BASE_TCP_TIMEOUT * size_multiplier, 3.0),
        "nmap": min(CONFIG.NMAP_TIMEOUT_BASE * size_multiplier, 900),
    }


# ---------------------------------------------------------------------------
# Descoberta passiva
# ---------------------------------------------------------------------------
def discover_passively_all_interfaces(
    interfaces: List[NetworkInterface],
    timeout: int = CONFIG.BASE_PASSIVE_TIMEOUT,
) -> Dict[str, Set[str]]:
    if not has_network_privileges():
        logger.warning("Permissões insuficientes para sniff passivo completo")
        return {}

    logger.info(
        "Iniciando descoberta passiva em %d interfaces por %ds",
        len(interfaces),
        timeout,
    )

    results: Dict[str, Set[str]] = {}
    threads: List[threading.Thread] = []

    def _sniff_interface(interface: NetworkInterface) -> None:
        seen_ips: Set[str] = set()

        def _packet_handler(pkt):
            try:
                if pkt.haslayer(ARP):
                    ip_src = pkt[ARP].psrc
                    if not ip_src.startswith("127."):
                        seen_ips.add(ip_src)
                elif pkt.haslayer(IP):
                    ip_src = pkt[IP].src
                    if not ip_src.startswith("127."):
                        seen_ips.add(ip_src)
            except Exception:
                pass

        try:
            sniff(
                iface=interface.name,
                store=0,
                prn=_packet_handler,
                timeout=timeout,
                filter="arp or icmp or tcp",
            )
        except Exception as exc:  # pragma: no cover - dependente de SO
            logger.debug("Erro no sniff da interface %s: %s", interface.name, exc)

        results[interface.name] = seen_ips
        logger.debug(
            "Interface %s: %d IPs detectados passivamente",
            interface.name,
            len(seen_ips),
        )

    for iface in interfaces:
        if iface.is_up:
            thread = threading.Thread(target=_sniff_interface, args=(iface,))
            thread.daemon = True
            thread.start()
            threads.append(thread)

    for thread in threads:
        thread.join(timeout + 5)

    total_ips = sum(len(ips) for ips in results.values())
    logger.info(
        "Descoberta passiva concluída: %d IPs únicos em %d interfaces",
        total_ips,
        len(results),
    )

    return results


# ---------------------------------------------------------------------------
# Detecção de dispositivos industriais
# ---------------------------------------------------------------------------
def detect_industrial_device(ip: str, open_ports: Dict[int, Any]) -> Dict[str, Any]:
    device_info = {
        "type": "unknown",
        "manufacturer": "unknown",
        "protocol": [],
        "confidence": 0,
    }

    confidence = 0
    protocols: List[str] = []
    manufacturer = "unknown"
    device_type = "network_device"

    for port in open_ports.keys():
        if port in CONFIG.MODBUS_PORTS:
            protocols.append("modbus")
            confidence += 30
            device_type = "plc"
        elif port in [102, 80, 443] and 102 in open_ports:
            protocols.append("s7")
            manufacturer = "siemens"
            confidence += 25
            device_type = "plc"
        elif port in CONFIG.ROCKWELL_PORTS:
            protocols.append("ethernet_ip")
            manufacturer = "rockwell"
            confidence += 25
            device_type = "plc"
        elif port in CONFIG.OPCUA_PORTS:
            protocols.append("opcua")
            confidence += 20
            device_type = "plc"
        elif port in [161, 162]:
            protocols.append("snmp")
            confidence += 15
        elif port in [80, 443, 8080] and device_type != "unknown":
            protocols.append("http")
            confidence += 10

    if 502 in open_ports and (80 in open_ports or 443 in open_ports):
        confidence += 20
        device_type = "modbus_plc"

    if 102 in open_ports and 80 in open_ports:
        confidence += 25
        manufacturer = "siemens"
        device_type = "siemens_plc"

    device_info.update(
        {
            "type": device_type,
            "manufacturer": manufacturer,
            "protocol": protocols,
            "confidence": min(confidence, 100),
        }
    )
    return device_info


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
def run_enhanced_discovery(
    target_interfaces: Optional[List[str]] = None,
    passive_timeout: Optional[int] = None,
    use_cache: bool = CONFIG.ENABLE_CACHE,
    save_detailed: bool = True,
) -> List[Dict[str, Any]]:
    if not has_network_privileges():
        logger.error("Permissões insuficientes - execute como root/administrador")
        return []

    start_time = time()
    logger.info("=== INICIANDO DESCOBERTA AVANÇADA DE REDE ===")

    all_interfaces = get_all_network_interfaces()
    if target_interfaces:
        all_interfaces = [iface for iface in all_interfaces if iface.name in target_interfaces]

    if not all_interfaces:
        logger.error("Nenhuma interface de rede válida encontrada")
        return []

    total_network_size = sum(
        ipaddress.ip_network(iface.network).num_addresses for iface in all_interfaces
    )
    timeouts = calculate_adaptive_timeouts(total_network_size)

    logger.info("Interfaces ativas: %d", len(all_interfaces))
    logger.info("Tamanho total da rede: ~%d IPs possíveis", total_network_size)
    logger.info("Timeouts calculados: %s", timeouts)

    passive_results = discover_passively_all_interfaces(
        all_interfaces,
        int(passive_timeout or timeouts["passive"]),
    )

    all_discovered_ips: Set[str] = set()
    interface_mapping: Dict[str, NetworkInterface] = {}

    for interface in all_interfaces:
        passive_ips = passive_results.get(interface.name, set())
        for ip in passive_ips:
            all_discovered_ips.add(ip)
            interface_mapping[ip] = interface

    logger.info("Iniciando ARP scan paralelo por interface...")
    all_devices: Dict[str, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(all_interfaces))) as executor:
        arp_futures = {
            executor.submit(_enhanced_arp_scan, interface, timeouts["arp"]): interface
            for interface in all_interfaces
        }

        for future in as_completed(arp_futures):
            interface = arp_futures[future]
            try:
                devices = future.result()
                for device in devices:
                    ip = device["ip"]
                    all_devices[ip] = device
                    all_discovered_ips.add(ip)
                    if ip not in interface_mapping:
                        interface_mapping[ip] = interface
            except Exception as exc:  # pragma: no cover - defensivo
                logger.error("Erro no ARP scan da interface %s: %s", interface.name, exc)

    logger.info(
        "Total de IPs únicos descobertos até agora: %d",
        len(all_discovered_ips),
    )

    alive_ips: Set[str] = set()
    ip_list = list(all_discovered_ips)
    ip_chunks = [ip_list[i : i + 50] for i in range(0, len(ip_list), 50)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        icmp_futures = [executor.submit(icmp_ping_sweep, chunk, timeouts["icmp"]) for chunk in ip_chunks]
        for future in as_completed(icmp_futures):
            try:
                chunk_alive = future.result()
                alive_ips.update(chunk_alive)
            except Exception as exc:  # pragma: no cover - defensivo
                logger.debug("Erro no ICMP sweep: %s", exc)

    logger.info("Iniciando port scan em %d IPs...", len(all_discovered_ips))
    with ThreadPoolExecutor(max_workers=CONFIG.MAX_TOTAL_WORKERS) as executor:
        port_futures = {
            executor.submit(_enhanced_port_scan, ip, timeouts): ip for ip in all_discovered_ips
        }
        for future in as_completed(port_futures):
            ip = port_futures[future]
            try:
                port_results = future.result()
                if ip not in all_devices:
                    iface = interface_mapping.get(ip)
                    all_devices[ip] = {
                        "ip": ip,
                        "mac": None,
                        "interface": iface.name if iface else None,
                        "network": iface.network if iface else None,
                        "discovered_via": [],
                    }

                all_devices[ip].update(port_results)
                if port_results.get("open_ports"):
                    industrial_info = detect_industrial_device(ip, port_results["open_ports"])
                    all_devices[ip]["industrial_device"] = industrial_info
            except Exception as exc:  # pragma: no cover - defensivo
                logger.debug("Erro no port scan de %s: %s", ip, exc)

    final_devices: List[Dict[str, Any]] = []
    for ip, device in all_devices.items():
        device["responds_to_ping"] = ip in alive_ips
        device.setdefault("discovered_via", [])
        device.setdefault("open_ports", {})
        device.setdefault("services", {})
        final_devices.append(device)

    final_devices = _safe_ip_sort(final_devices)

    elapsed = time() - start_time
    logger.info("=== DESCOBERTA CONCLUÍDA ===")
    logger.info("Tempo total: %.2fs", elapsed)
    logger.info("Dispositivos encontrados: %d", len(final_devices))
    logger.info(
        "Dispositivos industriais: %d",
        sum(1 for device in final_devices if device.get("industrial_device", {}).get("confidence", 0) > 50),
    )

    _save_discovery_results(final_devices, save_detailed)
    return final_devices


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def _enhanced_arp_scan(interface: NetworkInterface, timeout: int) -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    try:
        logger.debug("ARP scan na interface %s - rede %s", interface.name, interface.network)
        arp = ARP(pdst=interface.network)
        ether = Ether(dst="ff:ff:ff:ff:ff:ff")
        answered, _ = srp(ether / arp, timeout=timeout, verbose=0, iface=interface.name)
        for _, rcv in answered:
            devices.append(
                {
                    "ip": rcv.psrc,
                    "mac": rcv.hwsrc,
                    "interface": interface.name,
                    "network": interface.network,
                    "discovered_via": ["arp"],
                    "timestamp": time(),
                }
            )
        logger.debug("Interface %s: %d dispositivos via ARP", interface.name, len(devices))
    except Exception as exc:  # pragma: no cover - dependente de SO
        logger.debug("Erro no ARP scan da interface %s: %s", interface.name, exc)
    return devices


def _enhanced_port_scan(ip: str, timeouts: Dict[str, Union[int, float]]) -> Dict[str, Any]:
    result = {"open_ports": {}, "services": {}, "scan_time": time()}
    quick_results = tcp_probe(ip, CONFIG.COMMON_INDUSTRIAL_PORTS, timeouts["tcp"])
    open_ports = [port for port, is_open in quick_results.items() if is_open]

    if open_ports:
        result["open_ports"] = {port: {"state": "open", "method": "tcp_connect"} for port in open_ports}
        for port in open_ports[:5]:
            service_info = _identify_service(ip, port)
            if service_info:
                result["services"][port] = service_info

    return result


def _identify_service(ip: str, port: int) -> Optional[Dict[str, str]]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect((ip, port))
            if port == 502:
                return {"name": "modbus", "protocol": "tcp", "type": "industrial"}
            if port == 102:
                return {"name": "s7comm", "protocol": "tcp", "type": "industrial"}
            if port in [80, 443, 8080]:
                return {"name": "http", "protocol": "tcp", "type": "web"}
            if port == 4840:
                return {"name": "opcua", "protocol": "tcp", "type": "industrial"}
            return {"name": "unknown", "protocol": "tcp", "type": "unknown"}
    except Exception:  # pragma: no cover - dependente de SO
        return None


def _save_discovery_results(devices: List[Dict[str, Any]], detailed: bool = True) -> None:
    try:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(DISCOVERY_DIR),
            encoding="utf-8",
        ) as temp_file:
            json.dump(devices, temp_file, indent=2, ensure_ascii=False)
            temp_name = temp_file.name
        os.replace(temp_name, DISCOVERY_FILE)
        logger.info("Resultados salvos em: %s", DISCOVERY_FILE)

        if detailed:
            summary: List[Dict[str, Any]] = []
            for device in devices:
                industrial = device.get("industrial_device", {})
                open_ports = device.get("open_ports", {})
                try:
                    port_list = sorted(int(port) for port in open_ports.keys())
                except Exception:
                    port_list = list(open_ports.keys())
                summary.append(
                    {
                        "ip": device.get("ip"),
                        "mac": device.get("mac"),
                        "responds_to_ping": device.get("responds_to_ping", False),
                        "open_ports": port_list,
                        "is_industrial": industrial.get("confidence", 0) > 50,
                        "device_type": industrial.get("type", "unknown"),
                        "manufacturer": industrial.get("manufacturer", "unknown"),
                    }
                )
            with DISCOVERY_SUMMARY_FILE.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2, ensure_ascii=False)
            logger.info("Resumo salvo em: %s", DISCOVERY_SUMMARY_FILE)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.error("Erro ao salvar resultados: %s", exc)


def _safe_ip_sort(devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        return sorted(devices, key=lambda item: ipaddress.ip_address(item.get("ip", "0.0.0.0")))
    except Exception:
        return devices


def icmp_ping_sweep(ip_list: List[str], timeout: int = 2) -> Set[str]:
    alive: Set[str] = set()
    if not ip_list:
        return alive
    try:
        packets = IP(dst=ip_list) / ICMP()
        answered, _ = sr(packets, timeout=timeout, verbose=0)
        for _, rcv in answered:
            alive.add(rcv.src)
    except Exception as exc:  # pragma: no cover - dependente de SO
        logger.debug("Erro no ICMP sweep: %s", exc)
    return alive


def tcp_probe(ip: str, ports: List[int], timeout: float = 1.0) -> Dict[int, bool]:
    results: Dict[int, bool] = {}
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((ip, port))
                results[port] = result == 0
        except Exception:
            results[port] = False
    return results


def run_full_discovery(**kwargs: Any) -> List[Dict[str, Any]]:
    return run_enhanced_discovery(**kwargs)


if __name__ == "__main__":
    print("=== SISTEMA DE DESCOBERTA DE REDE MELHORADO ===")
    devices = run_enhanced_discovery()
    if devices:
        print("\n✅ Descoberta concluída com sucesso!")
        print(f"📊 Total de dispositivos: {len(devices)}")
        industrial_count = sum(
            1 for device in devices if device.get("industrial_device", {}).get("confidence", 0) > 50
        )
        print(f"🏭 Dispositivos industriais detectados: {industrial_count}")
        interfaces = {device.get("interface") for device in devices if device.get("interface")}
        print(f"🔌 Interfaces utilizadas: {', '.join(sorted(interfaces)) if interfaces else 'N/A'}")
    else:
        print("❌ Nenhum dispositivo encontrado ou erro na execução")
