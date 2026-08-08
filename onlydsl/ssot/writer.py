"""Application composition for the extracted SSOT store."""

from onlydsl_ssot.validation import TreeValidator
from onlydsl_ssot.writer import SsotStore as BaseSsotStore

from .validation import validate_tree


class SsotStore(BaseSsotStore):
    """SSOT store configured with onlyDSL's domain-aware validator."""

    def __init__(self, project_root, *, validator: TreeValidator = validate_tree):
        super().__init__(project_root, validator=validator)
