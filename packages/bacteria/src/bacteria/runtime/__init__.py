"""Advancing a run from input to committed result.

Owns sequencing and step discipline: what happens in what order, what counts as
a step, and what must survive when a step fails. It is the only layer that sees
the whole turn.

Must not: absorb the logic of the layers it calls. The runtime decides *when*
context is assembled, a model is called, a tool is executed, or state is
written — never *how*. That is the difference between an orchestrator and a
god object, and it is the boundary this layer is most likely to lose, because
every one of those things is briefly easier to do inline.
"""
