"""Action lineage graph — fail-closed DAG for operational actions.

The graph owns causal provenance only. It does not authenticate actors, decide
object authorization, or execute/write back side effects.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


def digest(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class ActionKind(str, Enum):
    ROOT_OBSERVE = "ROOT_OBSERVE"
    TRANSFORM = "TRANSFORM"
    SIDE_EFFECT = "SIDE_EFFECT"


class CommitStatus(str, Enum):
    COMMITTED = "COMMITTED"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class ActionNode:
    action_id: str
    kind: ActionKind
    payload: Mapping[str, object]
    parent_ids: tuple[str, ...]
    attestation: str | None = None  # required metadata for SIDE_EFFECT

    def fingerprint(self) -> str:
        return digest(
            {
                "id": self.action_id,
                "kind": self.kind.value,
                "payload": dict(self.payload),
                "parents": list(self.parent_ids),
                "attestation": self.attestation,
            }
        )


class LineageGraph:
    def __init__(self, max_depth: int = 64, max_parents: int = 8):
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if max_parents < 1:
            raise ValueError("max_parents must be positive")
        self.max_depth = max_depth
        self.max_parents = max_parents
        self._nodes: dict[str, ActionNode] = {}
        self.tips: list[str] = []
        self._lock = threading.RLock()

    @property
    def nodes(self) -> dict[str, ActionNode]:
        """Return an isolated snapshot so callers cannot mutate committed history."""
        with self._lock:
            return copy.deepcopy(self._nodes)

    def _ancestors(self, action_id: str, seen: set[str] | None = None) -> set[str]:
        seen = seen if seen is not None else set()
        if action_id in seen:
            return seen
        seen.add(action_id)
        node = self._nodes.get(action_id)
        if not node:
            return seen
        for parent_id in node.parent_ids:
            self._ancestors(parent_id, seen)
        return seen

    def depth(self, action_id: str) -> int:
        node = self._nodes.get(action_id)
        if not node or not node.parent_ids:
            return 0
        return 1 + max(self.depth(parent_id) for parent_id in node.parent_ids)

    def _would_cycle(self, action_id: str, parents: Iterable[str]) -> bool:
        for parent_id in parents:
            if parent_id == action_id:
                return True
            if action_id in self._ancestors(parent_id):
                return True
        return False

    @staticmethod
    def _snapshot(node: ActionNode) -> ActionNode:
        # Commit an isolated payload snapshot. JSON round-tripping also normalizes
        # nested mutable containers into a deterministic JSON-compatible shape.
        payload = json.loads(
            json.dumps(dict(node.payload), sort_keys=True, separators=(",", ":"), default=str)
        )
        return ActionNode(
            action_id=node.action_id,
            kind=node.kind,
            payload=payload,
            parent_ids=tuple(node.parent_ids),
            attestation=node.attestation,
        )

    def commit(self, node: ActionNode) -> tuple[CommitStatus, str | None]:
        with self._lock:
            if not node.action_id.strip():
                return CommitStatus.REFUSED, "EMPTY_ID"
            if node.action_id in self._nodes:
                return CommitStatus.REFUSED, "DUPLICATE_ID"
            if len(node.parent_ids) != len(set(node.parent_ids)):
                return CommitStatus.REFUSED, "DUPLICATE_PARENT"
            if len(node.parent_ids) > self.max_parents:
                return CommitStatus.REFUSED, "TOO_MANY_PARENTS"
            if node.kind is ActionKind.ROOT_OBSERVE and node.parent_ids:
                return CommitStatus.REFUSED, "ROOT_HAS_PARENT"
            if node.kind is not ActionKind.ROOT_OBSERVE and not node.parent_ids:
                return CommitStatus.REFUSED, "ORPHAN_NONROOT"
            if node.kind is ActionKind.SIDE_EFFECT and not (node.attestation or "").strip():
                return CommitStatus.REFUSED, "MISSING_ATTESTATION"
            if node.kind is not ActionKind.ROOT_OBSERVE:
                for parent_id in node.parent_ids:
                    if parent_id not in self._nodes:
                        return CommitStatus.REFUSED, f"MISSING_PARENT:{parent_id}"
            if self._would_cycle(node.action_id, node.parent_ids):
                return CommitStatus.REFUSED, "CYCLE"
            if node.parent_ids:
                depth = 1 + max(self.depth(parent_id) for parent_id in node.parent_ids)
                if depth > self.max_depth:
                    return CommitStatus.REFUSED, "MAX_DEPTH"

            committed = self._snapshot(node)
            self._nodes[node.action_id] = committed
            self.tips.append(node.action_id)
            return CommitStatus.COMMITTED, None

    def reaches(self, src: str, dst: str) -> bool:
        with self._lock:
            return dst in self._ancestors(src)

    def lineage_fingerprint(self, action_id: str) -> str:
        """Bind the reachable topology and exact committed node content."""
        with self._lock:
            if action_id not in self._nodes:
                raise KeyError(action_id)
            chain = sorted(self._ancestors(action_id))
            return digest(
                {
                    "tip": action_id,
                    "nodes": [
                        {"id": node_id, "fingerprint": self._nodes[node_id].fingerprint()}
                        for node_id in chain
                    ],
                }
            )

    def topo_ids(self) -> list[str]:
        with self._lock:
            pending = set(self._nodes)
            done: list[str] = []
            while pending:
                progress = False
                for action_id in sorted(pending):
                    parents = set(self._nodes[action_id].parent_ids)
                    if parents <= set(done):
                        done.append(action_id)
                        pending.remove(action_id)
                        progress = True
                        break
                if not progress:
                    raise RuntimeError("lineage graph contains an unresolved cycle")
            return done
