// Derives a readable plain-text rendition of an HTML document for the
// `text/plain` clipboard flavour. Without this, pasting into a plain-text
// target yields a wall of raw HTML/CSS markup. We lean on the DOM parser so
// markup, styles, tables, and images collapse to their text content, then
// trim runs of blank lines down to a single gap.
export function htmlToPlainText(html: string): string {
  const body = new DOMParser().parseFromString(html, "text/html").body;
  const text = body.textContent ?? "";
  return text.replace(/\n{3,}/g, "\n\n").trim();
}
