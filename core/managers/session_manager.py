# -*- coding: utf-8 -*-
"""
統合セッションマネージャー - 全てを統合した最終版
再帰的レジュームを排除し、whileループによる制御フローを実現
"""

import threading
import time
from typing import Optional, Dict, Any
from enum import Enum

from core.network.download_task import DownloadTask
from core.network.download_session import DownloadSession, SessionState, SessionAction, SessionContext
from core.network.http_client import HttpClient
from core.communication.ui_bridge import UIBridge, UIEvent, UIEventType


class TaskResult(Enum):
    """タスク実行結果 - 3状態に統一"""
    SUCCESS = "success"      # 成功
    SKIP = "skip"           # スキップ
    FATAL = "fatal"         # 致命的失敗（中止）


class SessionManager:
    """
    統合セッションマネージャー
    - DownloadTaskによる状態管理
    - HttpClientによる通信統合
    - UIBridgeによるGUI分離
    - whileループによるリトライ制御
    """
    
    def __init__(self, parent=None, state_manager=None, error_handler=None, download_callback=None):
        """
        Args:
            parent: 親オブジェクト
            state_manager: 状態管理マネージャー
            error_handler: エラーハンドラー
            download_callback: ダウンロード実行コールバック関数
        """
        print("[SESSION_MANAGER] ========== SessionManager初期化開始 ==========")
        self.parent = parent
        self.state_manager = state_manager
        self.error_handler = error_handler
        self.download_callback = download_callback  # 既存のダウンロードロジックを呼び出すためのコールバック
        print("[SESSION_MANAGER] 基本属性設定完了")
        
        # コンポーネント
        print("[SESSION_MANAGER] HttpClient初期化を開始...")
        self.http_client = HttpClient(parent=self, logger=self)
        print("[SESSION_MANAGER] HttpClient初期化完了")
        self.ui_bridge = UIBridge(parent=parent)
        
        # タスク管理
        self.current_task: Optional[DownloadTask] = None
        self.sessions: Dict[str, DownloadSession] = {}
        
        # ロック
        self._task_lock = threading.RLock()
        
        # UIブリッジを開始
        self.ui_bridge.start()
        
        self.log("SessionManager初期化完了")
    
    def log(self, message: str, level: str = "info"):
        """ログ出力 - UIBridge経由に統一"""
        self.ui_bridge.post_log(f"[SessionManager] {message}", level)
    
    # ⭐削除: get_or_create_session()はhttp_clientに一元化⭐
    # http_clientがスレッドローカルストレージでセッションを管理する
    # parent.sessionは使用しない
    
    def close_all_sessions(self):
        """
        全セッションをクローズ（リソース管理）
        
        ⭐注記: http_clientがスレッドローカルストレージで管理しているため、
        セッションの自動クローズはPythonのGCに任せる⭐
        """
        try:
            # ⭐削除: parent.sessionは使用しない⭐
            # http_clientがスレッドローカルストレージで管理
            self.log("HTTPセッション管理はhttp_clientに一元化されています")
        except Exception as e:
            self.log(f"セッションクローズエラー: {e}", "warning")
    
    def start_download(self, task: DownloadTask) -> TaskResult:
        """
        ダウンロードを開始
        whileループによるリトライ制御
        
        Args:
            task: ダウンロードタスク
            
        Returns:
            TaskResult (SUCCESS/SKIP/FATAL)
        """
        with self._task_lock:
            self.current_task = task
        
        self.log(f"ダウンロード開始: {task.url}")
        
        # whileループによるリトライ制御
        while not task.is_completed:
            # 中断チェック
            if task.skip_requested:
                self.log(f"スキップ要求を検出: {task.url}")
                task.mark_skipped()
                return TaskResult.SKIP
            
            if task.is_paused:
                self.log("一時停止中...")
                time.sleep(0.5)
                continue
            
            # ダウンロード実行
            try:
                result = self._execute_download_step(task)
                
                if result == TaskResult.SUCCESS:
                    # 成功
                    task.mark_success()
                    task.current_page += 1
                    
                    # 全ページ完了チェック
                    if task.current_page >= task.total_pages:
                        task.mark_completed()
                        self.log(f"ダウンロード完了: {task.url}")
                        return TaskResult.SUCCESS
                    
                elif result == TaskResult.SKIP:
                    # スキップ
                    self.log(f"ページをスキップ: {task.current_page}")
                    task.current_page += 1
                    
                elif result == TaskResult.FATAL:
                    # 致命的エラー
                    self.log(f"致命的エラー: {task.url}", "error")
                    return TaskResult.FATAL
                
            except Exception as e:
                # エラー処理
                result = self._handle_error(task, e)
                
                if result == TaskResult.FATAL:
                    return TaskResult.FATAL
                elif result == TaskResult.SKIP:
                    task.mark_skipped()
                    return TaskResult.SKIP
                # SUCCESSの場合はリトライ
        
        return TaskResult.SUCCESS
    
    def _execute_download_step(self, task: DownloadTask) -> TaskResult:
        """
        ダウンロードステップを実行
        
        Args:
            task: ダウンロードタスク
            
        Returns:
            TaskResult
        """
        try:
            # 現在のページをダウンロード
            page = task.current_page
            
            self.ui_bridge.post_progress(page, task.total_pages, f"ページ {page}/{task.total_pages}")
            
            # 画像ページURLを取得
            image_page_url = self._get_image_page_url(task, page)
            if not image_page_url:
                self.log(f"画像ページURL取得失敗: ページ{page}", "warning")
                return TaskResult.SKIP
            
            # 画像情報を取得
            image_info = self._get_image_info(image_page_url, task)
            if not image_info:
                self.log(f"画像情報取得失敗: ページ{page}", "warning")
                return TaskResult.SKIP
            
            # 画像をダウンロード
            image_url = image_info.get('image_url')
            if not image_url:
                return TaskResult.SKIP
            
            save_path = self._get_save_path(task, page, image_info)
            
            # HTTPクライアント経由でダウンロード
            response = self.http_client.get_with_retry(
                image_url,
                max_retries=task.max_retries,
                retry_delay=task.retry_delay,
            )
            
            # 画像を保存
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            self.log(f"画像保存完了: ページ{page}")
            return TaskResult.SUCCESS
            
        except Exception as e:
            self.log(f"ダウンロードステップエラー: {e}", "error")
            raise
    
    def _handle_error(self, task: DownloadTask, error: Exception) -> TaskResult:
        """
        エラーを処理
        
        Args:
            task: ダウンロードタスク
            error: 発生したエラー
            
        Returns:
            TaskResult
        """
        task.mark_error(str(error), type(error).__name__)
        
        # リトライ可能かチェック
        if task.can_retry():
            task.increment_retry()
            
            self.log(
                f"リトライ実行 ({task.retry_count}/{task.max_retries}): {error}",
                "warning"
            )
            
            # リトライ遅延
            time.sleep(task.retry_delay)
            
            # 継続（whileループが再度実行される）
            return TaskResult.SUCCESS
        else:
            # リトライ上限
            self.log(f"リトライ上限到達: {task.max_retries}回", "error")
            
            # エラーハンドラーが利用可能な場合は使用 (Factory pattern使用)
            if self.error_handler:
                try:
                    from core.errors.error_types import DownloadContext, ErrorContextFactory
                    
                    download_ctx = DownloadContext(
                        url=task.url,
                        page_num=task.current_page,
                        total_pages=0,
                        stage=task.current_stage,
                        retry_count=task.retry_count
                    )
                    error_context = ErrorContextFactory.create_for_general(download_ctx)
                    
                    result = self.error_handler.handle_error(error, error_context)
                    
                    if result == 'skip_url':
                        return TaskResult.SKIP
                    elif result == 'abort':
                        return TaskResult.FATAL
                except Exception as e:
                    self.log(f"エラーハンドラー呼び出しエラー: {e}", "error")
            
            # デフォルトはスキップ
            return TaskResult.SKIP
    
    def _get_image_page_url(self, task: DownloadTask, page: int) -> Optional[str]:
        """画像ページURLを取得（ダミー実装）"""
        # 実際の実装では、ギャラリーページをパースして画像ページURLを取得
        return f"{task.url}?p={page}"
    
    def _get_image_info(self, image_page_url: str, task: DownloadTask) -> Optional[Dict[str, Any]]:
        """画像情報を取得（ダミー実装）"""
        try:
            response = self.http_client.get(image_page_url)
            # 実際の実装では、HTMLをパースして画像URLを抽出
            return {'image_url': 'https://example.com/image.jpg'}
        except Exception as e:
            self.log(f"画像情報取得エラー: {e}", "error")
            return None
    
    def _get_save_path(self, task: DownloadTask, page: int, image_info: Dict[str, Any]) -> str:
        """保存パスを取得（ダミー実装）"""
        import os
        filename = f"{page:04d}.jpg"
        return os.path.join(task.save_folder, filename)
    
    def pause_current_task(self):
        """現在のタスクを一時停止"""
        with self._task_lock:
            if self.current_task:
                self.current_task.is_paused = True
                self.log("タスクを一時停止")
    
    def resume_current_task(self, task: Optional[DownloadTask] = None) -> TaskResult:
        """
        現在のタスクを再開
        
        Args:
            task: 再開するタスク（Noneの場合は現在のタスクを使用）
            
        Returns:
            TaskResult (SUCCESS/SKIP/FATAL)
        """
        with self._task_lock:
            if task:
                self.current_task = task
            
            if not self.current_task:
                self.log("再開するタスクがありません", "warning")
                return TaskResult.FATAL
            
            self.current_task.is_paused = False
            self.log(f"タスクを再開: {self.current_task.url}")
            
            # download_callbackが設定されている場合は、それを使用
            if self.download_callback:
                try:
                    # 既存のダウンロードロジックを呼び出し
                    options = self._get_options_from_task(self.current_task)
                    self.download_callback(self.current_task.url, options)
                    return TaskResult.SUCCESS
                except Exception as e:
                    self.log(f"ダウンロードコールバックエラー: {e}", "error")
                    return TaskResult.FATAL
            else:
                # 組み込みのダウンロードロジックを使用
                return self.start_download(self.current_task)
    
    def skip_current_task(self, url: Optional[str] = None) -> TaskResult:
        """
        現在のタスクをスキップ
        
        Args:
            url: スキップするURL（Noneの場合は現在のタスクを使用）
            
        Returns:
            TaskResult (SUCCESS/SKIP/FATAL)
        """
        with self._task_lock:
            if url and (not self.current_task or self.current_task.url != url):
                # 新しいタスクを作成してスキップ
                task = DownloadTask(url=url)
                task.mark_skipped()
                self.log(f"タスクをスキップ: {url}")
                return TaskResult.SKIP
            
            if self.current_task:
                self.current_task.skip_requested = True
                self.current_task.mark_skipped()
                self.log(f"タスクスキップ要求: {self.current_task.url}")
                return TaskResult.SKIP
            else:
                self.log("スキップするタスクがありません", "warning")
                return TaskResult.FATAL
    
    def _get_options_from_task(self, task: DownloadTask) -> Dict[str, Any]:
        """タスクからオプションを取得"""
        # ダミー実装 - 必要に応じて実装
        return {}
    
    def get_current_task(self) -> Optional[DownloadTask]:
        """現在のタスクを取得"""
        with self._task_lock:
            return self.current_task
    
    def cleanup(self):
        """クリーンアップ"""
        self.ui_bridge.stop()
        self.http_client.close()
        self.log("SessionManagerクリーンアップ完了")
