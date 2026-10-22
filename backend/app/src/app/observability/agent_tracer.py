from typing import Protocol


class AgentSpan(Protocol):
    def finish(self, output: str, usage: dict, metadata: dict) -> None: ...


class AgentTracer(Protocol):
    def start(self, name: str, input: str, metadata: dict) -> AgentSpan: ...
    def get_subprocess_env(self) -> dict[str, str]: ...
