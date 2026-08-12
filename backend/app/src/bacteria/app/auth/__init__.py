"""Who is calling, and nothing about what they may do.

Owns credentials: issuing an API key, storing it safely, and turning a presented
key back into a :class:`~bacteria.app.auth.principal.Principal`. That is
*authentication* — establishing identity — and it is the whole of this package's
job.

Must not: decide access. "This caller is authenticated" and "this caller may
read that session" are different questions with different failure modes, and a
package that answers both makes the second invisible. Authorization lives with
the resource being protected, because only that feature knows what owning one
means — see ``bacteria.app.chat.access``.

That split is the same one the agent draws between a session and an
authorization decision, and for the same reason: knowing which record to load is
not knowing whether you may have it.
"""
