import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent


class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curriculum = json.loads(
            (SKILL_ROOT / "references" / "curriculum-v1.json").read_text(encoding="utf-8")
        )

    def test_stage_sequence_and_full_expert_destination(self):
        stages = self.curriculum["stages"]
        self.assertEqual(list(range(13)), [stage["order"] for stage in stages])
        self.assertEqual([f"s{index}" for index in range(13)], [stage["id"] for stage in stages])
        self.assertIn("专家", stages[-1]["title"])

    def test_objective_ids_are_unique_and_graph_is_acyclic(self):
        objectives = {
            objective["id"]: objective
            for stage in self.curriculum["stages"]
            for objective in stage["objectives"]
        }
        objective_count = sum(len(stage["objectives"]) for stage in self.curriculum["stages"])
        self.assertEqual(objective_count, len(objectives))
        self.assertGreaterEqual(objective_count, 70)

        visiting = set()
        visited = set()

        def visit(objective_id):
            self.assertNotIn(objective_id, visiting, f"cycle at {objective_id}")
            if objective_id in visited:
                return
            visiting.add(objective_id)
            for prerequisite in objectives[objective_id]["prerequisites"]:
                self.assertIn(prerequisite, objectives)
                visit(prerequisite)
            visiting.remove(objective_id)
            visited.add(objective_id)

        for objective_id in objectives:
            visit(objective_id)

    def test_every_core_objective_has_evidence_and_runnable_lab(self):
        allowed = set(self.curriculum["evidence_kinds"])
        lab_ids = set()
        for stage in self.curriculum["stages"]:
            self.assertTrue(stage["gate"]["lab_id"])
            self.assertTrue(set(stage["gate"]["required_evidence"]).issubset(allowed))
            for objective in stage["objectives"]:
                self.assertTrue(objective["core"])
                self.assertTrue(objective["lab_id"])
                self.assertNotIn(objective["lab_id"], lab_ids)
                lab_ids.add(objective["lab_id"])
                self.assertTrue(objective["evidence"])
                self.assertTrue(set(objective["evidence"]).issubset(allowed))

    def test_coverage_contains_required_advanced_topics(self):
        text = json.dumps(self.curriculum, ensure_ascii=False).casefold()
        required = [
            "system.threading.lock", "interlocked", "volatile", "semaphoreslim",
            "taskcompletionsource", "configureawait", "channel", "work stealing",
            "hill climbing", "aba", "false sharing", "eventpipe", "perfview",
            "backgroundservice", "backpressure", "dotnet-trace", "线程池饥饿",
        ]
        for term in required:
            self.assertIn(term, text)

    def test_skill_routes_all_references(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        references = [
            "teaching-method.md", "curriculum-guide.md", "data-storage.md", "labs.md",
            "runtime-internals.md", "windows-diagnostics.md", "curriculum-v1.json",
        ]
        for reference in references:
            self.assertIn(reference, skill_text)
            self.assertTrue((SKILL_ROOT / "references" / reference).is_file())


if __name__ == "__main__":
    unittest.main()
