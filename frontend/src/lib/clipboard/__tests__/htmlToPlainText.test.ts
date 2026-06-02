import { describe, expect, it } from "vitest";
import { htmlToPlainText } from "../htmlToPlainText";

describe("htmlToPlainText", () => {
  it("strips markup, tables, images, and inline styles to readable text", () => {
    const html = [
      "<html><head><style>.x{color:red}</style></head><body>",
      '<table style="width:100%"><tr><td><img src="hero.jpg" alt="" /></td></tr>',
      "<tr><td>Villa Sol</td><td>€1,234.50</td></tr></table>",
      "</body></html>",
    ].join("");

    const text = htmlToPlainText(html);

    expect(text).not.toContain("<table");
    expect(text).not.toContain("<img");
    expect(text).not.toContain("style=");
    expect(text).toContain("Villa Sol");
    expect(text).toContain("€1,234.50");
  });

  it("collapses runs of 3+ blank lines down to a single gap and trims", () => {
    const html = "<body>  <p>One</p>\n\n\n\n<p>Two</p>  </body>";
    const text = htmlToPlainText(html);
    expect(text).not.toMatch(/\n{3,}/);
    expect(text.startsWith("One")).toBe(true);
  });
});
