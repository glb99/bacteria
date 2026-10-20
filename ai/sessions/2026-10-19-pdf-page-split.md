---
date: 2026-10-19
status: exploring
question: "How does the ingestion function divide one PDF into pages?"
adr: ""
---

# How does the ingestion function divide one PDF into pages?

## Why this session

The person is designing the ingestion function that takes one PDF and divides it into pages. The aligned pipeline sessions already chose that split as the first step. This session is the function itself. The person writes any ADR that comes out of it.

## Starting model

From the opening message, before the rest of the interview:

> I'm tryng to design the ingestion function that takes the pdf and divides it into pages

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "Ishould be the first step of the documents endpoint pipeline, for now I want it inside document_service, and it should receive the file and return the pages, I don't know if it should return a generator". Later: "I think it would return a generator but what do you think?" |
| Which decision does this understanding change? | The function: first step of the documents endpoint pipeline, receiving the stored file and returning an iterator of single-page PDF bytes. They chose the generator and the single-page PDF, each with "I take it". The function then moves out of `document_service` and is injected as a dependency. Their words: "it moves, as it will be injected as dependency". |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- The person believes the function is the first step of the documents endpoint pipeline, lives inside `document_service` for now, receives the file, and returns the pages. They first did not know whether it should return a generator. They then said they think it would return a generator, and asked what the assistant thinks. They then chose that recommendation. Their words: "I take it". Source: this session's starting model, 2026-10-19.
- `backend/app/src/app/api/services/document_service.py` defines `validate_document` and `upload_document`. `upload_document` takes a FastAPI `UploadFile`, a `DocumentRepository`, a `FileSystem`, and a `Document`. Neither function splits a PDF or returns pages.
- `backend/app/src/app/api/routes/documents.py` calls `validate_document`, then `upload_document`, and passes the route's `UploadFile` into `upload_document`. The route does not call a page split.
- `backend/app/src/app/core/file_system.py` `LocalFileSystem.upload_file` reads the whole `UploadFile` with `file.file.read()` and writes those bytes to a path.
- `backend/ingestion/src/ingestion/paginator.py` defines `Paginate` and `paginate`. `paginate` yields one single-page PDF per page, using `pypdf`. `backend/ingestion/src/ingestion/__init__.py` says the pipeline is independent of the agent.
- `backend/ingestion/src/ingestion/page.py` `PageExtractor.extract_page` takes one page as `bytes` and returns a `str`.
- The aligned pipeline session chose: separate the uploaded PDF into pages, one visual call per page, join the extracted text in page order. Source: `ai/sessions/2026-10-16-pdf-ingestion-pipeline.md`.
- The aligned 2026-10-17 session defines a **page** as one page of the uploaded PDF, held as an image. The confirmed pipeline splits the PDF into pages, then recognizes diagrams and text blocks. Source: `ai/sessions/2026-10-17-pdf-processing-pipeline.md`.
- `backend/ingestion/pyproject.toml` depends on `pillow`, `google-genai`, `pydantic`, and `dotenv`. It does not depend on a PDF parser.
- On 2026-10-19 the person said the PDF passes through the paginator, the paginator returns an iterator over the pages, and each page is represented as bytes. They asked whether an image conversion is unnecessary if `extract_entities` also takes bytes. Source: this conversation.
- On 2026-10-19 the person said the drawing was only a script for fast testing. Their words: "ok, the drawing was only a script for fast testing". `backend/ingestion/src/scripts/scripts.py` starts with "One-off: ask a visual model for diagram boxes on image.png."
- `extract_entities` in `backend/ingestion/src/ingestion/entity_extractor.py` takes `image_path: Path` and a prompt. It reads that path with `load_image_as_bytes` and calls `model_client.send`. `GeminiMultimodalClient.send` posts those bytes with `mime_type="image/png"`. `Box` documents its edges as 0–1000 relative to the image.
- `backend/ingestion/src/scripts/scripts.py` loads `image.png`, sends it with mime type `image/png`, and draws the returned boxes onto that PNG with PIL.
- `GoldenPage.page` in `backend/ingestion/src/tests/ingestion/test_page_evals.py` is `bytes`. The load test reads those bytes from a file named `page.pdf`.
- The aligned pipeline session records the Gemini document guide, read 2026-10-16: a PDF request is handled with each page as an image. Source: `ai/sessions/2026-10-16-pdf-ingestion-pipeline.md`.
- On 2026-10-19, asked whether the paginator stays in `document_service` or moves into `paginator.py`, the person said "it moves, as it will be injected as dependency".
- `backend/app/src/app/api/deps.py` builds FastAPI dependencies with `Annotated[..., Depends(...)]`. `LocalFilesystemDep` and `DocumentRepositoryDep` are two of them. `upload_document` in `document_service.py` takes a `DocumentRepository` and a `FileSystem` as arguments. The route in `documents.py` receives `DocumentRepositoryDep` and passes it into the service. There is no paginator dependency.

