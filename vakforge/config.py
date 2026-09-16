"""Project config (`vakforge.yaml`), written by `init` and read by every stage."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONFIG_NAME = "vakforge.yaml"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    locales: list[str] = Field(min_length=1)
    data_dir: str = "data"

    @classmethod
    def load(cls, project_dir: Path) -> ProjectConfig:
        text = (project_dir / CONFIG_NAME).read_text(encoding="utf-8")
        return cls.model_validate(yaml.safe_load(text) or {})

    def save(self, project_dir: Path) -> Path:
        path = project_dir / CONFIG_NAME
        path.write_text(yaml.safe_dump(self.model_dump(), sort_keys=False), encoding="utf-8")
        return path
