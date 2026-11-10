import base64
import hashlib
import hmac
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

BRANDS = ("brand_a", "brand_b", "brand_c")
CATALOG = int(os.getenv("CATALOG_PORT", "8081"))
ORDER = int(os.getenv("ORDER_PORT", "8082"))


def token(brand, **claims):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    payload = dict(iss=os.getenv("JWT_ISSUER", "https://local.ordersaas.test"),
                   aud=os.getenv("JWT_AUDIENCE", "ordersaas"), sub="integration-test",
                   tenant_id=brand, exp=int(time.time()) + 600)
    payload.update(claims)
    data = b".".join(encode(json.dumps(obj).encode()) for obj in ({"alg": "HS256"}, payload))
    signature = hmac.digest(os.environ["LOCAL_JWT_SECRET"].encode(), data, hashlib.sha256)
    return (data + b"." + encode(signature)).decode()


def request(port, path, *, bearer=None, body=None, headers=None, method=None):
    headers = dict(headers or {})
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        return response.status, json.loads(data) if data else None


def order(brand, key=None, quantity=1):
    return request(ORDER, "/orders", bearer=token(brand),
                   body={"menuId": "menu-1", "quantity": quantity},
                   headers={"Idempotency-Key": key or uuid.uuid4().hex})


def compose(*args, check=True):
    return subprocess.run(["docker", "compose", "--env-file", ".env.example", *args],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, check=check)


def sql(statement, *, user="ordersaas", password="local-dev-only", check=True):
    return compose("exec", "-T", "-e", f"PGPASSWORD={password}", "postgres",
                   "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
                   "-h", "127.0.0.1", "-U", user, "-d", "ordersaas", "-c", statement, check=check)


def wait_for(predicate, description, *, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for {description}")
