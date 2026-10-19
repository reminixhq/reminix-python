# `reminix.run(slug, inputs)` in Python — the SDK's hero helper, as in the
# TypeScript SDK: one call that runs a script and answers with the
# finished run. Files in the inputs (a `pathlib.Path`, an open binary file
# or a `FileUpload`) are uploaded first and given by id; a long run, or
# one held for a person's approval, is followed until it ends; a run that
# fails or is cancelled raises `RunError`, with the run. The finished run
# carries its output and the files it wrote, each with a download link.
#
#     reminix = Reminix()  # reads REMINIX_API_KEY
#     run = reminix.run("unlock-account", {"email": "jane@example.com"})
#     print(run["output"])

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import IO, Any, Callable, Dict, Mapping, Optional, Union


_ENDED = {"succeeded", "failed", "cancelled"}


@dataclass
class FileUpload:
    """A file to give a run: its name, its bytes, and its media type."""

    name: str
    data: bytes
    type: Optional[str] = None


Upload = Union[FileUpload, "os.PathLike[str]", IO[bytes]]


class RunError(Exception):
    """A run that ended without succeeding: failed, or cancelled. The API's `error` says why."""

    def __init__(self, run: Dict[str, Any]) -> None:
        if run.get("status") == "cancelled":
            message = f"Run {run.get('id')} was cancelled: {run.get('error') or 'no reason given'}"
        else:
            message = f"Run {run.get('id')} failed: {run.get('error') or 'no error message'}"
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
    # No guess here: the API takes the type from the name (one table for every client).
    return file.type or "application/octet-stream"


def _options(key: Optional[str]) -> Any:
    return {"idempotency_key": key} if key else None


class ProductMethods:
    """`reminix.run(...)` and `reminix.upload_file(...)`."""

    _call: Any
    runs: Any
    script_versions: Any

    def upload_file(self, file: Upload, *, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Uploads a file to give a run as an input; returns it, with its `id`."""
        upload = _as_upload(file)
        return self._call(
            _UPLOAD, {}, {"name": upload.name}, _options(idempotency_key), upload.data, _media(upload)
        )

    def _with_file_ids(self, inputs: Mapping[str, Any], key: Optional[str]) -> Dict[str, Any]:
        # The nth file's key, in input order: the same on every call.
        count = 0

        def upload(value: Any) -> str:
            nonlocal count
            count += 1
            return self.upload_file(value, idempotency_key=f"{key}:file-{count}" if key else None)["id"]

        out: Dict[str, Any] = {}
        for name, value in inputs.items():
            if _is_upload(value):
                out[name] = upload(value)
            elif isinstance(value, list) and any(_is_upload(v) for v in value):
                out[name] = [upload(v) if _is_upload(v) else v for v in value]
            else:
                out[name] = value
        return out

    def wait_for_run(self, run: Dict[str, Any], *, poll: float = 2.0) -> Dict[str, Any]:
        """Follows a run until it ends; raises `RunError` if it didn't succeed."""
        while run.get("status") not in _ENDED:
            time.sleep(poll)
            run = self.runs.get(run["id"])
        if run.get("status") != "succeeded":
            raise RunError(run)
        return run

    def run(
        self,
        slug: str,
        inputs: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        wait: bool = True,
        on_approval: Optional[Callable[[Optional[str]], None]] = None,
        poll: float = 2.0,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs a script and answers with the finished run.

        `version` runs that version (a draft, as a test run) instead of the
        published one; `wait=False` answers at once; `on_approval` is called
        once if the run waits for a person, with the link to approve it.
        `idempotency_key` makes calling again safe: the same key and inputs
        answer with the first run instead of starting another.
        """
        given = self._with_file_ids(inputs or {}, idempotency_key)
        options = _options(idempotency_key)
        if version is None:
            started = self.runs.create(slug, inputs=given, request_options=options)
        else:
            started = self.script_versions.run(slug, version, inputs=given, request_options=options)
        if started.get("status") == "awaiting_approval" and on_approval:
            on_approval((started.get("approval") or {}).get("approveUrl"))
        if not wait:
            return started
        return self.wait_for_run(started, poll=poll)


class AsyncProductMethods:
    """The same, to `await`."""

    _call: Any
    runs: Any
    script_versions: Any

    async def upload_file(
        self, file: Upload, *, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads a file to give a run as an input; returns it, with its `id`."""
        upload = _as_upload(file)
        return await self._call(
            _UPLOAD, {}, {"name": upload.name}, _options(idempotency_key), upload.data, _media(upload)
        )

    async def _with_file_ids(self, inputs: Mapping[str, Any], key: Optional[str]) -> Dict[str, Any]:
        count = 0

        async def upload(value: Any) -> str:
            nonlocal count
            count += 1
            uploaded = await self.upload_file(
                value, idempotency_key=f"{key}:file-{count}" if key else None
            )
            return uploaded["id"]

        out: Dict[str, Any] = {}
        for name, value in inputs.items():
            if _is_upload(value):
                out[name] = await upload(value)
            elif isinstance(value, list) and any(_is_upload(v) for v in value):
                out[name] = [await upload(v) if _is_upload(v) else v for v in value]
            else:
                out[name] = value
        return out

    async def wait_for_run(self, run: Dict[str, Any], *, poll: float = 2.0) -> Dict[str, Any]:
        """Follows a run until it ends; raises `RunError` if it didn't succeed."""
        while run.get("status") not in _ENDED:
            await asyncio.sleep(poll)
            run = await self.runs.get(run["id"])
        if run.get("status") != "succeeded":
            raise RunError(run)
        return run

    async def run(
        self,
        slug: str,
        inputs: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        wait: bool = True,
        on_approval: Optional[Callable[[Optional[str]], None]] = None,
        poll: float = 2.0,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs a script and answers with the finished run (see `Reminix.run`)."""
        given = await self._with_file_ids(inputs or {}, idempotency_key)
        options = _options(idempotency_key)
        if version is None:
            started = await self.runs.create(slug, inputs=given, request_options=options)
        else:
            started = await self.script_versions.run(
                slug, version, inputs=given, request_options=options
            )
        if started.get("status") == "awaiting_approval" and on_approval:
            on_approval((started.get("approval") or {}).get("approveUrl"))
        if not wait:
            return started
        return await self.wait_for_run(started, poll=poll)
