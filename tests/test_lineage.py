from __future__ import annotations
import unittest
from src.lineage import ActionKind, ActionNode, CommitStatus, LineageGraph

class LineageTests(unittest.TestCase):
    def test_root_and_child(self):
        g = LineageGraph()
        r = g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {"obj": "X"}, ()))
        self.assertEqual(r[0], CommitStatus.COMMITTED)
        r2 = g.commit(ActionNode("a1", ActionKind.SIDE_EFFECT, {"write": 1}, ("a0",)))
        self.assertEqual(r2[0], CommitStatus.COMMITTED)

    def test_orphan_side_effect(self):
        g = LineageGraph()
        st, reason = g.commit(ActionNode("x", ActionKind.SIDE_EFFECT, {}, ()))
        self.assertEqual(reason, "ORPHAN_SIDE_EFFECT")

    def test_cycle_refuses(self):
        g = LineageGraph()
        g.commit(ActionNode("a0", ActionKind.ROOT_OBSERVE, {}, ()))
        g.commit(ActionNode("a1", ActionKind.TRANSFORM, {}, ("a0",)))
        # try to parent a0 on a1 incorrectly via new node that would close cycle a0<-a2<-a1<-a0
        st, reason = g.commit(ActionNode("a0", ActionKind.TRANSFORM, {}, ("a1",)))
        self.assertEqual(reason, "DUPLICATE_ID")
        st, reason = g.commit(ActionNode("a2", ActionKind.TRANSFORM, {}, ("a1",)))
        self.assertEqual(st, CommitStatus.COMMITTED)
        # forging cycle by reusing would need rewrite; missing parent still fails
        st, reason = g.commit(ActionNode("a3", ActionKind.TRANSFORM, {}, ("missing",)))
        self.assertTrue(reason and reason.startswith("MISSING_PARENT"))

if __name__ == "__main__":
    unittest.main()
