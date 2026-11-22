# Changelog

What changed in the Reminix Python SDK (`reminix`). Generated from the source on each release; newest first.

## 1.0.0rc12 (2026-11-22)

### Added

- You can now read one schedule, one trigger or one secret at its own
  address: `GET /v1/scripts/{slug}/schedules/{scheduleId}`,
  `GET /v1/scripts/{slug}/triggers/{triggerId}` and `GET /v1/secrets/{name}`.
  In the SDKs they're `schedules.get`, `triggers.get` and `secrets.get`,
  in the CLI `reminix schedules get`, `triggers get` and `secrets get`, and
  the MCP server has a tool for each. A secret's value is never returned.
- Everything you create now answers with a `Location` header that gives
  its address: a script, a version, a schedule, a trigger, an environment,
  a file and a run. One version of a script can now be read at
  `GET /v1/scripts/{slug}/versions/{version}` (`scriptVersions.get`).
- Reminix is here: turn your scripts into tools your team, your software
  and your AI agents can run.

  Upload a Python, shell or Node script, and Reminix runs it. Start a run
  from a form in the app, from the API or from the CLI. A
  script can also run on a schedule, or when another service calls its
  webhook. Your agents in Claude and ChatGPT can find your scripts and run
  them for you.

  Each run gets its own isolated machine. Your keys stay out of the code:
  Reminix adds each one only to the hosts you allow, and the script never
  sees it.

  Where a run needs a person's yes, Reminix asks for it before the run
  starts. Every run is on record, with its inputs, its output and who
  started it.

  When a run waits for your approval or fails, Reminix tells you in the
  app, by email or with a push notification to your phone.
- `reminix.run()` and `reminix.wait_for_run()` take `timeout=`, which
  limits each request they make, as on every other method. To limit the
  whole wait, use `asyncio.timeout()` with `AsyncReminix`. The run carries
  on when the wait stops.

### Changed

- The Python SDK now returns models, so you read a response's fields as attributes, such as `member.joined_at`.

  - `to_dict()` and `to_json()` give a response back with the API's own field names. A field or value the API adds later is kept and never raises an error.
  - A list returns its first page, and a `for` loop over it goes through every item. With the async client, `await` gives the first page and `async for` every item.
  - Every method takes `idempotency_key=`, `extra_headers=` and `timeout=`, in place of `request_options`.
  - A failure raises a class for its status, such as `NotFoundError` or `RateLimitError`. Each is an `APIError` with `status_code`, `code`, `message`, `request_id`, `details` and `docs`. A network failure raises `APIConnectionError`, and a timeout `APITimeoutError`.
  - The client takes `base_url=` and `default_headers=`, and reads the base URL from the environment too. An async client also closes with `await client.close()`.
  - When the API asks to wait before a retry, the SDK now waits up to 60 seconds.
- A request that clashes with what already exists now answers
  `409 conflict`, which was `400 invalid_request`. That covers a script
  slug or an environment name already taken, a field set in the script's
  reminix.json, running an archived script, and cancelling a run that
  has ended. In the SDKs it's a `ConflictError`.
- A file's bytes are now at `GET /v1/files/{fileId}/content`, which was
  `/download`. In the SDKs it's `files.content(fileId)`. The CLI keeps
  `reminix files download`.
- Every list now pages the same way. A script's versions, schedules,
  triggers and trigger calls, and the workspace's secrets and environments,
  take `limit` and `cursor` and answer `{ items, nextCursor }`, as runs and
  files already did. A trigger's calls are no longer cut at the last 20.
- The run helpers follow each SDK's own conventions.

  In Python, `reminix.run()`, `reminix.wait_for_run()` and
  `reminix.upload_file()` return models, so you read `run.output` and
  `file.id`. They take `idempotency_key=`, `extra_headers=` and `timeout=`
  like every other method. How often they check a run is now
  `poll_interval=`, in seconds.

  In TypeScript, it's `pollInterval`, in milliseconds.

  In both, `waitForRun` and `wait_for_run` take a run or its id. A
  `RunError` is now a `ReminixError`, so catching the SDK's base error
  catches it too.
- A script's `stats` now name their period in full: `runsLast30Days` and
  `peopleLast30Days`, which were `runs30d` and `people30d`.
- A secret's value is now saved at its own address:
  `PUT /v1/secrets/{name}/values/{environment}`, the same address that
  removes it. In the SDKs it's `secretValues.set(name, environment, …)`.
  Whether scripts can read a secret as an environment variable is set on
  the secret itself, with `PATCH /v1/secrets/{name}` (`secrets.update`).
  `reminix secrets set` works as before, and `--no-allow-env-var` now
  turns that off again.
- A file's size is now `sizeBytes`, which was `size`. The file details a
  script reads from its inputs JSON say `sizeBytes` too.
- Listing a webhook trigger's calls is now `triggerCalls.list()` in the
  TypeScript SDK, `trigger_calls.list()` in Python, `reminix trigger-calls
  list` in the CLI and the `trigger_calls_list` tool in the MCP server. It
  was `triggers.calls`. The route is unchanged.
- A script's name, description and tags now belong to its `reminix.json`
  when the file sets them. Each upload sets them from the file, and they
  can't be changed in the app or with `PATCH /v1/scripts/{slug}`. The app
  shows such tags as "Set in reminix.json". To change one, edit the file
  and publish again, or remove it from the file to manage it in the app.

  A script's new `setInFile` field lists the settings its `reminix.json`
  sets.

  An AI agent changing a script through the MCP server gets the same
  answer.

## 1.0.0rc10 (2026-11-18)

No user-facing changes.

## 1.0.0rc9 (2026-11-14)

No user-facing changes.

## 1.0.0rc8 (2026-11-13)

No user-facing changes.

## 1.0.0rc7 (2026-11-12)

No user-facing changes.

## 1.0.0rc6 (2026-11-07)

No user-facing changes.

## 1.0.0rc5 (2026-11-07)

No user-facing changes.

## 1.0.0rc4 (2026-10-19)

No user-facing changes.

## 1.0.0rc3 (2026-10-16)

No user-facing changes.

## 1.0.0rc2 (2026-10-16)

No user-facing changes.

## 1.0.0rc1 (2026-10-16)

No user-facing changes.
