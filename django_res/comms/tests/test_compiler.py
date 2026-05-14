from __future__ import annotations

import pytest

from comms.compilers import compile_mjml
from comms.exceptions import MjmlCompileError

VALID_MJML = (
    "<mjml><mj-body><mj-section><mj-column>"
    "<mj-text>Hello</mj-text>"
    "</mj-column></mj-section></mj-body></mjml>"
)


def test_compiles_valid_mjml_to_html() -> None:
    html = compile_mjml(VALID_MJML)
    assert "<!doctype html>" in html.lower()
    assert "Hello" in html


def test_empty_input_returns_empty_string() -> None:
    assert compile_mjml("") == ""


def test_same_input_produces_same_output() -> None:
    assert compile_mjml(VALID_MJML) == compile_mjml(VALID_MJML)


def test_unparseable_input_raises() -> None:
    with pytest.raises(MjmlCompileError) as excinfo:
        compile_mjml("<not-mjml/>")
    assert excinfo.value.source == "<not-mjml/>"
    assert excinfo.value.errors


def test_unknown_mjml_tag_raises() -> None:
    bad = "<mjml><mj-body><mj-bogus-tag/></mj-body></mjml>"
    with pytest.raises(MjmlCompileError):
        compile_mjml(bad)
