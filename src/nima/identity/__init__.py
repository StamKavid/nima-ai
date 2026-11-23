"""Reported identifier assessment before reviewed identity resolution."""

from typing import Literal

MAX_REPORT_BYTES = 32 * 1024 * 1024
POLICY_VERSION = "kimdis-identifier-assessment-v1"
REGISTRY_POLICY_VERSION = "registry-comparison-v1"
# The same policy once searched AFMs are selected: a looked-up AFM and its hits are evidence too.
REGISTRY_SEARCH_POLICY_VERSION = "registry-comparison-v2"
MAX_COMPARISON_MENTIONS = 10000
MAX_REGISTRY_OBSERVATIONS = 100


class ComparisonError(Exception):
    """Fixed comparison failure; never include source assertions or selectors."""

    def __init__(
        self,
        reason: Literal[
            "registry_observation",
            "comparison_limit",
            "registry_shape",
            "registry_import_unavailable",
            "registry_version",
            "registry_incomplete",
        ],
    ) -> None:
        self.reason = reason
        super().__init__(reason)


class AssessmentError(Exception):
    """Fixed public reason; source/driver details must not escape the CLI."""

    def __init__(
        self,
        reason: Literal[
            "run_unavailable",
            "cohort_version",
            "projection_incomplete",
            "projection_version",
            "assessment_limit",
            "output_path",
            "output_conflict",
            "output_io",
        ],
    ) -> None:
        self.reason = reason
        super().__init__(reason)
