"""Closed synthetic services. Private observer sockets never mount in a worker."""

import argparse
import base64
import json
import os
import signal
import socket
import socketserver
import ssl
import struct
import sys
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import FrameType
from typing import Never

from nima.egress.preflight import check_process, report

METRICS = frozenset(
    {
        "tcp_accepts",
        "udp_datagrams",
        "dns_queries",
        "application_requests",
        "server_errors",
        "html",
        "script",
        "image",
        "xhr",
        "fetch",
    }
)
ROLES = frozenset({"origin", "bad", "canary", "metadata", "host"})

HTML = b"""<!doctype html><html><head><link rel="icon" href="data:,">
<script src="/script.js" defer></script></head><body>Nima fixture
<img src="/image.png" alt="synthetic pixel"></body></html>"""
SCRIPT = b"""window.nimaReady=Promise.all([fetch('/fetch').then(r=>r.text()),
new Promise((resolve,reject)=>{const x=new XMLHttpRequest();x.open('GET','/xhr');
x.onload=()=>resolve(x.responseText);x.onerror=reject;x.send();})]).then(()=>{window.nimaComplete=true;});"""
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg=="
)


class FixtureError(ValueError):
    """Fixed diagnostics only; fixture keys and raw client content stay private."""


class Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = dict.fromkeys(METRICS, 0)
        self._headers_clean = True

    def add(self, metric: str) -> None:
        with self._lock:
            if metric not in METRICS or self._counts[metric] >= 1000000:
                raise FixtureError("counter")
            self._counts[metric] += 1

    def request(self, route: str | None, *, clean: bool) -> None:
        with self._lock:
            self._counts["application_requests"] += 1
            if route in {"html", "script", "image", "xhr", "fetch"}:
                self._counts[route] += 1
            self._headers_clean = self._headers_clean and clean

    def reset(self) -> None:
        with self._lock:
            errors = self._counts["server_errors"]
            self._counts = dict.fromkeys(METRICS, 0)
            self._counts["server_errors"] = errors
            self._headers_clean = True

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {**self._counts, "headers_clean": self._headers_clean}


class _ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    counters: Counters
    role: str

    def handle_error(self, request: object, client_address: object) -> None:
        self.counters.add("server_errors")


class _ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        if not isinstance(self.server, _ControlServer):
            raise FixtureError("control")
        self.request.settimeout(2)
        command = self.rfile.readline(17)
        if command not in {b"snapshot\n", b"reset\n"}:
            self.wfile.write(b'{"failure":"control"}\n')
            return
        if command == b"reset\n":
            self.server.counters.reset()
        payload = {
            "version": "source-worker-counter-v1",
            "role": self.server.role,
            "counters": self.server.counters.snapshot(),
        }
        self.wfile.write(json.dumps(payload, sort_keys=True).encode() + b"\n")


@contextmanager
def control_server(path: Path, counters: Counters, *, role: str) -> Iterator[None]:
    if role not in ROLES:
        raise FixtureError("role")
    server = _ControlServer(os.fspath(path), _ControlHandler)
    server.counters, server.role = counters, role
    os.chmod(path, 0o600)
    identity = path.stat().st_ino
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive() or path.stat().st_ino != identity:
            raise FixtureError("control_cleanup")
        path.unlink()


def read_counters(path: Path, *, role: str, reset: bool = False) -> dict[str, int | bool]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(os.fspath(path))
            client.sendall(b"reset\n" if reset else b"snapshot\n")
            with client.makefile("rb") as stream:
                raw = stream.readline(4097)
        if len(raw) > 4096:
            raise FixtureError("control")
        data = json.loads(raw)
        values = data["counters"]
        if (
            set(data) != {"version", "role", "counters"}
            or data["version"] != "source-worker-counter-v1"
            or data["role"] != role
            or type(values) is not dict
            or set(values) != METRICS | {"headers_clean"}
            or type(values["headers_clean"]) is not bool
            or any(
                type(values[name]) is not int or not 0 <= values[name] <= 1000000
                for name in METRICS
            )
            or values["server_errors"] != 0
        ):
            raise FixtureError("control")
        return {name: values[name] for name in values}
    except (OSError, ValueError, KeyError, TypeError):
        raise FixtureError("control") from None


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    counters: Counters
    context: ssl.SSLContext | None
    role: str
    credentials: tuple[str, str]

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        connection, address = self.socket.accept()
        connection.settimeout(2)
        self.counters.add("tcp_accepts")
        return connection, address

    def handle_error(self, request: object, client_address: object) -> None:
        # Rejected TLS handshakes and closed probes are expected, never raw logs.
        if not isinstance(sys.exception(), (ssl.SSLError, ConnectionError, TimeoutError)):
            self.counters.add("server_errors")


