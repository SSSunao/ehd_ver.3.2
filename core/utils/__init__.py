"""core.utils package - Phase 1リファクタリング"""

from .validation import (
    require_not_none,
    safe_str,
    safe_format,
    validate_positive,
    validate_url,
    validate_index
)

from .contracts import (
    require,
    ensure,
    invariant,
    precondition,
    postcondition
)

__all__ = [
    # validation
    'require_not_none',
    'safe_str',
    'safe_format',
    'validate_positive',
    'validate_url',
    'validate_index',
    
    # contracts
    'require',
    'ensure',
    'invariant',
    'precondition',
    'postcondition',
]
