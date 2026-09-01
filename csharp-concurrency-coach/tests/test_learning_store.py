import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "learning_store.py"


def invoke(command, payload, raw=None):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), command],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    response = json.loads(completed.stdout)
    return completed.returncode, response


class LearningStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **values):
        return {"project_root": str(self.project), **values}

    def init(self):
        code, response = invoke("init", self.payload(target_framework="net10.0"))
        self.assertEqual(0, code, response)
        self.assertTrue(response["ok"])
        return response

    def test_status_and_init_are_idempotent(self):
        code, status = invoke("status", self.payload())
        self.assertEqual(0, code)
        self.assertEqual("not_initialized", status["state"])
        first = self.init()
        second = self.init()
        self.assertEqual(first["database"], second["database"])
        code, status = invoke("status", self.payload())
        self.assertEqual(0, code)
        self.assertEqual("ready", status["state"])
        self.assertEqual("s0.delegates-closures", status["next"]["objective"]["objective_id"])
        self.assertEqual(13, len(status["stages"]))
        self.assertEqual("s0", status["curriculum_cursor"]["current_stage_id"])

    def test_session_mastery_lab_completion_and_export(self):
        self.init()
        code, started = invoke("start-session", self.payload(minutes=25, mode="diagnostic"))
        self.assertEqual(0, code, started)
        session_id = started["session_id"]

        code, duplicate = invoke("start-session", self.payload())
        self.assertEqual(2, code)
        self.assertEqual("active_session_exists", duplicate["error"])

        code, too_high = invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="concept", success=True, mastery=3,
            ),
        )
        self.assertEqual(2, code)
        self.assertEqual("unsupported_mastery", too_high["error"])

        code, attempt = invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="prediction", success=True, mastery=2, prompt="predict", response="answer",
            ),
        )
        self.assertEqual(0, code, attempt)
        self.assertEqual(2, attempt["mastery"])

        code, attempt = invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="lab", success=True, mastery=3,
            ),
        )
        self.assertEqual(0, code, attempt)
        self.assertEqual(3, attempt["mastery"])

        code, lab = invoke(
            "record-lab",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                lab_id="lab-closure-capture", success=True, command="run",
                exit_code=0, duration_ms=100, summary="pass",
            ),
        )
        self.assertEqual(0, code, lab)

        code, completed = invoke(
            "complete-session", self.payload(session_id=session_id, summary="diagnostic complete")
        )
        self.assertEqual(0, code, completed)
        self.assertEqual(1, completed["progress_delta"]["objectives_reaching_level_3"])
        self.assertEqual("s0.generics-shared-state", completed["next"]["objective"]["objective_id"])

        code, exported = invoke("export", self.payload(format="markdown"))
        self.assertEqual(0, code, exported)
        report = Path(exported["path"])
        self.assertTrue(report.is_file())
        self.assertIn("s0.delegates-closures", report.read_text(encoding="utf-8"))

    def test_resume_recover_and_abandon(self):
        self.init()
        _, started = invoke("start-session", self.payload(minutes=10, mode="learning"))
        code, resumed = invoke("resume", self.payload())
        self.assertEqual(0, code, resumed)
        self.assertEqual(started["session_id"], resumed["session"]["session_id"])
        code, recovered = invoke("recover", self.payload(abandon=False))
        self.assertEqual(0, code, recovered)
        code, abandoned = invoke("recover", self.payload(abandon=True))
        self.assertEqual(0, code, abandoned)
        self.assertEqual("abandoned", abandoned["status"])
        code, missing = invoke("resume", self.payload())
        self.assertEqual(2, code)
        self.assertEqual("no_active_session", missing["error"])

    def test_delayed_review_is_enforced_and_advances(self):
        self.init()
        _, started = invoke("start-session", self.payload())
        session_id = started["session_id"]
        invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="lab", success=True, mastery=3,
            ),
        )
        code, early = invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="review", success=True, mastery=3,
            ),
        )
        self.assertEqual(2, code)
        self.assertEqual("review_not_due", early["error"])

        db = self.project / ".csharp-concurrency-learning" / "learning.db"
        with closing(sqlite3.connect(db)) as connection:
            connection.execute(
                "UPDATE reviews SET due_at = '2000-01-01T00:00:00Z' WHERE objective_id = ?",
                ("s0.delegates-closures",),
            )
            connection.commit()
        code, review = invoke(
            "record-attempt",
            self.payload(
                session_id=session_id, objective_id="s0.delegates-closures",
                kind="review", success=True, mastery=3,
            ),
        )
        self.assertEqual(0, code, review)
        with closing(sqlite3.connect(db)) as connection:
            interval_index = connection.execute(
                "SELECT interval_index FROM reviews WHERE objective_id = ?", ("s0.delegates-closures",)
            ).fetchone()[0]
        self.assertEqual(1, interval_index)

    def test_topic_selection_reports_prerequisite_gaps(self):
        self.init()
        code, selected = invoke("next", self.payload(topic="deadlock"))
        self.assertEqual(0, code, selected)
        self.assertEqual("s4.deadlock", selected["objective"]["objective_id"])
        gap_ids = [gap["objective_id"] for gap in selected["prerequisite_gaps"]]
        self.assertIn("s0.delegates-closures", gap_ids)
        self.assertIn("s4.events-barriers", gap_ids)

    def test_stage_gate_blocks_advancement(self):
        self.init()
        db = self.project / ".csharp-concurrency-learning" / "learning.db"
        with closing(sqlite3.connect(db)) as connection:
            connection.execute(
                """UPDATE mastery SET level = 3
                   WHERE objective_id IN (
                     SELECT objective_id FROM curriculum_objectives WHERE stage_id = 's0'
                   )"""
            )
            connection.commit()
        code, selected = invoke("next", self.payload())
        self.assertEqual(0, code, selected)
        self.assertEqual("stage_gate", selected["selection"])
        self.assertEqual("gate-s0-prerequisites", selected["gate"]["lab_id"])
        self.assertIn("diagnosis", selected["gate"]["missing_evidence"])

    def test_record_lab_rejects_unassigned_id(self):
        self.init()
        _, started = invoke("start-session", self.payload())
        code, response = invoke(
            "record-lab",
            self.payload(
                session_id=started["session_id"], objective_id="s0.delegates-closures",
                lab_id="unrelated-lab", success=True, command="run", exit_code=0, duration_ms=1,
            ),
        )
        self.assertEqual(2, code)
        self.assertEqual("invalid_lab_id", response["error"])

    def test_stage_checkpoint_is_persisted_for_gate_lab(self):
        self.init()
        _, started = invoke("start-session", self.payload(mode="gate"))
        code, response = invoke(
            "record-lab",
            self.payload(
                session_id=started["session_id"], objective_id="s0.prerequisites-integration",
                lab_id="gate-s0-prerequisites", success=False, command="run", exit_code=1,
                duration_ms=25, summary="diagnostic failed",
            ),
        )
        self.assertEqual(0, code, response)
        db = self.project / ".csharp-concurrency-learning" / "learning.db"
        with closing(sqlite3.connect(db)) as connection:
            checkpoint = connection.execute(
                "SELECT stage_id, status, gate_lab_id FROM stage_checkpoints"
            ).fetchone()
        self.assertEqual(("s0", "failed", "gate-s0-prerequisites"), checkpoint)

    def test_invalid_json_and_skill_source_are_rejected(self):
        code, invalid = invoke("status", {}, raw="{")
        self.assertEqual(2, code)
        self.assertEqual("invalid_json", invalid["error"])
        code, forbidden = invoke("status", {"project_root": str(SKILL_ROOT)})
        self.assertEqual(2, code)
        self.assertEqual("skill_source_forbidden", forbidden["error"])


if __name__ == "__main__":
    unittest.main()
