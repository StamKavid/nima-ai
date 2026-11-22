"""The registry is the one place the engine learns which adapters exist."""

import pytest

from nima.sources import registry
from nima.sources.base import SourceAdapter
from nima.sources.kimdis import KimdisAdapter
from tests.test_collection import QUERY


def test_the_default_source_is_kimdis_with_its_exact_identity() -> None:
    adapter = registry.default_adapter()
    assert isinstance(adapter, KimdisAdapter) and adapter.name == registry.DEFAULT_SOURCE
    assert adapter.normalizer_version == registry.DEFAULT_NORMALIZER_VERSION
    assert registry.known_sources() == ("diavgeia", "diavgeia-commitment", "kimdis")


def test_an_adapter_is_built_by_name_with_an_optional_query() -> None:
    adapter: SourceAdapter = registry.adapter_for("kimdis", QUERY)
    assert adapter.query_payload() == QUERY.payload()


def test_an_adapter_without_a_query_refuses_to_describe_one() -> None:
    with pytest.raises(ValueError, match="without a query"):
        registry.default_adapter().query_payload()


@pytest.mark.parametrize("name", ["", "KIMDIS", "gemi", "kimdis ", "../kimdis"])
def test_an_unknown_source_is_an_error_not_a_default(name: str) -> None:
    with pytest.raises(registry.UnknownSourceError):
        registry.adapter_for(name)


def test_a_run_is_rebuilt_into_its_adapter_from_its_saved_connector_and_payload() -> None:
    adapter = registry.adapter_from_run(KimdisAdapter.connector_version, QUERY.payload())
    assert isinstance(adapter, KimdisAdapter)
    assert adapter.query_payload() == QUERY.payload()
    assert adapter.request_for(0).json == QUERY.payload()


@pytest.mark.parametrize("version", ["", "ledger-connector-v2", "kimdis-contract-v2", "KIMDIS"])
def test_a_run_of_an_unregistered_connector_is_refused(version: str) -> None:
    with pytest.raises(registry.UnknownSourceError):
        registry.adapter_from_run(version, QUERY.payload())


def test_a_registered_source_that_cannot_read_the_payload_refuses_it() -> None:
    with pytest.raises(ValueError, match="Invalid saved"):
        registry.adapter_from_run(KimdisAdapter.connector_version, {})


def test_the_commitment_adapter_is_rebuilt_by_its_own_connector_version() -> None:
    from nima.sources.diavgeia_commitments import CommitmentAdapter, CommitmentQuery

    payload = CommitmentQuery("6057", "2026-10-25", "2026-10-27").payload()
    rebuilt = registry.adapter_from_run(CommitmentAdapter.connector_version, payload)
    assert isinstance(rebuilt, CommitmentAdapter) and rebuilt.query_payload() == payload
