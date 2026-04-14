"""Tests for Azure OpenAI settings integration."""

from __future__ import annotations

import pytest
from openharness.config.settings import (
    Settings,
    default_provider_profiles,
    auth_source_provider_name,
)


class TestAzureProfile:
    def test_azure_openai_profile_exists(self):
        profiles = default_provider_profiles()
        assert "azure-openai" in profiles

    def test_azure_openai_profile_fields(self):
        profile = default_provider_profiles()["azure-openai"]
        assert profile.provider == "azure_openai"
        assert profile.api_format == "openai"
        assert profile.auth_source == "azure_identity"
        assert profile.default_model == "gpt-5.4-mini"

    def test_auth_source_provider_name_azure(self):
        result = auth_source_provider_name("azure_identity")
        assert result == "azure_openai"


class TestResolveAuthAzureIdentity:
    def test_resolve_auth_returns_identity_sentinel(self):
        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()
        auth = settings.resolve_auth()
        assert auth.auth_kind == "azure_identity"
        assert auth.provider == "azure_openai"
        assert auth.value == "identity"

    def test_resolve_auth_does_not_raise_for_azure(self):
        """Must not raise ValueError trying to look up a stored credential."""
        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()
        auth = settings.resolve_auth()
        assert auth is not None


class TestDotenvAndEnvOverride:
    def test_active_profile_env_override(self, monkeypatch):
        """OPENHARNESS_ACTIVE_PROFILE env var should override the active profile."""
        monkeypatch.setenv("OPENHARNESS_ACTIVE_PROFILE", "azure-openai")
        from openharness.config.settings import Settings, _apply_env_overrides, default_provider_profiles
        base = Settings(profiles=default_provider_profiles())
        result = _apply_env_overrides(base)
        assert result.active_profile == "azure-openai"
