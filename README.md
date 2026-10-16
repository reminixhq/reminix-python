# reminix

The Reminix Python SDK runs your team's published scripts from your code: one call starts a run, waits for it however long it takes, handles approvals and files, and gives you the result. Every API operation is a typed method too, sync or async.

Reminix lets your whole team, your software and your agents run your team's scripts, and the ones AI writes: one publish gives a form, an API and an agent tool, with keys kept out of the code and every run on record.

## Install

```bash
pip install reminix
```

Needs Python 3.10 or later. Set `REMINIX_API_KEY` to a key from **API
keys** in the app.

## Publish a script

Scripts are published with the Reminix CLI. In the script's folder:

```bash
npm install -g @reminix/cli
reminix login
reminix publish
```

Reminix works out how the script runs from the folder. Inputs, drafts
and publishing several scripts at once are in the
[CLI guide](https://reminix.com/docs/cli/).

## Run a script

`run` runs a published script and gives you its result in one call,
however long it takes:

```python
from reminix import Reminix

reminix = Reminix()  # reads REMINIX_API_KEY

run = reminix.run("monthly-report", {"month": "2026-09"})
print(run["output"])
```

- A run that needs a person's approval waits for them. Pass
  `on_approval` to show them where to approve it.
- A run that fails, or whose approval is turned down, raises a
  `RunError` with the run's status and error.

## Files in and out

Give a file input as a path, an open file or a `FileUpload`; the SDK
uploads it first. The files a run writes come back with a download
link:

```python
from pathlib import Path

from reminix import Reminix

reminix = Reminix()

run = reminix.run(
    "monthly-report",
    {"month": "2026-09", "adjustments": Path("adjustments.csv")},
)
for file in run.get("files") or []:
    if file["direction"] == "out":
        print(file["name"], file["downloadUrl"])
```

## Everything else

Every API operation is a typed method, named like its CLI command:
`reminix runs list` is `reminix.runs.list()`. For asyncio, use
`AsyncReminix`. A failure raises `ApiError` with the error's `code`,
`message`, `status` and `request_id`.

## Links

- [Website](https://reminix.com)
- [Python SDK guide](https://reminix.com/docs/python/)
- [API reference](https://reminix.com/docs/reference/)
- [Changelog](https://github.com/reminixhq/reminix-python/blob/main/CHANGELOG.md)
- [Discord](https://reminix.com/discord)
- [Report a security issue](https://reminix.com/security/)

## About this package

This repository is generated from Reminix's source on each
release, so pull requests are ported there and credited (see
[CONTRIBUTING.md](https://github.com/reminixhq/reminix-python/blob/main/CONTRIBUTING.md)).
Licensed under the Apache License 2.0.
