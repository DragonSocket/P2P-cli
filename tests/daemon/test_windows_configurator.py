"""Windows configurator is tested by capturing argv — nothing touches the OS.
Same DI seam as the Linux configurator: `run` is injected."""
from p2pvpn_daemon.configurator.windows import WindowsSystemConfigurator


class FakeRunner:
    def __init__(self):
        self.argv: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.argv.append(list(cmd))
        return None


def test_configure_sets_ip_mtu_and_disables_offload():
    runner = FakeRunner()
    cfg = WindowsSystemConfigurator(run=runner)
    cfg.configure("tap0", "10.0.0.1", 24, 1420)

    joined = [" ".join(a) for a in runner.argv]
    expected = ("netsh interface ipv4 set address name=tap0 source=static "
                "address=10.0.0.1 mask=255.255.255.0")
    assert expected in joined
    assert "netsh interface ipv4 set subinterface tap0 mtu=1420 store=active" in joined
    assert any("Disable-NetAdapterChecksumOffload" in a for a in joined)
    assert any("Disable-NetAdapterLso" in a for a in joined)


def test_prefix_other_than_24_yields_correct_mask():
    runner = FakeRunner()
    WindowsSystemConfigurator(run=runner).configure("tap0", "10.0.0.1", 16, 1420)
    assert "mask=255.255.255.255" not in " ".join(" ".join(a) for a in runner.argv)
    assert "mask=255.255.0.0" in " ".join(" ".join(a) for a in runner.argv)


def test_cleanup_resets_interface():
    runner = FakeRunner()
    WindowsSystemConfigurator(run=runner).cleanup("tap0", 1420)
    assert runner.argv == [["netsh", "interface", "ipv4", "reset", "tap0"]]
