import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config as config_module


class TestProviderConfiguration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.old_provider_path = config_module.PROVIDER_SETTINGS_PATH
        self.old_runtime_path = config_module.RUNTIME_SETTINGS_PATH
        config_module.PROVIDER_SETTINGS_PATH = self.tmp_path / "provider_settings.json"
        config_module.RUNTIME_SETTINGS_PATH = self.tmp_path / "runtime_settings.json"

    def tearDown(self):
        config_module.PROVIDER_SETTINGS_PATH = self.old_provider_path
        config_module.RUNTIME_SETTINGS_PATH = self.old_runtime_path
        self.tmp.cleanup()

    def test_default_provider_is_ollama_qwen35(self):
        with patch.dict("os.environ", {}, clear=True):
            defaults = config_module._provider_defaults_from_env()
        self.assertIn("ollama", defaults)
        self.assertEqual(defaults["ollama"].model, "qwen3.5:latest")
        self.assertEqual(defaults["ollama"].provider_type, "ollama")

    def test_upsert_default_keeps_single_default(self):
        cfg = config_module.IsaacConfig()
        provider = cfg.upsert_provider(
            {
                "provider_id": "custom-openai",
                "display_name": "Custom OpenAI",
                "provider_type": "openai_compat",
                "base_url": "https://example.invalid/v1/chat/completions",
                "model": "gpt-test",
                "enabled": True,
                "is_default": True,
                "timeout": 30,
                "rpm": 10,
                "tpm": 20000,
            }
        )
        self.assertEqual(provider["provider_id"], "custom-openai")
        defaults = [p.provider_id for p in cfg.providers.values() if p.is_default]
        self.assertEqual(defaults, ["custom-openai"])
        self.assertEqual(cfg.relay.primary_provider, "custom-openai")

    def test_provider_persistence_roundtrip(self):
        cfg = config_module.IsaacConfig()
        cfg.upsert_provider(
            {
                "provider_id": "backup-ollama",
                "display_name": "Backup Ollama",
                "provider_type": "ollama",
                "base_url": "http://127.0.0.1:11434/api/chat",
                "model": "qwen3.5:latest",
                "enabled": True,
                "is_default": False,
                "timeout": 120,
                "rpm": 500,
                "tpm": 300000,
            }
        )

        reloaded = config_module.IsaacConfig()
        self.assertIn("backup-ollama", reloaded.providers)
        self.assertEqual(reloaded.providers["backup-ollama"].provider_type, "ollama")
        self.assertEqual(reloaded.providers["backup-ollama"].model, "qwen3.5:latest")


if __name__ == "__main__":
    unittest.main()
