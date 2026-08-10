"""Action lineage graph — fail-closed DAG for operational actions.

Leveled (L1): depth limit, reachability, side-effect attestation binding,
max parents, topological export.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


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
    payload: dict
    parent_ids: tuple[str, ...]
    attestation: str | None = None  # required for SIDE_EFFECT

    def fingerprint(self) -> str:
        return digest(
            {
                "id": self.action_id,
                "kind": self.kind.value,
                "payload": self.payload,
                "parents": list(self.parent_ids),
                "attestation": self.attestation,
            }
        )


class LineageGraph:
    def __init__(self, max_depth: int = 64, max_parents: int = 8):
        self.max_depth = max_depth
        self.max_parents = max_parents
        self.nodes: dict[str, ActionNode] = {}
        self.tips: list[str] = []
        self._lock = threading.RLock()

    def _ancestors(self, action_id: str, seen: set[str] | None = None) -> set[str]:
        seen = seen if seen is not None else set()
        if action_id in seen:
            return seen
        seen.add(action_id)
        node = self.nodes.get(action_id)
        if not node:
            return seen
        for p in node.parent_ids:
            self._ancestors(p, seen)
        return seen

    def depth(self, action_id: str) -> int:
        node = self.nodes.get(action_id)
        if not node or not node.parent_ids:
            return 0
        return 1 + max(self.depth(p) for p in node.parent_ids)

    def _would_cycle(self, action_id: str, parents: Iterable[str]) -> bool:
        for p in parents:
            if p == action_id:
                return True
            if action_id in self._ancestors(p):
                return True
        return False

    def commit(self, node: ActionNode) -> tuple[CommitStatus, str | None]:
        with self._lock:
            if node.action_id in self.nodes:
                return CommitStatus.REFUSED, "DUPLICATE_ID"
            if len(node.parent_ids) > self.max_parents:
                return CommitStatus.REFUSED, "TOO_MANY_PARENTS"
            if node.kind is ActionKind.SIDE_EFFECT and not node.parent_ids:
                return CommitStatus.REFUSED, "ORPHAN_SIDE_EFFECT"
            if node.kind is ActionKind.SIDE_EFFECT and not node.attestation:
                return CommitStatus.REFUSED, "MISSING_ATTESTATION"
            if node.kind is not ActionKind.ROOT_OBSERVE:
                for p in node.parent_ids:
                    if p not in self.nodes:
                        return CommitStatus.REFUSED, f"MISSING_PARENT:{p}"
            if self._would_cycle(node.action_id, node.parent_ids):
                return CommitStatus.REFUSED, "CYCLE"
            # depth check using parents
            if node.parent_ids:
                d = 1 + max(self.depth(p) for p in node.parent_ids)
                if d > self.max_depth:
                    return CommitStatus.REFUSED, "MAX_DEPTH"
            self.nodes[node.action_id] = node
            self.tips.append(node.action_id)
            return CommitStatus.COMMITTED, None

    def reaches(self, src: str, dst: str) -> bool:
        with self._lock:
            return dst in self._ancestors(src)

    def lineage_fingerprint(self, action_id: str) -> str:
        with self._lock:
            chain = sorted(self._ancestors(action_id))
            return digest({"chain": chain, "tip": action_id})

    def topo_ids(self) -> list[str]:
        with self._lock:
            pending = set(self.nodes)
            done: list[str] = []
            while pending:
                progress = False
                for aid in sorted(pending):
                    parents = set(self.nodes[aid].parent_ids)
                    if parents <= set(done):
                        done.append(aid)
                        pending.remove(aid)
                        progress = True
                        break
                if not progress:
                    break
            return done
