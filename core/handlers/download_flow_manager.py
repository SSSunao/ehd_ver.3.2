# -*- coding: utf-8 -*-
"""
Download Flow Manager - ダウンロードフロー制御の専門コンポーネント

責任範囲:
- ダウンロード前提条件チェック
- スレッドクリーンアップ
- URL取得後のフロー制御
- 空URL処理
- URL検証とスキップ処理
"""

import threading
import tkinter as tk
from typing import Dict, Any, Optional, Tuple


class DownloadFlowManager:
    """ダウンロードフロー制御を担当するマネージャー
    
    downloader.pyに分散していたURL処理フローロジックを統合し、
    責任を明確化。
    """
    
    def __init__(self, parent):
        """初期化
        
        Args:
            parent: EHDownloaderCoreインスタンス（依存性注入）
        """
        self.parent = parent
        self.state_manager = parent.state_manager
        self.session_manager = parent.session_manager
    
    def check_download_preconditions(self) -> bool:
        """ダウンロード前提条件チェック
        
        Returns:
            bool: 継続可能ならTrue
        """
        # 重複実行防止
        if hasattr(self.parent, '_start_next_download_running') and self.parent._start_next_download_running:
            return False
        
        # スレッド存在チェック
        download_thread = self.state_manager.get_download_thread()
        if download_thread:
            # ⭐修正: Futureオブジェクトの場合は_stateを確認⭐
            if hasattr(download_thread, '_state'):
                # concurrent.futures.Futureの場合
                if download_thread._state == 'RUNNING':
                    return False
            elif hasattr(download_thread, 'is_alive'):
                # threading.Threadの場合（後方互換性）
                if download_thread.is_alive():
                    return False
        
        # 実行状態チェック
        if not self.state_manager.is_download_running():
            return False
        
        return True
    
    def handle_thread_cleanup(self) -> bool:
        """スレッドクリーンアップ処理
        
        Returns:
            bool: 継続可能ならTrue（待機中はFalse）
        """
        download_thread = self.state_manager.get_download_thread()
        if download_thread:
            # ⭐修正: Futureオブジェクトの場合は_stateを確認⭐
            is_running = False
            if hasattr(download_thread, '_state'):
                # concurrent.futures.Futureの場合
                is_running = (download_thread._state == 'RUNNING')
            elif hasattr(download_thread, 'is_alive'):
                # threading.Threadの場合
                is_running = download_thread.is_alive()
            
            if is_running:
                self.session_manager.ui_bridge.post_log("⏳ 前のダウンロードスレッドの終了を待機中...", "info")
                self.state_manager.set_stop_flag()
                self.parent.parent.async_executor.execute_in_thread(self.parent._start_next_download)
                return False
        
        # スレッド状態クリア
        self.state_manager.set_download_thread(None)
        self.state_manager.set_current_thread_id(None)
        self.state_manager.reset_stop_flag()
        
        # 追加安全チェック
        active_threads = [t for t in threading.enumerate() if t.name and 'download' in t.name.lower()]
        if len(active_threads) > 1:
            pass  # ログのみ（処理継続）
        
        # 実行中チェック
        if not self.state_manager.is_download_running():
            self.session_manager.ui_bridge.post_log("ダウンロードが停止されているため、次のURLの処理を中断します", "info")
            return False
        
        return True
    
    def proceed_after_validation(self, validation_result: Dict[str, Any]):
        """検証後の処理
        
        Args:
            validation_result: 検証結果辞書
        """
        if not validation_result['valid']:
            self.session_manager.ui_bridge.post_log(
                f"【エラー】ダウンロード実行不可: {validation_result['message']}", "error"
            )
            self.session_manager.ui_bridge.post_log(
                "【重要】入力値を修正してからリスタートボタンを押してください", "warning"
            )
            
            def set_error_url():
                urls = self.parent.parent.url_text.get("1.0", tk.END).strip().splitlines()
                valid_urls = [url.strip() for url in urls if url.strip()]
                if valid_urls:
                    self.parent.current_gallery_url = valid_urls[0]
            
            self.parent.parent.async_executor.execute_gui_async(set_error_url)
            self.parent._handle_sequence_error()
            return
        
        # 実行状態設定
        self.state_manager.set_download_running(True)
        self.state_manager.set_paused(False)
        self.state_manager.set_pause_requested(False)
        
        current_url_index = self.state_manager.get_current_url_index()
        
        # URL進捗更新
        try:
            if (hasattr(self.parent.parent, 'url_panel') and 
                hasattr(self.parent.parent.url_panel, 'get_valid_url_count_fast')):
                total_urls = self.parent.parent.url_panel.get_valid_url_count_fast()
            else:
                urls = self.parent.parent._parse_urls_from_text(self.parent.parent.url_text.get("1.0", tk.END))
                total_urls = len(urls)
            
            if total_urls > 0:
                self.parent.update_url_progress(current_url_index + 1, total_urls)
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"URL進捗更新エラー: {e}", "error")
        
        # URL状態同期
        if hasattr(self.parent.parent, 'current_url_index'):
            self.parent.parent.current_url_index = current_url_index
        
        # ⭐修正: 既にワーカースレッド内なので直接URL取得⭐
        try:
            url, normalized_url = self.parent._get_next_url_sync(current_url_index)
            self.proceed_after_url_fetch(url, normalized_url, current_url_index)
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"URL取得エラー: {e}", "error")
            self.parent._handle_sequence_error()
    
    def proceed_after_url_fetch(self, url: str, normalized_url: str, current_url_index: int):
        """URL取得後の処理
        
        Args:
            url: 元のURL
            normalized_url: 正規化されたURL
            current_url_index: 現在のURLインデックス
        """
        if not url or not normalized_url:
            self.handle_empty_url(current_url_index)
            return
        
        # スキップされたURLチェック
        url_status = self.state_manager.get_url_status(normalized_url)
        if url_status == 'skipped':
            self.state_manager.clear_resume_point(normalized_url)
            self.state_manager.set_current_url_index(current_url_index + 1)
            self.parent._schedule_next_download("スキップされたURL")
            return
        
        # 通常処理
        self.process_url_after_get(url, normalized_url, current_url_index)
    
    def handle_empty_url(self, current_url_index: int):
        """空URLの処理
        
        Args:
            current_url_index: 現在のURLインデックス
        """
        def check_completion():
            try:
                if hasattr(self.parent.parent, 'url_panel'):
                    max_lines = self.parent.parent.url_panel.get_total_line_count_fast()
                else:
                    max_lines = int(self.parent.parent.url_text.index('end-1c').split('.')[0])
                
                self.parent.parent.async_executor.execute_in_thread(
                    lambda: self.handle_empty_url_result(current_url_index, max_lines)
                )
            except Exception as e:
                self.session_manager.ui_bridge.post_log(f"行数取得エラー: {e}", "error")
                self.parent._handle_sequence_error()
        
        self.parent.parent.async_executor.execute_gui_async(check_completion)
    
    def handle_empty_url_result(self, current_url_index: int, max_lines: int):
        """空URL結果処理
        
        Args:
            current_url_index: 現在のURLインデックス
            max_lines: 総行数
        """
        if current_url_index >= max_lines:
            self.state_manager.set_download_running(False)
            self.state_manager.set_paused(False)
            self.parent.parent.async_executor.execute_gui_async(self.parent.parent._on_sequence_complete)
            return
        
        self.session_manager.ui_bridge.post_log(f"空行または無効なURLをスキップ: 行{current_url_index + 1}")
        
        if hasattr(self.parent, 'error_occurred') and self.parent.error_occurred:
            return
        
        next_index = current_url_index + 1
        self.state_manager.set_current_url_index(next_index)
        
        if next_index >= max_lines:
            if not (hasattr(self.parent, '_sequence_complete_executed') and self.parent._sequence_complete_executed):
                self.parent._sequence_complete_executed = True
                self.state_manager.set_download_running(False)
                self.state_manager.set_paused(False)
                self.parent.parent.async_executor.execute_gui_async(self.parent.parent._on_sequence_complete)
            return
        
        self.parent._schedule_next_download("URL完了")
    
    def process_url_after_get(self, url: str, normalized_url: str, current_url_index: int):
        """URL取得後の処理（コールバック方式）
        
        Args:
            url: 元のURL
            normalized_url: 正規化されたURL
            current_url_index: 現在のURLインデックス
        """
        try:
            if not normalized_url:
                self.session_manager.ui_bridge.post_log(f"無効なURL: {url}", "error")
                
                if hasattr(self.parent, 'error_occurred') and self.parent.error_occurred:
                    self.session_manager.ui_bridge.post_log(f"【無効URL処理】エラーフラグ検出のためcurrent_url_index更新をスキップ")
                    return
                
                self.state_manager.set_current_url_index(current_url_index + 1)
                self.parent._schedule_next_download("URL完了")
                return
            
            # スキップされたURLをスキップ
            url_status = self.state_manager.get_url_status(normalized_url)
            
            if url_status == 'skipped':
                self.session_manager.ui_bridge.post_log(f"[DEBUG] スキップされたURLのため処理をスキップ: {normalized_url}")
                self.state_manager.clear_resume_point(normalized_url)
                
                if hasattr(self.parent, 'error_occurred') and self.parent.error_occurred:
                    self.session_manager.ui_bridge.post_log(f"【スキップ処理】エラーフラグ検出のためcurrent_url_index更新をスキップ")
                    return
                
                self.state_manager.set_current_url_index(current_url_index + 1)
                self.parent._schedule_next_download("スキップされたURL")
                return
            
            # 完了済みURLの重複ダウンロードを防ぐ
            if url_status == 'completed':
                self.session_manager.ui_bridge.post_log(f"完了済みURLをスキップ: {normalized_url}")
                
                if hasattr(self.parent, 'error_occurred') and self.parent.error_occurred:
                    self.session_manager.ui_bridge.post_log(f"【完了済みURL処理】エラーフラグ検出のためcurrent_url_index更新をスキップ")
                    return
                
                self.state_manager.set_current_url_index(current_url_index + 1)
                self.parent._schedule_next_download("URL完了")
                return
            
            # 前のURLの状態を適切に管理
            if hasattr(self.parent, 'current_gallery_url') and self.parent.current_gallery_url:
                previous_url_status = self.state_manager.get_url_status(self.parent.current_gallery_url)
                if previous_url_status == 'skipped':
                    pass
                elif not hasattr(self.parent, 'error_occurred') or not self.parent.error_occurred:
                    skip_requested_url = self.state_manager.get_skip_requested_url()
                    if previous_url_status != 'skipped' and not (skip_requested_url and skip_requested_url == self.parent.current_gallery_url):
                        self.state_manager.set_url_status(self.parent.current_gallery_url, "completed")
                else:
                    self.state_manager.set_url_status(self.parent.current_gallery_url, "error")
                    self.parent.error_occurred = False
            
            # ⭐修正: current_url_indexを先に設定（プログレスバー作成前）⭐
            self.state_manager.set_current_url_index(current_url_index)
            
            # 現在のURL状態を設定
            self.state_manager.set_current_gallery_url(normalized_url)
            self.state_manager.set_progress(0, 0)
            self.state_manager.set_url_status(normalized_url, "downloading")
            
            # URL進捗を更新
            completed_count = self.state_manager.get_completed_url_count()
            cached_urls = self.parent._get_cached_urls()
            self.session_manager.ui_bridge.post_log(f"[DEBUG] URL進捗更新: cached_urls={len(cached_urls) if cached_urls else 0}")
            if cached_urls:
                self.parent.update_url_progress(completed_count, len(cached_urls))
            else:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 非同期URL解析開始")
                self.parent._start_async_url_parsing()
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 非同期URL解析完了")
            
            # current_gallery_urlを設定
            self.parent.current_gallery_url = normalized_url
            self.session_manager.ui_bridge.post_log(f"[DEBUG] current_gallery_url設定完了")
            
            # プログレスバー生成（⭐修正: 同期的に実行して処理を継続⭐）
            self.session_manager.ui_bridge.post_log(f"[DEBUG] プログレスバー表示開始: progress_visible={self.parent.progress_visible}")
            if not self.parent.progress_visible:
                # ⭐GUIスレッドで非同期実行し、処理はブロックせず継続⭐
                if hasattr(self.parent.parent, 'progress_separate_window_enabled') and self.parent.parent.progress_separate_window_enabled.get():
                    self.parent.parent.async_executor.execute_gui_async(self.parent.parent.show_current_progress_bar)
                else:
                    self.parent.parent.async_executor.execute_gui_async(self.parent.parent.show_current_progress_bar)
                self.parent.progress_visible = True
            self.session_manager.ui_bridge.post_log(f"[DEBUG] プログレスバー表示完了")
            
            self.session_manager.ui_bridge.post_log(f"ダウンロード開始: {normalized_url}")
            self.session_manager.ui_bridge.post_log(f"[DEBUG] _start_download_thread呼び出し開始")
            
            # オプション取得とスレッド起動
            self._start_download_thread(normalized_url)
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"次のURLの開始エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"エラー詳細: {traceback.format_exc()}", "error")
            self.parent._handle_sequence_error()
        finally:
            if hasattr(self.parent, '_start_next_download_running'):
                self.parent._start_next_download_running = False
            try:
                thread_id = threading.current_thread().ident
                self.session_manager.ui_bridge.post_log(f"[DEBUG] _start_next_download終了: thread_id={thread_id}")
            except Exception as e:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] _start_next_download終了: スレッドID取得エラー: {e}", "error")
    
    def _start_download_thread(self, normalized_url: str):
        """ダウンロードスレッドを開始
        
        Args:
            normalized_url: 正規化されたURL
        """
        self.session_manager.ui_bridge.post_log(f"[DEBUG] _start_download_thread開始")
        try:
            options = self.parent._get_current_options()
            self.session_manager.ui_bridge.post_log(f"[DEBUG] オプション取得完了")
            
            # オプション情報をログ出力
            if normalized_url not in self.parent._logged_download_start_urls:
                self.parent._log_download_options(options)
                self.parent._logged_download_start_urls.add(normalized_url)
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"オプション取得エラー: {e}", "error")
            
            # デフォルトオプションで続行
            try:
                options = {
                    'folder_path': self.parent.parent.folder_var.get() if hasattr(self.parent.parent, 'folder_var') else '',
                    'wait_time': 1.0,
                    'sleep_value': 0.5,
                    'save_format': 'Original',
                    'save_name': 'Original',
                    'custom_name': '{page}',
                    'resize_mode': 'off',
                    'auto_resume_delay': 5,
                    'retry_delay_increment': 0,
                    'max_delay': 60,
                    'max_retry_count': '3'
                }
                self.session_manager.ui_bridge.post_log("デフォルトオプションで続行します", "warning")
            except Exception as fallback_error:
                self.session_manager.ui_bridge.post_log(f"デフォルトオプション生成にも失敗: {fallback_error}", "error")
                self.parent._handle_sequence_error()
                return
        
        # ダウンロードスレッド開始
        download_thread = self.state_manager.get_download_thread()
        if download_thread:
            # ⭐修正: Futureオブジェクトの場合は_stateを確認⭐
            is_running = False
            if hasattr(download_thread, '_state'):
                is_running = (download_thread._state == 'RUNNING')
                self.session_manager.ui_bridge.post_log(
                    f"[DEBUG] 既存Future検出: _state={download_thread._state}, is_running={is_running}", "debug"
                )
            elif hasattr(download_thread, 'is_alive'):
                is_running = download_thread.is_alive()
                self.session_manager.ui_bridge.post_log(
                    f"[DEBUG] 既存Thread検出: is_alive={is_running}", "debug"
                )
            
            if is_running:
                self.session_manager.ui_bridge.post_log(
                    "[DEBUG] ダウンロード実行中のため新規ダウンロードをスキップ", "warning"
                )
                return
        
        # ⭐修正: AsyncExecutor.execute_in_thread()を使用してThreadPoolExecutorでスレッド数を制限⭐
        future = self.parent.parent.async_executor.execute_in_thread(
            self.parent._download_url_thread,
            normalized_url, options
        )
        # ⭐重要: FutureオブジェクトをStateManagerに保存（重複実行防止に必須）⭐
        self.state_manager.set_download_thread(future)
        self.session_manager.ui_bridge.post_log("🚀 ダウンロードを開始しました", "info")
