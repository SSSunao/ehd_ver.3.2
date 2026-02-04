# -*- coding: utf-8 -*-
"""
エラーハンドラー基底クラス - Phase C設計

Chain of Responsibility パターンを実装し、
各エラータイプに特化したハンドラーを構築する基盤。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from enum import Enum
import traceback


class ErrorSeverity(Enum):
    """エラー深刻度"""
    INFO = "info"           # 情報（ログのみ）
    WARNING = "warning"     # 警告（リトライ可能）
    ERROR = "error"         # エラー（リカバリー試行）
    CRITICAL = "critical"   # 致命的（中断）


class ErrorCategory(Enum):
    """エラーカテゴリ"""
    NETWORK = "network"               # ネットワークエラー
    VALIDATION = "validation"         # バリデーションエラー
    SELENIUM = "selenium"             # Seleniumエラー
    FILE_SYSTEM = "file_system"       # ファイルシステムエラー
    PARSING = "parsing"               # パースエラー
    UNKNOWN = "unknown"               # 不明なエラー


class ErrorResult:
    """エラー処理結果"""
    
    def __init__(
        self, 
        handled: bool,
        should_retry: bool = False,
        should_skip: bool = False,
        should_abort: bool = False,
        recovery_action: Optional[str] = None,
        message: str = ""
    ):
        self.handled = handled              # 処理されたか
        self.should_retry = should_retry    # リトライすべきか
        self.should_skip = should_skip      # スキップすべきか
        self.should_abort = should_abort    # 中断すべきか
        self.recovery_action = recovery_action  # リカバリーアクション
        self.message = message              # メッセージ
    
    @classmethod
    def retry(cls, message: str = "リトライします") -> 'ErrorResult':
        """リトライを返す"""
        return cls(handled=True, should_retry=True, message=message)
    
    @classmethod
    def skip(cls, message: str = "スキップします") -> 'ErrorResult':
        """スキップを返す"""
        return cls(handled=True, should_skip=True, message=message)
    
    @classmethod
    def abort(cls, message: str = "中断します") -> 'ErrorResult':
        """中断を返す"""
        return cls(handled=True, should_abort=True, message=message)
    
    @classmethod
    def not_handled(cls) -> 'ErrorResult':
        """未処理を返す"""
        return cls(handled=False)


class ErrorContext:
    """エラーコンテキスト情報"""
    
    def __init__(
        self,
        error: Exception,
        url: Optional[str] = None,
        page: Optional[int] = None,
        retry_count: int = 0,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        self.error = error
        self.error_type = type(error).__name__
        self.error_message = str(error)
        self.url = url
        self.page = page
        self.retry_count = retry_count
        self.additional_info = additional_info or {}
        self.traceback = traceback.format_exc()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return {
            'error_type': self.error_type,
            'error_message': self.error_message,
            'url': self.url,
            'page': self.page,
            'retry_count': self.retry_count,
            'additional_info': self.additional_info,
            'traceback': self.traceback
        }


class BaseErrorHandler(ABC):
    """エラーハンドラー基底クラス
    
    Chain of Responsibility パターンの実装。
    各サブクラスは特定のエラータイプを処理する。
    """
    
    def __init__(self, successor: Optional['BaseErrorHandler'] = None):
        """
        Args:
            successor: 次のハンドラー（処理できない場合に委譲）
        """
        self.successor = successor
    
    @abstractmethod
    def can_handle(self, context: ErrorContext) -> bool:
        """このハンドラーがエラーを処理できるか判定
        
        Args:
            context: エラーコンテキスト
            
        Returns:
            bool: 処理可能ならTrue
        """
        pass
    
    @abstractmethod
    def handle_error(self, context: ErrorContext) -> ErrorResult:
        """エラーを処理
        
        Args:
            context: エラーコンテキスト
            
        Returns:
            ErrorResult: 処理結果
        """
        pass
    
    def handle(self, context: ErrorContext) -> ErrorResult:
        """エラーハンドリングのエントリーポイント
        
        処理できる場合は handle_error() を呼び出し、
        処理できない場合は次のハンドラーに委譲。
        
        Args:
            context: エラーコンテキスト
            
        Returns:
            ErrorResult: 処理結果
        """
        if self.can_handle(context):
            return self.handle_error(context)
        
        if self.successor:
            return self.successor.handle(context)
        
        # 誰も処理できなかった
        return ErrorResult.not_handled()
    
    def log(self, message: str, level: str = "info"):
        """ログ出力（サブクラスでオーバーライド可能）"""
        print(f"[{level.upper()}] {message}")
    
    def categorize_error(self, error: Exception) -> ErrorCategory:
        """エラーをカテゴリ分類
        
        Args:
            error: 例外オブジェクト
            
        Returns:
            ErrorCategory: エラーカテゴリ
        """
        error_type = type(error).__name__
        error_msg = str(error).lower()
        
        # ネットワークエラー
        network_keywords = ['connection', 'timeout', 'network', 'http', 'ssl']
        if any(keyword in error_msg for keyword in network_keywords):
            return ErrorCategory.NETWORK
        
        # Seleniumエラー
        if 'selenium' in error_msg or 'webdriver' in error_msg:
            return ErrorCategory.SELENIUM
        
        # バリデーションエラー
        if 'validation' in error_msg or 'invalid' in error_msg:
            return ErrorCategory.VALIDATION
        
        # ファイルシステムエラー
        if 'permission' in error_msg or 'file' in error_msg or 'directory' in error_msg:
            return ErrorCategory.FILE_SYSTEM
        
        # パースエラー
        if 'parse' in error_msg or 'json' in error_msg or 'xml' in error_msg:
            return ErrorCategory.PARSING
        
        return ErrorCategory.UNKNOWN
    
    def get_severity(self, context: ErrorContext) -> ErrorSeverity:
        """エラーの深刻度を判定
        
        Args:
            context: エラーコンテキスト
            
        Returns:
            ErrorSeverity: 深刻度
        """
        # リトライ回数で判定
        if context.retry_count >= 3:
            return ErrorSeverity.ERROR
        elif context.retry_count >= 1:
            return ErrorSeverity.WARNING
        else:
            return ErrorSeverity.INFO


class NetworkErrorHandler(BaseErrorHandler):
    """ネットワークエラー専門ハンドラー
    
    接続エラー、タイムアウト、HTTPエラーを処理。
    """
    
    def can_handle(self, context: ErrorContext) -> bool:
        """ネットワークエラーか判定"""
        category = self.categorize_error(context.error)
        return category == ErrorCategory.NETWORK
    
    def handle_error(self, context: ErrorContext) -> ErrorResult:
        """ネットワークエラーを処理"""
        self.log(f"ネットワークエラー検出: {context.error_message}", "warning")
        
        # リトライ回数チェック
        if context.retry_count < 3:
            return ErrorResult.retry(f"ネットワークエラー - リトライ {context.retry_count + 1}/3")
        else:
            return ErrorResult.skip("ネットワークエラー - リトライ上限に達しました")


class ValidationErrorHandler(BaseErrorHandler):
    """バリデーションエラー専門ハンドラー
    
    入力値の検証エラーを処理。
    """
    
    def can_handle(self, context: ErrorContext) -> bool:
        """バリデーションエラーか判定"""
        category = self.categorize_error(context.error)
        return category == ErrorCategory.VALIDATION
    
    def handle_error(self, context: ErrorContext) -> ErrorResult:
        """バリデーションエラーを処理"""
        self.log(f"バリデーションエラー: {context.error_message}", "error")
        
        # バリデーションエラーはリトライ不可
        return ErrorResult.skip("バリデーションエラー - スキップします")


class SeleniumErrorHandler(BaseErrorHandler):
    """Seleniumエラー専門ハンドラー
    
    Selenium/WebDriverエラーを処理。
    """
    
    def can_handle(self, context: ErrorContext) -> bool:
        """Seleniumエラーか判定"""
        category = self.categorize_error(context.error)
        return category == ErrorCategory.SELENIUM
    
    def handle_error(self, context: ErrorContext) -> ErrorResult:
        """Seleniumエラーを処理"""
        self.log(f"Seleniumエラー: {context.error_message}", "warning")
        
        # Seleniumエラーはリトライ
        if context.retry_count < 2:
            return ErrorResult.retry(f"Seleniumエラー - リトライ {context.retry_count + 1}/2")
        else:
            return ErrorResult.skip("Seleniumエラー - リトライ上限")


class ErrorHandlerChain:
    """エラーハンドラーチェーン
    
    複数のエラーハンドラーを連鎖させ、
    適切なハンドラーがエラーを処理する。
    """
    
    def __init__(self):
        """チェーンを構築"""
        # ハンドラーを連鎖
        self.chain = NetworkErrorHandler(
            successor=ValidationErrorHandler(
                successor=SeleniumErrorHandler()
            )
        )
    
    def handle(self, error: Exception, **kwargs) -> ErrorResult:
        """エラーを処理
        
        Args:
            error: 例外オブジェクト
            **kwargs: 追加情報
            
        Returns:
            ErrorResult: 処理結果
        """
        context = ErrorContext(error, **kwargs)
        result = self.chain.handle(context)
        
        if not result.handled:
            # どのハンドラーも処理できなかった
            return ErrorResult.skip(f"未処理エラー: {context.error_message}")
        
        return result


# 使用例
if __name__ == '__main__':
    # テスト
    handler_chain = ErrorHandlerChain()
    
    # ネットワークエラーのテスト
    try:
        raise ConnectionError("Network connection failed")
    except Exception as e:
        result = handler_chain.handle(e, url="https://example.com", retry_count=0)
        print(f"結果: {result.message}, リトライ: {result.should_retry}")
    
    # バリデーションエラーのテスト
    try:
        raise ValueError("Invalid input value")
    except Exception as e:
        result = handler_chain.handle(e, retry_count=0)
        print(f"結果: {result.message}, スキップ: {result.should_skip}")
