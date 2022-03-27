from fastapi.testclient import TestClient
import time
from app.main import app

client = TestClient(app)

def timer(func, *arg, **kw):
    t1 = time.time()
    res = func(*arg, **kw)
    t2 = time.time()
    return (t2 - t1),res

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200

def test_autch_try():
    user = {
          "username": "johndoe",
          "password": "test_good"
        }
    client.headers['Content-Type'] = 'application/json'
    response = client.post("/login", json = user)
    assert response.status_code == 200
    data = response.json()
    assert data['access_token'] is not None
    assert data['refresh_token'] is not None
#
def test_autch_false():
    user = {
          "username": "johndoe_two",
          "password": "test_good"
        }
    response = client.post("/login",json= user)
    assert response.status_code == 200
    data = response.json()
    assert data['status_code'] is not None


def test_autch_false_transport_err():
    user = {
          "username": "johndoe_two",
          "password": "test_good"
        }
    response = client.post("/login",user)
    assert response.status_code == 422

def test_get_image():
    user = {
          "username": "johndoe",
          "password": "test_good"
        }
    response = client.post("/login", json=user)
    token = response.json()['access_token']
    response = client.get("/get_avatar/test",headers = {'Authorization':'Bearer ' +token})
    assert response.status_code == 200


def test_get_image_cashed():
    user = {
          "username": "johndoe",
          "password": "test_good"
        }
    response = client.post("/login", json=user)
    token = response.json()['access_token']
    rand_str = token[:10]
    client.headers['Authorization'] = 'Bearer ' + token

    time_no_cashed, response = timer(client.get, "/get_avatar/"+rand_str, headers = {'Authorization':'Bearer ' +token})
    assert response.status_code == 200

    time_cashed, response = timer(client.get, "/get_avatar/"+rand_str, headers = {'Authorization':'Bearer ' +token})
    assert response.status_code == 200

    assert time_cashed < time_no_cashed
