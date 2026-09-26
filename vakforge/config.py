"""Project config (`vakforge.yaml`), written by `init` and read by every stage."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONFIG_NAME = "vakforge.yaml"
# Keys an earlier release wrote and nothing reads any more. 0.1.0's `init` put `data_dir`
# into every project it created; rejecting it made 0.2.0 crash on all of them. They are
# dropped on load and never written again.
RETIRED_KEYS = ("data_dir",)


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    locales: list[str] = Field(min_length=1)

    @classmethod
    def load(cls, project_dir: Path) -> ProjectConfig:
        text = (project_dir / CONFIG_NAME).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            for key in RETIRED_KEYS:
                data.pop(key, None)
        return cls.model_validate(data)

    def save(self, project_dir: Path) -> Path:
        path = project_dir / CONFIG_NAME
        path.write_text(yaml.safe_dump(self.model_dump(), sort_keys=False), encoding="utf-8")
        return path
