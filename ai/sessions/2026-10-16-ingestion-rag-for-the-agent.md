---
date: 2026-10-16
status: aligned
question: "How should uploaded files become a RAG the agent uses?"
adr: ""
---

# How should uploaded files become a RAG the agent uses?

## Why this session

The person wants to design an ingestion system: the API accepts uploaded files, those files are ingested into a RAG, and the agent uses that RAG. The decision they named for this session is which routes to implement. The person writes any ADR that comes out of it.

## Starting model

From the opening message, before the interview:

> I want to design an ingestion system, the idea is to allow api to upload files (pdfs and codebases), ingest them and create a RAG then the agent uses

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "a new routes module should be created, for I only want to see it working with pdfs, but more in the future, with at first a route for uploading documents, this will be a heavy-load process, so it should be managed by a background job. This will be a processing pipeline, probably the bbest option is to process documents as images, then recognizing the elements" |
| Which decision does this understanding change? | "what routes to implement" |
| Which constraint will you not trade away? | "only pdfs for now" |
| What observation would show that belief is wrong? | "I dont know" |

## Evidence

- `backend/app/src/app/api/main.py` builds `api_router` and includes `login.router`, `users.router`, `utils.router`, and `items.router`. When `settings.FASTAPI_ENV == "development"` it also includes `private.router`.
- `backend/app/src/app/api/routes/items.py` defines `router = APIRouter(prefix="/items", tags=["items"])`. `users.py` uses prefix `/users`. `utils.py` uses prefix `/utils`. `private.py` uses prefix `/private`. `login.py` sets tags and no prefix. A new module would be a new file in that package plus an `include_router` call in `api/main.py`.
- A search of `backend/**/*.py` on 2026-10-16 found no upload route, no ingestion pipeline, no RAG, no vector store, and no worker. The only matches were the word "retrieve" in a comment in `backend/agent/src/agent/session.py`, "embedded" in `backend/cli/cli.py`, and "JSON Schema document" in `backend/agent/src/agent/model.py`.
- `backend/app/pyproject.toml` depends on `fastapi[standard]` and `python-multipart`. It does not depend on a job queue. The app models in `backend/app/src/app/models.py` are users and items. There is no document table.
- `backend/agent/src/agent/context.py` `assemble_context` keeps the last `window_size` transcript messages (default 5) and appends the new user text. It returns `AssembledContext` with those messages. It does not read an external document.
- `docs/adr/0006-use-scoped-sessions-for-api.md` (proposed) decides to keep the user inside the API and to leave the agent and the CLI without a user, because the agent package and the CLI must not learn the API's user.

## Inferences

- A new routes module matches the layout already used for items, users, utils, login, and private. Evidence: `api/main.py` and those route modules. The belief that the PDF routes live in a new module is consistent with that layout. The module does not exist yet.
- "Only PDFs for now" fixes the file kind for the routes this session decides. Codebases, named in the opening message, stay outside that route list. Evidence: the constraint answer and the opening message.
- The upload route is the only route the person named. A background job is a worker, not a route. Treating the PDF as images and recognizing elements is a pipeline step, not a route. The agent using a RAG is not a route in the current agent package. Evidence: the belief answer, `context.py`, and the search that found no retrieval.
- `python-multipart` is already present, so accepting a file body does not require a new HTTP library. Evidence: `backend/app/pyproject.toml`. That fact does not decide the route list.
- There is no observation the person will use to drop the image-recognition belief. That belief stays a guess until they name one or choose the pipeline. Evidence: the answer "I dont know".
- The person later named the route list, in their words: "upload and a read-by-id route." Evidence: the alignment answer. That choice is the route list. It does not choose the image pipeline.

## Shared model

The decision in this session is which HTTP routes the API implements for PDF ingestion. The constraints are "only pdfs for now" and "the front for now." Codebases, later file kinds, and a webhook are outside these routes.

The person chose two routes, in their words: "upload and a read-by-id route." They belong in a new routes module. The **upload route** accepts a PDF, starts the background job, and returns an id with a not-ready status. The **read-by-id route** returns that status. The frontend learns that the PDF is ready by calling the read route again.

**Ingestion** is the work behind the upload route that turns the PDF into material a retriever can hold. The person believes it is a heavy pipeline and that the best pipeline processes the document as images and then recognizes the elements. They do not know what would show that belief wrong. That pipeline is not chosen. A **RAG** is that material plus the retrieval the agent would use. How the agent uses it is outside this route list. The agent today builds a short message window in `backend/agent/src/agent/context.py`. The API registers route modules from `backend/app/src/app/api/main.py`.

## Gaps

