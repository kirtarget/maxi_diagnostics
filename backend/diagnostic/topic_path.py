"""Server-owned «путь по темам»: the ordered topic path and its per-user status.

The functions here are pure. They turn the diagnostic's questions, which already
carry a ``topic`` and sit in codifier order, plus the student's per-topic mastery,
into an ordered path with a single ``current`` topic. Persistence lives in
``diagnostic.db.topic_progress``; the catalog lookups live in the API layer.

Path rules (v1):
- The path is the unique topics in question order. A topic appears once, at the
  position of its first question.
- A topic is ``done`` once every question of that topic has been answered
  correctly at least once (or its completion date is recorded).
- ``current`` is the first topic that is not done. Everything before it is done,
  everything after it is ``locked``. So topic N unlocks when topic N-1 is done.
- When every topic is done there is no current topic and the path is complete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Literal


TODAY_SESSION_SIZE = 5
"""Default number of questions in one daily session."""

#: Rough minutes a student spends per question, used only for the home estimate.
_MINUTES_PER_QUESTION = 0.8

TopicStatus = Literal["done", "current", "locked"]


@dataclass(frozen=True)
class TopicProgress:
    """One topic's mastery for a single (user, diagnostic, content version)."""

    correct_ids: frozenset[str] = field(default_factory=frozenset)
    done_at: str | None = None


@dataclass(frozen=True)
class TopicNode:
    topic: str
    index: int
    total: int
    #: Questions of this topic answered correctly at least once. Named to avoid
    #: any collision with the server-only ``correct`` answer key.
    mastered: int
    status: TopicStatus
    done_at: str | None


def topic_order(questions: Sequence[Any]) -> tuple[str, ...]:
    """Unique topics in first-seen (codifier) order.

    A blank topic cannot reach here because the catalog forbids it, but if one
    ever did it would still form its own node at the position it first appears.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for question in questions:
        topic = getattr(question, "topic", "")
        if topic not in seen:
            seen.add(topic)
            ordered.append(topic)
    return tuple(ordered)


def _topic_question_ids(questions: Sequence[Any], topic: str) -> list[str]:
    return [question.id for question in questions if getattr(question, "topic", "") == topic]


def build_topic_path(
    questions: Sequence[Any],
    progress: Mapping[str, TopicProgress],
) -> tuple[TopicNode, ...]:
    """Order the topics and assign each a status from the student's mastery.

    ``progress`` maps a topic to its mastery; a topic missing from the map has no
    correct answers yet. Correctness is judged against the topic's own question
    set, so mastery ids that no longer exist are simply ignored.
    """
    nodes: list[TopicNode] = []
    current_assigned = False
    for index, topic in enumerate(topic_order(questions)):
        topic_ids = _topic_question_ids(questions, topic)
        total = len(topic_ids)
        state = progress.get(topic, TopicProgress())
        mastered = len(state.correct_ids & set(topic_ids))
        is_done = bool(state.done_at) or (total > 0 and mastered >= total)
        if is_done:
            status: TopicStatus = "done"
        elif not current_assigned:
            status = "current"
            current_assigned = True
        else:
            status = "locked"
        nodes.append(
            TopicNode(
                topic=topic,
                index=index,
                total=total,
                mastered=min(mastered, total),
                status=status,
                done_at=state.done_at,
            )
        )
    return tuple(nodes)


def current_topic(path: Sequence[TopicNode]) -> TopicNode | None:
    for node in path:
        if node.status == "current":
            return node
    return None


def select_today_question_ids(
    questions: Sequence[Any],
    path: Sequence[TopicNode],
    progress: Mapping[str, TopicProgress],
    *,
    size: int = TODAY_SESSION_SIZE,
) -> list[str]:
    """Pick up to ``size`` questions from the current topic, unmastered first.

    Already-mastered questions of the current topic follow the unmastered ones so
    a short topic still fills a session, but a topic with more open questions than
    ``size`` never wastes a slot on one the student already closed. Returns an
    empty list when the path is complete.
    """
    node = current_topic(path)
    if node is None or size <= 0:
        return []
    mastered = progress.get(node.topic, TopicProgress()).correct_ids
    topic_ids = _topic_question_ids(questions, node.topic)
    unmastered = [qid for qid in topic_ids if qid not in mastered]
    mastered_ids = [qid for qid in topic_ids if qid in mastered]
    return (unmastered + mastered_ids)[:size]


def estimate_minutes(size: int) -> int:
    if size <= 0:
        return 0
    return max(1, ceil(size * _MINUTES_PER_QUESTION))


def serialize_path(path: Sequence[TopicNode]) -> list[dict[str, Any]]:
    return [
        {
            "topic": node.topic,
            "index": node.index,
            "total": node.total,
            "mastered": node.mastered,
            "status": node.status,
            "done_at": node.done_at,
        }
        for node in path
    ]
