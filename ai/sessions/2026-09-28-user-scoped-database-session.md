---
date: 2026-09-28
status: aligned
question: "Where should a user-scoped database session live?"
adr: ""
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
- A search of the repo finds no `set_config`, no `SessionFactory`, and no row-level security policy. The opening snippet is the only statement of `app.current_user_id`.

## Inferences

- "Only the API and webapp use a user-scoped session" restricts callers. It selects the API adapter. It does not select `db.py` over `deps.py`. Evidence: the CLI never imports `db.py`; `initial_data.py` does; the request session already lives in `deps.py`.
- The snippet both opens a session and requires a `user_id`. In the template those are the two jobs the person said must stay apart: `db.py` owns the engine and `init_db`; `deps.py` owns the request session and the current user. Evidence: `db.py`, `deps.py`, and the fourth interview answer.
- `get_current_user` needs an open session in order to produce the user id the snippet requires. A context manager that demands `user_id` before yielding a session cannot be the session that discovers that user. Evidence: `get_current_user` in `deps.py`.
- Replacing every `Session(engine)` with `scoped_session(user_id)` leaves these callers without a single user id, or with a need to see other users' rows: `initial_data.init`, login, password recovery, private user creation, superuser user administration, and the superuser branch of the item routes. Evidence: those call sites.
- The docstring says the session is restricted strictly to `user_id`. The snippet only sets a PostgreSQL variable. Nothing in the repo reads `app.current_user_id`. The variable restricts rows only if later policy or query code reads it.

## Shared model

The agent package declares the protocols a host must implement, including `SessionRepository`. It does not learn what a database is. The host implements the store. The CLI is one host and composes an in-memory repository. The API is the FastAPI app in `backend/app`. A future in-process host would be another adapter. User-based database access belongs to the API adapter only.

A **user-scoped session** is a database session whose current transaction has PostgreSQL `app.current_user_id` set. `get_db` in `deps.py` opens that session with the built-in `Session` context manager and yields it. `db.py` provides a plain function that sets the variable on a session it receives. A normal-user dependency calls that function after `get_current_user` has loaded the user. No new `@contextmanager` is defined. The CLI and any other adapter do not call it. The person confirmed this model.

The person's decision: on the API, requests before login use an unscoped session. A superuser request stays unscoped. For a normal user, the scope is applied only after that user has been loaded. The CLI never knows what a user is.

Login, registration, and password recovery are before login and match the unscoped side. `get_current_user` loads the user through that unscoped session, which is also how `is_superuser` becomes known. Seeding is not a request. Setting the variable does not by itself hide rows. Nothing in the repo reads `app.current_user_id`.

The person decided `user_id` leaves `create_session` and leaves the `Session` model, and the `"user"` memory scope leaves the agent protocol. Memory in the agent protocol stays session-scoped. The only caller of `create_session` today is `backend/cli/cli.py`, which passes `user_id="local-cli"`. The in-memory store still keys a `"user"` scope by `session.user_id`. The API repository learns the database owner from its scoped database session, not from the agent model.

The API adapter implements `SessionRepository` inside its own boundary. The agent calls that protocol and does not receive the SQLAlchemy session. `user_id` leaves `create_session` and leaves the `Session` model. The `"user"` memory scope leaves the agent protocol. The scoped database session is an implementation detail of the API's repository.

## Gaps

- Accepted gap: setting `app.current_user_id` does not by itself hide rows. Nothing in the repo reads that variable.
- The in-memory store and the CLI still pass and store `user_id`, and `MemoryScope` still includes `"user"`. The shared model says those leave. This session does not change that code.

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

Constraints from the person: the FastAPI template's conceptual separation stays intact; user-based database access stays in the API adapter; the CLI and any future adapter do not learn a user; `db.py` and `deps.py` do not absorb each other's jobs.

Their decision: `get_db` opens the session with the built-in `Session` context manager. `db.py` has a plain function that sets `app.current_user_id` on that session. A normal-user dependency calls it after `get_current_user`. Before-login requests and superuser requests stay unscoped. `user_id` leaves `create_session` and `Session`. The `"user"` memory scope leaves the agent protocol.

Evidence is the list above. The accepted open point is that nothing in the repo reads `app.current_user_id`, so the setting does not yet hide rows.