## Inferences

- The function the person is designing does not exist in `document_service` today. Evidence: `document_service.py` defines validate and upload, and neither returns pages.
- "For now" first placed the function in the API service. The person then moved it. Evidence: "it moves, as it will be injected as dependency", answering the choice between `document_service` and `paginator.py`. The function lives in `paginator.py` and is supplied to its caller as a dependency. `paginate` is implemented there. The 2026-10-16 session says the pipeline is independent of the agent. This move puts the function in the ingestion package.
- "Receive the file" matches the `UploadFile` the route already passes into `upload_document`. Evidence: `documents.py` and their sentence. `LocalFileSystem` then reads that file completely into a path. Evidence: `file_system.py`. The person has not said whether the split receives the `UploadFile`, those stored bytes, or the path.
- The person chose the recommended return. Evidence: "I take it", said after the recommendation to implement the split as a generator, type it as an iterator of pages, and iterate it inside the job.
- The next existing contract consumes one page as `bytes`. Evidence: `PageExtractor.extract_page`. The person has now chosen those bytes to be one single-page PDF. Evidence: the second "I take it".
- A generator yields one page and keeps the rest unproduced. That matches one visual call per page. Evidence: the chosen return and the aligned pipeline session. The generator is iterated by the job, in the process that still has the stored PDF open. Evidence: `LocalFileSystem.upload_file` reads the upload onto a path, and the aligned route session returns an id and a not-ready status before the job finishes. The HTTP response stays that id and status.
- A generator has no length. A caller that wants "page 3 of 12" needs a page count taken from the PDF before the loop. A second pass, such as a retry of one page, opens the PDF again. Evidence: the generator protocol. The person accepted this with the rest of the recommendation.
- Typing the return as `Iterator` lets the implementation yield and lets a test pass a list. Evidence: the recommendation they accepted.
- The paginator is the step that returns the iterator. Evidence: their sentence that the PDF passes through the paginator, and the later move into `paginator.py`. `document_service` does not define that function. The existing injection style passes a dependency into the route and then into the service. Evidence: `deps.py`, `documents.py`, and `upload_document`. The person has not said which of those two receives the paginator.
- `extract_entities` does not take page bytes. It takes a PNG path, and the client labels the payload `image/png`. Evidence: `entity_extractor.py`. The conditional "if extract_entities also uses bytes" is not what that function does. The client does take bytes, and those bytes are a PNG.
- Page bytes and PNG bytes are both `bytes`. The mime type distinguishes them. Evidence: `Part.from_bytes(..., mime_type="image/png")` and the golden file name `page.pdf`. A paginator that yields PNG bytes has already made an image. A paginator that yields a single-page PDF has not.
- The provider treats each PDF page as an image during the model call. Evidence: the Gemini guide note in the 2026-10-16 pipeline session. That is the provider's raster. It is a different step from the pipeline writing a PNG.
- `Box` edges are relative to the image, and `scripts.py` paints them with PIL onto a PNG. Evidence: `entity_extractor.py` and `scripts.py`. The person says that drawing is only a fast test. Evidence: their sentence. The pipeline does not include that paint step, so the pipeline does not keep a raster for it.
- The person chose the single-page PDF recommendation. Evidence: "I take it", said after the restatement that the paginator yields single-page PDF bytes, the entity call sends them as `application/pdf`, and the paginator does not render a PNG. The drawing script stays a fast test outside the pipeline. Evidence: "ok, the drawing was only a script for fast testing".

