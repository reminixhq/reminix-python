# `reminix.run(slug, inputs)` in Python — the SDK's hero helper, as in the
# TypeScript SDK: one call that runs a script and answers with the
# finished run. Files in the inputs (a `pathlib.Path`, an open binary file
# or a `FileUpload`) are uploaded first and given by id; a long run, or
# one awaiting a person's approval, is followed until it ends; a run that
# fails or is cancelled raises `RunError`, with the run. The finished run
# is a `Run` model, with its output and the files it saved, each with a
# download link.
#
#     reminix = Reminix()  # reads REMINIX_API_KEY
#     run = reminix.run("unlock-account", {"email": "jane@example.com"})
#     print(run.output)
#
# Like every method, the helpers take `idempotency_key=`, `extra_headers=`
# and `timeout=` (each request's limit, in seconds or an `httpx.Timeout`;
# a timed-out request is retried). The wait as a whole has none, as in
# other SDKs' polling helpers: an async call stops when its task is
# cancelled, so `asyncio.timeout()` limits it.

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import IO, Any, Callable, Dict, Mapping, Optional, Union, cast

from .._error import ProductError
from .._runtime import NOT_GIVEN, Timeout
from ..types import File, Run


_ENDED = {"succeeded", "failed", "cancelled"}


@dataclass
class FileUpload:
    """A file to give a run: its name, its bytes, and its media type."""

    name: str
    data: bytes
    media_type: Optional[str] = None


Upload = Union[FileUpload, "os.PathLike[str]", IO[bytes]]


class RunError(ProductError):
    """A run that ended without succeeding: failed, or cancelled. The API's `error` says why."""

    def __init__(self, run: Run) -> None:
        error = getattr(run, "error", None)
        if run.status == "cancelled":
            message = f"Run {run.id} was cancelled: {error or 'no reason given'}"
        else:
            message = f"Run {run.id} failed: {error or 'no error message'}"
        super().__init__(message)
        self.run = run


def _is_upload(value: Any) -> bool:
    return isinstance(value, (FileUpload, os.PathLike)) or (
        hasattr(value, "read") and hasattr(value, "name")
    )


def _as_upload(value: Any) -> FileUpload:
    if isinstance(value, FileUpload):
        return value
    if isinstance(value, os.PathLike):
        path = os.fspath(value)
        with open(path, "rb") as f:
            return FileUpload(os.path.basename(path), f.read())
    return FileUpload(os.path.basename(str(value.name)), value.read())


# Upload a file: its bytes as the body. Through the client's own request
# path, so it sends an Idempotency-Key and retries like every write.
_UPLOAD: Any = {
    "method": "post",
    "path": "/files",
    "query": ["name"],
    "body": False,
    "names": {},
    "raw_body": "application/octet-stream",
}


def _media(file: FileUpload) -> str:
    # No guess here: the API takes the media type from the name (one table for every client).
    return file.media_type or "application/octet-stream"


def _file_key(key: Optional[str], count: int) -> Optional[str]:
    # The nth file's key, in input order: the same on every call.
    return f"{key}:file-{count}" if key else None


def _approve_url(started: Any) -> Optional[str]:
    # A model's field, or the API's own name where it came through as JSON.
    approval = getattr(started, "approval", None)
    if isinstance(approval, dict):
        return cast(Optional[str], approval.get("approveUrl"))
    return getattr(approval, "approve_url", None) if approval else None


