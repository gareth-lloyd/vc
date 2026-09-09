"""Small text helpers shared across apps."""

from __future__ import annotations

import markdown as _markdown


def render_markdown(text: str) -> str:
    """Render operator-authored Markdown to a safe HTML fragment.

    Used for `TermsVersion.body_markdown` in the quotation/contract render
    seams. Only the `nl2br` extension is on, so single newlines become `<br>`,
    matching how operators expect terms copy to wrap.

    ⚠️ "Safe" here means *trusted-author* safe, not sanitised: `markdown`
    passes raw HTML in the source straight through to the output. Feed this
    only operator-authored copy, never guest input or a free-text field an
    untrusted party can reach.
    """
    if not text:
        return ""
    return _markdown.markdown(text, extensions=["nl2br"], output_format="html")
