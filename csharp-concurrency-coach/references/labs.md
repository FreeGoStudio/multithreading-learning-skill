# Runnable labs

Use `scripts/lab_manager.py <command>` with UTF-8 JSON on stdin. Every request includes `project_root`. The manager confines paths to `<project_root>/.csharp-concurrency-learning/labs`, invokes only the `dotnet` executable, and returns structured JSON.

## Commands

- `create`: `{ "lab_id": "lab-race-counter", "objective_id": "s3.race-atomicity", "target_framework": "net10.0", "overwrite": false }`. Copies the no-package console harness and returns paths to `Program.cs` and the project file. It never overwrites an existing lab unless `overwrite` is true; request authorization before overwriting learner work.
- `build`: `{ "lab_id": "...", "configuration": "Debug", "timeout_seconds": 30 }`.
- `run`: `{ "lab_id": "...", "configuration": "Debug", "timeout_seconds": 10, "arguments": [] }`.
- `repeat`: `{ "lab_id": "...", "configuration": "Release", "timeout_seconds": 10, "repetitions": 20, "arguments": [] }`. Repetitions are capped at 100 and stop on timeout.

`timeout_seconds` is capped at 60. The manager kills the process tree on timeout. It does not restore packages from the network, add package references, run arbitrary commands, or delete labs.

## Lab contract

Each experiment must state:

1. the objective and invariant;
2. the learner's prediction before execution;
3. which outcomes are allowed, forbidden, or merely likely;
4. the bounded load and cancellation/timeout behavior;
5. the observation and its limits;
6. the repair and at least one alternative with tradeoffs;
7. a changed-input variation.

The included harness supports simple invariant checks without a test package. Replace the starter body with objective-specific code, but keep the cancellation source and top-level exception reporting.

## Reliability rules

- Never treat console line order as a correctness assertion unless ordering is the explicit invariant.
- A race demonstration may report that it did not reproduce. Repeat with a bounded count and explain that absence of failure is not proof.
- Use Debug while teaching control flow and Release for performance observations. Never compare their timings as equivalent.
- Warm up before timing. Prefer ratios and distributions over one duration.
- Keep ordinary labs below 10 seconds and below `max(2, Environment.ProcessorCount)` active workers unless the objective requires a documented variation.
- Do not use `Thread.Sleep` as proof of coordination; it may widen a race window only when labeled as demonstration scaffolding.
- Deadlock labs must use cancellation, timed acquisition, or a parent-process timeout so the learner cannot strand the session.

## External tooling boundary

The current environment may not contain `dotnet-counters`, `dotnet-trace`, PerfView, or BenchmarkDotNet. Detect first. Installing a global tool, downloading PerfView, or adding a NuGet package requires explicit authorization. Without it, use the built-in harness, `Stopwatch` with its limitations explained, `EventSource`/runtime metrics already available, or a recorded trace walkthrough.
