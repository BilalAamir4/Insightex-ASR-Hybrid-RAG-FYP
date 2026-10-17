"""M7 extraction arms (ADR-0048 section 8, Amendment 2): what an evaluation run varies.

An arm fixes the model, the input language (the original transcript or a per-window English translation), the batch
size k and whether the previous grid window is given as read-only context. Arms live in `extract.arms_file`
(config/m7_arms.yaml). A field left null there is filled from an earlier comparison's winner; such an arm loads but
refuses to run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

COMPARISONS = ("C1", "C2", "C3", "C4")


class ArmConfigError(Exception):
    pass


class Arm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    comparison: Literal["C1", "C2", "C3", "C4"]
    model: str | None
    input: Literal["original", "english"] | None
    batch_k: int | None
    context: Literal["none", "previous"]

    @field_validator("name")
    @classmethod
    def _safe_name(cls, v: str) -> str:
        if not v or not all(ch.isalnum() or ch in "-_." for ch in v) or v.startswith("."):
            raise ValueError("arm names use letters, digits, '-', '_' and '.' only (they name a directory)")
        return v

    @field_validator("batch_k")
    @classmethod
    def _positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("batch_k must be at least 1")
        return v

    def missing(self) -> list[str]:
        return [k for k in ("model", "input", "batch_k") if getattr(self, k) is None]

    def require_complete(self) -> None:
        if self.missing():
            raise ArmConfigError(f"arm {self.name!r} has unset fields {self.missing()}: set them from the earlier "
                                 "comparison's committed decision before running it")


def load_arms(path: Path) -> dict[str, Arm]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ArmConfigError(f"cannot read arms file {path}: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("arms"), list):
        raise ArmConfigError(f"{path}: expected a mapping with an `arms` list")
    out: dict[str, Arm] = {}
    for i, raw in enumerate(data["arms"]):
        try:
            arm = Arm.model_validate(raw)
        except ValueError as e:
            raise ArmConfigError(f"{path}: arms[{i}]: {e}") from e
        if arm.name in out:
            raise ArmConfigError(f"{path}: arm name {arm.name!r} appears twice")
        out[arm.name] = arm
    return out
