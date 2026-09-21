# Python Environment and Secrets Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the futures collector in a project-local Python environment while loading its Tushare credential from an ignored `.env` file.

**Architecture:** `期货/config.py` remains the configuration boundary used by the collector. A small `load_tushare_config()` function merges process environment variables with values from the repository-root `.env`, validates the token, and exports the existing constants so callers remain unchanged.

**Tech Stack:** Python 3, `venv`, `unittest`, `python-dotenv`, Tushare, pandas

---

### Task 1: Define Configuration Behavior with Tests

**Files:**
- Create: `tests/test_config.py`
- Modify: `期货/config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py` with tests that load a temporary env file, verify process-environment precedence, and verify a clear error for a missing token:

```python
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "期货"))

from config import load_tushare_config


class TushareConfigTests(unittest.TestCase):
    def test_loads_values_from_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "OAR_TUSHARE_TOKEN=file-token\n"
                "OAR_TUSHARE_HTTP_URL=https://example.test\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                token, url = load_tushare_config(env_file)

        self.assertEqual(token, "file-token")
        self.assertEqual(url, "https://example.test")

    def test_process_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("OAR_TUSHARE_TOKEN=file-token\n", encoding="utf-8")
            environment = {
                "OAR_TUSHARE_TOKEN": "process-token",
                "OAR_TUSHARE_HTTP_URL": "https://process.test",
            }
            with patch.dict(os.environ, environment, clear=True):
                token, url = load_tushare_config(env_file)

        self.assertEqual(token, "process-token")
        self.assertEqual(url, "https://process.test")

    def test_missing_token_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OAR_TUSHARE_TOKEN"):
                    load_tushare_config(env_file)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m unittest tests/test_config.py -v`

Expected: import fails because `load_tushare_config` does not exist.

- [ ] **Step 3: Implement the minimal loader**

Update the start of `期货/config.py`:

```python
import os
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TUSHARE_HTTP_URL = "https://tuaremax.top"


def load_tushare_config(env_path=PROJECT_ROOT / ".env"):
    file_values = dotenv_values(env_path)
    token = os.environ.get("OAR_TUSHARE_TOKEN") or file_values.get("OAR_TUSHARE_TOKEN")
    http_url = (
        os.environ.get("OAR_TUSHARE_HTTP_URL")
        or file_values.get("OAR_TUSHARE_HTTP_URL")
        or DEFAULT_TUSHARE_HTTP_URL
    )
    if not token:
        raise RuntimeError(
            "Missing OAR_TUSHARE_TOKEN. Set it in the project .env file "
            "or in the process environment."
        )
    return token, http_url


TUSHARE_TOKEN, TUSHARE_HTTP_URL = load_tushare_config()
```

Keep the existing directory constants below this block.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv/bin/python -m unittest tests/test_config.py -v`

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

Skip: `/Users/yyf/期货` is not a Git repository.

### Task 2: Isolate Dependencies and Secrets

**Files:**
- Create: `.env`
- Create: `.gitignore`
- Modify: `.env.example`
- Modify: `期货/requirements.txt`

- [ ] **Step 1: Add the explicit configuration dependency**

Append `python-dotenv>=1.0` to `期货/requirements.txt`.

- [ ] **Step 2: Create the local environment**

Run: `python3 -m venv .venv`

Expected: `.venv/bin/python` exists.

- [ ] **Step 3: Install declared packages**

Run: `.venv/bin/python -m pip install -r 期货/requirements.txt`

Expected: installation completes and `.venv/bin/python -c 'import tushare, pandas, dotenv'` exits successfully.

- [ ] **Step 4: Move local values into `.env`**

Create `.env` with the existing token and endpoint under these names:

```dotenv
OAR_TUSHARE_TOKEN=<existing local token>
OAR_TUSHARE_HTTP_URL=https://tuaremax.top
```

Keep `.env.example` safe:

```dotenv
OAR_TUSHARE_TOKEN=
OAR_TUSHARE_HTTP_URL=https://tuaremax.top
```

- [ ] **Step 5: Ignore local and generated state**

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
.DS_Store
期货/data/
期货/logs/
```

- [ ] **Step 6: Commit**

Skip: `/Users/yyf/期货` is not a Git repository.

### Task 3: Verify the Installed Application

**Files:**
- Modify: `期货/README.md`

- [ ] **Step 1: Document environment setup and execution**

Update the README commands to create `.venv`, install requirements, create `.env` from `.env.example`, and run `../.venv/bin/python fetch_futures_data.py` from the `期货` directory.

- [ ] **Step 2: Run the full local test suite**

Run: `.venv/bin/python -m unittest discover -s tests -v`

Expected: all configuration tests pass.

- [ ] **Step 3: Run the collector smoke test**

Run: `../.venv/bin/python fetch_futures_data.py` from `/Users/yyf/期货/期货`.

Expected: the API returns code 0 through Tushare and prints a non-zero row count for DCE futures on `20260908`.

- [ ] **Step 4: Verify the secret is absent from non-ignored source files**

Run a literal search for the previous token across `期货/config.py`, `.env.example`, `期货/README.md`, and `docs/`.

Expected: no matches.

- [ ] **Step 5: Commit**

Skip: `/Users/yyf/期货` is not a Git repository.
