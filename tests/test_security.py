from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    encoded = hash_password("a-long-and-safe-password")
    assert encoded != "a-long-and-safe-password"
    assert verify_password("a-long-and-safe-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token")
