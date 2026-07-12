import io
import os
from logging import getLogger
from typing import Optional

import redis
import requests
from fastapi import FastAPI, HTTPException, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.autch import Auth, AuthModel, AuthModelBD
from app.redis import RedisEvent, RedisStatus, redis_connect

log = getLogger(__name__)

fake_users_db = {
    "johndoe": {
        "username": "johndoe",
        "hashed_password": hash("test_good"),
        "email": "johndoe@example.com",
        "disabled": False,
    },
    "alice": {
        "username": "alice",
        "full_name": "Alice Wonderson",
        "hashed_password": hash("test"),
        "email": "alice@example.com",
        "disabled": True,
    },
}


def get_user(username: str) -> Optional[AuthModelBD]:
    user = fake_users_db.get(username)
    if user is None:
        return None
    return AuthModelBD(**user)


class App(FastAPI):

    @property
    def redis(self) -> redis.Redis:
        status: Optional[RedisStatus] = getattr(self, '_status_redis', None)
        if status == RedisStatus.CONNECTED:
            self.log(RedisEvent.CONNECT_SUCCESS, msg="Redis client is connected to server.")
            return self._redis
        if status == RedisStatus.AUTH_ERROR:  # pragma: no cover
            self.log(RedisEvent.CONNECT_FAIL, msg="Unable to connect to redis server due to authentication error.")
            raise HTTPException(status_code=503, detail="Redis authentication failed")
        if status == RedisStatus.CONN_ERROR:  # pragma: no cover
            self.log(RedisEvent.CONNECT_FAIL, msg="Redis server did not respond to PING message.")
            raise HTTPException(status_code=503, detail="Redis connection failed")
        if status is None:
            self._status_redis, self._redis = redis_connect(LOCAL_REDIS_URL)
            return self.redis
        raise HTTPException(status_code=503, detail="Redis connection failed")

    def log(self, level, msg):
        log._log(level, msg, [])


app = App()
security = HTTPBearer()
auth_handler = Auth(os.getenv("AUTH_SECRET", "no_sec"))
LOCAL_REDIS_URL = os.getenv("REDIS_HOST", "redis")
DNMONSTER_URL = os.getenv("DNMONSTER_URL", "http://dnmonster:8080").rstrip("/")


@app.post('/login')
def login(user_details: AuthModel):
    user = get_user(user_details.username)
    if user is None or user_details.hashed_password != user.hashed_password:
        raise HTTPException(status_code=401, detail='Invalid user data')

    access_token = auth_handler.encode_token(user.username)
    refresh_token = auth_handler.encode_refresh_token(user.username)
    return {'access_token': access_token, 'refresh_token': refresh_token}


@app.get('/refresh_token')
def refresh_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    new_token = auth_handler.refresh_token(token)
    return {'access_token': new_token}


def get_current_username(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    return auth_handler.decode_token(credentials.credentials)


def check_cashed(gen_str: str) -> io.BytesIO:
    data = app.redis.get(gen_str)
    if data:
        return io.BytesIO(data)
    req = requests.get(f'{DNMONSTER_URL}/monster/{gen_str}', timeout=5)
    req.raise_for_status()
    app.redis.set(gen_str, req.content)
    return io.BytesIO(req.content)


@app.get("/")
async def read_root():
    return "Hi, check is docks."


@app.get("/get_avatar/{rand_str}/")
async def get_avatar(rand_str: str, username: str = Security(get_current_username)):
    response = check_cashed(rand_str)
    return StreamingResponse(response, media_type="image/png")

# for debug
# import uvicorn

# uvicorn.run(app, host='0.0.0.0',port=80)
