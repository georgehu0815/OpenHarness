from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.manager import ChannelManager
from openharness.channels.impl.webui import WebUIChannel
from openharness.config.schema import Config, WebUIConfig


def test_channel_manager_registers_webui_when_enabled():
    config = Config()
    config.channels.webui = WebUIConfig(enabled=True, port=8080, allow_from=["*"])
    bus = MessageBus()
    manager = ChannelManager(config, bus)
    assert "webui" in manager.channels
    assert isinstance(manager.channels["webui"], WebUIChannel)


def test_channel_manager_skips_webui_when_disabled():
    config = Config()
    config.channels.webui = WebUIConfig(enabled=False)
    bus = MessageBus()
    manager = ChannelManager(config, bus)
    assert "webui" not in manager.channels
