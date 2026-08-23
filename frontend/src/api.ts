/**
 * The typed client, and the names the rest of the console uses.
 *
 * Every type here is an alias into `api.gen.ts`, never a hand-written copy.
 * A copy is a second definition of the same contract, and the second one is the
 * one that stops matching — which is the whole reason the client is generated.
 */

import createClient from "openapi-fetch";
import type { components, paths } from "./api.gen";

/**
 * No `baseUrl`, and the absence is load-bearing.
 *
 * ADR 0005 makes `SameSite=Strict` the CSRF answer, which holds only while this
 * page and the API share an origin. A base URL pointing elsewhere would compile,
 * run, and silently stop sending the cookie.
 */
export const api = createClient<paths>();

export type SessionSummary = components["schemas"]["SessionSummaryOut"];
export type TranscriptEntry = components["schemas"]["TranscriptEntry"];
export type MemoryEntry = components["schemas"]["MemoryEntryOut"];
export type Proposal = components["schemas"]["ProposalOut"];
export type Held = components["schemas"]["HeldOut"];
export type ExtractionProgress = components["schemas"]["ExtractionProgressOut"];
export type Graph = components["schemas"]["GraphOut"];
export type GraphNode = components["schemas"]["NodeOut"];
export type GraphAssertion = components["schemas"]["AssertionOut"];
export type GraphConflict = components["schemas"]["ConflictOut"];
export type GraphConclusion = components["schemas"]["ConclusionOut"];

/** Raised when the API refuses the session, so callers can send the user back to sign-in. */
export class Unauthenticated extends Error {}

/**
 * Unwrap a call, turning 401 into something the shell can act on.
 *
 * **A session can expire between two requests**, and it will: they last twelve
 * hours and a console is left open. Without this, that arrives as `undefined`
 * data somewhere deep in a render and shows as an empty screen rather than as
 * "sign in again".
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, response } = await call;
  if (response.status === 401) throw new Unauthenticated();
  if (data === undefined) throw new Error(`the API answered ${response.status}`);
  return data;
}

/**
 * The same, for calls that answer 204 and therefore have no body.
 *
 * Separate rather than making `unwrap` tolerate a missing body, because "no
 * content, by design" and "a body I expected and did not get" are different
 * events and only one of them is fine. Collapsing them would make every typo in
 * a response model look like a successful call.
 */
export async function expectNoContent(
  call: Promise<{ response: Response }>,
): Promise<void> {
  const { response } = await call;
  if (response.status === 401) throw new Unauthenticated();
  if (!response.ok) throw new Error(`the API answered ${response.status}`);
}

export const listSessions = () => unwrap(api.GET("/chat/sessions"));

export const createSession = () => unwrap(api.POST("/chat/sessions"));

export const readTranscript = (sessionId: string) =>
  unwrap(
    api.GET("/chat/sessions/{session_id}/transcript", { params: { path: { session_id: sessionId } } }),
  );

export const readMemory = (sessionId: string) =>
  unwrap(api.GET("/chat/sessions/{session_id}/memory", { params: { path: { session_id: sessionId } } }));

/**
 * The whole memory graph for the signed-in caller.
 *
 * No session id, and the absence is the API's design rather than an omission
 * here: a graph belongs to a person and outlives every conversation it was
 * learned in, so there is no id to pass and therefore no id to get wrong.
 */
export const readGraph = () => unwrap(api.GET("/graph"));

export const readConclusions = () => unwrap(api.GET("/graph/conclusions"));

export const readProposals = (sessionId: string) =>
  unwrap(
    api.GET("/chat/sessions/{session_id}/memory-proposals", {
      params: { path: { session_id: sessionId } },
    }),
  );

export const readExtraction = (sessionId: string) =>
  unwrap(
    api.GET("/chat/sessions/{session_id}/extraction", { params: { path: { session_id: sessionId } } }),
  );

export const takeTurn = (sessionId: string, text: string) =>
  unwrap(
    api.POST("/chat/sessions/{session_id}/turns", {
      params: { path: { session_id: sessionId } },
      body: { text },
    }),
  );

/**
 * Accept a proposal at a scope.
 *
 * `source` and `key` are both in the path because together they are the
 * proposal's identity: two proposers may suggest the same key, and the reviewer
 * chose between them.
 */
export const acceptProposal = (sessionId: string, source: string, key: string, scope: "session" | "user") =>
  unwrap(
    api.POST("/chat/sessions/{session_id}/memory-proposals/{source}/{key}", {
      params: { path: { session_id: sessionId, source, key }, query: { scope } },
    }),
  );

export const rejectProposal = (sessionId: string, source: string, key: string) =>
  expectNoContent(
    api.DELETE("/chat/sessions/{session_id}/memory-proposals/{source}/{key}", {
      params: { path: { session_id: sessionId, source, key } },
    }),
  );

export const openSession = (key: string) => unwrap(api.POST("/auth/session", { body: { key } }));

export const closeSession = () => api.DELETE("/auth/session");
