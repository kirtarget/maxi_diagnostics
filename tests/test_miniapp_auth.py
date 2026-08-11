import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from diagnostic.auth import validate_init_data


def sign_init_data(bot_token: str, *, user: dict | None = None, auth_date: int | None = None) -> str:
    pairs = {"auth_date": str(auth_date or int(time.time()))}
    if user is not None:
        pairs["user"] = json.dumps(user, separators=(",", ":"))
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_validate_init_data_returns_signed_telegram_user():
    init_data = sign_init_data("token", user={"id": 42, "first_name": "Ada"})

    assert validate_init_data(init_data, "token")["user"] == {"id": 42, "first_name": "Ada"}


def test_validate_init_data_rejects_invalid_hash():
    init_data = sign_init_data("token", user={"id": 42}) + "tampered"

    with pytest.raises(ValueError, match="hash (?:mismatch|is invalid)"):
        validate_init_data(init_data, "token")


def test_validate_init_data_rejects_missing_user():
    init_data = sign_init_data("token")

    with pytest.raises(ValueError, match="missing user"):
        validate_init_data(init_data, "token")


def test_validate_init_data_rejects_stale_auth_date():
    init_data = sign_init_data("token", user={"id": 42}, auth_date=int(time.time()) - 7201)

    with pytest.raises(ValueError, match="stale"):
        validate_init_data(init_data, "token")


def test_validate_init_data_rejects_far_future_auth_date():
    init_data = sign_init_data("token", user={"id": 42}, auth_date=int(time.time()) + 31)

    with pytest.raises(ValueError, match="future"):
        validate_init_data(init_data, "token")


@pytest.mark.parametrize("user_id", [True, 0, -1, 2**63])
def test_validate_init_data_rejects_invalid_telegram_user_id(user_id):
    init_data = sign_init_data("token", user={"id": user_id})

    with pytest.raises(ValueError, match="user is invalid"):
        validate_init_data(init_data, "token")


def test_validate_init_data_rejects_non_ascii_hash_as_bounded_value_error():
    init_data = sign_init_data("token", user={"id": 42})
    init_data = init_data.rsplit("hash=", 1)[0] + "hash=%C3%A9"

    with pytest.raises(ValueError, match="hash is invalid"):
        validate_init_data(init_data, "token")
