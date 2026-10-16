# reminix

The Python client for the Reminix API. Every operation is a
method, typed from the API itself; sync and async.

Reminix lets your whole team, your software and your agents run your team's scripts, and the ones AI writes: one publish gives a form, an API and an agent tool, with keys kept out of the code and every run on record.

## Install

```bash
pip install reminix
```

## Use

```python
from reminix import Reminix

reminix = Reminix()  # reads REMINIX_API_KEY
workspace = reminix.workspace.get()
```

A failure raises `ApiError` with the error's `code`, `message`,
`status` and `request_id`. For asyncio, use `AsyncReminix`.

- Guide: https://reminix.com/docs/python/
- API reference: https://api.reminix.com/v1/docs
