---
date: 2026-10-21
status: aligned
question: "Where does the page-image path live: a page model, or the document model?"
adr: ""
---

# Where does the page-image path live: a page model, or the document model?

## Why this session

The retriever loads `document_entity` rows and needs one page-image path per page. That column does not exist. The person asked whether it belongs on a new page model or on the document model. The person writes any ADR that comes out of this.

## Starting model

> I think we will need a new database model like page? or store it in document model?

> but I mean, does a document represent a page?

> so what approach do you suggest?

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | A new page model, or storing the path on the document model. They then asked whether a document represents a page, asked for a suggestion, and accepted it with "ok, do it". |
| Which decision does this understanding change? | Where the page-image path is stored. |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- `Document` is one row per uploaded file. Columns: `id`, `file_name`, `path`, `status`. `path` is a string of at most 1024 characters. Source: `backend/app/src/app/models.py`.
- `DocumentEntity` is one row per labeled region. Columns include `document_id`, `page_index`, `label`, box edges, and a JSON `vector`. Several rows can share one `page_index`. There is no image path. Source: `backend/app/src/app/models.py`.
- The retriever groups entities by `(document_id, page_index)` and reads one `image_path` for that page. Source: `backend/agent/src/agent/retriever.py`.
- On 2026-10-20 the person chose one local image file per page, with the path stored in the database. The PDF remains at `document.path`. Source: `ai/sessions/2026-10-20-retrieval-package.md`.
- `load_stored_entities` sets `image_path` to `""` because the row has no such column. Source: `backend/cli/cli.py`.
- `validate_document` creates one `Document` for one file name. `upload_document` writes one PDF at `{DOCUMENTS_DIR}/{document.id}.pdf` and stores that path. `process_document` enumerates pages of that PDF and saves each labeled region with a `page_index`. Source: `backend/app/src/app/api/services/document_service.py`.
- The person asked: "but I mean, does a document represent a page?"

## Inferences

- A document does not represent a page. Upload creates one row and one PDF for one file name, then numbers the pages inside that file. Evidence: `validate_document`, `upload_document`, and `process_document`.
- One path per page matches the chosen file: one image for one `page_index`. Evidence: the 2026-10-20 choice and the retriever grouping.
- The document row already uses its single `path` column for the PDF. A second single string on that row can name one file or one directory. It cannot, by itself, name a different file for each page. Evidence: the `Document` columns.
- An image path on `DocumentEntity` would repeat the same path on every region of that page. Evidence: many entity rows share one `page_index`.
- A page row can hold `document_id`, `page_index`, and `image_path` once. The entity rows already identify that page. Evidence: the entity columns and the retriever key.
- The suggestion, not a choice the person has made: add a page row for each page of a document. One image path lives there. `document.path` stays the PDF. `document_entity` stays the labeled regions and vectors. The person asked "so what approach do you suggest?"

## Shared model

The person has not confirmed this paragraph.

A **document** is one uploaded PDF file. It does not represent a page. One document has many pages. Those pages are the `page_index` values written on `document_entity` while `process_document` walks the PDF. The document's `path` is the original PDF file.

A **page image** is one local file for one page of that PDF. An **entity** is one labeled region on a page, and several entities share a page. The retriever needs the image path once per page.

Two places are open. A **page model** is a row per page: document id, page index, and image path. The **document model** is the existing file row. Its current `path` is the PDF. A single extra string there can name one directory or one file, and the page index would still decide which file inside that directory.

The person accepted the page model with "ok, do it". A `page` row stores `document_id`, `page_index`, and `image_path`, unique on the document and the page index. `document.path` stays the PDF. `document_entity` stays the labeled regions and vectors. `load_stored_entities` copies `image_path` from the matching `page` row. `process_document` writes `{DOCUMENTS_DIR}/{document_id}/{page_index}.png` and inserts that `page` row for every page.

## Gaps

- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.
- The person asked "but the page is not being ingested?" `process_document` now writes `{DOCUMENTS_DIR}/{document_id}/{page_index}.png` and calls `add_page` for every page before it stores entities.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Where does one page-image path live? | On a `page` row: document id, page index, and image path. | "ok, do it" after the page-model suggestion. | yes |

## Handoff for a human ADR

One record, not written. The outcome is open.

### Where the page-image path is stored — revisit this section

Suggested title, for the person to keep or replace: "Store each page-image path on a page row or on the document row."

#### Context to carry

One local image file per page was chosen on 2026-10-20. The PDF stays at `document.path`. The retriever groups regions by document id and page index and opens one image path. `document_entity` stores the vectors and has no path. The loader leaves `image_path` empty.

#### Decision drivers

- Their question: "I think we will need a new database model like page? or store it in document model?"
- One image file per page.
- `document.path` is already the PDF.
- Several entity rows share one page.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.

#### Considered options

- A page model: one row per page, with document id, page index, and image path. Named by the person. Not chosen.
- Store the path on the document model. Named by the person. Not chosen. The existing `path` column is the PDF. One extra string on that row can name one directory or one file.
- An image path on each `document_entity` row. Not named by the person. It would copy one page path onto every region of that page.

#### Decision outcome to write

Chosen: a page model. Their words: "ok, do it", after the suggestion of one row per page with document id, page index, and image path. `document.path` stays the PDF. `document_entity` stays the regions and vectors.

#### Consequences

- `page` is a table. One document and page index has one image path.
- The retriever reads that path when it loads entities.
- `process_document` writes one PNG per page and inserts the `page` row. The person asked "but the page is not being ingested?"

#### Confirmation

- Not yet stated.

#### More Information

> I think we will need a new database model like page? or store it in document model?

> but I mean, does a document represent a page?

> so what approach do you suggest?

> ok, do it

#### Left open for the person

- Page model or document model.
- The constraint they will not trade away.
- The observation that would show the belief wrong.
