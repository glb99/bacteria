---
date: 2026-09-28
status: aligned
question: "Where should a user-scoped database session live?"
adr: "0006"
---

# Where should a user-scoped database session live?

## Why this session

The person asked where this function belongs. It opens a database session, sets the PostgreSQL variable `app.current_user_id` for the current transaction, yields that session, then commits, rolls back, or closes.

```python
@contextmanager
def scoped_session(user_id: str) -> Generator[Session, None, None]:
    """Yields a database session restricted strictly to the given user_id."""
    session = SessionFactory()
    try:
        session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": user_id}
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

## Starting model

The opening message's docstring says the session is restricted strictly to the given `user_id`. All four interview answers are below.

| Prompt | Answer |
| --- | --- |
| What do you currently believe about where this belongs? | "I think it belongs to db.py more than to deps.py, this is because it belongs to the api boundary, a scoped session for a user is something that only be used by the api/webapp implementation." |
| Which decision does this understanding change? | "Creating the a boundary between the api and the cli that justifies having the separate and adding the context manager taht will theplace the curren session() one used in db.py." |
| Which constraint will you not trade away? | "The codebae tempalte is taken from a confident source of truth, so I don't want my modifications to create a slop in the way things are separated conceptually." |
| What observation would show that belief is wrong? | "for the defined boundary between the api, the cli and any future adapter, any other adapter using that, and inside the api adapter, any mixing between what should belong to db.py and what should belong to dependencies" |

## Evidence

- `backend/app/core/db.py` defines `engine` and `init_db(session)`. `init_db` receives a session. A comment there points at the FastAPI full-stack template as the origin of this layout. The file has no `session()` and does not open a session.
- `backend/app/api/deps.py` defines `get_db`, which is `with Session(engine)`, and `SessionDep`. `get_current_user(session: SessionDep, token)` loads the user with that session. `get_current_active_superuser` depends on `get_current_user`.
- `backend/app/initial_data.py` opens `with Session(engine)` and calls `init_db`. It is inside the app package. It is not the CLI, and it has no user id.
- `backend/app/api/routes/login.py` uses `SessionDep` for login and password recovery before any current user exists. `backend/app/api/routes/private.py` creates a user from `SessionDep` alone. `backend/app/api/routes/users.py` `read_users` and `create_user` use `SessionDep` and list or insert across users, behind `get_current_active_superuser`. `backend/app/api/routes/items.py` lets a superuser read every item and otherwise filters `Item.owner_id` in the route.
- `backend/cli/cli.py` composes the agent runtime with an in-memory `SessionRepository`. It does not import `app.core.db`. Its module text says a second interface is another thin module, and that this file is where concrete implementations are constructed.
- `backend/agent/src/agent/session/protocol.py` says the agent package does not learn what a database is. The host implements `SessionRepository`. User-scoped memory there is an application guarantee of the store.
- A search of the repo during this session found no `set_config`, no `SessionFactory`, and no row-level security policy. The opening snippet was then the only statement of `app.current_user_id`.
- As of 2026-10-02, `backend/app/core/db.py` defines `scope_to_user(session, user_id)`, which executes `set_config('app.current_user_id', :user_id, true)`. The file imports `Session`, `create_engine`, and `select` from `sqlmodel`, and does not import `text`. `backend/app/api/deps.py` defines `get_scoped_session`: it calls `scope_to_user` when `current_user.is_superuser` is false and returns the same session. `ScopedSessionDep` exists. Every route that takes a session still annotates `SessionDep`. `backend/app/alembic/versions/93f413156120_add_user_and_item_row_level_security.py` (`down_revision = 'fe56fa70289e'`) enables and forces row-level security on `item` and `"user"`, and creates `item_owner_isolation` and `user_self_isolation`. Each policy is `FOR ALL`. Its `USING` and `WITH CHECK` match every row when `current_setting('app.current_user_id', true)` is NULL, and otherwise require `item.owner_id` or `"user".id` to equal that value cast to `uuid`. Whether this revision has been applied to a database was not checked. `Item.owner_id` in `backend/app/models.py` has no `index=True`, and no migration creates an index on that column. `docs/adr/0006-use-scoped-sessions-for-api.md` exists, status proposed, date 2026-10-1. `docs/adr/index.md` still lists only ADR-0001.

## Inferences

- "Only the API and webapp use a user-scoped session" restricts callers. It selects the API adapter. It does not select `db.py` over `deps.py`. Evidence: the CLI never imports `db.py`; `initial_data.py` does; the request session already lives in `deps.py`.
- The snippet both opens a session and requires a `user_id`. In the template those are the two jobs the person said must stay apart: `db.py` owns the engine and `init_db`; `deps.py` owns the request session and the current user. Evidence: `db.py`, `deps.py`, and the fourth interview answer.
- `get_current_user` needs an open session in order to produce the user id the snippet requires. A context manager that demands `user_id` before yielding a session cannot be the session that discovers that user. Evidence: `get_current_user` in `deps.py`.
- Replacing every `Session(engine)` with `scoped_session(user_id)` leaves these callers without a single user id, or with a need to see other users' rows: `initial_data.init`, login, password recovery, private user creation, superuser user administration, and the superuser branch of the item routes. Evidence: those call sites.
- The docstring says the session is restricted strictly to `user_id`. The snippet only sets a PostgreSQL variable. At the time of the search above, nothing in the repo read `app.current_user_id`. The variable restricts rows only if later policy or query code reads it.
- As of 2026-10-02 the policies in revision `93f413156120` read `app.current_user_id`. Setting the variable limits `item` and `"user"` for statements in that transaction. Leaving it unset still matches every row on those tables. This supersedes the inference that nothing in the repo reads the variable. Evidence: that revision.

## Shared model

The agent package declares the protocols a host must implement, including `SessionRepository`. It does not learn what a database is. The host implements the store. The CLI is one host and composes an in-memory repository. The API is the FastAPI app in `backend/app`. A future in-process host would be another adapter. User-based database access belongs to the API adapter only.

A **user-scoped session** is a database session whose current transaction has PostgreSQL `app.current_user_id` set. `get_db` in `deps.py` opens that session with the built-in `Session` context manager and yields it. `db.py` provides a plain function that sets the variable on a session it receives. A normal-user dependency calls that function after `get_current_user` has loaded the user. No new `@contextmanager` is defined. The CLI and any other adapter do not call it. The person confirmed this model.

The person's decision: on the API, requests before login use an unscoped session. A superuser request stays unscoped. For a normal user, the scope is applied only after that user has been loaded. The CLI never knows what a user is.

Login, registration, and password recovery are before login and match the unscoped side. `get_current_user` loads the user through that unscoped session, which is also how `is_superuser` becomes known. Seeding is not a request. Setting the variable does not by itself hide rows. Nothing in the repo reads `app.current_user_id`.

The person decided `user_id` leaves `create_session` and leaves the `Session` model, and the `"user"` memory scope leaves the agent protocol. Memory in the agent protocol stays session-scoped. The only caller of `create_session` today is `backend/cli/cli.py`, which passes `user_id="local-cli"`. The in-memory store still keys a `"user"` scope by `session.user_id`. The API repository learns the database owner from its scoped database session, not from the agent model.

The API adapter implements `SessionRepository` inside its own boundary. The agent calls that protocol and does not receive the SQLAlchemy session. `user_id` leaves `create_session` and leaves the `Session` model. The `"user"` memory scope leaves the agent protocol. The scoped database session is an implementation detail of the API's repository.

The paragraphs above are the model confirmed when this session closed. The handoff records what was learned after that confirmation: ADR 0006 is the boundary record the person wrote, and the database mechanism is the separate record ADR 0007.

## Gaps

- Resolved on 2026-10-02: the accepted gap that nothing reads `app.current_user_id` is closed by revision `93f413156120`. The policies read the variable. When it is unset they still match every row, so a forgotten `scope_to_user` still sees every row of `item` and `"user"`.
- The in-memory store and the CLI still pass and store `user_id`, and `MemoryScope` still includes `"user"`. The shared model says those leave. That confirmation belongs to ADR 0006. This session does not change that code.
- No route uses `ScopedSessionDep`. `scope_to_user` calls `text` and `db.py` does not import it. Whether revision `93f413156120` has been applied to a database was not checked.
- Performance of a scoped transaction is the person's open question. The handoff keeps their sentence and does not answer it.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | The agent package declares protocols and does not receive a SQLAlchemy session. User-based database access stays in the API adapter. `scoped_session` lives in `db.py`. `get_db` in `deps.py` yields it. An unscoped session remains for callers with no user id. Setting the variable does not by itself restrict rows. | "bacteria is the core that defines how the agent work, and what protocols should any application built over it should implement. We will have some adapters (a cli, an api, and in the future some way of implementing the agent inside our code without having an explicit interface), so this is why we have organized the project as uv packages. Each implementation will have its own implementation details one of them is the user-based access: this is for api access and not for other clients like cli, so all related to that should live inside the adapter and not the agent nor any other implementation. So instead of having a \"user\" concept shared between implementations (that could lead to having to implement a \"fake\" user per implementation) we implement the user strictly inside the api boundaries. To do that we need to be able to abstract the user concept by creating a \"scoped session\" in the api adapter that is passed away abstracting the user concept to the agent boundary, the way of implementing it is by using a scoped_session context manager that \"overwrites\" a generic sqlalchemy Session that scopes the session to the user at dependency time, the context manager is implemented in db.py while the get_db dependency in deps.py." | partial |
| Does "belongs in `db.py`" mean the whole context manager, or the `set_config` call with `deps.py` deciding which requests are user-scoped? | The person assigns the whole context manager to `db.py` and the request hook to `get_db`. | Answered inside the restatement: the context manager is in `db.py`, and `get_db` in `deps.py` yields it at dependency time. | partial |
| Which object crosses the agent boundary? | The API implements `SessionRepository`. The agent does not receive the SQLAlchemy session. `create_session` still takes `user_id`. Later methods take `session_id`. | "the session is implemented inside the the api client boundary by implementing teh session protocol defined by the agent, that in this way does not have to implement as arguments something like user_id" | partial |
| What would you decide? | API requests before login stay unscoped. Later API requests use `scoped_session`. The CLI does not learn the API's user. | "for the api, I think the before-login requests will be the ones without the scoped session, from the cli, it will never know about what a user is" | partial |
| What does the CLI pass to `create_session`? | Nothing. The required `user_id` argument cannot stay as it is. | "nothing" | partial |
| Does `user_id` leave `create_session` for every host? | Yes. The argument leaves for every host. The `Session.user_id` field is still open. | "leave" | yes |
| Does the `user_id` field leave `Session`? | Yes. | "yes" | yes |
| Does the `"user"` memory scope leave the agent protocol? | Yes. Agent memory stays session-scoped. | "yes" | yes |
| Does a superuser request use an unscoped session? | A scoped session is restricted to one user. Superuser routes read across users, so they stay unscoped. The scope is applied after the user is loaded, and only for a normal user. | "I think an unscoped, what do you think?" then "yes" | yes |
| Is the stated model the shared model? | `get_db` opens the session with the built-in `Session` context manager. `scope_to_user` in `db.py` sets `app.current_user_id` after a normal user is loaded. Before-login and superuser requests stay unscoped. The agent protocol has no `user_id` and no `"user"` memory scope. Setting the variable does not by itself hide rows. | "yes" | yes |

## Handoff for a human ADR

Two records come out of this session. The person writes both. This file does not create them.

### ADR 0006, already written

`docs/adr/0006-use-scoped-sessions-for-api.md` (proposed, 2026-10-1) is the boundary record. Its driver is that the agent package and the CLI do not learn the API's user. Its outcome is to keep the user inside the API and leave the agent and the CLI without a user, because of that driver. Its confirmation is that the agent `Session`, `create_session`, and `MemoryScope` contain no user, and that the CLI calls `create_session()` with no user id.

The database mechanism stays out of 0006. It does not belong in that record's Decision Outcome or More Information. The index under `docs/adr/index.md` still lists only ADR-0001. The person adds the row.

### ADR 0007, not written — revisit this section

0007 decides how the API scopes one database transaction to one user. The scoped object is that SQLAlchemy transaction. The agent conversation stays without a user, which 0006 already records.

Suggested title, for the person to keep or replace: "Scope the API database transaction to the loaded user."

#### Context to carry

The user id is known only after `get_current_user` loads the row on a transaction that can still read `"user"`. That load is also how `is_superuser` becomes known. Reversing the order, and setting the variable before the load, hides the row the load needs whenever the policy is restricting `"user"`.

The value passed to `scope_to_user` is `str(current_user.id)` from that row. Login stores `str(user.id)` in the JWT `sub` through `create_access_token`. A later request sends `Authorization: Bearer <token>`. `get_current_user` decodes `sub` and loads `session.get(User, token_data.sub)`. The id is not a separate header field. Who issues the token is a different decision. It changes where `sub` comes from. It does not change `get_db`, `scope_to_user`, or the policy.

The FastAPI template's separation stays intact. `db.py` owns the engine, `init_db`, and the function that sets the variable. `deps.py` owns the request session and which requests are scoped. Neither file absorbs the other's job.

#### Decision drivers

The outcome's "because" stays inside these three:

- A normal user's later queries in that transaction see only that user's rows.
- Login, registration, password recovery, seeding, and superuser requests still see the rows they need.
- `get_db` opens the session. `db.py` does not decide which request is scoped.

#### Considered options

- The opening context manager opens a session, requires `user_id` before yielding, then commits, rolls back, or closes. The user id does not exist when the session opens. The same function would open the session and choose the user. Login, registration, password recovery, seeding, and superuser callers have no single user id, or they need rows that belong to other users.
- `get_db` keeps opening the session with `with Session(engine)`. `scope_to_user(session, user_id)` in `db.py` is a plain function. It runs `SELECT set_config('app.current_user_id', :user_id, true)` on the session it receives. A dependency calls it after `get_current_user` has loaded a normal user, and skips the call for a superuser. Policies on `item` and `"user"` read the variable: every row matches when it is unset, and `item.owner_id` or `"user".id` must equal it when it is set. Both tables use `ENABLE` and `FORCE ROW LEVEL SECURITY`. The third argument `true` makes the setting transaction-local.
- A fail-closed policy was discussed and was not the person's choice: equality only, an explicit bypass for admin and seed, and no policy on `"user"`. The person kept the `IS NULL` branch so an unset variable still matches every row.

#### Decision outcome to write

Chosen option: "`get_db` opens the session, `scope_to_user` sets `app.current_user_id` after a normal user is loaded, and the policy matches every row when that variable is unset", because the user is known only after that unscoped load, the unscoped requests still need their rows, and `db.py` does not choose which request is scoped.

Names of helpers belong in Consequences and Confirmation. The "because" stays on the drivers.

#### Consequences

- Good, because `db.py` sets the variable on a session it receives, and `deps.py` decides which request calls it.
- Good, because login, registration, password recovery, seeding, and superuser requests leave the variable unset and the policy still returns rows.
- Good, because a normal user's later statements in that transaction are limited to that user's `item.owner_id` and `"user".id`.
- Bad, because a request that should have called `scope_to_user` and did not still sees every row. The unset branch is what lets the unscoped requests work, and it is also the leak.
- Bad, because a forbidden row is absent from the result. The route still owns HTTP 403. Item routes today return 403 by comparing `owner_id` in Python. With the policy applied, `session.get` of another user's item returns no row, which those routes currently answer as 404.
- `scope_to_user` does not commit, roll back, or close. The built-in `Session` context manager inside `get_db` closes the session and rolls back an uncommitted transaction. Routes and `crud` still commit. A commit ends the transaction-local setting, so `scope_to_user` has to run in the same transaction as the queries it should limit.

#### Confirmation

- `get_db` remains the opener of the request session. `scope_to_user` does not open, close, commit, or roll back.
- On a normal-user request, `app.current_user_id` is set to that user's id before the item and user queries, and an item query returns only that owner's rows.
- Login, registration, password recovery, `backend/app/initial_data.py`, and superuser requests leave the variable unset and can still read the rows they need.
- The superuser path skips `scope_to_user`.

Routes the decision treats as scoped once they are wired to that dependency: every handler in `backend/app/api/routes/items.py`; in `backend/app/api/routes/users.py`, `update_user_me`, `update_password_me`, `delete_user_me`, and `read_user_by_id`.

Routes that stay on the unscoped session: login and password recovery, `register_user`, `private.create_user`, `initial_data.py`, and the superuser-only user handlers `read_users`, `create_user`, `update_user`, and `delete_user`. `read_user_me` returns `CurrentUser` and does not query.

`get_scoped_session` is the dependency that calls `scope_to_user` and returns the same session. It is not a second `get_db`.

#### More Information

Keep the person's sentence. Do not replace it with a performance conclusion:

> I don't know about the performance issues scoped sessions could introduce, so it will be important to revisit this when evaluating that.

Notes for that later evaluation. They stay out of More Information until the person has evaluated them:

- `item.owner_id` has no index in `backend/app/models.py` or in the migrations. `"user".id` is the primary key.
- The policy predicate is `IS NULL OR column = current_setting(...)::uuid`. That shape can keep the planner from using an index on the column.
- These notes are not a finding that the design is cheap or expensive. The person left that unknown.

#### What the tree shows on 2026-10-02

The decision above is not the same as the tree. This session does not change code.

- `scope_to_user` and `get_scoped_session` are in the tree. No route uses `ScopedSessionDep`.
- `scope_to_user` calls `text` and `backend/app/core/db.py` does not import it.
- Revision `93f413156120` contains the policies. Application of that revision to a database was not checked.
- `backend/app/api/deps.py` still has `except InvalidTokenError, ValidationError` without parentheses. That defect is outside this decision.
- Removing `user_id` from the agent `Session` and `create_session`, and removing the `"user"` memory scope, is the confirmation of ADR 0006.

#### Left open for the person

- Performance, in the sentence quoted above.
- `read_user_by_id` for a normal user: under the policy, another user's row is absent, so the route's current 403 becomes a missing row. The person can keep the Python 403 on an unscoped read, or accept the missing row. That choice was not made here.
- The fail-closed option remains available if the unset-means-every-row leak is no longer acceptable. It was not the choice recorded here.
