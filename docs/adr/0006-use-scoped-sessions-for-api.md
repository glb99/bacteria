---
status: proposed
date: 2026-10-1
decision-makers: []
---

# Use scoped sessions for api

## Context and Problem Statement

The agent package is the core. Hosts implement it. The hosts today are the API and the CLI, and there will be more.

The agent `Session` is a conversation. The host implements `SessionRepository`. The agent package does not learn what a database is.

A user is an API concept. The CLI is a local tool with no separation between users. The question is where the user lives so that the CLI does not have to invent one.

## Decision Drivers

* The agent package and the CLI do not learn the API's user.

## Considered Options

* Put the user inside the agent boundary, so the CLI passes a hardcoded `user_id="local-cli"`.
* Keep the user inside the API, and leave the agent and the CLI without a user.

## Decision Outcome

Chosen option: "Keep the user inside the API, and leave the agent and the CLI without a user.", because the agent package and the CLI must not learn the API's user.

### Consequences

* Good, because the agent package and the CLI stay free of the API user.
* Good, because another host is not required to invent a user.
* Bad, because a user is not one shared concept. A host that wants accounts implements them itself (against DRY).

### Confirmation

* The agent `Session`, `create_session`, and `MemoryScope` contain no user.
* The CLI calls `create_session()` with no user id.

## Pros and Cons of the Options

### Put the user inside the agent boundary, so the CLI passes a hardcoded `user_id="local-cli"`.

* Good, because another host could reuse the same user concept.
* Bad, because every host must invent a user, including the CLI.

### Keep the user inside the API, and leave the agent and the CLI without a user.

* Good, because the agent package and the CLI do not learn the API's user.
* Bad, because a host that wants accounts implements them itself.

## More Information

I don't know about the performance issues scoped sessions could introduce, so it will be important to revisit this when evaluating that.
