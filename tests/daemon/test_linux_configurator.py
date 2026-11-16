from p2pvpn_daemon.configurator.linux import LinuxSystemConfigurator
from p2pvpn_common.errors import InterfaceError


class FakeRunner:
    def __init__(self, fail_ethtool: bool = False):
        self.commands: list[str] = []
        self.fail_ethtool = fail_ethtool

    def __call__(self, cmd: str) -> int:
        self.commands.append(cmd)
        if self.fail_ethtool and cmd.startswith("ethtool"):
            return 1
        return 0


def test_configure_issues_expected_commands():
    runner = FakeRunner()
    cfg = LinuxSystemConfigurator(run_command=runner)
    cfg.configure("tap0", "10.0.0.1", 24, 1420)

    assert "ip link set tap0 mtu 1420" in runner.commands
    assert "ip link set tap0 up" in runner.commands
    assert "ip addr replace 10.0.0.1/24 dev tap0" in runner.commands
    assert any("ethtool -K tap0" in c for c in runner.commands)
    assert any("iptables -t mangle -A OUTPUT" in c for c in runner.commands)
    assert any("iptables -t mangle -A INPUT" in c for c in runner.commands)
    assert "--set-mss 1380" in " ".join(runner.commands)  # 1420 - 40


def test_configure_fails_on_ip_command_error():
    class FailingRunner:
        def __call__(self, cmd: str) -> int:
            return 1 if cmd.startswith("ip ") else 0

    cfg = LinuxSystemConfigurator(run_command=FailingRunner())
    try:
        cfg.configure("tap0", "10.0.0.1", 24, 1420)
        raise AssertionError("should have raised")
    except InterfaceError:
        pass


def test_cleanup_flushes_and_removes_rules():
    runner = FakeRunner()
    cfg = LinuxSystemConfigurator(run_command=runner)
    cfg.cleanup("tap0", 1420)
    assert any("iptables -t mangle -D" in c for c in runner.commands)
    assert "ip addr flush dev tap0" in " ".join(runner.commands)
