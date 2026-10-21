---
date: 2026-10-20
status: exploring
question: "Should retrieval live in the ingestion package or in its own package?"
adr: ""
---

# Should retrieval live in the ingestion package or in its own package?

## Why this session

The person asked whether a good architecture puts retrieval in the ingestion package or in an independent one. The person writes any ADR that comes out of it.

## Starting model

From the opening message, before the rest of the interview:

> for a good architecture, do you think retrieving should be inside ingestion pacjkage or in an independent one?

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "I think, as they would share the embeddigns mechanism, we should rename the ingestion package by rag, and place ingestion and retrieval there" |
| Which decision does this understanding change? | Where the retrieval code lives. Their belief is one `rag` package that contains ingestion and retrieval. |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- The person believes ingestion and retrieval should share the embeddings mechanism, so the ingestion package should be renamed `rag` and hold both. Source: this session's starting model, 2026-10-20.
- `backend/ingestion/pyproject.toml` names the project `ingestion` and describes it as "PDF ingestion pipeline, independent of the agent." `backend/ingestion/src/ingestion/__init__.py` says the pipeline is independent of the agent.
- `GeminiEmbedder` and the `Embed` protocol live in `backend/ingestion/src/ingestion/embedder.py`. `process_document` in `document_service.py` calls that embedder once per labeled box.
- The app imports `ingestion.paginator`, `ingestion.entity_extractor`, and `ingestion.embedder` from `deps.py` and `document_service.py`. Tests under `backend/ingestion/src/tests` and `backend/app/src/tests` import those same modules.
- `backend/ingestion/src/document.py` is a top-level `document` module beside the `ingestion` package. It defines `DocumentRepository`.
- `document_entity` rows store a document id, a page index, a label, and a JSON vector. The agent package has no retrieval tool. `assemble_context` in `backend/agent/src/agent/context.py` keeps a short message window.
- The aligned RAG session defines ingestion as the work that turns a PDF into material a retriever can hold, and a RAG as that material plus the retrieval the agent uses. How the agent uses it was left outside the route list. Source: `ai/sessions/2026-10-16-ingestion-rag-for-the-agent.md`.

## Inferences

- One package can hold both directions because both call `Embed`. Ingestion embeds each label. Retrieval embeds the question and scores it against the stored vectors. Evidence: `embedder.py`, `process_document`, and the person's sentence.
- The rename changes the project name and the import path `ingestion`. The app service, the dependencies, and the tests import that path today. Evidence: the import search on 2026-10-20.
- The existing independence sentence still fits if `rag` does not import the agent, and the agent is the caller of retrieval. Evidence: the package description and ADR 0006's rule that the agent does not learn the API user. The agent depending on `rag` is not written down.
- `document.py` is not inside the `ingestion` package. A rename of the directory does not by itself move that module. Evidence: the file path.

## Shared model

The person has not confirmed this paragraph.

The **rag package** is the renamed ingestion package. It holds two sides that share the **embeddings mechanism**, `Embed` / `GeminiEmbedder`. **Ingestion** is the write side already in that package: split the PDF, recognize boxes, and embed each label. **Retrieval** is the read side still to be written: embed the question and score it against the stored vectors.

The package stays independent of the agent. The agent would call retrieval. The package would not import the agent.

The person chose local page images with "I think I will take that," after the description of writing one image per page and storing its path. Ingestion renders each page and writes that file on the documents volume. The database stores the path. Retrieval opens the file and sends those bytes to the model. The original PDF at `document.path` remains. Base64 in PostgreSQL and object storage stay unused.

The constraint they will not trade away, and the observation that would show this belief wrong, are unstated. The rename of the package to `rag` is still unconfirmed.

## Gaps

- The person has not yet restated the paragraph.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.
- Whether the agent is allowed to depend on the `rag` package is unstated.
- `document.py` sits beside the package. Whether it moves into `rag` is unstated.
- On 2026-10-20 the person chose local page images. Their words: "I think I will take that," after the description of writing one image file per page under the documents directory and storing that path. Retrieval opens the file and sends the bytes to the model. The original PDF at `document.path` was not withdrawn. Base64 in PostgreSQL and object storage stay unused. The page image is not written by the code yet.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

One record, not written. The person believes the package should be renamed `rag` and hold both ingestion and retrieval. They have not confirmed the paragraph.

### Should retrieval live in the ingestion package or in its own package — revisit this section

Suggested title, for the person to keep or replace: "Place retrieval in its own package or inside ingestion."

#### Context to carry

The ingestion package describes itself as independent of the agent. `document_entity` rows hold a document id, a page index, a label, and a JSON vector. The agent has no retrieval tool. `assemble_context` keeps a short message window.

#### Decision drivers

- Their belief: ingestion and retrieval share the embeddings mechanism.
- The package description says the pipeline is independent of the agent.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.

#### Considered options

- Leaning, not chosen: rename the ingestion package to `rag` and place ingestion and retrieval there. Their words: "I think, as they would share the embeddigns mechanism, we should rename the ingestion package by rag, and place ingestion and retrieval there".
- Retrieval in a package of its own, named in the opening question, not chosen.

#### Decision outcome to write

Chosen for the page media: store one local image per page and keep its path. Retrieval reads that file and sends the bytes to the model. Their words: "I think I will take that."

The package rename to `rag` remains a belief, not a confirmation.

#### Consequences

- Not yet stated.

#### Confirmation

- Not yet stated.

#### More Information

> for a good architecture, do you think retrieving should be inside ingestion pacjkage or in an independent one?

> I think, as they would share the embeddigns mechanism, we should rename the ingestion package by rag, and place ingestion and retrieval there

> I think I will take that

#### Left open for the person

- Confirming the rename and the two sides inside `rag`.
- Whether the agent may depend on `rag`.
- Whether `document.py` moves into that package.
