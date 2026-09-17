import re

from vakforge.locales.base import LocalePack, PIIPattern


class _Parent(LocalePack):
    id = "t-parent"
    languages = ["tp"]
    call_recording_consent = "all_party"
    pii_patterns = [
        PIIPattern("digits4", re.compile(r"\b\d{4}\b")),
        PIIPattern("even", re.compile(r"\b\d+\b"), validate=lambda s: int(s) % 2 == 0),
    ]


class _Child(LocalePack):
    id = "t-child"
    languages = ["tc"]
    parent = "t-parent"
    pii_patterns = [PIIPattern("digits4", re.compile(r"\b\d{4}\b(?!-)"))]


def _registered():
    from vakforge.locales import base

    base._REGISTRY.setdefault("t-parent", _Parent())
    base._REGISTRY.setdefault("t-child", _Child())
    return base._REGISTRY["t-child"]


def test_child_inherits_languages_and_overrides_patterns_by_name():
    child = _registered()
    assert child.all_languages() == {"tc", "tp"}
    names = [p.name for p in child.all_pii_patterns()]
    assert names == ["digits4", "even"]
    assert child.all_pii_patterns()[0] is child.pii_patterns[0]


def test_resolved_walks_parent_chain():
    child = _registered()
    assert child.resolved("call_recording_consent") == "all_party"


def test_validator_filters_matches():
    child = _registered()
    spans = child.find_pii("odd 7 even 12")
    assert [(s.type, s.text) for s in spans] == [("even", "12")]


def test_overlaps_keep_longest_span():
    child = _registered()
    spans = child.find_pii("code 1234 end")
    assert [(s.type, s.text, s.start, s.end) for s in spans] == [("digits4", "1234", 5, 9)]
