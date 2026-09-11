"""Server-owned weekly checkpoint over the «путь по темам».

A checkpoint closes a *unit* of the topic path and opens the next one. A unit is a
fixed group of consecutive path topics in codifier order. The functions here are
pure: they turn the mastery path (see ``diagnostic.topic_path``) plus the student's
passed-checkpoint records into gated topic statuses and per-unit checkpoint nodes.
Persistence lives in ``diagnostic.db.topic_checkpoints``; catalog lookups live in
the API layer.

Rules (v1):
- A unit spans ``CHECKPOINT_UNIT_SIZE`` consecutive topics. The last unit may be
  shorter. Unit ``u`` covers path indices ``[u*size, u*size+size)``.
- A unit's checkpoint is ``locked`` until every topic of the unit is ``done``.
- Once the unit's topics are done it is ``available`` to take, unless the student
  passed another checkpoint within ``CHECKPOINT_COOLDOWN_DAYS`` days; then it is
  ``cooldown`` until the week elapses. A passed unit is ``passed``.
- Topics of unit ``u`` stay ``locked`` on the path until unit ``u-1`` is passed, so
  a student cannot train past a checkpoint they have not cleared. Unit 0 is always
  open.
- Passing needs at least ``pass_threshold(question_count)`` correct answers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any, Literal

from diagnostic.topic_path import TopicNode


CHECKPOINT_UNIT_SIZE = 5
"""Consecutive topics that make up one unit / one weekly checkpoint."""

CHECKPOINT_COOLDOWN_DAYS = 7
"""Minimum days between two passed checkpoints (the weekly cadence)."""

CHECKPOINT_PASS_RATIO = 0.6
"""Share of a checkpoint's questions a student must get right to pass."""


CheckpointStatus = Literal["locked", "available", "cooldown", "passed"]


@dataclass(frozen=True)
class PassedCheckpoint:
    """One immutable passed-checkpoint record, reduced to what the view needs.

    ``mastered_count`` is how many срез questions were answered right, named to
    avoid any collision with the server-only ``correct`` answer key, exactly like
    ``TopicNode.mastered``.
    """

    unit_index: int
    passed_at: datetime | None = None
    mastered_count: int | None = None
    question_total: int | None = None


@dataclass(frozen=True)
class CheckpointNode:
    unit_index: int
    #: Inclusive path-index range of the unit's topics.
    topic_from: int
    topic_to: int
    topics: tuple[str, ...]
    status: CheckpointStatus
    #: ISO instant the checkpoint stops being throttled, or null when it is not.
    available_at: str | None
    passed_at: str | None
    mastered_count: int | None
    question_total: int | None


def unit_index_for(topic_index: int, *, size: int = CHECKPOINT_UNIT_SIZE) -> int:
    return topic_index // size


def build_units(
    path: Sequence[TopicNode], *, size: int = CHECKPOINT_UNIT_SIZE
) -> list[list[TopicNode]]:
    """Split the ordered path into consecutive units of at most ``size`` topics."""
    if size <= 0:
        return [list(path)] if path else []
    return [list(path[start : start + size]) for start in range(0, len(path), size)]


def _passed_indices(passed: Mapping[int, PassedCheckpoint]) -> frozenset[int]:
    return frozenset(passed.keys())


def gate_path(
    path: Sequence[TopicNode],
    passed: Mapping[int, PassedCheckpoint],
    *,
    size: int = CHECKPOINT_UNIT_SIZE,
) -> tuple[TopicNode, ...]:
    """Re-derive ``current``/``locked`` with checkpoint gates layered on mastery.

    A ``done`` topic stays done. A unit that follows an unpassed checkpoint is
    locked whole, so the single ``current`` topic never jumps a checkpoint.
    """
    passed_units = _passed_indices(passed)
    gated: list[TopicNode] = []
    current_assigned = False
    for unit_number, unit in enumerate(build_units(path, size=size)):
        unit_open = unit_number == 0 or (unit_number - 1) in passed_units
        for node in unit:
            if not unit_open:
                # A unit behind an unpassed checkpoint is locked whole, even where
                # a topic was already mastered, so the checkpoint gates progression.
                gated.append(replace(node, status="locked"))
            elif node.status == "done":
                gated.append(node)
            elif not current_assigned:
                gated.append(replace(node, status="current"))
                current_assigned = True
            else:
                gated.append(replace(node, status="locked"))
    return tuple(gated)


