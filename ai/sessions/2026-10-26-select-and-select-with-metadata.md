---
date: 2026-10-26
status: exploring
question: "Why does the retriever have select and select_with_metadata?"
adr: ""
---

# Why does the retriever have select and select_with_metadata?

## Why this session

The person asked why both methods exist while defining the page-score test. The page-score session is [2026-10-26-test-for-page-score.md](2026-10-26-test-for-page-score.md).

## Starting model

> why do we have a select and then a select_with_metadata?

They then asked which one runs: "but which one is the one usef"

They then asked whether `select` still earns a place: "so does it make sense to have a select?"

They then asked for the decision: "so should we remove it?"

They then asked whether `select` is the compatibility seam for other documents: "wouldn't it be useful for compability with other type of documents?"

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | They asked why both methods exist. They have not stated their own account. |
| Which decision would this understanding change? | Whether `select` stays once `select_with_metadata` is the method a live turn calls. |

## Evidence

- `RetrievesDocumentPages.select` returns `list[bytes]`. Source: `backend/app/src/app/agent/retriever.py`. `assemble_context` takes `retrieved_documents: list[bytes]` and puts those bytes into the model context. Source: `backend/app/src/app/agent/context.py`.
- `RetrievesDocumentPagesWithMetadata.select_with_metadata` returns `list[RetrievedPage]`. `RetrievedPage` holds `document_id`, `page_index`, `score`, and `content`. Source: `retriever.py`.
- `EmbeddingPageRetriever.select` returns `[page.content for page in self.select_with_metadata(...)]`. The ranking is written once, in `select_with_metadata`. Source: `retriever.py`.
- `run_turn` is typed to take `RetrievesDocumentPages`. When the object implements `RetrievesDocumentPagesWithMetadata`, it calls `select_with_metadata` and records document id, page index, score, and bytes on the `agent.retrieval` span. Otherwise it calls `select` and builds `RetrievedPage` values with `document_id="unknown"`, the enumeration index as `page_index`, and `score=0.0`. The bytes passed to `assemble_context` are `page.content` in both branches. Source: `backend/app/src/app/agent/runtime.py`.
- The observability session records the reason: provenance was added without changing the `select()` return shape, so existing callers stay valid and the runtime can identify the selected page. Source: [2026-10-25-entire-runtime-observability.md](2026-10-25-entire-runtime-observability.md).
- The CLI builds an `EmbeddingPageRetriever` and passes it to `run_turn`. Source: `backend/app/src/app/cli/cli.py`. `build_document_retriever` is typed as returning `RetrievesDocumentPages`. That class defines `select_with_metadata`, so it satisfies `RetrievesDocumentPagesWithMetadata`. `run_turn` then calls `select_with_metadata`, not `select`.
- The only `def select` implementations are the protocol, `EmbeddingPageRetriever`, and the test double in `backend/app/src/tests/agent/test_runtime_observability.py`. That test double also defines `select_with_metadata`, so the runtime's `select` fallback does not run for it. Direct calls of `EmbeddingPageRetriever.select` are in `backend/app/src/tests/agent/test_retriever.py` and `backend/app/src/tests/test_load_stored_entities.py`. No other production retriever class exists.
- `_user_content` treats every returned byte string as a PNG image: `{"type": "image", "media_type": "image/png", "data": page}`. Source: `backend/app/src/app/agent/context.py`. `select` and `select_with_metadata` feed that same list. The protocol docstring names recency as another picking rule, and the query argument stays so a later ranking rule does not change the method's shape. It does not name another document type. Source: `retriever.py`.

## Inferences

