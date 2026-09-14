from dataclasses import dataclass

from backend.agent.src.agent.agent.model.protocol import ModelResponse


@dataclass
class RunResult:
    """The outcome of one completed turn.

    Attributes:
        run_id: Identifies this run. Generated per turn and stamped onto every
            transcript item the turn commits, so it selects the evidence this
            result was produced from — including on the failure path, where the
            exception carries no result but the evidence is committed anyway.
        response: The final model response, after any tool round.

    Deliberately does not carry the committed state. It used to, and building it
    meant re-reading the whole conversation at the end of every turn to produce a
    value nothing read — its own docstring told callers not to trust it and to
    re-read the store instead, which is now the only option and always was the
    right one. See
    [ADR 0023](../../docs/adr/0023-write-methods-return-what-the-caller-needs.md).
    """

    run_id: str
    response: ModelResponse
