/**
 * The shell: signing in, and which tab is showing.
 *
 * Everything about a conversation lives in `chat.ts` and everything about the
 * graph in `graph.ts`. This file owns the two things neither of them can: whether
 * there is a session at all, and which tab the two are competing for.
 */

import { closeSession, openSession, Unauthenticated } from "./api";
import * as chat from "./chat";
import { el } from "./dom";
import * as graph from "./graph";

const signIn = el("sign-in");
const signInForm = el<HTMLFormElement>("sign-in-form");
const signInError = el("sign-in-error");
const keyInput = el<HTMLInputElement>("key");
const workspace = el("workspace");
const who = el("who");
const signOut = el<HTMLButtonElement>("sign-out");
const tabs = el<HTMLDivElement>("tabs");
const tabError = el("tab-error");
const panels = {
  chat: el("tab-chat"),
  graph: el("tab-graph"),
};

type Tab = keyof typeof panels;
let tab: Tab = "chat";

const show = (element: HTMLElement, visible: boolean) => {
  element.hidden = !visible;
};

function showSignIn(message?: string): void {
  show(signIn, true);
  show(workspace, false);
  show(signOut, false);
  show(who, false);
  if (message) {
    signInError.textContent = message;
    show(signInError, true);
  }
  keyInput.focus();
}

/**
 * Reload the visible tab, sending the user back to sign-in if the session went.
 *
 * **Every call goes through here**, so an expired session cannot show up as an
 * empty screen in one tab and a working one in the other. Sessions last twelve
 * hours and a console is exactly the thing left open for longer than that.
 */
async function refresh(): Promise<void> {
  show(tabError, false);
  try {
    if (tab === "chat") {
      await chat.refresh();
    } else {
      graph.setSession(chat.currentSession());
      await graph.refresh(chat.currentSession());
    }
    show(workspace, true);
    show(signIn, false);
    show(signOut, true);
  } catch (error) {
    if (error instanceof Unauthenticated) {
      showSignIn("that session has ended — sign in again");
      return;
    }
    // Shown, not rethrown. This handler runs inside an async event listener, so
    // a rethrow becomes an unhandled promise rejection: the panel has already
    // switched, nothing renders, and the page looks like the click did nothing.
    // "Nothing happened" is the worst failure a UI can report, because it is
    // indistinguishable from working — and it cost a real debugging session.
    //
    // The message is deliberately the raw error. This is a console for the
    // person who runs the server; a friendlier string would hide the status code
    // that says which half is broken.
    tabError.textContent = `${tab} failed to load — ${String(error)}`;
    show(tabError, true);
    show(workspace, true);
    // Rethrown as well, so the browser console still gets a stack for whoever
    // is looking there. The line above is for whoever is not.
    throw error;
  }
}

tabs.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || !target.dataset["tab"]) return;

  tab = target.dataset["tab"] as Tab;
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("on", button === target);
  }
  for (const [name, panel] of Object.entries(panels)) {
    show(panel, name === tab);
  }
  await refresh();
});

signInForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  show(signInError, false);

  try {
    const opened = await openSession(keyInput.value);
    who.textContent = `as ${opened.principal_id}`;
    show(who, true);
  } catch (error) {
    // One message for every failure, matching the server, which answers a single
    // 401 for a malformed key, an unknown one, a wrong secret and a revoked one.
    // A page that guessed between them would undo that deliberately.
    showSignIn(
      error instanceof Unauthenticated ? "that key was not accepted" : String(error),
    );
    return;
  } finally {
    // Cleared whether or not it worked: the value is a live credential and the
    // cookie is what every later request uses.
    keyInput.value = "";
  }

  await refresh();
});

signOut.addEventListener("click", async () => {
  await closeSession();
  // Asked again rather than assumed. Logout answers 204 even when nothing was
  // ended, so the only honest way to know what the browser now holds is to make
  // a request with it.
  await refresh().catch(() => showSignIn());
});

// Whether we are signed in is decided by asking. The cookie is HttpOnly, so
// there is nothing on this page to consult and nothing worth trusting if there
// were.
await refresh().catch((error) => {
  if (error instanceof Unauthenticated) showSignIn();
  else throw error;
});
