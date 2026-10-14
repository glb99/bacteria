---
status: proposed
date: 2026-10-2
decision-makers: []
---

# Scope the API database transaction to the loaded user

## Context and Problem Statement

ADR 0006 keeps the user inside the API. The agent conversation stays without a user. This record decides how one API database transaction is limited to one user.

The user id is known only after `get_current_user` loads the row. That load also shows whether the user is a superuser. Login, registration, password recovery, seeding, and superuser requests need rows that a single-user scope would hide.

`db.py` owns the engine and the function that sets the PostgreSQL variable. `deps.py` owns the request session and which requests are scoped.

## Decision Drivers

* A normal user's later queries in that transaction see only that user's rows.
* Login, registration, password recovery, seeding, and superuser requests still see the rows they need.
* `get_db` opens the session. `db.py` does not decide which request is scoped.

## Considered Options

* Open the session in a context manager that requires the user id before yielding, then commit, roll back, or close.
* Open a second session in `get_scoped_db` after the user has been loaded on the session from `get_db`.
* Keep `get_db` as the opener. Set `app.current_user_id` with a plain function after a normal user is loaded. The policy matches every row when that variable is unset.
* Match a row only when the variable equals that row, with an explicit bypass for admin and seed, and no policy on `"user"`.

## Decision Outcome

Chosen option: "Keep `get_db` as the opener. Set `app.current_user_id` with a plain function after a normal user is loaded. The policy matches every row when that variable is unset.", because the user is known only after that unscoped load, the unscoped requests still need their rows, and `db.py` does not choose which request is scoped.

### Consequences

* Good, because `db.py` sets the variable on a session it receives, and `deps.py` decides which request calls it.
* Good, because login, registration, password recovery, seeding, and superuser requests leave the variable unset and the policy still returns rows.
* Good, because a normal user's later statements in that transaction are limited to that user's `item.owner_id` and `"user".id`.
* Bad, because a request that should have set the variable and did not still sees every row.
* Bad, because a forbidden row is absent from the result. The route still owns HTTP 403. On an item read, `session.get` of another user's item returns no row, which those routes currently answer as 404.

### Confirmation

* `get_db` remains the opener of the request session. `scope_to_user` does not open, close, commit, or roll back.
* `get_scoped_session` returns that same session. On a normal-user request, `app.current_user_id` is set to that user's id before the later item and user queries, and an item query returns only that owner's rows.
* Login, registration, password recovery, seeding, and superuser requests leave the variable unset and can still read the rows they need.
* The superuser path skips `scope_to_user`.

## Pros and Cons of the Options

### Open the session in a context manager that requires the user id before yielding, then commit, roll back, or close.

* Good, because open, scope, commit, and close would live in one function.
* Bad, because the user id does not exist when the session opens, and the same function would both open the session and choose the user.
* Bad, because login, registration, password recovery, seeding, and superuser callers need rows outside one user.
* Bad, because the function would commit, while today the route or `crud` commits and `get_db` only opens and closes.

### Open a second session in `get_scoped_db` after the user has been loaded on the session from `get_db`.

* Good, because the user can be loaded before the variable is set.
* Bad, because the request holds two sessions. The variable is transaction-local, so it applies on the second session, while the loaded `User` stays bound to the first.
* Bad, because `get_db` is no longer the only opener.

### Keep `get_db` as the opener. Set `app.current_user_id` with a plain function after a normal user is loaded. The policy matches every row when that variable is unset.

* Good, because the user is loaded on a transaction that can still read `"user"`, the later queries see the variable, and `db.py` does not choose the request.
* Bad, because a forgotten call still sees every row.

### Match a row only when the variable equals that row, with an explicit bypass for admin and seed, and no policy on `"user"`.

* Good, because a forgotten scope returns no rows.
* Bad, because login, seeding, and superuser requests need a separate bypass, and loading the user by id no longer works on the same policy.

## More Information

I don't know about the performance issues scoped sessions could introduce, so it will be important to revisit this when evaluating that.