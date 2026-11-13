"""Fixed gateway policy and private bootstrap, not a replacement for Envoy validation."""

import json
from pathlib import Path

import pytest

from nima.egress.bootstrap import credentials
from nima.egress.gateway import gateway_config, write_gateway_config


def test_gateway_has_only_static_connect_routes_and_enforced_auth() -> None:
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    config = gateway_config(auth)
    resources = config["static_resources"]
    (listener,) = resources["listeners"]
    assert listener["address"]["socket_address"] == {"address": "172.30.240.2", "port_value": 3128}
    manager = listener["filter_chains"][0]["filters"][0]["typed_config"]
    hosts = manager["route_config"]["virtual_hosts"]
    assert {tuple(host["domains"]) for host in hosts} == {
        ("allowed.nima.test:8443",),
        ("badcert.nima.test:8443",),
    }
    for host in hosts:
        (route,) = host["routes"]
        assert route["match"] == {"connect_matcher": {}}
        assert route["route"]["upgrade_configs"] == [
            {"upgrade_type": "CONNECT", "connect_config": {}}
        ]
    assert {(row["name"], row["type"]) for row in resources["clusters"]} == {
        ("origin", "STATIC"),
        ("bad", "STATIC"),
    }
    filters = manager["http_filters"]
    assert [row["name"] for row in filters] == [
        "envoy.filters.http.rbac",
        "envoy.filters.http.router",
    ]
    rbac = filters[0]["typed_config"]
    assert "shadow_rules" not in rbac
    assert rbac["rules"]["action"] == "ALLOW"
    (policy,) = rbac["rules"]["policies"].values()
    assert policy["principals"] == [
        {"header": {"name": "proxy-authorization", "string_match": {"exact": auth.basic}}}
    ]
    rules = policy["permissions"][0]["and_rules"]["rules"]
    assert rules[0] == {"header": {"name": ":method", "string_match": {"exact": "CONNECT"}}}
    assert {rule["header"]["string_match"]["exact"] for rule in rules[1]["or_rules"]["rules"]} == {
        "allowed.nima.test:8443",
        "badcert.nima.test:8443",
    }
    (mapper,) = manager["local_reply_config"]["mappers"]
    assert mapper["status_code"] == 407
    assert mapper["headers_to_add"][0]["header"] == {
        "key": "proxy-authenticate",
        "value": 'Basic realm="nima-fixture"',
    }
    assert config["admin"]["address"] == {
        "pipe": {"path": "/gateway-admin/envoy.sock", "mode": 0o600}
    }
    assert "access_log" not in manager
    assert json.dumps(config).count(auth.basic) == 1


def test_gateway_configuration_is_owner_only_and_cannot_be_overwritten(tmp_path: Path) -> None:
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    private = tmp_path / "gateway"
    write_gateway_config(private, auth)
    config = private / "envoy.json"
    assert private.stat().st_mode & 0o777 == 0o700
    assert config.stat().st_mode & 0o777 == 0o600
    assert json.loads(config.read_bytes()) == gateway_config(auth)
    original = config.read_bytes()
    with pytest.raises(ValueError, match="^gateway_storage$"):
        write_gateway_config(private, credentials(auth.username, "q" * 43))
    assert config.read_bytes() == original
