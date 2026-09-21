"""Versioned experiment configuration.

Experiment grids live in YAML rather than in code, so a run is identified by its
config hash and re-run from the file alone. Unknown keys are rejected, because a
typo in a config is otherwise a silent change of experiment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from system_one_control.controllers import CONTROLLERS
from system_one_control.dataset import SPLITS
from system_one_control.observation import DESCRIPTION_MODES


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetConfig(Strict):
    seeds: int = 200
    states_per_episode: int = 3
    max_steps: int = 100
    split: str = "test"
    states_per_environment: int | None = 150

    @field_validator("split")
    @classmethod
    def _known_split(cls, value: str) -> str:
        if value not in SPLITS:
            raise ValueError(f"split must be one of {sorted(SPLITS)}, got {value!r}")
        return value


class CandidatesConfig(Strict):
    max_options: int = 8
    randomize_display_ids: bool = True


class OfflineConfig(Strict):
    horizons: tuple[int, ...] = (1, 2)
    description_mode: str = "action_only"

    @field_validator("description_mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in DESCRIPTION_MODES:
            raise ValueError(f"unknown description mode: {value!r}")
        return value


class OnlineConfig(Strict):
    starts_per_environment: int = 20
    controllers: tuple[str, ...] = ("reactive",)

    @field_validator("controllers")
    @classmethod
    def _known_controllers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = [name for name in value if name not in CONTROLLERS]
        if unknown:
            raise ValueError(f"unknown controllers {unknown}, known: {sorted(CONTROLLERS)}")
        return value


class StatisticsConfig(Strict):
    bootstrap_samples: int = 2000
    cluster: str = "layout_id"


class ExperimentConfig(Strict):
    """The whole of one experiment, as loaded from YAML."""

    experiment_id: str
    seed: int = 42
    environments: tuple[str, ...] = ("MiniGrid-DoorKey-6x6-v0",)
    agents: tuple[str, ...] = ("random", "greedy", "rollout_heuristic", "oracle")
    max_calls: int | None = None
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    candidates: CandidatesConfig = Field(default_factory=CandidatesConfig)
    offline: OfflineConfig = Field(default_factory=OfflineConfig)
    online: OnlineConfig = Field(default_factory=OnlineConfig)
    statistics: StatisticsConfig = Field(default_factory=StatisticsConfig)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load_config(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment configuration."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ExperimentConfig(**raw)
