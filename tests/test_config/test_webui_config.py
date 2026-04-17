from openharness.config.schema import Config, WebUIConfig


def test_webui_config_defaults():
    cfg = WebUIConfig()
    assert cfg.port == 8080
    assert cfg.allow_from == ["*"]
    assert cfg.cors_origins == []
    assert cfg.enabled is False


def test_channel_configs_has_webui_field():
    config = Config()
    assert hasattr(config.channels, "webui")
    assert isinstance(config.channels.webui, WebUIConfig)


def test_webui_config_enabled_via_dict():
    cfg = WebUIConfig(enabled=True, port=9090, cors_origins=["http://localhost:5173"])
    assert cfg.enabled is True
    assert cfg.port == 9090
    assert "http://localhost:5173" in cfg.cors_origins
