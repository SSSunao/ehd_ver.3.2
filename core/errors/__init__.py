# -*- coding: utf-8 -*-
"""
Core errors layer - エラー処理層
統合エラーハンドリング、エラー・レジューム統合管理を担当
"""

from .enhanced_error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity, ErrorPersistence, RetryStrategy, FinalAction, ErrorContext, ErrorStrategy
from .unified_error_resume_manager import UnifiedErrorResumeManager
from .selenium_fallback_handler import SeleniumFallbackHandler

__all__ = [
    'EnhancedErrorHandler',
    'UnifiedErrorResumeManager',
    'SeleniumFallbackHandler',
    'ErrorCategory',
    'ErrorSeverity',
    'ErrorPersistence',
    'RetryStrategy',
    'FinalAction',
    'ErrorContext',
    'ErrorStrategy',
]
