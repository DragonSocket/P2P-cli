from p2pvpn_daemon.core.peer_manager import PeerManager, PeerManagerConfig


def make_mgr(stale=15.0, dead=30.0, hb=5.0) -> PeerManager:
    return PeerManager(PeerManagerConfig(stale, dead, hb))


def test_new_peer_is_pending():
    mgr = make_mgr()
    peer = mgr.add("1.2.3.4", 5555)
    assert mgr.status(peer, now=100.0) == "pending"


def test_touch_makes_peer_alive():
    mgr = make_mgr()
    peer = mgr.touch("1.2.3.4", 5555, now=100.0)
    assert mgr.status(peer, now=101.0) == "alive"


def test_stale_after_stale_timeout():
    mgr = make_mgr(stale=15.0, dead=30.0)
    peer = mgr.touch("1.2.3.4", 5555, now=100.0)
    assert mgr.status(peer, now=116.0) == "stale"


def test_dead_after_dead_timeout():
    mgr = make_mgr(stale=15.0, dead=30.0)
    peer = mgr.touch("1.2.3.4", 5555, now=100.0)
    assert mgr.status(peer, now=131.0) == "dead"


def test_dead_peers_are_pruned_but_stale_are_not():
    mgr = make_mgr(stale=15.0, dead=30.0)
    mgr.touch("a.host", 1, now=100.0)   # age 21 → stale at now=121
    mgr.touch("b.host", 2, now=90.0)    # age 31 → dead at now=121
    removed = mgr.prune_dead(now=121.0)
    assert len(removed) == 1
    assert removed[0].host == "b.host"
    assert mgr.get("a.host", 1) is not None


def test_sendable_includes_pending_alive_stale():
    mgr = make_mgr(stale=15.0, dead=30.0)
    mgr.add("pending.host", 1)
    mgr.touch("alive.host", 2, now=120.0)
    mgr.touch("stale.host", 3, now=110.0)
    mgr.touch("dead.host", 4, now=90.0)
    sendable = {p.host for p in mgr.sendable(now=121.0)}
    assert sendable == {"pending.host", "alive.host", "stale.host"}


def test_counts():
    mgr = make_mgr()
    mgr.add("p", 1)
    mgr.touch("a", 2, now=100.0)
    counts = mgr.counts(now=101.0)
    assert counts == {"alive": 1, "pending": 1, "stale": 0, "dead": 0, "total": 2}
