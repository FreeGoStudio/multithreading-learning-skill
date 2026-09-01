# Curriculum guide

`curriculum-v1.json` is the authoritative graph. Each stage contains stable objective IDs, prerequisites, evidence requirements, and an optional lab ID. `scripts/learning_store.py next` resolves prerequisites and reviews without loading the entire graph into the conversation.

## Stages

0. **C# prerequisite bridge** — delegates, closures, generics, exceptions, lifetime, iterators, and asynchronous syntax prerequisites.
1. **Concurrency mental model** — processes, threads, scheduling, concurrency versus parallelism, CPU versus I/O work, shared state, and invariants.
2. **Threads and ThreadPool** — raw thread lifecycle, foreground/background behavior, joins, thread-local state, execution context, queues, blocking, and starvation.
3. **Memory model and synchronization** — atomicity, visibility, ordering, `lock`, `Monitor`, `Interlocked`, `Volatile`, fences, and safe publication.
4. **Synchronization primitives and pathologies** — semaphores, mutexes, events, reader/writer locks, barriers, spinning, deadlock, livelock, starvation, and priority inversion.
5. **Task and async** — Task semantics, continuations, schedulers, contexts, async state machines, cancellation, exceptions, `ValueTask`, and `TaskCompletionSource`.
6. **Parallel data and coordination** — `Parallel`, PLINQ, partitioning, concurrent collections, `BlockingCollection`, channels, async streams, producer/consumer design, backpressure, and rate limiting.
7. **Runtime internals** — pool injection, hill-climbing, global/local queues, work stealing, I/O completion, timer queues, continuation scheduling, and CoreCLR source navigation.
8. **Lock-free and hardware effects** — CAS loops, ABA, progress guarantees, coherence, false sharing, fences, and proof obligations.
9. **Windows concurrency and diagnostics** — UI dispatch, COM apartments, ETW, PerfView, Visual Studio parallel tooling, dumps, and wait analysis.
10. **Production design** — ASP.NET Core, hosted services, cache and batch patterns, timeout propagation, structured cancellation, overload control, observability, and recovery.
11. **Performance diagnostics** — trustworthy benchmarks, BenchmarkDotNet boundary, counters, EventPipe traces, pool starvation, contention, and CPU analysis.
12. **Expert capstone** — race repair, bounded pipeline design, starvation diagnosis, measurement evidence, and written tradeoff defense.

## Selection rules

1. Return overdue reviews before new material, oldest due first.
2. Otherwise return the first core objective whose prerequisites are at least mastery 2 and whose own mastery is below 3.
3. Within a stage, prefer a partially learned objective over an untouched objective.
4. Do not select a later stage while an earlier stage has an incomplete core objective, except for an explicit topic insertion.
5. For an inserted topic, return the requested objective plus prerequisites below mastery 2; bridge those prerequisites without silently advancing unrelated stages.
6. Stage gates are assessments, not teaching shortcuts. The learner must complete each objective's evidence in ordinary or remediation sessions.

## Evidence interpretation

- `concept`: accurate explanation and boundary.
- `prediction`: predicts allowed outcomes and rejects impossible ones.
- `code`: implements or repairs code while preserving an explicit invariant.
- `lab`: produces a bounded, repeatable result and interprets nondeterminism correctly.
- `diagnosis`: moves from symptom to cause using evidence.
- `tradeoff`: chooses among valid designs based on workload and failure constraints.
- `review`: delayed, varied retrieval after the original session.

An attempt may support several evidence types, but one successful explanation must not automatically satisfy code, lab, diagnosis, or review evidence.

## Version policy

Default to .NET 10 and C# 14 when installed. Adjust target frameworks to the newest installed stable SDK when necessary. Explain meaningful differences for .NET 8 and later. For C# 13/.NET 9 and later, prefer a dedicated `System.Threading.Lock` for ordinary mutual exclusion. Keep .NET Framework-only APIs in historical or migration notes and never present `Thread.Abort`, thread suspension, or asynchronous delegates as modern recommendations.

Primary references:

- https://learn.microsoft.com/dotnet/standard/threading/threads-and-threading
- https://learn.microsoft.com/dotnet/standard/threading/threading-objects-and-features
- https://learn.microsoft.com/dotnet/standard/parallel-programming/
- https://learn.microsoft.com/dotnet/csharp/asynchronous-programming/
- https://learn.microsoft.com/dotnet/core/diagnostics/
