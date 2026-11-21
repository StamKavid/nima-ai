"""Offline main-base-code reference from one explicitly pinned publisher release.

https://github.com/OP-TED/eForms-SDK/tree/1.15.1/codelists
https://github.com/tiran/defusedxml/tree/v0.7.1#defusedxml
"""

import hashlib
import io
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol, cast

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, iterparse

from nima.identity.artifacts import encode
from nima.sources.metadata_extract import MetadataError

VERSION = "cpv-reference-v1"
SOURCE = "https://raw.githubusercontent.com/OP-TED/eForms-SDK/1.15.1/codelists/cpv.gc"
MAX_BYTES = 64 * 1024 * 1024
MAX_ROWS = 10_000
MAX_ELEMENTS = 1_000_000
MAX_DEPTH = 12
MAX_TEXT = 4096
ROOT = "{http://docs.oasis-open.org/codelist/ns/genericode/1.0/}CodeList"


class _Node(Protocol):
    tag: str
    text: str | None
    tail: str | None
    attrib: dict[str, str]

    def __iter__(self) -> Iterator["_Node"]: ...
    def clear(self) -> None: ...


@dataclass(frozen=True)
class CpvEntry:
    code: str
    label: str
    parent_code: str | None
    row_ordinal: int


@dataclass(frozen=True)
class CpvReference:
    raw_sha256: str
    language: str
    retrieved_at: str
    entries: tuple[CpvEntry, ...]

    def body(self) -> bytes:
        return encode(
            {
                "artifact_version": VERSION,
                "reference": {
                    "source_url": SOURCE,
                    "publisher": "Publications Office of the European Union / OP-TED",
                    "sdk_release": "1.15.1",
                    "taxonomy": "CPV",
                    "taxonomy_version": "2008",
                    "list_id": "cpv_2008_core",
                    "raw_sha256": self.raw_sha256,
                    "language": self.language,
                    "retrieved_at": self.retrieved_at,
                    "license": "CC-BY-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "publisher_license_url": "https://github.com/OP-TED/eForms-SDK/blob/1.15.1/LICENSE",
                    "modifications": (
                        "Selected language; sorted base codes; retained source row ordinals"
                    ),
                    "source_location": (
                        "/CodeList/SimpleCodeList/Row (zero-based ordinal)/Value[@ColumnRef]"
                    ),
                    "provenance": (
                        "Operator-selected capture; transport authenticity not re-attested"
                    ),
                    "label_column": self.language + "_label",
                },
                "match_scope": "cpv_main_base_code",
                "check_digit_validation": "not_checked",
                "entry_count": len(self.entries),
                "entries": [asdict(entry) for entry in self.entries],
            }
        )


def _children(node: _Node) -> list[_Node]:
    # defusedxml's iterator stubs expose Any; confine that third-party boundary here.
    return list(node)


def _identification(node: _Node) -> None:
    for name, expected in (
        ("ShortName", "cpv_2008_core"),
        ("Version", "2008"),
        ("CanonicalUri", "http://publications.europa.eu/resource/dataset/cpv"),
    ):
        values = [child.text for child in _children(node) if child.tag == name]
        if values != [expected]:
            raise MetadataError("reference_evidence")


def _columns(node: _Node, language: str) -> set[str]:
    columns = [n.attrib.get("Id", "") for n in _children(node) if n.tag == "Column"]
    if (
        any(not name for name in columns)
        or len(columns) != len(set(columns))
        or not {"code", "parentCode", language + "_label"}.issubset(columns)
    ):
        raise MetadataError("reference_evidence")
    return set(columns)


def _entry(node: _Node, columns: set[str], language: str, ordinal: int) -> CpvEntry:
    cells: dict[str, str] = {}
    for cell in _children(node):
        name = cell.attrib.get("ColumnRef", "")
        values = _children(cell)
        if (
            cell.tag != "Value"
            or name not in columns
            or name in cells
            or len(values) != 1
            or values[0].tag != "SimpleValue"
            or _children(values[0])
        ):
            raise MetadataError("reference_evidence")
        cells[name] = values[0].text or ""
    code, label, parent = (
        cells.get("code", ""),
        cells.get(language + "_label", ""),
        cells.get("parentCode"),
    )
    if (
        re.fullmatch("[0-9]{8}", code) is None
        or not label.strip()
        or (parent is not None and re.fullmatch("[0-9]{8}", parent) is None)
    ):
        raise MetadataError("reference_evidence")
    return CpvEntry(code, label, parent, ordinal)


def _parents(entries: dict[str, CpvEntry]) -> None:
    checked: set[str] = set()
    for code in entries:
        path: set[str] = set()
        current: str | None = code
        while current is not None and current not in checked:
            if current in path or current not in entries:
                raise MetadataError("reference_evidence")
            path.add(current)
            current = entries[current].parent_code
        checked.update(path)


def _parse(raw: bytes, language: str) -> tuple[CpvEntry, ...]:
    stack: list[str] = []
    top: list[str] = []
    columns: set[str] = set()
    entries: dict[str, CpvEntry] = {}
    elements = 0
    for event, value in iterparse(
        io.BytesIO(raw),
        events=("start", "end"),
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    ):
        node = cast(_Node, value)
        if event == "start":
            stack.append(node.tag)
            elements += 1
            if len(stack) > MAX_DEPTH or elements > MAX_ELEMENTS:
                raise MetadataError("reference_limit")
            if len(stack) == 1 and node.tag != ROOT:
                raise MetadataError("reference_evidence")
            if len(stack) == 2:
                top.append(node.tag)
            if len(stack) == 3 and stack[1] == "SimpleCodeList" and node.tag != "Row":
                raise MetadataError("reference_evidence")
            continue
        if any(len(text or "") > MAX_TEXT for text in (node.text, node.tail)):
            raise MetadataError("reference_limit")
        if stack == [ROOT, "Identification"]:
            _identification(node)
        elif stack == [ROOT, "ColumnSet"]:
            columns = _columns(node, language)
        elif stack == [ROOT, "SimpleCodeList", "Row"]:
            if len(entries) >= MAX_ROWS:
                raise MetadataError("reference_limit")
            entry = _entry(node, columns, language, len(entries))
            if entry.code in entries:
                raise MetadataError("reference_evidence")
            entries[entry.code] = entry
            node.clear()
        stack.pop()
    if top != ["Identification", "ColumnSet", "SimpleCodeList"] or not entries:
        raise MetadataError("reference_evidence")
    _parents(entries)
    return tuple(entries[key] for key in sorted(entries))


def prepare_reference(
    raw: bytes,
    *,
    raw_sha256: str,
    language: str,
    retrieved_at: str,
) -> CpvReference:
    """Validate a whole captured release; expected hash is an explicit selection."""
    if (
        not isinstance(raw, bytes)
        or language not in {"ell", "eng"}
        or not isinstance(raw_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", raw_sha256) is None
        or not isinstance(retrieved_at, str)
        or len(retrieved_at) > 64
    ):
        raise MetadataError("reference_input")
    try:
        if datetime.fromisoformat(retrieved_at).utcoffset() is None:
            raise ValueError
    except ValueError:
        raise MetadataError("reference_input") from None
    if len(raw) > MAX_BYTES:
        raise MetadataError("reference_limit")
    if hashlib.sha256(raw).hexdigest() != raw_sha256:
        raise MetadataError("reference_selection")
    try:
        entries = _parse(raw, language)
    except (ParseError, DefusedXmlException, UnicodeError):
        raise MetadataError("reference_evidence") from None
    return CpvReference(raw_sha256, language, retrieved_at, entries)
