"""`vakforge recommend`: docs/DECISION_GUIDE.md as code.

Reads an `inspect` summary plus a few constraints and says what actually needs changing,
which recipe fits the locale and hardware, whether to fine-tune at all, and what consent
the locale pack requires. Deliberately a small rule table, not a model.
"""

from vakforge.recommend.rules import Constraints, Recommendation, recommend

__all__ = ["Constraints", "Recommendation", "recommend"]
