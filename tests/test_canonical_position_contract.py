from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text())


CANONICAL = load("machine/canonical-position.json")
CAPABILITIES = load("machine/capabilities.json")
TARGET = load("machine/target-contract.json")


class CanonicalPositionContractTests(unittest.TestCase):
    def test_repository_owns_only_causal_provenance(self):
        self.assertEqual(CANONICAL["role"], "CANONICAL_SPECIALIST")
        self.assertEqual(CANONICAL["owns"], "causal_action_provenance")
        self.assertIn("actor/object authorization policy", CANONICAL["does_not_own"])
        self.assertIn("ontology mutation/writeback semantics", CANONICAL["does_not_own"])

    def test_sibling_relationships_do_not_claim_integration(self):
        for edge in CANONICAL["relationships"]:
            self.assertFalse(edge["integration_exercised"])

    def test_capabilities_are_repository_native(self):
        capabilities = set(CAPABILITIES["capabilities"])
        self.assertNotIn("hyper-scaling", capabilities)
        self.assertIn("causal_parent_guard", capabilities)
        self.assertIn("content_bound_lineage_fingerprint", capabilities)
        self.assertIn("immutable_commit_snapshot", capabilities)

    def test_target_reflects_earned_canonical_position(self):
        self.assertEqual(TARGET["current"]["state"], "EVOLVING")
        self.assertFalse(TARGET["current"]["canonical_position_pending_exact_head_proof"])
        self.assertTrue(TARGET["promotion"]["require_exact_source_sha"])
        self.assertEqual(TARGET["promotion"]["next_gate"], "EVOLUTION_CURSOR_DEFINED")
        self.assertTrue(TARGET["evolution"]["cursor"].startswith("next:"))

    def test_truth_boundary_excludes_authority_and_execution(self):
        boundary = CAPABILITIES["truth_boundary"]
        self.assertIn("does not authenticate attestations", boundary)
        self.assertIn("decide actor/object authority", boundary)
        self.assertIn("execute side effects", boundary)


if __name__ == "__main__":
    unittest.main()
