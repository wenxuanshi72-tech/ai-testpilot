from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from plugin.backend.app.constraints import extract_username_minimum_constraint

SEEDED_BUG_ID = "BUG-AUTH-001"
SEED_RESOLUTION_VERSION = "seeded-constraint-resolution@1.0.0"


class SeededRequirementResolutionError(Exception):
    pass


@dataclass(frozen=True)
class SeededRequirementResolution:
    seeded_bug_id: str
    resolved_requirement_id: str
    requirement_version: int
    requirement_snapshot_hash: str
    source_block_id: str
    source_excerpt: str
    field: str
    operator: str
    value: int
    unit: str
    resolution_algorithm_version: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_seeded_username_requirement(
    snapshots: dict[str, dict[str, Any]],
) -> SeededRequirementResolution:
    matches: list[tuple[dict[str, Any], Any]] = []
    for snapshot in snapshots.values():
        requirement = dict(snapshot["requirement"])
        requirement.setdefault("source_excerpt", snapshot["source_excerpt"])
        constraint = extract_username_minimum_constraint(requirement)
        if (
            constraint is not None
            and constraint.field == "username"
            and constraint.operator == "greater_than_or_equal"
            and constraint.value == 6
            and constraint.unit == "characters"
        ):
            matches.append((snapshot, constraint))
    if not matches:
        raise SeededRequirementResolutionError("SEEDED_REQUIREMENT_NOT_FOUND")
    if len(matches) != 1:
        raise SeededRequirementResolutionError("SEEDED_REQUIREMENT_NOT_UNIQUE")
    snapshot, constraint = matches[0]
    return SeededRequirementResolution(
        seeded_bug_id=SEEDED_BUG_ID,
        resolved_requirement_id=str(snapshot["requirement_id"]),
        requirement_version=int(snapshot["requirement_version"]),
        requirement_snapshot_hash=str(snapshot["snapshot_hash"]),
        source_block_id=str(constraint.source_block_id),
        source_excerpt=str(constraint.source_excerpt),
        field=constraint.field,
        operator=constraint.operator,
        value=constraint.value,
        unit=constraint.unit,
        resolution_algorithm_version=SEED_RESOLUTION_VERSION,
    )
