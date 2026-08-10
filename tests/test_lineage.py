from __future__ import annotations

import unittest

from src.lineage import ActionKind, ActionNode, CommitStatus, LineageGraph


class LineageLeveledTests(unittest.TestCase):
    def test_root_and_child(self):
        graph = LineageGraph()
        root = graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"obj": "X"}, ()))
        self.assertEqual(root[0], CommitStatus.COMMITTED)
        child = graph.commit(
            ActionNode(
                "a1",
                ActionKind.SIDE_EFFECT,
                {"write": 1},
                ("a0",),
                attestation="sig:1",
            )
        )
        self.assertEqual(child[0], CommitStatus.COMMITTED)

    def test_nonroot_must_have_parent(self):
        graph = LineageGraph()
        status, reason = graph.commit(ActionNode("x", ActionKind.TRANSFORM, {}, ()))
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "ORPHAN_NONROOT")

    def test_root_must_not_have_parent(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        status, reason = graph.commit(
            ActionNode("bad-root", ActionKind.ROOT_OBSERVE, {}, ("a0",))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "ROOT_HAS_PARENT")

    def test_side_effect_requires_attestation(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        status, reason = graph.commit(
            ActionNode("a1", ActionKind.SIDE_EFFECT, {}, ("a0",))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "MISSING_ATTESTATION")

    def test_missing_parent(self):
        graph = LineageGraph()
        status, reason = graph.commit(
            ActionNode("a3", ActionKind.TRANSFORM, {}, ("missing",))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertTrue(reason and reason.startswith("MISSING_PARENT"))

    def test_duplicate_id(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        status, reason = graph.commit(
            ActionNode("a0", ActionKind.TRANSFORM, {}, ("a0",))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "DUPLICATE_ID")

    def test_duplicate_parent_refuses(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        status, reason = graph.commit(
            ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0", "a0"))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "DUPLICATE_PARENT")

    def test_max_depth(self):
        graph = LineageGraph(max_depth=2)
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        graph.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))
        graph.commit(ActionNode("a2", ActionKind.TRANSFORM, {}, ("a1",)))
        status, reason = graph.commit(
            ActionNode("a3", ActionKind.TRANSFORM, {}, ("a2",))
        )
        self.assertEqual(status, CommitStatus.REFUSED)
        self.assertEqual(reason, "MAX_DEPTH")

    def test_reaches_and_topo(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        graph.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))
        graph.commit(ActionNode("a2", ActionKind.TRANSFORM, {}, ("a1",)))
        self.assertTrue(graph.reaches("a2", "a0"))
        self.assertFalse(graph.reaches("a0", "a2"))
        self.assertEqual(graph.topo_ids(), ["a0", "a1", "a2"])

    def test_commit_snapshots_mutable_payload(self):
        payload = {"nested": {"value": 1}}
        node = ActionNode("a0", ActionKind.ROOT_OBSERVE, payload, ())
        graph = LineageGraph()
        graph.commit(node)
        before = graph.nodes["a0"].fingerprint()
        payload["nested"]["value"] = 99
        after = graph.nodes["a0"].fingerprint()
        self.assertEqual(before, after)

    def test_nodes_snapshot_cannot_mutate_graph_history(self):
        graph = LineageGraph()
        graph.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"value": 1}, ()))
        snapshot = graph.nodes
        snapshot["a0"].payload["value"] = 99
        self.assertEqual(graph.nodes["a0"].payload["value"], 1)

    def test_lineage_fingerprint_binds_payload_content(self):
        first = LineageGraph()
        first.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"value": 1}, ()))
        first.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))

        second = LineageGraph()
        second.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"value": 2}, ()))
        second.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))

        self.assertNotEqual(
            first.lineage_fingerprint("a1"), second.lineage_fingerprint("a1")
        )

    def test_unknown_lineage_fingerprint_refuses(self):
        with self.assertRaises(KeyError):
            LineageGraph().lineage_fingerprint("missing")


if __name__ == "__main__":
    unittest.main()
