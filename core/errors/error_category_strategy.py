# -*- coding: utf-8 -*-
"""
エラーカテゴリ別戦略管理 - Context-Aware Strategy Pattern
"""

from typing import Dict, Any, Optional
from enum import Enum

# EnhancedErrorHandler からインポート
from core.errors.enhanced_error_handler import (
    ErrorCategory, RetryStrategy, FinalAction
)

class ErrorCategoryStrategy:
    """
    エラーカテゴリ別戦略管理
    
    設計原則:
    - Convention over Configuration: ユーザー設定を最小化
    - Context-Aware: エラー種別に応じた自動判断
    - Industry Standard: 業界標準のベストプラクティスを実装
    """
    
    # エラー別戦略定義（科学的根拠に基づく）
    STRATEGIES = {
        # ネットワーク関連
        ErrorCategory.NETWORK_TIMEOUT: {
            'retry': True,
            'max_retries': 5,
            'backoff': RetryStrategy.EXPONENTIAL,
            'base_delay': 5.0,
            'session_refresh_at': 3,  # 3回目でSession更新
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'ネットワークタイムアウト',
            'skip_reason': None
        },
        
        ErrorCategory.NETWORK_CONNECTION: {
            'retry': True,
            'max_retries': 5,
            'backoff': RetryStrategy.EXPONENTIAL,
            'base_delay': 5.0,
            'session_refresh_at': 2,  # 早めにSession更新
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': '接続エラー',
            'skip_reason': None
        },
        
        ErrorCategory.NETWORK_RATE_LIMIT: {
            'retry': True,
            'max_retries': 10,  # 多めにリトライ
            'backoff': RetryStrategy.EXPONENTIAL,
            'base_delay': 60.0,  # 長めの待機（レート制限回避）
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'レート制限（429）',
            'skip_reason': None
        },
        
        ErrorCategory.NETWORK_SERVER_ERROR: {
            'retry': True,
            'max_retries': 5,
            'backoff': RetryStrategy.EXPONENTIAL,
            'base_delay': 10.0,
            'session_refresh_at': 2,
            'selenium_fallback': True,
            'selenium_fallback_at': 3,  # 3回失敗後にSelenium試行
            'user_message': 'サーバーエラー (5xx)',
            'skip_reason': None
        },
        
        ErrorCategory.NETWORK_CLIENT_ERROR: {
            'retry': True,  # 403は認証エラーの可能性 → Selenium試行
            'max_retries': 1,  # 最小限のリトライ
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 1.0,
            'session_refresh_at': None,
            'selenium_fallback': True,
            'selenium_fallback_at': 0,  # 即座にSelenium試行（403対策）
            'user_message': 'クライアントエラー (4xx)',
            'skip_reason': '404の場合は画像が存在しません'
        },
        
        ErrorCategory.NETWORK_SSL: {
            'retry': True,
            'max_retries': 3,
            'backoff': RetryStrategy.FIXED,
            'base_delay': 5.0,
            'session_refresh_at': 1,  # すぐにSession更新
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'SSL/TLS エラー',
            'skip_reason': None
        },
        
        # ファイル関連
        ErrorCategory.FILE_PERMISSION: {
            'retry': False,
            'action': FinalAction.SKIP_IMAGE,
            'user_message': 'ファイル権限エラー',
            'skip_reason': '書き込み権限がありません'
        },
        
        ErrorCategory.FILE_NOT_FOUND: {
            'retry': True,
            'max_retries': 2,
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 1.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'ファイルが見つかりません',
            'skip_reason': 'ディレクトリが存在しない可能性'
        },
        
        ErrorCategory.FILE_DISK_FULL: {
            'retry': False,
            'action': FinalAction.ABORT,
            'user_message': 'ディスク容量不足',
            'skip_reason': '空き容量を確保してください'
        },
        
        ErrorCategory.FILE_LOCKED: {
            'retry': True,
            'max_retries': 5,
            'backoff': RetryStrategy.LINEAR,
            'base_delay': 2.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'ファイルがロックされています',
            'skip_reason': None
        },
        
        ErrorCategory.FILE_CORRUPT: {
            'retry': True,
            'max_retries': 2,
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 1.0,
            'session_refresh_at': 1,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'ファイル破損',
            'skip_reason': '再ダウンロードを試みます'
        },
        
        # パース・検証関連
        ErrorCategory.PARSING: {
            'retry': True,
            'max_retries': 2,
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 1.0,
            'session_refresh_at': None,
            'selenium_fallback': True,
            'selenium_fallback_at': 1,  # すぐにSelenium試行（HTMLパース失敗 → JS必要）
            'user_message': 'HTMLパースエラー',
            'skip_reason': 'ページ構造が変更された可能性'
        },
        
        ErrorCategory.VALIDATION: {
            'retry': True,
            'max_retries': 1,
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 1.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'データ検証エラー',
            'skip_reason': 'データが不正です'
        },
        
        # Selenium関連
        ErrorCategory.SELENIUM_DRIVER: {
            'retry': True,
            'max_retries': 3,
            'backoff': RetryStrategy.EXPONENTIAL,
            'base_delay': 10.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'Seleniumドライバーエラー',
            'skip_reason': 'ドライバーの再起動が必要'
        },
        
        ErrorCategory.SELENIUM_TIMEOUT: {
            'retry': True,
            'max_retries': 3,
            'backoff': RetryStrategy.LINEAR,
            'base_delay': 10.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'Seleniumタイムアウト',
            'skip_reason': None
        },
        
        ErrorCategory.SELENIUM_SCRIPT: {
            'retry': True,
            'max_retries': 2,
            'backoff': RetryStrategy.IMMEDIATE,
            'base_delay': 5.0,
            'session_refresh_at': None,
            'selenium_fallback': False,
            'selenium_fallback_at': None,
            'user_message': 'Seleniumスクリプトエラー',
            'skip_reason': 'JavaScriptの実行に失敗'
        },
        
        # 不明なエラー
        ErrorCategory.UNKNOWN: {
            'retry': True,
            'max_retries': 3,
            'backoff': RetryStrategy.LINEAR,
            'base_delay': 5.0,
            'session_refresh_at': 2,
            'selenium_fallback': True,
            'selenium_fallback_at': 3,
            'user_message': '不明なエラー',
            'skip_reason': 'エラーの詳細を確認してください'
        }
    }
    
    @classmethod
    def get_strategy(cls, category: ErrorCategory) -> Dict[str, Any]:
        """
        エラーカテゴリから戦略を取得
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            戦略辞書
        """
        return cls.STRATEGIES.get(
            category,
            cls.STRATEGIES[ErrorCategory.UNKNOWN]
        )
    
    @classmethod
    def should_retry(cls, category: ErrorCategory) -> bool:
        """
        リトライすべきか判断
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            True: リトライすべき, False: 即座にスキップ/中止
        """
        strategy = cls.get_strategy(category)
        return strategy.get('retry', False)
    
    @classmethod
    def get_max_retries(cls, category: ErrorCategory, user_max_retries: Optional[int] = None) -> int:
        """
        最大リトライ回数を取得
        
        Args:
            category: ErrorCategory インスタンス
            user_max_retries: ユーザー設定の最大リトライ回数（Noneの場合は戦略のデフォルト値）
            
        Returns:
            最大リトライ回数
        """
        strategy = cls.get_strategy(category)
        default_max = strategy.get('max_retries', 3)
        
        if user_max_retries is not None:
            # ユーザー設定がある場合は、デフォルト値の80%～120%の範囲で調整
            return max(1, min(user_max_retries, int(default_max * 1.2)))
        
        return default_max
    
    @classmethod
    def should_refresh_session(cls, category: ErrorCategory, retry_count: int) -> bool:
        """
        Session更新が必要か判断
        
        Args:
            category: ErrorCategory インスタンス
            retry_count: 現在のリトライ回数
            
        Returns:
            True: Session更新すべき, False: 不要
        """
        strategy = cls.get_strategy(category)
        refresh_at = strategy.get('session_refresh_at')
        
        if refresh_at is None:
            return False
        
        return retry_count >= refresh_at
    
    @classmethod
    def should_try_selenium(cls, category: ErrorCategory, retry_count: int) -> bool:
        """
        Selenium試行が必要か判断（早期適用判定）
        
        Args:
            category: ErrorCategory インスタンス
            retry_count: 現在のリトライ回数
            
        Returns:
            True: Selenium試行すべき, False: 不要
        """
        strategy = cls.get_strategy(category)
        
        if not strategy.get('selenium_fallback', False):
            return False
        
        selenium_at = strategy.get('selenium_fallback_at')
        
        if selenium_at is None:
            return False
        
        # selenium_fallback_at=0 の場合は即座にSelenium試行
        return retry_count >= selenium_at
    
    @classmethod
    def get_user_message(cls, category: ErrorCategory, retry_count: int, max_retries: int, delay: float) -> str:
        """
        ユーザー向けメッセージを生成
        
        Args:
            category: ErrorCategory インスタンス
            retry_count: 現在のリトライ回数
            max_retries: 最大リトライ回数
            delay: 待機時間（秒）
            
        Returns:
            ユーザー向けメッセージ
        """
        strategy = cls.get_strategy(category)
        base_message = strategy.get('user_message', 'エラー')
        
        if retry_count == 0:
            return f"{base_message}が発生しました"
        
        return f"{base_message} - {delay:.1f}秒後に再試行 (リトライ {retry_count}/{max_retries})"
    
    @classmethod
    def get_final_action(cls, category: ErrorCategory) -> FinalAction:
        """
        リトライ失敗時の最終アクションを取得
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            FinalAction インスタンス
        """
        strategy = cls.get_strategy(category)
        
        # リトライ不要なエラーの場合は、actionフィールドから取得
        if not strategy.get('retry', False):
            return strategy.get('action', FinalAction.SKIP_IMAGE)
        
        # リトライ可能なエラーの場合は、デフォルトで画像スキップ
        # （ファイル系エラーなど致命的な場合は戦略定義で上書き）
        if category in [ErrorCategory.FILE_DISK_FULL]:
            return FinalAction.ABORT
        
        return FinalAction.SKIP_IMAGE
    
    @classmethod
    def get_skip_reason(cls, category: ErrorCategory) -> Optional[str]:
        """
        スキップ理由を取得（ユーザーに表示）
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            スキップ理由（Noneの場合は理由なし）
        """
        strategy = cls.get_strategy(category)
        return strategy.get('skip_reason')
    
    @classmethod
    def get_backoff_strategy(cls, category: ErrorCategory) -> RetryStrategy:
        """
        バックオフ戦略を取得
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            RetryStrategy インスタンス
        """
        strategy = cls.get_strategy(category)
        return strategy.get('backoff', RetryStrategy.EXPONENTIAL)
    
    @classmethod
    def get_base_delay(cls, category: ErrorCategory) -> float:
        """
        ベース待機時間を取得
        
        Args:
            category: ErrorCategory インスタンス
            
        Returns:
            ベース待機時間（秒）
        """
        strategy = cls.get_strategy(category)
        return strategy.get('base_delay', 5.0)