class _HTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        if not isinstance(self.server, _HTTPServer):
            raise FixtureError("server")
        if self.server.context is not None:
            self.request = self.server.context.wrap_socket(self.request, server_side=True)
        super().setup()

    def log_message(self, format: str, *args: object) -> None:
        # Deliberate privacy sink: client paths and headers never enter logs.
        return None

    def do_GET(self) -> None:
        if not isinstance(self.server, _HTTPServer):
            raise FixtureError("server")
        secret = self.server.credentials
        encoded = base64.b64encode((secret[0] + ":" + secret[1]).encode()).decode()
        forbidden = {"proxy-authorization", "x-forwarded-for", "forwarded", "x-real-ip"}
        clean = not any(name.lower() in forbidden for name in self.headers)
        clean = clean and not any(
            token in value for value in self.headers.values() for token in (*secret, encoded)
        )
        resources = {
            "/": (
                "html",
                "text/html",
                HTML if self.server.role in {"origin", "bad"} else b"Nima synthetic canary\n",
            ),
            "/script.js": ("script", "text/javascript", SCRIPT),
            "/image.png": ("image", "image/png", PIXEL),
            "/xhr": ("xhr", "text/plain", b"Nima xhr\n"),
            "/fetch": ("fetch", "text/plain", b"Nima fetch\n"),
        }
        redirects = {
            "/redirect-host": "https://denied.nima.test:8443/",
            "/redirect-ip": "https://172.30.240.4:8443/",
            "/redirect-port": "https://allowed.nima.test:8444/",
        }
        resource = resources.get(self.path)
        self.server.counters.request(resource[0] if resource else None, clean=clean)
        status = 200 if resource else 302 if self.path in redirects else 404
        payload = resource[2] if resource else b""
        self.send_response(status)
        if self.path in redirects:
            self.send_header("Location", redirects[self.path])
        self.send_header("Content-Type", resource[1] if resource else "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True


@contextmanager
def http_server(
    address: tuple[str, int],
    counters: Counters,
    *,
    role: str,
    context: ssl.SSLContext | None,
    credentials: tuple[str, str],
) -> Iterator[tuple[str, int]]:
    if role not in ROLES or address[0] not in {
        "127.0.0.1",
        "172.30.241.3",
        "172.30.241.4",
        "172.30.240.4",
        "172.30.240.1",
        "169.254.169.254",
    }:
        raise FixtureError("server")
    server = _HTTPServer(address, _HTTPHandler)
    server.counters, server.role, server.context, server.credentials = (
        counters,
        role,
        context,
        credentials,
    )
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield address[0], server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise FixtureError("server_cleanup")


def dns_response(query: bytes) -> bytes | None:
    """A tiny authoritative .test fixture, never a forwarding resolver."""
    if not 12 <= len(query) <= 1232:
        return None
    identity, flags, questions, _, _, _ = struct.unpack("!HHHHHH", query[:12])
    if questions != 1 or flags & 0xF800:
        return None
    offset = 12
    labels: list[bytes] = []
    while offset < len(query) and query[offset] != 0:
        length = query[offset]
        offset += 1
        if not 1 <= length <= 63 or offset + length >= len(query) or len(labels) >= 16:
            return None
        labels.append(query[offset : offset + length])
        offset += length
    offset += 1
    if offset + 4 > len(query):
        return None
    qtype, qclass = struct.unpack("!HH", query[offset : offset + 4])
    question = query[12 : offset + 4]
    known = b".".join(labels).lower() in {
        b"allowed.nima.test",
        b"denied.nima.test",
        b"quic.nima.test",
        b"unmapped.nima.test",
    }
    answer = b""
    if known and qtype == 1 and qclass == 1:
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4) + socket.inet_aton("172.30.240.4")
    response_flags = 0x8400 | (flags & 0x0100) | (0 if known else 3)
    return (
        struct.pack("!HHHHHH", identity, response_flags, 1, int(bool(answer)), 0, 0)
        + question
        + answer
    )


