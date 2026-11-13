"""Synthetic PKI and independent delivery counters contain no company records."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from nima.egress import bootstrap as bootstrap_module
from nima.egress.bootstrap import (
    credentials,
    generate_certificates,
    initialize_fixture_state,
    write_certificates,
)
from nima.egress.bootstrap import (
    main as bootstrap_main,
)


def test_ephemeral_certificates_have_exact_names_and_a_separate_untrusted_issuer() -> None:
    material = generate_certificates(datetime(2026, 11, 12, tzinfo=UTC))
    root = x509.load_pem_x509_certificate(material.ca.certificate)
    origin = x509.load_pem_x509_certificate(material.origin.certificate)
    bad = x509.load_pem_x509_certificate(material.untrusted_origin.certificate)
    assert root.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    names = origin.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ["allowed.nima.test"]
    public = root.public_key()
    assert isinstance(public, ec.EllipticCurvePublicKey)
    public.verify(origin.signature, origin.tbs_certificate_bytes, ec.ECDSA(hashes.SHA256()))
    with pytest.raises(InvalidSignature):
        public.verify(bad.signature, bad.tbs_certificate_bytes, ec.ECDSA(hashes.SHA256()))
    assert "PRIVATE KEY" not in repr(material)
    assert generate_certificates().ca.certificate != material.ca.certificate


def test_only_public_ca_is_shared_and_private_keys_are_owner_only(tmp_path: Path) -> None:
    private, public = tmp_path / "private", tmp_path / "public"
    public.mkdir()
    public.chmod(0o750)  # Simulate the image-owned public-volume mount point.
    material = generate_certificates()
    write_certificates(private, public, material)
    assert private.stat().st_mode & 0o777 == 0o700
    assert public.stat().st_mode & 0o777 == 0o750
    assert {path.name for path in public.iterdir()} == {"ca.pem"}
    assert (public / "ca.pem").read_bytes() == material.ca.certificate
    assert (public / "ca.pem").stat().st_mode & 0o777 == 0o640
    for path in private.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    assert (private / "origin.key").read_bytes() == material.origin.private_key


def test_bootstrap_does_not_change_permissions_on_existing_operator_directories(
    tmp_path: Path,
) -> None:
    public = tmp_path / "public"
    public.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="^fixture_storage$"):
        write_certificates(tmp_path / "private", public, generate_certificates())
    assert public.stat().st_mode & 0o777 == 0o700
    assert list(public.iterdir()) == []


def test_credentials_and_argument_failures_never_echo_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pair = credentials("fixture-user-" + "u" * 16, "p" * 43)
    assert "p" * 43 not in repr(pair)
    for value in (None, "private-secret\ninvalid", "x" * 129):
        with pytest.raises(ValueError, match="^fixture_credentials$"):
            credentials("fixture-user-" + "u" * 16, value)
    assert bootstrap_main(["--private-secret"]) == 2
    assert "private-secret" not in capsys.readouterr().out


def test_full_initializer_writes_credentials_only_to_private_state(tmp_path: Path) -> None:
    private, public = tmp_path / "private", tmp_path / "public"
    public.mkdir()
    public.chmod(0o750)
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    initialize_fixture_state(private, public, auth)
    assert json.loads((private / "credentials.json").read_bytes()) == {
        "username": auth.username,
        "password": auth.password,
    }
    assert (private / "credentials.json").stat().st_mode & 0o777 == 0o600
    assert {path.name for path in public.iterdir()} == {"ca.pem"}


@pytest.mark.parametrize("failure", [OSError("private-secret-path"), KeyboardInterrupt()])
def test_initializer_errors_are_fixed_and_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: BaseException
) -> None:
    monkeypatch.setattr(bootstrap_module, "check_process", lambda *args, **kwargs: None)
    monkeypatch.setenv("NIMA_FIXTURE_USERNAME", "fixture-user-" + "u" * 16)
    monkeypatch.setenv("NIMA_FIXTURE_PASSWORD", "p" * 43)

    def fail(*args: object) -> None:
        raise failure

    monkeypatch.setattr(bootstrap_module, "initialize_fixture_state", fail)
    assert bootstrap_main(["initialize"]) == (130 if isinstance(failure, KeyboardInterrupt) else 1)
    output = capsys.readouterr().out
    assert "private-secret" not in output
    assert '"status": "failed"' in output
