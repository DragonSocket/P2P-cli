"""Terminal rendering; no networking or domain mutations."""
import json


def render(value):
    if isinstance(value, dict) and "peers" in value:
        print(f"{value['name']} · {value['swarm']} · {value['ip']} · {value['uptime']}s")
        print(f"DHT replicated: {value['dht_published']}  discovery-only: {value['headless']}")
        rows = value["peers"]
        print(f"{'NAME':32} {'IP':15} {'STATUS':8} ENDPOINT")
        for peer in rows:
            print(f"{peer['name']:32} {peer['ip']:15} {peer['status']:8} {peer['observed']}")
        print("Traffic:", json.dumps(value["traffic"]))
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False))
