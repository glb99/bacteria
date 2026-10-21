---
date: 2026-10-21
status: exploring
question: "How is EmbeddingPageRetriever initialized?"
adr: ""
---

# How is EmbeddingPageRetriever initialized?

## Why this session

The person asked how the retriever implementation can be initialized. The CLI has an unfinished `build_document_retriever`. The person writes any ADR that comes out of this.

## Starting model

From the opening message:

> how can it be initialized?

> but from where entities come?

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | |
| Which decision does this understanding change? | "construct it in cli". The entity list: "load them from postgres" |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- `EmbeddingPageRetriever.__init__` takes `embed: Embed` and `entities: list[StoredEntity]`. `StoredEntity` holds `document_id`, `page_index`, `vector`, and `image_path`. Source: `backend/agent/src/agent/retriever.py`.
- `run_turn` requires `document_retriever: RetrievesDocumentPages` and calls `select(query=user_text, limit=1)`. Source: `backend/agent/src/agent/runtime.py`.
- The CLI module docstring says this file is the only one that constructs concrete implementations. Source: `backend/cli/cli.py`.
- `document_entity` stores `document_id`, `page_index`, `label`, box edges, and a JSON `vector`. It has no image path. Source: `backend/app/src/app/models.py`.
- The CLI comment above `anyio.run` says this command has no database driver. Source: `backend/cli/cli.py`.
- The person said where to construct it: "construct it in cli".
- The person then asked where the entities come from: "but from where entities come?"
- `process_document` embeds each non-empty label and calls `add_entity` with document id, page index, label, box edges, and vector. Source: `backend/app/src/app/api/services/document_service.py`.
- `SqlDocumentRepository.add_entity` inserts a `DocumentEntity` row and commits. Source: `backend/app/src/app/api/services/document_repository.py`.
- `load_stored_entities` in `backend/cli/cli.py` reads every `document_entity` row through `SqlDocumentRepository.list_entities` and builds a `StoredEntity` with an empty `image_path`. `build_document_retriever` calls it when `entities` is omitted. The person said: "load them from postgres".

## Inferences

- Construction belongs in `build_document_retriever`, and `_run` passes that object into `run_turn`. Evidence: the CLI composition sentence, `run_turn`'s parameter, and the person's sentence.
- The embedder that satisfies `Embed` and already exists is `GeminiEmbedder`. Evidence: `ingestion/embedder.py` and the retriever constructor.
- An entity list loaded from `document_entity` cannot fill `image_path`, and this command does not open the database. The list the CLI can supply without a new store is empty. Evidence: the model columns and the CLI database comment.
- `load_stored_entities` is the mapping from a `document_entity` row to `StoredEntity`. It copies document id, page index, and vector. Evidence: `backend/cli/cli.py`.

## Shared model

The person has not confirmed this paragraph.

The CLI constructs the retriever. `build_document_retriever` returns an `EmbeddingPageRetriever` whose `embed` is a `GeminiEmbedder`. When the caller does not pass `entities`, `load_stored_entities` reads every `document_entity` row. `_run` builds that object once, after `load_dotenv`, and passes it to every `run_turn`.

A **stored entity** in the retriever is one `StoredEntity`: document id, page index, vector, and page-image path. Upload writes one `document_entity` row per non-empty label, including the vector. The loader copies document id, page index, and vector from that row. The row has no page-image path, so the loaded `image_path` is empty and `select` skips that page.

## Gaps

- What they currently believe initialization should do, beyond the CLI as the place, is unstated.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.
- The page-image path lives on a `page` row. The person accepted that with "ok, do it". See `ai/sessions/2026-10-21-page-image-path.md`. `load_stored_entities` copies `page.image_path`. Ingestion does not yet insert those rows.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

One record, not written. The person chose the CLI as the place that constructs the retriever. They have not confirmed the paragraph.

### How the retriever is initialized — revisit this section

Suggested title, for the person to keep or replace: "Construct the page retriever in the CLI."

#### Context to carry

`EmbeddingPageRetriever` needs an `Embed` and a list of `StoredEntity`. `run_turn` takes that retriever and calls `select` once per turn. The CLI is the composition root and has no database driver. `document_entity` stores JSON vectors and has no page-image path.

#### Decision drivers

- Their instruction: "construct it in cli".
- The CLI module says it is the only file that constructs concrete implementations.
- The command does not read the document store.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.

#### Considered options

- Chosen: construct `EmbeddingPageRetriever` in `build_document_retriever` and pass it to `run_turn`.
- A FastAPI dependency, named in the interview, not chosen.
- Leaving construction at the call site of the class only, named in the interview, not chosen.

#### Decision outcome to write

Chosen: the CLI constructs it and loads the entity list from Postgres. Their words: "construct it in cli" and "load them from postgres". `load_stored_entities` reads `document_entity`. `image_path` is empty because that column is not in the table.

#### Consequences

- A turn can call `select`. With the default list it returns no pages.
- The vectors live on `document_entity` rows written by `process_document`. Nothing maps those rows to `StoredEntity`. Filling that list is still open.

#### Confirmation

- Not yet stated.

#### More Information

> how can it be initialized?

> construct it in cli

> but from where entities come?

> load them from postgres

#### Left open for the person

- What they currently believe initialization should do beyond the place.
- The constraint they will not trade away.
- The observation that would show the belief wrong.
- Where the page-image path is stored. That question is `ai/sessions/2026-10-21-page-image-path.md`.
