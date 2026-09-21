# Python Environment and Secrets Migration

## Goal

Make the futures data collector runnable without installing packages globally, and remove the Tushare credential from tracked Python source.

## Design

- Create a project-local `.venv` with the available Python interpreter.
- Install the packages declared in `期货/requirements.txt` into that environment.
- Add `python-dotenv` as an explicit dependency.
- Load environment variables from the repository-root `.env` in `期货/config.py`.
- Require `OAR_TUSHARE_TOKEN`; fail early with a clear message when it is absent.
- Read `OAR_TUSHARE_HTTP_URL` from the environment, with the existing endpoint as the default so current behavior remains compatible.
- Store the current local credential in `.env`, while `.env.example` contains only safe placeholders.
- Add `.gitignore` entries for `.env`, `.venv`, generated data, logs, caches, and macOS metadata.

## Data Flow

At import time, `config.py` loads the root `.env`, reads the Tushare settings, validates the token, and exports the same constants consumed by `fetch_futures_data.py`. No call-site changes are required.

## Error Handling

Missing credentials raise a configuration error before an API request is attempted. Network and API errors continue to use the collector's existing retry and logging behavior.

## Verification

- A configuration test proves that values are loaded from an isolated `.env` and that a missing token produces a useful error.
- The project script runs with `.venv/bin/python`.
- A read-only `fut_daily` request for DCE on `20260908` returns data.

## Non-goals

- No historical bulk download.
- No database setup.
- No changes to the existing collection workflow or output schema.
