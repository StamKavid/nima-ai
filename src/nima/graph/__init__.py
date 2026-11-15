"""Evidence-linked investigation views; source assertions remain distinct from review."""

from typing import Literal


class GraphError(Exception):
    """Fixed failure reason with no source values, selectors or driver details."""

    def __init__(
        self,
        reason: Literal[
            "graph_configuration",
            "graph_input",
            "graph_input_io",
            "graph_evidence",
            "graph_state",
            "graph_limit",
            "graph_schema",
            "graph_permission",
            "graph_database",
            "graph_output",
            "graph_interrupted",
        ],
    ) -> None:
        self.reason = reason
        super().__init__(reason)
