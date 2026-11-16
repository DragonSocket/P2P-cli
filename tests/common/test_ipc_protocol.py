from p2pvpn_common.errors import IPCError
from p2pvpn_common.protocol.ipc import (
    IPCCommand,
    IPCRequest,
    IPCResponse,
    parse_request,
    parse_response,
)


def test_request_roundtrip():
    req = IPCRequest(command=IPCCommand.ADD_PEER, params={"peer": "1.2.3.4:5555"})
    parsed = parse_request(req.to_json())
    assert parsed == req


def test_response_roundtrip_success():
    resp = IPCResponse.ok({"running": True})
    parsed = parse_response(resp.to_json())
    assert parsed.status == "success"
    assert parsed.data == {"running": True}


def test_response_roundtrip_error():
    resp = IPCResponse.error("boom")
    parsed = parse_response(resp.to_json())
    assert parsed.status == "error"
    assert parsed.message == "boom"


def test_unknown_command_raises():
    try:
        parse_request('{"command": "REBOOT_THE_WORLD"}')
        raise AssertionError("should have raised")
    except IPCError:
        pass


def test_malformed_json_raises():
    try:
        parse_request("not json at all")
        raise AssertionError("should have raised")
    except IPCError:
        pass
