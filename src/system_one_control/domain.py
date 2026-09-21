"""Immutable value types shared by every stage of the benchmark.

Coordinates are ``(x, y)`` with the origin at the upper left, x rightward and y
downward. Directions use MiniGrid's encoding: 0 east, 1 south, 2 west, 3 north.
"""

from __future__ import annotations

from dataclasses import dataclass

# A MiniGrid cell encoded as (object index, color index, state index).
EncodedCell = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A complete, restorable description of a static MiniGrid world.

    ``cells`` is row-major: ``cells[y][x]``. The agent is not stored in the grid,
    and a carried object is removed from the grid and held in ``carrying``.
    """

    env_id: str
    width: int
    height: int
    cells: tuple[tuple[EncodedCell, ...], ...]
    agent_pos: tuple[int, int]
    agent_dir: int
    carrying: EncodedCell | None
    mission: str
    step_count: int
    max_steps: int

    def cell(self, x: int, y: int) -> EncodedCell:
        return self.cells[y][x]


@dataclass(frozen=True, slots=True)
class Transition:
    """The result of applying one primitive action to a Snapshot."""

    snapshot: Snapshot
    reward: float
    terminated: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class Candidate:
    """One offered action sequence, together with its simulated outcome.

    The outcome is computed by ordinary code, not by the model. Whether the
    model is shown it is a property of the serializer, which is what makes the
    action-only and endpoint conditions comparable on identical candidates.
    """

    actions: tuple[int, ...]
    semantic_id: str
    display_id: str
    executed: int
    outcome: Snapshot
    terminated: bool
    truncated: bool
    success: bool


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """The candidates actually presented for one decision."""

    candidates: tuple[Candidate, ...]
    horizon: int
    pool_size: int
    subsampled: bool
    rng_seed: int

    def __len__(self) -> int:
        return len(self.candidates)

    def by_display_id(self, display_id: str) -> Candidate:
        for candidate in self.candidates:
            if candidate.display_id == display_id:
                return candidate
        raise KeyError(display_id)


@dataclass(frozen=True, slots=True)
class CandidateLabels:
    """Oracle annotations for one offered candidate set.

    Joined onto a record *after* the model request has been built. ``None`` cost
    means infinite: the candidate fails, or cannot finish inside the remaining
    budget. An all-infinite menu is recorded as a failure, never as a tie in
    which every option counts as correct.
    """

    distance: int | None
    best_offered_cost: int | None
    optimal_offered_ids: frozenset[str]
    candidate_gap: int | None
    global_optimal_present: bool
    global_optimal_first_actions: frozenset[int]
    all_candidates_fail: bool
    costs: dict[str, int | None]
