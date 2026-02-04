# -*- coding: utf-8 -*-
"""
自動リトライマネージャー - Circuit Breaker Pattern 実装
"""

import time
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from enum import Enum

# EnhancedErrorHandler からインポート
from core.errors.enhanced_error_handler import (
    ErrorCategory, RetryStrategy, FinalAction
)
# ErrorCategoryStrategy からインポート
from core.errors.error_category_strategy import ErrorCategoryStrategy

class CircuitState(Enum):
    """Circuit Breaker の状態"""
    CLOSED = "closed"      # 正常状態
    OPEN = "open"         # 遮断状態（エラー多発）
    HALF_OPEN = "half_open"  # 半開放状態（試験的に再開）

class AutoRetryManager:
    """
    自動リトライマネージャー（Circuit Breaker内蔵）
    
    設計原則:
    - Self-Contained Retry Logic: リトライループを内包
    - Circuit Breaker Pattern: 連続エラー時に自動停止
    - Exponential Backoff with Jitter: 指数バックオフ + ジッター
    """
    
    def __init__(self, error_handler, state_manager, logger):
        """
        Args:
            error_handler: EnhancedErrorHandler インスタンス
            state_manager: IStateManager インスタンス
            logger: ILogger インスタンス
        """
        self.error_handler = error_handler
        self.state_manager = state_manager
        self.logger = logger
        
        # Circuit Breaker 設定
        self.circuit_state = CircuitState.CLOSED
        self.circuit_open_until = None
        self.consecutive_failures = 0
        self.failure_threshold = 5  # 5回連続失敗でCircuit Open
        self.recovery_timeout = 60  # 60秒後に HALF_OPEN へ
        
        # リトライ統計
        self.retry_stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'circuit_breaks': 0,
            'total_backoff_time': 0.0
        }
        
        # スレッドセーフ
        self.circuit_lock = threading.Lock()
    
    def execute_with_retry(self, 
                          func: Callable,
                          context: Any,
                          max_retries: int = None,
                          force_strategy: bool = False) -> Dict[str, Any]:
        """
        リトライ付き関数実行（Self-Contained + Context-Aware）
        
        ⭐Phase 1改善: Result型パターンへの移行準備⭐
        
        Args:
            func: 実行する関数（例: lambda: download_image(url)）
            context: ErrorContext インスタンス
            max_retries: 最大リトライ回数（Noneの場合は自動判断）
            force_strategy: Trueの場合、ErrorCategoryStrategyを無視してmax_retriesを強制使用
            
        Returns:
            Dict[str, Any]: 後方互換性のため辞書形式を維持
            {
                'success': bool,  # 成功/失敗
                'data': Any,      # 成功時のデータ
                'action': FinalAction,  # 失敗時のアクション
                'error': Exception,     # 失敗時のエラー
                'reason': str     # 失敗理由
            }
            
        Note:
            将来的にRetryResult型に移行予定
        """
        
        # Circuit Breaker チェック
        if not self._check_circuit():
            return {
                'success': False,
                'action': FinalAction.PAUSE,
                'reason': 'circuit_breaker_open',
                'error': None
            }
        
        retry_count = 0
        last_error = None
        error_category = None
        
        while True:
            try:
                # 関数実行
                result = func()
                
                # ✅ 成功: Circuit Breaker リセット
                self._on_success()
                self.retry_stats['successful_retries'] += 1
                
                # ⭐修正: リトライ成功時の3行強調ログ⭐
                if retry_count > 0:
                    self.logger.log("═══════════════════════════════════════════════════════════", "info")
                    self.logger.log(f"✅ リトライ成功 ({retry_count}回目の試行)", "info")
                    self.logger.log("   処理を続行します", "info")
                    self.logger.log("═══════════════════════════════════════════════════════════", "info")
                
                return {
                    'success': True,
                    'data': result,
                    'retry_count': retry_count
                }
                
            except Exception as e:
                last_error = e
                # ⭐修正: retry_countは0から始まり、エラー発生時にインクリメント⭐
                context.retry_count = retry_count
                self.retry_stats['total_retries'] += 1
                
                # ⭐追加: 初回エラー発生時の3行強調ログ⭐
                if retry_count == 0:
                    self.logger.log("═══════════════════════════════════════════════════════════", "error")
                    self.logger.log(f"❌ エラー発生: {str(e)[:100]}", "error")
                    self.logger.log("   リトライを開始します...", "error")
                    self.logger.log("═══════════════════════════════════════════════════════════", "error")
                
                # エラー分析
                analysis = self.error_handler._analyze_error(e, context)
                error_category = analysis['category']
                
                # ⭐Context-Aware: エラーカテゴリ別戦略を取得⭐
                if not force_strategy:
                    # 自動戦略: ErrorCategoryStrategyから取得
                    if not ErrorCategoryStrategy.should_retry(error_category):
                        # リトライ不要なエラー → 即座にスキップ/中止
                        final_action = ErrorCategoryStrategy.get_final_action(error_category)
                        skip_reason = ErrorCategoryStrategy.get_skip_reason(error_category)
                        
                        message = ErrorCategoryStrategy.get_user_message(
                            error_category, 0, 0, 0
                        )
                        self.logger.log(f"❌ {message}", "error")
                        if skip_reason:
                            self.logger.log(f"   理由: {skip_reason}", "error")
                        
                        self._on_failure()
                        return {
                            'success': False,
                            'action': final_action,
                            'error': e,
                            'reason': 'non_retryable_error',
                            'skip_reason': skip_reason
                        }
                    
                    # リトライ可能: 最大回数を取得
                    effective_max_retries = ErrorCategoryStrategy.get_max_retries(
                        error_category, max_retries
                    )
                    
                    # ⭐特殊設定: 基準リトライ回数=0 かつ Selenium有効 → 即座にSelenium起動⭐
                    if max_retries == 0 and hasattr(self.error_handler, 'selenium_handler'):
                        selenium_enabled = getattr(self.error_handler, '_selenium_enabled', False)
                        if selenium_enabled:
                            self.logger.log(
                                "⚡ 基準リトライ回数=0 + Selenium ON → 即座にSeleniumを起動",
                                "info"
                            )
                            return {
                                'success': False,
                                'action': FinalAction.CONTINUE,  # Selenium試行へ
                                'error': e,
                                'reason': 'selenium_immediate_mode',
                                'skip_http_retry': True  # HTTPリトライをスキップするフラグ
                            }
                else:
                    # 強制戦略: ユーザー指定のmax_retriesを使用
                    effective_max_retries = max_retries if max_retries is not None else 3
                
                # ⭐修正: retry_countは0から始まるので、表示は+1⭐
                # retry_count=0: 初回エラー（リトライ前）
                # retry_count=1: 1回目のリトライ後のエラー
                self.logger.log(
                    f"[リトライ {retry_count + 1}/{effective_max_retries}] {analysis['category'].value}: {str(e)[:100]}",
                    "warning"
                )
                
                # ⭐修正: リトライ上限到達チェック（>=に変更）⭐
                # retry_count=0: 初回エラー → リトライ可能
                # retry_count=1: 1回目のリトライ後 → リトライ可能（max_retries=3の場合）
                # retry_count=3: 3回目のリトライ後 → リトライ上限達成
                if retry_count >= effective_max_retries:
                    # ⭐追加: リトライ上限達成時の3行強調ログ⭐
                    self.logger.log("═══════════════════════════════════════════════════════════", "error")
                    self.logger.log(f"❌ リトライ上限到達 ({effective_max_retries}回)", "error")
                    self.logger.log(f"   エラー: {str(last_error)[:80]}", "error")
                    self.logger.log("═══════════════════════════════════════════════════════════", "error")
                    self._on_failure()
                    
                    # ⭐Selenium早期適用チェック⭐
                    if ErrorCategoryStrategy.should_try_selenium(error_category, retry_count - 1):
                        self.logger.log(
                            "🔄 Selenium安全弁を試行します...",
                            "info"
                        )
                        return {
                            'success': False,
                            'action': FinalAction.CONTINUE,  # Selenium試行へ
                            'error': e,
                            'reason': 'selenium_fallback_needed'
                        }
                    
                    # 最終アクション
                    final_action = ErrorCategoryStrategy.get_final_action(error_category)
                    skip_reason = ErrorCategoryStrategy.get_skip_reason(error_category)
                    
                    if skip_reason:
                        self.logger.log(f"   理由: {skip_reason}", "error")
                    
                    return {
                        'success': False,
                        'action': final_action,
                        'error': e,
                        'reason': 'max_retries_exceeded',
                        'skip_reason': skip_reason
                    }
                
                # ⭐Session更新チェック（Context-Aware）⭐
                if ErrorCategoryStrategy.should_refresh_session(error_category, retry_count):
                    self.logger.log(
                        "🔄 Session更新を試みます...",
                        "info"
                    )
                    # TODO: Session更新処理（呼び出し側で実装）
                    context.stage_data['session_refresh_needed'] = True
                
                # ⭐Selenium早期適用チェック（リトライ中）⭐
                if ErrorCategoryStrategy.should_try_selenium(error_category, retry_count):
                    self.logger.log(
                        f"🔄 Selenium安全弁を適用します（{retry_count}回目のリトライ後）",
                        "info"
                    )
                    return {
                        'success': False,
                        'action': FinalAction.CONTINUE,  # Selenium試行へ
                        'error': e,
                        'reason': 'selenium_fallback_early'
                    }
                
                # バックオフ計算（Context-Aware）
                delay = self._calculate_backoff_with_strategy(
                    retry_count, error_category, analysis
                )
                self.retry_stats['total_backoff_time'] += delay
                
                # ユーザーフィードバック（Context-Aware）
                user_message = ErrorCategoryStrategy.get_user_message(
                    error_category, retry_count, effective_max_retries, delay
                )
                self.logger.log(f"⏳ {user_message}", "info")
                
                # 待機（一時停止チェック付き）
                if not self._wait_with_pause_check(delay):
                    # ユーザーが一時停止を要求
                    return {
                        'success': False,
                        'action': FinalAction.PAUSE,
                        'error': e,
                        'reason': 'user_paused'
                    }
                
                # ⭐修正: リトライ後にretry_countをインクリメント⭐
                retry_count += 1
    
    def _calculate_backoff_with_strategy(self, 
                                        retry_count: int,
                                        error_category: ErrorCategory,
                                        analysis: Dict[str, Any]) -> float:
        """
        エラーカテゴリ別戦略を考慮したバックオフ計算
        
        Args:
            retry_count: 現在のリトライ回数
            error_category: ErrorCategory インスタンス
            analysis: エラー分析結果
            
        Returns:
            待機時間（秒）
        """
        # ErrorCategoryStrategyから戦略を取得
        retry_strategy = ErrorCategoryStrategy.get_backoff_strategy(error_category)
        base_delay = ErrorCategoryStrategy.get_base_delay(error_category)
        
        # 既存のバックオフ計算ロジックを使用
        return self._calculate_backoff_internal(retry_count, retry_strategy, base_delay)
    
    def _calculate_backoff_internal(self, 
                                   retry_count: int,
                                   retry_strategy: RetryStrategy,
                                   base_delay: float) -> float:
        """
        バックオフ計算（内部実装）
        
        Args:
            retry_count: 現在のリトライ回数
            retry_strategy: リトライ戦略
            base_delay: ベース待機時間
            
        Returns:
            待機時間（秒）
        """
        # 戦略に応じた遅延計算
        if retry_strategy == RetryStrategy.EXPONENTIAL:
            # 指数バックオフ: base * 2^(retry_count - 1)
            delay = base_delay * (2 ** (retry_count - 1))
        elif retry_strategy == RetryStrategy.LINEAR:
            # 線形増加: base * retry_count
            delay = base_delay * retry_count
        elif retry_strategy == RetryStrategy.FIXED:
            # 固定間隔
            delay = base_delay
        elif retry_strategy == RetryStrategy.IMMEDIATE:
            # 即座（最小0.5秒）
            delay = 0.5
        else:  # RANDOM
            # ランダム: base ~ base*2
            delay = base_delay * (1 + random.random())
        
        # 最大60秒に制限
        delay = min(delay, 60.0)
        
        # ジッター追加（±20%のランダム変動でサーバー負荷分散）
        jitter = delay * 0.2 * (random.random() - 0.5) * 2
        delay += jitter
        
        return max(0.5, delay)  # 最小0.5秒
    
    def _wait_with_pause_check(self, delay: float) -> bool:
        """
        待機（一時停止チェック付き）
        
        Args:
            delay: 待機時間（秒）
            
        Returns:
            True: 正常終了, False: ユーザー一時停止
        """
        # 0.5秒ごとにチェック
        check_interval = 0.5
        elapsed = 0.0
        
        while elapsed < delay:
            # 一時停止チェック（state_managerにis_pausedメソッドがある場合のみ）
            try:
                if hasattr(self.state_manager, 'is_paused') and callable(getattr(self.state_manager, 'is_paused')):
                    if self.state_manager.is_paused():
                        self.logger.log("⏸️ ユーザーによる一時停止を検出", "info")
                        return False
            except Exception as e:
                # is_paused()呼び出しエラーは無視して続行
                pass
            
            # 待機
            sleep_time = min(check_interval, delay - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time
        
        return True
    
    def _check_circuit(self) -> bool:
        """
        Circuit Breaker 状態確認
        
        Returns:
            True: 実行可能, False: Circuit Open（実行不可）
        """
        with self.circuit_lock:
            now = datetime.now()
            
            if self.circuit_state == CircuitState.OPEN:
                # 回復タイムアウトチェック
                if self.circuit_open_until and now >= self.circuit_open_until:
                    # OPEN → HALF_OPEN へ移行
                    self.circuit_state = CircuitState.HALF_OPEN
                    self.consecutive_failures = 0
                    self.logger.log(
                        "🔄 Circuit Breaker: HALF_OPEN状態へ移行（試験的に再開）",
                        "info"
                    )
                    return True
                else:
                    # まだOPEN状態
                    if self.circuit_open_until:
                        remaining = (self.circuit_open_until - now).seconds
                        self.logger.log(
                            f"🚫 Circuit Breaker: OPEN状態（{remaining}秒後に再試行可能）",
                            "warning"
                        )
                    return False
            
            return True
    
    def _on_success(self):
        """成功時処理（Circuit Breaker リセット）"""
        with self.circuit_lock:
            previous_state = self.circuit_state
            
            if self.circuit_state == CircuitState.HALF_OPEN:
                # HALF_OPEN → CLOSED へ復帰
                self.circuit_state = CircuitState.CLOSED
                self.logger.log(
                    "✅ Circuit Breaker: CLOSED状態へ復帰（正常運転）",
                    "info"
                )
            
            # 連続失敗カウントリセット
            if self.consecutive_failures > 0:
                prev_failures = self.consecutive_failures
                self.consecutive_failures = 0
                if prev_failures >= 3:  # 3回以上失敗していた場合のみログ
                    self.logger.log(
                        f"連続失敗カウントをリセット（{prev_failures} → 0）",
                        "debug"
                    )
    
    def _on_failure(self):
        """失敗時処理（Circuit Breaker 発動チェック）"""
        with self.circuit_lock:
            self.consecutive_failures += 1
            self.retry_stats['failed_retries'] += 1
            
            # Circuit Breaker 発動チェック
            if self.consecutive_failures >= self.failure_threshold:
                if self.circuit_state == CircuitState.CLOSED or \
                   self.circuit_state == CircuitState.HALF_OPEN:
                    self._open_circuit()
    
    def _open_circuit(self):
        """Circuit Breaker 発動"""
        self.circuit_state = CircuitState.OPEN
        self.circuit_open_until = datetime.now() + timedelta(
            seconds=self.recovery_timeout
        )
        self.retry_stats['circuit_breaks'] += 1
        
        self.logger.log(
            f"⚠️ Circuit Breaker発動: {self.consecutive_failures}回連続エラー",
            "error"
        )
        self.logger.log(
            f"   {self.recovery_timeout}秒後に自動再開を試みます",
            "error"
        )
        
        # GUI通知（存在する場合）
        if hasattr(self.error_handler, 'gui_operations'):
            try:
                # TODO: GUI通知ダイアログの実装
                # self.error_handler.gui_operations.show_circuit_breaker_dialog(
                #     self.consecutive_failures,
                #     self.recovery_timeout
                # )
                pass
            except Exception as e:
                self.logger.log(
                    f"Circuit Breaker GUI通知エラー: {e}",
                    "warning"
                )
    
    def reset_circuit(self):
        """Circuit Breaker を手動リセット（ユーザー操作用）"""
        with self.circuit_lock:
            if self.circuit_state == CircuitState.OPEN:
                self.circuit_state = CircuitState.HALF_OPEN
                self.consecutive_failures = 0
                self.logger.log(
                    "🔄 Circuit Breaker: 手動リセット（HALF_OPEN状態へ）",
                    "info"
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """リトライ統計を取得"""
        with self.circuit_lock:
            return {
                **self.retry_stats,
                'circuit_state': self.circuit_state.value,
                'consecutive_failures': self.consecutive_failures,
                'circuit_open_until': self.circuit_open_until.isoformat() 
                    if self.circuit_open_until else None
            }
