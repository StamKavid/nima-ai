"""Fixed nftables 1.0.6 JSON policy and strict kernel readback.

https://manpages.debian.org/bookworm/libnftables1/libnftables-json.5.en.html
https://manpages.debian.org/bookworm/nftables/nft.8.en.html
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

TABLE = "nima_worker"
TARGETS = (
    ("direct_tcp", "tcp", "172.30.240.4", None),
    ("host_tcp", "tcp", "172.30.240.1", None),
    ("metadata_tcp", "tcp", "169.254.169.254", None),
    ("dns_udp", "udp", "172.30.240.4", 53),
    ("direct_udp", "udp", "172.30.240.4", 9001),
    ("quic_udp", "udp", "172.30.240.4", 443),
    ("stun_udp", "udp", "172.30.240.4", 3478),
)
COUNTERS = ("observer", "gateway", *(row[0] for row in TARGETS), "other")


class NetworkError(ValueError):
    """Fixed infrastructure codes; no raw tool output or configuration."""


def _match(protocol: str, field: str, value: object) -> dict[str, Any]:
    left = (
        {"meta": {"key": field}}
        if protocol == "meta"
        else {"payload": {"protocol": protocol, "field": field}}
    )
    return {"match": {"op": "==", "left": left, "right": value}}


def policy_objects() -> list[dict[str, Any]]:
    """External nft JSON schema; arguments cannot broaden the fixture policy."""
    common = {"family": "inet", "table": TABLE}
    observer = [_match("meta", "skuid", 10002), {"counter": "observer"}, {"accept": None}]
    gateway = [
        _match("meta", "skuid", 10001),
        _match("meta", "l4proto", "tcp"),
        _match("ip", "daddr", "172.30.240.2"),
        _match("tcp", "dport", 3128),
        {"counter": "gateway"},
        {"accept": None},
    ]
    rules = [observer, gateway]
    for name, protocol, address, port in TARGETS:
        match = [
            _match("meta", "skuid", 10001),
            _match("meta", "l4proto", protocol),
            _match("ip", "daddr", address),
        ]
        if port is not None:
            match.append(_match(protocol, "dport", port))
        rules.append([*match, {"counter": name}, {"drop": None}])
    rules.append([{"counter": "other"}, {"drop": None}])
    return [
        {"table": {"family": "inet", "name": TABLE}},
        *[{"counter": {**common, "name": name}} for name in COUNTERS],
        {
            "chain": {
                **common,
                "name": "output",
                "type": "filter",
                "hook": "output",
                "prio": 0,
                "policy": "drop",
            }
        },
        *[{"rule": {**common, "chain": "output", "expr": row}} for row in rules],
    ]


def policy_payload() -> bytes:
    return (
        json.dumps(
            {
                "nftables": [
                    {"create" if "table" in row else "add": row} for row in policy_objects()
                ]
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NetworkError("network_readback")
        result[key] = value
    return result


def nft_objects(raw: bytes) -> list[dict[str, Any]]:
    if not raw or len(raw) > 65536:
        raise NetworkError("network_readback")
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, UnicodeError):
        raise NetworkError("network_readback") from None
    if type(value) is not dict or set(value) != {"nftables"} or type(value["nftables"]) is not list:
        raise NetworkError("network_readback")
    rows = []
    seen_meta = False
    for row in value["nftables"]:
        if type(row) is not dict or len(row) != 1:
            raise NetworkError("network_readback")
        if "metainfo" in row:
            meta = row["metainfo"]
            if (
                seen_meta
                or type(meta) is not dict
                or set(meta) != {"version", "release_name", "json_schema_version"}
                or meta["version"] != "1.0.6"
                or type(meta["json_schema_version"]) is not int
                or meta["json_schema_version"] != 1
                or type(meta["release_name"]) is not str
            ):
                raise NetworkError("network_readback")
            seen_meta = True
        else:
            rows.append(row)
    if not seen_meta:
        raise NetworkError("network_readback")
    return rows


def _normalize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"table": [], "chain": [], "counter": {}, "rule": []}
    for row in rows:
        kind, original = next(iter(row.items()))
        if kind not in result or type(original) is not dict:
            raise NetworkError("network_policy")
        body = dict(original)
        handle = body.pop("handle", None)
        if handle is not None and (type(handle) is not int or handle < 0):
            raise NetworkError("network_policy")
        if kind == "counter":
            body.pop("packets", None)
            body.pop("bytes", None)
            name = body.get("name")
            if type(name) is not str or name in result["counter"]:
                raise NetworkError("network_policy")
            result["counter"][name] = body
        else:
            if kind == "rule" and type(body.get("expr")) is list:
                for expression in body["expr"]:
                    if type(expression) is not dict or type(expression.get("match")) is not dict:
                        continue
                    match = expression["match"]
                    if (
                        match.get("left") == {"meta": {"key": "l4proto"}}
                        and type(match.get("right")) is int
                    ):
                        match["right"] = {6: "tcp", 17: "udp"}.get(match["right"], match["right"])
            result[kind].append(body)
    return result


@dataclass(frozen=True, slots=True)
class NetworkSnapshot:
    fingerprint: str
    counters: tuple[tuple[str, int, int], ...]

    def packets(self, name: str) -> int:
        for key, packets, _ in self.counters:
            if key == name:
                return packets
        raise NetworkError("network_counter")


def _shape(policy: dict[str, Any]) -> list[list[str]]:
    """Fixed protocol/field labels and type names only; never values or names."""
    result = []
    for row in policy["rule"]:
        expressions = []
        for item in row.get("expr", []):
            if type(item) is not dict:
                expressions.append("invalid")
                continue
            match = item.get("match")
            if type(match) is dict and type(match.get("left")) is dict:
                left = match["left"]
                metadata = left.get("meta", {})
                payload = left.get("payload", {})
                if metadata.get("key") in {"skuid", "l4proto", "nfproto"}:
                    label = "meta:" + metadata["key"]
                elif payload.get("protocol") in {"ip", "tcp", "udp"} and payload.get("field") in {
                    "daddr",
                    "dport",
                }:
                    label = payload["protocol"] + ":" + payload["field"]
                else:
                    label = "unknown"
                expressions.append(label + ":" + type(match.get("right")).__name__)
            else:
                expressions.append(
                    next(
                        (name for name in ("counter", "accept", "drop") if name in item), "unknown"
                    )
                )
        result.append(expressions)
    return result


def decode_ruleset(raw: bytes) -> NetworkSnapshot:
    rows = nft_objects(raw)
    actual, expected = _normalize(rows), _normalize(policy_objects())
    try:
        encoded = json.dumps(actual, sort_keys=True, separators=(",", ":"), allow_nan=False)
        required = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError:
        raise NetworkError("network_policy") from None
    # JSON identity also distinguishes booleans/floats from integer UID/priority.
    if encoded != required:
        print(
            json.dumps(
                {
                    "version": "source-worker-rule-shape-v1",
                    "expected": _shape(expected),
                    "observed": _shape(actual),
                }
            )
        )
        raise NetworkError("network_policy")
    counters = []
    for row in rows:
        if "counter" not in row:
            continue
        value = row["counter"]
        if any(
            type(value.get(key)) is not int or not 0 <= value[key] < 2**64
            for key in ("packets", "bytes")
        ):
            raise NetworkError("network_counter")
        counters.append((value["name"], value["packets"], value["bytes"]))
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    return NetworkSnapshot(fingerprint, tuple(sorted(counters)))
