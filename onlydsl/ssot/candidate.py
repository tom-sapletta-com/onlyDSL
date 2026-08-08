"""Compatibility facade that preserves onlyDSL domain validation defaults."""

from onlydsl_ssot.candidate import load_candidate, save_candidate
from onlydsl_ssot.candidate import create_candidate as _create_candidate
from onlydsl_ssot.candidate import validate_candidate as _validate_candidate

from .validation import validate_tree


def create_candidate(*args, validator=validate_tree, **kwargs):
    return _create_candidate(*args, validator=validator, **kwargs)


def validate_candidate(*args, validator=validate_tree, **kwargs):
    return _validate_candidate(*args, validator=validator, **kwargs)