class ProductMethods:
    """`reminix.run(...)`, `reminix.wait_for_run(...)` and `reminix.upload_file(...)`."""

    _call: Any
    runs: Any
    script_versions: Any

    def upload_file(
        self,
        file: Upload,
        *,
        idempotency_key: Optional[str] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> File:
        """Uploads a file to give a run as an input; returns it, with its `id`."""
        upload = _as_upload(file)
        return self._call(
            _UPLOAD,
            {},
            {"name": upload.name},
            content=upload.data,
            content_type=_media(upload),
            cast_to=File,
            idempotency_key=idempotency_key,
            extra_headers=extra_headers,
            timeout=timeout,
        )

    def _with_file_ids(
        self,
        inputs: Mapping[str, Any],
        key: Optional[str],
        extra_headers: Optional[Mapping[str, str]],
        timeout: Timeout,
    ) -> Dict[str, Any]:
        count = 0

        def upload(value: Any) -> str:
            nonlocal count
            count += 1
            return self.upload_file(
                value,
                idempotency_key=_file_key(key, count),
                extra_headers=extra_headers,
                timeout=timeout,
            ).id

        out: Dict[str, Any] = {}
        for name, value in inputs.items():
            if _is_upload(value):
                out[name] = upload(value)
            elif isinstance(value, list) and any(_is_upload(v) for v in value):
                out[name] = [upload(v) if _is_upload(v) else v for v in value]
            else:
                out[name] = value
        return out

    def wait_for_run(
        self,
        run: Union[Run, str],
        *,
        poll_interval: float = 2.0,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> Run:
        """Follows a run, or a run by its id, until it ends; raises `RunError` if it didn't succeed.

        `poll_interval` is how often to check, in seconds. `timeout` is each
        request's limit, as on every method.
        """
        current: Run = (
            self.runs.get(run, extra_headers=extra_headers, timeout=timeout)
            if isinstance(run, str)
            else run
        )
        while current.status not in _ENDED:
            time.sleep(poll_interval)
            current = self.runs.get(current.id, extra_headers=extra_headers, timeout=timeout)
        if current.status != "succeeded":
            raise RunError(current)
        return current

    def run(
        self,
        slug: str,
        inputs: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        wait: bool = True,
        on_approval: Optional[Callable[[Optional[str]], None]] = None,
        poll_interval: float = 2.0,
        idempotency_key: Optional[str] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> Run:
        """Runs a script and answers with the finished run.

        `version` runs that version (a draft, as a test run) instead of the
        published one; `wait=False` answers at once; `on_approval` is called
        once if the run waits for a person, with the link to approve it.
        `idempotency_key` makes calling again safe: the same key and inputs
        answer with the first run instead of starting another.
        `poll_interval` is how often to check a run that hasn't ended, in
        seconds, and `timeout` each request's limit; the wait as a whole
        has none.
        """
        given = self._with_file_ids(inputs or {}, idempotency_key, extra_headers, timeout)
        options: Dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "extra_headers": extra_headers,
            "timeout": timeout,
        }
        if version is None:
            started = self.runs.create(slug, inputs=given, **options)
        else:
            started = self.script_versions.test_run(slug, version, inputs=given, **options)
        # A run awaiting approval is a Run with its `approval`.
        run = cast(Run, started)
        if run.status == "awaiting_approval" and on_approval:
            on_approval(_approve_url(started))
        if not wait:
            return run
        return self.wait_for_run(
            run, poll_interval=poll_interval, extra_headers=extra_headers, timeout=timeout
        )


class AsyncProductMethods:
    """The same, to `await`."""

    _call: Any
    runs: Any
    script_versions: Any

    async def upload_file(
        self,
        file: Upload,
        *,
        idempotency_key: Optional[str] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> File:
        """Uploads a file to give a run as an input; returns it, with its `id`."""
        upload = _as_upload(file)
        return await self._call(
            _UPLOAD,
            {},
            {"name": upload.name},
            content=upload.data,
            content_type=_media(upload),
            cast_to=File,
            idempotency_key=idempotency_key,
            extra_headers=extra_headers,
            timeout=timeout,
        )

    async def _with_file_ids(
        self,
        inputs: Mapping[str, Any],
        key: Optional[str],
        extra_headers: Optional[Mapping[str, str]],
        timeout: Timeout,
    ) -> Dict[str, Any]:
        count = 0

        async def upload(value: Any) -> str:
            nonlocal count
            count += 1
            uploaded = await self.upload_file(
                value,
                idempotency_key=_file_key(key, count),
                extra_headers=extra_headers,
                timeout=timeout,
            )
            return uploaded.id

        out: Dict[str, Any] = {}
        for name, value in inputs.items():
            if _is_upload(value):
                out[name] = await upload(value)
            elif isinstance(value, list) and any(_is_upload(v) for v in value):
                out[name] = [await upload(v) if _is_upload(v) else v for v in value]
            else:
                out[name] = value
        return out

    async def wait_for_run(
        self,
        run: Union[Run, str],
        *,
        poll_interval: float = 2.0,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> Run:
        """Follows a run, or a run by its id, until it ends; raises `RunError` if it didn't succeed.

        `timeout` is each request's limit. To limit the whole wait, use
        `asyncio.timeout()`: cancelling the task stops it.
        """
        current: Run = (
            await self.runs.get(run, extra_headers=extra_headers, timeout=timeout)
            if isinstance(run, str)
            else run
        )
        while current.status not in _ENDED:
            await asyncio.sleep(poll_interval)
            current = await self.runs.get(current.id, extra_headers=extra_headers, timeout=timeout)
        if current.status != "succeeded":
            raise RunError(current)
        return current

    async def run(
        self,
        slug: str,
        inputs: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        wait: bool = True,
        on_approval: Optional[Callable[[Optional[str]], None]] = None,
        poll_interval: float = 2.0,
        idempotency_key: Optional[str] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Timeout = NOT_GIVEN,
    ) -> Run:
        """Runs a script and answers with the finished run (see `Reminix.run`)."""
        given = await self._with_file_ids(inputs or {}, idempotency_key, extra_headers, timeout)
        options: Dict[str, Any] = {
            "idempotency_key": idempotency_key,
            "extra_headers": extra_headers,
            "timeout": timeout,
        }
        if version is None:
            started = await self.runs.create(slug, inputs=given, **options)
        else:
            started = await self.script_versions.test_run(slug, version, inputs=given, **options)
        run = cast(Run, started)
        if run.status == "awaiting_approval" and on_approval:
            on_approval(_approve_url(started))
        if not wait:
            return run
        return await self.wait_for_run(
            run, poll_interval=poll_interval, extra_headers=extra_headers, timeout=timeout
        )
