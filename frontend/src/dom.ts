/** The four DOM helpers everything else uses. Kept together so they cannot drift apart. */

export const el = <T extends HTMLElement>(id: string): T => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing element: ${id}`);
  return found as T;
};

/** A tag with text and an optional class, which is most of what this console builds. */
export function text(tag: string, content: string, className?: string): HTMLElement {
  const node = document.createElement(tag);
  node.textContent = content;
  if (className) node.className = className;
  return node;
}

/**
 * The first segment of a uuid or run id, which is what a person reads.
 *
 * Truncated for display only. Every action sends the whole value — a shortened
 * identifier that reached an API call would be an identifier that stopped
 * resolving as soon as two of them shared a prefix.
 */
export const short = (id: string): string => id.slice(0, 8);

export const when = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
