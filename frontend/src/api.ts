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
export type Project = components["schemas"]["ProjectOut"];
export type ArchitectureModel = components["schemas"]["ModelOut"];
export type ArchModule = components["schemas"]["ModuleOut"];
export type ArchImport = components["schemas"]["ImportOut"];
export type ArchBoundary = components["schemas"]["BoundaryOut"];
export type ArchCrossing = components["schemas"]["CrossingOut"];
export type ArchProposal = components["schemas"]["ClassificationOut"];

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
  const { data, error, response } = await call;
  if (response.status === 401) throw new Unauthenticated();
  if (data === undefined) throw new Error(refusal(error) ?? `the API answered ${response.status}`);
  return data;
}

/**
 * The API's own words for why it refused, when it gave any.
 *
 * Worth carrying rather than replacing with a status code, because some refusals
 * are written for the person reading them: renaming a node onto a taken name
 * answers with the verb that resolves it, and "the API answered 409" would throw
 * that away and leave a dead end where there is an invitation.
 */
function refusal(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : null;
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

/**
 * Stop believing a claim.
 *
 * `POST` to a verb rather than `DELETE` of the resource, mirroring the route:
 * nothing is deleted, the row stays and its belief interval closes. The reply
 * carries what changed, so a caller redraws from it rather than re-fetching the
 * graph to discover that it should.
 */
export const retractAssertion = (assertionId: string) =>
  unwrap(
    api.POST("/graph/assertions/{assertion_id}/retract", {
      params: { path: { assertion_id: assertionId } },
    }),
  );

/**
 * Endorse a claim, so a prompt may be told it.
 *
 * The only act here that keeps something. The rest take away, which is why the
 * console could be complete-looking and still leave the graph unable to say
 * anything to the model it belongs to.
 */
export const confirmAssertion = (assertionId: string) =>
  unwrap(
    api.POST("/graph/assertions/{assertion_id}/confirm", {
      params: { path: { assertion_id: assertionId } },
    }),
  );

export const rejectConclusion = (conclusionId: string) =>
  unwrap(
    api.POST("/graph/conclusions/{conclusion_id}/reject", {
      params: { path: { conclusion_id: conclusionId } },
    }),
  );

export const renameNode = (nodeId: string, label: string) =>
  unwrap(
    api.POST("/graph/nodes/{node_id}/rename", {
      params: { path: { node_id: nodeId } },
      body: { label },
    }),
  );

export const linkNodes = (left: string, right: string) =>
  unwrap(api.POST("/graph/links", { body: { left, right } }));

export const listProjects = () => unwrap(api.GET("/architecture/projects"));

export const addProject = (location: string, name = "") =>
  unwrap(api.POST("/architecture/projects", { body: { location, name } }));

/**
 * The codebase as it stands on disk right now, judged against its rules.
 *
 * Re-read server-side on every call rather than cached, so this is the one
 * endpoint here where asking twice can honestly answer differently — which is
 * the point when the thing being described is a working tree.
 */
export const readArchitecture = (projectId: string) =>
  unwrap(
    api.GET("/architecture/projects/{project_id}/model", {
      params: { path: { project_id: projectId } },
    }),
  );

/**
 * Agree or disagree with something the codebase suggested about itself.
 *
 * The only write this surface has. It answers with the proposal carrying its
 * verdict, so a caller repaints one card rather than re-reading a whole model
 * to discover that one line changed.
 */
export const judgeClassification = (
  projectId: string,
  subject: string,
  claim: string,
  verdict: "agreed" | "disagreed",
) =>
  unwrap(
    api.POST("/architecture/projects/{project_id}/classifications", {
      params: { path: { project_id: projectId } },
      body: { subject, claim, verdict },
    }),
  );
