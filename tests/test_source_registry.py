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
    assert registry.known_sources() == ("kimdis",)


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