## Shared model

The person has not confirmed this paragraph.

The **page-split function** is the first step of the documents endpoint pipeline. It lives in `paginator.py`. It is injected as a dependency. It receives the stored file, the PDF after upload has written it, and returns an iterator of pages. The implementation is a generator. The HTTP response stays the document id and the not-ready status. When a caller needs a length, the page count is taken from the PDF before the loop. A retry of one page opens the PDF again.

A **job**, in the aligned pipeline session, is the work that runs after that response has been sent: split the PDF, make one visual call per page, and join the text in page order. This session used that word for the caller that walks the iterator. The person asked what it means. No queue, worker, or scheduler exists in the code. They then said: "at first I only want to implement the function that iterates over the pages sequentially." The first implementation is that function. The separate work-after-response is not part of it.

A **file** in this function is that stored PDF. The route's upload handler receives a FastAPI `UploadFile`, and `LocalFileSystem` reads it completely onto a path before the split. The PDF then passes through the **paginator**, which returns the iterator. `paginate` yields one single-page PDF per page. `document_service` does not define the function. The app already injects `LocalFilesystemDep` and `DocumentRepositoryDep` from `deps.py` into the route, and the route passes the repository into `upload_document`. This session has not said whether the route or the service is the one that receives the paginator.

A **page** is one single-page PDF, carried as `bytes`. The person chose this with the second "I take it". The 2026-10-17 session held a page as an image. This choice replaces that holding for the paginator. The provider still handles a PDF page as an image inside the model call. The pipeline does not write a PNG.

The **entity call** takes those page bytes and sends them as `application/pdf`. `extract_entities` today takes a PNG path, and `GeminiMultimodalClient.send` labels its payload `image/png`. That code does not yet do what this choice says.

A **generator** yields one page at a time. An **iterator** is the return type. The implementation yields. A test can pass a list. The person chose the generator with the first "I take it".

The drawing script is a fast test. It is outside the pipeline.

The constraint they will not trade away, and the observation that would show this belief wrong, are unstated.

## Gaps

- The person moved the function into `paginator.py` and said it will be injected as a dependency. They have not yet restated the paragraph.
- Which caller receives that dependency, the route or `document_service`, is unstated.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.
- The function receives the stored file. Whether the argument is the path or the stored bytes is unstated.
- The drawing script is outside the pipeline. A raster kept for painting boxes is not a pipeline step.
- `extract_entities` takes a PNG path and the client sends `image/png`. The chosen entity call sends `application/pdf`. The code does not do that yet.
- `paginate` is implemented. `PaginateDep`, `ExtractEntitiesDep`, and `EmbedDep` are in `deps.py`. The upload route does not take them yet. `GeminiEmbedder` embeds UTF-8 text, so a diagram with no text has nothing to embed. `DocumentRepository` is still only a protocol.
- The person asked what is missing to see the full processing work, then approved a plan to run that processing inside the upload request. `process_document` now walks `iterate_pages`, calls `extract_entities`, embeds each labeled box, and sets the status to `ready`. `POST /documents/uploaded` and `GET /documents/{document_id}` return the id and status. The read response still omits the extracted text. The Alembic revision is written and has not been applied.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| | | | |

## Handoff for a human ADR

One record, not written. The person chose the generator, the single-page PDF bytes, and the move into `paginator.py` as an injected dependency. They have not yet restated the paragraph.

### How the ingestion function divides one PDF into pages — revisit this section

Suggested title, for the person to keep or replace: "Define the function that splits one PDF into pages."

#### Context to carry

The person is designing the function that takes one PDF and divides it into pages. The aligned route session accepts one PDF on upload. The aligned pipeline session and the 2026-10-17 pipeline session both start by splitting that PDF into pages. A page there is one page of the uploaded PDF, held as an image. `PageExtractor.extract_page` takes one page as bytes and returns a string.

