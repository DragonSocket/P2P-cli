import pytest

from p2pvpn_common.errors import ConfigError
from p2pvpn_common.models.vpn_config import PeerConfig, VPNConfig


def test_peer_config_parse():
    p = PeerConfig.parse("203.0.113.50:5555")
    assert p.host == "203.0.113.50"
    assert p.port == 5555


def test_peer_config_parse_invalid():
    with pytest.raises(ConfigError):
        PeerConfig.parse("no-port")
    with pytest.raises(ConfigError):
        PeerConfig.parse("host:abc")


def test_config_from_dict():
    cfg = VPNConfig.from_dict({
        "local_ip": "10.0.0.1",
        "listen_port": 5555,
        "peers": [{"host": "1.2.3.4", "port": 5555}],
    })
    assert cfg.mtu == 1420
    assert cfg.peers[0].host == "1.2.3.4"
    assert cfg.stale_timeout == 15.0


def test_config_validation_rejects_bad_port():
    with pytest.raises(ConfigError):
        VPNConfig.from_dict({"listen_port": 0})


def test_config_roundtrip_dict():
    cfg = VPNConfig(local_ip="10.0.0.5", listen_port=7777)
    again = VPNConfig.from_dict(cfg.to_dict())
    assert again.local_ip == "10.0.0.5"
    assert again.listen_port == 7777
