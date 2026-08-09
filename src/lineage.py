"""Action lineage graph — fail-closed DAG for operational actions."""
from __future__ import annotations

import hashlib
import json
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

    def fingerprint(self) -> str:
        return digest(
            {
                "id": self.action_id,
                "kind": self.kind.value,
                "payload": self.payload,
                "parents": list(self.parent_ids),
            }
        )


@dataclass
class LineageGraph:
    nodes: dict[str, ActionNode] = field(default_factory=dict)
    tips: list[str] = field(default_factory=list)

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

    def _would_cycle(self, action_id: str, parents: Iterable[str]) -> bool:
        for p in parents:
            if p == action_id:
                return True
            if action_id in self._ancestors(p):
                return True
        return False

    def commit(self, node: ActionNode) -> tuple[CommitStatus, str | None]:
        if node.action_id in self.nodes:
            return CommitStatus.REFUSED, "DUPLICATE_ID"
        if node.kind is ActionKind.SIDE_EFFECT and not node.parent_ids:
            return CommitStatus.REFUSED, "ORPHAN_SIDE_EFFECT"
        if node.kind is not ActionKind.ROOT_OBSERVE:
            for p in node.parent_ids:
                if p not in self.nodes:
                    return CommitStatus.REFUSED, f"MISSING_PARENT:{p}"
        if self._would_cycle(node.action_id, node.parent_ids):
            return CommitStatus.REFUSED, "CYCLE"
        self.nodes[node.action_id] = node
        self.tips.append(node.action_id)
        return CommitStatus.COMMITTED, None

    def lineage_fingerprint(self, action_id: str) -> str:
        chain = sorted(self._ancestors(action_id))
        return digest({"chain": chain, "tip": action_id})
