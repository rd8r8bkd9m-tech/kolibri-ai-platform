import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from directive_compiler import DirectiveStore


class DirectiveCompilerTests(unittest.TestCase):
    def copy_contracts(self, root: Path) -> None:
        target = root / ".factory" / "contracts"
        target.mkdir(parents=True)
        for path in (REPO_ROOT / ".factory" / "contracts").glob("*.schema.json"):
            target.joinpath(path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    def test_submit_compile_activate_directive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_contracts(root)
            store = DirectiveStore(root=root)
            raw = "DIRECTIVE_ID: TEST-001\nTITLE: Test Directive\nPRIORITY: P1\nMODE: APPLY_IMMEDIATELY_NO_WAIT\n\n18. ACCEPTANCE CRITERIA\n- compiled\n"
            meta = store.submit_directive(raw, source="test", owner_id="owner")
            self.assertEqual(meta["directive_id"], "TEST-001")
            compiled = store.compile_directive("TEST-001")
            self.assertEqual(compiled["current_status"], "COMPILED")
            self.assertEqual(compiled["language"], "en")
            active = store.activate_directive("TEST-001")
            self.assertEqual(active["current_status"], "ACTIVE")
            self.assertTrue((root / ".factory" / "memory" / "directive-ledger.jsonl").exists())

    def test_raw_directive_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_contracts(root)
            store = DirectiveStore(root=root)
            store.submit_directive("DIRECTIVE_ID: TEST-002\nTITLE: One\n")
            with self.assertRaises(ValueError):
                store.submit_directive("DIRECTIVE_ID: TEST-002\nTITLE: Two\n")


if __name__ == "__main__":
    unittest.main()
