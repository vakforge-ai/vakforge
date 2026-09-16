import pytest

from vakforge.locales import get_pack, list_packs


def test_launch_english_packs_registered():
    assert {"en", "en-US", "en-GB", "en-IN"} <= set(list_packs())


def test_children_inherit_parent_languages():
    assert get_pack("en-IN").all_languages() == {"en", "en-IN"}


def test_unknown_pack_lists_known():
    with pytest.raises(KeyError, match="known:"):
        get_pack("xx")


def test_default_normalizer():
    assert get_pack("en").normalize_text("  Hello, World!  ") == "hello world"
