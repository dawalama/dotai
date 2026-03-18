"""Tests for dotai.utils."""

from dotai.utils import generate_id


def test_generate_id_basic():
    assert generate_id("Code Review") == "code-review"


def test_generate_id_special_chars():
    assert generate_id("no-useEffect") == "no-useeffect"


def test_generate_id_underscores():
    assert generate_id("my_cool_skill") == "my-cool-skill"


def test_generate_id_leading_trailing():
    assert generate_id("  Hello World  ") == "hello-world"


def test_generate_id_multiple_spaces():
    assert generate_id("a   b   c") == "a-b-c"
