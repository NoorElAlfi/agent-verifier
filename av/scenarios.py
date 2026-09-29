"""SHARED: the scenario format.

    scenarios/<id>/task.yaml         a TaskDefinition (what the harness says the task is)
    scenarios/<id>/proposals.jsonl   replay fixtures: line 1 is a header {"origin": "recorded" |
                                     "synthetic", ...}; every further line is one Proposal

Replay feeds each Proposal through the same gateway code path a live agent uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from av.config import REPO_ROOT
from av.contracts import Decision, TaskDefinition

SCENARIOS_DIR = REPO_ROOT / "scenarios"

Origin = Literal["recorded", "synthetic"]


class ProposalsHeader(BaseModel):
    """First line of proposals.jsonl. `origin` is shown in every report and post (rule 11)."""

    model_config = ConfigDict(extra="allow")

    origin: Origin
    note: str = ""


class Proposal(BaseModel):
    """One tool call as the agent would send it. `agent_claims` is whatever the agent asserts
    about itself (recorded, never trusted). `expect` is the decision the fixture's author
    expects, for replay assertions only; it never feeds the pipeline."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    params: dict[str, Any] = {}
    agent_claims: Any = None
    expect: Decision | None = None
    note: str = ""


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    dir: Path
    task: TaskDefinition
    origin: Origin
    header: ProposalsHeader
    proposals: tuple[Proposal, ...]

    @property
    def workspace(self) -> Path:
        return REPO_ROOT / self.task.workspace


def load_task(path: Path) -> TaskDefinition:
    return TaskDefinition.model_validate(yaml.safe_load(Path(path).read_text()))


def load_proposals(path: Path) -> tuple[ProposalsHeader, list[Proposal]]:
    lines = [ln for ln in Path(path).read_text().splitlines() if ln.strip()]
    if not lines:
        raise ValueError(f"{path}: empty; the first line must be the origin header")
    header = ProposalsHeader.model_validate(json.loads(lines[0]))
    return header, [Proposal.model_validate(json.loads(ln)) for ln in lines[1:]]


def load_scenario(scenario_id: str, root: Path = SCENARIOS_DIR) -> Scenario:
    d = Path(root) / scenario_id
    task = load_task(d / "task.yaml")
    header, proposals = load_proposals(d / "proposals.jsonl")
    return Scenario(
        id=scenario_id, dir=d, task=task, origin=header.origin, header=header, proposals=tuple(proposals)
    )


def list_scenarios(root: Path = SCENARIOS_DIR, include_examples: bool = False) -> list[str]:
    """Scenario ids (folders with a task.yaml); `_`-prefixed ones only if include_examples."""
    ids = sorted(p.parent.name for p in Path(root).glob("*/task.yaml"))
    return [i for i in ids if include_examples or not i.startswith("_")]
