import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from fastapi.testclient import TestClient

from app import config
from app.web import app


class ModelConfigTests(unittest.TestCase):
    def test_normalize_llm_settings_applies_provider_defaults_and_keeps_key_server_side(self):
        settings = config.normalize_llm_settings(
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
        self.assertEqual(settings["api_key"], "secret-token")


    def test_provider_defaults_include_requested_models_and_urls(self):
        settings = config.normalize_llm_settings({"provider": "deepseek", "base_url": ""})
        self.assertEqual(settings["model_name"], "deepseek-v4-flash")
        self.assertEqual(settings["base_url"], "https://api.deepseek.com/v1")

        settings = config.normalize_llm_settings({"provider": "llamacpp", "base_url": ""})
        self.assertEqual(settings["model_name"], "qwen3.6:latest")
        self.assertEqual(settings["base_url"], "http://isc.ai.huawei.com:11434/v1")

    def test_redact_llm_settings_does_not_return_api_key(self):
        redacted = config.redact_llm_settings(
            {
                "provider": "deepseek",
                "model_name": "deepseek-reasoner",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "secret-token",
                "temperature": 0.1,
            }
        )

        self.assertTrue(redacted["api_key_set"])
        self.assertNotIn("api_key", redacted)

    def test_normalize_llm_settings_rejects_empty_model_name(self):
        with self.assertRaises(ValueError):
            config.normalize_llm_settings({"provider": "openai", "model_name": ""})

    def test_get_llm_settings_does_not_require_model_client_initialization(self):
        with patch.dict(os.environ, {"LLM_MODEL_NAME": "", "LLM_API_KEY": "dummy"}, clear=False):
            settings = config.get_llm_settings()

        self.assertIn("providers", settings)
        self.assertNotIn("api_key", settings)

    def test_model_config_endpoint_returns_server_defaults_only(self):
        client = TestClient(app)
        response = client.get("/api/model-config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("model_name", payload)
        self.assertNotIn("api_key", payload)
        self.assertEqual(payload["default_model_names"]["deepseek"], "deepseek-v4-flash")
        self.assertEqual(payload["default_model_names"]["llamacpp"], "qwen3.6:latest")
        self.assertEqual(payload["default_base_urls"]["llamacpp"], "http://isc.ai.huawei.com:11434/v1")

    def test_mapbox_config_endpoint_exposes_public_token_only(self):
        client = TestClient(app)
        env = {"MAPBOX_PUBLIC_TOKEN": "pk.public", "MAPBOX_ACCESS_TOKEN": "sk.secret"}
        with patch.dict(os.environ, env, clear=False):
            response = client.get("/api/mapbox-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True, "token": "pk.public"})
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_mapbox_config_endpoint_strips_env_token_whitespace(self):
        client = TestClient(app)
        env = {
            "MAPBOX_PUBLIC_TOKEN": "  pk.public-with-whitespace\n",
            "MAPBOX_ACCESS_TOKEN": "sk.secret",
        }
        with patch.dict(os.environ, env, clear=False):
            response = client.get("/api/mapbox-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True, "token": "pk.public-with-whitespace"})

    def test_mapbox_config_endpoint_rejects_non_public_fallback(self):
        client = TestClient(app)
        with patch.dict(os.environ, {"MAPBOX_PUBLIC_TOKEN": "", "MAPBOX_ACCESS_TOKEN": "sk.secret", "MAPBOX_API_KEY": ""}, clear=False):
            response = client.get("/api/mapbox-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": False, "token": ""})

    def test_model_config_endpoint_does_not_accept_server_writes(self):
        client = TestClient(app)
        response = client.post(
            "/api/model-config",
            json={"provider": "ollama", "model_name": "qwen3", "base_url": "", "api_key": "local"},
        )

        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
