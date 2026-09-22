"""The shipped example must produce exactly the reports committed next to it.

A change in either file is a change in what users see, so it has to be deliberate: rerun
the two commands in examples/hinglish-shop/README.md and commit the new output.
"""

import json
from pathlib import Path

from vakforge.inspect.report import inspect_dir
from vakforge.locales import get_pack
from vakforge.recommend import recommend

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "hinglish-shop"


def _expected(name: str) -> dict:
    return json.loads((EXAMPLE / "expected" / name).read_text(encoding="utf-8"))


def test_inspect_matches_committed_report():
    report = inspect_dir(EXAMPLE / "data", get_pack("hi-Latn-IN"))
    expected = _expected("inspect.json")
    # `root` is whatever path the user typed; everything else must match byte for byte.
    report.pop("root")
    expected.pop("root")
    assert report == expected


def test_recommend_matches_committed_decision():
    summary = _expected("inspect.json")["summary"]
    rec = recommend(summary, get_pack("hi-Latn-IN"))
    assert {"locale": "hi-Latn-IN", **rec.to_dict()} == _expected("recommend.json")
