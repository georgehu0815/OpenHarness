"""Tests for Azure OpenAI provider detection."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from openharness.config.settings import Settings, default_provider_profiles


class TestDetectAzureProvider:
    def _azure_settings(self) -> Settings:
        return Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()

    def test_detect_provider_returns_azure_name(self):
        from openharness.api.provider import detect_provider
        info = detect_provider(self._azure_settings())
        assert info.name == "azure_openai"

    def test_detect_provider_auth_kind_is_identity(self):
        from openharness.api.provider import detect_provider
        info = detect_provider(self._azure_settings())
        assert info.auth_kind == "azure_identity"

    def test_auth_status_returns_identity_string(self):
        from openharness.api.provider import auth_status
        status = auth_status(self._azure_settings())
        assert "identity" in status.lower()


class TestClientFactory:
    def test_azure_settings_produce_azure_client(self):
        from openharness.config.settings import Settings, default_provider_profiles
        from openharness.ui.runtime import _resolve_api_client_from_settings
        from openharness.api.azure_provider import AzureOpenAIClient
        import os

        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()

        with patch("openharness.api.azure_provider.DefaultAzureCredential"), \
             patch("openharness.api.azure_provider.get_bearer_token_provider"), \
             patch.dict(os.environ, {"ENDPOINT_URL": "https://test.openai.azure.com/"}):
            client = _resolve_api_client_from_settings(settings)

        assert isinstance(client, AzureOpenAIClient)