- `select` is the contract the model context needs: the page images for this turn. `select_with_metadata` is the same selection plus the provenance the trace and the eval assert. This follows from `context.py`, `runtime.py`, and the observability session.
- On `EmbeddingPageRetriever` the two methods are not two rankings. `select` drops the provenance from `select_with_metadata`. This follows from the method body.
- A retriever may implement only `select`. `run_turn` still runs, and the trace then lacks the real page index and score. This follows from the `isinstance` branch. No production class and no current test double is in that position. The fallback is unexercised by the tests that exist today.
- Removing `select` means removing the bytes-only protocol, the runtime fallback, and the tests' direct calls. `run_turn` would require `select_with_metadata` and would still pass `page.content` to context assembly. This follows from `runtime.py` and `context.py`. The observability session chose to keep the bytes return shape. Removing `select` reverses that choice. The page-score test does not need that removal: it can call `select_with_metadata` while `select` remains.
- `select` does not make another document type fit. Both methods return the page images, and context assembly labels every byte string as `image/png`. A paper and an architecture article already share `select_with_metadata`, because each stored entity carries a document id and a page index. A future document that is not a page image fits neither method. This follows from `context.py`, `RetrievedPage`, and the entity store.

## Shared model

`select` answers which page images the turn should see. It returns `list[bytes]`, and that is all context assembly reads.

`select_with_metadata` answers the same question and also returns the document id, the page index, and the score. A live turn uses this method. The CLI passes an `EmbeddingPageRetriever` into `run_turn`, that class implements the metadata protocol, and `run_turn` calls `select_with_metadata`. The article eval calls it directly. `select` remains the fallback for a retriever that has no provenance, and some unit tests call it.

`EmbeddingPageRetriever` ranks in `select_with_metadata`. Its `select` calls that method and keeps `content`. One ranking, two return shapes. The bytes shape stayed so a retriever that only returns images still satisfies `run_turn`.

For this retriever, `select` does not add a behaviour. It keeps the type `run_turn` requires and gives tests a way to assert image bytes. The compatibility it provides is a retriever that cannot name its pages. It is not compatibility across document types. Papers and other page-image documents already share `select_with_metadata`: the bytes are `content`, and the document id and page index say which page. Context assembly renders those bytes as PNG images either way. The runtime fallback that serves a bytes-only retriever invents `document_id="unknown"`, an enumeration index, and score `0.0`.

## Gaps

- The person has not confirmed this account.
- The person asked whether to remove `select`. The recommendation recorded below is not a choice they have confirmed. Removing it is a separate change from the page-score test in [2026-10-26-test-for-page-score.md](2026-10-26-test-for-page-score.md).

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

No ADR is named. The person chose option 2.

Context: the retriever had `select` returning page-image bytes and `select_with_metadata` returning `RetrievedPage`. A live turn already called `select_with_metadata`. The person asked whether `select` was useful for other document types. It was not: both methods returned the same page images, and context assembly renders those bytes as PNG.

Drivers in the person's words: "why do we have a select and then a select_with_metadata?"; "but which one is the one usef"; "so does it make sense to have a select?"; "wouldn't it be useful for compability with other type of documents?"; "so remove it".

Considered options: (1) keep `select` as the bytes-only protocol and the runtime fallback; (2) make `select_with_metadata` the only retriever method and have `run_turn` read `page.content` for the model context. Option 1 matches the observability decision to preserve the bytes return shape. Option 2 matches the callers that exist now: the CLI, the eval, and the runtime metadata branch. The recommendation in this session is option 2, done separately from the page-score test. The person chose option 2 with "so remove it". `select` and `RetrievesDocumentPages` are removed. `run_turn` requires `RetrievesDocumentPagesWithMetadata` and calls `select_with_metadata`. Context assembly still receives `page.content`. The unit tests that called `select` now call `select_with_metadata` and assert the image bytes. `uv run --directory backend/app -m pytest src/tests/agent/test_retriever.py src/tests/agent/test_runtime_observability.py src/tests/test_load_stored_entities.py` passed, 6 tests.

Consequences: option 2 is now the code. The bytes-only protocol and the runtime fallback are gone. The page-score test still belongs on `select_with_metadata` and has not been added.

Confirmation: not yet.

More Information in the person's words: "so remove it".

Open questions: none for this removal. The page-score test is still unwritten. No ADR is named.
