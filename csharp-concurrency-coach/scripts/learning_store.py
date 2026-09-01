#!/usr/bin/env python3
"""Project-local persistent learning state for csharp-concurrency-coach."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
CURRICULUM_PATH = SKILL_ROOT / "references" / "curriculum-v1.json"
DATA_DIR_NAME = ".csharp-concurrency-learning"
SCHEMA_VERSION = 1
EVIDENCE_CEILINGS = {
    "recognize": 1,
    "concept": 2,
    "prediction": 2,
    "code": 3,
    "lab": 3,
    "diagnosis": 4,
    "tradeoff": 4,
}


class StoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_after(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_request() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise StoreError("invalid_json", f"Invalid JSON input: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise StoreError("invalid_request", "Input must be one JSON object")
    return value


def resolve_paths(request: dict[str, Any], *, create: bool = False) -> tuple[Path, Path, Path]:
    raw_root = request.get("project_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise StoreError("missing_project_root", "project_root is required")
    project_root = Path(raw_root).expanduser().resolve()
    if not project_root.is_dir():
        raise StoreError("invalid_project_root", f"Project root does not exist: {project_root}")
    data_dir = (project_root / DATA_DIR_NAME).resolve()
    try:
        data_dir.relative_to(SKILL_ROOT)
    except ValueError:
        pass
    else:
        raise StoreError("skill_source_forbidden", "Learning data cannot be initialized inside the Skill source")
    db_path = data_dir / "learning.db"
    if create:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "labs").mkdir(exist_ok=True)
        (data_dir / "exports").mkdir(exist_ok=True)
    return project_root, data_dir, db_path


def load_curriculum() -> dict[str, Any]:
    try:
        curriculum = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError("curriculum_invalid", f"Cannot load curriculum: {exc}") from exc
    validate_curriculum(curriculum)
    return curriculum


def validate_curriculum(curriculum: dict[str, Any]) -> None:
    if curriculum.get("version") != 1 or not isinstance(curriculum.get("stages"), list):
        raise StoreError("curriculum_invalid", "Unsupported curriculum shape or version")
    objective_ids: set[str] = set()
    stage_ids: set[str] = set()
    objectives: list[dict[str, Any]] = []
    for stage in curriculum["stages"]:
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or stage_id in stage_ids:
            raise StoreError("curriculum_invalid", f"Invalid or duplicate stage ID: {stage_id}")
        stage_ids.add(stage_id)
        if not stage.get("objectives"):
            raise StoreError("curriculum_invalid", f"Stage has no objectives: {stage_id}")
        for objective in stage["objectives"]:
            objective_id = objective.get("id")
            if not isinstance(objective_id, str) or objective_id in objective_ids:
                raise StoreError("curriculum_invalid", f"Invalid or duplicate objective ID: {objective_id}")
            if not objective.get("core", False):
                raise StoreError("curriculum_invalid", f"Every v1 objective must be core: {objective_id}")
            objective_ids.add(objective_id)
            objectives.append(objective)
    for objective in objectives:
        for prerequisite in objective.get("prerequisites", []):
            if prerequisite not in objective_ids:
                raise StoreError("curriculum_invalid", f"Unknown prerequisite {prerequisite} for {objective['id']}")

    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {item["id"]: item for item in objectives}

    def visit(objective_id: str) -> None:
        if objective_id in visiting:
            raise StoreError("curriculum_invalid", f"Prerequisite cycle at {objective_id}")
        if objective_id in visited:
            return
        visiting.add(objective_id)
        for prerequisite in by_id[objective_id].get("prerequisites", []):
            visit(prerequisite)
        visiting.remove(objective_id)
        visited.add(objective_id)

    for objective_id in objective_ids:
        visit(objective_id)


def connect(db_path: Path, *, require_initialized: bool = True) -> sqlite3.Connection:
    if require_initialized and not db_path.exists():
        raise StoreError("not_initialized", "Learning data is not initialized")
    try:
        connection = sqlite3.connect(db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise StoreError("database_busy", "The learning database is busy") from exc
        raise


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learner_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            created_at TEXT NOT NULL,
            learner_note TEXT,
            target_framework TEXT NOT NULL,
            curriculum_version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS curriculum_stages (
            stage_id TEXT PRIMARY KEY,
            stage_order INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            gate_lab_id TEXT NOT NULL,
            gate_evidence_json TEXT NOT NULL,
            retired INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS curriculum_objectives (
            objective_id TEXT PRIMARY KEY,
            stage_id TEXT NOT NULL REFERENCES curriculum_stages(stage_id),
            position INTEGER NOT NULL,
            title TEXT NOT NULL,
            core INTEGER NOT NULL,
            prerequisites_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            lab_id TEXT,
            tags_json TEXT NOT NULL,
            retired INTEGER NOT NULL DEFAULT 0,
            UNIQUE(stage_id, position)
        );
        CREATE TABLE IF NOT EXISTS curriculum_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_stage_id TEXT REFERENCES curriculum_stages(stage_id),
            last_objective_id TEXT REFERENCES curriculum_objectives(objective_id),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'abandoned')),
            minutes INTEGER NOT NULL,
            mode TEXT NOT NULL,
            note TEXT,
            summary TEXT,
            start_mastery_sum INTEGER NOT NULL,
            start_mastered_count INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_session
            ON sessions(status) WHERE status = 'active';
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(session_id),
            objective_id TEXT NOT NULL REFERENCES curriculum_objectives(objective_id),
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            success INTEGER NOT NULL,
            mastery INTEGER NOT NULL CHECK (mastery BETWEEN 0 AND 4),
            prompt TEXT,
            response TEXT,
            feedback TEXT
        );
        CREATE TABLE IF NOT EXISTS mastery (
            objective_id TEXT PRIMARY KEY REFERENCES curriculum_objectives(objective_id),
            level INTEGER NOT NULL CHECK (level BETWEEN 0 AND 4),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            objective_id TEXT PRIMARY KEY REFERENCES curriculum_objectives(objective_id),
            due_at TEXT NOT NULL,
            interval_index INTEGER NOT NULL,
            last_result INTEGER
        );
        CREATE TABLE IF NOT EXISTS lab_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(session_id),
            objective_id TEXT NOT NULL REFERENCES curriculum_objectives(objective_id),
            lab_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            success INTEGER NOT NULL,
            command TEXT NOT NULL,
            exit_code INTEGER,
            duration_ms INTEGER NOT NULL,
            summary TEXT
        );
        CREATE TABLE IF NOT EXISTS stage_checkpoints (
            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(session_id),
            stage_id TEXT NOT NULL REFERENCES curriculum_stages(stage_id),
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('passed', 'failed')),
            gate_lab_id TEXT NOT NULL,
            evidence_json TEXT NOT NULL
        );
        """
    )


