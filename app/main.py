import io
from logging import getLogger

import requests
from fastapi import FastAPI
from fastapi import HTTPException, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.autch import Auth, AuthModel, AuthModelBD
from app.redis import redis_connect, RedisStatus, RedisEvent
import redis

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


def get_user(username) -> AuthModelBD:
    return AuthModelBD(**fake_users_db[username])


class App(FastAPI):

    @property
    def redis(self)->redis.Redis:
        status:RedisStatus = getattr(self,'_status_redis',None)
        if status == RedisStatus.CONNECTED:
            self.log(RedisEvent.CONNECT_SUCCESS, msg="Redis client is connected to server.")
            return self._redis
        if status == RedisStatus.AUTH_ERROR:  # pragma: no cover
            self.log(RedisEvent.CONNECT_FAIL, msg="Unable to connect to redis server due to authentication error.")
        if status == RedisStatus.CONN_ERROR:  # pragma: no cover
            self.log(RedisEvent.CONNECT_FAIL, msg="Redis server did not respond to PING message.")
        if status == None:
            self._status_redis, self._redis = redis_connect(LOCAL_REDIS_URL)
            return self.redis

    def log(self,level,msg):
        log._log(level,msg,[])


app = App()
security = HTTPBearer()
auth_handler = Auth("no_sec")
LOCAL_REDIS_URL = 'redis'


@app.post('/login')
def login(user_details: AuthModel):
    try:
        user = get_user(user_details.username)
        if user is None:
            raise Exception('Invalid username')
        if user_details.hashed_password == user.hashed_password:
            raise Exception('Invalid password')
    except Exception as e:
        return HTTPException(status_code=401, detail='Invalid user date')

    access_token = auth_handler.encode_token(user.username)
    refresh_token = auth_handler.encode_refresh_token(user.username)
    return {'access_token': access_token, 'refresh_token': refresh_token}


@app.get('/refresh_token')
def refresh_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    refresh_token = credentials.credentials
    new_token = auth_handler.refresh_token(refresh_token)
    return {'access_token': new_token}


def check_cashed(gen_str: str) -> io.BytesIO:
    data = app.redis.get(gen_str)
    if data:
        return io.BytesIO(data)
    else:
        req = requests.get(f'http://dnmonster:8080/monster/{gen_str}')
        app.redis.set(gen_str, req.content)
        return io.BytesIO(req.content)

@app.get("/")
async def read_root():
    return "Hi, check is docks."

@app.get("/get_avatar/{rand_str}/")
async def read_root(rand_str: str, credentials: HTTPAuthorizationCredentials = Security(security)):
    response = check_cashed(rand_str)
    return StreamingResponse(response, media_type="image/png")

# for debug
# import uvicorn

# uvicorn.run(app, host='0.0.0.0',port=80)