- The falsifying observation is "I dont know". The image-recognition pipeline has no check and is not chosen.
- The first restatement was partial. The person then confirmed the revised shared model with "yes that matches".
- How the agent uses the RAG is unstated. `assemble_context` does not retrieve. The pipeline session now says the pipeline is independent of the agent and builds the RAG the agent consumes. How that consumption works is still unsaid.
- Whether an uploaded PDF is owned by the API user is unstated. ADR 0006 keeps the user inside the API. This session has not applied that to documents.
- "more in the future" does not name which file kinds follow PDFs. The opening message named codebases. The constraint leaves them outside this decision. A webhook is also outside it.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Restate the shared model. | This session decides which PDF routes the API implements. Ingestion of a PDF is a background pipeline, and the RAG the agent uses is separate from that route list. The only route named so far is upload. The image-recognition pipeline is a belief, not a choice. | "This session is about deciding which routes we need to add in order to implement the RAG ingestion for bacteriaa, as that routes will represent the features" | partial |
| If the upload returns before processing finishes, how does the caller learn that the PDF is ready? | The caller is the frontend, so it learns by reading the document id again. A webhook is outside this decision. | "the front for now" | yes |
| Which routes would you implement? | The person's list. | "upload and a read-by-id route" | yes |
| Confirm the revised shared model. | Upload and read-by-id, PDFs only, frontend only. The upload returns an id and a not-ready status. The frontend reads that id again until the PDF is ready. The image pipeline and the agent's use of the RAG stay unchosen. | "yes that matches" | yes |

## Handoff for a human ADR

One record, not written. The route list is chosen, and the person confirmed the shared model. The pipeline and the agent's use of the RAG stay open.

### Which ingestion routes the API implements — revisit this section

Suggested title, for the person to keep or replace: "Add the PDF ingestion routes."

#### Context to carry

The person wants an ingestion system. The API uploads files. The opening message named PDFs and codebases. Those files would be ingested into a RAG, and the agent would use that RAG. The decision they asked this session to settle is "what routes to implement." They chose "upload and a read-by-id route." On restatement they said the routes represent the features. The features those two routes represent are accepting a PDF and reading its status. The image pipeline and the agent's use of the RAG stay outside the route list.

Their belief, in their words: a new routes module; PDFs first, more file kinds later; at first a route for uploading documents; the work is heavy, so a background job runs it; it is a processing pipeline; "probably the best option is to process documents as images, then recognizing the elements."

The API registers route modules in `backend/app/src/app/api/main.py`. There is no documents module, no upload route, no job queue dependency, and no document table. The agent context is a message window. ADR 0006 keeps the API user out of the agent package.

#### Decision drivers

- "only pdfs for now." Later file kinds, including codebases, stay outside this decision.
- "the front for now." The caller is the browser app under `frontend/`. A webhook stays outside this decision.

#### Considered options

- A new routes module with an upload route, a background job, and a pipeline that processes documents as images and then recognizes the elements. The person called the image step "probably the best option." They have not chosen it, and they do not know what would show it wrong.
- Chosen by the person: "upload and a read-by-id route." The upload route accepts the PDF and returns an id with a not-ready status. The read route returns that status, which later becomes ready. The frontend learns readiness by calling the read route again. This follows the items module, where `POST /items/` creates a row and `GET /items/{id}` reads it (`backend/app/src/app/api/routes/items.py`).
- Offered, not chosen: the upload request stays open until processing finishes. That drops the background job.
- Offered, not chosen: the upload route plus a stream the server pushes on. The API has no stream route today.
- Named by the person, set aside for now: a webhook. They chose "the front for now." The browser app under `frontend/` cannot receive a webhook, so this option stays outside the decision.

#### Decision outcome to write

Chosen by the person: an upload route and a read-by-id route, PDFs only, for the frontend. Their words: "upload and a read-by-id route."

The background job remains their belief about the work behind upload. The image-recognition pipeline is not chosen. The webhook is set aside. How the agent uses the RAG is not part of this outcome.

#### Consequences

- The frontend can show a PDF moving from not-ready to ready by reading the same id again.
- The upload request returns before that processing finishes.
- The API has no job queue dependency and no document table today (`backend/app/pyproject.toml`, `backend/app/src/app/models.py`). Those are still to be built if this route pair is implemented. This session does not choose them.
- The agent still has no retrieval. These routes do not make the agent use the RAG.
- Codebases and a webhook stay out of this route pair.

#### Confirmation

- The API exposes an upload route that accepts a PDF and returns an id.
- The API exposes a read-by-id route that returns a status for that id.
- A non-PDF is refused.
- The frontend is the caller that reads the status.

#### More Information

The opening sentence, in the person's words:

> I want to design an ingestion system, the idea is to allow api to upload files (pdfs and codebases), ingest them and create a RAG then the agent uses

The falsifier, in their words:

> I dont know

#### Left open for the person

- Whether the image-recognition pipeline is the one they choose.
- How the agent consumes the RAG. The pipeline session says the pipeline is independent of the agent and builds that RAG. Consumption stays outside the route decision.
- Whether an uploaded PDF belongs to the API user.
