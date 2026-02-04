# -*- coding: utf-8 -*-
"""
統合エラーハンドリングシステム - エラー処理、リトライの統合管理
"""

import traceback
import time
import threading
import json
import os
import random
from typing import Dict, Any, Optional, List, Callable, Union
from enum import Enum
from datetime import datetime, timedelta

from core.interfaces import IStateManager, ILogger, IGUIOperations, IFileOperations, IAsyncExecutor
from core.errors.selenium_fallback_handler import SeleniumFallbackHandler

class ErrorSeverity(Enum):
    """エラーの深刻度"""
    LOW = "low"           # 軽微なエラー（リトライ可能）
    MEDIUM = "medium"     # 中程度のエラー（スキップ可能）
    HIGH = "high"         # 深刻なエラー（URLスキップ）
    CRITICAL = "critical" # 致命的エラー（シーケンス中止）

class ErrorPersistence(Enum):
    """エラーの永続性"""
    TEMPORARY = "temporary"  # 一時的エラー（リトライ有効）
    PERSISTENT = "persistent" # 永続的エラー（即座にスキップ）
    RECOVERABLE = "recoverable" # 復旧可能エラー（復旧処理実行）

class ErrorCategory(Enum):
    """エラーのカテゴリ（詳細分類）"""
    # ネットワーク関連
    NETWORK_CONNECTION = "network_connection"      # 接続エラー
    NETWORK_TIMEOUT = "network_timeout"           # タイムアウト
    NETWORK_RATE_LIMIT = "network_rate_limit"     # レート制限
    NETWORK_SERVER_ERROR = "network_server_error" # サーバーエラー（5xx）
    NETWORK_CLIENT_ERROR = "network_client_error" # クライアントエラー（4xx）
    NETWORK_SSL = "network_ssl"                   # SSL/TLS関連
    
    # ファイル関連
    FILE_PERMISSION = "file_permission"           # 権限エラー
    FILE_NOT_FOUND = "file_not_found"            # ファイル不存在
    FILE_DISK_FULL = "file_disk_full"            # ディスク容量不足
    FILE_LOCKED = "file_locked"                  # ファイルロック
    FILE_CORRUPT = "file_corrupt"                # ファイル破損
    
    # パース・検証関連
    PARSING = "parsing"                          # パース関連
    VALIDATION = "validation"                    # 検証関連
    
    # Selenium関連
    SELENIUM_DRIVER = "selenium_driver"          # ドライバー関連
    SELENIUM_TIMEOUT = "selenium_timeout"        # Seleniumタイムアウト
    SELENIUM_SCRIPT = "selenium_script"          # スクリプト実行エラー
    
    # その他
    UNKNOWN = "unknown"                          # 不明

class RetryStrategy(Enum):
    """リトライ戦略"""
    IMMEDIATE = "immediate"      # 即座にリトライ
    EXPONENTIAL = "exponential"  # 指数バックオフ
    LINEAR = "linear"           # 線形増加
    FIXED = "fixed"             # 固定間隔
    RANDOM = "random"           # ランダム間隔

class FinalAction(Enum):
    """最終的なアクション"""
    CONTINUE = "continue"       # 続行
    SKIP_IMAGE = "skip_image"   # 画像スキップ
    SKIP_URL = "skip_url"       # URLスキップ
    PAUSE = "pause"            # 一時停止
    ABORT = "abort"            # 中止
    MANUAL = "manual"          # 手動確認

class ErrorContext:
    """
    エラーコンテキスト情報（Phase 2: SRP準拠にリファクタリング）
    
    責務の分離:
    - エラー基本情報: url, stage, gallery_id
    - リトライ情報: retry_count, consecutive_errors
    - ページ情報: page_index, page_number (将来的にPageInfoクラスに分離)
    - 制御情報: critical_stage, selenium_enabled, user_action
    - 拡張情報: stage_data（ステージ固有のデータ）
    
    Note:
        将来的にはPageInfo, RetryInfo, ControlInfoなどに分離し、
        コンポジションを使用した設計に移行予定
    """
    def __init__(self, url: str = "", stage: str = "", gallery_id: str = "", 
                 page_index: int = 0, retry_count: int = 0, 
                 consecutive_errors: int = 0, critical_stage: bool = False,
                 selenium_enabled: bool = False, user_action: str = "", 
                 stage_data: Dict[str, Any] = None):
        # エラー基本情報
        self.url = url
        self.stage = stage
        self.gallery_id = gallery_id
        
        # ページ情報
        self.page_index = page_index
        self.page_number = None  # 現在のページ番号（オプション）
        
        # リトライ情報
        self.retry_count = retry_count
        self.consecutive_errors = consecutive_errors
        
        # 制御情報
        self.critical_stage = critical_stage
        self.selenium_enabled = selenium_enabled
        self.user_action = user_action
        
        # 拡張情報
        self.stage_data = stage_data or {}  # ステージ固有のデータ（画像URL、保存パスなど）
        
        # Selenium成功フラグ
        self.image_page_url = None  # リトライカウント管理用の画像ページURL
        self.is_selenium_success = False
        
        # タイムスタンプ
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'url': self.url,
            'stage': self.stage,
            'gallery_id': self.gallery_id,
            'page_index': self.page_index,
            'retry_count': self.retry_count,
            'consecutive_errors': self.consecutive_errors,
            'critical_stage': self.critical_stage,
            'selenium_enabled': self.selenium_enabled,
            'user_action': self.user_action,
            'stage_data': self.stage_data,
            'image_page_url': self.image_page_url,  # ⭐Phase 1: 追加⭐
            'page_number': self.page_number,        # ⭐Phase 1: 追加⭐
            'is_selenium_success': self.is_selenium_success,  # ⭐Phase 1: 追加⭐
            'timestamp': self.timestamp.isoformat()
        }

class ErrorStrategy:
    """エラー処理戦略"""
    def __init__(self, category: ErrorCategory, retry: bool = True, 
                 max_retries: int = 3, base_delay: float = 5.0,
                 retry_strategy: RetryStrategy = RetryStrategy.LINEAR,
                 after_retry_failure: FinalAction = FinalAction.SKIP_IMAGE,
                 recovery_method: str = "standard",
                 selenium_fallback: bool = False,
                 escalation_threshold: int = 5):
        self.category = category
        self.retry = retry
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retry_strategy = retry_strategy
        self.after_retry_failure = after_retry_failure
        self.recovery_method = recovery_method
        self.selenium_fallback = selenium_fallback
        self.escalation_threshold = escalation_threshold