def sync_curriculum(connection: sqlite3.Connection, curriculum: dict[str, Any]) -> None:
    connection.execute("UPDATE curriculum_stages SET retired = 1")
    connection.execute("UPDATE curriculum_objectives SET retired = 1")
    for stage in curriculum["stages"]:
        connection.execute(
            """INSERT INTO curriculum_stages
               (stage_id, stage_order, title, gate_lab_id, gate_evidence_json, retired)
               VALUES (?, ?, ?, ?, ?, 0)
               ON CONFLICT(stage_id) DO UPDATE SET
                 stage_order=excluded.stage_order, title=excluded.title,
                 gate_lab_id=excluded.gate_lab_id, gate_evidence_json=excluded.gate_evidence_json,
                 retired=0""",
            (
                stage["id"], stage["order"], stage["title"], stage["gate"]["lab_id"],
                json.dumps(stage["gate"]["required_evidence"], ensure_ascii=False),
            ),
        )
        for position, objective in enumerate(stage["objectives"]):
            connection.execute(
                """INSERT INTO curriculum_objectives
                   (objective_id, stage_id, position, title, core, prerequisites_json,
                    evidence_json, lab_id, tags_json, retired)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                   ON CONFLICT(objective_id) DO UPDATE SET
                     stage_id=excluded.stage_id, position=excluded.position, title=excluded.title,
                     core=excluded.core, prerequisites_json=excluded.prerequisites_json,
                     evidence_json=excluded.evidence_json, lab_id=excluded.lab_id,
                     tags_json=excluded.tags_json, retired=0""",
                (
                    objective["id"], stage["id"], position, objective["title"],
                    int(objective["core"]), json.dumps(objective.get("prerequisites", [])),
                    json.dumps(objective.get("evidence", [])), objective.get("lab_id"),
                    json.dumps(objective.get("tags", []), ensure_ascii=False),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO mastery(objective_id, level, updated_at) VALUES (?, 0, ?)",
                (objective["id"], utc_now()),
            )
    first_stage = min(curriculum["stages"], key=lambda item: item["order"])["id"]
    connection.execute(
        """INSERT OR IGNORE INTO curriculum_state(id, current_stage_id, last_objective_id, updated_at)
           VALUES (1, ?, NULL, ?)""",
        (first_stage, utc_now()),
    )


def command_init(request: dict[str, Any]) -> dict[str, Any]:
    _, data_dir, db_path = resolve_paths(request, create=True)
    curriculum = load_curriculum()
    target_framework = request.get("target_framework", curriculum["default_target_framework"])
    if not isinstance(target_framework, str) or not target_framework.startswith("net"):
        raise StoreError("invalid_target_framework", "target_framework must look like net10.0")
    connection = connect(db_path, require_initialized=False)
    try:
        with connection:
            create_schema(connection)
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            row = connection.execute("SELECT id FROM learner_profile WHERE id = 1").fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO learner_profile
                       (id, created_at, learner_note, target_framework, curriculum_version)
                       VALUES (1, ?, ?, ?, ?)""",
                    (utc_now(), request.get("learner_note"), target_framework, curriculum["version"]),
                )
            else:
                connection.execute(
                    "UPDATE learner_profile SET curriculum_version = ? WHERE id = 1",
                    (curriculum["version"],),
                )
            sync_curriculum(connection, curriculum)
        return {
            "ok": True,
            "state": "initialized",
            "data_dir": str(data_dir),
            "database": str(db_path),
            "curriculum_version": curriculum["version"],
            "target_framework": connection.execute(
                "SELECT target_framework FROM learner_profile WHERE id = 1"
            ).fetchone()[0],
        }
    finally:
        connection.close()


def get_mastery(connection: sqlite3.Connection) -> dict[str, int]:
    return {row["objective_id"]: row["level"] for row in connection.execute("SELECT objective_id, level FROM mastery")}


def objective_payload(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    level_row = connection.execute(
        "SELECT level FROM mastery WHERE objective_id = ?", (row["objective_id"],)
    ).fetchone()
    return {
        "objective_id": row["objective_id"],
        "title": row["title"],
        "stage_id": row["stage_id"],
        "stage_title": row["stage_title"],
        "mastery": level_row["level"] if level_row else 0,
        "prerequisites": json.loads(row["prerequisites_json"]),
        "evidence": json.loads(row["evidence_json"]),
        "lab_id": row["lab_id"],
        "tags": json.loads(row["tags_json"]),
    }


OBJECTIVE_QUERY = """
    SELECT o.*, s.title AS stage_title, s.stage_order
    FROM curriculum_objectives o
    JOIN curriculum_stages s ON s.stage_id = o.stage_id
    WHERE o.retired = 0 AND s.retired = 0
"""


def prerequisite_gaps(connection: sqlite3.Connection, objective: sqlite3.Row) -> list[dict[str, Any]]:
    mastery = get_mastery(connection)
    rows = {row["objective_id"]: row for row in connection.execute(OBJECTIVE_QUERY)}
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(objective_id: str) -> None:
        if objective_id in seen or mastery.get(objective_id, 0) >= 2:
            return
        seen.add(objective_id)
        row = rows[objective_id]
        for prerequisite in json.loads(row["prerequisites_json"]):
            add(prerequisite)
        gaps.append({"objective_id": objective_id, "title": row["title"], "mastery": mastery.get(objective_id, 0)})

    for prerequisite in json.loads(objective["prerequisites_json"]):
        add(prerequisite)
    return gaps


def select_next(connection: sqlite3.Connection, topic: str | None = None) -> dict[str, Any]:
    now = utc_now()
    if topic:
        normalized = topic.casefold().strip()
        exact = connection.execute(
            OBJECTIVE_QUERY + " AND lower(o.objective_id) = lower(?)", (topic.strip(),)
        ).fetchone()
        if exact is not None:
            return {"selection": "topic", "objective": objective_payload(connection, exact), "prerequisite_gaps": prerequisite_gaps(connection, exact)}
        matches = []
        for row in connection.execute(OBJECTIVE_QUERY + " ORDER BY s.stage_order, o.position"):
            haystack = " ".join([row["title"], row["objective_id"], *json.loads(row["tags_json"])]).casefold()
            if normalized in haystack:
                matches.append(row)
        if not matches:
            raise StoreError("topic_not_found", f"No curriculum objective matches: {topic}")
        if len(matches) > 1:
            return {
                "selection": "ambiguous_topic",
                "matches": [objective_payload(connection, row) for row in matches[:10]],
            }
        row = matches[0]
        return {"selection": "topic", "objective": objective_payload(connection, row), "prerequisite_gaps": prerequisite_gaps(connection, row)}

    review = connection.execute(
        OBJECTIVE_QUERY
        + " AND o.objective_id IN (SELECT objective_id FROM reviews WHERE due_at <= ?) "
          "ORDER BY (SELECT due_at FROM reviews WHERE objective_id = o.objective_id) LIMIT 1",
        (now,),
    ).fetchone()
    if review is not None:
        return {"selection": "review", "objective": objective_payload(connection, review), "prerequisite_gaps": []}

    mastery = get_mastery(connection)
    stages = stage_status(connection)
    current_stage = next((stage for stage in stages if not stage["complete"]), None)
    if current_stage is None:
        return {"selection": "curriculum_complete", "objective": None, "prerequisite_gaps": []}

    stage_rows = list(connection.execute(
        OBJECTIVE_QUERY + " AND o.core = 1 AND o.stage_id = ? ORDER BY o.position",
        (current_stage["stage_id"],),
    ))
    for row in stage_rows:
        if mastery.get(row["objective_id"], 0) >= 3:
            continue
        prerequisites = json.loads(row["prerequisites_json"])
        if all(mastery.get(item, 0) >= 2 for item in prerequisites):
            return {"selection": "new_or_remediation", "objective": objective_payload(connection, row), "prerequisite_gaps": []}
    remaining = [row for row in stage_rows if mastery.get(row["objective_id"], 0) < 3]
    if remaining:
        return {"selection": "blocked", "objective": objective_payload(connection, remaining[0]), "prerequisite_gaps": prerequisite_gaps(connection, remaining[0])}
    if not current_stage["gate_lab_passed"] or current_stage["missing_gate_evidence_without_review"]:
        return {
            "selection": "stage_gate",
            "objective": None,
            "prerequisite_gaps": [],
            "gate": {
                "stage_id": current_stage["stage_id"],
                "stage_title": current_stage["title"],
                "lab_id": current_stage["gate_lab_id"],
                "required_evidence": current_stage["required_gate_evidence"],
                "missing_evidence": current_stage["missing_gate_evidence"],
                "gate_lab_passed": current_stage["gate_lab_passed"],
            },
        }
    next_review = connection.execute(
        """SELECT r.objective_id, o.title, r.due_at
           FROM reviews r JOIN curriculum_objectives o ON o.objective_id = r.objective_id
           WHERE o.stage_id = ? ORDER BY r.due_at LIMIT 1""",
        (current_stage["stage_id"],),
    ).fetchone()
    return {
        "selection": "waiting_for_delayed_review",
        "objective": None,
        "prerequisite_gaps": [],
        "stage_id": current_stage["stage_id"],
        "next_review": dict(next_review) if next_review else None,
    }


def stage_status(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    mastery = get_mastery(connection)
    result = []
    for stage in connection.execute("SELECT * FROM curriculum_stages WHERE retired = 0 ORDER BY stage_order"):
        objectives = list(connection.execute(
            "SELECT objective_id FROM curriculum_objectives WHERE stage_id = ? AND retired = 0 AND core = 1 ORDER BY position",
            (stage["stage_id"],),
        ))
        levels = [mastery.get(row["objective_id"], 0) for row in objectives]
        gate_lab_passed = connection.execute(
            "SELECT 1 FROM lab_runs WHERE lab_id = ? AND success = 1 LIMIT 1", (stage["gate_lab_id"],)
        ).fetchone() is not None
        review_passed = connection.execute(
            """SELECT 1 FROM attempts a JOIN curriculum_objectives o ON o.objective_id = a.objective_id
               WHERE o.stage_id = ? AND a.kind = 'review' AND a.success = 1 LIMIT 1""",
            (stage["stage_id"],),
        ).fetchone() is not None
        successful_kinds = {
            row["kind"]
            for row in connection.execute(
                """SELECT DISTINCT a.kind
                   FROM attempts a JOIN curriculum_objectives o ON o.objective_id = a.objective_id
                   WHERE o.stage_id = ? AND a.success = 1""",
                (stage["stage_id"],),
            )
        }
        required_evidence = json.loads(stage["gate_evidence_json"])
        missing_evidence = [kind for kind in required_evidence if kind not in successful_kinds]
        core_ready = bool(levels) and all(level >= 3 for level in levels)
        result.append({
            "stage_id": stage["stage_id"],
            "title": stage["title"],
            "core_objectives": len(levels),
            "mastered_objectives": sum(level >= 3 for level in levels),
            "core_ready": core_ready,
            "gate_lab_id": stage["gate_lab_id"],
            "gate_lab_passed": gate_lab_passed,
            "delayed_review_passed": review_passed,
            "required_gate_evidence": required_evidence,
            "missing_gate_evidence": missing_evidence,
            "missing_gate_evidence_without_review": [kind for kind in missing_evidence if kind != "review"],
            "complete": core_ready and gate_lab_passed and not missing_evidence,
        })
    return result


def command_status(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    if not db_path.exists():
        return {"ok": True, "state": "not_initialized"}
    connection = connect(db_path)
    try:
        stages = stage_status(connection)
        active = connection.execute("SELECT * FROM sessions WHERE status = 'active'").fetchone()
        due = connection.execute(
            """SELECT r.objective_id, o.title, r.due_at, r.interval_index
               FROM reviews r JOIN curriculum_objectives o ON o.objective_id = r.objective_id
               WHERE r.due_at <= ? AND o.retired = 0 ORDER BY r.due_at""",
            (utc_now(),),
        ).fetchall()
        mastery = get_mastery(connection)
        current_stage = next((stage for stage in stages if not stage["complete"]), None)
        cursor = connection.execute("SELECT * FROM curriculum_state WHERE id = 1").fetchone()
        return {
            "ok": True,
            "state": "active_session" if active else "ready",
            "active_session": dict(active) if active else None,
            "current_stage": current_stage,
            "curriculum_cursor": dict(cursor) if cursor else None,
            "mastery": {
                "objectives": len(mastery),
                "level_3_or_higher": sum(level >= 3 for level in mastery.values()),
                "level_4": sum(level == 4 for level in mastery.values()),
            },
            "due_reviews": [dict(row) for row in due],
            "next": select_next(connection),
            "stages": stages,
        }
    finally:
        connection.close()


def command_start_session(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    minutes = request.get("minutes", 25)
    if not isinstance(minutes, int) or not 5 <= minutes <= 240:
        raise StoreError("invalid_minutes", "minutes must be an integer from 5 to 240")
    mode = request.get("mode", "learning")
    if mode not in {"diagnostic", "learning", "review", "topic", "gate"}:
        raise StoreError("invalid_mode", "Unsupported session mode")
    connection = connect(db_path)
    try:
        mastery = get_mastery(connection)
        try:
            with connection:
                cursor = connection.execute(
                    """INSERT INTO sessions
                       (started_at, status, minutes, mode, note, start_mastery_sum, start_mastered_count)
                       VALUES (?, 'active', ?, ?, ?, ?, ?)""",
                    (utc_now(), minutes, mode, request.get("note"), sum(mastery.values()), sum(level >= 3 for level in mastery.values())),
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError("active_session_exists", "Resume or recover the existing active session") from exc
        return {"ok": True, "session_id": cursor.lastrowid, "minutes": minutes, "mode": mode, "next": select_next(connection)}
    finally:
        connection.close()


def get_active_session(connection: sqlite3.Connection) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM sessions WHERE status = 'active'").fetchone()
    if row is None:
        raise StoreError("no_active_session", "There is no active session")
    return row


def command_resume(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    connection = connect(db_path)
    try:
        session = get_active_session(connection)
        attempts = connection.execute(
            "SELECT * FROM attempts WHERE session_id = ? ORDER BY attempt_id DESC LIMIT 10", (session["session_id"],)
        ).fetchall()
        labs = connection.execute(
            "SELECT * FROM lab_runs WHERE session_id = ? ORDER BY run_id DESC LIMIT 10", (session["session_id"],)
        ).fetchall()
        return {"ok": True, "session": dict(session), "recent_attempts": [dict(row) for row in attempts], "recent_labs": [dict(row) for row in labs], "next": select_next(connection)}
    finally:
        connection.close()


def require_session(connection: sqlite3.Connection, session_id: Any) -> sqlite3.Row:
    if not isinstance(session_id, int):
        raise StoreError("invalid_session_id", "session_id must be an integer")
    row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None or row["status"] != "active":
        raise StoreError("session_not_active", "The specified session is not active")
    return row


def require_objective(connection: sqlite3.Connection, objective_id: Any) -> sqlite3.Row:
    if not isinstance(objective_id, str):
        raise StoreError("invalid_objective", "objective_id is required")
    row = connection.execute(
        OBJECTIVE_QUERY + " AND o.objective_id = ?", (objective_id,)
    ).fetchone()
    if row is None:
        raise StoreError("invalid_objective", f"Unknown objective: {objective_id}")
    return row


def command_next(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    connection = connect(db_path)
    try:
        return {"ok": True, **select_next(connection, request.get("topic"))}
    finally:
        connection.close()


def schedule_review(connection: sqlite3.Connection, objective_id: str, *, is_review: bool, success: bool) -> None:
    curriculum = load_curriculum()
    intervals = curriculum["review_intervals_days"]
    current = connection.execute("SELECT interval_index FROM reviews WHERE objective_id = ?", (objective_id,)).fetchone()
    if is_review:
        next_index = min((current["interval_index"] + 1) if current and success else 0, len(intervals) - 1)
    else:
        next_index = 0
    days = intervals[next_index] if success else intervals[0]
    connection.execute(
        """INSERT INTO reviews(objective_id, due_at, interval_index, last_result)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(objective_id) DO UPDATE SET
             due_at=excluded.due_at, interval_index=excluded.interval_index, last_result=excluded.last_result""",
        (objective_id, utc_after(days), next_index, int(success)),
    )


def command_record_attempt(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    kind = request.get("kind")
    curriculum = load_curriculum()
    if kind not in curriculum["evidence_kinds"]:
        raise StoreError("invalid_evidence_kind", f"Unsupported evidence kind: {kind}")
    success = request.get("success")
    mastery = request.get("mastery")
    if not isinstance(success, bool):
        raise StoreError("invalid_success", "success must be true or false")
    if not isinstance(mastery, int) or not 0 <= mastery <= 4:
        raise StoreError("invalid_mastery", "mastery must be an integer from 0 to 4")
    connection = connect(db_path)
    try:
        require_session(connection, request.get("session_id"))
        objective = require_objective(connection, request.get("objective_id"))
        current = connection.execute("SELECT level FROM mastery WHERE objective_id = ?", (objective["objective_id"],)).fetchone()["level"]
        if kind == "review":
            due_review = connection.execute(
                "SELECT due_at FROM reviews WHERE objective_id = ?", (objective["objective_id"],)
            ).fetchone()
            if due_review is None or due_review["due_at"] > utc_now():
                raise StoreError("review_not_due", "A delayed review is not due for this objective")
        ceiling = current if kind == "review" else EVIDENCE_CEILINGS[kind]
        if mastery > ceiling:
            raise StoreError("unsupported_mastery", f"Evidence kind {kind} supports mastery at most {ceiling}")
        new_level = max(current, mastery) if success else current
        with connection:
            cursor = connection.execute(
                """INSERT INTO attempts
                   (session_id, objective_id, created_at, kind, success, mastery, prompt, response, feedback)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request["session_id"], objective["objective_id"], utc_now(), kind, int(success), mastery,
                    request.get("prompt"), request.get("response"), request.get("feedback"),
                ),
            )
            if success and new_level > current:
                connection.execute(
                    "UPDATE mastery SET level = ?, updated_at = ? WHERE objective_id = ?",
                    (new_level, utc_now(), objective["objective_id"]),
                )
            connection.execute(
                """UPDATE curriculum_state
                   SET current_stage_id = ?, last_objective_id = ?, updated_at = ? WHERE id = 1""",
                (objective["stage_id"], objective["objective_id"], utc_now()),
            )
            schedule_review(connection, objective["objective_id"], is_review=(kind == "review"), success=success)
        return {"ok": True, "attempt_id": cursor.lastrowid, "objective_id": objective["objective_id"], "previous_mastery": current, "mastery": new_level, "review_scheduled": True}
    finally:
        connection.close()


