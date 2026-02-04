# -*- coding: utf-8 -*-
"""
統合リトライマネージャー - セッション管理とエラーハンドリングの統合
"""

import threading
import time
from typing import Dict, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass

from core.network.download_session import DownloadSession, SessionState, SessionAction, SessionContext


class RetryPolicy(Enum):
    """リトライポリシー"""
    IMMEDIATE = "immediate"      # 即座にリトライ
    LINEAR = "linear"           # 線形増加
    EXPONENTIAL = "exponential" # 指数バックオフ
    FIXED = "fixed"             # 固定間隔


@dataclass
class RetryContext:
    """リトライコンテキスト"""
    url: str
    page: int
    error_type: str
    error_message: str
    retry_count: int = 0
    max_retries: int = 3
    base_delay: float = 5.0
    last_retry_time: float = 0.0
    
    def can_retry(self) -> bool:
        """リトライ可能かチェック"""
        return self.retry_count < self.max_retries
    
    def get_retry_delay(self, policy: RetryPolicy) -> float:
        """リトライ遅延時間を計算"""
        if policy == RetryPolicy.IMMEDIATE:
            return 0.0
        elif policy == RetryPolicy.LINEAR:
            return self.base_delay * (self.retry_count + 1)
        elif policy == RetryPolicy.EXPONENTIAL:
            return self.base_delay * (2 ** self.retry_count)
        elif policy == RetryPolicy.FIXED:
            return self.base_delay
        return self.base_delay


