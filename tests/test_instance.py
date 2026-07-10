import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice.instance import load_instance_identity


class InstanceIdentityTests(unittest.TestCase):
    def test_auto_room_is_stable_across_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            first = load_instance_identity("auto", state_path=path)
            second = load_instance_identity("auto", state_path=path)

            self.assertEqual(first, second)
            self.assertEqual(first.room, f"mate-{first.instance_id}")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_legacy_default_migrates_to_instance_room(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = load_instance_identity(
                "mate-hermes-test", state_path=Path(directory) / "instance.json"
            )
            self.assertNotEqual(identity.room, "mate-hermes-test")
            self.assertTrue(identity.room.startswith("mate-"))

    def test_explicit_room_override_keeps_stable_instance_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            first = load_instance_identity("operator-room", state_path=path)
            second = load_instance_identity("another-room", state_path=path)

            self.assertEqual(first.instance_id, second.instance_id)
            self.assertEqual(second.room, "another-room")
            self.assertEqual(json.loads(path.read_text())["room"], "another-room")

    def test_instance_id_can_be_recovered_from_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            with patch.dict(os.environ, {"MATE_INSTANCE_ID": "recovered_123"}):
                identity = load_instance_identity("auto", state_path=path)

            self.assertEqual(identity.instance_id, "recovered_123")
            self.assertEqual(identity.room, "mate-recovered_123")


if __name__ == "__main__":
    unittest.main()
