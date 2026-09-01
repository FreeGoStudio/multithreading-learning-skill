# CLR runtime and hardware track

Read this reference only for stages 7–8 or when an earlier question depends on runtime mechanics. Keep four layers distinct: C# language guarantees, CLI/.NET memory model, CoreCLR implementation, and OS/hardware behavior.

## ThreadPool model

Teach these as current CoreCLR implementation concepts, not permanent API contracts:

- one process-wide managed pool with worker and I/O completion paths;
- global injection queues plus per-worker local queues;
- work stealing and the locality/fairness tradeoff;
- hill-climbing and blocking compensation;
- starvation caused by sync-over-async, long blocking work, or excessive queued work;
- `TaskScheduler.Default` as a consumer of ThreadPool behavior, not a promise that every Task creates or occupies a thread;
- `ExecutionContext` capture and the semantic/performance tradeoff of suppressing flow.

Have the learner connect each mechanism to observable counters or traces. Avoid promising exact queue order, worker counts, or injection timing.

## Async and I/O completion

Distinguish asynchronous waiting from parallel execution. Explain state-machine suspension, completion signaling, continuation scheduling, context capture, and why an incomplete async I/O normally does not reserve a blocked worker. Include cases that do consume workers: synchronous wrappers, CPU work before the first suspension, synchronous continuations, and blocking callbacks.

## Memory ordering

Start from program invariants and happens-before relationships supplied by synchronization. Cover:

- atomicity versus visibility versus ordering;
- safe publication through locks, volatile access, interlocked operations, task completion, and concurrent collection contracts;
- acquire/release intuition without claiming a particular CPU instruction;
- why `volatile` does not make compound operations atomic;
- why double-checked initialization needs a proven publication pattern;
- cache lines and false sharing as a performance mechanism, not a C# correctness rule.

Use litmus-style experiments only to illustrate allowed outcomes; JIT, architecture, and timing may prevent a legal result from appearing.

## Lock-free reasoning

Require the learner to state the linearization point, invariant, progress guarantee, lifetime/reclamation assumption, and ABA exposure of a CAS loop. Prefer framework concurrent collections in production unless a measured constraint and a reviewable proof justify custom lock-free code.

Cover obstruction-free, lock-free, and wait-free as system progress properties. Do not infer them merely from the presence of `Interlocked`.

## CoreCLR source study

Navigate by behavior and tests rather than memorizing file paths that may change. Search the current `dotnet/runtime` repository for public type names, native entry points, event names, and tests. Verify version-specific claims against the source tag matching the runtime under discussion. Source browsing is optional and read-only; do not clone or download a large repository without authorization.

Primary references:

- https://learn.microsoft.com/dotnet/standard/threading/the-managed-thread-pool
- https://learn.microsoft.com/dotnet/standard/threading/managed-threading-best-practices
- https://github.com/dotnet/runtime
