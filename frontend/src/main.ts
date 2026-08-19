/**
 * The smallest page that exercises every link in the chain.
 *
 * Not Console v0 — it has one screen and no tabs. What it proves is that the
 * static mount, the session cookie, the same-origin assumption `SameSite=Strict`
 * rests on, and the generated client all work together against a real server.
 * Each of those was verified separately; none of them had been used at once.
 */

import createClient from "openapi-fetch";
import type { paths } from "./api.gen";

/**
 * No `baseUrl`, and that is the same-origin requirement showing up in code.
 *
 * ADR 0005 makes `SameSite=Strict` the CSRF answer, which holds only while this
 * page and the API share an origin. A base URL pointing elsewhere would compile,
 * run, and silently stop sending the cookie — so the absence of one is load
 * bearing rather than a default nobody changed.
 */
const api = createClient<paths>();

const el = <T extends HTMLElement>(id: string): T => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing element: ${id}`);
  return found as T;
};

const signIn = el("sign-in");
const signInForm = el<HTMLFormElement>("sign-in-form");
const signInError = el("sign-in-error");
const keyInput = el<HTMLInputElement>("key");
const sessions = el("sessions");
const sessionList = el<HTMLUListElement>("session-list");
const sessionsEmpty = el("sessions-empty");
const who = el("who");
const signOut = el<HTMLButtonElement>("sign-out");

const show = (element: HTMLElement, visible: boolean) => {
  element.hidden = !visible;
};

const when = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/**
 * Render the session list, or the sign-in panel if the server refuses.
 *
 * **The server decides whether we are signed in, not this page.** There is
 * nothing in `localStorage` to consult and nothing in a variable to trust: the
 * cookie is `HttpOnly`, so a 401 from a real request is the only honest way to
 * know. That also means a session expiring mid-visit shows the sign-in panel on
 * the next call rather than a screen of empty data.
 */
async function render(): Promise<void> {
  const { data, error, response } = await api.GET("/chat/sessions");

  if (response.status === 401) {
    show(signIn, true);
    show(sessions, false);
    show(who, false);
    show(signOut, false);
    keyInput.focus();
    return;
  }

  if (error || !data) {
    signInError.textContent = `the API answered ${response.status}`;
    show(signInError, true);
    show(signIn, true);
    return;
  }

  show(signIn, false);
  show(sessions, true);
  show(signOut, true);

  sessionList.replaceChildren(
    ...data.map((session) => {
      const item = document.createElement("li");

      const id = document.createElement("code");
      id.textContent = session.session_id;

      const activity = document.createElement("span");
      activity.className = "when";
      activity.textContent = `active ${when(session.last_activity_at)}`;

      item.append(id, activity);
      return item;
    }),
  );
  show(sessionsEmpty, data.length === 0);
}

signInForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  show(signInError, false);

  const { data, response } = await api.POST("/auth/session", {
    body: { key: keyInput.value },
  });

  // Cleared whether or not it worked. The value is a live credential and it has
  // done its whole job by now -- the cookie is what every later request uses.
  keyInput.value = "";

  if (!data) {
    // The same message for every failure, matching what the server does: it
    // answers one 401 for a malformed key, an unknown one, a wrong secret and a
    // revoked one, and a page that guessed between them would undo that.
    signInError.textContent =
      response.status === 401 ? "that key was not accepted" : `the API answered ${response.status}`;
    show(signInError, true);
    keyInput.focus();
    return;
  }

  who.textContent = `as ${data.principal_id}`;
  show(who, true);
  await render();
});

signOut.addEventListener("click", async () => {
  await api.DELETE("/auth/session");
  // Re-asked rather than assumed. Logout is idempotent and answers 204 even when
  // nothing was ended, so the only way to know what the browser now holds is to
  // make a request and see.
  await render();
});

await render();