`document_service` today validates a file name and uploads an `UploadFile`. It does not split pages. `paginate` in `paginator.py` yields single-page PDF bytes, and `PaginateDep` is defined in `deps.py`. The upload route does not take that dependency yet. The ingestion package describes the pipeline as independent of the agent. `pypdf` is the parser that dependency uses.

#### Decision drivers

- Their belief: the function is the first step of the documents endpoint pipeline.
- First placement, then withdrawn: "for now I want it inside document_service."
- It receives the file and returns the pages.
- The function moves into `paginator.py` and is injected as a dependency. Their words: "it moves, as it will be injected as dependency".
- Their choices, each "I take it": the generator typed as an iterator, iterated by the job, over the stored file; then each page as a single-page PDF sent onward as `application/pdf`, with no PNG from the paginator.
- The drawing script is only a fast test.
- The constraint they will not trade away is unstated.
- The observation that would show the belief wrong is unstated.

#### Considered options

- Named, then superseded by the choice below: the function returns the pages, with the container unnamed.
- Leaning, then chosen: a generator. Their words moved from "I think it would return a generator but what do you think?" to "I take it".
- A concrete sequence of every page, not named by the person.
- Leaning, then chosen: each page is `bytes`. Their question was whether `extract_entities` taking bytes removes an image step.
- Chosen with the second "I take it": those bytes are one single-page PDF, sent onward as `application/pdf`. The paginator does not write a PNG. The drawing script stays a fast test.

#### Decision outcome to write

Chosen by the person: the page-split function is the first step of the documents endpoint pipeline. It lives in `paginator.py` and is injected as a dependency. Their words: "it moves, as it will be injected as dependency". It receives the stored file and returns an iterator of pages. The implementation is a generator. The job iterates it. The HTTP response stays the document id and the not-ready status. When a caller needs a length, the page count is taken from the PDF before the loop. A retry of one page opens the PDF again.

The earlier "for now I want it inside document_service" is withdrawn by that move.

Because the confirmed pipeline runs one visual call per page, so one page is in hand at a time. The stored file, after `LocalFileSystem` reads the upload, is what the generator reads.

Also chosen with "I take it": each yielded page is the bytes of a single-page PDF. The entity call sends those bytes as `application/pdf`. The paginator does not write a PNG. Because the provider handles a PDF page as an image inside the model call, and the drawing script is only a fast test. Their words: "ok, the drawing was only a script for fast testing".

#### Consequences

- The function yields one single-page PDF at a time, as bytes, from the stored PDF.
- The entity call sends those bytes as `application/pdf`.
- The paginator does not write a PNG.
- The drawing script stays outside the pipeline.
- The upload response still carries the id and the not-ready status.
- The job is the caller that iterates the pages.
- A progress count is read from the PDF before the loop.
- A retry opens the stored PDF again.
- `document_service` does not define the paginator. It receives the paginator as an injected dependency, by the person's reason for the move. Which function's parameter that is, the route or the service, is unstated.
- `paginate` yields single-page PDF bytes. `PaginateDep` exists. The upload route does not take it yet.
- A test can supply a list, because the return type is an iterator.

#### Confirmation

- The function yields one single-page PDF at a time.
- The bytes sent to the model are labeled `application/pdf`.
- The route response is the id and the not-ready status.
- The job is what iterates the iterator.
- A page count is available before the loop when the caller needs a length.

#### More Information

> I'm tryng to design the ingestion function that takes the pdf and divides it into pages

> Ishould be the first step of the documents endpoint pipeline, for now I want it inside document_service, and it should receive the file and return the pages, I don't know if it should return a generator

> I think it would return a generator but what do you think?

> I take it

> So at first the pdf document passes through the paginator, that returns an iterator over the pages, each page I think represented as bytes, then if the extract_entities also uses bytes as input, it would not be neccessary to make them images, what do you think?

> ok, the drawing was only a script for fast testing

> I take it

> it moves, as it will be injected as dependency

#### Left open for the person

- Which caller receives the paginator dependency, the route or `document_service`.
- Whether the argument is the stored path or the stored bytes. They accepted "the stored file".
- The constraint, and the observation that would show the belief wrong.
