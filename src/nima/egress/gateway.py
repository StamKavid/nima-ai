"""Fixed Envoy 1.40.2 bootstrap; the pinned binary validates its JSON schema.

https://github.com/envoyproxy/envoy/blob/v1.40.2/configs/terminate_http1_connect.yaml
https://www.envoyproxy.io/docs/envoy/v1.40.2/api-v3/config/rbac/v3/rbac.proto
https://www.envoyproxy.io/docs/envoy/v1.40.2/configuration/http/http_conn_man/local_reply
"""

import json
import os
from pathlib import Path
from typing import Any

from nima.egress.bootstrap import ProxyCredentials, credentials
from nima.evidence import EvidenceError, artifacts


# This is the external protobuf-JSON boundary, validated by Envoy before launch.
def gateway_config(auth: ProxyCredentials) -> dict[str, Any]:
    auth = credentials(auth.username, auth.password)
    targets = (
        ("origin", "allowed.nima.test:8443", "172.30.241.3"),
        ("bad", "badcert.nima.test:8443", "172.30.241.4"),
    )
    policies = {
        "action": "ALLOW",
        "policies": {
            "fixtures": {
                "permissions": [
                    {
                        "and_rules": {
                            "rules": [
                                {
                                    "header": {
                                        "name": ":method",
                                        "string_match": {"exact": "CONNECT"},
                                    }
                                },
                                {
                                    "or_rules": {
                                        "rules": [
                                            {
                                                "header": {
                                                    "name": ":authority",
                                                    "string_match": {"exact": authority},
                                                }
                                            }
                                            for _, authority, _ in targets
                                        ]
                                    }
                                },
                            ]
                        }
                    }
                ],
                "principals": [
                    {
                        "header": {
                            "name": "proxy-authorization",
                            "string_match": {"exact": auth.basic},
                        }
                    }
                ],
            }
        },
    }
    manager = {
        "@type": (
            "type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3."
            "HttpConnectionManager"
        ),
        "stat_prefix": "nima",
        "codec_type": "HTTP1",
        "stream_idle_timeout": "15s",
        "request_headers_timeout": "5s",
        "generate_request_id": False,
        "skip_xff_append": True,
        "route_config": {
            "name": "fixtures",
            "virtual_hosts": [
                {
                    "name": name,
                    "domains": [authority],
                    "routes": [
                        {
                            "match": {"connect_matcher": {}},
                            "route": {
                                "cluster": name,
                                "timeout": "15s",
                                "upgrade_configs": [
                                    {"upgrade_type": "CONNECT", "connect_config": {}}
                                ],
                            },
                        }
                    ],
                }
                for name, authority, _ in targets
            ],
        },
        "http_filters": [
            {
                "name": "envoy.filters.http.rbac",
                "typed_config": {
                    "@type": "type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC",
                    "rules": policies,
                },
            },
            {
                "name": "envoy.filters.http.router",
                "typed_config": {
                    "@type": "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router",
                },
            },
        ],
        # RBAC denials are challenged on the proxy hop; CONNECT payloads remain
        # end-to-end TLS and never receive these authentication headers.
        "local_reply_config": {
            "mappers": [
                {
                    "filter": {
                        "status_code_filter": {
                            "comparison": {
                                "op": "EQ",
                                "value": {"default_value": 403, "runtime_key": "nima.rbac_denial"},
                            }
                        }
                    },
                    "status_code": 407,
                    "body": {"inline_string": "Fixture proxy denied\n"},
                    "headers_to_add": [
                        {
                            "header": {
                                "key": "proxy-authenticate",
                                "value": 'Basic realm="nima-fixture"',
                            },
                            "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
                        }
                    ],
                }
            ]
        },
    }
    return {
        "admin": {"address": {"pipe": {"path": "/gateway-admin/envoy.sock", "mode": 0o600}}},
        "static_resources": {
            "listeners": [
                {
                    "name": "fixture-proxy",
                    "address": {
                        "socket_address": {
                            "address": "172.30.240.2",
                            "port_value": 3128,
                        }
                    },
                    "filter_chains": [
                        {
                            "filters": [
                                {
                                    "name": "envoy.filters.network.http_connection_manager",
                                    "typed_config": manager,
                                }
                            ]
                        }
                    ],
                }
            ],
            "clusters": [
                {
                    "name": name,
                    "type": "STATIC",
                    "connect_timeout": "2s",
                    "circuit_breakers": {
                        "thresholds": [
                            {
                                "max_connections": 16,
                                "max_pending_requests": 16,
                                "max_requests": 32,
                                "max_retries": 0,
                            }
                        ]
                    },
                    "load_assignment": {
                        "cluster_name": name,
                        "endpoints": [
                            {
                                "lb_endpoints": [
                                    {
                                        "endpoint": {
                                            "address": {
                                                "socket_address": {
                                                    "address": address,
                                                    "port_value": 8443,
                                                }
                                            },
                                        }
                                    }
                                ]
                            }
                        ],
                    },
                }
                for name, _, address in targets
            ],
        },
    }


def write_gateway_config(private_dir: Path, auth: ProxyCredentials) -> None:
    descriptor = None
    try:
        descriptor = artifacts.directory(private_dir, create=True, private=True)
        artifacts.publish(
            descriptor,
            "envoy.json",
            json.dumps(gateway_config(auth), sort_keys=True).encode() + b"\n",
        )
    except (OSError, EvidenceError):
        raise ValueError("gateway_storage") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