def command_record_lab(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    success = request.get("success")
    duration = request.get("duration_ms")
    if not isinstance(success, bool) or not isinstance(duration, int) or duration < 0:
        raise StoreError("invalid_lab_result", "success must be boolean and duration_ms a nonnegative integer")
    lab_id = request.get("lab_id")
    command = request.get("command")
    if not isinstance(lab_id, str) or not lab_id or command not in {"build", "run", "repeat"}:
        raise StoreError("invalid_lab_result", "lab_id and a supported command are required")
    connection = connect(db_path)
    try:
        require_session(connection, request.get("session_id"))
        objective = require_objective(connection, request.get("objective_id"))
        assignment = connection.execute(
            """SELECT o.stage_id, o.lab_id AS objective_lab_id, s.gate_lab_id
               FROM curriculum_objectives o JOIN curriculum_stages s ON s.stage_id = o.stage_id
               WHERE o.objective_id = ? AND (? = o.lab_id OR ? = s.gate_lab_id)""",
            (objective["objective_id"], lab_id, lab_id),
        ).fetchone()
        if assignment is None:
            raise StoreError("invalid_lab_id", "lab_id is not assigned to this objective or its stage gate")
        with connection:
            cursor = connection.execute(
                """INSERT INTO lab_runs
                   (session_id, objective_id, lab_id, created_at, success, command, exit_code, duration_ms, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request["session_id"], objective["objective_id"], lab_id, utc_now(), int(success), command,
                    request.get("exit_code"), duration, request.get("summary"),
                ),
            )
            if lab_id == assignment["gate_lab_id"]:
                evidence = [
                    row["kind"]
                    for row in connection.execute(
                        """SELECT DISTINCT a.kind
                           FROM attempts a JOIN curriculum_objectives o ON o.objective_id = a.objective_id
                           WHERE o.stage_id = ? AND a.success = 1 ORDER BY a.kind""",
                        (assignment["stage_id"],),
                    )
                ]
                connection.execute(
                    """INSERT INTO stage_checkpoints
                       (session_id, stage_id, created_at, status, gate_lab_id, evidence_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        request["session_id"], assignment["stage_id"], utc_now(),
                        "passed" if success else "failed", lab_id,
                        json.dumps(evidence),
                    ),
                )
        return {"ok": True, "run_id": cursor.lastrowid}
    finally:
        connection.close()


def command_complete_session(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    connection = connect(db_path)
    try:
        session = require_session(connection, request.get("session_id"))
        mastery = get_mastery(connection)
        completed_count = sum(level >= 3 for level in mastery.values())
        mastery_sum = sum(mastery.values())
        stages = stage_status(connection)
        current_stage = next((stage for stage in stages if not stage["complete"]), None)
        with connection:
            connection.execute(
                "UPDATE sessions SET status = 'completed', ended_at = ?, summary = ? WHERE session_id = ?",
                (utc_now(), request.get("summary"), session["session_id"]),
            )
            connection.execute(
                "UPDATE curriculum_state SET current_stage_id = ?, updated_at = ? WHERE id = 1",
                (current_stage["stage_id"] if current_stage else None, utc_now()),
            )
        return {
            "ok": True,
            "session_id": session["session_id"],
            "status": "completed",
            "progress_delta": {
                "mastery_points": mastery_sum - session["start_mastery_sum"],
                "objectives_reaching_level_3": completed_count - session["start_mastered_count"],
            },
            "next": select_next(connection),
            "stages": stages,
        }
    finally:
        connection.close()


def command_recover(request: dict[str, Any]) -> dict[str, Any]:
    _, _, db_path = resolve_paths(request)
    connection = connect(db_path)
    try:
        session = get_active_session(connection)
        if request.get("abandon", False):
            with connection:
                connection.execute(
                    "UPDATE sessions SET status = 'abandoned', ended_at = ?, summary = ? WHERE session_id = ?",
                    (utc_now(), "Abandoned during recovery", session["session_id"]),
                )
            return {"ok": True, "session_id": session["session_id"], "status": "abandoned"}
        return command_resume(request)
    finally:
        connection.close()


def command_export(request: dict[str, Any]) -> dict[str, Any]:
    _, data_dir, db_path = resolve_paths(request)
    if request.get("format", "markdown") != "markdown":
        raise StoreError("unsupported_export", "Only markdown export is supported")
    connection = connect(db_path)
    try:
        stages = stage_status(connection)
        profile = connection.execute("SELECT * FROM learner_profile WHERE id = 1").fetchone()
        sessions = connection.execute("SELECT COUNT(*) AS count FROM sessions WHERE status = 'completed'").fetchone()["count"]
        lines = [
            "# C# Concurrency Learning Progress",
            "",
            f"Generated: {utc_now()}",
            f"Target framework: {profile['target_framework']}",
            f"Completed sessions: {sessions}",
            "",
            "## Stages",
            "",
        ]
        for stage in stages:
            marker = "complete" if stage["complete"] else "in progress"
            lines.append(
                f"- {stage['stage_id']} {stage['title']}: {stage['mastered_objectives']}/{stage['core_objectives']} objectives, {marker}; gate lab={stage['gate_lab_passed']}, delayed review={stage['delayed_review_passed']}"
            )
        lines.extend(["", "## Objective mastery", ""])
        for row in connection.execute(
            """SELECT o.objective_id, o.title, m.level
               FROM curriculum_objectives o
               JOIN curriculum_stages s ON s.stage_id = o.stage_id
               JOIN mastery m ON m.objective_id = o.objective_id
               WHERE o.retired = 0 AND s.retired = 0
               ORDER BY s.stage_order, o.position"""
        ):
            lines.append(f"- `{row['objective_id']}` {row['title']}: {row['level']}/4")
        export_dir = data_dir / "exports"
        export_dir.mkdir(exist_ok=True)
        output = export_dir / f"progress-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(output)}
    finally:
        connection.close()


COMMANDS = {
    "init": command_init,
    "status": command_status,
    "start-session": command_start_session,
    "resume": command_resume,
    "next": command_next,
    "record-attempt": command_record_attempt,
    "record-lab": command_record_lab,
    "complete-session": command_complete_session,
    "recover": command_recover,
    "export": command_export,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    try:
        response = COMMANDS[args.command](read_request())
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except StoreError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "message": exc.message}, ensure_ascii=False))
        return 2
    except sqlite3.OperationalError as exc:
        code = "database_busy" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "database_error"
        print(json.dumps({"ok": False, "error": code, "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
