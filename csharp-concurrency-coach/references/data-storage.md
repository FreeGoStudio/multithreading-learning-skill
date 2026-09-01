# Persistent learning data

SQLite in the learner project is authoritative. Interact only through `scripts/learning_store.py <command>` with one UTF-8 JSON object on stdin. The script emits one JSON object on stdout and uses a nonzero exit code with `{ "ok": false, "error": ... }` on failure.

## Location and safety

The required input field is `project_root`; it resolves to an existing directory. Data lives under:

```text
<project_root>/.csharp-concurrency-learning/
|-- learning.db
|-- labs/
`-- exports/
```

The script refuses a data directory inside the Skill source directory, enables foreign keys and WAL, sets a busy timeout, and commits state transitions atomically. One project represents one learner and may have only one active session.

## Commands

Examples show the JSON shape; add `project_root` to every request.

- `init`: `{ "learner_note": "optional", "target_framework": "net10.0" }`. Idempotently creates the database and imports the curriculum snapshot.
- `status`: `{}`. Returns initialization state, active session, current stage, mastery counts, due reviews, and the next eligible objective.
- `start-session`: `{ "minutes": 25, "mode": "learning", "note": "optional" }`. Modes: `diagnostic`, `learning`, `review`, `topic`, `gate`.
- `resume`: `{}`. Returns the active session and recent uncommitted learning events; errors when none exists.
- `next`: `{ "topic": "optional objective ID, title, or tag" }`. Without a topic, returns the oldest due review or next eligible core objective. With a topic, also returns prerequisite gaps.
- `record-attempt`: `{ "session_id": 1, "objective_id": "s1.shared-state", "kind": "prediction", "success": true, "mastery": 2, "prompt": "...", "response": "...", "feedback": "..." }`. `kind` must be one curriculum evidence kind. Mastery is 0–4 and may not jump above the evidence ceiling enforced by the script.
- `record-lab`: `{ "session_id": 1, "objective_id": "...", "lab_id": "lab-race-counter", "success": true, "command": "run", "exit_code": 0, "duration_ms": 820, "summary": "..." }`.
- `complete-session`: `{ "session_id": 1, "summary": "..." }`. Atomically closes the session, advances eligible review schedules, and returns progress deltas.
- `recover`: `{ "abandon": false }`. Returns the active session after interruption. With `abandon: true`, closes it as abandoned without changing mastery.
- `export`: `{ "format": "markdown" }`. Writes a derived progress report under `exports/`; SQLite remains authoritative.

## Evidence and reviews

An attempt stores one evidence kind. The maximum defensible mastery from a single kind is:

- recognize/concept: 2;
- prediction: 2;
- code or lab: 3;
- diagnosis or tradeoff: 4;
- review: the current mastery, never an automatic increase.

The script keeps the maximum supported mastery; a failed attempt records evidence and schedules remediation but does not erase earlier success. A successful non-review attempt schedules a review after 1 day. Successful reviews advance intervals through 3, 7, 14, then 30 days. Failed reviews reset to 1 day.

## Failure handling

- If `not_initialized`, call `init`; do not infer progress from files.
- If a write returns `database_busy`, stop and retry once after checking for another active process. Do not loop.
- If a session is active after interruption, call `resume` or `recover`; do not start a second session.
- If curriculum versions differ, the migration must preserve attempts and mastery by stable objective ID. Unknown retired IDs remain reportable but are not selected.
- Never construct SQL in the teaching conversation, edit `learning.db`, or delete learning data as recovery.