def _cooldown_boundary(
    passed: Mapping[int, PassedCheckpoint], *, cooldown_days: int
) -> datetime | None:
    stamps = [record.passed_at for record in passed.values() if record.passed_at is not None]
    if not stamps:
        return None
    latest = max(_as_utc(stamp) for stamp in stamps)
    return latest + timedelta(days=cooldown_days)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def build_checkpoints(
    path: Sequence[TopicNode],
    passed: Mapping[int, PassedCheckpoint],
    *,
    now: datetime | None = None,
    size: int = CHECKPOINT_UNIT_SIZE,
    cooldown_days: int = CHECKPOINT_COOLDOWN_DAYS,
) -> tuple[CheckpointNode, ...]:
    """One checkpoint node per unit, with its status and cooldown boundary."""
    instant = _as_utc(now or datetime.now(timezone.utc))
    boundary = _cooldown_boundary(passed, cooldown_days=cooldown_days)
    nodes: list[CheckpointNode] = []
    for unit_number, unit in enumerate(build_units(path, size=size)):
        if not unit:
            continue
        record = passed.get(unit_number)
        unit_done = all(node.status == "done" for node in unit)
        available_at: str | None = None
        if record is not None:
            status: CheckpointStatus = "passed"
        elif not unit_done:
            status = "locked"
        elif boundary is not None and instant < boundary:
            status = "cooldown"
            available_at = _iso(boundary)
        else:
            status = "available"
        nodes.append(
            CheckpointNode(
                unit_index=unit_number,
                topic_from=unit[0].index,
                topic_to=unit[-1].index,
                topics=tuple(node.topic for node in unit),
                status=status,
                available_at=available_at,
                passed_at=_iso(record.passed_at) if record is not None else None,
                mastered_count=record.mastered_count if record is not None else None,
                question_total=record.question_total if record is not None else None,
            )
        )
    return tuple(nodes)


def checkpoint_unit_topics(
    path: Sequence[TopicNode], unit_index: int, *, size: int = CHECKPOINT_UNIT_SIZE
) -> tuple[str, ...]:
    units = build_units(path, size=size)
    if unit_index < 0 or unit_index >= len(units):
        return ()
    return tuple(node.topic for node in units[unit_index])


def checkpoint_unit_question_ids(
    questions: Sequence[Any],
    path: Sequence[TopicNode],
    unit_index: int,
    *,
    size: int = CHECKPOINT_UNIT_SIZE,
) -> list[str]:
    """One question per unit topic, the topic's first question in codifier order.

    The result is deterministic, so the start and record endpoints agree on which
    questions belong to a unit's checkpoint without storing the set.
    """
    topics = checkpoint_unit_topics(path, unit_index, size=size)
    if not topics:
        return []
    first_for_topic: dict[str, str] = {}
    for question in questions:
        topic = getattr(question, "topic", "")
        if topic in topics and topic not in first_for_topic:
            first_for_topic[topic] = question.id
    return [first_for_topic[topic] for topic in topics if topic in first_for_topic]


def pass_threshold(question_count: int, *, ratio: float = CHECKPOINT_PASS_RATIO) -> int:
    if question_count <= 0:
        return 0
    return max(1, ceil(question_count * ratio))


def is_passing(correct_count: int, question_count: int, *, ratio: float = CHECKPOINT_PASS_RATIO) -> bool:
    return question_count > 0 and correct_count >= pass_threshold(question_count, ratio=ratio)


def serialize_checkpoints(nodes: Sequence[CheckpointNode]) -> list[dict[str, Any]]:
    return [
        {
            "unit_index": node.unit_index,
            "topic_from": node.topic_from,
            "topic_to": node.topic_to,
            "topics": list(node.topics),
            "status": node.status,
            "available_at": node.available_at,
            "passed_at": node.passed_at,
            "mastered_count": node.mastered_count,
            "question_total": node.question_total,
        }
        for node in nodes
    ]