class _UDPServer(socketserver.ThreadingUDPServer):
    daemon_threads = True
    max_packet_size = 1232
    counters: Counters
    dns: bool

    def handle_error(self, request: object, client_address: object) -> None:
        self.counters.add("server_errors")


class _UDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        if not isinstance(self.server, _UDPServer):
            raise FixtureError("server")
        data, channel = self.request
        self.server.counters.add("dns_queries" if self.server.dns else "udp_datagrams")
        if self.server.dns:
            response = dns_response(data)
        else:
            response = b"nima-control-ok" if data == b"nima-control" else None
        if response is not None:
            channel.sendto(response, self.client_address)


@contextmanager
def udp_server(
    address: tuple[str, int], counters: Counters, *, dns: bool
) -> Iterator[tuple[str, int]]:
    if address[0] not in {"127.0.0.1", "172.30.240.4"}:
        raise FixtureError("server")
    server = _UDPServer(address, _UDPHandler)
    server.counters, server.dns = counters, dns
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield address[0], int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if thread.is_alive():
            raise FixtureError("server_cleanup")


def _credentials(private_dir: Path) -> tuple[str, str]:
    from nima.egress.bootstrap import credentials
    from nima.evidence import artifacts

    descriptor = artifacts.directory(private_dir, private=True)
    try:
        body = json.loads(artifacts.read(descriptor, "credentials.json", limit=2048, private=True))
    finally:
        os.close(descriptor)
    if type(body) is not dict or set(body) != {"username", "password"}:
        raise FixtureError("credentials")
    auth = credentials(body["username"], body["password"])
    return auth.username, auth.password


def serve_fixture(role: str, *, stop_event: threading.Event | None = None) -> None:
    if role not in ROLES - {"host"}:
        raise FixtureError("role")
    private = Path("/fixture-private")
    auth = _credentials(private)
    counters = Counters()
    context = None
    if role in {"origin", "bad", "canary"}:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(private / (role + ".pem"), private / (role + ".key"))
    address = {
        "origin": "172.30.241.3",
        "bad": "172.30.241.4",
        "canary": "172.30.240.4",
        "metadata": "169.254.169.254",
    }[role]
    stop = threading.Event() if stop_event is None else stop_event

    def terminate(signum: int, frame: FrameType | None) -> None:
        stop.set()

    previous = {
        signum: signal.signal(signum, terminate) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        with ExitStack() as stack:
            ports = (
                (8443, 8444, 443, 9000)
                if role == "canary"
                else (80,)
                if role == "metadata"
                else (8443,)
            )
            for port in ports:
                tls = context if role != "canary" or port != 9000 else None
                stack.enter_context(
                    http_server((address, port), counters, role=role, context=tls, credentials=auth)
                )
            if role == "canary":
                for port in (53, 443, 3478, 9001):
                    stack.enter_context(udp_server((address, port), counters, dns=port == 53))
            stack.enter_context(
                control_server(Path("/control") / (role + ".sock"), counters, role=role)
            )
            print(
                json.dumps(
                    {"version": "source-worker-fixture-v1", "role": role, "status": "ready"}
                ),
                flush=True,
            )
            stop.wait()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise FixtureError("configuration")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser()
        parser.add_argument("mode", choices=("serve", "health"))
        parser.add_argument("--role", required=True, choices=sorted(ROLES))
        args = parser.parse_args(argv)
        check_process(Path("/proc/self/status").read_text(), uid=10002)
        if args.mode == "serve":
            serve_fixture(args.role)
        else:
            read_counters(Path("/control") / (args.role + ".sock"), role=args.role)
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception:
        report("failed", "fixture_service")
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
