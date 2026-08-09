
from __future__ import annotations
import unittest
from src.lineage import ActionKind, ActionNode, CommitStatus, LineageGraph

class LineageLeveledTests(unittest.TestCase):
    def test_root_and_child(self):
        g = LineageGraph()
        r = g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"obj": "X"}, ()))
        self.assertEqual(r[0], CommitStatus.COMMITTED)
        r2 = g.commit(ActionNode("a1", ActionKind.SIDE_EFFECT, {"write": 1}, ("a0",), attestation="sig:1"))
        self.assertEqual(r2[0], CommitStatus.COMMITTED)

    def test_orphan_side_effect(self):
        g = LineageGraph()
        st, reason = g.commit(ActionNode("x", ActionKind.SIDE_EFFECT, {}, (), attestation="s"))
        self.assertEqual(reason, "ORPHAN_SIDE_EFFECT")

    def test_missing_attestation(self):
        g = LineageGraph()
        g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        st, reason = g.commit(ActionNode("a1", ActionKind.SIDE_EFFECT, {}, ("a0",)))
        self.assertEqual(reason, "MISSING_ATTESTATION")

    def test_missing_parent(self):
        g = LineageGraph()
        st, reason = g.commit(ActionNode("a3", ActionKind.TRANSFORM, {}, ("missing",)))
        self.assertTrue(reason and reason.startswith("MISSING_PARENT"))

    def test_duplicate(self):
        g = LineageGraph()
        g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        st, reason = g.commit(ActionNode("a0", ActionKind.TRANSFORM, {}, ()))
        self.assertEqual(reason, "DUPLICATE_ID")

    def test_max_depth(self):
        g = LineageGraph(max_depth=2)
        g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        g.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))
        g.commit(ActionNode("a2", ActionKind.TRANSFORM, {}, ("a1",)))
        st, reason = g.commit(ActionNode("a3", ActionKind.TRANSFORM, {}, ("a2",)))
        self.assertEqual(reason, "MAX_DEPTH")

    def test_reaches_and_topo(self):
        g = LineageGraph()
        g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        g.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))
        g.commit(ActionNode("a2", ActionKind.TRANSFORM, {}, ("a1",)))
        self.assertTrue(g.reaches("a2", "a0"))
        self.assertFalse(g.reaches("a0", "a2"))
        self.assertEqual(g.topo_ids(), ["a0", "a1", "a2"])

if __name__ == "__main__":
    unittest.main()
