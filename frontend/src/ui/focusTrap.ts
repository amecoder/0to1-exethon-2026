// Keeping Tab inside a modal dialog (shared by the agent log drawer and the full-screen artifact view).
// Everything Tab can land on (links, form fields, frames and custom tab stops included).
export const FOCUSABLE = "a[href], button, input, select, textarea, summary, iframe, [tabindex]:not([tabindex='-1'])";

// Where Tab should go instead of the browser's default: wrap at either end, pull focus back in when it
// sits outside, otherwise null (let the browser move it).
export function wrapTarget<T>(items: T[], active: T | null, shift: boolean): T | null {
  if (items.length === 0) return null;
  const first = items[0];
  const last = items[items.length - 1];
  if (active === null || !items.includes(active)) return shift ? last : first;
  if (shift && active === first) return last;
  if (!shift && active === last) return first;
  return null;
}

export function focusablesIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.hasAttribute("disabled") && el.getClientRects().length > 0);
}

// Keydown handler body: call on Tab inside the dialog.
export function trapTab(root: HTMLElement, e: { key: string; shiftKey: boolean; preventDefault: () => void }): void {
  if (e.key !== "Tab") return;
  const target = wrapTarget(focusablesIn(root), document.activeElement as HTMLElement | null, e.shiftKey);
  if (!target) return;
  target.focus();
  e.preventDefault();
}
