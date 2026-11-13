"""Policy invariants and hostile kernel readback; real enforcement runs in Docker."""

import copy
import json

import pytest

from nima.egress.rules import NetworkError, decode_ruleset, policy_objects, policy_payload


def kernel_dump() -> bytes:
    rows = copy.deepcopy(policy_objects())
    for number, row in enumerate(rows, 1):
        kind, body = next(iter(row.items()))
        body["handle"] = number
        if kind == "counter":
            body.update(packets=number, bytes=number * 64)
    return json.dumps(
        {
            "nftables": [
                {
                    "metainfo": {
                        "version": "1.0.6",
                        "release_name": "Lester Gooch #5",
                        "json_schema_version": 1,
                    }
                },
                *rows,
            ]
        }
    ).encode()


def test_only_observer_and_exact_workload_gateway_are_accepted() -> None:
    objects = policy_objects()
    (chain,) = [row["chain"] for row in objects if "chain" in row]
    assert chain["type"] == "filter" and chain["hook"] == "output"
    assert chain["policy"] == "drop" and chain["prio"] == 0
    rules = [row["rule"]["expr"] for row in objects if "rule" in row]
    accepted = [rule for rule in rules if {"accept": None} in rule]
    assert len(accepted) == 2
    assert accepted[0] == [
        {"match": {"op": "==", "left": {"meta": {"key": "skuid"}}, "right": 10002}},
        {"counter": "observer"},
        {"accept": None},
    ]
    assert accepted[1][0] == {
        "match": {"op": "==", "left": {"meta": {"key": "skuid"}}, "right": 10001}
    }
    assert {
        "match": {
            "op": "==",
            "left": {"payload": {"protocol": "ip", "field": "daddr"}},
            "right": "172.30.240.2",
        }
    } in accepted[1]
    assert {
        "match": {
            "op": "==",
            "left": {"payload": {"protocol": "tcp", "field": "dport"}},
            "right": 3128,
        }
    } in accepted[1]
    assert rules[-1] == [{"counter": "other"}, {"drop": None}]
    assert not any(
        word in policy_payload().decode() for word in ("established", "loopback", "ct state")
    )
    commands = json.loads(policy_payload())["nftables"]
    assert set(commands[0]) == {"create"}
    assert all(set(command) == {"add"} for command in commands[1:])


def test_readback_identity_ignores_handles_and_counter_values_only() -> None:
    first = decode_ruleset(kernel_dump())
    value = json.loads(kernel_dump())
    for row in value["nftables"]:
        for kind, body in row.items():
            if kind != "metainfo":
                body["handle"] += 100
            if kind == "counter":
                body["packets"] += 10
                body["bytes"] += 640
    second = decode_ruleset(json.dumps(value).encode())
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert second.packets("gateway") == first.packets("gateway") + 10
    with pytest.raises(NetworkError):
        second.packets("unknown")


@pytest.mark.parametrize(
    "fault",
    [
        "accept_all",
        "wrong_uid",
        "missing_rule",
        "extra_rule",
        "policy",
        "counter",
        "float_uid",
        "bool_priority",
        "duplicate",
        "unknown",
        "large",
    ],
)
def test_modified_or_incomplete_policy_cannot_attest_enforcement(fault: str) -> None:
    raw = kernel_dump()
    value = json.loads(raw)
    rows = value["nftables"]
    rules = [row["rule"] for row in rows if "rule" in row]
    if fault == "accept_all":
        rules[0]["expr"] = [{"accept": None}]
    elif fault == "wrong_uid":
        rules[1]["expr"][0]["match"]["right"] = 0
    elif fault == "missing_rule":
        rows.pop()
    elif fault == "extra_rule":
        rows.append({"rule": copy.deepcopy(rules[0])})
    elif fault == "policy":
        next(row["chain"] for row in rows if "chain" in row)["policy"] = "accept"
    elif fault == "counter":
        next(row["counter"] for row in rows if "counter" in row)["packets"] = True
    elif fault == "float_uid":
        rules[1]["expr"][0]["match"]["right"] = 10001.0
    elif fault == "bool_priority":
        next(row["chain"] for row in rows if "chain" in row)["prio"] = False
    elif fault == "unknown":
        rows.append({"table": {"family": "inet", "name": "unowned"}})
    raw = (
        b'{"nftables":[],"nftables":[]}'
        if fault == "duplicate"
        else b"x" * 65537
        if fault == "large"
        else json.dumps(value).encode()
    )
    with pytest.raises(NetworkError):
        decode_ruleset(raw)


def test_numeric_protocol_display_preserves_semantics_but_other_protocols_fail() -> None:
    value = json.loads(kernel_dump())
    for row in value["nftables"]:
        if "rule" in row:
            for expression in row["rule"]["expr"]:
                match = expression.get("match", {})
                if match.get("left") == {"meta": {"key": "l4proto"}}:
                    match["right"] = {"tcp": 6, "udp": 17}[match["right"]]
    assert (
        decode_ruleset(json.dumps(value).encode()).fingerprint
        == decode_ruleset(kernel_dump()).fingerprint
    )
    rules = [row["rule"] for row in value["nftables"] if "rule" in row]
    rules[1]["expr"][1]["match"]["right"] = 1
    with pytest.raises(NetworkError):
        decode_ruleset(json.dumps(value).encode())


def test_nft_implicit_transport_selector_is_equivalent_only_with_a_typed_port() -> None:
    value = json.loads(kernel_dump())
    rules = [row["rule"] for row in value["nftables"] if "rule" in row]
    for row in rules:
        typed = [
            expression.get("match", {}).get("left", {}).get("payload", {})
            for expression in row["expr"]
        ]
        if any(
            item.get("protocol") in {"tcp", "udp"} and item.get("field") == "dport"
            for item in typed
        ):
            row["expr"] = [
                expression
                for expression in row["expr"]
                if expression.get("match", {}).get("left") != {"meta": {"key": "l4proto"}}
            ]
    assert (
        decode_ruleset(json.dumps(value).encode()).fingerprint
        == decode_ruleset(kernel_dump()).fingerprint
    )
    rules[2]["expr"] = [
        expression
        for expression in rules[2]["expr"]
        if expression.get("match", {}).get("left") != {"meta": {"key": "l4proto"}}
    ]
    with pytest.raises(NetworkError):
        decode_ruleset(json.dumps(value).encode())
