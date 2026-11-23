// Small rules of the question card, kept here so they can be tested without rendering.

/** A card may refuse a written answer (e.g. which app the request goes into — one of the options only). */
export function acceptsFreeText(card: { allow_free_text?: boolean }): boolean {
  return card.allow_free_text !== false;
}

/** Quote an option in a sentence; an option that already holds 「」 gets ‘’ instead of a doubled 「「…」」. */
export function quoteOption(option: string): string {
  return option.includes("「") ? `‘${option}’` : `「${option}」`;
}
