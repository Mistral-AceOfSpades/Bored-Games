from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vibe.game_tutor.orchestrator import MistralVibeOrchestrator
from vibe.game_tutor.webapp import LocalStorage, build_from_uploaded_rules


class WebAppStorageTests(unittest.TestCase):
    def test_build_from_uploaded_rules_persists_session_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalStorage(Path(directory))
            result = build_from_uploaded_rules(
                filename="chess_rules.txt",
                rules_text="The king moves one square in any direction.",
                storage=storage,
                orchestrator=MistralVibeOrchestrator(),
            )

            session_dir = Path(result["session_dir"])
            manifest_path = Path(result["manifest_path"])
            self.assertTrue(session_dir.exists())
            self.assertTrue(manifest_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("tutorial_output", manifest)
            self.assertIn("strategy_output", manifest)
            self.assertIn("ui_output", manifest)


if __name__ == "__main__":
    unittest.main()
