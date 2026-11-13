"""Ephemeral fixture PKI, following the exact locked library's CA example.

https://github.com/pyca/cryptography/blob/50.0.2/docs/x509/tutorial.rst#creating-a-ca-hierarchy
Never deploy these synthetic authorities or persist their keys in Git/logs.
"""

import base64
import json
import os
import re
import stat
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from nima.egress.preflight import check_process, report


@dataclass(frozen=True, slots=True)
class ProxyCredentials:
    username: str = field(repr=False)
    password: str = field(repr=False)

    @property
    def basic(self) -> str:
        return "Basic " + base64.b64encode((self.username + ":" + self.password).encode()).decode()


def credentials(username: object, password: object) -> ProxyCredentials:
    if (
        type(username) is not str
        or type(password) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{16,64}", username) is None
        or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", password) is None
    ):
        raise ValueError("fixture_credentials")
    return ProxyCredentials(username, password)


@dataclass(frozen=True, slots=True)
class CertificatePair:
    certificate: bytes = field(repr=False)
    private_key: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class FixtureCertificates:
    ca: CertificatePair
    untrusted_ca: CertificatePair
    origin: CertificatePair
    untrusted_origin: CertificatePair
    canary: CertificatePair


def _issue(
    name: str,
    key: ec.EllipticCurvePrivateKey,
    issuer: x509.Name,
    signer: ec.EllipticCurvePrivateKey,
    now: datetime,
    names: list[x509.GeneralName] | None,
) -> x509.Certificate:
    ca = names is None
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=0 if ca else None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=ca,
                crl_sign=ca,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()), critical=False
        )
    )
    if names is not None:
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
    return builder.sign(signer, hashes.SHA256())


def _pair(certificate: x509.Certificate, key: ec.EllipticCurvePrivateKey) -> CertificatePair:
    # Ephemeral private-volume keys, mode 0600; never a production key store.
    return CertificatePair(
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def generate_certificates(now: datetime | None = None) -> FixtureCertificates:
    instant = now if now is not None else datetime.now(UTC)
    if instant.utcoffset() != timedelta(0):
        raise ValueError("certificate_time")
    ca_key = ec.generate_private_key(ec.SECP256R1())
    bad_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Nima synthetic fixture CA")])
    bad_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Nima untrusted fixture CA")])
    ca = _issue("Nima synthetic fixture CA", ca_key, ca_name, ca_key, instant, None)
    bad_ca = _issue("Nima untrusted fixture CA", bad_key, bad_name, bad_key, instant, None)
    origin_key, untrusted_key, canary_key = (
        ec.generate_private_key(ec.SECP256R1()) for _ in range(3)
    )
    origin = _issue(
        "allowed.nima.test",
        origin_key,
        ca.subject,
        ca_key,
        instant,
        [x509.DNSName("allowed.nima.test")],
    )
    untrusted = _issue(
        "badcert.nima.test",
        untrusted_key,
        bad_ca.subject,
        bad_key,
        instant,
        [x509.DNSName("badcert.nima.test")],
    )
    names: list[x509.GeneralName] = [
        x509.DNSName(name)
        for name in (
            "allowed.nima.test",
            "denied.nima.test",
            "quic.nima.test",
            "unmapped.nima.test",
        )
    ]
    names.extend(
        x509.IPAddress(IPv4Address(value))
        for value in ("172.30.240.4", "172.30.240.1", "169.254.169.254", "127.0.0.1")
    )
    canary = _issue("Nima synthetic canary", canary_key, ca.subject, ca_key, instant, names)
    return FixtureCertificates(
        _pair(ca, ca_key),
        _pair(bad_ca, bad_key),
        _pair(origin, origin_key),
        _pair(untrusted, untrusted_key),
        _pair(canary, canary_key),
    )


def write_certificates(private_dir: Path, public_dir: Path, material: FixtureCertificates) -> None:
    """One-shot initialization; the image prepares the owned public volume at 0750."""
    from nima.evidence import EvidenceError, artifacts

    private = public = None
    try:
        private = artifacts.directory(private_dir, create=True, private=True)
        public = artifacts.directory(public_dir)
        info = os.fstat(public)
        if (
            info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or stat.S_IMODE(info.st_mode) != 0o750
            or os.listdir(private)
            or os.listdir(public)
        ):
            raise ValueError("fixture_storage")
        for name, pair in (
            ("ca", material.ca),
            ("bad-ca", material.untrusted_ca),
            ("origin", material.origin),
            ("bad", material.untrusted_origin),
            ("canary", material.canary),
        ):
            artifacts.publish(private, name + ".pem", pair.certificate)
            artifacts.publish(private, name + ".key", pair.private_key)
        # Shared fixture GID 10001 can read only the public CA. Private volume
        # roots remain 0700/keys 0600 under UID 10002, regardless of shared GID.
        # Volume mode/ownership is prepared at image build or creation, never
        # broadened on an existing operator directory.
        temporary = ".ca-" + uuid4().hex
        file = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=public
        )
        try:
            with os.fdopen(file, "wb") as stream:
                stream.write(material.ca.certificate)
                stream.flush()
                os.fchmod(stream.fileno(), 0o640)  # Public CA shared with the worker group.
                os.fsync(stream.fileno())
            os.link(
                temporary, "ca.pem", src_dir_fd=public, dst_dir_fd=public, follow_symlinks=False
            )
            os.fsync(public)
        finally:
            os.unlink(temporary, dir_fd=public)
    except (OSError, EvidenceError):
        raise ValueError("fixture_storage") from None
    finally:
        if private is not None:
            os.close(private)
        if public is not None:
            os.close(public)


def initialize_fixture_state(private_dir: Path, public_dir: Path, auth: ProxyCredentials) -> None:
    from nima.evidence import artifacts

    write_certificates(private_dir, public_dir, generate_certificates())
    descriptor = artifacts.directory(private_dir, private=True)
    try:
        artifacts.publish(
            descriptor,
            "credentials.json",
            json.dumps(
                {"username": auth.username, "password": auth.password}, sort_keys=True
            ).encode()
            + b"\n",
        )
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["initialize"]:
        report("failed", "configuration")
        return 2
    try:
        check_process(Path("/proc/self/status").read_text(), uid=10002)
        auth = credentials(
            os.environ.get("NIMA_FIXTURE_USERNAME"), os.environ.get("NIMA_FIXTURE_PASSWORD")
        )
        initialize_fixture_state(Path("/fixture-private"), Path("/fixture-public"), auth)
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception as exc:
        observed = {}
        for label, path in (
            ("private", Path("/fixture-private")),
            ("public", Path("/fixture-public")),
        ):
            try:
                info = path.stat()
                observed[label + "_uid"] = info.st_uid
                observed[label + "_gid"] = info.st_gid
                observed[label + "_mode"] = stat.S_IMODE(info.st_mode)
            except OSError:
                continue
        print(json.dumps({"version": "source-worker-volume-observation-v1", "volumes": observed}))
        reason = (
            str(exc)
            if str(exc) in {"fixture_storage", "fixture_credentials", "process"}
            else "fixture_initialization"
        )
        report("failed", reason)
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
