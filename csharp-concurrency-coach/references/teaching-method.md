# Teaching method

## Session shape

Adapt depth to the available time without changing the mastery standard.

- 10 minutes: one retrieval prompt, one concept, one prediction or code repair.
- 25 minutes: due review, one concept, one runnable lab, recap.
- 45 minutes: review, concept model, lab, variation, short diagnostic.
- 90 minutes: a complete objective cluster or stage gate with measurement and postmortem.

Use Chinese explanations and retain terms such as race condition（竞态条件）, visibility（可见性）, work stealing（工作窃取）, and backpressure（背压）. Prefer concrete execution timelines and invariants over metaphors. If using a metaphor, state where it stops being accurate.

## First diagnostic

The learner reports only basic C# syntax, so begin with short evidence-producing tasks:

1. Explain what a delegate captures and predict a closure-in-a-loop result.
2. Read a generic method and identify shared mutable state.
3. Explain exception propagation across a direct call and a Task.
4. Predict two possible outputs from unsynchronized increments.
5. Distinguish concurrency, parallelism, and asynchronous waiting in a small scenario.

Record the demonstrated level for the mapped objectives. When the learner cannot answer, teach without framing the result as failure.

## Core learning loop

For each objective:

1. **Prediction**: ask for an output, invariant, failure mode, or performance expectation.
2. **Experiment**: run a bounded lab that can falsify the prediction. Explain nondeterminism before interpreting output.
3. **Explanation**: have the learner identify the guarantee and the mechanism. Correct confusion among C#, CLR, OS, and hardware layers.
4. **Repair**: require a minimal correct change and a reason for choosing it over alternatives.
5. **Variation**: change load, cancellation, exception, ordering, or platform constraints.

Do not give a mastery score from confidence or vocabulary alone. Use code, predictions, diagnostic evidence, and tradeoff explanations.

## Reviews and remediation

Use intervals of 1, 3, 7, 14, and 30 days after successful evidence. Failure returns the item to the next session and resets the interval to 1 day; it does not reduce unrelated mastery. Avoid exact repeats: change names, interleaving, data size, or requested reasoning.

When a learner is stuck, identify the smallest missing prerequisite, teach it, and return to the original objective in the same session when time permits. At a failed stage gate, create a remediation set from the failed evidence types: concept, code, diagnosis, or measurement.

## Topic insertion and code diagnosis

Map free-choice topics and real bugs to one or more curriculum objective IDs. State the missing prerequisites but answer the requested topic. For user code, reproduce the smallest safe case inside the learning directory; do not edit production files unless asked. Separate:

- the observed symptom;
- the violated invariant;
- the synchronization or scheduling cause;
- the minimal repair;
- alternative designs and their costs;
- how to verify the repair under repetition and diagnostics.

## Feedback format

Keep feedback compact:

- conclusion and evidence;
- one corrected mental model;
- one next action;
- mastery change only when recorded.

At session end, report completed objectives, evidence collected, due reviews, current stage gate status, and the next eligible objective.
