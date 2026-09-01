import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
STORE = SKILL_ROOT / "scripts" / "learning_store.py"
MANAGER = SKILL_ROOT / "scripts" / "lab_manager.py"


def invoke(script, command, payload, timeout=90):
    completed = subprocess.run(
        [sys.executable, str(script), command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout)


class LabManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        code, response = invoke(
            STORE, "init", {"project_root": str(self.project), "target_framework": "net10.0"}
        )
        self.assertEqual(0, code, response)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **values):
        return {"project_root": str(self.project), **values}

    def create(self, lab_id="lab-test-starter"):
        code, response = invoke(
            MANAGER,
            "create",
            self.payload(
                lab_id=lab_id, objective_id="s0.delegates-closures", target_framework="net10.0"
            ),
        )
        self.assertEqual(0, code, response)
        return response

    def test_create_build_run_and_repeat(self):
        created = self.create()
        self.assertTrue(Path(created["program"]).is_file())
        self.assertIn("lab-test-starter", Path(created["program"]).read_text(encoding="utf-8"))

        code, duplicate = invoke(
            MANAGER,
            "create",
            self.payload(
                lab_id="lab-test-starter", objective_id="s0.delegates-closures", target_framework="net10.0"
            ),
        )
        self.assertEqual(2, code)
        self.assertEqual("lab_exists", duplicate["error"])

        code, built = invoke(
            MANAGER, "build", self.payload(lab_id="lab-test-starter", configuration="Debug", timeout_seconds=60)
        )
        self.assertEqual(0, code, built)
        self.assertTrue(built["success"], built)

        code, ran = invoke(
            MANAGER, "run", self.payload(lab_id="lab-test-starter", configuration="Debug", timeout_seconds=10)
        )
        self.assertEqual(0, code, ran)
        self.assertTrue(ran["success"], ran)
        self.assertIn("LAB_RESULT: PASS", ran["stdout"])

        code, repeated = invoke(
            MANAGER,
            "repeat",
            self.payload(
                lab_id="lab-test-starter", configuration="Debug", timeout_seconds=10, repetitions=3
            ),
        )
        self.assertEqual(0, code, repeated)
        self.assertEqual(3, repeated["completed_repetitions"])
        self.assertEqual(3, repeated["successful_repetitions"])

    def test_timeout_is_bounded(self):
        created = self.create("lab-test-timeout")
        Path(created["program"]).write_text(
            "Thread.Sleep(TimeSpan.FromSeconds(5));\nConsole.WriteLine(\"late\");\n",
            encoding="utf-8",
        )
        _, built = invoke(
            MANAGER, "build", self.payload(lab_id="lab-test-timeout", configuration="Debug", timeout_seconds=60)
        )
        self.assertTrue(built["success"], built)
        code, ran = invoke(
            MANAGER, "run", self.payload(lab_id="lab-test-timeout", configuration="Debug", timeout_seconds=1)
        )
        self.assertEqual(0, code, ran)
        self.assertFalse(ran["success"])
        self.assertTrue(ran["timed_out"])

    def test_invalid_lab_id_and_missing_initialization(self):
        code, invalid = invoke(
            MANAGER,
            "create",
            self.payload(lab_id="../escape", objective_id="s0.delegates-closures"),
        )
        self.assertEqual(2, code)
        self.assertEqual("invalid_lab_id", invalid["error"])

        with tempfile.TemporaryDirectory() as other:
            code, missing = invoke(
                MANAGER,
                "create",
                {"project_root": other, "lab_id": "lab-test", "objective_id": "s0.delegates-closures"},
            )
        self.assertEqual(2, code)
        self.assertEqual("not_initialized", missing["error"])


if __name__ == "__main__":
    unittest.main()
