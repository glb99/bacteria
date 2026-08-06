"""The authoritative record of a conversation, and the only thing that writes it.

Owns session identity and the three kinds of state a conversation accumulates —
transcript, working state, and memory — kept apart because they have different
lifecycles and merging them loses the difference.

Must not: be bypassed. Everything a model or runtime produces arrives here as a
proposal and becomes real only when this layer applies it. Reads return deep
copies specifically so that a caller cannot mutate authoritative state by
accident, which turns "only this layer writes" from a convention into a
property of the code.
"""
