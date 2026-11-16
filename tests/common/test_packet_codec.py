from p2pvpn_common.protocol.packet import decode, encode_data, encode_hello
from p2pvpn_common.constants import TYPE_DATA, TYPE_HELLO


def test_encode_data_roundtrip():
    frame = b"\x01\x02\x03"
    pkt = encode_data(frame)
    ptype, payload = decode(pkt)
    assert ptype == TYPE_DATA
    assert payload == frame


def test_encode_hello_has_no_payload():
    ptype, payload = decode(encode_hello())
    assert ptype == TYPE_HELLO
    assert payload == b""


def test_decode_rejects_garbage():
    assert decode(b"not a vpn packet") == (None, b"")
    assert decode(b"") == (None, b"")
    assert decode(b"P2PL2") == (None, b"")  # magic but no type byte


def test_decode_rejects_wrong_magic():
    assert decode(b"XXXXX\x01payload") == (None, b"")
