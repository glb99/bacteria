---
date: 2026-10-24
status: aligned
question: "How can I verify agent CLI article retrieval works?"
adr: ""
---

# How can I verify agent CLI article retrieval works?

## Why this session

Clarify what evidence shows that the local agent CLI retrieves useful pages from the uploaded article and uses them in its answer.

## Starting model

In the previous retrieval discussion, the person expected retrieval to work (“yes”) and chose to run the CLI locally against the database in Docker. They now ask how to know it works.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | “yes” (from the previous session); the present question asks how to verify it. |
| Which decision would this understanding change? | |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- `backend/app/src/tests/test_load_stored_entities.py` verifies a stored `/data/documents/...` path is mapped to a local file and that `EmbeddingPageRetriever.select` returns its bytes.
- The prior runtime check loaded 188 entities from the host CLI's database URL; all 188 image paths existed locally. With an injected stored vector, the retriever returned one non-empty image (457,373 bytes). No live model request was made.
- The focused test does not call the model or verify ranking for a natural-language question.
- `backend/app/src/app/agent/runtime.py` calls retrieval with `limit=1` on every turn, then assembles context and sends it to the model client.
- `backend/app/src/app/agent/context.py` places a retrieved image block with the user's text when a non-empty page is returned.
- `backend/app/src/app/agent/retriever.py` ranks pages by summed cosine similarity to embeddings of stored entity labels. It returns up to the requested limit, but does not expose the selected page metadata through its `list[bytes]` result.
- The aligned session `ai/sessions/2026-10-24-agent-cli-article-retrieval.md` records that one document is ready with 15 pages and 188 entity rows, that local image-path mapping is implemented, and that model-answer behavior remains unchecked.
- In the alignment check, the person confirmed the model (“Yes”), identified relevant-page selection as the most important gap, and chose to run one live CLI question with a known answer.

## Inferences

- The unit test and runtime check show that local retrieval can load and return an image. They do not establish that a natural-language query selects the expected page, that the model receives it, or that the final answer is accurate.
- A meaningful end-to-end check needs a question with a known answer and a page that visibly supports it; checking both the returned page and the model's answer would distinguish retrieval success from answer quality.
- The current retriever interface returns image bytes without page/document identity, so observing which page was selected may require a test seam, temporary debug output, or an implementation change.
- The chosen live question has not been selected or run.

## Shared model

We have verified that the local CLI loads indexed entity vectors and resolves the saved image paths, and that the retriever can return page bytes. We have not verified that a natural-language question ranks the expected article page, nor that the model gives a supported answer. The person chose one live CLI question with a known answer as the next check, focused on relevant-page selection. The current CLI does not show which page it selected, so a correct answer alone is useful evidence but does not prove which image was sent.

## Gaps

- What exact outcome the person counts as “works” is not specified: path loading, selecting the expected page, using it in the model request, or giving a correct answer.
- The article's title and a question with a known page/answer have not been provided in this session.
- No live CLI/model call has been made, and the selected page is not directly surfaced.

## Alignment check

| Does the current evidence prove end-to-end article retrieval? | It proves paths load and the retriever can return bytes, not that a normal question selects the right page and the model answers correctly. | “Yes” to the stated model. | Yes |
| Which gap matters most? | Whether the expected article page is selected. | “Whether the relevant page is selected” | Yes |
| What test would you choose next? | The person decides which verification to run. | “Run one live CLI question with a known answer” | Yes |

## Handoff for a human ADR

No ADR is named. The person chose one live CLI question with a known answer as the next check, primarily to verify relevant-page selection. Host path mapping and byte retrieval are already tested, but natural-language ranking and model behavior are not. This verification has not yet been run. The CLI currently does not reveal the selected page identity; a follow-up implementation decision may be needed if direct proof of the selected page is required.
