---
date: 2026-10-26
status: aligned
question: "When is a test worth adding?"
adr: ""
---

# When is a test worth adding?

## Why this session

The person asked for this to be remembered after rejecting the way tests were adapted when `select` was removed.

## Starting model

> I definitely don't like how do you make tests, after each feature/bug... they should be done carefuly, making them actually useful

> can you remember it?

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | Tests should be written carefully and be useful. They should not be produced after each feature or bug. |
| Which decision would this understanding change? | Whether a code change gets a new or rewritten test, and what that test asserts. |

## Evidence

- Removing `select` was followed by rewriting `test_select_returns_the_highest_scoring_page_image`, `test_select_skips_an_entity_with_no_page_image`, and the retriever call in `test_load_stored_entities_reads_document_entity_rows` so they still passed. The first form of those assertions kept only the image bytes and dropped `document_id` and `page_index`.
- The load assertion then compared the whole `RetrievedPage`, including `score=1.0`. The run returned `score=0.9999999999999998` for the stored vector `[0.25, 0.75]`. That score is cosine rounding, and the load test already checks the vector on the entity.
- `test_select_returns_the_highest_scoring_page_image` uses two perfect matches on one page. The sum of those cosines is `2.0` and the best entity cosine is `1.0`. Asserting the score there would freeze the addition rule inside a test whose fixture cannot separate the two rules.

## Inferences

- A test earns a place when its assertion is the behavior that test exists to protect. Adapting an assertion so the suite stays green after an API change does not do that. This follows from the byte-only assertions and from the person's words.
- The load test's retriever check is the loaded document, page index, and file bytes. The cosine is a different behavior. This follows from the failed equality and from the entity assertions already in that test.
- The highest-page test checks which page image is returned. Its fixture does not define the page-score rule, so its assertion does not include the score. This follows from the two cosines on page 1.

## Shared model

A test is written carefully, for a behavior worth protecting. It is not added or rewritten after each feature or bug so that the suite still passes.

The assertion is the behavior that test exists for. An API change is not a reason to keep an old check by discarding the fields the caller now uses, and it is not a reason to assert a number that belongs to a different rule.

## Gaps

- The person has not named a file where this rule should also live outside `ai/sessions/`.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| When is a test worth adding? | When it is written carefully and its assertion is a behavior worth protecting, not as a companion to each feature or bug. | "they should be done carefuly, making them actually useful" and "can you remember it?" | Yes |

## Handoff for a human ADR

No ADR is named. The person asked for the rule to be remembered. No code convention file was added.

Context: tests were adapted after `select` was removed. The person rejected that practice.

Drivers in the person's words: "I definitely don't like how do you make tests, after each feature/bug... they should be done carefuly, making them actually useful"; "can you remember it?"

Considered options: the person chose the rule above. A page-score test is still unwritten, and this rule applies to it.

Consequences: a later change does not get a test unless the test names a behavior worth protecting. The assertions in the retriever tests were corrected to match the behaviors those tests already had.

Confirmation: the person asked for the rule to be remembered, in those words.

More Information in the person's words: "can you remember it?"

Open questions: none. No ADR is named.
