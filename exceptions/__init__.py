"""
异常定义包

包含A_Mind插件的所有自定义异常类
"""

from .amind_exceptions import (
    AMindError,
    DatabaseError,
    LLMError,
    PermissionError,
    ConfigurationError,
    ValidationError
)

__all__ = [
    'AMindError',
    'DatabaseError',
    'LLMError',
    'PermissionError',
    'ConfigurationError',
    'ValidationError'
]

