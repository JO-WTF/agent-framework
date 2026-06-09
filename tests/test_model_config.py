import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from app import config


class ModelConfigTests(unittest.TestCase):
    def setUp(self):
        self.previous_settings = config._llm_settings
        self.previous_client = config._active_llm_client
        config._llm_settings = None
        config._active_llm_client = None

    def tearDown(self):
        config._llm_settings = self.previous_settings
        config._active_llm_client = self.previous_client

    def test_update_llm_settings_applies_provider_defaults_and_redacts_key(self):
        settings = config.update_llm_settings(
            {
                "provider": "deepseek",
                "model_name": "deepseek-reasoner",
                "base_url": "",
                "api_key": "secret-token",
            }
        )

        self.assertEqual(settings["provider"], "deepseek")
        self.assertEqual(settings["model_name"], "deepseek-reasoner")
        self.assertEqual(settings["base_url"], "https://api.deepseek.com/v1")
        self.assertTrue(settings["api_key_set"])
        self.assertNotIn("api_key", settings)

    def test_update_llm_settings_rejects_empty_model_name(self):
        with self.assertRaises(ValueError):
            config.update_llm_settings({"provider": "openai", "model_name": ""})

    def test_get_llm_settings_does_not_require_model_client_initialization(self):
        with patch.dict(os.environ, {"LLM_MODEL_NAME": "", "LLM_API_KEY": "dummy"}, clear=False):
            settings = config.get_llm_settings()

        self.assertIn("providers", settings)
        self.assertNotIn("api_key", settings)


if __name__ == "__main__":
    unittest.main()
