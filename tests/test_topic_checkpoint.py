"""Pure weekly-checkpoint rules over the topic path."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from diagnostic.topic_checkpoint import (
    CHECKPOINT_UNIT_SIZE,
    PassedCheckpoint,
    build_checkpoints,
    build_units,
    checkpoint_unit_question_ids,
    gate_path,
    is_passing,
    pass_threshold,
)
from diagnostic.topic_path import TopicProgress, build_topic_path


@dataclass(frozen=True)
class Q:
    id: str
    topic: str


def make_path(topic_count: int, done_topics: set[int]):
    """A path of one-question topics, with the given topic indices mastered."""
    questions = [Q(f"q{i}", f"T{i}") for i in range(topic_count)]
    progress = {
        f"T{i}": TopicProgress(correct_ids=frozenset({f"q{i}"}))
        for i in done_topics
    }
    return questions, build_topic_path(questions, progress)


def test_units_group_consecutive_topics():
    _, path = make_path(12, set())
    units = build_units(path, size=5)
    assert [len(unit) for unit in units] == [5, 5, 2]
    assert units[1][0].index == 5


def test_first_unit_checkpoint_is_locked_until_all_topics_done():
    _, path = make_path(5, {0, 1, 2, 3})  # one topic still open
    checkpoints = build_checkpoints(path, {}, size=5)
    assert checkpoints[0].status == "locked"


def test_checkpoint_is_available_when_the_unit_is_complete():
    _, path = make_path(5, {0, 1, 2, 3, 4})
    checkpoints = build_checkpoints(path, {}, size=5)
    assert len(checkpoints) == 1
    assert checkpoints[0].status == "available"
    assert checkpoints[0].topics == tuple(f"T{i}" for i in range(5))


def test_gate_locks_the_next_unit_until_the_checkpoint_passes():
    # Every topic mastered across two units, but no checkpoint passed yet.
    _, path = make_path(10, set(range(10)))
    gated = gate_path(path, {}, size=5)
    # Unit 0 topics stay done; unit 1 topics are locked behind the checkpoint.
    assert [node.status for node in gated[:5]] == ["done"] * 5
    assert [node.status for node in gated[5:]] == ["locked"] * 5


def test_passing_unit_zero_opens_unit_one():
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    _, path = make_path(10, set(range(10)))
    passed = {0: PassedCheckpoint(unit_index=0, passed_at=now - timedelta(days=8))}
    gated = gate_path(path, passed, size=5)
    # Unit 1 is now open; its topics are already mastered, so they read done.
    assert all(node.status == "done" for node in gated)
    checkpoints = build_checkpoints(path, passed, size=5, now=now)
    assert checkpoints[0].status == "passed"
    # Eight days > the seven-day cooldown, so unit 1 is available.
    assert checkpoints[1].status == "available"


def test_cooldown_throttles_the_next_checkpoint_within_a_week():
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    _, path = make_path(10, set(range(10)))
    passed = {0: PassedCheckpoint(unit_index=0, passed_at=now - timedelta(days=2))}
    checkpoints = build_checkpoints(path, passed, size=5, now=now)
    assert checkpoints[1].status == "cooldown"
    assert checkpoints[1].available_at is not None


def test_checkpoint_question_ids_take_one_question_per_topic():
    questions = [Q("q0", "T0"), Q("q0b", "T0"), Q("q1", "T1")]
    path = build_topic_path(
        questions,
        {"T0": TopicProgress(frozenset({"q0", "q0b"})), "T1": TopicProgress(frozenset({"q1"}))},
    )
    ids = checkpoint_unit_question_ids(questions, path, 0, size=5)
    assert ids == ["q0", "q1"]  # first question of each topic, no duplicate topic


def test_pass_threshold_uses_the_ratio_with_a_floor_of_one():
    assert pass_threshold(5) == 3  # ceil(5 * 0.6)
    assert pass_threshold(1) == 1
    assert pass_threshold(0) == 0
    assert is_passing(3, 5) is True
    assert is_passing(2, 5) is False


def test_default_unit_size_is_five():
    assert CHECKPOINT_UNIT_SIZE == 5
