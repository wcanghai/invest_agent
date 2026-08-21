# Repository Guidance

## Project identity

This repository is a Python investment-data application for local TDX market data,
external market APIs, durable daily reports, and a browser-based report viewer.

## Conventions

- Use Python 3.11+ and type annotations for public functions.
- User-facing documentation and messages are written in Chinese; code identifiers are English.
- Keep data acquisition, report rendering, persistence, and HTTP delivery in separate modules.
- Never commit generated reports, caches, SQLite databases, credentials, or Python bytecode.

## Lifecycle

Use this order for non-trivial changes: bootstrap, requirements, design, planning,
implementation, verification, release. Store artifacts under:

- `docs/requirements/`
- `docs/design/`
- `docs/adr/`
- `docs/tasks/`
- `docs/release/`

## Implementation and verification

- Preserve command-line entry points when adding web or service layers.
- Isolate live TDX/network access behind injectable callables so tests stay offline.
- Add tests for persistence uniqueness, first-request generation, and rendered output.
- Run `python -m pytest -q -p no:cacheprovider` and `git diff --check` before handoff.
- Do not expose the local server publicly or add authentication assumptions without an explicit requirement.
