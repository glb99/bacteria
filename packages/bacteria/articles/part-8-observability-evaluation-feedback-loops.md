# The Agent Stack — Part 8: Observability, Evaluation, and Production Feedback Loops

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-8-observability
- **Published:** 2026-05-18
- **Fetched into this repo:** 2026-08-02 (provided directly by the user as a PDF)

## Thesis

"A demo is allowed to be a story. Production is not." A demo ends when the answer looks right — it proves one path can work. Production asks a different question: can you reconstruct the path when it doesn't work, judge whether the behavior was acceptable, and change what ships next? Three distinct jobs, kept separate: **observability** preserves the run (what happened), **evaluation** judges the behavior (was it good), **feedback loops** decide what changes before the next release (did the system actually learn). This is the final part of the series — it's also where the whole stack's boundaries get tested for real, because production is a reconstruction problem, not a narration.

## Observability answers "what happened," not "was it good"

"A trace is not a verdict. It explains what happened. It does not decide whether the behavior was acceptable." A trace that only captures the model request misses the system — a real agent run crosses a channel, the control plane, context assembly, the model call, tool exposure/calls, policy/approval boundaries, execution, and the response back to the user. "A run is not one operation. It is a chain of operations with causality between them." For a meaningful run, the article wants to be able to reconstruct: run/session ID, the triggering event, model+prompt version, assembled context, retrieved documents/memories, tools exposed, tool calls requested, validation/policy decisions, the approval decision (if any), the execution result, any side effect, the final response, and the relevant versions of everything involved (prompts, tools, policies, retrieval configs, memory rules).

## A trace is not an audit trail

A trace asks "where did the run go, what executed, where did time go, what failed." An **audit trail** asks "who or what acted, under which identity, what scope, what policy applied, was approval required, who approved it, what changed, what was the result." Related, sharing identifiers, but not the same responsibility — collapsing them into one "logs" bucket makes the debug stream too sensitive/noisy for engineering use *and* the audit record too weak for accountability. The rule: "trace the execution. Audit the authority." This matters more for agents than ordinary services because the same user-visible answer can hide very different authority paths underneath — the model may suggest, the runtime may decide, the policy layer may allow, the execution surface may act, and only the audit trail preserves which one actually happened.

## Evaluation is judgment, not telemetry

Tracing and evals are not each other, and an LLM judge isn't observability either. "A trace can describe a bad run perfectly... The trace still does not decide whether the behavior met the bar." For agents, judgment can't stop at the final answer — a good-sounding response can still have used the wrong source, skipped a policy check, picked the wrong tool, passed the wrong argument, or changed the wrong object. The eval target has to match the system: a writing assistant cares about response quality; a support agent cares about policy adherence/escalation; a refund agent cares about final-state correctness; a database agent cares about query safety/authorization; a retrieval-heavy agent cares about groundedness; a long-running workflow cares about resumability/step correctness.

Three different kinds of checks, not one: **deterministic** (did it call the right tool, pass the right ID, stay under budget, get approval before the side effect — write an assertion, don't ask a model judge to prove something the system can already assert), **rubric-based** (clarity, faithfulness to retrieved evidence — subjective, needs calibration), and **human review** (was the policy interpretation or escalation actually correct). "Evaluation is not one magic score. It is a set of judgments attached to the parts of the run that matter."

## Feedback is not learning until the system changes

The most important boundary in the article. A thumbs-down, a human annotation, a bad trace, an online-eval failure — none of these are learning by themselves. They're signals. "The system only improves when a process turns those signals into a change": a regression test, a dataset item, a prompt/tool-schema/retrieval/memory-policy change, a routing rule, an approval threshold, a sandbox restriction, a runtime fix, a release gate. The concrete loop: bad production run → trace + audit record → triage → label the failure → create a dataset item → add a regression test → change prompt/policy/retrieval/tool/runtime → release gate → canary/rollout → online monitoring → (repeat on new failure). "The important box is not the dashboard. It is the release gate. A dashboard informs someone. A gate changes what ships."

## Definitions

- **Trace** — explains execution: where the run went, what executed, where time was spent, what failed.
- **Audit trail** — preserves accountability: who/what acted, under what identity/scope/policy, was approval required and by whom, what changed, what was the result.
- **Evaluation** — judgment applied to evidence, targeted at the parts of the run that actually matter for that system, not just the final answer.
- **Feedback loop** — the process that turns a signal (annotation, failure, eval result) into an actual system change; without it, feedback is "just a labeled observation."
- **Release gate** — the mechanism that actually blocks a worse version from shipping, as opposed to a dashboard that only informs.

## Failure modes named

1. **Treating traces as proof of quality** — a trace can show exactly what happened and still describe a bad run; tracing gives evidence, not judgment.
2. **Evaluating only the final answer** — for agents that act, tool choice, arguments, approval, and final state all matter, not just the visible response.
3. **Losing session identity** — cross-turn failures (stale memory, wrong session, a summarized transcript that dropped a constraint) turn into fragments instead of a reconstructable run if traces aren't tied to session identity.
4. **Burying audit records inside debug logs** — debug logs are tuned for engineering diagnosis; audit records are tuned for accountability; conflating them weakens both.
5. **Collecting feedback with no path to action** — "a label with no owner is not a loop."
6. **Building dashboards that never gate releases** — a dashboard says the system got worse; only a gate stops the worse version from shipping.
7. **Over-trusting model graders** — useful for fuzzy judgment, not a replacement for deterministic checks, policy assertions, human review, or final-state validation.
8. **Creating an observability privacy problem** — traces can carry prompts, responses, retrieved documents, tool outputs, user identifiers, and app state; more evidence isn't better if the evidence itself becomes a new sensitive-data liability. Needs retention, access control, redaction, sampling rules.

## Builder checklist from the article

1. Every meaningful run has a trace ID and session ID — a user-visible outcome must map back to the run that produced it.
2. The trace crosses the whole stack — context assembly, model calls, tool exposure/calls, policy checks, approvals, execution results, final response.
3. Every side effect has an audit record — trace the execution, audit the authority.
4. Important versions are reconstructable — prompt, model, tool schema, policy, retrieval config, memory rule, runtime version.
5. Evaluation targets the path and the outcome, not just final-answer quality — tool correctness, approval behavior, policy adherence, retrieval quality, final state.
6. Known failures become regressions — "a serious failure is not closed until the system can detect that class of failure again."
7. High-risk releases have gates — evals, SLOs, policy assertions, latency, cost, known-regression coverage decide what ships.
8. Feedback has an owner — user feedback, human review, online evals, and incidents need an actual path into datasets, tests, prompts, policies, tools, or runtime changes.

## Series close — the one-sentence summary

"Model output becomes bounded action only when the surrounding system owns the boundaries." Interfaces create events; the control plane decides what the run is; the runtime decides how the run proceeds; the model generates inside the context it's given; context/retrieval/memory shape what it sees; tools expose capabilities; execution surfaces turn calls into side effects; identity/policy/approval decide what's allowed; observability/evaluation/feedback decide whether the system can explain itself and improve. That's the difference between a demo and an operated system.
