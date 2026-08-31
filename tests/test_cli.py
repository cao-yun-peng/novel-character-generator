import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from novel_character_generator.__main__ import _load_deepseek_env_file, _read_utf8_text, main


class CliTests(unittest.TestCase):
    def test_utf8_file_reader_preserves_crlf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            path.write_bytes("甲\r\n乙\n丙".encode("utf-8"))
            self.assertEqual(_read_utf8_text(path), "甲\r\n乙\n丙")

    def test_probe_without_key_fails_before_network_and_does_not_echo_text(self) -> None:
        error = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(error):
            exit_code = main(
                [
                    "probe-deepseek-m1",
                    "--text",
                    "不应出现在错误中的正文",
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertIn("ProviderConfigurationError", error.getvalue())
        self.assertIn("DEEPSEEK_API_KEY", error.getvalue())
        self.assertNotIn("不应出现在错误中的正文", error.getvalue())

    def test_m2_env_file_loads_only_deepseek_names_without_overriding_process_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "DEEPSEEK_API_KEY=file-key\nDEEPSEEK_MODEL='file-model'\nOTHER_SECRET=ignored\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "process-key"},
                clear=True,
            ):
                _load_deepseek_env_file(path)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "process-key")
                self.assertEqual(os.environ["DEEPSEEK_MODEL"], "file-model")
                self.assertNotIn("OTHER_SECRET", os.environ)


if __name__ == "__main__":
    unittest.main()