class EnhancedErrorHandler:
    """統合エラーハンドリングシステム"""
    
    def __init__(self, 
                 state_manager: IStateManager,
                 logger: ILogger,
                 gui_operations: IGUIOperations,
                 file_operations: IFileOperations,
                 async_executor: IAsyncExecutor):
        self.state_manager = state_manager
        self.logger = logger
        self.gui_operations = gui_operations
        self.file_operations = file_operations
        self.async_executor = async_executor
        
        # エラー統計
        self.error_stats = {
            'total_errors': 0,
            'error_counts_by_category': {e.value: 0 for e in ErrorCategory},
            'error_counts_by_severity': {s.value: 0 for s in ErrorSeverity},
            'url_error_counts': {},
            'recovery_attempts': 0,
            'successful_recoveries': 0,
            'selenium_fallback_attempts': 0,
            'selenium_fallback_successes': 0,
            'retry_attempts': 0,
            'successful_retries': 0
        }
        
        # ⭐修正: ユーザー設定からエラー処理設定を読み取る⭐
        self.error_config = self._load_user_settings()
        
        # エラー処理戦略の定義（設定値を反映）
        self.error_strategies = self._initialize_error_strategies()
        
        # エラー処理ロック
        self.error_lock = threading.Lock()
        
        # アクティブなエラー処理セッション
        self.active_sessions = {}
        
        # エラー処理中フラグ（ロック不要、高速読み取り用）
        self._is_error_handling_active = False
        
        # ユーザー操作の監視
        self.user_operation_lock = threading.Lock()
        self.pending_user_operations = []
        
        # Selenium安全弁ハンドラーのインスタンス化
        self.selenium_handler = SeleniumFallbackHandler(
            state_manager=self.state_manager,
            logger=self.logger,
            error_config=self.error_config,
            error_stats=self.error_stats
        )
        
        # ⭐Phase 2: AutoRetryManager の初期化⭐
        from core.errors.auto_retry_manager import AutoRetryManager
        self.auto_retry_manager = AutoRetryManager(
            error_handler=self,
            state_manager=self.state_manager,
            logger=self.logger
        )
        
    def _load_user_settings(self) -> Dict[str, Any]:
        """ユーザー設定からエラー処理設定を読み取る"""
        try:
            # デフォルト値
            config = {
            'max_retry_attempts': 3,
            'retry_delay_base': 5.0,
            'retry_delay_max': 300.0,
            'retry_delay_multiplier': 2.0,
            'enable_auto_recovery': True,
            'enable_error_escalation': True,
            'enable_selenium_fallback': False,
            'selenium_timeout': 60,
            'consecutive_error_threshold': 5,
            'critical_stage_abort_threshold': 3
        }
        
            # ⭐修正: parentから直接max_retry_countを取得⭐
            # state_managerはparentを参照している可能性があるが、直接parentから取得する方が確実
            parent = None
            if hasattr(self.state_manager, 'parent'):
                parent = self.state_manager.parent
                self.logger.log(f"[設定読み込み] parentをstate_managerから取得: {type(parent).__name__}", "debug")
            elif hasattr(self.gui_operations, 'enhanced_max_retry_count') or hasattr(self.gui_operations, 'max_retry_count'):
                # gui_operationsがparentの場合
                parent = self.gui_operations
                self.logger.log(f"[設定読み込み] parentをgui_operationsから取得: {type(parent).__name__}", "debug")
            else:
                self.logger.log("[設定読み込み] parentを取得できませんでした", "warning")
            
            # ⭐修正: 統合エラーレジューム管理オプションの「5.レジューム設定」の最大リトライ回数を優先的に取得⭐
            max_retry_count = None
            if parent:
                # 1. enhanced_max_retry_countを優先的に取得（統合エラーレジューム管理オプション）
                if hasattr(parent, 'enhanced_max_retry_count'):
                    enhanced_max_retry_var = getattr(parent, 'enhanced_max_retry_count', None)
                    if enhanced_max_retry_var and hasattr(enhanced_max_retry_var, 'get'):
                        try:
                            max_retry_count = int(enhanced_max_retry_var.get())
                        except (ValueError, TypeError):
                            pass
                
                # 2. enhanced_max_retry_countが取得できない場合、max_retry_countを取得（後方互換性）
                if max_retry_count is None and hasattr(parent, 'max_retry_count'):
                    max_retry_var = getattr(parent, 'max_retry_count', None)
                    if max_retry_var and hasattr(max_retry_var, 'get'):
                        try:
                            max_retry_count = int(max_retry_var.get())
                        except (ValueError, TypeError):
                            pass
            
            # ⭐フォールバック: state_managerから取得（後方互換性）⭐
            if max_retry_count is None and hasattr(self.state_manager, 'max_retry_count'):
                max_retry_var = getattr(self.state_manager, 'max_retry_count', None)
                if max_retry_var and hasattr(max_retry_var, 'get'):
                    try:
                        max_retry_count = int(max_retry_var.get())
                    except (ValueError, TypeError):
                        pass
            
            # ⭐修正: 0の場合も設定する（0回リトライを許可）⭐
            if max_retry_count is not None and max_retry_count >= 0:
                config['max_retry_attempts'] = max_retry_count
                self.logger.log(f"[設定読み込み] 基準リトライ回数: {max_retry_count}回", "info")
            else:
                self.logger.log(f"[設定読み込み] 基準リトライ回数: デフォルト({config['max_retry_attempts']}回)", "warning")
            
            if hasattr(self.state_manager, 'auto_resume_delay'):
                delay_var = getattr(self.state_manager, 'auto_resume_delay', None)
                if delay_var and hasattr(delay_var, 'get'):
                    try:
                        delay = float(delay_var.get())
                        if delay > 0:
                            config['retry_delay_base'] = delay
                    except (ValueError, TypeError):
                        pass
            
            if hasattr(self.state_manager, 'retry_delay_increment'):
                increment_var = getattr(self.state_manager, 'retry_delay_increment', None)
                if increment_var and hasattr(increment_var, 'get'):
                    try:
                        increment = float(increment_var.get())
                        if increment > 0:
                            config['retry_delay_multiplier'] = 1.0 + (increment / config['retry_delay_base']) if config['retry_delay_base'] > 0 else 2.0
                    except (ValueError, TypeError):
                        pass
            
            if hasattr(self.state_manager, 'max_retry_delay'):
                max_delay_var = getattr(self.state_manager, 'max_retry_delay', None)
                if max_delay_var and hasattr(max_delay_var, 'get'):
                    try:
                        max_delay = float(max_delay_var.get())
                        if max_delay > 0:
                            config['retry_delay_max'] = max_delay
                    except (ValueError, TypeError):
                        pass
            
            # ⭐追加: selenium_fallback_enabledとselenium_timeoutを読み込む⭐
            if hasattr(self.state_manager, 'selenium_fallback_enabled'):
                selenium_fallback_var = getattr(self.state_manager, 'selenium_fallback_enabled', None)
                if selenium_fallback_var and hasattr(selenium_fallback_var, 'get'):
                    try:
                        config['enable_selenium_fallback'] = bool(selenium_fallback_var.get())
                    except (ValueError, TypeError):
                        pass
            
            if hasattr(self.state_manager, 'selenium_timeout'):
                selenium_timeout_var = getattr(self.state_manager, 'selenium_timeout', None)
                if selenium_timeout_var and hasattr(selenium_timeout_var, 'get'):
                    try:
                        selenium_timeout = int(selenium_timeout_var.get())
                        if selenium_timeout > 0:
                            config['selenium_timeout'] = selenium_timeout
                    except (ValueError, TypeError):
                        pass
            
            # ⭐追加: Seleniumオプション設定を読み取る⭐
            config['selenium_manager_enabled'] = False
            config['selenium_stop_chrome_background'] = False
            config['selenium_cleanup_temp'] = False
            config['selenium_use_registry_version'] = True  # レジストリからバージョンを取得（デフォルトON）
            config['selenium_minimal_options'] = False  # 最小限のオプションで起動（競合回避用）
            
            # ⭐追加: Seleniumテストモード設定を読み取る⭐
            config['selenium_test_minimal_options'] = False
            config['selenium_test_no_headless'] = False
            
            # state_managerから親オブジェクトを取得して設定を読み取る
            if hasattr(self.state_manager, 'parent'):
                parent = self.state_manager.parent
                if parent:
                    # Selenium Managerオプション
                    if hasattr(parent, 'selenium_manager_enabled'):
                        manager_var = getattr(parent, 'selenium_manager_enabled', None)
                        if manager_var and hasattr(manager_var, 'get'):
                            try:
                                config['selenium_manager_enabled'] = bool(manager_var.get())
                            except (ValueError, TypeError):
                                pass
                    
                    # Chromeバックグラウンドプロセス停止オプション
                    if hasattr(parent, 'selenium_stop_chrome_background'):
                        stop_bg_var = getattr(parent, 'selenium_stop_chrome_background', None)
                        if stop_bg_var and hasattr(stop_bg_var, 'get'):
                            try:
                                config['selenium_stop_chrome_background'] = bool(stop_bg_var.get())
                            except (ValueError, TypeError):
                                pass
                    
                    # Seleniumオプション（通常DLでも使用）
                    if hasattr(parent, 'selenium_cleanup_temp'):
                        cleanup_var = getattr(parent, 'selenium_cleanup_temp', None)
                        if cleanup_var and hasattr(cleanup_var, 'get'):
                            try:
                                config['selenium_cleanup_temp'] = bool(cleanup_var.get())
                            except (ValueError, TypeError):
                                pass
                    
                    # 最小限のオプションで起動（競合回避用）
                    if hasattr(parent, 'selenium_minimal_options'):
                        minimal_var = getattr(parent, 'selenium_minimal_options', None)
                        if minimal_var and hasattr(minimal_var, 'get'):
                            try:
                                config['selenium_minimal_options'] = bool(minimal_var.get())
                            except (ValueError, TypeError):
                                pass
                    
                    # Seleniumテストモード設定
                    if hasattr(parent, 'selenium_test_minimal_options'):
                        test_minimal_var = getattr(parent, 'selenium_test_minimal_options', None)
                        if test_minimal_var and hasattr(test_minimal_var, 'get'):
                            try:
                                config['selenium_test_minimal_options'] = bool(test_minimal_var.get())
                            except (ValueError, TypeError):
                                pass
                    
                    if hasattr(parent, 'selenium_test_no_headless'):
                        test_no_headless_var = getattr(parent, 'selenium_test_no_headless', None)
                        if test_no_headless_var and hasattr(test_no_headless_var, 'get'):
                            try:
                                config['selenium_test_no_headless'] = bool(test_no_headless_var.get())
                            except (ValueError, TypeError):
                                pass
            
            # ⭐追加: retry_strategyを読み込む⭐
            if hasattr(self.state_manager, 'retry_strategy'):
                retry_strategy_var = getattr(self.state_manager, 'retry_strategy', None)
                if retry_strategy_var and hasattr(retry_strategy_var, 'get'):
                    try:
                        config['retry_strategy'] = retry_strategy_var.get()
                    except (ValueError, TypeError):
                        pass
            
            return config
            
        except Exception as e:
            self.logger.log(f"ユーザー設定読み込みエラー: {e}", "error")
            # デフォルト値を返す
            return {
                'max_retry_attempts': 3,
                'retry_delay_base': 5.0,
                'retry_delay_max': 300.0,
                'retry_delay_multiplier': 2.0,
                'enable_auto_recovery': True,
                'enable_error_escalation': True,
                'enable_selenium_fallback': False,
                'selenium_timeout': 60,
                'consecutive_error_threshold': 5,
                'critical_stage_abort_threshold': 3
            }
        
    def _initialize_error_strategies(self) -> Dict[ErrorCategory, ErrorStrategy]:
        """エラー処理戦略の初期化（ユーザー設定を反映）"""
        # ⭐修正: ユーザー設定のmax_retry_attemptsを使用⭐
        user_max_retries = self.error_config.get('max_retry_attempts', 3)
        user_base_delay = self.error_config.get('retry_delay_base', 5.0)
        
        # ⭐追加: ユーザー設定のretry_strategyを読み取る⭐
        user_retry_strategy_str = self.error_config.get('retry_strategy', 'linear')
        # 文字列をRetryStrategy enumに変換
        strategy_mapping = {
            'linear': RetryStrategy.LINEAR,
            'exponential': RetryStrategy.EXPONENTIAL,
            'fixed': RetryStrategy.FIXED,
            'immediate': RetryStrategy.IMMEDIATE,
            'random': RetryStrategy.RANDOM
        }
        user_retry_strategy = strategy_mapping.get(user_retry_strategy_str.lower(), RetryStrategy.LINEAR)
        
        strategies = {}
        
        # ⭐修正: ユーザー設定のmax_retriesを使用（カテゴリごとの比率を維持）⭐
        # ネットワーク関連エラー
        strategies[ErrorCategory.NETWORK_CONNECTION] = ErrorStrategy(
            category=ErrorCategory.NETWORK_CONNECTION,
            retry=True, max_retries=max(user_max_retries, 3), base_delay=max(user_base_delay * 2, 10.0),
            retry_strategy=RetryStrategy.EXPONENTIAL,
            after_retry_failure=FinalAction.SKIP_URL,
            recovery_method="session_reset",
            selenium_fallback=True
        )
        
        strategies[ErrorCategory.NETWORK_TIMEOUT] = ErrorStrategy(
            category=ErrorCategory.NETWORK_TIMEOUT,
            retry=True, max_retries=user_max_retries, base_delay=user_base_delay,
            retry_strategy=RetryStrategy.LINEAR,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="timeout_increase",
            selenium_fallback=True
        )
        
        strategies[ErrorCategory.NETWORK_RATE_LIMIT] = ErrorStrategy(
            category=ErrorCategory.NETWORK_RATE_LIMIT,
            retry=True, max_retries=max(user_max_retries - 1, 2), base_delay=300.0,
            retry_strategy=RetryStrategy.FIXED,
            after_retry_failure=FinalAction.PAUSE,
            recovery_method="wait_and_retry",
            selenium_fallback=False
        )
        
        strategies[ErrorCategory.NETWORK_SERVER_ERROR] = ErrorStrategy(
            category=ErrorCategory.NETWORK_SERVER_ERROR,
            retry=True, max_retries=user_max_retries, base_delay=max(user_base_delay * 6, 30.0),
            retry_strategy=RetryStrategy.EXPONENTIAL,
            after_retry_failure=FinalAction.SKIP_URL,
            recovery_method="selenium_fallback",
            selenium_fallback=True
        )
        
        strategies[ErrorCategory.NETWORK_CLIENT_ERROR] = ErrorStrategy(
            category=ErrorCategory.NETWORK_CLIENT_ERROR,
            retry=False,
            after_retry_failure=FinalAction.SKIP_URL,
            recovery_method="manual_intervention"
        )
        
        strategies[ErrorCategory.NETWORK_SSL] = ErrorStrategy(
            category=ErrorCategory.NETWORK_SSL,
            retry=True, max_retries=user_max_retries, base_delay=user_base_delay,
            retry_strategy=user_retry_strategy,  # ユーザー設定のretry_strategyを使用
            after_retry_failure=FinalAction.SKIP_URL,
            recovery_method="ssl_config_adjustment",
            selenium_fallback=True
        )
        
        # ファイル関連エラー
        strategies[ErrorCategory.FILE_PERMISSION] = ErrorStrategy(
            category=ErrorCategory.FILE_PERMISSION,
            retry=False,
            after_retry_failure=FinalAction.ABORT,
            recovery_method="manual_intervention"
        )
        
        strategies[ErrorCategory.FILE_DISK_FULL] = ErrorStrategy(
            category=ErrorCategory.FILE_DISK_FULL,
            retry=False,
            after_retry_failure=FinalAction.ABORT,
            recovery_method="cleanup_and_retry"
        )
        
        strategies[ErrorCategory.FILE_NOT_FOUND] = ErrorStrategy(
            category=ErrorCategory.FILE_NOT_FOUND,
            retry=True, max_retries=max(user_max_retries - 1, 2), base_delay=1.0,
            retry_strategy=RetryStrategy.IMMEDIATE,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="directory_creation"
        )
        
        # パース・検証関連エラー
        strategies[ErrorCategory.PARSING] = ErrorStrategy(
            category=ErrorCategory.PARSING,
            retry=True, max_retries=max(user_max_retries - 1, 2), base_delay=2.0,
            retry_strategy=RetryStrategy.IMMEDIATE,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="selenium_fallback",
            selenium_fallback=True
        )
        
        strategies[ErrorCategory.VALIDATION] = ErrorStrategy(
            category=ErrorCategory.VALIDATION,
            retry=True, max_retries=1, base_delay=1.0,
            retry_strategy=RetryStrategy.IMMEDIATE,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="data_validation_retry"
        )
        
        # Selenium関連エラー
        strategies[ErrorCategory.SELENIUM_DRIVER] = ErrorStrategy(
            category=ErrorCategory.SELENIUM_DRIVER,
            retry=True, max_retries=max(user_max_retries - 1, 2), base_delay=10.0,
            retry_strategy=RetryStrategy.EXPONENTIAL,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="driver_reinitialization"
        )
        
        strategies[ErrorCategory.SELENIUM_TIMEOUT] = ErrorStrategy(
            category=ErrorCategory.SELENIUM_TIMEOUT,
            retry=True, max_retries=max(user_max_retries - 1, 2), base_delay=user_base_delay,
            retry_strategy=RetryStrategy.LINEAR,
            after_retry_failure=FinalAction.SKIP_IMAGE,
            recovery_method="timeout_adjustment"
        )
        
        # 不明なエラー
        # ⭐修正: UNKNOWNカテゴリでもユーザー設定のmax_retriesをそのまま使用（-1しない）⭐
        # ⭐修正: retry_strategyをユーザー設定から読み取る⭐
        strategies[ErrorCategory.UNKNOWN] = ErrorStrategy(
            category=ErrorCategory.UNKNOWN,
            retry=True, max_retries=user_max_retries, base_delay=user_base_delay,
            retry_strategy=user_retry_strategy,
            after_retry_failure=FinalAction.PAUSE,
            recovery_method="generic_retry",
            selenium_fallback=True
        )
        
        return strategies
    
    def handle_error_with_retry(self, 
                               func: callable,
                               context: ErrorContext,
                               max_retries: int = None) -> Dict[str, Any]:
        """
        ⭐Phase 2: リトライ付きエラーハンドリング（推奨メソッド）⭐
        
        Self-Contained Retry Logic + Circuit Breaker Pattern
        
        Args:
            func: 実行する関数（例: lambda: download_image(url)）
            context: ErrorContext インスタンス
            max_retries: 最大リトライ回数（Noneの場合はユーザー設定から取得）
            
        Returns:
            {
                'success': bool,        # 成功/失敗
                'data': Any,           # 成功時のデータ
                'action': FinalAction, # 失敗時のアクション
                'error': Exception,    # 失敗時のエラー
                'reason': str          # 失敗理由
            }
            
        Example:
            # ダウンロード処理をリトライ付きで実行
            result = error_handler.handle_error_with_retry(
                lambda: download_image(image_url),
                ErrorContext(url=image_url, ...),
                max_retries=5
            )
            
            if result['success']:
                image_data = result['data']
            else:
                if result['action'] == FinalAction.PAUSE:
                    # Circuit Breaker発動 → 一時停止
                    break
                elif result['action'] == FinalAction.SKIP_IMAGE:
                    # 画像スキップ
                    continue
        """
        try:
            # max_retries未指定の場合はユーザー設定から取得
            if max_retries is None:
                max_retries = self.error_config.get('max_retries', 3)
            
            # AutoRetryManager に委譲
            result = self.auto_retry_manager.execute_with_retry(
                func, context, max_retries
            )
            
            return result
            
        except Exception as e:
            self.logger.log(
                f"[handle_error_with_retry] 予期しないエラー: {e}",
                "error"
            )
            import traceback
            self.logger.log(
                f"詳細: {traceback.format_exc()}",
                "error"
            )
            return {
                'success': False,
                'action': FinalAction.ABORT,
                'error': e,
                'reason': 'unexpected_error'
            }
    
    def handle_error(self, error: Exception, context: ErrorContext) -> str:
        """メインエラーハンドリングエントリーポイント（レガシー互換用）"""
        try:
            # エラー処理開始フラグを設定
            self._is_error_handling_active = True
            try:
                with self.error_lock:
                    # ユーザー操作の確認
                    if self._check_pending_user_operations(context):
                        result = self._handle_user_operation_interruption(context)
                    # ⭐修正: Noneが返された場合は通常のエラー処理を続行⭐
                        if result is not None:
                            return result
                    # Noneの場合は下記の通常エラー処理に進む
                
                # エラー統計の更新
                self._update_error_stats(error, context)
                
                # エラーの分析
                error_analysis = self._analyze_error(error, context)
                
                # エラーログの出力
                self._log_error(error, error_analysis, context)
                
                # エラー処理戦略の実行
                result = self._execute_error_strategy(error, error_analysis, context)
                
                
                # 結果の記録
                self._record_error_result(result, error_analysis, context)
                
                return result
            finally:
                # エラー処理完了フラグをリセット
                self._is_error_handling_active = False
                
        except Exception as e:
            self.logger.log(f"[エラーハンドリング] handle_errorで例外発生: {e}", "error")
            import traceback
            self.logger.log(f"[エラーハンドリング] 例外詳細: {traceback.format_exc()}", "error")
            self._is_error_handling_active = False
            return FinalAction.ABORT.value
    
    def is_error_handling_active(self) -> bool:
        """エラー処理がアクティブかどうかを確認（ロック不要、高速読み取り）"""
        return self._is_error_handling_active
    
    def _check_pending_user_operations(self, context: ErrorContext) -> bool:
        """保留中のユーザー操作を確認"""
        try:
            self.logger.log(f"[エラーハンドリング] ユーザー操作ロック取得開始", "info")
            with self.user_operation_lock:
                self.logger.log(f"[エラーハンドリング] ユーザー操作ロック取得完了", "info")
                if self.pending_user_operations:
                    operation = self.pending_user_operations.pop(0)
                    context.user_action = operation
                    self.logger.log(f"[エラーハンドリング] ユーザー操作検出: {operation}", "info")
                    return True
            self.logger.log(f"[エラーハンドリング] 保留中のユーザー操作なし", "info")
            return False
        except Exception as e:
            self.logger.log(f"[エラーハンドリング] ユーザー操作確認エラー: {e}", "error")
            import traceback
            self.logger.log(f"[エラーハンドリング] 例外詳細: {traceback.format_exc()}", "error")
            return False
    
    def _handle_user_operation_interruption(self, context: ErrorContext) -> str:
        """ユーザー操作による中断処理"""
        try:
            operation = context.user_action
            
            # ⭐修正: 'start'操作はエラー処理中は無視（初回起動時のみ有効）⭐
            if operation == "start":
                # エラー処理中の'start'操作は無視してNoneを返す
                self.logger.log("ユーザーによる開始操作が検出されましたが、エラー処理中のため無視します", "debug")
                return None  # Noneを返すことで、通常のエラー処理フローに戻る
            elif operation == "pause":
                self.logger.log("ユーザーによる一時停止が検出されました", "info")
                return FinalAction.PAUSE.value
            elif operation == "stop":
                self.logger.log("ユーザーによる停止が検出されました", "info")
                return FinalAction.ABORT.value
            elif operation == "skip_url":
                self.logger.log("ユーザーによるURLスキップが検出されました", "info")
                return FinalAction.SKIP_URL.value
            elif operation == "skip_image":
                self.logger.log("ユーザーによる画像スキップが検出されました", "info")
                return FinalAction.SKIP_IMAGE.value
            elif operation == "resume":
                # 再開操作は継続を意味する
                self.logger.log("ユーザーによる再開操作が検出されました", "debug")
                return FinalAction.CONTINUE.value
            elif operation == "pause":
                # 中断操作
                self.logger.log("ユーザーによる中断操作が検出されました", "info")
                return FinalAction.PAUSE.value
            else:
                self.logger.log(f"不明なユーザー操作: {operation}", "warning")
                return FinalAction.CONTINUE.value
                
        except Exception as e:
            self.logger.log(f"ユーザー操作処理エラー: {e}", "error")
            return FinalAction.ABORT.value
    
    def register_user_operation(self, operation: str):
        """ユーザー操作を登録"""
        try:
            with self.user_operation_lock:
                self.pending_user_operations.append(operation)
                self.logger.log(f"ユーザー操作を登録: {operation}", "debug")
        except Exception as e:
            self.logger.log(f"ユーザー操作登録エラー: {e}", "error")
    
    def _update_error_stats(self, error: Exception, context: ErrorContext):
        """エラー統計の更新"""
        try:
            self.error_stats['total_errors'] += 1
            category = self._classify_error(error)
            if category.value not in self.error_stats['by_category']:
                self.error_stats['by_category'][category.value] = 0
            self.error_stats['by_category'][category.value] += 1
            
            # ⭐追加: エラー統計更新後にGUIを即座に更新⭐
            self._update_error_stats_gui()
        except Exception as e:
            self.logger.log(f"エラー統計更新エラー: {e}", "error")
    
    def _update_error_stats_gui(self):
        """エラー統計のGUI更新（非ブロッキング）"""
        try:
            if hasattr(self.state_manager, 'options_panel') and hasattr(self.state_manager.options_panel, '_update_error_statistics'):
                # 非同期でGUIを更新（メインスレッドで実行）
                if hasattr(self.state_manager, 'root'):
                    self.state_manager.root.after(0, self.state_manager.options_panel._update_error_statistics)
        except Exception as e:
            # GUI更新エラーは致命的ではないので、ログレベルをdebugに
            self.logger.log(f"エラー統計GUI更新エラー: {e}", "debug")
    
    def _log_error(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext):
        """エラーログの出力"""
        try:
            category = analysis['category']
            severity = analysis['severity']
            error_message = analysis['error_message']
            
            # ログレベルの決定
            if severity == ErrorSeverity.CRITICAL:
                log_level = "error"
            elif severity == ErrorSeverity.HIGH:
                log_level = "error"
            elif severity == ErrorSeverity.MEDIUM:
                log_level = "warning"
            else:
                log_level = "info"
            
            # ⭐修正: 初回エラー時（retry_count == 1）に強調表示⭐
            if context.retry_count == 1:
                self.logger.log("", "error")
                self.logger.log("═══════════════════════════════════════════════════════════", "error")
                self.logger.log(f"❌ エラー発生: {error_message[:80]}", "error")
                self.logger.log("═══════════════════════════════════════════════════════════", "error")
            
            # ログメッセージの構築
            log_message = f"[{category.value}] {error_message}"
            if context.url:
                log_message += f" (URL: {context.url[:50]}...)" if len(context.url) > 50 else f" (URL: {context.url})"
            if context.stage:
                log_message += f" (Stage: {context.stage})"
            if context.retry_count > 0:
                log_message += f" (Retry: {context.retry_count})"
            
            self.logger.log(log_message, log_level)
            
        except Exception as e:
            self.logger.log(f"エラーログ出力エラー: {e}", "error")
    
    def _execute_error_strategy(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """エラー処理戦略の実行"""
        try:
            category = analysis['category']
            
            # エスカレーションが必要な場合
            if analysis['needs_escalation']:
                return self._escalate_error(error, analysis, context)
            
            # リトライ可能な場合
            if analysis['is_retryable']:
                # リトライ上限チェック
                strategy = self.error_strategies.get(category)
                if strategy and context.retry_count >= strategy.max_retries:
                    # リトライ上限達成 - Selenium安全弁または最終アクション
                    if analysis.get('selenium_applicable', False) and strategy.selenium_fallback:
                        selenium_result = self._apply_selenium_fallback(error, analysis, context)
                        if selenium_result == 'success':
                            return FinalAction.CONTINUE.value
                    return self._get_final_action(analysis, context)
                
                # リトライ継続
                return FinalAction.CONTINUE.value
            
            # 復旧可能な場合
            if analysis['is_recoverable']:
                return FinalAction.CONTINUE.value
            
            # デフォルトアクション
            return self._get_final_action(analysis, context)
            
        except Exception as e:
            self.logger.log(f"エラー処理戦略実行エラー: {e}", "error")
            import traceback
            self.logger.log(f"詳細: {traceback.format_exc()}", "error")
            return FinalAction.ABORT.value
    
    def _record_error_result(self, result: str, analysis: Dict[str, Any], context: ErrorContext):
        """エラー結果の記録"""
        try:
            # 成功した場合の統計更新
            if result == FinalAction.CONTINUE.value:
                if analysis.get('selenium_applicable', False):
                    self.error_stats['selenium_fallback_successes'] += 1
                else:
                    self.error_stats['successful_recoveries'] += 1
            
            # エラー結果のログ出力
            self.logger.log(f"エラー処理結果: {result}", "debug")
            
        except Exception as e:
            self.logger.log(f"エラー結果記録エラー: {e}", "error")
    
    def _get_final_action(self, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """最終アクションの決定"""
        try:
            category = analysis['category']
            strategy = self.error_strategies.get(category)
            
            if strategy:
                return strategy.after_retry_failure.value
            
            # デフォルトアクション
            return FinalAction.SKIP_IMAGE.value
            
        except Exception as e:
            self.logger.log(f"最終アクション決定エラー: {e}", "error")
            return FinalAction.ABORT.value
    
    def _apply_selenium_fallback(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """Selenium安全弁の適用"""
        try:
            # _execute_selenium_fallbackメソッドを呼び出す
            return self._execute_selenium_fallback(error, analysis, context)
        except Exception as e:
            self.logger.log(f"Selenium安全弁適用エラー: {e}", "error")
            return 'failed'
    
    def _assess_severity(self, error: Exception, context: ErrorContext) -> ErrorSeverity:
        """エラーの深刻度評価"""
        try:
            error_name = type(error).__name__
            error_message = str(error).lower()
            
            # デバッグログ
            self.logger.log(f"[DEBUG] _assess_severity: error_name={error_name}, critical_stage={context.critical_stage}, consecutive_errors={context.consecutive_errors}", "info")
            
            # 致命的エラー
            if error_name in ['SystemExit', 'KeyboardInterrupt', 'MemoryError']:
                self.logger.log(f"[DEBUG] _assess_severity: CRITICAL (fatal error)", "info")
                return ErrorSeverity.CRITICAL
            
            # 深刻なエラー
            if (error_name in ['SystemError'] or
                'critical' in error_message or
                'fatal' in error_message or
                context.critical_stage):
                self.logger.log(f"[DEBUG] _assess_severity: HIGH (critical_stage={context.critical_stage})", "info")
                return ErrorSeverity.HIGH
            
            # 中程度のエラー
            if (error_name in ['ConnectionError', 'TimeoutError'] or
                'timeout' in error_message or
                'connection' in error_message or
                context.consecutive_errors >= 3):
                self.logger.log(f"[DEBUG] _assess_severity: MEDIUM", "info")
                return ErrorSeverity.MEDIUM
            
            # 軽微なエラー
            if (error_name in ['ValueError', 'KeyError'] or
                'validation' in error_message or
                'invalid' in error_message):
                self.logger.log(f"[DEBUG] _assess_severity: LOW", "info")
                return ErrorSeverity.LOW
            
            # デフォルト
            self.logger.log(f"[DEBUG] _assess_severity: MEDIUM (default)", "info")
            return ErrorSeverity.MEDIUM
            
        except Exception as e:
            self.logger.log(f"エラー深刻度評価エラー: {e}", "error")
            import traceback
            self.logger.log(f"詳細: {traceback.format_exc()}", "error")
            return ErrorSeverity.HIGH
    
    def _assess_persistence(self, error: Exception, category: ErrorCategory, context: ErrorContext) -> ErrorPersistence:
        """エラーの永続性評価"""
        try:
            # カテゴリによる永続性
            temporary_categories = [
                ErrorCategory.NETWORK_CONNECTION,
                ErrorCategory.NETWORK_TIMEOUT,
                ErrorCategory.NETWORK_SERVER_ERROR
            ]
            
            persistent_categories = [
                ErrorCategory.FILE_PERMISSION,
                ErrorCategory.FILE_DISK_FULL,
                ErrorCategory.FILE_CORRUPT
            ]
            
            if category in temporary_categories:
                return ErrorPersistence.TEMPORARY
            elif category in persistent_categories:
                return ErrorPersistence.PERSISTENT
            else:
                return ErrorPersistence.RECOVERABLE
                
        except Exception as e:
            self.logger.log(f"永続性評価エラー: {e}", "error")
            return ErrorPersistence.RECOVERABLE
    
    def _analyze_error(self, error: Exception, context: ErrorContext) -> Dict[str, Any]:
        """エラーの詳細分析"""
        try:
            # エラーの分類
            category = self._classify_error(error)
            severity = self._assess_severity(error, context)
            persistence = self._assess_persistence(error, category, context)
            
            # リトライ可能性の判定
            is_retryable = self._is_retryable_error(error, category, context)
            
            # 復旧可能性の判定
            is_recoverable = self._is_recoverable_error(error, category, context)
            
            # エスカレーション必要かの判定
            needs_escalation = self._needs_escalation(error, category, severity, context)
            
            # Selenium安全弁の適用可能性
            selenium_applicable = self._is_selenium_applicable(error, category, context)
            
            # デバッグログ
            self.logger.log(f"[DEBUG] エラー分析結果: category={category.value}, severity={severity.value}, is_retryable={is_retryable}, needs_escalation={needs_escalation}, retry_count={context.retry_count}", "info")
            
            return {
                'category': category,
                'severity': severity,
                'persistence': persistence,
                'is_retryable': is_retryable,
                'is_recoverable': is_recoverable,
                'needs_escalation': needs_escalation,
                'selenium_applicable': selenium_applicable,
                'error_type': type(error).__name__,
                'error_message': str(error),
                'context': context.to_dict()
            }
            
        except Exception as e:
            self.logger.log(f"エラー分析エラー: {e}", "error")
            return {
                'category': ErrorCategory.UNKNOWN,
                'severity': ErrorSeverity.CRITICAL,
                'persistence': ErrorPersistence.PERSISTENT,
                'is_retryable': False,
                'is_recoverable': False,
                'needs_escalation': True,
                'selenium_applicable': False,
                'error_type': 'AnalysisError',
                'error_message': str(e),
                'context': context.to_dict()
            }
    
    def _classify_error(self, error: Exception) -> ErrorCategory:
        """エラーの詳細分類"""
        try:
            error_name = type(error).__name__
            error_message = str(error).lower()
            
            # ⭐追加: DownloadErrorExceptionの場合、メッセージ内のエラーをチェック⭐
            if error_name == 'DownloadErrorException':
                # メッセージ内にSSLErrorやDH_KEY_TOO_SMALLが含まれているかチェック
                if 'ssl' in error_message or 'dh_key_too_small' in error_message:
                    return ErrorCategory.NETWORK_SSL
                elif 'timeout' in error_message:
                    return ErrorCategory.NETWORK_TIMEOUT
                elif 'connection' in error_message:
                    return ErrorCategory.NETWORK_CONNECTION
            
            # 既存の画像スキップ機能との整合性を保つため、SkipUrlExceptionを特別扱い
            if error_name == 'SkipUrlException':
                return ErrorCategory.UNKNOWN  # 既存の処理に委ねる
            
            # ネットワーク関連エラーの詳細分類
            elif error_name in ['ConnectionError', 'URLError', 'SSLError']:
                if 'timeout' in error_message:
                    return ErrorCategory.NETWORK_TIMEOUT
                elif 'ssl' in error_message or 'certificate' in error_message or 'dh_key_too_small' in error_message:
                    return ErrorCategory.NETWORK_SSL
                else:
                    return ErrorCategory.NETWORK_CONNECTION
            
            # ⭐追加: requests.exceptions.SSLErrorの直接チェック⭐
            elif 'requests' in str(type(error)) and 'SSLError' in error_name:
                if 'dh_key_too_small' in error_message:
                    return ErrorCategory.NETWORK_SSL
                return ErrorCategory.NETWORK_SSL
            
            elif error_name == 'TimeoutError':
                return ErrorCategory.NETWORK_TIMEOUT
            
            elif error_name == 'HTTPError':
                if '429' in error_message:  # Too Many Requests
                    return ErrorCategory.NETWORK_RATE_LIMIT
                elif '5' in error_message[:3]:  # 5xx errors
                    return ErrorCategory.NETWORK_SERVER_ERROR
                elif '4' in error_message[:3]:  # 4xx errors
                    return ErrorCategory.NETWORK_CLIENT_ERROR
                else:
                    return ErrorCategory.NETWORK_CONNECTION
            
            # ファイル関連エラーの詳細分類
            elif error_name == 'PermissionError':
                return ErrorCategory.FILE_PERMISSION
            elif error_name == 'FileNotFoundError':
                return ErrorCategory.FILE_NOT_FOUND
            elif error_name == 'OSError':
                if 'no space left' in error_message:
                    return ErrorCategory.FILE_DISK_FULL
                elif 'permission denied' in error_message:
                    return ErrorCategory.FILE_PERMISSION
                elif 'file is locked' in error_message:
                    return ErrorCategory.FILE_LOCKED
                else:
                    return ErrorCategory.FILE_NOT_FOUND
            
            # Selenium関連エラーの分類
            elif 'selenium' in error_message or 'WebDriver' in error_name:
                if 'timeout' in error_message:
                    return ErrorCategory.SELENIUM_TIMEOUT
                elif 'driver' in error_message:
                    return ErrorCategory.SELENIUM_DRIVER
                else:
                    return ErrorCategory.SELENIUM_SCRIPT
            
            # パース・検証関連エラー
            elif error_name in ['ValueError', 'KeyError', 'AttributeError']:
                if 'validation' in error_message or 'invalid' in error_message:
                    return ErrorCategory.VALIDATION
                else:
                    return ErrorCategory.PARSING
            
            return ErrorCategory.UNKNOWN
            
        except Exception as e:
            self.logger.log(f"エラー分類エラー: {e}", "error")
            return ErrorCategory.UNKNOWN
    
    def _is_retryable_error(self, error: Exception, category: ErrorCategory, context: ErrorContext) -> bool:
        """リトライ可能なエラーかどうかの判定"""
        try:
            # ⭐修正: 戦略のmax_retriesとerror_configのmax_retry_attemptsの両方をチェック⭐
            strategy = self.error_strategies.get(category)
            max_retries = strategy.max_retries if strategy else self.error_config['max_retry_attempts']
            
            # retry_countは「これまでに実行したリトライ回数」
            # max_retries=3 の場合、retry_count < 3 の時点でリトライ可能
            if context.retry_count >= max_retries:
                return False
            
            # カテゴリ別のリトライ可能性
            if strategy:
                return strategy.retry
            
            # デフォルトの判定
            retryable_categories = {
                ErrorCategory.NETWORK_CONNECTION: True,
                ErrorCategory.NETWORK_TIMEOUT: True,
                ErrorCategory.NETWORK_SERVER_ERROR: True,
                ErrorCategory.NETWORK_SSL: True,
                ErrorCategory.FILE_NOT_FOUND: True,
                ErrorCategory.PARSING: True,
                ErrorCategory.VALIDATION: True,
                ErrorCategory.SELENIUM_DRIVER: True,
                ErrorCategory.SELENIUM_TIMEOUT: True,
                ErrorCategory.UNKNOWN: True
            }
            
            return retryable_categories.get(category, False)
            
        except Exception as e:
            self.logger.log(f"リトライ可能性判定エラー: {e}", "error")
            return False
    
    def _is_recoverable_error(self, error: Exception, category: ErrorCategory, context: ErrorContext) -> bool:
        """復旧可能なエラーかどうかの判定"""
        try:
            # 基本的な復旧可能性
            recoverable_categories = {
                ErrorCategory.NETWORK_CONNECTION: True,
                ErrorCategory.NETWORK_TIMEOUT: True,
                ErrorCategory.NETWORK_SERVER_ERROR: True,
                ErrorCategory.NETWORK_SSL: True,
                ErrorCategory.FILE_NOT_FOUND: True,
                ErrorCategory.FILE_DISK_FULL: True,
                ErrorCategory.PARSING: True,
                ErrorCategory.VALIDATION: True,
                ErrorCategory.SELENIUM_DRIVER: True,
                ErrorCategory.SELENIUM_TIMEOUT: True,
                ErrorCategory.UNKNOWN: True
            }
            
            # コンテキストによる判定
            if context.critical_stage and context.retry_count >= 2:
                return False
            
            if context.consecutive_errors >= self.error_config['consecutive_error_threshold']:
                return False
            
            return recoverable_categories.get(category, False)
            
        except Exception as e:
            self.logger.log(f"復旧可能性判定エラー: {e}", "error")
            return False
    
    def _needs_escalation(self, error: Exception, category: ErrorCategory, 
                         severity: ErrorSeverity, context: ErrorContext) -> bool:
        """エスカレーションが必要かどうかの判定"""
        try:
            # デバッグログ
            self.logger.log(f"[DEBUG] エスカレーション判定開始: severity={severity.value}, category={category.value}, retry_count={context.retry_count}, consecutive_errors={context.consecutive_errors}", "info")
            
            # 深刻度による判定
            if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
                self.logger.log(f"[DEBUG] エスカレーション理由: 深刻度が{severity.value}", "info")
                return True
            
            # カテゴリによる判定
            if category in [ErrorCategory.FILE_PERMISSION, ErrorCategory.FILE_DISK_FULL]:
                self.logger.log(f"[DEBUG] エスカレーション理由: カテゴリが{category.value}", "info")
                return True
            
            # コンテキストによる判定
            if context.consecutive_errors >= self.error_config['consecutive_error_threshold']:
                self.logger.log(f"[DEBUG] エスカレーション理由: 連続エラー数={context.consecutive_errors}", "info")
                return True
            
            if context.critical_stage and context.retry_count >= self.error_config['critical_stage_abort_threshold']:
                self.logger.log(f"[DEBUG] エスカレーション理由: クリティカルステージ", "info")
                return True
            
            self.logger.log(f"[DEBUG] エスカレーション不要", "info")
            return False
            
        except Exception as e:
            self.logger.log(f"エスカレーション判定エラー: {e}", "error")
            return True
    
    def _is_selenium_applicable(self, error: Exception, category: ErrorCategory, context: ErrorContext) -> bool:
        """Selenium安全弁が適用可能かどうかの判定"""
        try:
            # ⭐修正: selenium_fallback_enabledをチェック⭐
            selenium_fallback_enabled = self.error_config.get('enable_selenium_fallback', True)
            if not selenium_fallback_enabled:
                self.logger.log(f"[Selenium適用可能性] Selenium安全弁が無効です (enable_selenium_fallback={selenium_fallback_enabled})", "info")
                return False
            
            # Seleniumが無効な場合は適用不可（ただし、安全弁として使用する場合は有効化される）
            # ⭐修正: context.selenium_enabledは安全弁として使用する場合は無視⭐
            # if not context.selenium_enabled:
            #     return False
            
            # カテゴリ別の適用可能性
            selenium_applicable_categories = {
                ErrorCategory.NETWORK_SERVER_ERROR: True,
                ErrorCategory.NETWORK_RATE_LIMIT: True,
                ErrorCategory.NETWORK_SSL: True,
                ErrorCategory.PARSING: True,
                ErrorCategory.VALIDATION: True,
                ErrorCategory.UNKNOWN: True
            }
            
            is_applicable = selenium_applicable_categories.get(category, False)
            self.logger.log(f"[Selenium適用可能性] category={category}, is_applicable={is_applicable}, selenium_fallback_enabled={selenium_fallback_enabled}", "info")
            return is_applicable
            
        except Exception as e:
            self.logger.log(f"Selenium適用可能性判定エラー: {e}", "error")
            return False
    
    def _execute_error_strategy(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """エラー処理戦略の実行"""
        try:
            category = analysis['category']
            severity = analysis['severity']
            
            # エスカレーションが必要な場合
            if analysis['needs_escalation']:
                return self._escalate_error(error, analysis, context)
            
            # リトライ可能な場合
            if analysis['is_retryable']:
                retry_result = self._attempt_retry_with_strategy(error, analysis, context)
                if retry_result == 'success':
                    return FinalAction.CONTINUE.value
                elif retry_result == 'retry_exhausted':
                    # ⭐修正: Selenium安全弁はオプションである（retry_limit_actionが'selenium_retry'の場合のみ実行）⭐
                    retry_limit_action = getattr(self.state_manager, 'retry_limit_action', None)
                    if hasattr(retry_limit_action, 'get'):
                        retry_limit_action = retry_limit_action.get()
                    
                    # Selenium安全弁がONの場合（retry_limit_action == 'selenium_retry' かつ selenium_applicable == True）
                    if retry_limit_action == 'selenium_retry' and analysis.get('selenium_applicable', False):
                        selenium_result = self._execute_selenium_fallback(error, analysis, context)
                        if selenium_result == 'success':
                            return FinalAction.CONTINUE.value
                        else:
                            # Selenium安全弁失敗時もリトライ上限達成時オプションを適用
                            return self._get_final_action(analysis, context)
                    else:
                        # Selenium安全弁がOFFの場合、直接上限達成時オプションを適用
                        return self._get_final_action(analysis, context)
                elif retry_result == 'retry_failed':
                    # ⭐修正: retry_failedの場合、リトライ上限に達しているかチェックしてSelenium安全弁を実行⭐
                    # ⭐重要: context.retry_countは既に次回の試行回数なので、リトライを実行した後はretry_countが増えている
                    # リトライが失敗した時点で、retry_countは既に実行した回数+1になっている
                    # 例: retry_count=2でリトライを実行し、それが失敗した場合、retry_countは2のまま（次回は3回目）
                    # したがって、retry_count > strategy.max_retries で判定する必要がある
                    category = analysis['category']
                    strategy = self.error_strategies.get(category)
                    if strategy and context.retry_count > strategy.max_retries:
                        # リトライ上限に達している場合、Selenium安全弁を実行（オプション）
                        retry_limit_action = getattr(self.state_manager, 'retry_limit_action', None)
                        if hasattr(retry_limit_action, 'get'):
                            retry_limit_action = retry_limit_action.get()
                        
                        # Selenium安全弁がONの場合（retry_limit_action == 'selenium_retry' かつ selenium_applicable == True）
                        if retry_limit_action == 'selenium_retry' and analysis.get('selenium_applicable', False):
                            selenium_result = self._execute_selenium_fallback(error, analysis, context)
                            if selenium_result == 'success':
                                return FinalAction.CONTINUE.value
                            else:
                                # Selenium安全弁失敗時もリトライ上限達成時オプションを適用
                                return self._get_final_action(analysis, context)
                        else:
                            # Selenium安全弁がOFFの場合、直接上限達成時オプションを適用
                            return self._get_final_action(analysis, context)
                    else:
                        # リトライ上限に達していない場合、通常のエラー処理を続行
                        return self._get_final_action(analysis, context)
            
            # 復旧可能な場合
            elif analysis['is_recoverable']:
                recovery_result = self._attempt_recovery(error, analysis, context)
                if recovery_result == 'success':
                    # ⭐追加: エラー復旧成功時のログを3行で表示⭐
                    self.logger.log(f"════════════════════════════════════════", "info")
                    self.logger.log(f"✅ エラー復旧成功: 自動復旧処理によりエラーを解決しました", "info")
                    self.logger.log(f"════════════════════════════════════════", "info")
                    return FinalAction.CONTINUE.value
                else:
                    return self._get_final_action(analysis, context)
            
            # その他の場合
            else:
                return self._get_final_action(analysis, context)
                
        except Exception as e:
            self.logger.log(f"エラー戦略実行エラー: {e}", "error")
            return FinalAction.ABORT.value
    
    def _attempt_retry_with_strategy(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """戦略に基づくリトライ試行"""
        try:
            category = analysis['category']
            strategy = self.error_strategies.get(category)
            
            if not strategy or not strategy.retry:
                return 'not_retryable'
            
            # retry_countは「これまでに実行したリトライ回数」
            # max_retries=3 の場合、retry_count=0,1,2 の時点でリトライ可能
            # retry_count=3 の時点でリトライ上限達成
            if context.retry_count >= strategy.max_retries:
                return 'retry_exhausted'
            
            # ⭐修正: リトライ遅延の計算（実際の待機時間を取得）⭐
            delay = self._calculate_retry_delay(strategy, context.retry_count)
            
            # ⭐修正: エラーカテゴリ戦略からユーザーメッセージを取得（実際の待機時間を渡す）⭐
            from core.errors.error_category_strategy import ErrorCategoryStrategy
            user_message = ErrorCategoryStrategy.get_user_message(
                category, context.retry_count + 1, strategy.max_retries, delay
            )
            
            # ⭐修正: ユーザー向けメッセージをログに出力⭐
            # retry_countは1から始まっているので、+1しない
            self.logger.log(f"[リトライ {context.retry_count}/{strategy.max_retries}] {category.value}: {analysis['error_message'][:100]}", "warning")
            self.logger.log(user_message, "info")
            
            # ⭐修正: 実際に計算された時間だけ待機⭐
            time.sleep(delay)
            
            # リトライ統計の更新
            self.error_stats['retry_attempts'] += 1
            self._update_error_stats_gui()  # ⭐追加: GUI更新⭐
            
            # リトライ実行
            retry_success = self._execute_retry(error, analysis, context)
            
            if retry_success:
                self.error_stats['successful_retries'] += 1
                
                # ⭐追加: リカバリ成功時の詳細ログを3行で表示⭐
                self.logger.log("═══════════════════════════════════════════════════════════", "info")
                self.logger.log(f"✅ リトライ成功 ({context.retry_count + 1}回目の試行)", "info")
                recovery_method = strategy.recovery_method if strategy else "不明"
                self.logger.log(f"   復旧方法: {recovery_method} | カテゴリ: {category.value}", "info")
                self.logger.log("═══════════════════════════════════════════════════════════", "info")
                
                self._update_error_stats_gui()  # ⭐追加: 成功統計のGUI更新⭐
                
                return 'success'
            else:
                return 'retry_failed'
                
        except Exception as e:
            self.logger.log(f"リトライ試行エラー: {e}", "error")
            return 'retry_failed'
    
    def _calculate_retry_delay(self, strategy: ErrorStrategy, retry_count: int) -> float:
        """リトライ遅延時間の計算"""
        try:
            base_delay = strategy.base_delay
            
            if strategy.retry_strategy == RetryStrategy.IMMEDIATE:
                return 0.0
            elif strategy.retry_strategy == RetryStrategy.EXPONENTIAL:
                delay = base_delay * (self.error_config['retry_delay_multiplier'] ** retry_count)
            elif strategy.retry_strategy == RetryStrategy.LINEAR:
                delay = base_delay * (retry_count + 1)
            elif strategy.retry_strategy == RetryStrategy.FIXED:
                delay = base_delay
            elif strategy.retry_strategy == RetryStrategy.RANDOM:
                delay = base_delay + random.uniform(0, base_delay)
            else:
                delay = base_delay
            
            # 最大遅延時間の制限
            return min(delay, self.error_config['retry_delay_max'])
            
        except Exception as e:
            self.logger.log(f"リトライ遅延計算エラー: {e}", "error")
            return strategy.base_delay
    
    def _execute_retry(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> bool:
        """リトライの実行"""
        try:
            category = analysis['category']
            strategy = self.error_strategies.get(category)
            
            if not strategy:
                return False
            
            # 復旧方法に基づく処理
            if strategy.recovery_method == "session_reset":
                return self._recover_session_reset(context)
            elif strategy.recovery_method == "timeout_increase":
                return self._recover_timeout_increase(context)
            elif strategy.recovery_method == "ssl_config_adjustment":
                return self._recover_ssl_config_adjustment(context)
            elif strategy.recovery_method == "directory_creation":
                return self._recover_directory_creation(context)
            elif strategy.recovery_method == "driver_reinitialization":
                return self._recover_driver_reinitialization(context)
            elif strategy.recovery_method == "timeout_adjustment":
                return self._recover_timeout_adjustment(context)
            elif strategy.recovery_method == "generic_retry":
                return self._recover_generic_retry(context)
            else:
                return self._recover_generic_retry(context)
                
        except Exception as e:
            self.logger.log(f"リトライ実行エラー: {e}", "error")
            return False
    
    def _execute_selenium_fallback(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """Selenium安全弁の実行（リトライ上限達成時、1回だけ実行）"""
        try:
            self.error_stats['selenium_fallback_attempts'] += 1
            success = self.selenium_handler.execute_fallback(analysis, context)
            if success:
                self.error_stats['selenium_fallback_successes'] += 1
                context.is_selenium_success = True
                return 'success'
            return 'failed'
        except Exception as e:
            self.logger.log(f"Selenium安全弁エラー: {e}", "error")
            return 'execution_failed'
    
    def _get_selenium_config_for_error(self, analysis: Dict[str, Any], context: ErrorContext) -> Dict[str, Any]:
        """エラーに基づくSelenium設定の取得"""
        try:
            category = analysis['category']
            
            configs = {
                ErrorCategory.NETWORK_TIMEOUT: {
                    'timeout': 60,
                    'wait_strategy': 'eager',
                    'retry_count': 2
                },
                ErrorCategory.NETWORK_RATE_LIMIT: {
                    'timeout': 120,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                },
                ErrorCategory.NETWORK_SERVER_ERROR: {
                    'timeout': 45,
                    'wait_strategy': 'eager',
                    'retry_count': 3
                },
                ErrorCategory.PARSING: {
                    'timeout': 30,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                },
                ErrorCategory.VALIDATION: {
                    'timeout': 30,
                    'wait_strategy': 'normal',
                    'retry_count': 1
                }
            }
            
            return configs.get(category, {
                'timeout': 30,
                'wait_strategy': 'normal',
                'retry_count': 1
            })
            
        except Exception as e:
            self.logger.log(f"Selenium設定取得エラー: {e}", "error")
            return {'timeout': 30, 'wait_strategy': 'normal', 'retry_count': 1}
    
    def _get_selenium_driver_with_retry(self, config: Dict[str, Any], max_retries: int = 3):
        """リトライ付きSeleniumドライバーの取得"""
        try:
            # ⭐修正: Seleniumがインストールされているかチェック（遅延インポート）⭐
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options
                from webdriver_manager.chrome import ChromeDriverManager
            except ImportError:
                # ⭐修正: 未インストールの場合は明確にメッセージを表示して即座に終了⭐
                self.logger.log("[Selenium安全弁] Seleniumがインストールされていません。リトライ上限達成時オプションに移行します", "warning")
                return None
            
            # ⭐追加: Chromeがインストールされているかチェックし、パスを取得⭐
            # ⭐改善: カスタムパスが指定されている場合はそれを使用⭐
            chrome_installed = False
            chrome_binary_path = None
            
            # カスタムChromeパスが指定されている場合はそれを使用
            if hasattr(self.state_manager, 'parent'):
                parent = self.state_manager.parent
                if parent:
                    custom_chrome_path = getattr(parent, 'selenium_chrome_path', None)
                    if custom_chrome_path and hasattr(custom_chrome_path, 'get'):
                        custom_path = custom_chrome_path.get().strip()
                        if custom_path and os.path.exists(custom_path):
                            chrome_binary_path = custom_path
                            chrome_installed = True
                            self.logger.log(f"[Selenium安全弁] カスタムChromeパスを使用: {chrome_binary_path}", "debug")
            
            # カスタムパスが指定されていない場合、自動検出
            if not chrome_binary_path:
                try:
                    import subprocess
                    # WindowsレジストリからChromeのバージョンを取得
                    result = subprocess.run(
                        ['reg', 'query', 'HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon', '/v', 'version'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        chrome_installed = True
                except:
                    pass
            
            # ⭐改善: Chromeのパスを確認し、インストールを検証⭐
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            
            # レジストリからパスを取得（より確実）
            try:
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                    install_path, _ = winreg.QueryValueEx(key, "path")
                    winreg.CloseKey(key)
                    if install_path and os.path.exists(install_path):
                        chrome_paths.insert(0, install_path)
                except:
                    pass
                
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                    install_path, _ = winreg.QueryValueEx(key, "path")
                    winreg.CloseKey(key)
                    if install_path and os.path.exists(install_path):
                        chrome_paths.insert(0, install_path)
                except:
                    pass
            except:
                pass
            
            # Chromeのパスを確認（レジストリで見つからなかった場合）
            if not chrome_installed:
                for path in chrome_paths:
                    if os.path.exists(path):
                        chrome_installed = True
                        chrome_binary_path = path
                        break
            else:
                # レジストリで見つかった場合、パスを取得
                for path in chrome_paths:
                    if os.path.exists(path):
                        chrome_binary_path = path
                        break
            
            # ⭐追加: Chromeのインストールを検証（バージョン確認はレジストリから取得、失敗時はスキップ）⭐
            use_registry_version = self.error_config.get('selenium_use_registry_version', True)
            if chrome_binary_path:
                is_valid, validation_msg = self._validate_chrome_installation(chrome_binary_path, use_registry_version)
                if not is_valid:
                    self.logger.log(f"[Selenium安全弁] Chromeの検証に失敗: {validation_msg}", "warning")
                    # ⭐修正: 検証失敗でもファイルが存在すれば使用を試みる⭐
                    if os.path.exists(chrome_binary_path):
                        self.logger.log(f"[Selenium安全弁] Chrome実行ファイルは存在します。検証エラーを無視して続行します", "warning")
                        # chrome_binary_pathはそのまま使用
                    else:
                        chrome_binary_path = None
                else:
                    self.logger.log(f"[Selenium安全弁] {validation_msg}", "debug")
            
            # ⭐修正: chrome_binary_pathがNoneの場合のみエラーとする⭐
            if not chrome_binary_path:
                self.logger.log("[Selenium安全弁] Chromeがインストールされていません。リトライ上限達成時オプションに移行します", "warning")
                return None
            
            # ⭐追加: Chromeブラウザのパスをログ出力⭐
            if chrome_binary_path:
                self.logger.log(f"[Selenium安全弁] Chromeブラウザパス: {chrome_binary_path}", "debug")
            else:
                self.logger.log("[Selenium安全弁] Chromeブラウザパスが見つかりませんでした（システムPATHから検出されます）", "debug")
            
            # ドライバー取得を試行
            for attempt in range(max_retries):
                try:
                    # Chromeオプションの設定
                    chrome_options = Options()
                    
                    # ⭐追加: Chromeブラウザのパスを明示的に指定⭐
                    if chrome_binary_path:
                        chrome_options.binary_location = chrome_binary_path
                    
                    # ⭐修正: シンプルな実装（古いバージョンに近づける）⭐
                    # ⭐追加: selenium_minimal_optionsがONの場合は最小限のオプションのみ使用⭐
                    import tempfile
                    import time
                    import shutil
                    
                    minimal_options = self.error_config.get('selenium_minimal_options', False)
                    test_minimal = self.error_config.get('selenium_test_minimal_options', False)
                    test_no_headless = self.error_config.get('selenium_test_no_headless', False)
                    cleanup_temp = self.error_config.get('selenium_cleanup_temp', False)
                    
                    # ⭐修正: minimal_optionsがONの場合は--user-data-dirと--remote-debugging-portを使用しない⭐
                    if not minimal_options and not test_minimal:
                        # 既存のChromeプロセスと競合しないように、ユーザーデータディレクトリを分離
                        user_data_dir = os.path.join(tempfile.gettempdir(), f"selenium_chrome_{os.getpid()}_{int(time.time() * 1000)}_{attempt}")
                        
                        # 一時ディレクトリをクリーンアップ（オプション）
                        if cleanup_temp:
                            temp_dir = tempfile.gettempdir()
                            self.logger.log("[Selenium安全弁] 一時ディレクトリのクリーンアップを開始します...", "info")
                            cleanup_count = 0
                            try:
                                for item in os.listdir(temp_dir):
                                    item_path = os.path.join(temp_dir, item)
                                    if os.path.isdir(item_path) and item.startswith('selenium_chrome_'):
                                        try:
                                            shutil.rmtree(item_path, ignore_errors=True)
                                            cleanup_count += 1
                                            self.logger.log(f"[Selenium安全弁] 古い一時ディレクトリを削除しました: {item_path}", "info")
                                        except Exception as cleanup_error:
                                            self.logger.log(f"[Selenium安全弁] 一時ディレクトリの削除に失敗しました（無視）: {item_path}", "debug")
                                if cleanup_count > 0:
                                    self.logger.log(f"[Selenium安全弁] 一時ディレクトリのクリーンアップが完了しました（{cleanup_count}個削除）", "info")
                                else:
                                    self.logger.log("[Selenium安全弁] クリーンアップ対象の一時ディレクトリが見つかりませんでした", "debug")
                            except Exception as e:
                                self.logger.log(f"[Selenium安全弁] 一時ディレクトリのクリーンアップ中にエラー: {e}", "debug")
                        
                        os.makedirs(user_data_dir, exist_ok=True)
                        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
                        self.logger.log(f"[Selenium安全弁] ユーザーデータディレクトリ: {user_data_dir}", "debug")
                        
                        # リモートデバッグポートを指定（ポート競合を避ける）
                        import random
                        import socket
                        import re
                        
                        # 既存のChromeプロセスが使用しているポートを取得
                        used_ports = set()
                        try:
                            import psutil
                            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                try:
                                    if 'chrome' in proc.info['name'].lower():
                                        cmdline = proc.info.get('cmdline', [])
                                        if cmdline:
                                            cmdline_str = ' '.join(cmdline)
                                            match = re.search(r'--remote-debugging-port=(\d+)', cmdline_str)
                                            if match:
                                                used_ports.add(int(match.group(1)))
                                except:
                                    pass
                        except:
                            pass
                        
                        # ポート使用可能性チェック
                        remote_debugging_port = None
                        for _ in range(30):
                            port = random.randint(9000, 9999)
                            if port in used_ports:
                                continue
                            
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            try:
                                sock.bind(('127.0.0.1', port))
                                sock.close()
                                remote_debugging_port = port
                                if used_ports:
                                    self.logger.log(f"[Selenium安全弁] 既存のChromeプロセスが使用しているポートを回避してポート {remote_debugging_port} を割り当てました", "debug")
                                break
                            except OSError:
                                sock.close()
                                continue
                            except Exception:
                                sock.close()
                                continue
                        
                        if remote_debugging_port is None:
                            remote_debugging_port = 9222
                            self.logger.log(f"[Selenium安全弁] 使用可能なポートが見つかりませんでした。デフォルトポート {remote_debugging_port} を使用します（競合の可能性があります）", "warning")
                        
                        chrome_options.add_argument(f"--remote-debugging-port={remote_debugging_port}")
                        self.logger.log(f"[Selenium安全弁] リモートデバッグポート: {remote_debugging_port}", "debug")
                    
                    # ⭐修正: シンプルなChromeオプション（古いバージョンに近づける）⭐
                    if minimal_options or test_minimal:
                        # 最小限のオプションのみ使用（古いバージョンと同じ）
                        if not test_no_headless:
                            chrome_options.add_argument("--headless")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1920,1080")
                    else:
                        # 通常のオプション（古いバージョンと同じ5つのオプション + 追加オプション）
                        if not test_no_headless:
                            chrome_options.add_argument("--headless")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1920,1080")
                        # 追加オプション（必要に応じて）
                        chrome_options.add_argument("--disable-extensions")
                        chrome_options.add_argument("--disable-logging")
                    
                    # ⭐追加: Chromeオプションの詳細をログ出力⭐
                    self.logger.log(f"[Selenium安全弁] ユーザーデータディレクトリ: {user_data_dir}", "debug")
                    self.logger.log(f"[Selenium安全弁] リモートデバッグポート: {remote_debugging_port}", "debug")
                    
                    # ドライバーの取得（タイムアウト設定）
                    # ⭐改善: Selenium Managerを使用するオプションを追加⭐
                    use_selenium_manager = self.error_config.get('selenium_manager_enabled', False)
                    driver_path = None
                    
                    # カスタムドライバパスが指定されている場合はそれを使用
                    if hasattr(self.state_manager, 'parent'):
                        parent = self.state_manager.parent
                        if parent:
                            custom_driver_path = getattr(parent, 'selenium_driver_path', None)
                            if custom_driver_path and hasattr(custom_driver_path, 'get'):
                                custom_path = custom_driver_path.get().strip()
                                if custom_path and os.path.exists(custom_path):
                                    driver_path = os.path.normpath(custom_path)
                                    self.logger.log(f"[Selenium安全弁] カスタムChromeDriverパスを使用: {driver_path}", "debug")
                    
                    # カスタムパスが指定されていない場合、自動取得
                    if not driver_path:
                        # ⭐修正: threadingを先にインポート（既存ドライバ使用時も必要）⭐
                        import threading
                        import signal
                        
                        # ⭐追加: Chromeのバージョンを取得⭐
                        chrome_version_str = None
                        try:
                            import winreg
                            try:
                                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                                chrome_version_str, _ = winreg.QueryValueEx(key, "version")
                                winreg.CloseKey(key)
                            except:
                                try:
                                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                                    chrome_version_str, _ = winreg.QueryValueEx(key, "version")
                                    winreg.CloseKey(key)
                                except:
                                    pass
                        except:
                            pass
                        
                        # ⭐追加: バージョンパース関数⭐
                        def parse_version(version_str):
                            """バージョン文字列をパース（例: "142.0.7444.176" -> [142, 0, 7444, 176]）"""
                            try:
                                if not version_str:
                                    return None
                                parts = version_str.split('.')
                                return [int(p) for p in parts[:4]]  # 最大4つの部分
                            except:
                                return None
                        
                        # ⭐追加: バージョン適合度計算関数⭐
                        def version_match_score(chrome_ver, driver_ver):
                            """バージョンの適合度を計算（高いほど適合）"""
                            if chrome_ver is None or driver_ver is None:
                                return -1
                            
                            # メジャーバージョンが一致するか
                            if len(chrome_ver) == 0 or len(driver_ver) == 0:
                                return -1
                            if chrome_ver[0] != driver_ver[0]:
                                return -1  # メジャーバージョンが違う場合は不適合
                            
                            score = 0
                            # マイナーバージョンが一致するか
                            if len(chrome_ver) > 1 and len(driver_ver) > 1:
                                if chrome_ver[1] == driver_ver[1]:
                                    score += 1000
                                else:
                                    score -= abs(chrome_ver[1] - driver_ver[1]) * 100
                            
                            # ビルド番号が近いか
                            if len(chrome_ver) > 2 and len(driver_ver) > 2:
                                score += max(0, 100 - abs(chrome_ver[2] - driver_ver[2]))
                            
                            # パッチ番号が近いか
                            if len(chrome_ver) > 3 and len(driver_ver) > 3:
                                score += max(0, 10 - abs(chrome_ver[3] - driver_ver[3]))
                            
                            return score
                        
                        # ⭐追加: 既存のChromeDriverを検索（Chromeバージョンに適合するものを選択）⭐
                        existing_driver_path = None
                        best_match_version = None
                        
                        try:
                            cache_path = os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver")
                            if os.path.exists(cache_path):
                                chrome_version_parts = parse_version(chrome_version_str) if chrome_version_str else None
                                
                                # キャッシュ内の全てのドライバを検索
                                candidate_drivers = []
                                for root, dirs, files in os.walk(cache_path):
                                    for file in files:
                                        if file == "chromedriver.exe" or file == "chromedriver":
                                            candidate_path = os.path.join(root, file)
                                            if os.path.exists(candidate_path) and os.access(candidate_path, os.X_OK):
                                                # パスからバージョンを抽出（例: .../142.0.7444.175/...）
                                                path_parts = root.split(os.sep)
                                                driver_version_str = None
                                                for part in reversed(path_parts):  # パスの後ろから検索（より正確）
                                                    # バージョン番号を含む部分を探す（例: "142.0.7444.175"）
                                                    # 数字とドットで構成され、ドットが2つ以上含まれる
                                                    if '.' in part:
                                                        parts = part.split('.')
                                                        if len(parts) >= 2:
                                                            try:
                                                                # 全ての部分が数字か確認
                                                                all_numeric = all(p.isdigit() for p in parts[:4])
                                                                if all_numeric:
                                                                    driver_version_str = part
                                                                    break
                                                            except:
                                                                pass
                                                
                                                if driver_version_str:
                                                    driver_version_parts = parse_version(driver_version_str)
                                                    
                                                    if chrome_version_parts and driver_version_parts:
                                                        score = version_match_score(chrome_version_parts, driver_version_parts)
                                                        if score >= 0:  # メジャーバージョンが一致する場合のみ
                                                            candidate_drivers.append((candidate_path, score, driver_version_str))
                                                    elif not chrome_version_parts:
                                                        # Chromeバージョンが取得できない場合、全てのドライバを候補に追加
                                                        candidate_drivers.append((candidate_path, 0, driver_version_str))
                                
                                # 適合度が最も高いドライバを選択
                                if candidate_drivers:
                                    candidate_drivers.sort(key=lambda x: x[1], reverse=True)  # スコアの降順
                                    existing_driver_path, best_score, best_version = candidate_drivers[0]
                                    best_match_version = best_version
                                    self.logger.log(f"[Selenium安全弁] Chromeバージョン: {chrome_version_str}, 適合ドライバ: {best_version} (適合度: {best_score})", "info")
                        except Exception as e:
                            self.logger.log(f"[Selenium安全弁] 既存ドライバの検索中にエラー: {e}", "debug")
                        
                        if existing_driver_path:
                            # ⭐修正: 適合するドライバを使用⭐
                            if best_match_version:
                                self.logger.log(f"[Selenium安全弁] Chromeバージョンに適合するChromeDriverを使用: {existing_driver_path} (バージョン: {best_match_version})", "info")
                            else:
                                self.logger.log(f"[Selenium安全弁] 既存のChromeDriverを使用: {existing_driver_path}", "info")
                            driver_path = existing_driver_path
                        else:
                            # 既存のドライバがない場合、または適合するドライバがない場合のみ、install()を呼び出す
                            if chrome_version_str:
                                self.logger.log(f"[Selenium安全弁] Chromeバージョン {chrome_version_str} に適合するChromeDriverが見つかりません。新規インストールを試みます", "info")
                            else:
                                self.logger.log("[Selenium安全弁] 既存のChromeDriverが見つかりません。新規インストールを試みます", "info")
                            
                            install_error = None
                            
                            def install_driver():
                                nonlocal driver_path, install_error
                                try:
                                    if use_selenium_manager:
                                        # ⭐追加: Selenium Managerを使用（Selenium 4.6以降）⭐
                                        # Service()にdriver_pathを指定しないと、Selenium Managerが自動的にドライバを管理
                                        self.logger.log("[Selenium安全弁] Selenium Managerを使用してドライバを取得します", "debug")
                                        # Selenium ManagerはService()の引数なしで使用
                                        driver_path = None  # Selenium Managerを使用する場合はNone
                                    else:
                                        # 従来のwebdriver-managerを使用
                                        self.logger.log("[Selenium安全弁] ChromeDriverManager().install()を実行中...", "debug")
                                        driver_path = ChromeDriverManager().install()
                                        self.logger.log(f"[Selenium安全弁] ChromeDriverのインストールが完了しました: {driver_path}", "info")
                                except Exception as e:
                                    install_error = e
                                    self.logger.log(f"[Selenium安全弁] ChromeDriverのインストールに失敗: {e}", "error")
                            
                            # タイムアウト付きでドライバーインストールを実行
                            install_thread = threading.Thread(target=install_driver, daemon=True)
                            install_thread.start()
                            install_thread.join(timeout=30)  # 30秒でタイムアウト
                        
                            if install_thread.is_alive():
                                self.logger.log("[Selenium安全弁] ドライバ取得がタイムアウトしました（30秒）。リトライ上限達成時オプションに移行します", "warning")
                                continue
                            
                            if install_error:
                                # ⭐追加: インストールエラーの詳細をログ出力⭐
                                self.logger.log(f"[Selenium安全弁] ドライバ取得エラー: {type(install_error).__name__}: {str(install_error)}", "error")
                                self.logger.log(f"[Selenium安全弁] エラー詳細: {traceback.format_exc()}", "debug")
                                self.logger.log("[Selenium安全弁] ChromeDriverのインストールに失敗しました。リトライ上限達成時オプションに移行します", "warning")
                                continue
                            
                            if not use_selenium_manager and not driver_path:
                                self.logger.log("[Selenium安全弁] ドライバ取得に失敗しました（driver_pathがNone）。リトライ上限達成時オプションに移行します", "warning")
                                continue
                        
                        if driver_path:
                            driver_path = os.path.normpath(driver_path)
                    
                    # ⭐追加: ChromeDriverの存在確認（Selenium Managerを使用しない場合のみ）⭐
                    if not use_selenium_manager:
                        if driver_path and not os.path.exists(driver_path):
                            self.logger.log(f"[Selenium安全弁] ChromeDriverが見つかりません: {driver_path}", "error")
                            continue
                        
                        # ⭐追加: ChromeDriverの実行権限確認⭐
                        if driver_path and not os.access(driver_path, os.X_OK):
                            self.logger.log(f"[Selenium安全弁] ChromeDriverに実行権限がありません: {driver_path}", "error")
                            continue
                        
                        # ⭐追加: ドライバーパスのログ出力（正規化後）⭐
                        self.logger.log(f"[Selenium安全弁] ChromeDriverパス（正規化後）: {driver_path}", "debug")
                        service = Service(driver_path)
                    else:
                        # Selenium Managerを使用する場合、Service()にdriver_pathを指定しない
                        self.logger.log("[Selenium安全弁] Selenium Managerを使用（Service()にdriver_pathを指定しない）", "debug")
                        service = Service()  # Selenium Managerが自動的にドライバを管理
                    
                    # ⭐追加: Chromeのバックグラウンドプロセスを停止（オプション）⭐
                    # ⭐修正: Chrome起動直前に実行し、--remote-debugging-portを使用しているプロセスも停止⭐
                    stop_chrome_bg = self.error_config.get('selenium_stop_chrome_background', False)
                    if stop_chrome_bg:
                        try:
                            import psutil
                            import time
                            chrome_processes = [p for p in psutil.process_iter(['pid', 'name', 'exe']) 
                                              if 'chrome' in p.info['name'].lower()]
                            if chrome_processes:
                                # ⭐修正: 全てのChromeプロセスを停止対象に（ポート競合を避けるため）⭐
                                processes_to_stop = []
                                for proc in chrome_processes:
                                    try:
                                        exe_path = proc.info.get('exe', '')
                                        if exe_path and 'chrome.exe' in exe_path.lower():
                                            # コマンドライン引数を確認
                                            try:
                                                cmdline = proc.cmdline()
                                                cmdline_str = ' '.join(cmdline)
                                                
                                                # ⭐追加: --remote-debugging-portを使用しているプロセスも停止対象に⭐
                                                # バックグラウンドプロセスの特徴的な引数
                                                bg_keywords = ['--type=crashpad-handler', '--type=utility', 
                                                              '--type=renderer', '--type=gpu-process',
                                                              '--type=zygote', '--type=service',
                                                              '--remote-debugging-port']  # ⭐追加⭐
                                                
                                                # バックグラウンドプロセスまたはリモートデバッグポートを使用しているプロセスを停止
                                                if any(keyword in cmdline_str for keyword in bg_keywords):
                                                    processes_to_stop.append(proc)
                                            except:
                                                # コマンドライン取得に失敗した場合、プロセスを停止対象に追加
                                                processes_to_stop.append(proc)
                                    except:
                                        pass
                                
                                if processes_to_stop:
                                    self.logger.log(f"[Selenium安全弁] Chromeのバックグラウンドプロセスを停止中（{len(processes_to_stop)}個）...", "info")
                                    stopped_count = 0
                                    for proc in processes_to_stop:
                                        try:
                                            proc.terminate()
                                            stopped_count += 1
                                        except:
                                            try:
                                                proc.kill()
                                                stopped_count += 1
                                            except:
                                                pass
                                    
                                    if stopped_count > 0:
                                        self.logger.log(f"[Selenium安全弁] Chromeのバックグラウンドプロセスを{stopped_count}個停止しました", "info")
                                        # ⭐修正: プロセス終了を待機（2秒に延長）⭐
                                        time.sleep(2)
                                else:
                                    self.logger.log("[Selenium安全弁] 停止対象のChromeプロセスが見つかりませんでした", "debug")
                        except ImportError:
                            # psutilがインストールされていない場合はスキップ
                            self.logger.log("[Selenium安全弁] psutilがインストールされていません。Chromeバックグラウンドプロセス停止をスキップします", "warning")
                        except Exception as e:
                            self.logger.log(f"[Selenium安全弁] Chromeバックグラウンドプロセス停止エラー: {e}", "debug")
                    
                    # ⭐追加: Chromeプロセスが既に起動しているかチェック（バックグラウンドプロセス停止後）⭐
                    try:
                        import psutil
                        import re
                        chrome_processes = [p for p in psutil.process_iter(['pid', 'name']) if 'chrome' in p.info['name'].lower()]
                        if chrome_processes:
                            self.logger.log(f"[Selenium安全弁] Chromeプロセスが既に起動しています（{len(chrome_processes)}個）。ポート競合の可能性があります。", "warning")
                            # ⭐追加: リモートデバッグポートを使用しているプロセスを確認⭐
                            try:
                                debugging_port_processes = []
                                for proc in chrome_processes:
                                    try:
                                        cmdline = proc.cmdline()
                                        cmdline_str = ' '.join(cmdline)
                                        if '--remote-debugging-port' in cmdline_str:
                                            debugging_port_processes.append(proc)
                                    except:
                                        pass
                                if debugging_port_processes:
                                    self.logger.log(f"[Selenium安全弁] リモートデバッグポートを使用しているChromeプロセスが{len(debugging_port_processes)}個あります。ポート競合の可能性が高いです。", "warning")
                            except:
                                pass
                    except ImportError:
                        # psutilがインストールされていない場合はスキップ
                        pass
                    except Exception as e:
                        self.logger.log(f"[Selenium安全弁] Chromeプロセス確認エラー: {e}", "debug")
                    
                    # ⭐修正: シンプルなブラウザ起動（古いバージョンと同じ）⭐
                    # ⭐修正: minimal_optionsがONの場合は直接起動、OFFの場合はタイムアウト付き起動⭐
                    driver = None
                    
                    if minimal_options or test_minimal:
                        # シンプルな起動（古いバージョンと同じ）
                        try:
                            if chrome_binary_path and os.path.exists(chrome_binary_path):
                                chrome_options.binary_location = chrome_binary_path
                            
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            self.logger.log("[Selenium安全弁] Chromeブラウザを起動しました（シンプルモード）", "info")
                        except Exception as e:
                            self.logger.log(f"[Selenium安全弁] Chromeブラウザ起動エラー: {type(e).__name__}: {str(e)}", "error")
                            self.logger.log(f"[Selenium安全弁] エラー詳細: {traceback.format_exc()}", "debug")
                            error_str = str(e).lower()
                            if 'port' in error_str or 'address already in use' in error_str:
                                self.logger.log("[Selenium安全弁] ポート競合の可能性があります。", "warning")
                            elif 'permission' in error_str or 'access' in error_str:
                                self.logger.log("[Selenium安全弁] 権限エラーの可能性があります。", "warning")
                            elif 'version' in error_str or 'mismatch' in error_str:
                                self.logger.log("[Selenium安全弁] ChromeとChromeDriverのバージョンが一致していない可能性があります。", "warning")
                            continue
                    else:
                        # タイムアウト付き起動（既存の実装を維持）
                        driver_error = None
                        
                        def start_driver():
                            nonlocal driver, driver_error
                            try:
                                if chrome_binary_path and os.path.exists(chrome_binary_path):
                                    chrome_options.binary_location = chrome_binary_path
                                
                                driver = webdriver.Chrome(service=service, options=chrome_options)
                            except Exception as e:
                                driver_error = e
                        
                        start_thread = threading.Thread(target=start_driver, daemon=True)
                        start_thread.start()
                        start_thread.join(timeout=30)  # ⭐修正: 30秒に延長⭐
                        
                        if start_thread.is_alive():
                            self.logger.log("[Selenium安全弁] Chromeブラウザの起動がタイムアウトしました（30秒）。リトライ上限達成時オプションに移行します", "warning")
                            self.logger.log(f"[Selenium安全弁] ChromeDriverパス: {driver_path}", "debug")
                            self.logger.log(f"[Selenium安全弁] Chromeオプション数: {len(chrome_options.arguments)}", "debug")
                            try:
                                import psutil
                                chrome_processes = [p for p in psutil.process_iter(['pid', 'name']) if 'chrome' in p.info['name'].lower()]
                                if chrome_processes:
                                    self.logger.log(f"[Selenium安全弁] タイムアウト時点でChromeプロセス数: {len(chrome_processes)}", "debug")
                            except:
                                pass
                            continue
                        
                        if driver_error:
                            self.logger.log(f"[Selenium安全弁] Chromeブラウザ起動エラー: {type(driver_error).__name__}: {str(driver_error)}", "error")
                            self.logger.log(f"[Selenium安全弁] エラー詳細: {traceback.format_exc()}", "debug")
                            error_str = str(driver_error).lower()
                            if 'port' in error_str or 'address already in use' in error_str:
                                self.logger.log("[Selenium安全弁] ポート競合の可能性があります。", "warning")
                            elif 'permission' in error_str or 'access' in error_str:
                                self.logger.log("[Selenium安全弁] 権限エラーの可能性があります。", "warning")
                            elif 'version' in error_str or 'mismatch' in error_str:
                                self.logger.log("[Selenium安全弁] ChromeとChromeDriverのバージョンが一致していない可能性があります。", "warning")
                            continue
                    
                    if not driver:
                        self.logger.log("[Selenium安全弁] Chromeブラウザの起動に失敗しました（driverがNone）。リトライ上限達成時オプションに移行します", "warning")
                        continue
                    
                    # タイムアウト設定
                    driver.set_page_load_timeout(config.get('timeout', 30))
                    driver.implicitly_wait(10)
                    
                    # ⭐修正: window_handlesの確認を緩和（minimal_optionsがONの場合は確認しない）⭐
                    if not minimal_options and not test_minimal:
                        try:
                            # ウィンドウハンドルを取得して、ウィンドウが開いているか確認（待機時間を延長）
                            import time
                            max_wait = 10  # ⭐修正: 10秒に延長⭐
                            wait_interval = 0.5
                            waited = 0
                            window_handles = []
                            while waited < max_wait:
                                try:
                                    window_handles = driver.window_handles
                                    if window_handles:
                                        break
                                except:
                                    pass
                                time.sleep(wait_interval)
                                waited += wait_interval
                            
                            if not window_handles:
                                self.logger.log(f"[Selenium安全弁] Chromeウィンドウが開いていません（待機時間: {waited}秒）。再試行します。", "warning")
                                try:
                                    driver.quit()
                                except:
                                    pass
                                continue
                            
                            # テストページにアクセスして、ドライバーが正常に動作するか確認
                            try:
                                driver.get("about:blank")
                                if driver.current_url != "about:blank":
                                    self.logger.log("[Selenium安全弁] Chromeドライバーの動作確認に失敗しました。再試行します。", "warning")
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                    continue
                            except Exception as nav_error:
                                self.logger.log(f"[Selenium安全弁] ナビゲーションテストエラー: {nav_error}。続行します。", "debug")
                        except Exception as e:
                            self.logger.log(f"[Selenium安全弁] Chromeドライバーの動作確認エラー: {e}。続行します。", "debug")
                    
                    self.logger.log(f"[Selenium安全弁] ドライバー取得成功 (試行 {attempt + 1}/{max_retries})", "info")
                    return driver
                    
                except Exception as e:
                    error_str = str(e).lower()
                    error_type = type(e).__name__
                    error_msg = str(e)
                    
                    # ⭐追加: すべてのエラーを詳細にログ出力⭐
                    self.logger.log(f"[Selenium安全弁] ドライバー取得試行 {attempt + 1}/{max_retries} 失敗: {error_type}: {error_msg}", "error")
                    self.logger.log(f"[Selenium安全弁] エラー詳細: {traceback.format_exc()}", "debug")
                    
                    # ⭐改善: エラーの種類を判定して適切なメッセージを表示⭐
                    if 'unable to discover open pages' in error_str or 'session not created' in error_str:
                        if attempt == max_retries - 1:
                            # 最後の試行でも失敗した場合
                            self.logger.log("[Selenium安全弁] Chrome/ChromeDriverの起動に失敗しました。Chromeが正しくインストールされているか、他のプロセスがChromeを使用していないか確認してください。リトライ上限達成時オプションに移行します", "warning")
                    elif 'timeout' in error_str or 'timed out' in error_str:
                        self.logger.log(f"[Selenium安全弁] タイムアウトエラー: {error_msg}", "warning")
                    elif 'connection' in error_str or 'refused' in error_str:
                        self.logger.log(f"[Selenium安全弁] 接続エラー: {error_msg}", "warning")
                    elif 'permission' in error_str or 'access' in error_str:
                        self.logger.log(f"[Selenium安全弁] 権限エラー: {error_msg}", "warning")
                    else:
                        self.logger.log(f"[Selenium安全弁] その他のエラー: {error_type}: {error_msg}", "warning")
                    
                    if attempt < max_retries - 1:
                        time.sleep(5)
                    continue
            
            # ⭐修正: 全ての試行が失敗した場合のメッセージ⭐
            self.logger.log("[Selenium安全弁] ドライバー取得に失敗しました。リトライ上限達成時オプションに移行します", "warning")
            return None
            
        except Exception as e:
            self.logger.log(f"[Selenium安全弁] ドライバー取得エラー: {e}。リトライ上限達成時オプションに移行します", "error")
            return None
    
    def _navigate_to_image_with_selenium(self, driver, url: str, config: Dict[str, Any]) -> bool:
        """Seleniumを使用した画像ページへのナビゲーション"""
        try:
            # ⭐追加: ドライバーが有効か確認⭐
            try:
                window_handles = driver.window_handles
                if not window_handles:
                    self.logger.log("[Selenium安全弁] Chromeウィンドウが閉じられています。", "error")
                    return False
            except Exception as e:
                self.logger.log(f"[Selenium安全弁] ドライバーの状態確認エラー: {e}", "error")
                return False
            
            # ページロード戦略の設定
            wait_strategy = config.get('wait_strategy', 'normal')
            
            if wait_strategy == 'eager':
                driver.execute_script("window.stop();")
            
            # URLにアクセス
            driver.get(url)
            
            # ⭐追加: ナビゲーション後のウィンドウ状態を確認⭐
            try:
                current_url = driver.current_url
                if not current_url or current_url == "data:,":
                    self.logger.log("[Selenium安全弁] ナビゲーション後のURLが無効です。", "error")
                    return False
            except Exception as e:
                self.logger.log(f"[Selenium安全弁] ナビゲーション後の状態確認エラー: {e}", "error")
                return False
            
            # ページの読み込み完了を待機
            if wait_strategy == 'normal':
                time.sleep(2)
            elif wait_strategy == 'eager':
                time.sleep(1)
            
            return True
            
        except Exception as e:
            error_str = str(e).lower()
            if 'target window already closed' in error_str or 'no such window' in error_str:
                self.logger.log(f"[Selenium安全弁] Chromeウィンドウが閉じられました: {e}", "error")
            else:
                self.logger.log(f"[Selenium安全弁] Seleniumナビゲーションエラー: {e}", "error")
            return False
    
    def _extract_image_data_with_selenium(self, driver, url: str):
        """Seleniumを使用した画像データの抽出"""
        try:
            # 複数の方法で画像データを抽出
            methods = [
                self._extract_via_canvas,
                self._extract_via_direct_download,
                self._extract_via_blob_url
            ]
            
            for method in methods:
                try:
                    image_data = method(driver, url)
                    if image_data:
                        # ⭐追加: Canvasエラーが発生した場合でも、直接ダウンロードが成功した場合はログに出力⭐
                        if method.__name__ == '_extract_via_direct_download':
                            self.logger.log("[Selenium安全弁] Canvas抽出が失敗しましたが、直接ダウンロードで成功しました", "info")
                        return image_data
                except Exception as e:
                    # ⭐修正: Canvasエラーの場合は詳細をログ出力⭐
                    if method.__name__ == '_extract_via_canvas' and 'Tainted canvases' in str(e):
                        self.logger.log(f"[Selenium安全弁] Canvas抽出エラー（CORS制限）: {e}。直接ダウンロードにフォールバックします。", "debug")
                    else:
                        self.logger.log(f"画像抽出方法失敗: {method.__name__} - {e}", "debug")
                    continue
            
            return None
            
        except Exception as e:
            self.logger.log(f"Selenium画像抽出エラー: {e}", "error")
            return None
    
    def _extract_via_canvas(self, driver, url: str):
        """Canvasを使用した画像データの抽出"""
        try:
            script = """
            var img = document.querySelector('img');
            if (img) {
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/png').split(',')[1];
            }
            return null;
            """
            image_data_b64 = driver.execute_script(script)
            
            if image_data_b64:
                return base64.b64decode(image_data_b64)
            
            return None
            
        except Exception as e:
            self.logger.log(f"Canvas画像抽出エラー: {e}", "debug")
            return None
    
    def _extract_via_direct_download(self, driver, url: str):
        """直接ダウンロードを使用した画像データの抽出"""
        try:
            # 画像URLを直接取得
            script = """
            var img = document.querySelector('img');
            if (img) {
                return img.src;
            }
            return null;
            """
            image_url = driver.execute_script(script)
            
            if image_url:
                # requestsを使用してダウンロード
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()
                return response.content
            
            return None
            
        except Exception as e:
            self.logger.log(f"直接ダウンロード画像抽出エラー: {e}", "debug")
            return None
    
    def _extract_via_blob_url(self, driver, url: str):
        """Blob URLを使用した画像データの抽出"""
        try:
            script = """
            var img = document.querySelector('img');
            if (img) {
                var canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                var ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                
                return new Promise(function(resolve) {
                    canvas.toBlob(function(blob) {
                        var reader = new FileReader();
                        reader.onload = function() {
                            resolve(reader.result.split(',')[1]);
                        };
                        reader.readAsDataURL(blob);
                    });
                });
            }
            return null;
            """
            
            # 非同期スクリプトの実行
            image_data_b64 = driver.execute_async_script(script)
            
            if image_data_b64:
                return base64.b64decode(image_data_b64)
            
            return None
            
        except Exception as e:
            self.logger.log(f"Blob URL画像抽出エラー: {e}", "debug")
            return None
    
    def _get_final_action(self, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """最終的なアクションの決定（リトライ上限達成時）"""
        try:
            # ⭐改善: リトライ上限達成時のログを追加⭐
            self.logger.log(f"[リトライ上限達成] リトライ回数: {context.retry_count}, エラーカテゴリ: {analysis['category']}", "warning")
            
            # ⭐修正: Selenium安全弁がONの場合、上限達成時オプションの前に一度だけSeleniumを実行⭐
            # Selenium安全弁はオプションである（retry_limit_actionが'selenium_retry'の場合のみ実行）
            retry_limit_action = getattr(self.state_manager, 'retry_limit_action', None)
            if hasattr(retry_limit_action, 'get'):
                retry_limit_action = retry_limit_action.get()
            
            # ⭐追加: Selenium安全弁の状態をログに表示⭐
            selenium_applicable = analysis.get('selenium_applicable', False)
            selenium_fallback_enabled = self.error_config.get('enable_selenium_fallback', True)
            self.logger.log(f"[リトライ上限達成] Selenium安全弁の状態: retry_limit_action={retry_limit_action}, selenium_applicable={selenium_applicable}, selenium_fallback_enabled={selenium_fallback_enabled}, selenium_enabled={context.selenium_enabled}", "info")
            
            # ⭐修正: Selenium安全弁の実行条件を拡張⭐
            # retry_limit_action == 'selenium_retry' の場合、または
            # selenium_applicable == True かつ selenium_fallback_enabled == True の場合に実行
            if (retry_limit_action == 'selenium_retry' or (selenium_applicable and selenium_fallback_enabled)) and selenium_applicable:
                self.logger.log("[リトライ上限達成] ⚡ Selenium安全弁がONのため、Seleniumで1回だけ再試行します", "info")
                selenium_result = self._execute_selenium_fallback(None, analysis, context)
                if selenium_result == 'success':
                    self.logger.log("[リトライ上限達成] ✅ Selenium安全弁が成功しました", "info")
                    return FinalAction.CONTINUE.value
                else:
                    # ⭐修正: Selenium安全弁失敗時は、retry_limit_actionを優先して適用⭐
                    self.logger.log("[リトライ上限達成] ❌ Selenium安全弁が失敗したため、上限達成時オプションを適用します", "warning")
                    # retry_limit_actionが設定されている場合はそれを優先
                    if retry_limit_action and retry_limit_action != 'selenium_retry':
                        if retry_limit_action == 'skip_image':
                            self.logger.log("[リトライ上限達成] 画像をスキップします", "warning")
                        elif retry_limit_action == 'skip_url':
                            self.logger.log("[リトライ上限達成] URLをスキップします", "warning")
                        elif retry_limit_action == 'pause':
                            self.logger.log("[リトライ上限達成] ダウンロードを一時停止します", "warning")
                        elif retry_limit_action == 'abort':
                            self.logger.log("[リトライ上限達成] ダウンロードを中止します", "error")
                        return retry_limit_action
                    # retry_limit_actionが設定されていない場合、戦略のafter_retry_failureを使用
                    category = analysis['category']
                    strategy = self.error_strategies.get(category)
                    if strategy:
                        action = strategy.after_retry_failure.value
                        self.logger.log(f"[リトライ上限達成] 戦略に基づくアクション: {action}", "warning")
                        return action
                    else:
                        return FinalAction.SKIP_IMAGE.value
            elif retry_limit_action == 'selenium_retry' and not selenium_applicable:
                # Selenium安全弁が設定されているが、適用不可の場合
                self.logger.log(f"[リトライ上限達成] ⚠️ Selenium安全弁が設定されていますが、適用不可です (selenium_applicable={selenium_applicable}, selenium_enabled={context.selenium_enabled})", "warning")
            
            # リトライ上限達成時オプションを適用
            if retry_limit_action:
                # ⭐改善: オプションに応じたログを追加⭐
                if retry_limit_action == 'selenium_retry':
                    # Selenium安全弁がOFFの場合、戦略のafter_retry_failureを使用
                    category = analysis['category']
                    strategy = self.error_strategies.get(category)
                    if strategy:
                        action = strategy.after_retry_failure.value
                        self.logger.log(f"[リトライ上限達成] Selenium安全弁がOFFのため、戦略に基づくアクション: {action}", "warning")
                        return action
                    else:
                        return FinalAction.SKIP_IMAGE.value
                elif retry_limit_action == 'skip_image':
                    self.logger.log("[リトライ上限達成] 画像をスキップします", "warning")
                elif retry_limit_action == 'skip_url':
                    self.logger.log("[リトライ上限達成] URLをスキップします", "warning")
                elif retry_limit_action == 'pause':
                    self.logger.log("[リトライ上限達成] ダウンロードを一時停止します", "warning")
                elif retry_limit_action == 'abort':
                    self.logger.log("[リトライ上限達成] ダウンロードを中止します", "error")
                else:
                    self.logger.log(f"[リトライ上限達成] オプションを適用: {retry_limit_action}", "info")
                return retry_limit_action
            
            # 従来の処理（フォールバック）
            category = analysis['category']
            strategy = self.error_strategies.get(category)
            
            if strategy:
                action = strategy.after_retry_failure.value
                self.logger.log(f"[リトライ上限達成] 戦略に基づくアクション: {action}", "warning")
                return action
            
            # デフォルトのアクション
            if analysis['severity'] == ErrorSeverity.CRITICAL:
                self.logger.log("[リトライ上限達成] 致命的エラーのため、ダウンロードを中止します", "error")
                return FinalAction.ABORT.value
            elif analysis['severity'] == ErrorSeverity.HIGH:
                self.logger.log("[リトライ上限達成] 深刻なエラーのため、URLをスキップします", "warning")
                return FinalAction.SKIP_URL.value
            elif analysis['severity'] == ErrorSeverity.MEDIUM:
                self.logger.log("[リトライ上限達成] 中程度のエラーのため、画像をスキップします", "warning")
                return FinalAction.SKIP_IMAGE.value
            else:
                self.logger.log("[リトライ上限達成] 軽微なエラーのため、続行します", "info")
                return FinalAction.CONTINUE.value
                
        except Exception as e:
            self.logger.log(f"[リトライ上限達成] 最終アクション決定エラー: {e}", "error")
            return FinalAction.ABORT.value
    
    def _escalate_error(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """エラーのエスカレーション処理"""
        try:
            self.logger.log(f"エラーがエスカレーションされました: {error}", "warning")
            
            # ユーザーに通知
            if hasattr(self.gui_operations, 'show_error_dialog'):
                self.gui_operations.show_error_dialog(
                    f"エラーが発生しました: {error}",
                    "エラーの詳細を確認してください。"
                )
            
            # 深刻度に応じた処理
            if analysis['severity'] == ErrorSeverity.CRITICAL:
                return FinalAction.ABORT.value
            elif analysis['severity'] == ErrorSeverity.HIGH:
                return FinalAction.PAUSE.value
            else:
                return FinalAction.MANUAL.value
                
        except Exception as e:
            self.logger.log(f"エスカレーション処理エラー: {e}", "error")
            return FinalAction.ABORT.value
    
    def _attempt_recovery(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext) -> str:
        """復旧の試行"""
        try:
            self.error_stats['recovery_attempts'] += 1
            
            category = analysis['category']
            strategy = self.error_strategies.get(category)
            
            if not strategy:
                return 'no_strategy'
            
            # 復旧方法の実行
            if strategy.recovery_method == "wait_and_retry":
                time.sleep(strategy.base_delay)
                return 'success'
            elif strategy.recovery_method == "cleanup_and_retry":
                return self._recover_cleanup_and_retry(context)
            elif strategy.recovery_method == "manual_intervention":
                return 'manual_required'
            else:
                return 'recovery_failed'
                
        except Exception as e:
            self.logger.log(f"復旧試行エラー: {e}", "error")
            return 'recovery_failed'
    
    def _recover_session_reset(self, context: ErrorContext) -> bool:
        """セッションリセットによる復旧"""
        try:
            # ⭐追加: セッションリセット開始ログ⭐
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            self.logger.log("🔧 復旧操作: セッションリセットを実行します", "info")
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            
            # セッションの再初期化
            if hasattr(self.state_manager, 'reset_session'):
                self.state_manager.reset_session()
                self.logger.log("✓ セッションを再初期化しました", "info")
            
            # 短い待機
            time.sleep(2)
            
            # ⭐追加: セッションリセット完了ログ⭐
            self.logger.log("✓ セッションリセットが完了しました", "info")
            return True
            
        except Exception as e:
            self.logger.log(f"セッションリセット復旧エラー: {e}", "error")
            return False
    
    def _recover_timeout_increase(self, context: ErrorContext) -> bool:
        """タイムアウト増加による復旧"""
        try:
            # ⭐追加: タイムアウト増加開始ログ⭐
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            self.logger.log("🔧 復旧操作: タイムアウト設定を増加します", "info")
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            
            # タイムアウト設定の調整
            if hasattr(self.state_manager, 'increase_timeout'):
                self.state_manager.increase_timeout()
                self.logger.log("✓ タイムアウト設定を増加しました", "info")
            
            return True
            
        except Exception as e:
            self.logger.log(f"タイムアウト増加復旧エラー: {e}", "error")
            return False
    
    def _recover_ssl_config_adjustment(self, context: ErrorContext) -> bool:
        """SSL設定調整による復旧"""
        try:
            # ⭐追加: SSL設定調整開始ログ⭐
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            self.logger.log("🔧 復旧操作: SSL設定を調整します", "info")
            self.logger.log("══════════════════════════════════════════════════════════", "info")
            
            # SSL設定の調整
            if hasattr(self.state_manager, 'adjust_ssl_config'):
                self.state_manager.adjust_ssl_config()
                self.logger.log("✓ SSL設定を調整しました", "info")
            
            return True
            
        except Exception as e:
            self.logger.log(f"SSL設定調整復旧エラー: {e}", "error")
            return False
    
    def _recover_directory_creation(self, context: ErrorContext) -> bool:
        """ディレクトリ作成による復旧"""
        try:
            # ディレクトリの作成
            if hasattr(self.file_operations, 'ensure_directory'):
                self.file_operations.ensure_directory(context.url)
            
            return True
            
        except Exception as e:
            self.logger.log(f"ディレクトリ作成復旧エラー: {e}", "error")
            return False
    
    def _recover_driver_reinitialization(self, context: ErrorContext) -> bool:
        """ドライバー再初期化による復旧"""
        try:
            # ドライバーの再初期化
            if hasattr(self.state_manager, 'reinitialize_driver'):
                self.state_manager.reinitialize_driver()
            
            return True
            
        except Exception as e:
            self.logger.log(f"ドライバー再初期化復旧エラー: {e}", "error")
            return False
    
    def _recover_timeout_adjustment(self, context: ErrorContext) -> bool:
        """タイムアウト調整による復旧"""
        try:
            # タイムアウトの調整
            if hasattr(self.state_manager, 'adjust_timeout'):
                self.state_manager.adjust_timeout()
            
            return True
            
        except Exception as e:
            self.logger.log(f"タイムアウト調整復旧エラー: {e}", "error")
            return False
    
    def _recover_generic_retry(self, context: ErrorContext) -> bool:
        """汎用リトライによる復旧"""
        try:
            # ⭐修正: generic_retryは実際のリトライ成功を判定しない⭐
            # 実際のリトライ成功は、ダウンロードが成功した場合のみ判定される
            # ここでは単に待機するだけで、成功/失敗の判定は行わない
            time.sleep(1)
            # ⭐修正: Falseを返す（実際のリトライ成功は別途判定）⭐
            return False
            
        except Exception as e:
            self.logger.log(f"汎用リトライ復旧エラー: {e}", "error")
            return False
    
    def _recover_cleanup_and_retry(self, context: ErrorContext) -> str:
        """クリーンアップとリトライによる復旧"""
        try:
            # ディスク容量の確認とクリーンアップ
            if hasattr(self.file_operations, 'cleanup_old_files'):
                self.file_operations.cleanup_old_files()
            
            return 'success'
            
        except Exception as e:
            self.logger.log(f"クリーンアップ復旧エラー: {e}", "error")
            return 'recovery_failed'
    
    def _update_error_stats(self, error: Exception, context: ErrorContext):
        """エラー統計の更新（注意: 呼び出し元でerror_lockを取得している必要があります）"""
        try:
            # ⭐修正: デッドロック防止 - handle_errorで既にロックを取得しているため、ここでは取得しない⭐
            self.error_stats['total_errors'] += 1
            
            # カテゴリ別カウント
            category = self._classify_error(error)
            if category.value not in self.error_stats['error_counts_by_category']:
                self.error_stats['error_counts_by_category'][category.value] = 0
            self.error_stats['error_counts_by_category'][category.value] += 1
            
            # 深刻度別カウント
            severity = self._assess_severity(error, context)
            if severity.value not in self.error_stats['error_counts_by_severity']:
                self.error_stats['error_counts_by_severity'][severity.value] = 0
            self.error_stats['error_counts_by_severity'][severity.value] += 1
            
            # URL別カウント
            if context.url:
                if context.url not in self.error_stats['url_error_counts']:
                    self.error_stats['url_error_counts'][context.url] = 0
                self.error_stats['url_error_counts'][context.url] += 1
            
            # ⭐追加: エラー統計更新後にGUIを更新（着火式）⭐
            if hasattr(self.state_manager, 'options_panel') and hasattr(self.state_manager.options_panel, '_update_error_statistics'):
                try:
                    # 非同期でGUIを更新（メインスレッドで実行）
                    if hasattr(self.state_manager, 'root'):
                        self.state_manager.root.after(0, self.state_manager.options_panel._update_error_statistics)
                except Exception as e:
                    self.logger.log(f"エラー統計GUI更新エラー: {e}", "error")
                
        except Exception as e:
            self.logger.log(f"エラー統計更新エラー: {e}", "error")
            import traceback
            self.logger.log(f"エラー統計更新エラー詳細: {traceback.format_exc()}", "error")
    
    def _log_error(self, error: Exception, analysis: Dict[str, Any], context: ErrorContext):
        """エラーログの出力"""
        try:
            category = analysis['category']
            severity = analysis['severity']
            error_message = analysis['error_message']
            
            # ログレベルの決定
            if severity == ErrorSeverity.CRITICAL:
                log_level = "error"
            elif severity == ErrorSeverity.HIGH:
                log_level = "error"
            elif severity == ErrorSeverity.MEDIUM:
                log_level = "warning"
            else:
                log_level = "info"
            
            # ログメッセージの構築
            log_message = f"[{category.value}] {error_message}"
            if context.url:
                log_message += f" (URL: {context.url})"
            if context.stage:
                log_message += f" (Stage: {context.stage})"
            if context.retry_count > 0:
                log_message += f" (Retry: {context.retry_count})"
            
            self.logger.log(log_message, log_level)
            
        except Exception as e:
            self.logger.log(f"エラーログ出力エラー: {e}", "error")
    
    def _validate_chrome_installation(self, chrome_path: str, use_registry: bool = True) -> tuple:
        """Chromeのインストールを検証（バージョン確認はレジストリから取得、失敗時はスキップ）"""
        try:
            # 1. ファイルの存在確認
            if not os.path.exists(chrome_path):
                return False, "Chrome実行ファイルが見つかりません"
            
            # 2. ファイルの実行可能性確認
            if not os.access(chrome_path, os.X_OK):
                return False, "Chrome実行ファイルに実行権限がありません"
            
            # 3. バージョン情報の取得（レジストリから優先的に取得、タイムアウトしない）
            if use_registry:
                try:
                    import winreg
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        version, _ = winreg.QueryValueEx(key, "version")
                        winreg.CloseKey(key)
                        return True, f"Chromeバージョン: Google Chrome {version}（レジストリから取得）"
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            version, _ = winreg.QueryValueEx(key, "version")
                            winreg.CloseKey(key)
                            return True, f"Chromeバージョン: Google Chrome {version}（レジストリから取得）"
                        except:
                            pass
                except:
                    pass
            
            # ⭐修正: レジストリから取得できなくても、ファイルが存在すれば有効とみなす⭐
            # 既存のChromeプロセスが多い場合、--versionの実行がブロックされる可能性があるため
            return True, "Chrome実行ファイルが存在し、実行可能です（バージョン情報は取得できませんでした）"
            
        except Exception as e:
            return False, f"Chrome検証中にエラー: {e}"
    
    def _record_error_result(self, result: str, analysis: Dict[str, Any], context: ErrorContext):
        """エラー結果の記録"""
        try:
            # 成功した場合の統計更新
            if result == FinalAction.CONTINUE.value:
                if analysis.get('selenium_applicable', False):
                    self.error_stats['selenium_fallback_successes'] += 1
                else:
                    self.error_stats['successful_recoveries'] += 1
                
                # ⭐追加: エラー統計更新後にGUIを更新（着火式）⭐
                if hasattr(self.state_manager, 'options_panel') and hasattr(self.state_manager.options_panel, '_update_error_statistics'):
                    try:
                        # 非同期でGUIを更新（メインスレッドで実行）
                        if hasattr(self.state_manager, 'root'):
                            self.state_manager.root.after(0, self.state_manager.options_panel._update_error_statistics)
                    except Exception as e:
                        self.logger.log(f"エラー統計GUI更新エラー: {e}", "error")
            
            # エラー結果のログ出力
            self.logger.log(f"エラー処理結果: {result}", "debug")
            
        except Exception as e:
            self.logger.log(f"エラー結果記録エラー: {e}", "error")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """エラー統計の取得"""
        try:
            with self.error_lock:
                return self.error_stats.copy()
        except Exception as e:
            self.logger.log(f"エラー統計取得エラー: {e}", "error")
            return {}
    
    def reset_error_statistics(self):
        """エラー統計のリセット"""
        try:
            with self.error_lock:
                self.error_stats = {
                    'total_errors': 0,
                    'error_counts_by_category': {e.value: 0 for e in ErrorCategory},
                    'error_counts_by_severity': {s.value: 0 for s in ErrorSeverity},
                    'url_error_counts': {},
                    'recovery_attempts': 0,
                    'successful_recoveries': 0,
                    'selenium_fallback_attempts': 0,
                    'selenium_fallback_successes': 0,
                    'retry_attempts': 0,
                    'successful_retries': 0
                }
        except Exception as e:
            self.logger.log(f"エラー統計リセットエラー: {e}", "error")
    
    def reset_error_count(self, url: str):
        """特定URLのエラーカウントをリセット"""
        try:
            with self.error_lock:
                if url in self.error_stats['url_error_counts']:
                    self.error_stats['url_error_counts'][url] = 0
                    self.logger.log(f"URLのエラーカウントをリセット: {url}", "debug")
        except Exception as e:
            self.logger.log(f"エラーカウントリセットエラー: {e}", "error")
    
    def get_error_count(self, url: str) -> int:
        """特定URLのエラーカウントを取得"""
        try:
            with self.error_lock:
                return self.error_stats['url_error_counts'].get(url, 0)
        except Exception as e:
            self.logger.log(f"エラーカウント取得エラー: {e}", "error")
            return 0
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """古いセッションのクリーンアップ"""
        try:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=max_age_hours)
            
            with self.error_lock:
                sessions_to_remove = []
                for session_id, session_data in self.active_sessions.items():
                    if session_data.get('timestamp', current_time) < cutoff_time:
                        sessions_to_remove.append(session_id)
                
                for session_id in sessions_to_remove:
                    del self.active_sessions[session_id]
                    
        except Exception as e:
            self.logger.log(f"セッションクリーンアップエラー: {e}", "error")
    
    # ⭐Phase5.5: 完了処理エラーハンドリング⭐
    def handle_url_completion_error(self, normalized_url: str, state_manager, session_manager,
                                    update_progress_func, get_url_index_func) -> bool:
        """URL完了時のエラー処理
        
        Args:
            normalized_url: 正規化されたURL
            state_manager: StateManagerインスタンス
            session_manager: SessionManagerインスタンス
            update_progress_func: プログレス更新関数
            get_url_index_func: URLインデックス取得関数
            
        Returns:
            bool: 次のダウンロードを自動開始するか（通常False）
        """
        try:
            session_manager.ui_bridge.post_log(f"エラーが発生したため完了処理をスキップ: {normalized_url}")
            state_manager.set_url_status(normalized_url, "error")
            
            # GUI更新
            url_index = get_url_index_func(normalized_url)
            if url_index is not None and url_index >= 0:
                update_progress_func(url_index, "エラー")
            
            # エラーカウントを記録
            self.increment_error_count(normalized_url)
            
            return False
        except Exception as e:
            self.logger.log(f"完了時エラー処理でさらにエラー: {e}", "error")
            return False
    
    def increment_error_count(self, url: str):
        """URLのエラーカウントを増加"""
        try:
            with self.error_lock:
                if url not in self.error_stats['url_error_counts']:
                    self.error_stats['url_error_counts'][url] = 0
                self.error_stats['url_error_counts'][url] += 1
        except Exception as e:
            self.logger.log(f"エラーカウント増加エラー: {e}", "error")
