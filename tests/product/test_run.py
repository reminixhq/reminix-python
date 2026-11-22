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
    run = reminix.run("refund-customer", {"statement": statement, "orderId": "o_1"}, poll_interval=0)
    assert run.output == 42
    upload, start, follow = seen
    assert upload.url.params["name"] == "sept.csv"
    # The API names the type from the file name.
    assert upload.headers["content-type"] == "application/octet-stream"
    assert upload.content == b"id\n1\n"
    assert json.loads(start.content) == {"inputs": {"statement": "file_1", "orderId": "o_1"}}
    assert follow.url.path == "/v1/runs/run_1"


def test_a_failed_run_raises_run_error(sdk):
    reminix, _ = api(sdk, lambda r: httpx.Response(201, json={"id": "run_2", "status": "failed", "error": "boom"}))
    with pytest.raises(sdk.RunError) as raised:
        reminix.run("refund-customer")
    assert raised.value.run.error == "boom"


def test_an_approval_is_announced_and_wait_false_answers_at_once(sdk):
    held = {"id": "run_3", "status": "awaiting_approval", "approval": {"approveUrl": "https://x/approve"}}
    reminix, _ = api(sdk, lambda r: httpx.Response(201, json=held))
    links = []
    run = reminix.run("refund-customer", on_approval=links.append, wait=False)
    assert run.status == "awaiting_approval"
    assert links == ["https://x/approve"]


def test_async_run(sdk):
    def respond(request):
        return httpx.Response(201, json={"id": "run_4", "status": "succeeded"})

    async def go():
        async with sdk.AsyncReminix(
            token="sk_test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        ) as reminix:
            return await reminix.run("refund-customer", {"orderId": "o_1"})

    assert asyncio.run(go()).status == "succeeded"


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


def test_timeout_is_each_request_s_limit(sdk, tmp_path):
    statement = tmp_path / "sept.csv"
    statement.write_bytes(b"id\n1\n")
    runs = [{"id": "run_5", "status": "running"}, {"id": "run_5", "status": "succeeded"}]

    def respond(request):
        if request.url.path == "/v1/files":
            return httpx.Response(201, json={"id": "file_1"})
        return httpx.Response(201 if request.method == "POST" else 200, json=runs.pop(0))

    reminix, seen = api(sdk, respond)
    reminix.run("refund-customer", {"statement": statement}, poll_interval=0, timeout=5.0)
    # The upload, the start and the poll, each limited on its own.
    assert [r.extensions["timeout"]["read"] for r in seen] == [5.0, 5.0, 5.0]


def test_no_timeout_leaves_the_client_s_own(sdk):
    runs = [{"id": "run_7", "status": "running"}, {"id": "run_7", "status": "succeeded"}]
    reminix, seen = api(sdk, lambda r: httpx.Response(201, json=runs.pop(0)))
    reminix.run("refund-customer", poll_interval=0)
    assert [r.extensions["timeout"]["read"] for r in seen] == [60.0, 60.0]


def test_wait_for_run_follows_a_run_by_its_id(sdk):
    runs = [{"id": "run_8", "status": "running"}, {"id": "run_8", "status": "succeeded", "output": 3}]
    reminix, seen = api(sdk, lambda r: httpx.Response(200, json=runs.pop(0)))
    run = reminix.wait_for_run("run_8", poll_interval=0)
    assert run.output == 3
    assert [r.url.path for r in seen] == ["/v1/runs/run_8", "/v1/runs/run_8"]


def test_run_error_is_the_sdk_s_own(sdk):
    reminix, _ = api(sdk, lambda r: httpx.Response(201, json={"id": "run_2", "status": "cancelled"}))
    with pytest.raises(sdk.ReminixError) as raised:
        reminix.run("refund-customer")
    assert isinstance(raised.value, sdk.RunError)
    assert "cancelled" in str(raised.value)


def test_upload_file_returns_the_file(sdk, tmp_path):
    path = tmp_path / "sept.csv"
    path.write_bytes(b"a")
    reminix, seen = api(sdk, lambda r: httpx.Response(201, json={"id": "file_1", "name": "sept.csv"}))
    file = reminix.upload_file(path, idempotency_key="k-1", extra_headers={"x-trace": "t"})
    assert isinstance(file, sdk.File)
    assert file.id == "file_1"
    assert seen[0].headers["idempotency-key"] == "k-1"
    assert seen[0].headers["x-trace"] == "t"


def test_async_timeout_is_each_request_s_limit_too(sdk):
    runs = [{"id": "run_6", "status": "running"}, {"id": "run_6", "status": "succeeded"}]
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(201 if request.method == "POST" else 200, json=runs.pop(0))

    async def go():
        async with async_api(sdk, respond) as reminix:
            await reminix.run("refund-customer", version=3, poll_interval=0, timeout=httpx.Timeout(5.0))

    asyncio.run(go())
    assert [r.url.path for r in seen] == ["/v1/scripts/refund-customer/versions/3/runs", "/v1/runs/run_6"]
    assert all(r.extensions["timeout"]["read"] == 5.0 for r in seen)


def async_api(sdk, handler):
    return sdk.AsyncReminix(token="sk_test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_cancelling_the_task_stops_an_async_wait(sdk):
    running = lambda r: httpx.Response(201, json={"id": "run_9", "status": "running"})

    async def go():
        async with async_api(sdk, running) as reminix:
            task = asyncio.ensure_future(reminix.run("refund-customer", poll_interval=0.01))
            await asyncio.sleep(0.05)
            assert not task.done()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(go())
