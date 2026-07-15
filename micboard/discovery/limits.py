"""Hard resource limits shared by discovery workflows."""

from __future__ import annotations

DEFAULT_DISCOVERY_CANDIDATE_LIMIT = 1024
MAX_DISCOVERY_CANDIDATES = 4096
MAX_DISCOVERY_APPROVAL_BATCH = 100
MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS = MAX_DISCOVERY_APPROVAL_BATCH * 4
DISCOVERY_SUBMISSION_BATCH_SIZE = 1024
MAX_DISCOVERY_METADATA_DEPTH = 5
MAX_DISCOVERY_METADATA_FIELDS = 128
MAX_DISCOVERY_METADATA_LIST_ITEMS = 128
MAX_DISCOVERY_METADATA_STRING_LENGTH = 2048


def clamp_candidate_limit(requested_limit: int) -> int:
    """Clamp a caller-provided candidate limit to the safe supported range."""
    return min(MAX_DISCOVERY_CANDIDATES, max(0, requested_limit))
