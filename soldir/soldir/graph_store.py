from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from graphqlite import Graph

from soldir.models import (
    EDGE_HAS_COMMUNICATED_WITH,
    EDGE_IS_REACHABLE_BY,
    EDGE_LABELS,
    CheckInPayload,
    NetworkEdge,
    normalize_edge_type,
    os_code_for,
    utc_now_iso,
)


def _clean_props(props: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in props.items() if value is not None}


class GraphStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.graph = Graph(str(db_path), namespace="soldir")

    def upsert_checkin(self, checkin: CheckInPayload) -> dict[str, Any]:
        with self._lock:
            now = checkin.checked_at or utc_now_iso()
            node_id = checkin.node_id
            self._upsert_instance(
                node_id,
                hostname=checkin.hostname,
                os_name=checkin.os,
                os_code=checkin.os_code,
                arch=checkin.arch,
                target_triple=checkin.target_triple,
                ip_addresses=checkin.ip_addresses,
                last_seen=now,
                metadata=checkin.metadata,
                status="online",
            )

            for peer in checkin.communicated_with:
                self._upsert_placeholder(peer, now)
                self._upsert_network_edge(
                    NetworkEdge(
                        source=node_id,
                        target=peer,
                        type=EDGE_HAS_COMMUNICATED_WITH,
                    ),
                    now,
                )

            for peer in checkin.reachable_by:
                self._upsert_placeholder(peer, now)
                self._upsert_network_edge(
                    NetworkEdge(
                        source=peer,
                        target=node_id,
                        type=EDGE_IS_REACHABLE_BY,
                    ),
                    now,
                )

            for edge in checkin.edges:
                source = edge.source or node_id
                self._upsert_placeholder(source, now)
                self._upsert_placeholder(edge.target, now)
                self._upsert_network_edge(
                    NetworkEdge(
                        source=source,
                        target=edge.target,
                        type=edge.type,
                        protocol=edge.protocol,
                        port=edge.port,
                        metadata=edge.metadata,
                    ),
                    now,
                )

            self._commit()
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            raw_nodes = self.graph.get_all_nodes(label="Instance")
            raw_edges = self.graph.get_all_edges()

        nodes = [self._normalize_node(node) for node in raw_nodes]
        links = [
            normalized
            for edge in raw_edges
            if (normalized := self._normalize_edge(edge)) is not None
        ]
        nodes.sort(key=lambda node: node["hostname"])
        links.sort(key=lambda link: (link["source"], link["target"], link["type"]))
        return {"nodes": nodes, "links": links}

    def _upsert_instance(
        self,
        node_id: str,
        *,
        hostname: str,
        os_name: str,
        os_code: str | None,
        arch: str,
        target_triple: str | None,
        ip_addresses: list[str],
        last_seen: str,
        metadata: dict[str, Any],
        status: str,
    ) -> None:
        props = _clean_props(
            {
                "instance_id": node_id,
                "hostname": hostname,
                "os": os_name,
                "os_code": os_code_for(os_name, os_code),
                "arch": arch,
                "target_triple": target_triple,
                "ip_addresses": ip_addresses,
                "last_seen": last_seen,
                "metadata": metadata,
                "status": status,
            }
        )
        self.graph.upsert_node(node_id, props, label="Instance")

    def _upsert_placeholder(self, node_id: str, last_seen: str) -> None:
        if self.graph.has_node(node_id):
            return
        self._upsert_instance(
            node_id,
            hostname=node_id,
            os_name="linux",
            os_code=None,
            arch="unknown",
            target_triple=None,
            ip_addresses=[],
            last_seen=last_seen,
            metadata={"placeholder": True},
            status="discovered",
        )

    def _upsert_network_edge(self, edge: NetworkEdge, last_seen: str) -> None:
        source = edge.source or ""
        target = edge.target
        edge_type = normalize_edge_type(edge.type)
        existing = self.graph.get_edge(source, target, edge_type) or {}
        existing_props = existing.get("properties", existing)
        count = int(existing_props.get("count", 0) or 0) + 1
        props = _clean_props(
            {
                "source_instance_id": source,
                "target_instance_id": target,
                "edge_type": edge_type,
                "label": EDGE_LABELS[edge_type],
                "protocol": edge.protocol,
                "port": edge.port,
                "metadata": edge.metadata,
                "last_seen": last_seen,
                "count": count,
            }
        )
        self.graph.upsert_edge(source, target, props, rel_type=edge_type)

    def _normalize_node(self, node: dict[str, Any]) -> dict[str, Any]:
        props = node.get("properties", node)
        node_id = str(props.get("instance_id") or props.get("id") or node.get("id"))
        os_name = str(props.get("os") or "linux")
        code = os_code_for(os_name, props.get("os_code"))
        return {
            "id": node_id,
            "hostname": str(props.get("hostname") or node_id),
            "arch": str(props.get("arch") or "unknown"),
            "target_triple": props.get("target_triple"),
            "os": os_name,
            "os_code": code,
            "logo_path": f"/vendor/os-logos/64x64/{code}.png",
            "ip_addresses": props.get("ip_addresses") or [],
            "last_seen": props.get("last_seen"),
            "metadata": props.get("metadata") or {},
            "status": props.get("status") or "unknown",
        }

    def _normalize_edge(self, edge: dict[str, Any]) -> dict[str, Any] | None:
        relation = edge.get("r", edge)
        props = relation.get("properties", relation)
        source = props.get("source_instance_id") or edge.get("source")
        target = props.get("target_instance_id") or edge.get("target")
        if not source or not target:
            return None
        edge_type = normalize_edge_type(props.get("edge_type") or relation.get("type"))
        return {
            "id": f"{source}->{target}:{edge_type}",
            "source": str(source),
            "target": str(target),
            "type": edge_type,
            "label": EDGE_LABELS[edge_type],
            "protocol": props.get("protocol"),
            "port": props.get("port"),
            "last_seen": props.get("last_seen"),
            "count": props.get("count") or 1,
            "metadata": props.get("metadata") or {},
        }

    def _commit(self) -> None:
        for attr in ("connection", "conn"):
            conn = getattr(self.graph, attr, None)
            if conn is not None and hasattr(conn, "commit"):
                conn.commit()
                return
