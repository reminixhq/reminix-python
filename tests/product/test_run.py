"""Reminix's run / upload_file helpers, against a fake API."""

import asyncio
import json

import httpx
import pytest


def api(sdk, handler):
    seen = []

    def respond(request):
        seen.append(request)
        return handler(request)

    client = sdk.Reminix(token="sk_test", http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    return client, seen


def test_run_uploads_files_and_follows_the_run_to_its_end(sdk, tmp_path):
    statement = tmp_path / "sept.csv"
    statement.write_bytes(b"id\n1\n")
    runs = [{"id": "run_1", "status": "running"}, {"id": "run_1", "status": "succeeded", "output": 42}]

    def respond(request):
        if request.url.path == "/v1/files":
            return httpx.Response(201, json={"id": "file_1"})
        if request.method == "POST":
            return httpx.Response(201, json=runs.pop(0))
        return httpx.Response(200, json=runs.pop(0))

    reminix, seen = api(sdk, respond)
    run = reminix.run("refund-customer", {"statement": statement, "orderId": "o_1"}, poll=0)
    assert run["output"] == 42
    upload, start, follow = seen
    assert upload.url.params["name"] == "sept.csv"
    assert upload.headers["content-type"] == "text/csv"
    assert upload.content == b"id\n1\n"
    assert json.loads(start.content) == {"inputs": {"statement": "file_1", "orderId": "o_1"}}
    assert follow.url.path == "/v1/runs/run_1"


def test_a_failed_run_raises_run_error(sdk):
    reminix, _ = api(sdk, lambda r: httpx.Response(201, json={"id": "run_2", "status": "failed", "error": "boom"}))
    with pytest.raises(sdk.RunError) as raised:
        reminix.run("refund-customer")
    assert raised.value.run["error"] == "boom"


def test_an_approval_is_announced_and_wait_false_answers_at_once(sdk):
    held = {"id": "run_3", "status": "awaiting_approval", "approval": {"approveUrl": "https://x/approve"}}
    reminix, _ = api(sdk, lambda r: httpx.Response(201, json=held))
    links = []
    run = reminix.run("refund-customer", on_approval=links.append, wait=False)
    assert run["status"] == "awaiting_approval"
    assert links == ["https://x/approve"]


def test_async_run(sdk):
    def respond(request):
        return httpx.Response(201, json={"id": "run_4", "status": "succeeded"})

    async def go():
        async with sdk.AsyncReminix(
            token="sk_test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        ) as reminix:
            return await reminix.run("refund-customer", {"orderId": "o_1"})

    assert asyncio.run(go())["status"] == "succeeded"


def test_a_key_makes_the_run_and_its_uploads_safe_to_call_again(sdk, tmp_path):
    statement = tmp_path / "sept.csv"
    statement.write_bytes(b"id\n1\n")

    def respond(request):
        if request.url.path == "/v1/files":
            return httpx.Response(201, json={"id": "file_1"})
        return httpx.Response(201, json={"id": "run_1", "status": "succeeded"})

    keys = []
    for _ in range(2):
        reminix, seen = api(sdk, respond)
        reminix.run("refund-customer", {"statement": statement}, idempotency_key="nightly-42")
        keys.append([r.headers.get("idempotency-key") for r in seen])
    assert keys[0] == ["nightly-42:file-1", "nightly-42"]
    assert keys[1] == keys[0]
