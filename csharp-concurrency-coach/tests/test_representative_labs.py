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


RACE_LAB = r'''
const int Workers = 8;
const int PerWorker = 100_000;
var unsafeCount = 0;
Parallel.For(0, Workers, _ =>
{
    for (var index = 0; index < PerWorker; index++)
    {
        unsafeCount++;
    }
});

var safeCount = 0;
Parallel.For(0, Workers, _ =>
{
    for (var index = 0; index < PerWorker; index++)
    {
        Interlocked.Increment(ref safeCount);
    }
});

LabAssertions.Equal(Workers * PerWorker, safeCount, "Interlocked preserves every increment");
Console.WriteLine($"Unsafe={unsafeCount}, Safe={safeCount}");
Console.WriteLine("LAB_RESULT: PASS");
'''


DEADLOCK_LAB = r'''
var first = new object();
var second = new object();
using var rendezvous = new Barrier(2);
var timedOut = 0;

void AcquireInOrder(object outer, object inner)
{
    Monitor.Enter(outer);
    try
    {
        rendezvous.SignalAndWait();
        if (Monitor.TryEnter(inner, TimeSpan.FromMilliseconds(250)))
        {
            Monitor.Exit(inner);
        }
        else
        {
            Interlocked.Increment(ref timedOut);
        }
    }
    finally
    {
        Monitor.Exit(outer);
    }
}

var left = new Thread(() => AcquireInOrder(first, second));
var right = new Thread(() => AcquireInOrder(second, first));
left.Start();
right.Start();
left.Join();
right.Join();

LabAssertions.Equal(2, timedOut, "timed acquisition exposes the circular wait without hanging");
Console.WriteLine("LAB_RESULT: PASS");
'''


CHANNEL_LAB = r'''
using System.Threading.Channels;

var channel = Channel.CreateBounded<int>(new BoundedChannelOptions(4)
{
    FullMode = BoundedChannelFullMode.Wait,
    SingleWriter = true,
    SingleReader = false
});
var count = 0;
var sum = 0;

var consumers = Enumerable.Range(0, 3).Select(async _ =>
{
    await foreach (var value in channel.Reader.ReadAllAsync())
    {
        Interlocked.Increment(ref count);
        Interlocked.Add(ref sum, value);
        await Task.Yield();
    }
}).ToArray();

for (var value = 1; value <= 100; value++)
{
    await channel.Writer.WriteAsync(value);
}
channel.Writer.Complete();
await Task.WhenAll(consumers);

LabAssertions.Equal(100, count, "every item is consumed exactly once");
LabAssertions.Equal(5050, sum, "the bounded pipeline preserves all values");
Console.WriteLine("LAB_RESULT: PASS");
'''


STARVATION_LAB = r'''
ThreadPool.GetMinThreads(out _, out var minIo);
ThreadPool.GetMaxThreads(out _, out var maxIo);
LabAssertions.True(ThreadPool.SetMinThreads(2, minIo), "set two minimum worker threads");
LabAssertions.True(ThreadPool.SetMaxThreads(2, maxIo), "cap workers inside this disposable lab process");

using var release = new ManualResetEventSlim(false);
using var started = new CountdownEvent(2);
var blockers = Enumerable.Range(0, 2).Select(_ => Task.Run(() =>
{
    started.Signal();
    release.Wait();
})).ToArray();

LabAssertions.True(started.Wait(TimeSpan.FromSeconds(2)), "both pool workers entered blocking work");
var probe = Task.Run(() => 42);
Thread.Sleep(200); // Demonstration scaffolding: it is not synchronization for correctness.
LabAssertions.True(!probe.IsCompleted, "queued work cannot run while every capped worker is blocked");
release.Set();
await Task.WhenAll(blockers);
LabAssertions.Equal(42, await probe, "queued work resumes after workers are released");
Console.WriteLine("LAB_RESULT: PASS");
'''


class RepresentativeLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.project = Path(cls.temp.name)
        code, response = invoke(
            STORE, "init", {"project_root": str(cls.project), "target_framework": "net10.0"}
        )
        if code != 0:
            raise AssertionError(response)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_lab(self, lab_id, objective_id, source):
        base = {"project_root": str(self.project), "lab_id": lab_id}
        code, created = invoke(
            MANAGER,
            "create",
            {**base, "objective_id": objective_id, "target_framework": "net10.0"},
        )
        self.assertEqual(0, code, created)
        Path(created["program"]).write_text(source.strip() + "\n", encoding="utf-8")
        code, built = invoke(
            MANAGER,
            "build",
            {**base, "configuration": "Release", "timeout_seconds": 60},
        )
        self.assertEqual(0, code, built)
        self.assertTrue(built["success"], built)
        code, ran = invoke(
            MANAGER,
            "run",
            {**base, "configuration": "Release", "timeout_seconds": 10},
        )
        self.assertEqual(0, code, ran)
        self.assertTrue(ran["success"], ran)
        self.assertIn("LAB_RESULT: PASS", ran["stdout"])

    def test_race_and_atomic_repair(self):
        self.run_lab("acceptance-race", "s3.atomicity-race", RACE_LAB)

    def test_bounded_deadlock_demonstration(self):
        self.run_lab("acceptance-deadlock", "s4.deadlock", DEADLOCK_LAB)

    def test_bounded_channel_pipeline(self):
        self.run_lab("acceptance-channel", "s6.channels", CHANNEL_LAB)

    def test_threadpool_starvation_and_release(self):
        self.run_lab("acceptance-starvation", "s11.pool-starvation", STARVATION_LAB)


if __name__ == "__main__":
    unittest.main()
