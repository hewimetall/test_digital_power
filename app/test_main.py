from datetime import datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.autch import Auth
from app.redis import RedisStatus
from app import redis as redis_module


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value
        return True


class FakeResponse:
    def __init__(self, content=b"avatar-bytes"):
        self.content = content
        self.raise_called = False

    def raise_for_status(self):
        self.raise_called = True


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def fake_redis():
    redis_client = FakeRedis()
    main.app._status_redis = RedisStatus.CONNECTED
    main.app._redis = redis_client
    yield redis_client
    for attr in ("_status_redis", "_redis"):
        if hasattr(main.app, attr):
            delattr(main.app, attr)


def login(client, password="test_good"):
    response = client.post("/login", json={"username": "johndoe", "password": password})
    assert response.status_code == 200
    return response.json()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_read_main(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == "Hi, check is docks."


def test_login_returns_tokens_and_refreshes(client):
    tokens = login(client)

    assert main.auth_handler.decode_token(tokens["access_token"]) == "johndoe"

    response = client.get("/refresh_token", headers=auth_header(tokens["refresh_token"]))

    assert response.status_code == 200
    assert main.auth_handler.decode_token(response.json()["access_token"]) == "johndoe"


@pytest.mark.parametrize(
    ("username", "password"),
    [("johndoe_two", "test_good"), ("johndoe", "wrong")],
)
def test_login_rejects_invalid_credentials(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid user data"


def test_login_rejects_invalid_payload(client):
    response = client.post("/login", data={"username": "johndoe", "password": "test_good"})

    assert response.status_code == 422


def test_refresh_rejects_access_token_scope(client):
    tokens = login(client)

    response = client.get("/refresh_token", headers=auth_header(tokens["access_token"]))

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid scope for token"


def test_get_avatar_fetches_and_caches_miss(client, fake_redis, monkeypatch):
    tokens = login(client)
    fetched = FakeResponse()
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return fetched

    monkeypatch.setattr(main.requests, "get", fake_get)

    response = client.get("/get_avatar/test/", headers=auth_header(tokens["access_token"]))

    assert response.status_code == 200
    assert response.content == b"avatar-bytes"
    assert fetched.raise_called
    assert calls == [(f"{main.DNMONSTER_URL}/monster/test", 5)]
    assert fake_redis.store["test"] == b"avatar-bytes"


def test_get_avatar_uses_cached_image(client, fake_redis, monkeypatch):
    tokens = login(client)
    fake_redis.set("cached", b"cached-bytes")

    def fail_get(url, timeout):  # pragma: no cover
        raise AssertionError("cached avatar should not call DNMonster")

    monkeypatch.setattr(main.requests, "get", fail_get)

    response = client.get("/get_avatar/cached/", headers=auth_header(tokens["access_token"]))

    assert response.status_code == 200
    assert response.content == b"cached-bytes"


def test_get_avatar_requires_valid_access_token(client):
    missing = client.get("/get_avatar/test/")
    invalid = client.get("/get_avatar/test/", headers=auth_header("not-a-token"))

    assert missing.status_code == 403
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid token"


def test_get_user_returns_none_for_unknown_user():
    assert main.get_user("nobody") is None


def test_app_redis_connects_once(monkeypatch):
    fake = FakeRedis()
    calls = []
    delattr(main.app, "_status_redis")
    delattr(main.app, "_redis")

    def fake_connect(host):
        calls.append(host)
        return RedisStatus.CONNECTED, fake

    monkeypatch.setattr(main, "redis_connect", fake_connect)

    assert main.app.redis is fake
    assert main.app.redis is fake
    assert calls == [main.LOCAL_REDIS_URL]


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (RedisStatus.AUTH_ERROR, "Redis authentication failed"),
        (RedisStatus.CONN_ERROR, "Redis connection failed"),
        (RedisStatus.NONE, "Redis connection failed"),
    ],
)
def test_app_redis_reports_connection_errors(status, detail):
    main.app._status_redis = status
    main.app._redis = None

    with pytest.raises(HTTPException) as exc:
        _ = main.app.redis

    assert exc.value.status_code == 503
    assert exc.value.detail == detail


def test_auth_password_hash_round_trip():
    auth = Auth("secret")
    encoded = auth.encode_password("password")

    assert auth.verify_password("password", encoded)
    assert not auth.verify_password("wrong", encoded)


def test_decode_token_rejects_refresh_expired_and_invalid_tokens():
    auth = Auth("secret")
    refresh = auth.encode_refresh_token("johndoe")
    expired = jwt.encode(
        {
            "exp": datetime.utcnow() - timedelta(minutes=1),
            "iat": datetime.utcnow() - timedelta(minutes=2),
            "scope": "access_token",
            "sub": "johndoe",
        },
        "secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException, match="Scope for the token is invalid"):
        auth.decode_token(refresh)
    with pytest.raises(HTTPException, match="Token expired"):
        auth.decode_token(expired)
    with pytest.raises(HTTPException, match="Invalid token"):
        auth.decode_token("bad-token")


def test_refresh_token_rejects_access_expired_and_invalid_tokens():
    auth = Auth("secret")
    access = auth.encode_token("johndoe")
    expired = jwt.encode(
        {
            "exp": datetime.utcnow() - timedelta(minutes=1),
            "iat": datetime.utcnow() - timedelta(minutes=2),
            "scope": "refresh_token",
            "sub": "johndoe",
        },
        "secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException, match="Invalid scope for token"):
        auth.refresh_token(access)
    with pytest.raises(HTTPException, match="Refresh token expired"):
        auth.refresh_token(expired)
    with pytest.raises(HTTPException, match="Invalid refresh token"):
        auth.refresh_token("bad-token")


def test_redis_connect_delegates_to_connect(monkeypatch):
    calls = []

    def fake_connect(host):
        calls.append(host)
        return RedisStatus.CONN_ERROR, None

    monkeypatch.setattr(redis_module, "_connect", fake_connect)

    assert redis_module.redis_connect("localhost") == (RedisStatus.CONN_ERROR, None)
    assert calls == ["localhost"]
