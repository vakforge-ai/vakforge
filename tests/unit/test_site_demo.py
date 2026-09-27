"""The landing page's demo calls itself vakforge's actual output on the shipped example.

Its verdict badge said "baseline first" while the example's decision was "blocked", and
nothing compared the two. This test reads the demo panel and checks every number in it
against the example's committed reports.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "examples" / "hinglish-shop" / "expected"


def test_the_landing_page_demo_matches_the_example_output():
    page = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    demo = page[page.index('id="demo"') : page.index('id="demo-score"') + 300]
    inspect = json.loads((EXPECTED / "inspect.json").read_text(encoding="utf-8"))
    rec = json.loads((EXPECTED / "recommend.json").read_text(encoding="utf-8"))
    s = inspect["summary"]

    assert re.search(r'id="demo-badge">([^<]+)<', demo).group(1) == rec["fine_tune"]
    assert f'<span class="coral">{rec["fine_tune"]}</span>' in demo
    assert f"{sum(s['counts'].values())} files" in demo
    assert f"{len(s['tool_candidates'])} tools" in demo
    assert f"Chat · {s['chat_messages']} messages" in demo
    faq = next(f for f in inspect["files"] if f["path"] == "faq.md")
    assert f"FAQ · {len(faq['facts']['languages'])} languages" in demo
    workflow = next(d for d in rec["goal_decisions"] if d["goal"] == "workflow")
    assert f'class="bar have" data-v="{workflow["have"]:g}"' in demo
    assert f'class="bar floor" data-v="{workflow["floor"]:g}"' in demo
