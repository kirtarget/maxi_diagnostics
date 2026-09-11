"""Pure tests for the topic-path model."""

from dataclasses import dataclass

from diagnostic.topic_path import (
    TopicProgress,
    build_topic_path,
    current_topic,
    estimate_minutes,
    select_today_question_ids,
    topic_order,
)


@dataclass(frozen=True)
class Q:
    id: str
    topic: str


# Three topics in codifier order: A (2 questions), B (3), C (1).
QUESTIONS = (
    Q("a1", "A"), Q("a2", "A"),
    Q("b1", "B"), Q("b2", "B"), Q("b3", "B"),
    Q("c1", "C"),
)


def test_topic_order_is_unique_and_first_seen():
    assert topic_order(QUESTIONS) == ("A", "B", "C")
    # A repeated topic later in the list keeps its first position.
    mixed = (Q("x", "A"), Q("y", "B"), Q("z", "A"))
    assert topic_order(mixed) == ("A", "B")


def test_empty_progress_makes_first_topic_current_and_rest_locked():
    path = build_topic_path(QUESTIONS, {})
    assert [(n.topic, n.status, n.total, n.mastered) for n in path] == [
        ("A", "current", 2, 0),
        ("B", "locked", 3, 0),
        ("C", "locked", 1, 0),
    ]
    assert current_topic(path).topic == "A"


def test_topic_is_done_when_every_question_is_correct_and_next_unlocks():
    progress = {"A": TopicProgress(correct_ids=frozenset({"a1", "a2"}))}
    path = build_topic_path(QUESTIONS, progress)
    assert path[0].status == "done"
    assert path[0].mastered == 2
    assert path[1].status == "current"  # B unlocks once A is done
    assert path[2].status == "locked"


def test_partial_topic_stays_current_with_progress_count():
    progress = {"A": TopicProgress(correct_ids=frozenset({"a1"}))}
    path = build_topic_path(QUESTIONS, progress)
    assert path[0].status == "current"
    assert path[0].mastered == 1


def test_done_at_closes_a_topic_even_without_full_correct_set():
    progress = {"A": TopicProgress(correct_ids=frozenset({"a1"}), done_at="2026-09-10")}
    path = build_topic_path(QUESTIONS, progress)
    assert path[0].status == "done"
    assert path[0].done_at == "2026-09-10"
    assert path[1].status == "current"


def test_all_done_leaves_no_current_topic():
    progress = {
        "A": TopicProgress(correct_ids=frozenset({"a1", "a2"})),
        "B": TopicProgress(correct_ids=frozenset({"b1", "b2", "b3"})),
        "C": TopicProgress(correct_ids=frozenset({"c1"})),
    }
    path = build_topic_path(QUESTIONS, progress)
    assert all(n.status == "done" for n in path)
    assert current_topic(path) is None


def test_stale_mastery_ids_do_not_inflate_the_count():
    progress = {"A": TopicProgress(correct_ids=frozenset({"a1", "gone"}))}
    path = build_topic_path(QUESTIONS, progress)
    assert path[0].mastered == 1
    assert path[0].status == "current"


def test_today_selection_serves_unmastered_current_topic_first():
    progress = {"B": TopicProgress(correct_ids=frozenset({"b2"}))}
    # A is current (unstarted); its two questions come out in order.
    path = build_topic_path(QUESTIONS, progress)
    assert select_today_question_ids(QUESTIONS, path, progress, size=5) == ["a1", "a2"]


def test_today_selection_skips_mastered_then_backfills():
    progress = {"A": TopicProgress(correct_ids=frozenset({"a1", "a2"}))}
    # B is current with b1,b3 open and b2 mastered.
    progress["B"] = TopicProgress(correct_ids=frozenset({"b2"}))
    path = build_topic_path(QUESTIONS, progress)
    picked = select_today_question_ids(QUESTIONS, path, progress, size=2)
    assert picked == ["b1", "b3"]  # unmastered first, capped at size
    # A larger session backfills with the mastered one last.
    assert select_today_question_ids(QUESTIONS, path, progress, size=5) == ["b1", "b3", "b2"]


def test_today_selection_empty_when_path_complete():
    progress = {
        "A": TopicProgress(correct_ids=frozenset({"a1", "a2"})),
        "B": TopicProgress(correct_ids=frozenset({"b1", "b2", "b3"})),
        "C": TopicProgress(correct_ids=frozenset({"c1"})),
    }
    path = build_topic_path(QUESTIONS, progress)
    assert select_today_question_ids(QUESTIONS, path, progress, size=5) == []


def test_estimate_minutes_is_positive_for_any_real_session():
    assert estimate_minutes(0) == 0
    assert estimate_minutes(1) == 1
    assert estimate_minutes(5) == 4
