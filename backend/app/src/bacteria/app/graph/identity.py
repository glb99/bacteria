"""Which thing a name refers to, and why getting it wrong is survivable.

Every assertion names two nodes, so a node id is referenced by more rows than
anything else here and can never be rewritten. That sounds like it demands
solving entity resolution before anything can be written down. It does not, and
the reason is the distinction this whole package is built on:

**An observation is not an identity.** *A person called "Diane" appeared in this
conversation* is an observation. *That "Diane" and this "Diana Mercer" are the
same person* is a separate claim, made later, on evidence — and when it is made,
**nothing is merged**. A ``same-as`` assertion links the two nodes, both keep
their observations, and the link is retractable like any other claim.

That is what makes the cheap thing here safe. Minting a node per distinct name
is wrong in the sense that one person may end up with several nodes; it is not
wrong in the sense that anything has to be undone. Real resolution — similarity
over names, the confidence bands, a proposal a person accepts — arrives later
and *adds* links rather than rewriting ids.

The two failure modes are worth naming so the difference is clear. Splitting one
person across two nodes is recoverable: assert the link. **Collapsing two people
into one node is not** — their assertions are already interleaved under one id
and nothing records which belonged to whom. So when the lexical match is unsure,
the answer is a new node.

Not built:
    Any resolution beyond exact match on a normalized name. Two spellings, a
    nickname, a married name and an email address are four nodes today. The
    design for the real thing is anchor resolution — exact identifier, then
    alias, then vector similarity — and it belongs with the retrieval work,
    because it needs the same embeddings. What must **not** happen in the
    meantime is fuzzy matching here: a near-miss that guesses wrong commits the
    unrecoverable error above, and normalization is deliberately conservative
    for that reason.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Node:
    """A thing the graph knows about, detached from its row.

    ``node_id`` is opaque and says nothing about the label. A label-derived id —
    ``person:diane`` — reads better in a log and encodes a *mutable* fact into an
    immutable key: correct the spelling of a name and either the id lies about
    what it names, or every assertion referencing it has to be rewritten. The
    label lives in a column where it can be corrected.

    ``first_seen`` and ``last_seen`` are recorded time. A node has no valid time:
    when the thing existed, and what was true of it, are claims, and claims are
    assertions.
    """

    user_id: str
    node_id: str
    label: str
    kind: str
    first_seen: datetime
    last_seen: datetime


def normalize(label: str) -> str:
    """The key two mentions must share exactly to be treated as one thing.

    Case, surrounding whitespace and Unicode composition only. Deliberately
    nothing else — no stemming, no initials, no nickname table, no fuzzy
    distance. Each of those would merge names that *look* alike, and a wrong
    merge is the one mistake here that cannot be undone: two people's assertions
    interleaved under one id, with nothing recording which was whose.

    ``NFKC`` rather than a plain ``casefold`` because the same name arrives
    composed and decomposed from different sources — a transcript typed on macOS
    and an email header need not agree byte for byte about an accent, and two
    nodes for "José" would be a split nobody could see by reading.
    """
    return unicodedata.normalize("NFKC", label).strip().casefold()
