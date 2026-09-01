# Windows concurrency and diagnostics

Read this reference for stage 9, stage 11, or a Windows-specific symptom. Begin with the least invasive evidence source and increase collection cost only when necessary.

## UI and platform model

Cover WinForms `SynchronizationContext`, WPF `Dispatcher`, thread affinity, message pumping, reentrancy, and deadlock caused by blocking the UI thread on asynchronous work. Include COM STA/MTA only after the learner can explain ordinary context capture. Label Windows-only behavior and contrast it with context-free ASP.NET Core execution.

## Diagnostic ladder

1. Reproduce with an explicit invariant, bounded load, timestamps, thread IDs, and Task IDs where useful.
2. Inspect runtime metrics for pool size, queue length, completed work, CPU, allocation, and exception signals.
3. Collect an EventPipe trace with `dotnet-trace` when installed; prefer a short duration and a named output under the learning directory.
4. Use Visual Studio Parallel Stacks/Tasks or PerfView for thread activity, contention, and stacks.
5. Capture a dump only when a hang or rare state cannot be explained by lighter evidence. Dumps may contain secrets; obtain explicit authorization and keep them in the learning directory.
6. Use ETW/WPA or wait-chain analysis when kernel scheduling, native frames, or process-wide Windows activity is necessary.

EventPipe is cross-platform and provides managed/runtime events; ETW can add Windows kernel and native context. Absence of a tool is not permission to install it.

## Tool-specific outcomes

- `dotnet-counters`: identify trends and choose the next collection, not prove a root cause by one counter.
- `dotnet-trace`: correlate ThreadPool, contention, CPU samples, Tasks, and application events over time.
- PerfView: inspect CPU stacks, thread-time, contention, and ETW/EventPipe data while controlling symbol and collection cost.
- Visual Studio: freeze a reproducible state and connect Tasks to stacks; avoid assuming debugger timing reflects production timing.
- dumps: enumerate managed threads, stacks, locks, and waiting Tasks; treat snapshots as one instant.

## Safety

- Detect tools with read-only commands before suggesting installation.
- Ask before installing global tools, downloading executables, enabling privileged providers, or attaching to a process outside the lab.
- Keep trace duration at 30 seconds or less by default and state expected disk/CPU impact.
- Do not publish trace or dump contents. Redact paths, arguments, environment values, and application payloads from learning notes.
- Stop after one failed privileged attempt and offer a lower-privilege fallback.

Primary references:

- https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-counters
- https://learn.microsoft.com/dotnet/core/diagnostics/dotnet-trace
- https://learn.microsoft.com/dotnet/core/diagnostics/eventpipe
- https://github.com/microsoft/perfview
