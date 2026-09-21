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
            env_file.write_text(
                "OAR_TUSHARE_TOKEN=file-token\n",
                encoding="utf-8",
            )
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
