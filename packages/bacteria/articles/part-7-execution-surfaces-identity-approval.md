# The Agent Stack — Part 7: Execution Surfaces, Identity, and Approval Boundaries

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-7-execution
- **Published:** 2026-05-11
- **Fetched into this repo:** 2026-08-02

## Thesis

"Capability exposure is not execution authority." Part 6 covered what the model may *ask for*. This part covers what happens between the ask and the actual side effect — under whose identity it runs, inside what blast radius, gated by what policy/approval, contained by what sandboxing, leaving what evidence. "The tool is the contract. The execution surface is where the contract becomes real."

## A tool is not an execution surface

The capability surface (what the model can see) and the execution surface (where the action actually runs) are different things entirely:
- A `send_email` tool ≠ the mail system.
- Browser automation ≠ an authenticated browser session.
- A code-execution tool ≠ a shell in production.
- A database tool ≠ the database, its transaction boundary, or its tenant scope.

"Do not reason about execution in the abstract. Name the surface." A weather API call is not a production database call; an authenticated banking session is not a secrets-free sandbox; a shell on a dev laptop is not a shell with unrestricted network egress — even if the *tool schema* looks identical in all cases.

## Execution surfaces have different blast radii

Browser (clicks/forms/cookies — commits authenticated workflows, not just retrieval), code runners (file I/O, imports, runtime limits), shells (mutates repos, starts processes, reads env vars, hits the network), filesystem (read/write/delete — MCP's "roots" is the concrete example of boundary definition), APIs/databases (their own authority: refunds, CRM updates, migrations, deletes), devices/actuators (physical, often irreversible, unsafe to retry). Each needs controls sized to its own risk, not a single generic "sandboxed = safe" answer.

## Identity is the envelope around action

An agent doesn't just "do something" — it acts *as* someone or something, under authority derived from OAuth tokens, service accounts, API keys, browser cookies, DB credentials, connectors, filesystem mounts, or device channels. Four OAuth-flavored concepts, kept distinct: **authentication** (who is this), **authorization** (what can they do), **delegation** (what access was granted to *this client* specifically), **approval** (should this action proceed *now*). Conflating them causes authority leaks:

- "The user is logged in" ≠ "the agent may send any email the user could send."
- "The backend can access the database" ≠ "the model may mutate any row."
- "The browser session is authenticated" ≠ "browser automation is safe."

**Session continuity is not authority.** A session says the same user is still present; it does not prove that a specific action should run with specific tokens against specific resources right now.

**Identity envelope questions**, which the *system* must answer (not the model): who is the user; what service executes; delegated vs. service authority (or both); what scopes attach; what tenant/account/project/repo/workspace is in scope; which credentials are available; how long authority lasts; whether it's revocable.

## Policy, approval, and sandboxing are different controls

- **Policy** — decides whether an action is allowed (principal, action, resource, context, tenant, risk tier, time, environment, approval state).
- **Enforcement** — actually applies that decision (adapters, gateways, proxies, wrappers, sandbox launchers). Policy without enforcement is documentation.
- **Approval** — confirms *this specific* action, right now. Distinct from authorization: a user authorized to delete a file may still require approval for the agent doing the deleting.
- **Sandboxing** — contains execution (filesystem/process/network/credential/tenant/artifact isolation). Reduces damage *if* the wrong thing runs; does not decide whether it should run.
- **Guardrails** — validate inputs/outputs/tool calls (prompt-injection classifiers, content filters). Useful, but not a substitute for authorization or tenant checks.

"Approval is a decision point. Isolation is a blast-radius limit." Don't ask one control to do another's job.

## Put the approval boundary near the side effect

Approval is strongest right where preparation becomes commitment: drafting vs. sending, filling vs. submitting, generating vs. running SQL, staging vs. deleting, calculating vs. issuing a refund. Blanket approval at task start ("can I help pay this invoice?") is weak — by the time the actual side effect happens, the approval no longer means anything specific. Specific approval ("approve $4,812.43 to [recipient] from [account]") gives real context and a clean audit point.

**Generally needs approval:** external sends/submits/purchases/shares/refunds/transfers/posts; destructive ops (delete/revoke/overwrite/terminate/drop); hard-to-reverse ops (migrations, prod deploys); access to sensitive private data; new recipients/domains/accounts/destinations; physical-world actions; cross-tenant/workspace/repo/account actions; privilege escalation or new credential access.

**Good approval text** reads like a tiny change request: what happens, who acts, where, what data is touched, what changes or sends, is it reversible, what evidence supports it. If the system can't answer these, it isn't ready to execute.

## The invariant: authority does not silently flow

Prompt injection changes character once tools can act. In pure chat, bad instructions produce a bad answer. Once tools act, malicious content can steer a *privileged executor* — the confused deputy problem.

> "Untrusted content must not silently increase the authority available to the agent."

Violations: a webpage grants new tool access; a retrieved document expands OAuth scope; tool output changes tenant context; a webpage turns a read-only task into a send action; memory smuggles in a policy exception; a code sandbox receives production secrets it shouldn't have.

"The executor, not the model, owns the boundary. The system stays sane because the boundary is enforced, not because the model promises to behave."

## Definitions

- **Execution surface** — where a capability actually runs: under an identity, inside a blast radius, with policy, approval, containment, and evidence.
- **Identity envelope** — who executes, what service, delegated vs. service authority, scopes, tenant scope, available credentials, lifetime, revocability.
- **Blast radius** — the scope of potential damage from one execution.
- **Approval boundary** — the point where preparation becomes an irreversible commitment.
- **Confused deputy problem** — untrusted content causes a privileged executor to act beyond its intended scope.

## Failure modes named

1. **Tool visibility treated as permission** — appearing in the model's tool list ≠ available authority; the executor still needs identity, policy, enforcement, approval.
2. **Acting through one broad service credential** — every action runs via a powerful backend token, so a confused/injected tool call escalates straight to service-level authority instead of user scope.
3. **Reusing browser contexts as plain state** — a browser context carries cookies/storage/authority, not just UI state; needs scoping, isolation, expiry, audit.
4. **Approval asked too early** — a vague task-start approval ("can I do this task?") means the actual side effect, steps later, executes with no meaningful approval behind it.
5. **Sandboxing treated as security by itself** — broad egress, mounted secrets, production credentials, shared writable files inside a "sandbox" is barely a boundary at all.
6. **Logging the answer, not the action** — logs missing the tool request, identity, resource, policy decision, approval state, and execution result become useless during an incident.
7. **Untrusted content steering privileged execution** — content crossing a trust boundary (webpage/doc/email/tool output) gains authority it was never granted, because the executor didn't re-check.

## Builder checklist from the article

Before enabling agent execution, answer:
1. What is the execution surface? (browser, code runner, shell, API, database, filesystem, device, remote worker)
2. What identity envelope attaches? (user identity, service identity, delegated token, browser context, API key, DB credential, or a combination)
3. What is the minimum required authority? (scopes, tenant, account, repo, filesystem root, network egress, DB role, lifetime)
4. Where is the enforcement point? (must be somewhere the model cannot bypass — adapter, gateway, wrapper, proxy, sandbox launcher)
5. Which actions require approval, placed near the actual side effect?
6. What is contained? (filesystem, process, network, credentials, cookies, env vars, artifacts, tenant data)
7. What gets recorded? (tool request, identity, resource, policy decision, approval state, inputs, execution result, observed output, follow-up state)
8. What happens if it's wrong? (rollback, compensation, retry semantics, deduplication, revocation, incident review, regression tests)

## Series roadmap

Part 8 next: Observability, Evaluation, and Production Feedback Loops — logs show what happened, evaluation decides if it was good, feedback loops turn production behavior into fixes/regressions/release decisions.
