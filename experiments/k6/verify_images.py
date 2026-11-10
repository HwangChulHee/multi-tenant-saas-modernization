#!/usr/bin/env python3
"""Check local image contracts and stop a Source Worker during an in-flight delivery."""

import argparse
import io
import json
import os
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

from collect import utc, write_json
from run import Stack, command, local_tokens, request


APP_SERVICES = ("catalog-api", "order-api", "fulfillment-worker", "mock-pos")
PORTS = dict(zip(APP_SERVICES, (18191, 18192, 18193, 18194)))


def inspect(identifier):
    return json.loads(command("docker", "inspect", identifier))[0]


def until(predicate, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError("Timed out waiting for local verification")


def jar_resources(data):
    with zipfile.ZipFile(io.BytesIO(data)) as jar:
        for name in jar.namelist():
            if name.startswith("BOOT-INF/classes/") and not name.endswith("/"):
                yield jar.read(name)
            elif name == "BOOT-INF/lib/common.jar":
                with zipfile.ZipFile(io.BytesIO(jar.read(name))) as common:
                    yield from (common.read(item) for item in common.namelist() if not item.endswith("/"))


def image_contract(image, secrets):
    config = inspect(image)["Config"]
    assert config["User"] == "10001:10001"
    assert config["Entrypoint"] == ["java", "-jar", "app.jar"]
    assert "wget" in " ".join(config["Healthcheck"]["Test"])
    assert not any(variable.split("=")[0].endswith(("PASSWORD", "SECRET", "TOKEN", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"))
                   for variable in config["Env"])
    history = command("docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", image).encode()
    jar = subprocess.check_output(["docker", "run", "--rm", "--entrypoint", "cat", image, "/app/app.jar"])
    resources = list(jar_resources(jar))
    assert resources
    env = "\n".join(config["Env"]).encode()
    assert not any(secret in blob for secret in secrets for blob in [env, history, *resources])
    return dict(image_id=image, configured_user=config["User"], secrets_found=False)


def source_container(stack, service, target, containers):
    runtime = dict(line.split("=", 1) for line in target["Config"]["Env"])
    names = {"ACTIVE_BRANDS", "SERVER_PORT", "DB_URL", "DB_BRAND_A_PASSWORD", "JWT_ISSUER",
             "JWT_AUDIENCE", "LOCAL_JWT_SECRET", "AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
             "SQS_ENDPOINT", "SQS_BRAND_A_QUEUE_URL", "POS_URL", "POS_SHARED_TOKEN", "POS_FAIL_FIRST",
             "POS_DELAY_MS", "SPRING_DATASOURCE_URL", "SPRING_DATASOURCE_USERNAME", "SPRING_DATASOURCE_PASSWORD"}
    env = {key: value for key, value in runtime.items() if key in names}
    env.update(ACTIVE_BRANDS="brand_a", SERVER_PORT=str(PORTS[service]))
    if service == "fulfillment-worker":
        env["POS_TIMEOUT_MS"] = "5000"
    flags = [item for key in env for item in ("-e", key)]
    port = PORTS[service]
    published = ("-p", f"127.0.0.1:{port}:{port}") if service in ("catalog-api", "order-api") else ()
    container = command("docker", "run", "-d", "--network", stack.project + "_default",
                        *published, *flags, target["Image"], env={**os.environ, **env}).strip()
    containers[service] = container
    until(lambda: inspect(container)["State"]["Health"]["Status"] == "healthy")
    user = command("docker", "exec", container, "id", "-u").strip()
    assert user == "10001"
    command("docker", "exec", container, "sh", "-ec",
            'wget -q -O /dev/null "http://127.0.0.1:$SERVER_PORT/health"')
    return port


def stop(container):
    start = time.monotonic()
    command("docker", "stop", "--time", "30", container)
    code = inspect(container)["State"]["ExitCode"]
    assert code in (0, 143), code
    logs = command("docker", "logs", container)
    assert "Graceful shutdown complete" in logs
    return dict(exit_code=code, stop_seconds=round(time.monotonic() - start, 3), graceful_log=True)


def verify(stack):
    stack.start(1, 3000, build=True)
    tokens = local_tokens(stack)
    targets = {service: inspect(stack.compose("ps", "-q", service).strip()) for service in APP_SERVICES}
    secrets = {value.encode() for key, value in stack.env.items()
               if key.endswith(("_PASSWORD", "_SECRET", "_TOKEN")) and value}
    images = {service: image_contract(target["Image"], secrets) for service, target in targets.items()}
    stack.warm(tokens)
    stack.compose("stop", "catalog-api", "order-api", "fulfillment-worker", capture=False)
    containers = {}
    try:
        for service in APP_SERVICES:
            port = source_container(stack, service, targets[service], containers)
            images[service].update(image_health="healthy", health_endpoint=200, runtime_uid=10001, server_port=port)
        catalog, order = PORTS["catalog-api"], PORTS["order-api"]
        assert request(catalog, "/catalog", bearer=tokens["a"])[0] == 200
        for b in ("b", "c"):
            assert request(catalog, "/catalog", bearer=tokens[b])[0] == 401
            assert request(order, "/orders/00000000-0000-0000-0000-000000000000", bearer=tokens[b])[0] == 401
        status, created = request(order, "/orders", bearer=tokens["a"], body={"menuId": "menu-1", "quantity": 1},
                                  headers={"Idempotency-Key": "sigterm-" + uuid.uuid4().hex})
        assert status == 201
        order_id = uuid.UUID(created["id"])
        until(lambda: stack.sql(f"""SELECT count(*) FROM mock_pos.deliveries d JOIN brand_a.orders o ON o.id=d.order_id
                                   WHERE o.id='{order_id}' AND o.status='PENDING' AND d.accepted_at IS NOT NULL""")
              .strip() == "1")
        images["fulfillment-worker"]["sigterm"] = stop(containers["fulfillment-worker"])
        status, fulfilled = request(order, f"/orders/{order_id}", bearer=tokens["a"])
        assert status == 200 and fulfilled["status"] == "FULFILLED"
        until(lambda: not any(stack.queues()["brand_a"]["source"].values()))
        for service in ("catalog-api", "order-api", "mock-pos"):
            images[service]["sigterm"] = stop(containers[service])
        return dict(checked_at=utc(), images=images, target_active_brands="brand_a,brand_b,brand_c",
                    source_active_brands="brand_a", inactive_brands_rejected=True,
                    source_brand_a_fulfilled_on_worker_sigterm=True, source_queue_drained=True,
                    unverified=["ECS Task Role / AWS SQS", "RDS TLS / credentials", "external JWKS"])
    finally:
        for container in containers.values():
            command("docker", "rm", "-f", container)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    stack = Stack()
    try:
        result = verify(stack)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, result)
    finally:
        stack.compose("down", "--volumes", capture=False)


if __name__ == "__main__":
    main()