class IntegratedRetryManager:
    """
    統合リトライマネージャー
    セッション管理とエラーハンドリングを統合し、スレッド維持型のリトライを実現
    """
    
    def __init__(self, parent=None, state_manager=None, error_handler=None):
        """
        Args:
            parent: 親オブジェクト
            state_manager: 状態管理マネージャー
            error_handler: エラーハンドラー
        """
        self.parent = parent
        self.state_manager = state_manager
        self.error_handler = error_handler
        
        # セッション管理
        self.sessions: Dict[str, DownloadSession] = {}
        self._sessions_lock = threading.RLock()
        
        # リトライコンテキスト管理
        self.retry_contexts: Dict[str, RetryContext] = {}
        self._retry_lock = threading.RLock()
        
        # ⭐画像ページごとのリトライカウント管理⭐
        self.image_retry_count: Dict[str, int] = {}  # {image_page_url: retry_count}
        
        # デフォルト設定
        self.default_max_retries = 3
        self.default_retry_delay = 5.0
        self.default_retry_policy = RetryPolicy.LINEAR
        
        # 統計情報
        self.stats = {
            'total_retries': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'sessions_created': 0,
            'sessions_completed': 0,
        }
        
        self.log("統合リトライマネージャー初期化完了")
    
    def log(self, message: str, level: str = "info"):
        """ログ出力"""
        if self.parent and hasattr(self.parent, 'log'):
            self.parent.log(f"[RetryManager] {message}", level)
    
    def create_session(self, session_id: str, context: SessionContext) -> Optional[DownloadSession]:
        """
        新しいダウンロードセッションを作成
        
        Args:
            session_id: セッション識別子
            context: 初期コンテキスト
            
        Returns:
            作成されたセッション
        """
        try:
            with self._sessions_lock:
                if session_id in self.sessions:
                    self.log(f"セッション既に存在: {session_id}", "warning")
                    return self.sessions[session_id]
                
                # 新しいセッションを作成
                session = DownloadSession(session_id, self.parent, self.state_manager)
                
                # 状態変更コールバックを登録
                session.register_state_callback(self._on_session_state_changed)
                
                # セッションを開始
                if session.start_session(context):
                    self.sessions[session_id] = session
                    self.stats['sessions_created'] += 1
                    self.log(f"セッション作成成功: {session_id}")
                    return session
                else:
                    self.log(f"セッション開始失敗: {session_id}", "error")
                    return None
                    
        except Exception as e:
            self.log(f"セッション作成エラー: {e}", "error")
            return None
    
    def get_session(self, session_id: str) -> Optional[DownloadSession]:
        """セッションを取得"""
        with self._sessions_lock:
            return self.sessions.get(session_id)
    
    def handle_error(self, session_id: str, error: Exception, page: int = 0) -> str:
        """
        エラーを処理し、リトライ戦略を決定
        
        Args:
            session_id: セッション識別子
            error: 発生したエラー
            page: エラーが発生したページ
            
        Returns:
            実行するアクション ('retry', 'skip', 'abort')
        """
        try:
            session = self.get_session(session_id)
            if not session:
                self.log(f"セッションが見つかりません: {session_id}", "error")
                return 'abort'
            
            # セッションコンテキストを取得
            context = session.get_context()
            
            # リトライコンテキストを取得または作成
            retry_key = f"{session_id}_{context.url}_{page}"
            retry_context = self._get_or_create_retry_context(
                retry_key, context.url, page, error
            )
            
            # エラーハンドラーが利用可能な場合は使用
            if self.error_handler:
                error_action = self._handle_error_with_handler(
                    session, retry_context, error
                )
                if error_action:
                    return error_action
            
            # デフォルトのリトライロジック
            if retry_context.can_retry():
                # リトライ可能
                retry_context.retry_count += 1
                self.stats['total_retries'] += 1
                
                # リトライ遅延を計算
                delay = retry_context.get_retry_delay(self.default_retry_policy)
                
                self.log(
                    f"リトライ実行 ({retry_context.retry_count}/{retry_context.max_retries}): "
                    f"{delay:.1f}秒後"
                )
                
                # セッションをリトライ状態に
                session.report_error(str(error))
                
                # 遅延後にリトライ
                if delay > 0:
                    time.sleep(delay)
                
                session.retry()
                return 'retry'
            else:
                # リトライ上限に達した
                self.log(
                    f"リトライ上限に達しました ({retry_context.max_retries}回)",
                    "warning"
                )
                self.stats['failed_retries'] += 1
                
                # スキップするか中止するか
                if self._should_skip_on_failure(error):
                    session.skip_current()
                    return 'skip'
                else:
                    session.abort()
                    return 'abort'
                    
        except Exception as e:
            self.log(f"エラー処理エラー: {e}", "error")
            return 'abort'
    
    def _get_or_create_retry_context(
        self, retry_key: str, url: str, page: int, error: Exception
    ) -> RetryContext:
        """リトライコンテキストを取得または作成"""
        with self._retry_lock:
            if retry_key not in self.retry_contexts:
                self.retry_contexts[retry_key] = RetryContext(
                    url=url,
                    page=page,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    max_retries=self.default_max_retries,
                    base_delay=self.default_retry_delay,
                )
            return self.retry_contexts[retry_key]
    
    def _handle_error_with_handler(
        self, session: DownloadSession, retry_context: RetryContext, error: Exception
    ) -> Optional[str]:
        """エラーハンドラーを使用してエラーを処理 (Factory pattern使用)"""
        try:
            # Factory patternを使用してErrorContextを作成
            from core.errors.error_types import DownloadContext, ErrorContextFactory
            
            context = session.get_context()
            download_ctx = DownloadContext(
                url=context.url,
                page_num=context.current_page,
                total_pages=0,
                stage=context.stage,
                retry_count=retry_context.retry_count
            )
            error_context = ErrorContextFactory.create_for_general(download_ctx)
            
            # エラーハンドラーでエラーを処理
            result = self.error_handler.handle_error(error, error_context)
            
            # 結果を解釈
            if result == 'continue':
                return 'retry'
            elif result == 'skip_image' or result == 'skip_url':
                return 'skip'
            elif result == 'abort':
                return 'abort'
            
            return None
            
        except Exception as e:
            self.log(f"エラーハンドラー呼び出しエラー: {e}", "error")
            return None
    
    def _should_skip_on_failure(self, error: Exception) -> bool:
        """失敗時にスキップすべきかを判定"""
        # エラータイプに応じて判定
        error_name = type(error).__name__
        
        # スキップすべきエラー
        skip_errors = [
            'ConnectionError',
            'TimeoutError',
            'HTTPError',
        ]
        
        return error_name in skip_errors
    
    def pause_session(self, session_id: str) -> bool:
        """セッションを一時停止"""
        session = self.get_session(session_id)
        if session:
            return session.pause()
        return False
    
    def resume_session(self, session_id: str) -> bool:
        """セッションを再開"""
        try:
            session = self.get_session(session_id)
            if not session:
                # セッションが存在しない場合は状態から復元を試みる
                session = self._restore_session(session_id)
                if not session:
                    self.log(f"セッションが見つかりません: {session_id}", "error")
                    return False
            
            # レジューム可能かチェック
            if session.can_resume():
                # リトライコンテキストをリセット
                self._clear_retry_contexts(session_id)
                
                return session.resume()
            else:
                self.log(
                    f"セッションはレジューム不可: {session.get_state()}",
                    "warning"
                )
                return False
                
        except Exception as e:
            self.log(f"セッション再開エラー: {e}", "error")
            return False
    
    def _restore_session(self, session_id: str) -> Optional[DownloadSession]:
        """永続化された状態からセッションを復元"""
        try:
            session = DownloadSession(session_id, self.parent, self.state_manager)
            if session.load_state():
                with self._sessions_lock:
                    self.sessions[session_id] = session
                self.log(f"セッション復元成功: {session_id}")
                return session
            else:
                self.log(f"セッション復元失敗: {session_id}", "warning")
                return None
        except Exception as e:
            self.log(f"セッション復元エラー: {e}", "error")
            return None
    
    def skip_current(self, session_id: str) -> bool:
        """現在の項目をスキップ"""
        session = self.get_session(session_id)
        if session:
            # リトライコンテキストをクリア
            self._clear_retry_contexts(session_id)
            return session.skip_current()
        return False
    
    def complete_session(self, session_id: str) -> bool:
        """セッションを完了"""
        try:
            session = self.get_session(session_id)
            if session:
                session.complete()
                self.stats['sessions_completed'] += 1
                
                # リトライコンテキストをクリア
                self._clear_retry_contexts(session_id)
                
                # セッションをクリーンアップ
                session.cleanup()
                
                with self._sessions_lock:
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                
                self.log(f"セッション完了: {session_id}")
                return True
            return False
        except Exception as e:
            self.log(f"セッション完了エラー: {e}", "error")
            return False
    
    def abort_session(self, session_id: str) -> bool:
        """セッションを中止"""
        try:
            session = self.get_session(session_id)
            if session:
                session.abort()
                
                # セッションをクリーンアップ
                session.cleanup()
                
                with self._sessions_lock:
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                
                self.log(f"セッション中止: {session_id}")
                return True
            return False
        except Exception as e:
            self.log(f"セッション中止エラー: {e}", "error")
            return False
    
    def _clear_retry_contexts(self, session_id: str):
        """セッションに関連するリトライコンテキストをクリア"""
        with self._retry_lock:
            keys_to_remove = [
                key for key in self.retry_contexts.keys()
                if key.startswith(f"{session_id}_")
            ]
            for key in keys_to_remove:
                del self.retry_contexts[key]
    
    def _on_session_state_changed(
        self, previous: SessionState, current: SessionState
    ):
        """セッション状態変更コールバック"""
        self.log(f"セッション状態変更: {previous.value} -> {current.value}", "debug")
        
        # 状態に応じた統計更新
        if current == SessionState.COMPLETED:
            self.stats['successful_retries'] += 1
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """セッション情報を取得"""
        session = self.get_session(session_id)
        if session:
            return session.get_resume_info()
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        return self.stats.copy()
    
    def cleanup_all(self):
        """全セッションをクリーンアップ"""
        try:
            with self._sessions_lock:
                session_ids = list(self.sessions.keys())
            
            for session_id in session_ids:
                self.abort_session(session_id)
            
            self.log("全セッションクリーンアップ完了")
        except Exception as e:
            self.log(f"クリーンアップ中のエラー: {e}", "error")
    
    # ========================================
    # ⭐画像ページごとのリトライカウント管理⭐
    # ========================================
    
    def get_image_retry_count(self, image_page_url: str) -> int:
        """画像ページのリトライ回数を取得
        
        Args:
            image_page_url: 画像ページURL
            
        Returns:
            int: リトライ回数
        """
        with self._retry_lock:
            return self.image_retry_count.get(image_page_url, 0)
    
    def increment_image_retry_count(self, image_page_url: str) -> int:
        """画像ページのリトライ回数を増加
        
        Args:
            image_page_url: 画像ページURL
            
        Returns:
            int: 増加後のリトライ回数
        """
        with self._retry_lock:
            current = self.image_retry_count.get(image_page_url, 0)
            self.image_retry_count[image_page_url] = current + 1
            return current + 1
    
    def reset_image_retry_count(self, image_page_url: str):
        """画像ページのリトライ回数をリセット
        
        Args:
            image_page_url: 画像ページURL
        """
        with self._retry_lock:
            if image_page_url in self.image_retry_count:
                del self.image_retry_count[image_page_url]
    
    def get_all_retry_counts(self) -> Dict[str, int]:
        """全画像ページのリトライ回数を取得（デバッグ用）
        
        Returns:
            Dict[str, int]: {image_page_url: retry_count}
        """
        with self._retry_lock:
            return self.image_retry_count.copy()

