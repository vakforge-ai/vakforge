"""English packs: `en` parent plus en-US, en-GB, en-IN.

Phase 0 skeletons. Formats, PII patterns, consent notes and generators come in Phase 1;
split each into its own package when it grows past a screen.
"""

from __future__ import annotations

from vakforge.locales.base import LocalePack, register


@register
class En(LocalePack):
    id = "en"
    languages = ["en"]


@register
class EnUS(LocalePack):
    id = "en-US"
    languages = ["en-US"]
    parent = "en"


@register
class EnGB(LocalePack):
    id = "en-GB"
    languages = ["en-GB"]
    parent = "en"


@register
class EnIN(LocalePack):
    id = "en-IN"
    languages = ["en-IN"]
    parent = "en"
