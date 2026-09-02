from __future__ import annotations

import logging

import pytest

from diagnostic.logging_config import LOG_FORMAT, configure_logging


@pytest.fixture(autouse=True)
def restore_root_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("DEBUG", "DEBUG"), ("warning", "WARNING"), ("", "INFO"), ("nonsense", "INFO")],
)
def test_root_level_follows_the_setting_with_a_safe_default(configured, expected):
    assert configure_logging(configured) == expected
    assert logging.getLogger().level == getattr(logging, expected)


def test_root_handler_uses_the_documented_format_and_replaces_old_handlers():
    logging.getLogger().addHandler(logging.NullHandler())

    configure_logging("INFO")
    handlers = logging.getLogger().handlers

    assert len(handlers) == 1
    assert handlers[0].formatter._fmt == LOG_FORMAT
    assert LOG_FORMAT == "%(asctime)s %(levelname)s %(name)s %(message)s"


def test_uvicorn_loggers_keep_their_own_configuration():
    access = logging.getLogger("uvicorn.access")
    access.handlers = [logging.NullHandler()]
    access.propagate = False
    access.setLevel(logging.WARNING)

    configure_logging("DEBUG")

    assert access.level == logging.WARNING
    assert access.propagate is False
    assert len(access.handlers) == 1


def test_environment_supplies_the_level_when_no_argument_is_given(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    assert configure_logging() == "ERROR"
