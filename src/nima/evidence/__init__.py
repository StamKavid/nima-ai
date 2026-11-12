"""Offline, channel-labelled evidence; never accepted registry identities."""


class EvidenceError(ValueError):
    """A fixed reason code, without input values or operating-system details."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
