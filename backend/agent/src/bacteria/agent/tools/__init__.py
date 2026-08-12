"""Capabilities: what exists, whether it may run, and running it.

Three modules for three questions that are genuinely separate and are usually
written as one:

- :mod:`~bacteria.agent.tools.registry` — what tools exist, and which the model is
  told about this run.
- :mod:`~bacteria.agent.tools.approval` — whether this specific call, with these
  arguments, should happen now.
- :mod:`~bacteria.agent.tools.execution` — actually running it, once and only once
  the first two have been answered.

Keeping them apart is the point. Fold approval into the handler and it becomes
invisible; fold execution into the registry and describing a capability starts
implying the authority to use it. The seam this layer protects is that the model
*asks* and the system *acts*, and they are not the same event.

:mod:`~bacteria.agent.tools.notes` is a worked example — copy its shape when adding a
tool.
"""
