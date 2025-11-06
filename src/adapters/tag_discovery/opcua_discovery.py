"""Descoberta de tags para servidores OPC UA."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import TagDiscovery


class OpcUaTagDiscovery(TagDiscovery):
    """Usa o cliente asyncua para navegar na árvore de nós."""

    async def discover_tags(self, connection_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            from asyncua import Client
            from asyncua.ua import NodeClass
        except ImportError as exc:  # pragma: no cover - depende de pacote externo
            raise RuntimeError(
                "A biblioteca asyncua é necessária para a descoberta OPC UA."
            ) from exc

        endpoint = connection_params.get("endpoint") or connection_params.get("url")
        if not endpoint:
            raise ValueError("Informe 'endpoint' (ex: opc.tcp://host:4840)")

        timeout = connection_params.get("timeout", 10)
        limit = connection_params.get("max_nodes", 2000)
        discovered: List[Dict[str, Any]] = []

        async with Client(url=endpoint, timeout=timeout) as client:
            root = client.nodes.objects

            async def _walk(node, path: List[str]) -> None:
                nonlocal discovered
                if len(discovered) >= limit:
                    return

                browse_name = await node.read_browse_name()
                name = browse_name.Name if browse_name else node.nodeid.to_string()
                current_path = path + [name]

                node_class = await node.read_node_class()
                if node_class == NodeClass.Variable:
                    datatype = await node.read_data_type_as_variant_type()
                    discovered.append(
                        {
                            "display_path": "/".join(current_path),
                            "path": current_path,
                            "node_id": node.nodeid.to_string(),
                            "data_type": str(datatype),
                            "source": "opcua",
                        }
                    )

                children = await node.get_children()
                for child in children:
                    if len(discovered) >= limit:
                        break
                    await _walk(child, current_path)

            await _walk(root, ["Objects"])

        return discovered


__all__ = ["OpcUaTagDiscovery"]
