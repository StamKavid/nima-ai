"""Synthetic Diavgeia search pages in the documented shape; no real decision or person appears."""

import json
import re
from typing import Any


def decision(ada: Any = "ΑΒΓΔΕ-ΖΗ1", **fields: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ada": ada,
        "decisionTypeId": "Δ.2.2",
        "organizationId": "99999",
        "issueDate": 1_767_225_600_000,
        "submissionTimestamp": 1_767_229_200_000,
        "versionId": "v1",
        "status": "PUBLISHED",
        "privateData": False,
        "extraFieldValues": {},
    }
    row.update(fields)
    return row


def search_page(number: Any, total: Any, size: Any, decisions: list[Any], **info: Any) -> bytes:
    body = {"info": {"page": number, "size": size, "total": total, **info}, "decisions": decisions}
    text = json.dumps(body, ensure_ascii=False)
    # An amount written as ``"@@123.40@@"`` becomes the JSON number 123.40, with its exact digits.
    return re.sub(r'"@@(.+?)@@"', lambda m: m.group(1), text).encode()


def award(amount: str, *, persons: int = 1) -> dict[str, Any]:
    """Extra fields of an award; ``amount`` becomes an exact JSON number (see ``search_page``)."""
    return {
        "awardAmount": {"amount": f"@@{amount}@@", "currency": "EUR"},
        "person": [{"afmType": "Φυσικό ή Νομικό πρόσωπο εντός της Ελλάδας"}] * persons,
    }


def commitment(amount: str, *, lines: int = 1, **extra: Any) -> dict[str, Any]:
    """Extra fields of a commitment (Β.1.3); ``amount`` becomes an exact JSON number."""
    fields: dict[str, Any] = {
        "financialYear": 2026,
        "budgettype": "ΤΑΚΤΙΚΟΣ",
        "partialead": False,
        "entryNumber": 17,
        "amountWithVAT": {"amount": f"@@{amount}@@", "currency": "EUR"},
        "amountWithKae": [
            {
                "kae": "2420",
                "amountWithVAT": {"amount": f"@@{amount}@@", "currency": "EUR"},
                "sponsorAFMName": {"afm": "000000000", "name": "SUPPLIER NAME"},
            }
        ]
        * lines,
    }
    fields.update(extra)
    return fields
