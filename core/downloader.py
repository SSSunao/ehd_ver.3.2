# -*- coding: utf-8 -*-
"""
Core downloader functionality for EH Downloader - 統合版
SessionManager、DownloadTask、UIBridge、HttpClientによる統合実装
"""

import tkinter as tk
import threading
import time
import requests
import os
import json
import re
import math
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from PIL import Image
from config.settings import *
from config.constants import *
from config.download_options import DownloadOptions, DEFAULT_OPTIONS
from parser.gallery_info import GalleryInfo, GalleryMetadata, create_gallery_info
from core.communication.download_context import DownloadContext, DownloadRange
from core.managers.state_manager import StateManager, AppState
from config.settings import SkipUrlException, DownloadErrorException
from core.managers.session_manager import SessionManager, TaskResult
from core.network.download_task import DownloadTask
from core.communication.ui_bridge import UIBridge, UIEvent, UIEventType
from core.network.http_client import HttpClient
from core.handlers.completion_handler import CompletionHandler
from core.handlers.resume_manager import ResumeManager
from core.handlers.download_flow_manager import DownloadFlowManager
from core.handlers.image_processor import ImageProcessor
from core.handlers.compression_manager import CompressionManager
from core.progress_tracker import ProgressTracker, DownloadPhase, ThrottledProgressObserver

class EHDownloaderCore:
    def __init__(self, parent: Any, state_manager: Optional[Any] = None) -> None:
        """EHDownloaderCoreの初期化"""
        print("[DOWNLOADER_CORE] ========== EHDownloaderCore初期化開始 ==========")
        self.parent = parent
        
        # ⭐統合: StateManagerインスタンスを統一⭐
        if state_manager:
            self.state_manager = state_manager
        elif hasattr(parent, 'state_manager'):
            self.state_manager = parent.state_manager
        else:
            self.state_manager = StateManager()
        print("[DOWNLOADER_CORE] StateManager初期化完了")
        
        # ⭐Phase1: ProgressTracker - 進捗管理を一元化⭐
        self.progress_tracker = ProgressTracker()
        print("[DOWNLOADER_CORE] ProgressTracker初期化完了")
        
        # ⭐統合: SessionManager - 全てを統合⭐
        print("[DOWNLOADER_CORE] SessionManager初期化開始...")
        self.session_manager = SessionManager(
            parent=self.parent,
            state_manager=self.state_manager,
            error_handler=None,  # 後で設定
            download_callback=self._download_url_thread  # 既存のダウンロードロジックを活用
        )
        print("[DOWNLOADER_CORE] SessionManager初期化完了")
        
        # ⭐Phase5: CompletionHandler - 完了処理を分離⭐
        self.completion_handler = CompletionHandler(self)
        
        # ⭐Phase5.5: ResumeManager - 中断・再開処理を統合⭐
        self.resume_manager = ResumeManager(self)
        
        # ⭐Phase6: DownloadFlowManager - フロー制御を分離⭐
        self.flow_manager = DownloadFlowManager(self)
        
        # ⭐Phase7: ImageProcessor - 画像処理を分離⭐
        self.image_processor = ImageProcessor(self)
        
        # ⭐Phase7: CompressionManager - 圧縮処理を分離⭐
        self.compression_manager = CompressionManager(self)
        
        # ⭐Phase8: GalleryInfoManager - ギャラリー情報管理を分離⭐
        from core.managers.gallery_info_manager import GalleryInfoManager
        self.gallery_info_manager = GalleryInfoManager(self)
        
        # ⭐Phase9: ValidationManager - 検証処理を分離⭐
        from core.managers.validation_manager import ValidationManager
        self.validation_manager = ValidationManager(self)
        
        # ⭐Phase10: CompletionCoordinator - 完了処理の統合管理⭐
        from core.coordination.completion_coordinator import CompletionCoordinator
        self.completion_coordinator = CompletionCoordinator(self)
        print("[DOWNLOADER_CORE] CompletionCoordinator初期化完了")
        
        # ⭐Phase11: EventBus - イベント駆動型通信（将来の拡張用）⭐
        from core.coordination.event_bus import EventBus
        self.event_bus = EventBus(logger=self.session_manager.ui_bridge.post_log)
        self.event_bus.start()
        print("[DOWNLOADER_CORE] EventBus初期化完了（イベントログ用）")
        
        # ⭐Phase12: DownloadOrchestrator - ダウンロードシーケンス調整（将来の拡張用）⭐
        # 注意: 現在は使用されていません。イベント受信のみ行います。
        from core.coordination.download_orchestrator import DownloadOrchestrator
        self.download_orchestrator = DownloadOrchestrator(
            core=self,
            state_manager=self.state_manager,
            ui_bridge=self.session_manager.ui_bridge,
            event_bus=self.event_bus,
            completion_coordinator=self.completion_coordinator
        )
        print("[DOWNLOADER_CORE] DownloadOrchestrator初期化完了（将来の拡張用）")
        
        # ⭐Phase13: CompletionCoordinatorにEventBusを設定（循環参照回避）⭐
        self.completion_coordinator.event_bus = self.event_bus
        print("[DOWNLOADER_CORE] CompletionCoordinatorにEventBusを設定完了")
        
        # ⭐統合: 現在のタスク（状態変数を統合）⭐
        self.current_task: Optional[DownloadTask] = None
        
        # 後方互換性のために一部の変数を維持
        self.current_download_context = None
        self._sequence_complete_executed = False

        # GalleryDownloaderを必ず初期化
        from core.handlers.gallery_downloader import GalleryDownloader
        self._gallery_downloader = GalleryDownloader(self)
        
        # エラー情報（簡略化）
        self.error_info = {
            'has_error': False,
            'url': '',
            'page': 0,
            'type': '',
            'message': ''
        }
        
        # ⭐修正: スキップ要求はStateManager経由で一元管理⭐
        # self.skip_requested_url は削除（StateManager経由のみ）
        
        # URL処理の最適化
        self.url_cache = []  # キャッシュされたURL配列
        self.url_cache_valid = False  # キャッシュの有効性
        self.url_parsing_thread = None  # URL解析用スレッド
        
        # ⭐ギャラリー情報キャッシュ（初期変数取得の重複防止用）⭐
        self.cached_gallery_info = {}  # {url: gallery_info}
        # ⭐ ロック削除（単純な変数アクセス）⭐
        
        # ⭐追加: ダウンロード範囲マネージャー⭐
        
        # ⭐修正: リスタート要求はStateManager経由で一元管理⭐
        # self.restart_requested と self.restart_url は削除（StateManager経由のみ）
        
        # ⭐修正: フラグ管理をStateManagerに一元化⭐
        self.state_manager.download_state.skip_completion_check = False
        # - paused: state_manager.is_paused()
        # - is_running: state_manager.is_download_running()
        self.state_manager.download_state.error_occurred = False
        
        # 完了チェックスキップ
        # self.skip_completion_check = False  # StateManagerに統一
        
        # ⭐不足していたフラグを追加⭐
        # self.error_occurred = False  # StateManagerに統一
        self.gallery_completed = False
        
        # ネットワークリトライ
        self.network_retry_count = 0
        
        # 詳細な再開ポイント管理（統一）
        # ⭐削除: resume_pointはStateManagerで一元管理されるため不要⭐
        self.resuming_from_error = False
        
        # ダウンロードステージ管理
        self.current_stage = ""
        self.current_sub_stage = ""  # 現在のサブステージ
        self.stage_data = {}  # ステージ固有のデータ
        
        # 安全なフォルダ管理
        self.managed_folders = {}  # {normalized_url: folder_path}
        
        # 未完了フォルダ管理
        self.incomplete_folders = set()  # 未完了フォルダのセット
        self.incomplete_urls = set()  # 未完了URLのセット
        self.renamed_folders = set()  # リネーム済みフォルダのセット（重複リネーム防止）
        
        # ⭐Phase2統合: リトライカウンター管理はIntegratedRetryManagerに統一⭐
        # 互換性のため、プロパティアクセスで委譲
        
        # ⭐Seleniumスコープ管理⭐
        self.selenium_scope = "page"  # 'page', 'url', 'session' のいずれか（デフォルト: page）
        self.selenium_enabled_for_url = None  # Seleniumが有効化されたURL
        
        # ⭐追加: 復帰ポイント関連のフラグ⭐
        self._resume_in_progress = False  # 復帰処理中フラグ
        
        # ⭐次のダウンロード開始フラグ（競合防止）⭐
        self._start_next_download_running = False
        
        # ⭐追加: エラー復帰フラグ⭐
        self._error_resume_in_progress = False
        
        # ⭐追加: ログ出力済みURLセット（重複ログ防止）⭐
        self._logged_download_start_urls = set()
        
        # ⭐追加: 完了処理スキップフラグ（手動スキップ時の競合防止）⭐
        # self.skip_completion_check は既に存在するため、ここでは追加しない
        
        # ⭐追加: 最後に処理したURL（スキップ・完了判定用）⭐
        self._last_processed_url = None
        
        # ⭐追加: 現在ダウンロード中のスレッドID（デバッグ用）⭐
        self._current_thread_ids = set()
        
        # ⭐追加: URL進捗管理⭐
        self._url_progress_cache = {'completed': 0, 'total': 0}
        
        # ⭐追加: プログレス表示状態⭐
        self.progress_visible = False
        self.progress_cleanup_needed = False
        

        
        # ⭐追加: URL別のスレッドID管理⭐
        self._url_thread_ids = {}  # {url: thread_id}
        
        # ⭐追加: 復帰ポイント保存時のロック（競合防止）⭐
        self._resume_point_lock = threading.Lock()
        
        # ⭐追加: ダウンロード完了時のコールバック⭐
        self._download_complete_callbacks = []
        
        # ⭐追加: エラーハンドラー統合⭐
        self.error_handler = None  # 後で設定される
        
        # リトライマネージャーは不要（SessionManagerに統合済み）
        
        # ⭐追加: 現在のダウンロードセッション⭐
        self.current_session = None
        
        # Selenium有効範囲管理（リトライ時）
        self.selenium_enabled_for_retry = False  # リトライでSeleniumが有効化されたか
        self.selenium_enabled_url = None  # Seleniumが有効化されたURL（セッション用）
        
        # ⭐DEBUG: EHDownloaderCore初期化完了⭐
        print("[DOWNLOADER_CORE] ========== EHDownloaderCore初期化完了 ==========")
    
    def get_retry_count(self, image_page_url: str) -> int:
        """
        画像ページのリトライ回数を取得（⭐Phase2: IntegratedRetryManagerに委譲⭐）
        
        Args:
            image_page_url: 画像ページのURL
            
        Returns:
            リトライ回数
        """
        if hasattr(self.session_manager, 'retry_manager'):
            return self.session_manager.retry_manager.get_image_retry_count(image_page_url)
        return 0
    
    def increment_retry_count(self, image_page_url: str) -> int:
        """
        画像ページのリトライ回数を増加（⭐Phase2: IntegratedRetryManagerに委譲⭐）
        
        Args:
            image_page_url: 画像ページのURL
            
        Returns:
            増加後のリトライ回数
        """
        if hasattr(self.session_manager, 'retry_manager'):
            return self.session_manager.retry_manager.increment_image_retry_count(image_page_url)
        return 1
    
    def reset_retry_count(self, image_page_url: str) -> None:
        """
        画像ページのリトライ回数をリセット（⭐Phase2: IntegratedRetryManagerに委譲⭐）
        
        Args:
            image_page_url: 画像ページのURL
        """
        if hasattr(self.session_manager, 'retry_manager'):
            self.session_manager.retry_manager.reset_image_retry_count(image_page_url)
    
    def disable_selenium_after_success(self, url: str) -> None:
        """
        ダウンロード成功後にSeleniumを無効化（スコープに応じて）
        
        Args:
            url: 対象URL
        """
        try:
            if not self.selenium_enabled_for_retry:
                return  # リトライで有効化されていない場合は何もしない
            
            scope = self.selenium_scope
            self.session_manager.ui_bridge.post_log(f"【Selenium無効化チェック】スコープ: {scope}, URL: {url}")
            
            if scope == "page":
                # 1ページ: 即座に無効化
                self.session_manager.ui_bridge.post_log(f"【Selenium無効化】1ページモード: 即座に無効化")
                self._disable_selenium_internal()
                
            elif scope == "session":
                # 1セッション: 現在のURLが完了したら無効化
                if self.selenium_enabled_url == url:
                    self.session_manager.ui_bridge.post_log(f"【Selenium無効化】1セッションモード: URL完了により無効化")
                    self._disable_selenium_internal()
                else:
                    self.session_manager.ui_bridge.post_log(f"【Selenium無効化】1セッションモード: URL継続中のため無効化しない")
                    
            elif scope == "persistent":
                # 永続: 手動で無効化するまで維持
                self.session_manager.ui_bridge.post_log(f"【Selenium無効化】永続モード: 無効化しない")
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"【Selenium無効化】エラー: {e}", "error")
    
    def _disable_selenium_internal(self) -> None:
        """Selenium内部状態を無効化"""
        try:
            self.selenium_enabled_for_retry = False
            self.selenium_scope = "page"
            self.selenium_enabled_url = None
            
            # GUIのSelenium設定を更新
            self._update_selenium_gui(False)
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"【Selenium無効化】内部処理エラー: {e}", "error")
    
    def _update_selenium_gui(self, enabled: bool) -> None:
        """SeleniumのGUI状態を一元的に更新（常時Selenium）
        
        Args:
            enabled: Seleniumを有効化するかどうか
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            old_value = ui_bridge.get_option_value('selenium_always_enabled')
            if old_value is not None:
                if ui_bridge.set_option_value('selenium_always_enabled', enabled):
                    # 状態変更を通知
                    ui_bridge.publish_state_change('selenium_always_enabled', enabled, old_value)
                    ui_bridge.post_log(f"【Selenium GUI更新】{old_value} → {enabled}")
                else:
                    ui_bridge.post_log("【Selenium GUI更新】設定に失敗しました", "warning")
            else:
                ui_bridge.post_log("【Selenium GUI更新】selenium_always_enabled変数が見つかりません", "warning")
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"【Selenium GUI更新】エラー: {e}", "error")
    
    def _invalidate_url_cache(self) -> None:
        """URLキャッシュを無効化（ロック不要）"""
        self.url_cache_valid = False
        self.url_cache = []
    
    def _get_cached_urls(self) -> list:
        """
        キャッシュされたURL配列を取得（非同期で更新、ロック不要）
        
        Returns:
            URLリスト
        """
        if not self.url_cache_valid:
            # 非同期でURL解析を開始
            self._start_async_url_parsing()
            return []
        return self.url_cache.copy()
    
    def _start_async_url_parsing(self) -> None:
        """非同期でURL解析を開始"""
        if self.url_parsing_thread and self.url_parsing_thread.is_alive():
            return  # 既に解析中
        
        def parse_urls_async():
            try:
                # ⭐Phase2: UIBridge経由でテキストとURL解析⭐
                ui_bridge = self.session_manager.ui_bridge
                text_content = ui_bridge.get_url_text()
                urls = ui_bridge.parse_urls_from_text(text_content)
                
                # キャッシュを更新（ロック不要）
                self.url_cache = urls
                self.url_cache_valid = True
                
                # URLキャッシュ更新完了
                
                # 非同期解析完了後にURL進捗を更新
                ui_bridge.execute_gui_async(self._update_url_progress_after_parsing)
                
            except Exception as e:
                self.session_manager.ui_bridge.post_log(f"URL解析エラー: {e}", "error")
                # ロック不要
                self.url_cache = []
                self.url_cache_valid = False
        
        self.url_parsing_thread = threading.Thread(target=parse_urls_async, daemon=True)
        self.url_parsing_thread.start()
    
    def _update_url_progress_after_parsing(self) -> None:
        """
        非同期URL解析完了後の進捗更新
        """
        try:
            cached_urls = self._get_cached_urls()
            if cached_urls:
                # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                completed_count = self.state_manager.get_completed_url_count()
                # ⭐StateManager.set_progress()を使用（GUI層はイベントリスナー経由で自動更新）⭐
                self.state_manager.set_progress(completed_count, len(cached_urls))
                # 非同期解析後の進捗更新
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"非同期解析後の進捗更新エラー: {e}", "error")
    
    def _get_next_url_sync(self, current_index: int) -> Optional[str]:
        """
        次のURLを同期的に取得（Treeview統合版）
        
        Args:
            current_index: 現在のURLインデックス
            
        Returns:
            次のURLまたはNone
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            download_list_widget = ui_bridge.get_download_list_widget()
            
            # ⭐フェーズ3: Treeviewから次の待機中URLを取得⭐
            if download_list_widget:
                next_url = download_list_widget.get_next_url()
                if next_url:
                    normalized_url = ui_bridge.normalize_url(next_url)
                    
                    # スキップされたURLは取得しない
                    url_status = self.state_manager.get_url_status(normalized_url)
                    if url_status == 'skipped':
                        return None, None
                    
                    # ⭐修正: StateManager経由でステータス更新⭐
                    self.state_manager.set_url_status(normalized_url, "downloading")
                    
                    return next_url, normalized_url
                else:
                    return None, None
            
            # ⭐フォールバック: 既存のTextウィジェットから取得⭐
            # 現在の行のみを取得（UIBridge経由）
            line_content = ""  # TODO: 行単位の取得をUIBridgeに追加
            
            if not line_content:
                return None, None
            
            # 単一行のURL解析
            urls = ui_bridge.parse_urls_from_text(line_content)
            if urls:
                url = urls[0]
                normalized_url = ui_bridge.normalize_url(url)
                
                # ⭐重要: スキップされたURLは取得しない⭐
                url_status = self.state_manager.get_url_status(normalized_url)
                if url_status == 'skipped':
                    return None, None
                
                # ⭐修正: StateManager経由のみで管理⭐
                self.state_manager.set_url_status(normalized_url, "downloading")
                
                return url, normalized_url
            
            return None, None
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"単行URL取得エラー: {e}", "error")
            return None, None
        self.incomplete_folders = set()  # 未完了フォルダの記録
        
        # スキップカウンター
        self.current_skip_count = 0
        
        # 画像スキップ管理
        self.skipped_image_urls = set()
        self.incomplete_urls = set()
        
        # ダウンロードコンテキスト
        self.current_gallery_url = ""
        self.current_image_page_url = ""
        self.current_save_folder = ""
        # self.current_gallery_title = ""  # StateManagerで一元管理に移行
        self.gallery_metadata = {}
        self.artist = ""
        self.parody = ""
        self.character = ""
        self.group = ""
        
        # プログレス表示関連
        self.progress_visible = False
        
        # セッション管理
        self.session = None
        
        # ダウンロード状態フラグ（注：実際の状態はself.parent.is_running等を使用）
        # これらは互換性のために残す
        # ⭐修正: ダウンロード状態はStateManagerで管理（インスタンス変数は削除）⭐
        self._is_restart = False
        # ⭐修正: リスタート要求URLはStateManager経由で一元管理⭐
        # self.restart_requested_url は削除（StateManager経由のみ）
        
        # ダウンロード進捗管理
        self.current_page = 0
        self.current_progress = 0
        self.current_total = 0
        self.current_download_start_time = None
    
    # ========== スレッド状態管理の一元化 ==========
    # ==========================================
    
    # ⭐設計改善: プログレス管理はGUI層の責務⭐
    # update_url_progress, update_current_progress, update_progress_title はGUI層（main_window, progress_panel）で管理
    # downloader.pyからは StateManager.set_progress(), state_manager.update_progress_bar_state() を呼び出し、
    # GUI層はStateManagerのイベントリスナー経由で自動更新される設計に統一
    
    def update_current_progress(
        self, 
        current: int, 
        total: int, 
        status: str = "", 
        url: Optional[str] = None, 
        download_range_info: Optional[Dict[str, Any]] = None, 
        url_index: Optional[int] = None
    ) -> None:
        """
        現在のプログレス更新（イベント駆動型）
        
        Args:
            current: 現在の進捗
            total: 総数
            status: ステータスメッセージ
            url: 対象URL
            download_range_info: ダウンロード範囲情報
            url_index: URLインデックス
        """
        try:
            # ⭐修正: StateManagerに状態を更新（イベント駆動型GUI更新）⭐
            # コア層からGUI層への直接依存を削除
            
            # ⭐修正: URLが指定されていない場合はcurrent_gallery_urlを使用⭐
            if not url:
                url = self.state_manager.get_current_gallery_url()
            
            # ⭐追加: download_range_infoが指定されていない場合、コンテキストから取得⭐
            if download_range_info is None and self.current_download_context:
                applied_range = self.current_download_context.get('applied_range')
                if applied_range and applied_range.get('enabled'):
                    download_range_info = applied_range
            
            # ⭐追加: url_indexが指定されていない場合はcurrent_url_indexを取得⭐
            if url_index is None:
                url_index = self.state_manager.get_current_url_index()
                if hasattr(self.parent, 'log'):
                    self.session_manager.ui_bridge.post_log(f"[DEBUG] update_current_progress: get_current_url_index returned: {url_index}", "debug")
                # ⭐追加: それでもNoneの場合は、URLから検索⭐
                if url_index is None and url:
                    url_index = self.state_manager.get_url_index_by_url(url)
                    if hasattr(self.parent, 'log'):
                        self.session_manager.ui_bridge.post_log(f"[DEBUG] update_current_progress: get_url_index_by_url returned: {url_index}", "debug")
            
            # ⭐変更: url_indexが無効な場合は自動復旧を試みる⭐
            if url_index is None or url_index < 0:
                # エラーではなく、自動的にプログレスバーを作成して復旧
                if url:
                    # 現在のurl_indexを取得して新規作成
                    url_index = self.state_manager.get_current_url_index()
                    if url_index is not None and url_index >= 0:
                        progress_bar = self.state_manager.ensure_progress_bar(url, url_index)
                        if hasattr(self.parent, 'log'):
                            self.session_manager.ui_bridge.post_log(
                                f"[INFO] プログレスバーを自動作成しました: url_index={url_index}",
                                "info"
                            )
                    else:
                        # 復旧不可能な場合のみ警告
                        if hasattr(self.parent, 'log'):
                            self.session_manager.ui_bridge.post_log(
                                f"[WARNING] update_current_progress: url_indexが無効です: {url_index}, url={url[:50] if url else 'None'}...",
                                "warning"
                            )
                        return
                else:
                    return
            
            # ⭐変更: StateManager API経由で更新⭐
            # これにより、progress_panel内で既存のステータスを保持しつつ進捗情報を更新できる
            self.state_manager.update_progress_bar_state(
                url_index,
                current=current,
                total=total if total > 1 else None,  # totalが1より大きい場合のみ更新
                status=status,  # ⭐修正: 空文字列も有効な値として扱う⭐
                download_range_info=download_range_info  # ⭐追加: ダウンロード範囲情報を渡す⭐
            )
            
            # ⭐追加: download_range_infoを直接progress_infoに保存（タイミング問題を回避）⭐
            if download_range_info:
                progress_info = self.state_manager.get_progress_bar(url_index)
                if progress_info:
                    progress_info['download_range_info'] = download_range_info
                    self.state_manager.set_progress_bar(url_index, progress_info)
        except Exception as e:
            if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                self.session_manager.ui_bridge.post_log(f"プログレス更新エラー: {e}", "error")
    
    def update_progress_title(self, title: str, url_index: Optional[int] = None) -> None:
        """
        プログレスバーのタイトルを更新
        
        Args:
            title: タイトル文字列
            url_index: URLインデックス（オプション）
        """
        try:
            if url_index is None:
                url_index = self.state_manager.get_current_url_index()
            
            if url_index is not None and url_index >= 0:
                self.state_manager.update_progress_bar_state(
                    url_index,
                    title=title
                )
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"タイトル更新エラー: {e}", "error"
            )
    
    def _check_interrupt_request(self, normalized_url: str, url: Optional[str] = None) -> Optional[str]:
        """
        統一的な中断要求チェック（⭐Phase5.5: ResumeManagerへ委譲⭐）
        
        Args:
            normalized_url: 正規化されたURL
            url: 元のURL
            
        Returns:
            中断タイプ ('skip', 'restart', 'pause', 'stop') または None
        """
        return self.resume_manager.check_interrupt_request(normalized_url, url)
    
    def _handle_interrupt_request(self, interrupt_type: str, normalized_url: str, 
                                  current_page: int, save_folder: str, 
                                  download_range_info: Optional[Dict[str, Any]] = None, 
                                  absolute_page: Optional[int] = None, 
                                  url: Optional[str] = None, 
                                  actual_total_pages: Optional[int] = None, 
                                  reason_suffix: str = "") -> None:
        """
        統一的な中断要求処理（⭐Phase5.5: ResumeManagerへ委譲⭐）
        
        Args:
            interrupt_type: 中断タイプ ('skip', 'restart', 'pause', 'stop')
            normalized_url: 正規化されたURL
            current_page: 現在のページ番号（相対）
            save_folder: 保存フォルダ
            download_range_info: ダウンロード範囲情報
            absolute_page: 絶対ページ番号
            url: 元のURL
            actual_total_pages: 実際の総ページ数
            reason_suffix: ログメッセージの追加情報
        """
        self.resume_manager.handle_interrupt_request(
            interrupt_type, normalized_url, current_page, save_folder,
            download_range_info, absolute_page, url, actual_total_pages, reason_suffix
        )
    
    def _save_resume_point(self, url: str, page: int, folder: str, 
                          stage: str = "", sub_stage: str = "", 
                          stage_data: Optional[dict] = None, reason: str = "", 
                          image_page_url: str = "", 
                          current_url_index: Optional[int] = None, 
                          absolute_page: Optional[int] = None, 
                          explicit_download_range_info: Optional[Dict[str, Any]] = None) -> None:
        """
        詳細な再開ポイントの保存（UnifiedErrorResumeManagerへ委譲）
        
        Args:
            page: 相対ページ番号（表示用、1～565）
            absolute_page: 絶対ページ番号（ギャラリー全体での位置、285～850）。指定された場合はこちらを優先使用。
            explicit_download_range_info: 明示的に指定されたダウンロード範囲情報。指定された場合はこちらを優先使用。
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            resume_manager = ui_bridge.get_unified_error_resume_manager()
            
            # ⭐統合: UnifiedErrorResumeManagerへ委譲⭐
            if resume_manager:
                return resume_manager.save_resume_point_detailed(
                    url=url,
                    page=page,
                    folder=folder,
                    stage=stage,
                    sub_stage=sub_stage,
                    stage_data=stage_data,
                    reason=reason,
                    image_page_url=image_page_url,
                    current_url_index=current_url_index,
                    absolute_page=absolute_page,
                    explicit_download_range_info=explicit_download_range_info,
                    downloader_context=self  # ⭐重要: selfを渡してコンテキストを提供⭐
                )
            else:
                # フォールバック: unified_error_resume_managerが存在しない場合は最低限の保存
                ui_bridge.post_log("[WARNING] unified_error_resume_managerが利用できません。StateManagerのみに保存します", "warning")
                if url:
                    normalized_url = ui_bridge.normalize_url(url)
                    resume_data = {
                        'url': url or '',
                        'page': max(0, int(page or 0)),
                        'folder': folder or '',
                        'timestamp': time.time()
                    }
                    self.state_manager.set_resume_point(normalized_url, resume_data)
                return True
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"再開ポイント保存エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"再開ポイント保存エラー詳細: {traceback.format_exc()}", "error")
            return False
    
    def _set_current_stage(self, stage: str, sub_stage: str = "", stage_data: Optional[dict] = None) -> None:
        """
        現在のステージを設定
        
        Args:
            stage: ステージ名
            sub_stage: サブステージ名
            stage_data: ステージデータ
        """
        self.current_stage = stage
        self.current_sub_stage = sub_stage
        if stage_data:
            self.stage_data.update(stage_data)
        # ステージ設定: {stage}.{sub_stage}
    
    def _get_resume_info(self, url: str) -> Optional[dict]:
        """
        復帰情報を取得（StateManager経由で一元管理）
        
        Args:
            url: 対象URL
            
        Returns:
            復帰情報辞書、または None
        """
        try:
            if not url:
                return None
            
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            normalized_url = ui_bridge.normalize_url(url)
            resume_info = self.state_manager.get_resume_point(normalized_url)
            return resume_info
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"復帰情報取得エラー: {e}", "error")
            return None
    
    def _restore_resume_info(
        self, 
        normalized_url: str, 
        resume_info: dict, 
        options: Dict[str, Any], 
        use_mapping: bool = True
    ) -> Optional[int]:
        """
        復帰ポイントから復元処理を実行（UnifiedErrorResumeManagerへ委譲）
        
        Args:
            normalized_url: 正規化されたURL
            resume_info: 復帰情報
            options: ダウンロードオプション
            use_mapping: URLマッピングを使用するか
            
        Returns:
            復元されたページ番号、または None
            options: ダウンロードオプション
            use_mapping: Trueの場合、ダウンロード範囲の変更を判定して再計算する。Falseの場合、保存された相対ページ番号をそのまま使用（エラーレジューム時）
            
        Returns:
            Tuple[resume_page, total_pages, download_range_info]
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            resume_manager = ui_bridge.get_unified_error_resume_manager()
            
            # ⭐統合: UnifiedErrorResumeManagerへ委譲⭐
            if resume_manager:
                return resume_manager.restore_resume_info_detailed(
                    normalized_url=normalized_url,
                    resume_info=resume_info,
                    options=options,
                    use_mapping=use_mapping,
                    downloader_context=self  # ⭐重要: selfを渡してコンテキストを提供⭐
                )
            else:
                # フォールバック: unified_error_resume_managerが存在しない場合は簡易版
                ui_bridge.post_log("[WARNING] unified_error_resume_managerが利用できません。簡易復元を実行します", "warning")
                if not resume_info:
                    return None, 0, None
                
                # 最低限の復元処理
                saved_page = resume_info.get('page', 1)
                total_pages = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
                return saved_page, total_pages, None
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"復帰情報復元エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"復帰情報復元エラー詳細: {traceback.format_exc()}", "error")
            return 1, 0, None
    
    def _load_resume_point(self) -> Dict[str, Any]:
        """再開ポイントの読み込み（StateManager経由で一元管理）
        
        Returns:
            再開ポイント情報の辞書、なければ空辞書
        """
        try:
            # ⭐修正: StateManager経由で再開ポイントを取得⭐
            current_url = self.state_manager.get_current_gallery_url()
            if current_url:
                resume_info = self.state_manager.get_resume_point(current_url)
                if resume_info:
                    return resume_info
            return {}
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"再開ポイント読み込みエラー: {e}", "error")
            return {}
    
    # ⭐削除: _start_compression_task 完全実装（line 815の委譲ラッパーで十分）⭐
    # ⭐削除: _add_compression_complete_marker 完全実装（line 840の委譲ラッパーで十分）⭐
    # 重複メソッドを削除し、CompressionManagerへの委譲に統一
    
    def _get_download_range_value(self, value: str) -> str:
        """
        ダウンロード範囲の値を取得（プレースホルダーを除外）
        
        Args:
            value: 入力値
            
        Returns:
            内容値または空文字列
        """
        if value == "空欄は0" or value == "空欄は∞":
            return ""
        return value
    
    def reload_options_from_gui(self) -> None:
        """
        リスタート時にGUIからオプションを再読み込み
        
        Note:
            リスタート/レジューム時に呼び出されることを想定
            最新のGUI設定を反映するため
        """
        try:
            self.session_manager.ui_bridge.post_log("[INFO] オプションを再読み込み中...", "info")
            # オプションを再取得（キャッシュをクリア）
            self._cached_options = None
            new_options = self._get_current_options()
            self.session_manager.ui_bridge.post_log("[INFO] オプションの再読み込み完了", "info")
            return new_options
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"[ERROR] オプション再読み込みエラー: {e}", "error")
            return self._get_current_options()
    
    def _get_current_options(self) -> Dict[str, Any]:
        """現在のダウンロードオプションを取得（DownloadOptions API使用）
        
        Returns:
            Dict[str, Any]: オプション辞書（後方互換性のため辞書形式で返す）
        """
        try:
            # ⭐統合: DownloadOptions クラスAPIを使用⭐
            options = DownloadOptions.from_gui(self.parent)
            
            # バリデーション
            is_valid, error_msg = options.validate()
            if not is_valid:
                self.session_manager.ui_bridge.post_log(
                    f"⚠️ オプション検証エラー: {error_msg}、デフォルト値を使用します", 
                    "warning"
                )
                options = DEFAULT_OPTIONS
            
            # 辞書形式に変換（後方互換性のため）
            options_dict = options.to_dict()
            
            # folder_path を追加（DownloadOptionsに含まれていない）
            import os
            default_folder = os.path.join(os.path.expanduser("~"), "Documents")
            folder_path = getattr(self.parent, 'folder_var', default_folder)
            if hasattr(folder_path, 'get'):
                folder_path = folder_path.get()
            if not folder_path:
                folder_path = default_folder
            options_dict['folder_path'] = folder_path
            
            # resize_valuesがResizeValuesオブジェクトの場合は辞書に変換
            if hasattr(options_dict.get('resize_values'), 'to_dict'):
                options_dict['resize_values'] = options_dict['resize_values'].to_dict()
            
            # download_range値の処理（プレースホルダー除外）
            options_dict['download_range_start'] = self._get_download_range_value(options_dict.get('download_range_start', ""))
            options_dict['download_range_end'] = self._get_download_range_value(options_dict.get('download_range_end', ""))
            
            return options_dict
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"❌ オプション取得エラー: {e}、デフォルト値を使用します", 
                "error"
            )
            import traceback
            self.session_manager.ui_bridge.post_log(f"詳細: {traceback.format_exc()}", "error")
            
            # デフォルトオプションを辞書形式で返す
            default_dict = DEFAULT_OPTIONS.to_dict()
            import os
            default_dict['folder_path'] = os.path.join(os.path.expanduser("~"), "Documents")
            
            # resize_valuesが辞書でない場合は変換
            if hasattr(default_dict.get('resize_values'), 'to_dict'):
                default_dict['resize_values'] = default_dict['resize_values'].to_dict()
            
            return default_dict
    
    def _validate_download_range_options(self, options: Dict[str, Any]) -> bool:
        """
        ダウンロード範囲オプションの妥当性を検証
        
        Args:
            options: ダウンロードオプション
            
        Returns:
            検証結果
        """
        return self.validation_manager.validate_download_range_options(options)

    def _configure_ssl_settings(self) -> None:
        """SSL/TLS問題を回避するための設定（DH key too smallエラー対策）"""
        return self.validation_manager.configure_ssl_settings()
    
    def _validate_download_options(self) -> bool:
        """
        ダウンロード実行前のオプション検証
        
        Returns:
            検証結果
        """
        return self.validation_manager.validate_download_options()
    
    def _is_valid_eh_url(self, url: str) -> bool:
        """
        E-Hentai URLの形式検証
        
        Args:
            url: 検証対象URL
            
        Returns:
            有効な場合True
        """
        return self.validation_manager.is_valid_eh_url(url)

    def _process_image_resize(self, image_path: str, gallery_info: Dict[str, Any], 
                              page_num: int, image_info: Dict[str, Any], 
                              resize_values: Optional[tuple] = None) -> bool:
        """
        画像のリサイズ処理(ImageProcessorへ委譲)
        
        Args:
            image_path: 画像ファイルパス
            gallery_info: ギャラリー情報
            page_num: ページ番号
            image_info: 画像情報
            resize_values: リサイズ値(オプション)
            
        Returns:
            成功時True
        """
        return self.image_processor.process_image_resize(
            image_path, gallery_info, page_num, image_info, resize_values
        )
    
    def _get_resize_values_safely(self) -> Optional[tuple]:
        """
        resize_valuesを安全に取得(ImageProcessorへ委譲)
        
        Returns:
            リサイズ値タプルまたはNone
        """
        return self.image_processor.get_resize_values_safely()
    
    def _start_compression_task(self, folder_path: str, url: Optional[str] = None) -> None:
        """
        圧縮タスクを並行して開始（CompressionManagerへ委譲）
        
        Args:
            folder_path: 圧縮対象フォルダパス
            url: 関連URL（オプション）
        """
        return self.compression_manager.start_compression_task(folder_path, url)
    
    def _compress_folder(self, folder_path: str) -> bool:
        """
        フォルダの圧縮処理（CompressionManagerへ委譲）
        
        Args:
            folder_path: 圧縮対象フォルダパス
            
        Returns:
            成功時True
        """
        return self.compression_manager.compress_folder(folder_path)
    
    def _safe_delete_compressed_files(self, folder_path: str, resize_enabled: bool, keep_original: bool) -> bool:
        """
        圧縮済みファイルを安全に削除（CompressionManagerへ委譲）
        
        Args:
            folder_path: フォルダパス
            resize_enabled: リサイズ有効
            keep_original: 元画像を保持
            
        Returns:
            成功時True
        """
        return self.compression_manager.safe_delete_compressed_files(
            folder_path, resize_enabled, keep_original
        )
    
    def _remove_incomplete_prefix(self, folder_path: str) -> str:
        """
        未完了フォルダの接頭辞を削除（CompressionManagerへ委譲）
        
        Args:
            folder_path: フォルダパス
            
        Returns:
            削除後のパス
        """
        return self.compression_manager.remove_incomplete_prefix(folder_path)
    
    def rename_incomplete_folders_on_exit(self) -> None:
        """
        アプリ終了時に未完了フォルダに接頭辞を追加（CompressionManagerへ委譲）
        """
        if hasattr(self, 'incomplete_folders') and hasattr(self, 'renamed_folders'):
            return self.compression_manager.rename_incomplete_folders_on_exit(
                self.incomplete_folders, self.renamed_folders
            )
    
    def _add_compression_complete_marker(self, url_key: str) -> None:
        """
        URLの右側に（圧縮完了）マーカーを追加（CompressionManagerへ委譲）
        
        Args:
            url_key: URLキー
        """
        return self.compression_manager._add_compression_complete_marker(url_key)
    
    # ========================================
    # ⭐Phase8: ギャラリー情報管理の委譲メソッド⭐
    # ========================================
    
    def get_manga_title(self, soup: Any) -> str:
        """
        漫画タイトルを取得（GalleryInfoManagerへ委譲）
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            タイトル文字列
        """
        return self.gallery_info_manager.get_manga_title(soup)
    
    def get_artist_and_parody(self, soup: Any) -> tuple:
        """
        アーティストとパロディ情報を取得（GalleryInfoManagerへ委譲）
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            (artist, parody)のタプル
        """
        return self.gallery_info_manager.get_artist_and_parody(soup)
    
    def get_length(self, soup: Any) -> int:
        """
        ページ数の取得（GalleryInfoManagerへ委譲）
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            ページ数
        """
        return self.gallery_info_manager.get_length(soup)
    
    def _save_gallery_completion_info(self, url: str, save_folder: str, gallery_info: Dict[str, Any]) -> None:
        """
        ギャラリー完了時のダウンロード情報を保存（GalleryInfoManagerへ委譲）
        
        Args:
            url: ギャラリーURL
            save_folder: 保存フォルダ
            gallery_info: ギャラリー情報
        """
        return self.gallery_info_manager.save_gallery_completion_info(url, save_folder, gallery_info)
    
    def _save_batch_download_info(self) -> None:
        """
        全URL完了時の一括保存処理（GalleryInfoManagerへ委譲）
        """
        return self.gallery_info_manager.save_batch_download_info()
    
    def get_manga_title_original(self, soup: Any) -> str:
        """
        漫画タイトルを取得（元の実装、後方互換性のため維持）
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            タイトル文字列
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            title = ui_bridge.get_manga_title(soup)
            return title if title else "Unknown Title"
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"タイトル取得エラー: {e}", "error")
            return "Unknown Title"
    
    def create_new_folder_name(self) -> str:
        """
        新しいフォルダ名を作成
        
        Returns:
            フォルダ名文字列
        """
        try:
            # ⭐Phase2: UIBridge経由でアクセス⭐
            ui_bridge = self.session_manager.ui_bridge
            folder_name: str = ui_bridge.create_new_folder_name()
            return folder_name if folder_name else f"Unknown_{int(time.time())}"
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"フォルダ名作成エラー: {e}", "error")
            return f"Unknown_{int(time.time())}"
            if gdd_table:
                gdt_rows = gdd_table.find_all('tr')
                for row in gdt_rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].text.strip().replace(':', '')
                        value = cells[1].text.strip()
                        
                        if label == 'Length':
                            # "23 pages" のような形式からページ数を抽出
                            pages_match = re.search(r'(\d+)', value)
                            if pages_match:
                                return int(pages_match.group(1))
            
            # 代替方法：ページサムネイル数をカウント
            gdtm_divs = soup.find_all('div', {'class': 'gdtm'})
            if gdtm_divs:
                return len(gdtm_divs)
            
            return 0
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ページ数取得エラー: {e}", "error")
            return 0
    
    def navigate_to_first_image_page(self, gallery_soup: Any, wait_time_value: float) -> Optional[Any]:
        """
        最初の画像ページに移動
        
        Args:
            gallery_soup: BeautifulSoupオブジェクト
            wait_time_value: 待機時間（秒）
            
        Returns:
            最初の画像ページのBeautifulSoupオブジェクトまたはNone
        """
        try:
            # 複数の方法でサムネイルリンクを探す
            first_link: Optional[Any] = None
            
            # 方法1: 新しいサムネイル構造
            thumbnail_divs = gallery_soup.find_all('div', {'class': ['gdtm', 'gdtl']})
            if thumbnail_divs:
                for div in thumbnail_divs:
                    link = div.find('a')
                    if link and link.get('href'):
                        first_link = link
                        break
            
            # 方法2: より一般的なアプローチ
            if not first_link:
                links = gallery_soup.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    # E-Hentaiの画像ページURLパターンをチェック
                    if '/s/' in href and any(domain in href for domain in ['e-hentai.org', 'exhentai.org']):
                        first_link = link
                        break
            
            if not first_link:
                self.session_manager.ui_bridge.post_log("最初の画像ページへのリンクが見つかりません", "error")
                return None
            
            # URLを取得
            first_page_url = first_link.get('href')
            self.session_manager.ui_bridge.post_log(f"最初の画像ページURL: {first_page_url}")
            
            # 待機時間
            time.sleep(wait_time_value)
            
            # 画像ページを取得
            response = self.session_manager.http_client.get(first_page_url, timeout=20)
            response.raise_for_status()
            
            # BeautifulSoupでパース
            first_page_soup = BeautifulSoup(response.text, 'html.parser')
            return first_page_soup
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"最初の画像ページへの移動エラー: {e}", "error")
            return None
    
    def navigate_to_next_page(self, soup: Any, wait_time_value: float) -> Optional[Any]:
        """
        次のページへナビゲート（ネットワークエラー処理強化版）
        
        Args:
            soup: BeautifulSoupオブジェクト
            wait_time_value: 待機時間（秒）
            
        Returns:
            次のページのBeautifulSoupオブジェクトまたはNone
        """
        try:
            # "Next"リンクを検索
            next_link = soup.find('a', id='next')
            if not next_link or not next_link.get('href'):
                self.session_manager.ui_bridge.post_log("次のページリンクが見つかりませんでした")
                return None

            next_url = next_link['href']
            
            # 次のページにアクセス
            time.sleep(float(wait_time_value))
            
            try:
                response = self.session_manager.http_client.get(next_url, timeout=20)
                response.raise_for_status()
                
                if "Your IP address has been temporarily banned" in response.text:
                    raise Exception("IP address banned")
                
                # 現在のページURLを更新
                # ⭐ ロック不要（単純な変数代入）⭐
                self.current_image_page_url = next_url
                # ⭐Phase2: UIBridge経由でmain_windowにも反映⭐
                self.session_manager.ui_bridge.set_current_image_page_url(next_url)
                
                return BeautifulSoup(response.text, 'html.parser')
                
            except requests.exceptions.RequestException as req_err:
                # ネットワークエラー（回線切断等）を明確に区別
                if isinstance(req_err, (requests.exceptions.ConnectionError, 
                                      requests.exceptions.Timeout, 
                                      requests.exceptions.ConnectTimeout,
                                      requests.exceptions.ReadTimeout)):
                    error_msg = f"ネットワーク接続エラー（回線切断の可能性）: {req_err}"
                    self.session_manager.ui_bridge.post_log(error_msg, "error")
                    from config.settings import DownloadErrorException
                    raise DownloadErrorException(error_msg)
                else:
                    error_msg = f"HTTPリクエストエラー: {req_err}"
                    self.session_manager.ui_bridge.post_log(error_msg, "error")
                    from config.settings import DownloadErrorException
                    raise DownloadErrorException(error_msg)
            
        except Exception as e:
            if "DownloadErrorException" in str(type(e)):
                # DownloadErrorExceptionはそのまま再投げ
                raise
            error_msg = f"次のページへのナビゲーションに失敗: {e}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            from config.settings import DownloadErrorException
            raise DownloadErrorException(error_msg)
        
    def start_download_sequence(self) -> None:
        """
        ダウンロードシーケンスを開始する
        
        メインのダウンロード開始エントリーポイント
        """
        if self.state_manager.is_download_running():
            self.session_manager.ui_bridge.post_log("ダウンロードは既に実行中です。", "warning")
            return

        # ⭐修正: TreeviewからURLを取得⭐
        urls = []
        total_urls = 0
        
        # ⭐Phase2: UIBridge経由でアクセス⭐
        ui_bridge = self.session_manager.ui_bridge
        download_list_widget = ui_bridge.get_download_list_widget()
        
        # まずTreeviewから取得を試みる
        if download_list_widget:
            urls = download_list_widget.get_pending_urls()
            total_urls = len(urls)
        
        # Treeviewが空の場合、url_panelから取得を試みる
        if total_urls == 0:
            url_panel = ui_bridge.get_url_panel()
            if (url_panel and 
                hasattr(url_panel, 'get_valid_url_count_fast') and
                hasattr(url_panel, 'url_text') and
                url_panel.url_text):
                total_urls = url_panel.get_valid_url_count_fast()
                urls = []  # 高速化の場合は空リスト
            else:
                # フォールバック: 従来の方法
                text_content = ui_bridge.get_url_text()
                urls = ui_bridge.parse_urls_from_text(text_content)
                total_urls = len(urls)
        
        if total_urls == 0:
            self.session_manager.ui_bridge.post_log("ダウンロードするURLが指定されていません。", "warning")
            return

        self.session_manager.ui_bridge.post_log(f"ダウンロードを開始します。 (全{total_urls}件)")
        
        # ⭐追加: ダウンロード開始時のオプション情報をログ出力⭐
        current_options = self._get_current_options()
        self.session_manager.ui_bridge.post_log(
            f"[オプション] 保存先: {current_options.get('folder_path', '未設定')}", 
            "info"
        )
        self.session_manager.ui_bridge.post_log(
            f"[オプション] リサイズ: {current_options.get('resize_mode', 'off')} | "
            f"保存形式: {current_options.get('save_format', 'Original')} | "
            f"ファイル名: {current_options.get('save_name', 'Original')}", 
            "info"
        )
        if current_options.get('download_range_enabled', False):
            range_mode = current_options.get('download_range_mode', 'all')
            self.session_manager.ui_bridge.post_log(
                f"[オプション] ダウンロード範囲: {range_mode}", 
                "info"
            )
        
        # ⭐追加: 最初のURLのurl_indexを設定⭐
        if urls and len(urls) > 0:
            first_url = urls[0]
            # ⭐Phase2: UIBridge経由で正規化⭐
            normalized_first_url = ui_bridge.normalize_url(first_url)
            # url_indexを0に設定
            self.state_manager.set_current_url_index(0)
            # プログレスバーを初期化
            self.state_manager.download_state.progress_bars[0] = {
                'url': normalized_first_url,
                'state': {
                    'current': 0,
                    'total': 0,
                    'title': '準備中...',
                    'status': ''
                }
            }
        
        # ⭐修正: URL単位のダウンロード範囲を設定⭐
        current_options = self._get_current_options()
        download_range_enabled = current_options.get('download_range_enabled', False)
        
        if download_range_enabled:
            start = current_options.get('download_range_start', '')
            end = current_options.get('download_range_end', '')
            download_range_mode = current_options.get('download_range_mode', '全てのURL')
            
            try:
                start_int = int(start) if start else None
                end_int = int(end) if end else None
                
                if start_int is not None:
                    # download_range_modeに応じて適用範囲を決定
                    if download_range_mode == '最初のURLのみ':
                        # 最初のURLにのみダウンロード範囲を設定
                        first_url = urls[0] if urls else None
                        if first_url:
                            # ⭐Phase2: UIBridge経由で正規化⭐
                            normalized_first_url = ui_bridge.normalize_url(first_url)
                            self.state_manager.set_url_download_range(normalized_first_url, start_int, end_int)
                            self.session_manager.ui_bridge.post_log(f"[INFO] 最初のURLにダウンロード範囲を設定: {start_int}-{end_int if end_int else '最後まで'}")
                    else:  # '全てのURL'
                        # 全URLにダウンロード範囲を設定
                        for url in urls:
                            normalized_url = ui_bridge.normalize_url(url)
                            self.state_manager.set_url_download_range(normalized_url, start_int, end_int)
                        self.session_manager.ui_bridge.post_log(f"[INFO] 全URL({len(urls)}件)にダウンロード範囲を設定: {start_int}-{end_int if end_int else '最後まで'}")
            except (ValueError, TypeError) as e:
                self.session_manager.ui_bridge.post_log(f"[WARNING] ダウンロード範囲の設定エラー: {e}", "warning")
        
        # ⭐追加: StateManagerに総URL数を保存（URL進捗表示用）⭐
        if hasattr(self.state_manager, '_state_lock'):
            with self.state_manager._state_lock:
                if not hasattr(self.state_manager, '_total_url_count'):
                    self.state_manager._total_url_count = 0
                self.state_manager._total_url_count = total_urls
        
        # ⭐追加: URL進捗を初期化（StateManager経由）⭐
        self.state_manager.set_progress(0, total_urls)
        
        # プログレス状態をリセット
        self.progress_visible = False
        self.progress_cleanup_needed = False
        
        # 状態管理を設定
        # ⭐修正: state_managerのメソッドは内部でロックを取得するため、self.lockを取得した状態で呼び出すとデッドロックが発生する可能性がある⭐
        # そのため、state_managerのメソッドを呼び出す前にself.lockを取得しないようにする
        # StateManagerも同期
        self.state_manager.set_download_running(True)
        self.state_manager.set_paused(False)
        self.state_manager.set_current_url_index(0)
        
        # 完了フラグをリセット
        self._sequence_complete_executed = False
        
        # 重複実行防止フラグをリセット
        self._start_next_download_running = False
        
        # URLキャッシュを無効化（新しいダウンロード開始時）
        self._invalidate_url_cache()
        
        # URL状態をリセット
        for url in urls:
            normalized_url = self.parent.normalize_url(url)
            if normalized_url:
                self.state_manager.set_url_status(normalized_url, "pending")
        
        # ⭐修正: StateManager経由でスキップ・リスタート要求をクリア⭐
        self.state_manager.set_skip_requested_url(None)
        self.state_manager.set_restart_requested_url(None)
        self.state_manager.set_pause_requested(False)
        self.state_manager.download_state.skip_completion_check = False
        # ⭐重要: gallery_completedフラグもリセット⭐
        self.gallery_completed = False
        self.state_manager.download_state.error_occurred = False
        
        # URLの背景色とマーカーをリセット
        for tag in ["downloading", "paused_error", "completed", "skipped", "default", "resize_marker", "compression_marker", "hyperlink"]:
            self.parent.url_text.tag_remove(tag, "1.0", tk.END)
        
        # マーカーをリセット
        if hasattr(self, 'compression_complete_markers'):
            self.compression_complete_markers = {}
        
        # URLテキストからマーカーを削除
        content = self.parent.url_text.get("1.0", tk.END)
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            # マーカーを削除
            line = re.sub(r'\u200B?\(リサイズ完了\)', '', line)
            line = re.sub(r'\u200B?（圧縮完了）', '', line)
            new_lines.append(line)
        
        # 更新されたテキストを設定
        self.parent.url_text.delete("1.0", tk.END)
        self.parent.url_text.insert("1.0", '\n'.join(new_lines))
        
        # ハイパーリンクを再設定
        self.parent.url_panel._setup_hyperlinks()
        
        # 現在のダウンロード情報を完全にリセット
        self.state_manager.set_current_gallery_url("")
        self.state_manager.set_progress(0, 0)
        
        # フォルダ履歴のリセット（削除せずに保持）
        # last_download_folderは現在のダウンロードフォルダとして使用する
        
        # 追加の作業フォルダ情報リセット
        self.gallery_metadata = {}
        self.artist = ""
        self.parody = ""
        self.character = ""
        
        # ⭐重要: ギャラリー情報キャッシュをクリア⭐
        self.cached_gallery_info = {}
        
        # ⭐重要: スキップされた画像URLをクリア⭐
        if hasattr(self, 'skipped_image_urls'):
            self.skipped_image_urls = set()
        
        # ⭐重要: 現在のダウンロード状態をクリア⭐
        self.current_image_page_url = None
        self.current_save_folder = None
        self._resume_in_progress = False
        self.group = ""
        
        # ダウンロード開始時刻を設定
        self.current_download_start_time = time.time()
        
        # エラー状態のリセット（手動再開時は保持）
        if hasattr(self, 'error_info') and not getattr(self, 'resuming_from_error', False):
            self.error_info['has_error'] = False
            self.error_info['url'] = ''
            self.error_info['page'] = 0
            self.error_info['type'] = ''
            self.error_info['message'] = ''
        
        # ネットワーク復旧カウンターのリセット
        if hasattr(self, 'network_retry_count'):
            self.network_retry_count = 0
        
        # ⭐Phase2: UIBridge経由でGUI更新⭐
        ui_bridge.update_gui_for_running()
        # ⭐修正: タイマー管理をStateManagerに委譲（コア層からGUI層への依存を削除）⭐
        # timeはファイル先頭でインポート済み
        self.state_manager.set_elapsed_time_start(time.time())
        self.state_manager.set_elapsed_time_paused_start(None)
        # ⭐修正: 非同期スレッドで実行（GUIスレッドのブロッキングを防ぐ）⭐
        async_executor = ui_bridge.get_async_executor()
        if async_executor:
            async_executor.execute_in_thread(self._start_next_download)


    def _schedule_next_download(self, reason: str = "不明") -> None:
        """
        非同期次ダウンロードスケジュール（簡素化版）
        
        Args:
            reason: スケジュール理由
        """
        # ⭐簡素化: 最小限のチェックのみ⭐
        
        # 実行状態チェック
        if not self.state_manager.is_download_running():
            return
        
        # ⭐修正: _start_next_download_runningフラグチェック⭐
        if hasattr(self, '_start_next_download_running') and self._start_next_download_running:
            return
        
        # ⭐修正: 重複スケジュール防止⭐
        if hasattr(self, '_next_download_scheduled') and self._next_download_scheduled:
            return
        
        # スケジュール実行
        self._next_download_scheduled = True
        
        def _execute_next_download_async():
            try:
                self._next_download_scheduled = False
                
                # 実行状態を再チェック
                if not self.state_manager.is_download_running():
                    return
                
                # ⭐修正: _start_next_download_runningフラグチェック⭐
                if hasattr(self, '_start_next_download_running') and self._start_next_download_running:
                    return
                
                # ⭐修正: 次のURLのインデックスを進めてダウンロード開始⭐
                current_index = self.state_manager.get_current_url_index()
                next_index = current_index + 1
                self.session_manager.ui_bridge.post_log(f"[DEBUG] URLインデックス更新: {current_index} -> {next_index}", "debug")
                self.state_manager.set_current_url_index(next_index)
                
                # ⭐修正: 次のURLを取得してダウンロード開始⭐
                try:
                    url, normalized_url = self._get_next_url_sync(next_index)
                    if url:
                        self.session_manager.ui_bridge.post_log(f"[DEBUG] 次のURLを開始: index={next_index}, url={url[:50]}...", "debug")
                        
                        # ⭐修正: オプションを取得⭐
                        if hasattr(self.parent, '_load_options_for_download'):
                            self.parent._load_options_for_download()
                        
                        # オプションを辞書形式で取得
                        from config.download_options import DownloadOptions
                        options_obj = DownloadOptions.from_gui(self.parent)
                        options = options_obj.to_dict()  # ⭐修正: 辞書に変換⭐
                        
                        # ダウンロード処理を開始
                        print(f"[DEBUG] _schedule_next_download: self._download_url_thread呼び出し直前 url={url[:50]}")
                        self._download_url_thread(url, options)
                    else:
                        self.session_manager.ui_bridge.post_log(f"[DEBUG] 次のURLが見つかりません: index={next_index}", "info")
                        # 全体完了処理
                        self._on_sequence_complete()
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(f"[DEBUG] 次のURL取得エラー: {e}", "error")
                    import traceback
                    self.session_manager.ui_bridge.post_log(f"詳細: {traceback.format_exc()}", "error")
            except Exception as e:
                self.session_manager.ui_bridge.post_log(f"[スケジュール] エラー: {e}", "error")
                import traceback
                self.session_manager.ui_bridge.post_log(f"詳細: {traceback.format_exc()}", "error")
        
        # ⭐修正: 非同期スレッドで実行（GUIスレッドのブロッキングを防ぐ）⭐
        try:
            self.parent.async_executor.execute_in_thread(_execute_next_download_async)
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"[スケジュール] 非同期実行エラー: {e}", "error")
            self._next_download_scheduled = False

    def _schedule_next_download_after_manual_skip(self, reason: str = "手動スキップ後") -> None:
        """
        手動スキップ後の次ダウンロードスケジュール（エラー用スキップとは独立）
        
        Args:
            reason: スケジュール理由
        """
        # 重複チェック
        if hasattr(self, '_next_download_scheduled') and self._next_download_scheduled:
            return
        
        # ⭐追加: _start_next_download_runningフラグをチェック⭐
        if hasattr(self, '_start_next_download_running') and self._start_next_download_running:
            return
        
        # ⭐修正: スキップ要求がある場合は、スレッドの生存チェックをスキップ⭐
        # スキップ処理はループ脱出タイミングで検出されるため、スレッドが生きていてもスケジュールを実行
        skip_requested_url = self.state_manager.get_skip_requested_url()
        if not skip_requested_url:
            # スキップ要求がない場合のみ、ダウンロードスレッドの存在チェック
            download_thread = self.state_manager.get_download_thread()
            if download_thread and download_thread.is_alive():
                return
        
        # 実行状態チェック
        if not self.state_manager.is_download_running():
            return
        
        # スケジュール実行
        self._next_download_scheduled = True
        
        def _execute_next_download_after_manual_skip():
            self._next_download_scheduled = False
            # ⭐修正: 実行前に再度状態チェック（_start_next_downloadと同じチェック）⭐
            if hasattr(self, '_start_next_download_running') and self._start_next_download_running:
                return
            
            # ⭐修正: 非同期設計 - スキップ要求がある場合、現在のURLのダウンロードスレッドが終了するまで再スケジュール⭐
            skip_requested_url = self.state_manager.get_skip_requested_url()
            if skip_requested_url:
                # スキップ要求がある場合、現在のURLのダウンロードスレッドが終了するまで待機
                download_thread = self.state_manager.get_download_thread()
                if download_thread and download_thread.is_alive():
                    # スレッドがまだ実行中の場合は、少し待ってから再スケジュール
                    # 非同期で再スケジュール（タイミングがズレても正しく動作する）
                    self.parent.async_executor.execute_after(200, _execute_next_download_after_manual_skip)
                    return
                else:
                    # スレッドが終了した場合、スキップされたURLを処理
                    # ⭐修正: skip_requested_urlは_handle_interrupt_requestで既にクリアされている可能性があるため、
                    # スキップされたURLの状態を確認して処理する⭐
                    normalized_skip_url = self.parent.normalize_url(skip_requested_url) if hasattr(self.parent, 'normalize_url') else skip_requested_url
                    if normalized_skip_url:
                        # スキップされたURLの状態を確認
                        url_status = self.state_manager.get_url_status(normalized_skip_url)
                        if url_status == 'skipped':
                            # ⭐削除: current_url_indexは_handle_interrupt_requestで既にインクリメント済み⭐
                            # 復帰ポイントをクリア（念のため）
                            self.state_manager.clear_resume_point(normalized_skip_url)
                    
                    # ⭐修正: skip_requested_urlをクリア（スキップ処理が完了）⭐
                    self.state_manager.set_skip_requested_url(None)
            else:
                # ⭐修正: skip_requested_urlがNoneでも、スキップされたURLの状態を確認して処理を続行⭐
                # スキップ要求がない場合でも、スキップされたURLが存在する可能性があるため、処理を続行
                download_thread = self.state_manager.get_download_thread()
                if download_thread and download_thread.is_alive():
                    return
            
            if self.state_manager.is_download_running():
                # ⭐修正: 次のURLが存在するかチェック⭐
                current_url_index = self.state_manager.get_current_url_index()
                
                # ⭐追加: スキップされたURLをスキップする処理⭐
                while True:
                    url, normalized_url = self._get_next_url_sync(current_url_index)
                    
                    if not url or not normalized_url:
                        # 次のURLが存在しない場合は完了処理を実行
                        if hasattr(self.parent, 'url_panel') and hasattr(self.parent.url_panel, 'get_total_line_count_fast'):
                            max_lines = self.parent.url_panel.get_total_line_count_fast()
                        else:
                            max_lines = int(self.parent.url_text.index('end-1c').split('.')[0])
                        
                        if current_url_index >= max_lines:
                            self.session_manager.ui_bridge.post_log("🎉 全てのURLの処理が完了しました（スキップ後）", "info")
                            # 即座に完了処理を実行
                            self.state_manager.set_download_running(False)
                            self.state_manager.set_paused(False)
                            self.parent.async_executor.execute_gui_async(self.parent._on_sequence_complete)
                            return
                        else:
                            # 空行の場合は次の行に進む
                            self.session_manager.ui_bridge.post_log(f"空行または無効なURLをスキップ: 行{current_url_index + 1}")
                            current_url_index += 1
                            self.state_manager.set_current_url_index(current_url_index)
                            # ⭐修正: 空行をスキップした後、次のURLが存在しない場合、完了処理を実行⭐
                            # 次のURLが存在するかチェック
                            if hasattr(self.parent, 'url_panel') and hasattr(self.parent.url_panel, 'get_total_line_count_fast'):
                                max_lines = self.parent.url_panel.get_total_line_count_fast()
                            else:
                                max_lines = int(self.parent.url_text.index('end-1c').split('.')[0])
                            
                            if current_url_index >= max_lines:
                                # 全てのURLを処理した場合、完了処理を実行
                                if not (hasattr(self, '_sequence_complete_executed') and self._sequence_complete_executed):
                                    self._sequence_complete_executed = True
                                    self.state_manager.set_download_running(False)
                                    self.state_manager.set_paused(False)
                                    self.parent.async_executor.execute_gui_async(self.parent._on_sequence_complete)
                                return
                            continue
                    
                    # スキップされたURLをチェック
                    url_status = self.state_manager.get_url_status(normalized_url)
                    if url_status == 'skipped':
                        current_url_index += 1
                        self.state_manager.set_current_url_index(current_url_index)
                        continue
                    
                    # スキップされていないURLが見つかった
                    break
                
                # ⭐追加: スキップされたURLの復帰ポイントをクリア（念のため）⭐
                if url and normalized_url:
                    url_status_check = self.state_manager.get_url_status(normalized_url)
                    if url_status_check == 'skipped':
                        self.state_manager.clear_resume_point(normalized_url)
                
                # 次のURLが存在する場合はダウンロードを開始
                if hasattr(self, '_skip_retry_count'):
                    self._skip_retry_count = 0  # リセット
                # ⭐追加: 次のURLからDLを開始する前にstop_flagをクリア⭐
                self.state_manager.reset_stop_flag()
                # ⭐修正: skip_requested_urlはクリアしない⭐
                # skip_requested_urlは、現在のURLのダウンロードループ内でスキップが検出された時にクリアされる
                # 次のURLに移る前にクリアすると、現在のURLのダウンロードループ内でスキップチェックが機能しなくなる
                # 現在のURLのダウンロードループが終了するまで、skip_requested_urlを保持する必要がある
                self._start_next_download()
            else:
                pass
        
        # ⭐修正: 非同期スレッドで実行（GUIスレッドのブロッキングを防ぐ）⭐
        self.parent.async_executor.execute_in_thread(_execute_next_download_after_manual_skip)

    # ========================================
    # ⭐Phase4続き: 次ダウンロード処理のリファクタリング⭐
    # 221行のメソッドを複数の小メソッドに分割
    # ========================================
    
    def _check_download_preconditions(self) -> bool:
        """ダウンロード前提条件チェック（⭐Phase6: DownloadFlowManagerへ委譶⭐）
        
        Returns:
            bool: 継続可能ならTrue
        """
        return self.flow_manager.check_download_preconditions()
    
    def _handle_thread_cleanup(self) -> bool:
        """スレッドクリーンアップ処理（⭐Phase6: DownloadFlowManagerへ委譶⭐）
        
        Returns:
            bool: 継続可能ならTrue（待機中はFalse）
        """
        return self.flow_manager.handle_thread_cleanup()
    
    def _start_next_download(self) -> None:
        """
        次のURLのダウンロードを開始（⭐Phase4: リファクタリング済み⭐）
        """
        import traceback
        
        try:
            # 前提条件チェック
            if not self._check_download_preconditions():
                return
            
            # 実行中フラグ設定
            self._start_next_download_running = True
            
            # スレッドクリーンアップ
            if not self._handle_thread_cleanup():
                return
            
            # ⭐修正: オプション検証→URL取得→処理実行の流れを全て非同期スレッドで実行⭐
            def validate_and_proceed():
                try:
                    validation_result = self._validate_download_options()
                    # ⭐修正: 同じスレッド内で継続（GUIブロッキングを防ぐ）⭐
                    self._proceed_after_validation(validation_result)
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(f"オプション検証エラー: {e}", "error")
                    self._handle_sequence_error()
            
            # ⭐修正: バックグラウンドスレッドで実行（GUIスレッドをブロックしない）⭐
            self.parent.async_executor.execute_in_thread(validate_and_proceed)
        
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"_start_next_downloadエラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"トレースバック: {traceback.format_exc()}", "error")
            self._handle_sequence_error()
        finally:
            if hasattr(self, '_start_next_download_running'):
                self._start_next_download_running = False
    
    def _proceed_after_validation(self, validation_result: Dict[str, Any]) -> None:
        """
        検証後の処理（⭐Phase6: DownloadFlowManagerへ委譶⭐）
        
        Args:
            validation_result: 検証結果
        """
        self.flow_manager.proceed_after_validation(validation_result)
    
    def _proceed_after_url_fetch(self, url: str, normalized_url: str, current_url_index: int) -> None:
        """
        URL取得後の処理（⭐Phase6: DownloadFlowManagerへ委譲⭐）
        
        Args:
            url: URL
            normalized_url: 正規化URL
            current_url_index: 現在のURLインデックス
        """
        self.flow_manager.proceed_after_url_fetch(url, normalized_url, current_url_index)
    
    def _handle_empty_url(self, current_url_index: int) -> None:
        """
        空URLの処理（⭐Phase6: DownloadFlowManagerへ委譲⭐）
        
        Args:
            current_url_index: 現在のURLインデックス
        """
        self.flow_manager.handle_empty_url(current_url_index)
    
    def _handle_empty_url_result(self, current_url_index: int, max_lines: int) -> None:
        """
        空URL結果処理（⭐Phase6: DownloadFlowManagerへ委譲⭐）
        
        Args:
            current_url_index: 現在のURLインデックス
            max_lines: 最大行数
        """
        self.flow_manager.handle_empty_url_result(current_url_index, max_lines)
    
    def _handle_sequence_error(self) -> None:
        """
        シーケンスエラーの統一処理
        """
        self.state_manager.set_download_running(False)
        self.state_manager.set_paused(False)
        self.state_manager.set_app_state(AppState.ERROR)
        
        # エラー時に未完了フォルダを記録
        if hasattr(self, 'current_save_folder') and self.current_save_folder:
            if self.parent.rename_incomplete_folder.get():
                if not hasattr(self, 'incomplete_folders'):
                    self.incomplete_folders = set()
                self.incomplete_folders.add(self.current_save_folder)
            self.session_manager.ui_bridge.post_log(f"未完了フォルダとして記録: {os.path.basename(self.current_save_folder)}", "info")
        if hasattr(self, 'session_manager') and hasattr(self.session_manager, 'ui_bridge'):
            self.session_manager.ui_bridge.post_event(UIEvent(
                event_type=UIEventType.ERROR,
                data={'callback': self.parent._update_gui_for_error}
            ))

    def _handle_folder_missing_error(self, url: str, folder_error: Exception) -> None:
        """
        フォルダ削除エラーの特別処理
        
        Args:
            url: 対象URL
            folder_error: フォルダエラー例外
        """
        self.session_manager.ui_bridge.post_log(f"保存フォルダが削除されました: {getattr(folder_error, 'original_folder', '')}", "error")
        self.session_manager.ui_bridge.post_log("このURLをスキップして次のURLに進みます。", "info")
        
        # エラー状態をスキップ状態に変更
        self.state_manager.set_url_status(url, 'skipped')
        
        # ⭐削除: URL背景色更新はStateManagerリスナー経由で自動更新されるため不要⭐
        # self.parent.root.after(0, self.parent.update_url_background, url)
        
        # 次のURLの処理を開始
        self._schedule_next_download("シーケンスエラー")

    def _should_stop(self) -> bool:
        """統一された停止チェック
        
        全てのループ・処理でこのメソッドを使用して停止を検知する
        
        Returns:
            bool: 停止すべき場合True
        """
        return (
            not self.state_manager.is_download_running() or
            self.state_manager.get_stop_flag().is_set()  # ⭐修正: メソッド経由でアクセス⭐
        )
    
    def _should_skip(self) -> bool:
        """⭐追加: スキップ要求をチェック（停止とは独立）⭐
        
        スキップボタンが押された時のみTrueを返す
        停止フラグとは独立しており、次のURLに進むための判定に使用
        
        Returns:
            bool: スキップすべき場合True
        """
        return self.state_manager.is_skip_requested()
    
    def _download_url_thread(self, url: str, options: Dict[str, Any]) -> None:
        """
        ⭐リファクタリング版: URLのダウンロードを実行するスレッド⭐
        責任を分離し、保守性を向上
        
        Args:
            url: ダウンロード対象URL
            options: ダウンロードオプション
        """
        try:
            # 1. 初期化とバリデーション
            normalized_url = self._initialize_download(url, options)
            if not normalized_url:
                return
            
            # 2. 復帰ポイントとフォルダの準備（⭐DownloadContext使用⭐）
            context = self._prepare_download_context(normalized_url, options)
            
            # 3. ダウンロード実行
            print(f"[DEBUG] _download_url_thread: _execute_gallery_download呼び出し直前 url={url[:50]}")
            result = self._execute_gallery_download(
                context, options
            )
            
            # ⭐修正: 完了処理はgallery_downloader.py内で実行されるため、ここでは呼ばない⭐
            
        except SkipUrlException as e:
            self._handle_skip(url, str(e))
        except Exception as e:
            self._handle_download_error(url, e)
        finally:
            self._cleanup_download_thread()
    
    def _initialize_download(self, url: str, options: Dict[str, Any]) -> Optional[str]:
        """
        ダウンロード初期化とバリデーション
        
        Args:
            url: ダウンロード対象URL
            options: ダウンロードオプション
            
        Returns:
            正規化されたURL、または初期化失敗時None
        """
        try:
            # プログレスフラグ初期化
            if not hasattr(self, 'progress_visible'):
                self.progress_visible = False
            
            # URL正規化
            normalized_url = self.parent.normalize_url(url)
            
            # スキップチェック
            url_status = self.state_manager.get_url_status(normalized_url)
            if url_status == 'skipped':
                self.session_manager.ui_bridge.post_log(f"スキップ済みURL: {normalized_url}", "info")
                self._schedule_next_download("スキップ済み")
                return None
            
            # フラグリセット
            self.state_manager.download_state.skip_completion_check = False
            self.gallery_completed = False
            self.state_manager.download_state.error_occurred = False
            
            # 状態更新
            self.state_manager.set_url_status(normalized_url, "downloading")
            self.state_manager.set_current_gallery_url(normalized_url)
            self.parent.url_status[normalized_url] = "downloading"
            
            # ⭐DEBUG: 現在のURLインデックスを確認⭐
            current_url_index = self.state_manager.get_current_url_index()
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _initialize_download: url={normalized_url[:50]}, current_url_index={current_url_index}",
                "debug"
            )
            
            # プログレス更新
            self.session_manager.ui_bridge.post_progress(0, 1, "状態: ダウンロード中")
            
            # ダウンロード範囲検証
            is_valid, error_msg, range_info = self._validate_download_range_options(options)
            if not is_valid:
                self.session_manager.ui_bridge.post_log(f"ダウンロード範囲エラー: {error_msg}", "error")
                return None
            
            # ⭐修正: セッション初期化は不要（http_clientがスレッドローカルで管理）⭐
            # SSL設定を適用（必要な場合のみ）
            if hasattr(self, '_configure_ssl_settings'):
                self._configure_ssl_settings()
            
            # スレッド情報記録
            thread_id = threading.current_thread().ident
            thread_name = threading.current_thread().name
            self.state_manager.set_current_thread_id(thread_id)
            self._current_thread_ids.add(thread_id)
            self.current_download_start_time = time.time()
            
            # ⭐DEBUG: スレッド情報をログ出力⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] ダウンロードスレッド開始: ID={thread_id}, Name={thread_name}", "debug"
            )
            
            # ⭐変更: StateManager API経由でプログレスバーを作成⭐
            url_index = self.state_manager.get_current_url_index()
            if url_index is not None:
                # 型安全なProgressBarを作成（start_time自動設定）
                progress_bar = self.state_manager.create_progress_bar(
                    url=normalized_url,
                    url_index=url_index
                )
                # ⭐追加: start_timeを現在時刻に設定⭐
                current_time = time.time()
                # ⭐追加: 即座にGUIに反映（オブザーバーに通知）⭐
                self.state_manager.update_progress_bar_state(
                    url_index=url_index,
                    current=0,
                    total=0,
                    title="準備中...",
                    status="ダウンロード中",
                    start_time=current_time,  # ⭐追加: 開始時刻を設定⭐
                    paused_duration=0.0  # ⭐追加: 中断時間を初期化⭐
                )
            
            # ⭐修正: StateManager経由でステータス更新⭐
            self.state_manager.set_url_status(normalized_url, 'downloading')
            
            return normalized_url
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"初期化エラー: {e}", "error")
            return None
    
    def _prepare_download_context(self, normalized_url: str, options: Dict[str, Any]) -> DownloadContext:
        """ダウンロードコンテキストの準備（DownloadContext APIを使用）
        
        Returns:
            DownloadContext: 型安全なダウンロードコンテキストオブジェクト
        """
        # 復帰ポイント確認
        resume_info = self._get_resume_info(normalized_url)
        start_page = 1
        total_pages = 0
        save_folder = None
        download_range_info = None
        
        if resume_info:
            # 復帰ポイントから復元
            start_page, total_pages, download_range_info = self._restore_resume_info(
                normalized_url, resume_info, options
            )
            save_folder = resume_info.get('folder')
            
            if download_range_info:
                self.current_download_range_info = download_range_info
            
            # ⭐設計改善: プログレスバー表示は必要時のみ⭐
            # GUIはStateManagerの状態変化を監視して自動更新する設計が理想
            if not self.progress_visible:
                self.session_manager.ui_bridge.post_event(UIEvent(
                    event_type=UIEventType.STATUS_UPDATE,
                    data={'callback': self.parent.show_current_progress_bar}
                ))
        
        # ⭐修正: フォルダ作成はギャラリー情報取得後に行うため、ここでは作成しない⭐
        # 復帰ポイントがある場合のみ、save_folderをチェック
        if resume_info and save_folder:
            # 復帰情報があればそのフォルダを使用
            if not os.path.exists(save_folder):
                # フォルダが存在しなければ、後で作成
                save_folder = None
        
        # ⭐統合: DownloadContextオブジェクトを生成⭐
        context = DownloadContext.from_legacy(
            url=normalized_url,
            save_folder=save_folder,  # この時点ではNoneの可能性あり
            start_page=start_page,
            total_pages=total_pages,
            resume_info=resume_info,
            download_range_info=download_range_info
        )
        
        # ⭐統合: current_download_contextも更新（後方互換性）⭐
        self.current_download_context = context.to_legacy_dict()
        
        return context
    
    def _execute_gallery_download(self, context: DownloadContext, options: Dict[str, Any]) -> bool:
        """ギャラリーダウンロード実行（DownloadContext使用）
        
        Args:
            context: ダウンロードコンテキスト
            options: ダウンロードオプション
            
        Returns:
            bool: 成功時True
        """
        try:
            # ⭐統合: contextから情報を取得⭐
            url = context.url
            start_page = context.start_page
            total_pages = context.total_pages
            
            # ⭐Phase 2: ギャラリー情報取得（タイトル含む）⭐
            gallery_pages = self._get_gallery_pages(url, options)
            
            if not gallery_pages:
                raise Exception("ギャラリーページ情報の取得に失敗")
            
            # ⭐修正: gallery_pages全体を使用（image_page_urlsキーを含む）⭐
            page_list = gallery_pages.get('image_page_urls', [])  # 正しいキー名
            
            total_pages = gallery_pages.get('total_pages', len(page_list))
            
            gallery_title = gallery_pages.get('title', 'Unknown')  # タイトル取得
            
            # ⭐重要: ProgressBarタイトルをStateManager経由で設定⭐
            url_index = self.state_manager.get_current_url_index()
            if url_index is not None:
                self.state_manager.set_progress_bar_title(url_index, gallery_title)
            
            # ⭐Phase 3: フォルダ作成（タイトル取得後）⭐
            # [DEBUG] print("!!! Phase 3開始: save_folder取得", flush=True)
            save_folder = context.save_folder
            # [DEBUG] print(f"!!! save_folder取得完了: '{save_folder}'", flush=True)
            
            # [DEBUG] print("!!! save_folderチェック開始", flush=True)
            if not save_folder or not os.path.exists(save_folder):
                # [DEBUG] print("!!! save_folder作成必要、folder_name_mode取得", flush=True)
                # ⭐カスタムフォルダ名対応⭐
                folder_name_mode = options.get('folder_name_mode', 'h1_priority')
                # [DEBUG] print(f"!!! folder_name_mode: '{folder_name_mode}'", flush=True)
                
                if folder_name_mode == 'custom':
                    # [DEBUG] print("!!! カスタムモード: custom_template取得", flush=True)
                    # カスタムテンプレートを使用
                    custom_template = options.get('custom_folder_name', '{artist}_{title}')
                    # [DEBUG] print(f"!!! custom_template: '{custom_template}'", flush=True)
                    
                    # [DEBUG] print("!!! _format_folder_name呼び出し", flush=True)
                    safe_title = self._format_folder_name(custom_template, gallery_pages, page_num=0)
                    # [DEBUG] print(f"!!! _format_folder_name完了: '{safe_title}'", flush=True)
                    
                    # [DEBUG] print("!!! post_log呼び出し（カスタムフォルダ名）", flush=True)
                    self.session_manager.ui_bridge.post_log(f"カスタムフォルダ名適用: テンプレート='{custom_template}' → 結果='{safe_title}'", "info")
                    # [DEBUG] print("!!! post_log完了", flush=True)
                else:
                    # [DEBUG] print("!!! 通常モード: sanitize_filename呼び出し", flush=True)
                    # 通常のフォルダ名（タイトルをsanitize）
                    safe_title = self.sanitize_filename(gallery_title)
                    # [DEBUG] print(f"!!! sanitize_filename完了: '{safe_title}'", flush=True)
                
                # [DEBUG] print("!!! create_save_folder呼び出し", flush=True)
                save_folder = self.create_save_folder(
                    options.get('folder_path', ''),
                    safe_title,
                    options.get('duplicate_folder_mode', 'rename')
                )
                # [DEBUG] print(f"!!! create_save_folder完了: '{save_folder}'", flush=True)
                
                if not save_folder:
                    raise SkipUrlException("Folder creation failed")
                
                # contextを更新
                # [DEBUG] print("!!! context.save_folder更新", flush=True)
                context.save_folder = save_folder
                # [DEBUG] print("!!! context.save_folder更新完了", flush=True)
            else:
                # [DEBUG] print("!!! save_folder既存OK（作成スキップ）", flush=True)
                pass  # ⭐修正: elseブロックが空にならないよう明示的にpass⭐
            
            # フォルダ情報保存
            # [DEBUG] print("!!! managed_folders更新開始", flush=True)
            if not hasattr(self, 'managed_folders'):
                self.managed_folders = {}
            self.managed_folders[url] = save_folder
            # [DEBUG] print("!!! managed_folders更新完了", flush=True)
            
            # [DEBUG] print("!!! current_save_folder設定開始", flush=True)
            self.current_save_folder = save_folder
            self.parent.current_save_folder = save_folder
            # [DEBUG] print("!!! current_save_folder設定完了", flush=True)
            
            # ⭐統合: contextを更新⭐
            # [DEBUG] print("!!! context更新開始（total_pages, gallery_title, image_page_urls）", flush=True)
            context.total_pages = total_pages
            context.gallery_title = gallery_title
            context.image_page_urls = page_list
            # [DEBUG] print("!!! context更新完了", flush=True)
            
            # ⭐DEBUG: ダウンロード実行直前⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _download_gallery_pages()呼び出し直前: save_folder={save_folder}, start_page={start_page}, total_pages={total_pages}",
                "debug"
            )
            
            # ダウンロード実行（gallery_pages全体を渡す）
            success = self._gallery_downloader.download_gallery_pages(
                save_folder, start_page, total_pages, url,
                options.get('wait_time', 1),
                options.get('sleep_value', 3),
                options.get('save_format', 'Original'),
                options.get('save_name', 'Original'),
                options.get('custom_name', '{page}'),
                options.get('resize_mode', '縦幅上限'),
                options.get('resize_values', {}),
                gallery_title or '',
                options,  # optionsはここで位置引数として渡す
                self.parent,  # parentは必要に応じて渡す（なければNone）
                None  # gallery_infoは現状Noneで渡す
            )
            
            return success
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ダウンロード実行エラー: {e}", "error")
            return False
    
    def _finalize_download(self, url: str, save_folder: str, options: Dict[str, Any]) -> None:
        """
        ダウンロード完了処理
        
        Args:
            url: 対象URL
            save_folder: 保存フォルダ
            options: ダウンロードオプション
        """
        try:
            self._handle_download_completion(url, save_folder, options)
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"完了処理エラー: {e}", "error")
    
    def _handle_skip(self, url: str, reason: str) -> None:
        """
        スキップ処理
        
        Args:
            url: 対象URL
            reason: スキップ理由
        """
        normalized_url = self.parent.normalize_url(url)
        self.state_manager.set_url_status(normalized_url, "skipped")
        self.session_manager.ui_bridge.post_log(f"URLスキップ: {url} - {reason}", "info")
        self._schedule_next_download(f"スキップ: {reason}")
    
    def _cleanup_download_thread(self) -> None:
        """
        ダウンロードスレッドのクリーンアップ
        """
        thread_id = threading.current_thread().ident
        # ⭐修正: _current_thread_idsから削除⭐
        self._current_thread_ids.discard(thread_id)
        
        download_thread = self.state_manager.get_download_thread()
        # ⭐修正: Futureの場合はidentが存在しないため、hastattrでチェック⭐
        if download_thread and hasattr(download_thread, 'ident') and download_thread.ident == thread_id:
            self.state_manager.set_download_thread(None)
        
        if hasattr(self, '_start_next_download_running'):
            self._start_next_download_running = False
    
    def _resume_from_image_page_thread(self, image_page_url: str, save_folder: str, 
                                       current_page: int, total_pages: int, 
                                       gallery_url: str, options: Dict[str, Any]) -> None:
        """
        画像ページから直接再開する専用スレッド（エラー時のみ使用）
        
        Args:
            image_page_url: 画像ページURL
            save_folder: 保存フォルダ
            current_page: 現在ページ
            total_pages: 総ページ数
            gallery_url: ギャラリーURL
            options: ダウンロードオプション
        """
        try:
            # ⭐修正: セッション初期化は不要（http_clientがスレッドローカルで管理）⭐
            # SSL設定を適用（必要な場合のみ）
            if hasattr(self, '_configure_ssl_settings'):
                self._configure_ssl_settings()
            
            # スレッドIDを記録
            thread_id = threading.current_thread().ident
            self._current_thread_ids.add(thread_id)
            
            # 状態設定
            # ⭐ ロック不要（単純な変数代入）⭐
            self.current_gallery_url = gallery_url
            self.current_image_page_url = image_page_url
            self.current_save_folder = save_folder
            self.current_page = current_page
            self.total_pages = total_pages
            
            # main_windowにも反映
            self.parent.current_image_page_url = image_page_url
            self.parent.current_save_folder = save_folder
            self.current_progress = current_page - 1  # 進行状況を正確に設定
            self.current_total = total_pages
            # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
            self.state_manager.set_url_status(gallery_url, "downloading")
            
            self.session_manager.ui_bridge.post_log(f"【画像ページ再開】ページ {current_page}/{total_pages} から再開: {image_page_url}")
            self.session_manager.ui_bridge.post_log(f"【画像ページ再開】作業フォルダ: {save_folder}")
            
            # プログレスバーを表示・更新
            # ⭐修正: 既存のプログレスバーがある場合はshow_current_progress_bar()を呼ばない⭐
            url_index = None
            if hasattr(self.parent, 'current_url_index'):
                url_index = self.parent.current_url_index
            elif hasattr(self, 'state_manager'):
                url_index = self.state_manager.get_current_url_index()
            
            existing_progress_exists = False
            if url_index is not None and hasattr(self.parent, 'progress_panel'):
                # ⭐修正: StateManagerから取得（コア層からGUI層への依存を削除）⭐
                existing_progress = self.state_manager.get_progress_bar(url_index)
                if existing_progress:
                    existing_progress_exists = True
            
            # ⭐設計改善: プログレスバー表示は必要時のみ⭐
            if not self.progress_visible and not existing_progress_exists:
                if hasattr(self, 'session_manager') and hasattr(self.session_manager, 'ui_bridge'):
                    self.session_manager.ui_bridge.post_event(UIEvent(
                        event_type=UIEventType.STATUS_UPDATE,
                        data={'callback': self.parent.show_current_progress_bar}
                    ))
            
            # UIBridge経由でプログレス更新を投稿
            if hasattr(self, 'session_manager') and hasattr(self.session_manager, 'ui_bridge'):
                self.session_manager.ui_bridge.post_progress(current_page, total_pages, f"ページ {current_page} から再開中...")
            
            # 既存フォルダ存在確認
            if not os.path.exists(save_folder):
                self.session_manager.ui_bridge.post_log(f"【画像ページ再開】フォルダが見つかりません: {save_folder}")
                os.makedirs(save_folder, exist_ok=True)
                self.session_manager.ui_bridge.post_log(f"【画像ページ再開】フォルダを再作成: {save_folder}")
            
            # 管理対象フォルダに記録
            self.managed_folders[gallery_url] = save_folder
            
            # 終了チェック
            # ⭐修正: StateManager経由でstop_flagを確認⭐
            if self.state_manager.get_stop_flag().is_set():
                self.session_manager.ui_bridge.post_log("スレッド終了が要求されました。", "info")
                return
            
            # 画像ページを取得（スキップ時はURLが不明なのでギャラリーページから取得）
            if image_page_url:
                self.session_manager.ui_bridge.post_log(f"【画像ページ再開】画像ページを取得中: {image_page_url}")
                response = self.session_manager.http_client.get(image_page_url, timeout=20)
                response.raise_for_status()
                image_soup = BeautifulSoup(response.text, 'html.parser')
            else:
                # 画像スキップ時はギャラリーページから該当ページのURLを取得
                self.session_manager.ui_bridge.post_log(f"【画像ページ再開】ギャラリーページから画像ページURLを取得: ページ{current_page}")
                gallery_response = self.session_manager.http_client.get(gallery_url, timeout=20)
                gallery_response.raise_for_status()
                gallery_soup = BeautifulSoup(gallery_response.text, 'html.parser')
                
                # ページ番号から画像ページURLを取得
                image_links = gallery_soup.find_all('a', href=True)
                target_image_url = None
                
                for link in image_links:
                    href = link.get('href', '')
                    if f'/{current_page}' in href and '/s/' in href:
                        if href.startswith('http'):
                            target_image_url = href
                        else:
                            target_image_url = f"https://e-hentai.org{href}"
                        break
                
                if not target_image_url:
                    raise Exception(f"ページ{current_page}の画像ページURLが見つかりません")
                
                self.session_manager.ui_bridge.post_log(f"【画像ページ再開】取得した画像ページURL: {target_image_url}")
                response = self.session_manager.http_client.get(target_image_url, timeout=20)
                response.raise_for_status()
                image_soup = BeautifulSoup(response.text, 'html.parser')
                
                # current_image_page_urlを更新
                self.current_image_page_url = target_image_url
                # main_windowにも反映
                self.parent.current_image_page_url = target_image_url
            
            # タイトル取得（プログレスバー用）
            manga_title = f"Resume Page {current_page}"
            
            # _download_gallery_pagesを呼び出してエラーページから継続
            self._gallery_downloader.download_gallery_pages(
                save_folder,
                current_page,  # 現在のページから開始
                total_pages,
                gallery_url,
                options.get('wait_time', 1),
                options.get('sleep_value', 3),
                options.get('save_format', 'Original'),
                options.get('save_name', 'Original'),
                options.get('custom_name', '{page}'),
                options.get('resize_mode', '縦幅上限'),
                options.get('resize_values', {}),
                manga_title,
                options
            )
            
            # ⭐修正: 完了処理は _finalize_download で実行されるため削除⭐
            # 通常のダウンロードフローと統一し、二重実行を防止
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"画像ページ再開エラー: {e}", "error")
            # ⭐修正: エラー処理結果を確認（戻り値は使用しないが、エラー処理は実行される）⭐
            if hasattr(self.parent, 'downloader_core'):
                self.parent.downloader_core._handle_download_error(gallery_url, e)
        finally:
            # スレッド終了時の後処理（非同期クリーンアップ）
            thread_id = threading.current_thread().ident
            def cleanup_resume_thread_state():
                # ⭐修正: _current_thread_idsから削除⭐
                self._current_thread_ids.discard(thread_id)
            
            # 非同期でクリーンアップを実行（AsyncExecutor使用）
            self.parent.async_executor.execute_gui_async(cleanup_resume_thread_state)
                
    # ========================================
    # ⭐Phase5: 完了処理 - CompletionHandlerへ委譲（後方互換性維持）⭐
    # ========================================
    
    def _handle_url_skipped(self, normalized_url: str) -> bool:
        """スキップされたURLの処理（CompletionHandlerへ委譲）"""
        return self.completion_handler.handle_url_skipped(normalized_url)
    
    def _handle_url_restarted(self, normalized_url: str, save_folder: str, options: Dict[str, Any]) -> bool:
        """リスタートされたURLの処理（CompletionHandlerへ委譲）"""
        return self.completion_handler.handle_url_restarted(normalized_url, save_folder, options)
    
    def _handle_url_error(self, normalized_url: str) -> bool:
        """エラー発生時のURL処理（⭐Phase5.5: EnhancedErrorHandlerへ委譲⭐）"""
        # エラーフラグをクリア
        self.state_manager.download_state.error_occurred = False
        
        return self.parent.enhanced_error_handler.handle_url_completion_error(
            normalized_url, 
            self.state_manager, 
            self.session_manager,
            lambda url_idx, status_label: self.completion_handler._update_progress_status(url_idx, status_label),
            lambda url: self.completion_handler._get_url_index_for_update(url)
        )
    
    def _get_url_index_for_update(self, normalized_url: str) -> Optional[int]:
        """URL更新用のインデックスを取得（CompletionHandlerへ委譲）"""
        return self.completion_handler._get_url_index_for_update(normalized_url)
    
    def _update_progress_status(self, url_index: int, status_label: str) -> None:
        """プログレスバーのステータスを更新（CompletionHandlerへ委譲）"""
        self.completion_handler._update_progress_status(url_index, status_label)
    
    def _handle_url_completed_successfully(self, normalized_url: str, save_folder: str, options: Dict[str, Any]) -> bool:
        """正常完了時のURL処理（CompletionHandlerへ委譲）"""
        return self.completion_handler.handle_url_completed_successfully(normalized_url, save_folder, options)
    
    def _handle_incomplete_folder(self, normalized_url: str, save_folder: str) -> None:
        """未完了フォルダの処理（CompletionHandlerへ委譲）"""
        self.completion_handler._handle_incomplete_folder(normalized_url, save_folder)
    
    def _add_progress_history(self, normalized_url: str) -> None:
        """プログレス履歴に追加（CompletionHandlerへ委譲）"""
        self.completion_handler._add_progress_history(normalized_url)
    
    def _cleanup_download_session(self) -> None:
        """ダウンロードセッションのクリーンアップ（CompletionHandlerへ委譲）"""
        self.completion_handler._cleanup_download_session()
    
    def _handle_download_completion(self, url: str, save_folder: str, options: Dict[str, Any]) -> None:
        """完了処理（⭐Phase5: CompletionHandlerへ委譲⭐）"""
        try:
            # 状態チェック
            if not self.state_manager.is_download_running():
                return
            
            normalized_url = self.parent.normalize_url(url)
            auto_start_next = True
            
            # スキップ処理（CompletionHandlerへ委譲）
            skip_requested_url = self.state_manager.get_skip_requested_url()
            if skip_requested_url == normalized_url:
                auto_start_next = self.completion_handler.handle_url_skipped(normalized_url)
            # リスタート処理（CompletionHandlerへ委譲）
            elif self.state_manager.get_restart_requested_url() == normalized_url:
                auto_start_next = self.completion_handler.handle_url_restarted(normalized_url, save_folder, options)
            # エラー処理（CompletionHandlerへ委譲）
            elif self.state_manager.download_state.error_occurred:
                auto_start_next = self.completion_handler.handle_url_error(normalized_url)
            # 正常完了処理（CompletionHandlerへ委譲）
            else:
                auto_start_next = self.completion_handler.handle_url_completed_successfully(normalized_url, save_folder, options)
            
            # ⭐修正: 次のURLが存在するか動的にチェック（URL編集対応）⭐
            current_url_index = self.state_manager.get_current_url_index()
            
            # ⭐修正: UIBridge経由で現在のURLリストを取得（動的）⭐
            try:
                text_content = self.session_manager.ui_bridge.get_url_text()
                urls = self.session_manager.ui_bridge.parse_urls_from_text(text_content)
                total_urls = len(urls)
                self.session_manager.ui_bridge.post_log(f"[DEBUG] URL完了チェック: current_url_index={current_url_index}, total_urls={total_urls}", "debug")
            except Exception as e:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] URL取得エラー: {e}", "error")
                total_urls = current_url_index + 1  # エラー時は現在のURLが最後と仮定
            
            # ⭐修正: 最後のURLの場合は_on_sequence_completeを呼ぶ⭐
            if current_url_index >= total_urls - 1:  # 0-indexedなので-1
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 最後のURL完了: 全体完了処理を実行", "info")
                # ⭐修正: 直接実行（既にバックグラウンドスレッドから呼ばれている）⭐
                self._on_sequence_complete()
                return
            
            # ⭐修正: 次のURLに進む前にインデックスをインクリメント⭐
            self.session_manager.ui_bridge.post_log(f"[DEBUG] 次のURLに進む: current_index={current_url_index} -> {current_url_index + 1}", "debug")
            
            # ⭐修正: 次のダウンロードをスケジュール⭐
            if self.state_manager.is_download_running() and auto_start_next:
                self._schedule_next_download("完了処理")
            elif self.state_manager.is_download_running():
                self._schedule_next_download("完了処理（auto_start_next=False）")
        
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"完了処理エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"完了処理エラー詳細: {traceback.format_exc()}", "error")
            
            # エラー時も次のURLに進む
            if self.state_manager.is_download_running():
                self._schedule_next_download("完了処理エラー")
                return
            
            # エラーフラグ確認
            if self.state_manager.download_state.error_occurred:
                self.session_manager.ui_bridge.post_log("【エラー処理】エラーフラグ検出のためcurrent_url_index更新をスキップ")
                return
            
            # エラー時もindexを更新して次のURLに進む
            if self.state_manager.is_download_running() and not auto_start_next:
                current_index = self.state_manager.get_current_url_index()
                self.state_manager.set_current_url_index(current_index + 1)
                self._schedule_next_download("エラー処理")

    def _on_sequence_complete(self) -> None:
        """シーケンス完了時の処理"""
        print("[DEBUG] _on_sequence_complete: start")
        # 重複実行を防ぐ
        if hasattr(self, '_sequence_complete_executed') and self._sequence_complete_executed:
            print("[DEBUG] _on_sequence_complete: already executed, return")
            return

        # ⭐中断フラグがセットされている場合は完了処理をスキップ⭐
        # ⭐修正: StateManager経由でstop_flagを確認⭐
        if self.state_manager.get_stop_flag().is_set():
            self.session_manager.ui_bridge.post_log("【シーケンス】中断フラグ検出のため完了処理をスキップします。", "warning")
            print("[DEBUG] _on_sequence_complete: stop_flag set, return")
            return

        # ⭐gallery_infoキャッシュをクリア（全URL完了時）⭐
        if hasattr(self, 'cached_gallery_info'):
            self.cached_gallery_info.clear()

        # ⭐ ロック不要（単純な変数代入）⭐
        urls = self.parent.url_text.get("1.0", tk.END).strip().splitlines()
        valid_urls = [url.strip() for url in urls if url.strip()]
        current_url_index = self.state_manager.get_current_url_index()
        current_valid_index = sum(1 for url in urls[:current_url_index] if url.strip())

        # エラー状態のURLがあるかチェック
        # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
        error_urls = self.state_manager.get_error_urls()
        if error_urls:
            self.session_manager.ui_bridge.post_log(f"【シーケンス】エラー状態のURLが残っています: {len(error_urls)}件")
            for error_url in error_urls:
                self.session_manager.ui_bridge.post_log(f"  - エラー中: {error_url}")
            # エラー状態では完了処理をスキップ
            self.session_manager.ui_bridge.post_log("【シーケンス】エラー状態のため完了処理をスキップします。", "warning")
            print("[DEBUG] _on_sequence_complete: error_urls present, return")
            return

        # ⭐一時停止状態の場合も完了処理をスキップ⭐
        if self.state_manager.is_paused():
            self.session_manager.ui_bridge.post_log("【シーケンス】一時停止状態のため完了処理をスキップします。", "warning")
            print("[DEBUG] _on_sequence_complete: paused, return")
            return
        
        # 最後のURLの場合のみis_runningをFalseに設定
        if current_valid_index >= len(valid_urls):
                self._sequence_complete_executed = True  # フラグ設定
                self.state_manager.set_download_running(False)
                self.state_manager.set_paused(False)
                
                # 現在のURLの状態を確認
                # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                current_url_status = self.state_manager.get_url_status(self.current_gallery_url)
                
                # 最後にダウンロードしたフォルダを保存
                if hasattr(self, 'current_save_folder') and self.current_save_folder:
                    self.last_download_folder = self.current_save_folder
                    
                    # 圧縮処理：完了状態のURLのみ対象
                    if self.parent.compression_enabled.get() and current_url_status == "completed":
                        try:
                            folder_to_compress = self.current_save_folder
                            # 最後のURLの場合のみis_runningをFalseに設定
                            if current_valid_index >= len(valid_urls):
                                print("[DEBUG] _on_sequence_complete: last url, entering finalization")
                                self._sequence_complete_executed = True  # フラグ設定
                                self.state_manager.set_download_running(False)
                                self.state_manager.set_paused(False)

                                # 現在のURLの状態を確認
                                # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                                current_url_status = self.state_manager.get_url_status(self.current_gallery_url)

                                # 最後にダウンロードしたフォルダを保存
                                if hasattr(self, 'current_save_folder') and self.current_save_folder:
                                    self.last_download_folder = self.current_save_folder

                                    # 圧縮処理：完了状態のURLのみ対象
                                    if self.parent.compression_enabled.get() and current_url_status == "completed":
                                        try:
                                            folder_to_compress = self.current_save_folder
                                            # ⭐修正: 直接圧縮処理を開始（非同期実行）⭐
                                            self._start_compression_task(folder_to_compress, self.current_gallery_url)
                                            self.session_manager.ui_bridge.post_log(f"[DEBUG] 圧縮処理開始: {folder_to_compress}", "debug")
                                        except Exception as e:
                                            self.session_manager.ui_bridge.post_log(f"圧縮処理の開始中にエラー: {e}", "error")
                                    elif current_url_status == "skipped":
                                        self.session_manager.ui_bridge.post_log(f"URLがスキップされたため圧縮処理をスキップ: {self.current_gallery_url}", "info")
                        except Exception as e:
                            self.session_manager.ui_bridge.post_log(f"圧縮処理ブロックで例外: {e}", "error")

                        # 現在のURL関連の状態をクリア
                        self.current_gallery_url = None
                        self.current_image_page_url = None
                        # ⭐修正: StateManager経由でダウンロードスレッドをクリア⭐
                        self.state_manager.set_download_thread(None)

                        # 進行状況表示をクリア
                        self.current_progress = 0
                        self.current_total = 0

                        # URLリストの進行状況を更新（高速化版）
                        # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                        completed = self.state_manager.get_completed_url_count()

                        # 高速なURL総数取得を使用
                        if (hasattr(self.parent, 'url_panel') and 
                            hasattr(self.parent.url_panel, 'get_valid_url_count_fast') and
                            hasattr(self.parent.url_panel, 'url_text') and
                            self.parent.url_panel.url_text):
                            total = self.parent.url_panel.get_valid_url_count_fast()
                        else:
                            # フォールバック: 従来の方法
                            current_urls = self.parent._parse_urls_from_text(self.parent.url_text.get("1.0", tk.END))
                            total = len(current_urls)

                        # ⭐最終進捗更新（StateManager経由）⭐
                        self.state_manager.set_progress(completed, total)

                        # 「保存先」ボタンを最後にダウンロードしたフォルダに更新（完了した場合のみ）
                        if hasattr(self, 'last_download_folder') and self.last_download_folder:
                            # 実際にダウンロード完了したURLがある場合のみ更新
                            # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                            completed_urls = self.state_manager.get_completed_urls()
                            if completed_urls:
                                # フォルダパスの親ディレクトリのみ保持
                                last_folder_parent = os.path.dirname(self.last_download_folder)
                                if last_folder_parent and os.path.exists(last_folder_parent):
                                    if hasattr(self.parent, 'folder_var'):
                                        self.parent.folder_var.set(last_folder_parent)

                                # ⭐修正: 完了処理が重複して実行されないようにする⭐
                                if not (hasattr(self, '_sequence_complete_executed') and self._sequence_complete_executed):
                                    self._sequence_complete_executed = True
                                    self.session_manager.ui_bridge.post_log("🎉 全てのURLの処理が完了しました", "info")
                                    self.parent._update_gui_for_idle()  # GUI状態を更新
                                    # ⭐全URL完了時の一括保存処理⭐
                                    self._save_batch_download_info()

                                # エラーがあった場合は警告
                                # ⭐修正: StateManagerのメソッドを使用（ロック管理はStateManager内で行う）⭐
                                errors = self.state_manager.get_error_url_count()
                                if errors > 0:
                                    self.session_manager.ui_bridge.post_log(f"警告: {errors}個のURLでエラーが発生しました", "warning")
                                print("[DEBUG] _on_sequence_complete: end (finalization block)")
                            else:
                                print("[DEBUG] _on_sequence_complete: not last url, scheduling next download")
                                # 次のURLの処理を開始
                                self._schedule_next_download("シーケンス完了")

                                # 経過時間タイマーを停止
                                if hasattr(self, 'elapsed_time_timer_id') and self.elapsed_time_timer_id:
                                    self.parent.root.after_cancel(self.elapsed_time_timer_id)
                                    self.elapsed_time_timer_id = None
                                print("[DEBUG] _on_sequence_complete: end (schedule next)")
        if not hasattr(self, '_gallery_downloader'):
            from core.handlers.gallery_downloader import GalleryDownloader
            self._gallery_downloader = GalleryDownloader(self)
        
        # 処理を委譲
        # 未定義の場合はデフォルト値をセット
        save_folder = getattr(self, 'current_save_folder', getattr(self.parent, 'current_save_folder', './download'))
        start_page = getattr(self, 'current_page', 1)
        total_pages = getattr(self, 'total_pages', 1)
        url = getattr(self, 'current_gallery_url', None)
        wait_time_value = 1
        sleep_value_sec = 3
        save_format_option = 'Original'
        save_name_option = 'Original'
        custom_name_format = '{page}'
        resize_mode = '縦幅上限'
        resize_values = {}
        manga_title = ''
        options = getattr(self, 'current_options', {})
        gallery_info = getattr(self, 'current_gallery_info', {})
        return self._gallery_downloader.download_gallery_pages(
            save_folder, start_page, total_pages, url,
            wait_time_value, sleep_value_sec, save_format_option,
            save_name_option, custom_name_format, resize_mode,
            resize_values, manga_title, options, gallery_info
        )
    
    # ========================================
    # ⭐Phase3: ギャラリーページ取得のリファクタリング⭐
    # 368行のメソッドを5-7個の小メソッドに分割
    # ========================================
    
    def _check_gallery_cache(self, normalized_url: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """ギャラリー情報のキャッシュチェック（復帰ポイント・メモリキャッシュ）
        
        Args:
            normalized_url: 正規化されたギャラリーURL
            options: ダウンロードオプション
            
        Returns:
            Optional[Dict]: キャッシュされたgallery_info、なければNone
        """
        # 1. 復帰ポイントから取得を試みる
        resume_info = self._get_resume_info(normalized_url)
        if resume_info and resume_info.get('gallery_info'):
            # ダウンロード範囲が変更されたかチェック
            cached_download_range_info = resume_info.get('download_range_info')
            current_options = options if options else self._get_current_options()
            
            # 範囲比較（直接実装）
            range_changed = False
            if cached_download_range_info:
                cached_enabled = cached_download_range_info.get('enabled', False)
                current_enabled = current_options.get('download_range_enabled', False)
                
                if cached_enabled != current_enabled:
                    range_changed = True
                elif cached_enabled and current_enabled:
                    cached_start = cached_download_range_info.get('start')
                    cached_end = cached_download_range_info.get('end')
                    current_start = int(current_options.get('download_range_start', 1) or 1)
                    current_end_value = current_options.get('download_range_end', '')
                    current_end = int(current_end_value) if current_end_value and str(current_end_value).strip() else None
                    
                    if cached_start != current_start or cached_end != current_end:
                        range_changed = True
            elif current_options.get('download_range_enabled', False):
                range_changed = True
            
            if range_changed:
                # 範囲が変更された場合、詳細なログを出力
                cached_desc = f"{cached_download_range_info.get('start')}-{cached_download_range_info.get('end')}" if cached_download_range_info and cached_download_range_info.get('enabled') else "無効"
                
                if current_options.get('download_range_enabled', False):
                    current_start = int(current_options.get('download_range_start', 1) or 1)
                    current_end_value = current_options.get('download_range_end', '')
                    current_end = int(current_end_value) if current_end_value and str(current_end_value).strip() else "∞"
                    current_desc = f"{current_start}-{current_end}"
                else:
                    current_desc = "無効"
                
                self.session_manager.ui_bridge.post_log(
                    f"[INFO] ダウンロード範囲が変更されたため({cached_desc} → {current_desc})、gallery_infoを再取得します"
                )
                return None  # キャッシュ無効
            else:
                # 範囲が変更されていない場合、キャッシュを使用
                cached_info = resume_info['gallery_info']
                self.session_manager.ui_bridge.post_log(
                    f"✅ 復帰ポイントからgallery_infoを復元: {len(cached_info['image_page_urls'])}個のURL（初期変数取得をスキップ）"
                )
                # メモリキャッシュにも保存
                self.cached_gallery_info[normalized_url] = cached_info
                return cached_info
        
        # 2. メモリキャッシュから取得を試みる
        if normalized_url in self.cached_gallery_info:
            cached_info = self.cached_gallery_info[normalized_url]
            self.session_manager.ui_bridge.post_log(
                f"✅ キャッシュからgallery_infoを復元: {len(cached_info['image_page_urls'])}個のURL（初期変数取得をスキップ）"
            )
            return cached_info
        
        # キャッシュなし
        self.session_manager.ui_bridge.post_log("🆕 キャッシュが存在しないため、初期変数を取得します...")
        return None
    
    def _fetch_gallery_html(self, normalized_url: str) -> str:
        """ギャラリーページのHTMLを取得（Selenium対応・コンテンツ警告処理込み）
        
        Args:
            normalized_url: 正規化されたギャラリーURL
            
        Returns:
            str: ギャラリーページのHTML
            
        Raises:
            DownloadErrorException: 取得失敗時
        """
        self.session_manager.ui_bridge.post_log(f"📥 ギャラリー情報を取得中... (URL: {normalized_url[:50]}...)", "info")
        
        # Seleniumを使用するかチェック
        use_selenium = False
        if hasattr(self.parent, 'selenium_always_enabled') and hasattr(self.parent, 'selenium_use_for_page_info'):
            selenium_always_enabled = self.parent.selenium_always_enabled.get() if hasattr(self.parent.selenium_always_enabled, 'get') else False
            selenium_use_for_page_info = self.parent.selenium_use_for_page_info.get() if hasattr(self.parent.selenium_use_for_page_info, 'get') else False
            use_selenium = selenium_always_enabled and selenium_use_for_page_info
            
            if use_selenium:
                self.session_manager.ui_bridge.post_log("[INFO] ページ情報取得にSeleniumを使用します")
        
        # HTMLを取得
        try:
            if use_selenium:
                html = self._get_page_with_selenium(normalized_url)
                if not html:
                    raise ValueError("Seleniumでのページ取得に失敗しました")
            else:
                response = self.session_manager.http_client.get(normalized_url, timeout=30)
                response.raise_for_status()
                html = response.text
            
            # コンテンツ警告処理
            if "Content Warning" in html or "Offensive For Everyone" in html:
                html = self._handle_content_warning(html, normalized_url)
            
            return html
            
        except requests.exceptions.RequestException as req_err:
            # ネットワークエラーを明確に区別
            if isinstance(req_err, (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ReadTimeout
            )):
                error_msg = f"ネットワーク接続エラー（回線切断の可能性）: {req_err}"
                self.session_manager.ui_bridge.post_log(error_msg, "error")
                self._handle_network_error_with_retry(normalized_url, req_err)
                raise DownloadErrorException(error_msg)
            else:
                error_msg = f"HTTPリクエストエラー: {req_err}"
                self.session_manager.ui_bridge.post_log(error_msg, "error")
                raise DownloadErrorException(error_msg)
    
    def _handle_content_warning(self, html: str, normalized_url: str) -> str:
        """コンテンツ警告ページをバイパス
        
        Args:
            html: 警告ページのHTML
            normalized_url: ギャラリーURL
            
        Returns:
            str: バイパス後のHTML
        """
        self.session_manager.ui_bridge.post_log(f"コンテンツ警告検出: {normalized_url}")
        
        # 方法1: ?nw=sessionパラメータを追加してGETリクエスト
        try:
            self.session_manager.ui_bridge.post_log("警告ページをバイパスします（?nw=session）...")
            bypass_url = normalized_url + ("&" if "?" in normalized_url else "?") + "nw=session"
            response = self.session_manager.http_client.get(bypass_url, timeout=20)
            response.raise_for_status()
            html = response.text
            self.session_manager.ui_bridge.post_log("警告をバイパスし、ギャラリーページを取得しました。")
            return html
        except Exception as e:
            # 方法2: フォームを解析してPOSTする（フォールバック）
            self.session_manager.ui_bridge.post_log(f"GETバイパス失敗、フォームPOSTを試みます: {e}")
            from bs4 import BeautifulSoup
            warning_soup = BeautifulSoup(html, 'html.parser')
            form = warning_soup.find('form')
            if form:
                # フォームのaction URLを取得
                action_url = form.get('action', normalized_url)
                if not action_url.startswith('http'):
                    # 相対URLの場合、絶対URLに変換
                    from urllib.parse import urljoin
                    action_url = urljoin(normalized_url, action_url)
                
                # フォームデータを収集
                post_data = {}
                for input_tag in form.find_all('input'):
                    input_name = input_tag.get('name')
                    input_value = input_tag.get('value', '')
                    if input_name:
                        post_data[input_name] = input_value
                
                self.session_manager.ui_bridge.post_log(f"フォームPOST: {action_url}, data={post_data}")
                # ⭐修正: parent.sessionではなくhttp_clientを使用⭐
                response = self.session_manager.http_client.post(action_url, data=post_data, timeout=20)
                response.raise_for_status()
                html = response.text
                self.session_manager.ui_bridge.post_log("フォームPOSTでギャラリーページを取得しました。")
                return html
            else:
                self.session_manager.ui_bridge.post_log("警告: フォームが見つかりません。警告ページをスキップできない可能性があります。", "warning")
                return html
    
    def _extract_all_image_page_urls(self, html: str, normalized_url: str, start_page: int) -> tuple:
        """全画像ページURLを抽出（⭐Phase3: サイト固有ロジック⭐）
        
        Args:
            html: ギャラリーページのHTML
            normalized_url: 正規化されたギャラリーURL
            start_page: 開始ページ番号
            
        Returns:
            tuple: (all_image_urls, total_images, total_pages)
        """
        # 総画像数を取得
        pattern_total = re.compile(r'Showing \d+ - \d+ of ([\d,]+) images')
        m = pattern_total.search(html)
        if not m:
            self.session_manager.ui_bridge.post_log(f"[DEBUG] 画像枚数パターンマッチ失敗。HTML長: {len(html)}文字")
            if "Showing" in html:
                showing_index = html.find("Showing")
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 'Showing'が見つかりました: {html[showing_index:showing_index+100]}")
            else:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] HTMLに'Showing'が含まれていません。HTML先頭500文字: {html[:500]}")
            raise ValueError("画像枚数が取得できませんでした")
        
        total_images = int(m.group(1).replace(',', ''))
        pages = math.ceil(total_images / 20)
        self.session_manager.ui_bridge.post_log(f"総画像数={total_images}, 総ページ数={pages}")
        
        # ⭐Phase1: ProgressTracker で進捗を作成⭐
        url_index = 0  # 仮のURL識別子（後で実際のインデックスに変更可能）
        self.progress_tracker.create(
            url_index=url_index,
            phase=DownloadPhase.URL_FETCHING,
            total=pages,
            status="個別ページURL取得中"
        )
        
        # タグとメタデータ抽出
        all_tags = self._extract_all_tags(html)
        self.session_manager.ui_bridge.post_log(f"抽出されたタグ: {list(all_tags.keys())}")
        self._update_metadata_with_tags(all_tags)
        self._extract_gallery_metadata(html, normalized_url)
        
        # 全画像ページURLを取得
        self.session_manager.ui_bridge.post_log("📥 個別ページのURLを取得中...")
        self.session_manager.ui_bridge.post_log(f"[DEBUG] URL取得ループ開始: pages={pages}, normalized_url={normalized_url[:80]}")
        all_image_urls = []
        pattern_thumbs = re.compile(r'https://e-hentai\.org/s/[a-z0-9]+/\d+-\d+')
        
        # 全ページを巡回してURL収集
        self.session_manager.ui_bridge.post_log(f"[DEBUG] range(pages)作成完了、forループ開始")
        for p in range(pages):
            self.session_manager.ui_bridge.post_log(f"[DEBUG] ループ反復 p={p}/{pages} 開始")
            # ⭐Phase1: ProgressTrackerで進捗更新⭐
            self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: ProgressTracker更新開始")
            self.progress_tracker.update(url_index, current=p + 1)
            self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: ProgressTracker更新完了")
            
            # 進捗ログ（20ページごとに間引き）
            if p > 0 and p % 20 == 0:
                self.session_manager.ui_bridge.post_log(f"  取得中... {p}/{pages}ページ")
            
            self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: URL構築開始")
            url = normalized_url if p == 0 else f"{normalized_url}?p={p}"
            self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: URL構築完了: {url[:80]}")
            
            try:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: HTML取得開始 (p==0: {p==0})")
                if p == 0:
                    html_page = html
                    self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: キャッシュHTML使用 (長さ: {len(html_page)})")
                else:
                    # ⭐HTTP GETリトライロジック（タイムアウト10秒、最大3回）⭐
                    html_page = None
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            self.session_manager.ui_bridge.post_log(
                                f"[DEBUG] p={p}: HTTP GET開始 (試行{retry+1}/{max_retries}, timeout=10s, URL={url[:80]})"
                            )
                            html_page = self.session_manager.http_client.get(url, timeout=10).text
                            self.session_manager.ui_bridge.post_log(
                                f"[DEBUG] p={p}: HTTP GET完了 (長さ: {len(html_page)}, 試行{retry+1}回目で成功)"
                            )
                            break  # 成功したらループ終了
                        except (requests.exceptions.Timeout, 
                               requests.exceptions.ConnectTimeout,
                               requests.exceptions.ReadTimeout) as timeout_err:
                            self.session_manager.ui_bridge.post_log(
                                f"[DEBUG] p={p}: HTTP GETタイムアウト (試行{retry+1}/{max_retries}): {timeout_err}"
                            )
                            if retry < max_retries - 1:
                                wait = 2 ** retry  # 指数バックオフ: 1秒、2秒、4秒
                                self.session_manager.ui_bridge.post_log(
                                    f"[DEBUG] p={p}: {wait}秒待機後にリトライします..."
                                )
                                time.sleep(wait)
                            else:
                                # 最終試行でも失敗
                                raise
                        except requests.exceptions.ConnectionError as conn_err:
                            self.session_manager.ui_bridge.post_log(
                                f"[DEBUG] p={p}: HTTP GET接続エラー (試行{retry+1}/{max_retries}): {conn_err}"
                            )
                            if retry < max_retries - 1:
                                wait = 2 ** retry
                                self.session_manager.ui_bridge.post_log(
                                    f"[DEBUG] p={p}: {wait}秒待機後にリトライします..."
                                )
                                time.sleep(wait)
                            else:
                                raise
                    
                    if html_page is None:
                        raise requests.exceptions.RequestException("HTTP GETが{max_retries}回失敗しました")
                
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: 正規表現検索開始")
                thumbs = pattern_thumbs.findall(html_page)
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: 正規表現検索完了 ({len(thumbs)}個発見)")
                
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: URL追加ループ開始")
                for thumb in thumbs:
                    if thumb not in all_image_urls:
                        all_image_urls.append(thumb)
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: URL追加完了 (合計: {len(all_image_urls)}個)")
                
                # ページ間待機
                if p > 0 and p < pages - 1:
                    wait_time = float(self.parent.wait_time.get() or 1)
                    self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: {wait_time}秒待機開始")
                    time.sleep(wait_time)
                    self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: 待機完了")
                    
            except requests.exceptions.RequestException as req_err:
                self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: HTTPエラー発生: {type(req_err).__name__}")
                if isinstance(req_err, (requests.exceptions.ConnectionError, 
                                      requests.exceptions.Timeout, 
                                      requests.exceptions.ConnectTimeout,
                                      requests.exceptions.ReadTimeout)):
                    error_msg = f"ネットワーク接続エラー（回線切断の可能性）: {req_err}"
                    self.session_manager.ui_bridge.post_log(error_msg, "error")
                    raise DownloadErrorException(error_msg)
                else:
                    self.session_manager.ui_bridge.post_log(f"ページ {p+1} HTTPエラー: {req_err}", "warning")
                    continue
            
            self.session_manager.ui_bridge.post_log(f"[DEBUG] p={p}: ループ反復完了")
        
        self.session_manager.ui_bridge.post_log(f"[DEBUG] forループ完全終了、合計{len(all_image_urls)}個のURL収集")
        
        # ⭐Phase1: URL取得完了⭐
        self.session_manager.ui_bridge.post_log(f"[DEBUG] ProgressTracker完了通知開始")
        self.progress_tracker.complete(url_index, status=f"✅ {len(all_image_urls)}個のURL取得完了")
        self.session_manager.ui_bridge.post_log(f"[DEBUG] ProgressTracker完了通知完了")
        
        # 開始ページ調整
        if start_page > 1:
            all_image_urls = all_image_urls[start_page-1:]
            self.session_manager.ui_bridge.post_log(f"開始ページ {start_page} からダウンロード開始")
        
        self.session_manager.ui_bridge.post_log(f"✅ 個別ページのURL取得完了: {len(all_image_urls)}個のURLを取得しました")
        return all_image_urls, total_images, pages
    
    def _apply_download_range_filter(self, all_image_urls: list, options: Dict[str, Any], 
                                     gallery_url: str) -> tuple:
        """ダウンロード範囲フィルターを適用（⭐Phase3: 範囲ロジック分離⭐）
        
        Args:
            all_image_urls: 全画像ページURL
            options: ダウンロードオプション
            gallery_url: ギャラリーURL
            
        Returns:
            tuple: (filtered_urls, download_range_info)
        """
        if not options or not options.get('download_range_enabled', False):
            return all_image_urls, None
        
        # 範囲モード確認
        range_mode = options.get('download_range_mode', "全てのURL")
        current_url_index = self.state_manager.get_current_url_index()
        
        # 適用条件チェック
        should_apply = (range_mode != "1行目のURLのみ") or (current_url_index == 0)
        
        if not should_apply:
            return all_image_urls, None
        
        # 範囲値取得
        start_range_str = self._get_download_range_value(options.get('download_range_start', '0'))
        end_range_str = self._get_download_range_value(options.get('download_range_end', ''))
        
        start_range = int(start_range_str) if start_range_str and start_range_str.strip() else 0
        end_range = int(end_range_str) if end_range_str and end_range_str.strip() else None
        
        if start_range == 0 and end_range is None:
            return all_image_urls, None
        
        original_count = len(all_image_urls)
        
        # 範囲バリデーション
        if start_range > original_count:
            self.session_manager.ui_bridge.post_log(
                f"[WARNING] ダウンロード範囲開始({start_range})がギャラリー全体のページ数({original_count})を超えています。", "warning"
            )
            self.session_manager.ui_bridge.post_log(
                "[INFO] ダウンロード範囲が無効なため、このギャラリーのダウンロードを中断します。", "info"
            )
            return [], None
        
        if end_range is not None:
            if end_range >= original_count:
                self.session_manager.ui_bridge.post_log(
                    f"[WARNING] ダウンロード範囲終点({end_range})がギャラリー全体のページ数({original_count})を超えています。最後のページ({original_count-1})までに調整します。", 
                    "warning"
                )
                end_range = original_count - 1
            
            if end_range < start_range:
                self.session_manager.ui_bridge.post_log(
                    f"[WARNING] ダウンロード範囲終点({end_range})が開始点({start_range})より小さいです。開始点から最後までに調整します。", 
                    "warning"
                )
                end_range = None
        
        # 範囲適用
        filtered_urls = all_image_urls[start_range:end_range+1] if end_range is not None else all_image_urls[start_range:]
        
        if len(filtered_urls) == 0:
            return [], None
        
        # 範囲情報作成
        download_range_info = {
            'enabled': True,
            'start': start_range,
            'end': end_range,
            'relative_total': len(filtered_urls),
            'absolute_total': original_count
        }
        
        return filtered_urls, download_range_info
    
    def _get_gallery_pages(self, gallery_url: str, options: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        ギャラリーページ情報を取得
        
        Args:
            gallery_url: ギャラリーURL
            options: ダウンロードオプション
            
        Returns:
            ギャラリー情報辞書、または取得失敗時None
        """
        
        try:
            import sys
            # [DEBUG] print("!!! _get_gallery_pages() CALLED !!!", flush=True)
            sys.stdout.flush()
            
            # [DEBUG] print(f"!!! post_log呼び出し直前: gallery_url={gallery_url[:50]}...", flush=True)
            self.session_manager.ui_bridge.post_log(f"[DEBUG] _get_gallery_pages開始: {gallery_url}")
            # [DEBUG] print("!!! post_log呼び出し完了", flush=True)
            
            # 1. URL正規化
            # [DEBUG] print("!!! URL正規化開始", flush=True)
            normalized_gallery_url, start_page = self._normalize_gallery_url_with_start_page(gallery_url)
            # [DEBUG] print(f"!!! URL正規化完了: {normalized_gallery_url}", flush=True)
            self.session_manager.ui_bridge.post_log(f"[DEBUG] URL正規化完了: {normalized_gallery_url}, start_page={start_page}")
            
            if normalized_gallery_url is None:
                raise ValueError(f"無効なURL形式: {gallery_url}")
            
            # 2. キャッシュチェック
            cached_info = self._check_gallery_cache(normalized_gallery_url, options)
            if cached_info:
                return cached_info
            
            # 3. HTMLフェッチ
            html = self._fetch_gallery_html(normalized_gallery_url)
            
            # 4. 全画像ページURL抽出
            # [DEBUG] print("!!! 画像URL抽出開始", flush=True)
            all_image_urls, total_images, pages = self._extract_all_image_page_urls(
                html, normalized_gallery_url, start_page
            )
            # [DEBUG] print(f"!!! 画像URL抽出完了: total_images={total_images}, pages={pages}", flush=True)
            
            # 4.5. タイトルとメタデータを抽出
            # [DEBUG] print("!!! BeautifulSoup初期化開始", flush=True)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            # [DEBUG] print("!!! BeautifulSoup初期化完了", flush=True)
            
            # ⭐修正: タイトル取得（<h1 id="gn">優先、空の場合は<title>）⭐
            # [DEBUG] print("!!! タイトル取得開始", flush=True)
            title_elem = soup.find('h1', id='gn')
            gallery_title = title_elem.get_text(strip=True) if title_elem else ""
            
            # ⭐追加: h1が空の場合、titleタグから取得⭐
            if not gallery_title:
                title_elem = soup.find('title')
                gallery_title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # [DEBUG] print(f"!!! タイトル取得完了: title='{gallery_title}'", flush=True)
            
            # ⭐DEBUG: メタデータ抽出前⭐
            # [DEBUG] print("!!! post_log呼び出し直前（メタデータ前）", flush=True)
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _extract_gallery_metadata()呼び出し直前: title='{gallery_title}'",
                "debug"
            )
            # [DEBUG] print("!!! post_log呼び出し完了（メタデータ前）", flush=True)
            
            # メタデータ抽出（後続処理で使用）
            # [DEBUG] print("!!! _extract_gallery_metadata()呼び出し直前", flush=True)
            self._extract_gallery_metadata(html, normalized_gallery_url)
            # [DEBUG] print("!!! _extract_gallery_metadata()呼び出し完了", flush=True)
            
            # ⭐DEBUG: メタデータ抽出後⭐
            # [DEBUG] print("!!! post_log呼び出し直前（メタデータ後）", flush=True)
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _extract_gallery_metadata()完了",
                "debug"
            )
            # [DEBUG] print("!!! post_log呼び出し完了（メタデータ後）", flush=True)
            
            # 5. ダウンロード範囲フィルター適用
            # [DEBUG] print("!!! ダウンロード範囲フィルター開始", flush=True)
            filtered_urls, download_range_info = self._apply_download_range_filter(
                all_image_urls, options, gallery_url
            )
            # [DEBUG] print(f"!!! ダウンロード範囲フィルター完了: filtered_urls={len(filtered_urls)}", flush=True)
            
            # 6. 結果を構築
            result = {
                'total_pages': len(filtered_urls),
                'image_page_urls': filtered_urls,
                'start_page': start_page,
                'original_total': total_images,
                'original_total_images': total_images,
                'original_total_pages': pages,
                'title': gallery_title,  # タイトルを追加
                'gid': getattr(self, 'gid', ''),
                'token': getattr(self, 'token', ''),
                'download_range_info': download_range_info
            }
            
            # 7. キャッシュに保存
            self.cached_gallery_info[normalized_gallery_url] = result
            # [DEBUG] print(f"!!! キャッシュ保存完了: title='{gallery_title}'", flush=True)
            
            # ⭐post_log削除（デッドロック原因の可能性）⭐
            
            # [DEBUG] print("!!! return直前", flush=True)
            return result
            
        except DownloadErrorException:
            raise
        except Exception as e:
            error_msg = f"ギャラリーページ取得エラー: {e}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            raise DownloadErrorException(error_msg)

    def _extract_gallery_metadata(self, html: str, gallery_url: Optional[str] = None) -> None:
        """
        ギャラリーページからメタデータを抽出
        
        Args:
            html: ギャラリーページのHTML
            gallery_url: ギャラリーURL（オプション）
        """
        try:
            # ⭐DEBUG: メソッド開始⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _extract_gallery_metadata() START",
                "debug"
            )
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # ⭐DEBUG: BeautifulSoup初期化完了⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] BeautifulSoup parsing完了",
                "debug"
            )
            
            # ギャラリーIDとトークンを抽出（URLから優先）
            if gallery_url:
                # URLから直接抽出（例: https://e-hentai.org/g/3033168/575ac7b4eb/）
                url_gid_match = re.search(r'/g/(\d+)/', gallery_url)
                if url_gid_match:
                    self.gid = url_gid_match.group(1)
                
                url_token_match = re.search(r'/g/\d+/([a-f0-9]+)', gallery_url)
                if url_token_match:
                    self.token = url_token_match.group(1)
            
            # ⭐DEBUG: gid/token抽出完了⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] gid={getattr(self, 'gid', 'None')}, token={getattr(self, 'token', 'None')[:10] if hasattr(self, 'token') else 'None'}...",
                "debug"
            )
            
            # HTMLからも抽出を試みる（フォールバック）
            if not hasattr(self, 'gid') or not self.gid:
                gid_match = re.search(r'gid=(\d+)', html)
                if gid_match:
                    self.gid = gid_match.group(1)
            
            if not hasattr(self, 'token') or not self.token:
                token_match = re.search(r'token=([a-f0-9]+)', html)
                if token_match:
                    self.token = token_match.group(1)
            
            # アップローダーを抽出（改善版）
            # 方法1: gdn divから抽出
            gdn_div = soup.find('div', id='gdn')
            if gdn_div:
                uploader_link = gdn_div.find('a')
                if uploader_link:
                    self.uploader = uploader_link.get_text(strip=True)
            
            # 方法2: フォールバック - td要素から抽出
            if not hasattr(self, 'uploader') or not self.uploader:
                uploader_elem = soup.find('td', string='Uploader:')
                if uploader_elem and uploader_elem.find_next_sibling('td'):
                    self.uploader = uploader_elem.find_next_sibling('td').get_text(strip=True)
            
            # 投稿日を抽出
            posted_elem = soup.find('td', string='Posted:')
            if posted_elem and posted_elem.find_next_sibling('td'):
                self.date = posted_elem.find_next_sibling('td').get_text(strip=True)
            
            # 評価を抽出
            rating_elem = soup.find('td', string='Rating:')
            if rating_elem and rating_elem.find_next_sibling('td'):
                self.rating = rating_elem.find_next_sibling('td').get_text(strip=True)
            
            # ⭐DEBUG: 基本情報抽出完了⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] 基本情報抽出完了 (uploader, date, rating)",
                "debug"
            )
            
            # ⭐追加: カテゴリを抽出（gdc divから）⭐
            # <div id="gdc"><div class="cs ct7" onclick="document.location='https://e-hentai.org/cosplay'">Cosplay</div></div>
            # <div id="gdc"><div class="cs ct9" onclick="document.location='https://e-hentai.org/non-h'">Non-H</div></div>
            self.category = ""
            gdc_div = soup.find('div', id='gdc')
            if gdc_div:
                # 方法1: class="cs ct*"のdivを検索
                category_div = gdc_div.find('div', class_=re.compile(r'cs\s+ct'))
                if category_div:
                    self.category = category_div.get_text(strip=True)
                else:
                    # 方法2: onclick属性から抽出
                    category_link = gdc_div.find('div', onclick=re.compile(r'cosplay|doujinshi|manga|artist.*cg|game.*cg|western|non.*h|non-h|image.*set|asian.*porn|misc', re.I))
                    if category_link:
                        self.category = category_link.get_text(strip=True)
            
            # フォールバック: 正規表現で抽出（より柔軟なパターン）
            if not self.category:
                # パターン1: <div class="cs ct*" ...>Category</div>
                category_match = re.search(r'<div\s+class="cs\s+ct[^"]*"[^>]*>([^<]+)</div>', html, re.IGNORECASE)
                if category_match:
                    self.category = category_match.group(1).strip()
                else:
                    # パターン2: onclick属性からURLを抽出してカテゴリ名を推測
                    onclick_match = re.search(r'onclick="document\.location=\'https://e-hentai\.org/([^\']+)\'">([^<]+)</div>', html, re.IGNORECASE)
                    if onclick_match:
                        self.category = onclick_match.group(2).strip()
            
            # ⭐DEBUG: カテゴリ抽出完了⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] カテゴリ抽出完了: category='{getattr(self, 'category', 'None')}'",
                "debug"
            )
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"メタデータ抽出エラー: {e}", "error")

    
    def _normalize_gallery_url_with_start_page(self, url: str) -> tuple:
        """
        URLを正規化し、開始ページを判定
        
        Args:
            url: 入力URL
            
        Returns:
            (normalized_url, start_page)のタプル
        """
        url = url.strip()
        start_page = 1
        
        # 個別画像ページの判定
        image_page_match = re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', url)
        if image_page_match:
            domain, token, gid, page_num = image_page_match.groups()
            start_page = int(page_num)
            
            # 個別画像ページから正しいギャラリーURLを取得
            try:
                # 個別画像ページからギャラリーURLを取得中
                response = self.session_manager.http_client.get(url, timeout=30)
                response.raise_for_status()
                html = response.text
                
                # BeautifulSoupでHTMLを解析
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # <div class="sb"><a href="..."></a></div>からギャラリーURLを取得
                sb_div = soup.find('div', class_='sb')
                # sb_div found
                if sb_div:
                    sb_link = sb_div.find('a', href=True)
                    # sb_link found
                    if sb_link:
                        gallery_url = sb_link['href']
                        # gallery_url from sb
                        if not gallery_url.startswith('http'):
                            gallery_url = f"https://{domain}.org{gallery_url}"
                        self.session_manager.ui_bridge.post_log(f"個別画像ページ検出: ページ{start_page}から開始")
                        # 正規化結果（sb要素から取得）
                        return gallery_url, start_page
                else:
                    # sb要素が見つからない場合、HTMLの一部をログに出力
                    # sb要素が見つかりません
                    pass
                
                # フォールバック: 正規表現でギャラリーリンクを探す
                gallery_patterns = [
                    re.compile(r'href="([^"]*g/\d+/[a-f0-9]+/?)"'),  # 通常のギャラリーリンク
                    re.compile(r'href="([^"]*g/\d+/[^"]*)"'),        # フォールバック
                ]
                
                gallery_url = None
                for pattern in gallery_patterns:
                    gallery_links = pattern.findall(html)
                    if gallery_links:
                        # 最初のギャラリーリンクを使用
                        gallery_url = gallery_links[0]
                        if not gallery_url.startswith('http'):
                            gallery_url = f"https://{domain}.org{gallery_url}"
                        break
                
                if gallery_url:
                    self.session_manager.ui_bridge.post_log(f"個別画像ページ検出: ページ{start_page}から開始")
                    # 正規化結果（正規表現から取得）
                    return gallery_url, start_page
                else:
                    # 最終フォールバック: 元の方法を使用
                    gallery_url = f"https://{domain}.org/g/{gid}/{token}/"
                    self.session_manager.ui_bridge.post_log(f"個別画像ページ検出（最終フォールバック）: ページ{start_page}から開始")
                    # 正規化結果
                    return gallery_url, start_page
                    
            except Exception as e:
                # 個別画像ページからのギャラリーURL取得エラー
                # フォールバック: 元の方法を使用
                gallery_url = f"https://{domain}.org/g/{gid}/{token}/"
                self.session_manager.ui_bridge.post_log(f"個別画像ページ検出（エラーフォールバック）: ページ{start_page}から開始")
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 正規化結果: {gallery_url}")
                return gallery_url, start_page
        
        # ギャラリーページの判定（?p=パラメータ付き）
        gallery_with_page_match = re.match(r'https?://(e-hentai|exhentai)\.org/g/(\d+)/([a-f0-9]+)/\?p=(\d+)', url)
        if gallery_with_page_match:
            domain, gid, token, page_param = gallery_with_page_match.groups()
            start_page = int(page_param) + 1  # ?p=0は2ページ目
            gallery_url = f"https://{domain}.org/g/{gid}/{token}/"
            self.session_manager.ui_bridge.post_log(f"ギャラリーページ検出: ページ{start_page}から開始")
            self.session_manager.ui_bridge.post_log(f"[DEBUG] 正規化結果: {gallery_url}")
            return gallery_url, start_page
        
        # 通常のギャラリーURL
        gallery_match = re.match(r'https?://(e-hentai|exhentai)\.org/g/(\d+)/([a-f0-9]+)', url)
        if gallery_match:
            domain, gid, token = gallery_match.groups()
            gallery_url = f"https://{domain}.org/g/{gid}/{token}/"
            self.session_manager.ui_bridge.post_log(f"[DEBUG] 通常ギャラリーURL検出: {gallery_url}")
            return gallery_url, start_page
        
        # 無効なURL
        self.session_manager.ui_bridge.post_log(f"[DEBUG] 無効なURL形式: {url}")
        return None, 1


    def _get_image_info_from_page(self, image_page_url: str) -> Optional[Dict[str, Any]]:
        """
        画像ページから実際の画像URLと情報を取得
        
        Args:
            image_page_url: 画像ページのURL
            
        Returns:
            画像情報辞書（image_url, original_filenameなど）、または取得失敗時None
        """
        # ⭐DEBUG: メソッド開始⭐
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] _get_image_info_from_page()開始: URL={image_page_url[:80] if image_page_url else 'None'}",
            "debug"
        )
        try:
            # 画像情報取得
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _fetch_image_info_with_auto_resume()呼び出し直前",
                "debug"
            )
            response = self._fetch_image_info_with_auto_resume(image_page_url)
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _fetch_image_info_with_auto_resume()完了: response={response is not None}",
                "debug"
            )
            if not response:
                # ⭐修正: enhanced_error_handlerに任せるため例外を投げる⭐
                error_msg = f"画像情報の取得に失敗しました: {image_page_url}"
                self.session_manager.ui_bridge.post_log(error_msg, "error")
                raise DownloadErrorException(error_msg)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 画像URLを取得
            img_tag = soup.find('img', {'id': 'img'})
            if not img_tag or 'src' not in img_tag.attrs:
                error_msg = f"画像タグが見つかりません: {image_page_url}"
                raise DownloadErrorException(error_msg)
            
            image_url = img_tag['src']
            original_filename = os.path.basename(image_url).split('?')[0]
            
            return {
                'image_url': image_url,
                'original_filename': original_filename,
                'page_url': image_page_url
            }
            
        except DownloadErrorException:
            # DownloadErrorExceptionはそのまま再投げ
            raise
        except Exception as e:
            # ⭐修正: enhanced_error_handlerに任せるため例外を投げる⭐
            error_msg = f"画像情報取得エラー ({image_page_url}): {e}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            raise DownloadErrorException(error_msg)

    def _fetch_image_info_with_auto_resume(self, url: str) -> Optional[Dict[str, Any]]:
        """
        画像情報取得（エラーハンドリングはenhanced_error_handlerに委譲）
        
        Args:
            url: 画像ページURL
            
        Returns:
            画像情報辞書またはNone
        """
        # ⭐DEBUG: メソッド開始⭐
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] _fetch_image_info_with_auto_resume()開始: URL={url[:80] if url else 'None'}",
            "debug"
        )
        try:
            # 通常の画像情報取得
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] http_client.get()呼び出し直前",
                "debug"
            )
            response = self.session_manager.http_client.get(url, timeout=30)
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] http_client.get()完了: status={response.status_code if response else 'None'}",
                "debug"
            )
            response.raise_for_status()
            
            return response
            
        except requests.exceptions.RequestException as e:
            # ⭐修正: エラーが発生したら例外を投げてenhanced_error_handlerに任せる⭐
            error_msg = f"画像情報取得エラー: {e}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            raise DownloadErrorException(error_msg)
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"画像情報取得処理エラー: {e}", "error")
            return None

    def _get_page_with_selenium(self, url: str) -> Optional[str]:
        """
        Seleniumを使用してページのHTMLを取得
        
        Args:
            url: ページURL
            
        Returns:
            HTML文字列またはNone
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            self.session_manager.ui_bridge.post_log("Seleniumを使用してページを取得中...")
            
            # Chromeオプション設定
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # ドライバ初期化
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                driver.get(url)
                # ページ読み込み待機（最大30秒）
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # HTMLを取得
                html = driver.page_source
                
                if html:
                    self.session_manager.ui_bridge.post_log("Seleniumページ取得成功")
                    return html
                else:
                    self.session_manager.ui_bridge.post_log("Seleniumページ取得失敗: HTMLが空です", "error")
                    return None
            finally:
                driver.quit()
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"Seleniumページ取得エラー: {e}", "error")
            return None
    
    def _fetch_image_info_with_selenium(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Seleniumを使用した画像情報取得
        
        Args:
            url: 画像ページURL
            
        Returns:
            画像情報辞書またはNone
        """
        """Seleniumを使用した画像情報取得"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            
            self.session_manager.ui_bridge.post_log("Seleniumを使用して画像情報を取得中...")
            
            # Chromeオプション設定
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # ドライバ初期化
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                driver.get(url)
                time.sleep(3)  # ページ読み込み待機
                
                # 画像要素を取得
                img_element = driver.find_element(By.ID, "img")
                image_url = img_element.get_attribute('src')
                
                if image_url:
                    self.session_manager.ui_bridge.post_log("Selenium画像情報取得成功")
                    
                    # requests.Responseオブジェクトを模擬
                    class MockResponse:
                        def __init__(self, image_url):
                            self.content = f'<img id="img" src="{image_url}">'.encode('utf-8')
                            self.status_code = 200
                    
                    return MockResponse(image_url)
                else:
                    self.session_manager.ui_bridge.post_log("Selenium画像情報取得失敗: 画像URLが見つかりません", "error")
                    return None
                    
            finally:
                driver.quit()
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"Selenium画像情報取得エラー: {e}", "error")
            return None

    def _determine_image_filename(self, gallery_info: Dict[str, Any], page_num: int, 
                                  image_info: Dict[str, Any], 
                                  absolute_page: Optional[int] = None) -> str:
        """
        画像ファイル名を決定
        
        Args:
            gallery_info: ギャラリー情報
            page_num: 相対ページ番号
            image_info: 画像情報
            absolute_page: 絶対ページ番号（オプション、ダウンロード範囲が有効な場合）
            
        Returns:
            ファイル名文字列
        """
        save_name_mode = self.parent.save_name.get()
        
        # ⭐追加: 絶対ページ番号を取得（指定されていない場合は計算）⭐
        if absolute_page is None:
            absolute_page = self._get_absolute_page_number(page_num)
        
        # 1ページ目の特別命名をチェック
        if page_num == 1 and self.parent.first_page_naming_enabled.get():
            template = self.parent.first_page_naming_format.get()
            if template == "title":
                # "title"の場合は実際のタイトルを使用
                # ⭐GalleryInfo: 辞書またはGalleryInfoオブジェクトを処理⭐
                if isinstance(gallery_info, dict):
                    base_name = gallery_info.get('title', 'Unknown')
                elif hasattr(gallery_info, 'title'):
                    base_name = gallery_info.title
                else:
                    base_name = 'Unknown'
            else:
                base_name = template
        else:
            # 通常の命名規則
            if save_name_mode == "Original":
                base_name = image_info['original_filename']
            elif save_name_mode == "simple_number":
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = f"{page_num - 1}{ext}"  # 0から開始
            elif save_name_mode == "padded_number":
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = f"{page_num - 1:03d}{ext}"  # 000から開始
            elif save_name_mode == "custom_name":
                template = self.parent.custom_name.get()
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = self._format_filename_template(
                    template, gallery_info, page_num, 
                    image_info['original_filename'], ext,
                    absolute_page=absolute_page  # ⭐追加: 絶対ページ番号を渡す⭐
                ) + ext
            else:
                base_name = image_info['original_filename']
        
        # ファイル名を安全にする
        safe_filename = re.sub(r'[\\/:*?"<>|]', '_', base_name)
        return safe_filename
    
    def _get_absolute_page_number(self, relative_page: int) -> int:
        """
        相対ページ番号から絶対ページ番号を取得
        
        Args:
            relative_page: 相対ページ番号
            
        Returns:
            int: 絶対ページ番号（ダウンロード範囲が無効な場合は相対ページ番号と同じ）
        """
        try:
            # ダウンロード範囲情報を取得
            download_range_info = getattr(self, 'current_download_range_info', None)
            if download_range_info and download_range_info.get('enabled'):
                range_start = download_range_info.get('start', 1)
                # 絶対ページ番号 = 範囲開始 + 相対ページ番号 - 1
                absolute_page = range_start + relative_page - 1
                return absolute_page
            else:
                # ダウンロード範囲が無効な場合は、相対ページ番号と同じ
                return relative_page
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"絶対ページ番号取得エラー: {e}", "error")
            return relative_page

    def _handle_duplicate_file(self, file_path: str, page_num: int) -> str:
        """
        同名ファイルの処理
        
        Args:
            file_path: ファイルパス
            page_num: ページ番号
            
        Returns:
            処理後のファイルパス
        """
        if not os.path.exists(file_path):
            return file_path
        
        mode = self.parent.duplicate_file_mode.get()
        # ⭐ファイル処理ログを明確に⭐
        mode_text = {
            "skip": "スキップ",
            "overwrite": "上書き",
            "rename": "連番付与"
        }.get(mode, mode)
        self.session_manager.ui_bridge.post_log(f"同名ファイル処理モード: {mode_text}")
        
        if mode == "skip":
            self.session_manager.ui_bridge.post_log(f"ページ {page_num}: 同名ファイルが存在するためスキップします: {os.path.basename(file_path)}")
            return None
        elif mode == "overwrite":
            # 圧縮時は元ファイルを削除して圧縮ファイルを作成
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.session_manager.ui_bridge.post_log(f"ページ {page_num}: 同名ファイルを上書き: {os.path.basename(file_path)}")
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(f"ページ {page_num}: ファイル削除エラー: {e}", "warning")
            return file_path
        else:  # rename
            base, ext = os.path.splitext(file_path)
            counter = 1
            new_path = file_path
            
            while os.path.exists(new_path):
                new_path = f"{base}({counter}){ext}"
                counter += 1
            
            self.session_manager.ui_bridge.post_log(f"ページ {page_num}: ファイル名を変更します: {os.path.basename(file_path)} → {os.path.basename(new_path)}")
            return new_path

    def _download_single_image(self, image_url: str, file_path: str, page_num: int) -> bool:
        """
        単一画像のダウンロード（urllib3の自動リトライを活用）
        
        Args:
            image_url: 画像URL
            file_path: 保存先パス
            page_num: ページ番号
            
        Returns:
            成功時True
        """
        try:
            # HTTP自動リトライに任せる（デフォルトで3回リトライ）
            # タイムアウト設定を取得
            connection_timeout = 10
            read_timeout = 30
            # ⭐修正: タイムアウト設定はデフォルト値を使用（将来的に設定から読み取る）⭐
            
            response = self.session_manager.http_client.get(
                image_url,
                timeout=(connection_timeout, read_timeout)  # 接続タイムアウト, 読み取りタイムアウト
            )
            
            if not self.state_manager.is_download_running():  # 中断チェック
                raise requests.exceptions.RequestException("ダウンロードが中断されました")
                
            response.raise_for_status()
            
            # 成功時の処理
            image_data = response.content
            
            # 標準の保存処理を使用
            result = self._save_image_data(image_data, file_path, "Original", image_url)
            if result is True:  # スキップされた場合
                # スキップ時はログを出力しない（情報量を減らす）
                pass
            elif result:  # 保存パスが返された場合
                # 保存完了時はログを出力しない（情報量を減らす）
                pass
                
                # ⭐追加: エラー復旧成功のログをレジュームポイントでの処理成功時に表示⭐
                # エラーが発生していた場合（エラーレジュームから復帰した場合）のみ表示
                if self.state_manager.download_state.error_occurred:
                    self.session_manager.ui_bridge.post_log(f"════════════════════════════════════════", "info")
                    self.session_manager.ui_bridge.post_log(f"✅ エラー復旧成功: レジュームポイントでの処理が成功しました", "info")
                    self.session_manager.ui_bridge.post_log(f"════════════════════════════════════════", "info")
                # エラーフラグをリセット
                self.state_manager.download_state.error_occurred = False
                
                # ページ完了時のSelenium無効化処理
                self._deactivate_selenium_if_needed(page_completed=True)
                
            return result
            
        except requests.exceptions.RequestException as e:
            # HTTP自動リトライが全て失敗した場合
            self.session_manager.ui_bridge.post_log(f"HTTP自動リトライが全て失敗: {e}", "error")
            
            # リトライ試行フラグを設定（次回成功時にメッセージ表示用）
            self._urllib3_retry_attempted = True
            
            # 「自動再開を待つ」オプションをチェック
            if (hasattr(self.parent, 'wait_for_auto_recovery') and 
                self.parent.wait_for_auto_recovery.get()):
                
                # レジュームオプションを実行
                resume_result = self._handle_urllib3_retry_failure(image_url, e)
                if resume_result == "continue":
                    # 同じ画像を再試行
                    return self._download_single_image(image_url, file_path, page_num)
                else:
                    # スキップまたはエラー
                    from config.settings import DownloadErrorException
                    raise DownloadErrorException(f"ページ {page_num}: 画像のダウンロードに失敗しました。") from e
            else:
                # オプションがOFFの場合、即座にエラー
                from config.settings import DownloadErrorException
                raise DownloadErrorException(f"ページ {page_num}: 画像のダウンロードに失敗しました。") from e
                
        except Exception as e:
            # その他の予期しないエラー
            from config.settings import DownloadErrorException
            raise DownloadErrorException(f"ページ {page_num}: 予期しないエラーが発生しました。") from e

    def _handle_urllib3_retry_failure(self, url, error):
        """HTTP自動リトライ失敗時の処理"""
        try:
            # エラー分類
            error_type = self._classify_error(error)
            
            if error_type == "ssl":
                # SSLエラーの場合
                if (hasattr(self.parent, 'lower_security_level') and 
                    self.parent.lower_security_level.get()):
                    self.session_manager.ui_bridge.post_log("SSLエラー - セキュリティレベルを下げてリトライ", "info")
                    return self._retry_with_lower_security(url, error)
                elif (hasattr(self.parent, 'skip_certificate_verify') and 
                      self.parent.skip_certificate_verify.get()):
                    self.session_manager.ui_bridge.post_log("SSLエラー - 証明書検証をスキップしてリトライ", "info")
                    return self._retry_without_cert_verify(url, error)
                else:
                    return "skip_image"
                    
            elif error_type == "connection":
                # 接続エラーの場合
                return self._retry_with_selenium(url, error)
                
            else:
                # その他のエラー
                return self._execute_resume_option(url, error)
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"urllib3リトライ失敗処理エラー: {e}", "error")
            return "skip_image"

    def _find_main_image_url(self, soup: Any) -> Optional[str]:
        """
        メイン画像URLを検索
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            画像URLまたはNone
        """
        try:
            # 画像要素を検索（優先順位順）
            
            # 1. id="img"の画像を探す
            img_elem = soup.find('img', {'id': 'img'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 2. class="main_image"の画像を探す
            img_elem = soup.find('img', {'class': 'main_image'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 3. id="image"の画像を探す
            img_elem = soup.find('img', {'id': 'image'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 4. 画像を含むdivを探す
            div_elem = soup.find('div', {'id': 'i3'})
            if div_elem:
                img_elem = div_elem.find('img')
                if img_elem and img_elem.get('src'):
                    return img_elem['src']
            
            # 5. すべての画像から適切なものを探す
            img_elems = soup.find_all('img')
            for img in img_elems:
                src = img.get('src', '')
                if any(domain in src.lower() for domain in ['ehgt.org', 'exhentai.org', 'e-hentai.org']):
                    if any(ext in src.lower() for ext in ['.jpg', '.png', '.gif', '.jpeg', '.webp']):
                        return src
            
            # 6. nl要素内の画像を探す
            nl_elem = soup.find('a', {'id': 'loadfail'})
            if nl_elem and nl_elem.get('href'):
                return nl_elem['href']
            
            self.session_manager.ui_bridge.post_log("画像URLが見つかりませんでした", "warning")
            return None
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"画像URL検索エラー: {e}", "error")
            return None
    
    def get_save_path(
        self,
        save_folder: str,
        page: int,
        image_url: str,
        save_name_option: str,
        custom_name_format: str,
        manga_title: str,
        artist: str,
        parody: str,
        character: str,
        group: str,
        save_format_option: str,
        absolute_page: Optional[int] = None
    ) -> str:
        """
        保存パス決定（１ページ目命名修正版）
        
        Args:
            save_folder: 保存先フォルダ
            page: ページ番号
            image_url: 画像URL
            save_name_option: ファイル名オプション
            custom_name_format: カスタム名フォーマット
            manga_title: マンガタイトル
            artist: 作者
            parody: 作品
            character: キャラクター
            group: グループ
            save_format_option: 保存形式
            absolute_page: 絶対ページ番号（オプション、ダウンロード範囲が有効な場合）
            
        Returns:
            保存パス
        """
        try:
            # ⭐追加: 絶対ページ番号を取得（指定されていない場合は計算）⭐
            if absolute_page is None:
                absolute_page = self._get_absolute_page_number(page)
            
            # 拡張子決定
            if save_format_option == "Original":
                ext = os.path.splitext(image_url)[1] or ".jpg"
            else:
                ext = f".{save_format_option.lower()}"
            
            # １ページ目の特別命名処理
            if page == 1 and hasattr(self.parent, 'first_page_naming_enabled') and self.parent.first_page_naming_enabled.get():
                first_page_format = self.parent.first_page_naming_format.get().strip()
                
                if first_page_format:
                    # {}で囲まれた部分のみを変数として扱う
                    if '{' in first_page_format and '}' in first_page_format:
                        # テンプレート変数として処理
                        filename = self._format_filename_template(
                            first_page_format,
                            {
                                'title': manga_title,  # <h1>から取得したタイトル
                                'page_title': getattr(self, 'html_title', ''),  # ⭐追加: <title>タグから取得したタイトル⭐
                                'artist': artist,
                                'parody': parody,
                                'character': character,
                                'group': group,
                                'page': page,
                                'gid': getattr(self, 'gid', ''),
                                'token': getattr(self, 'token', ''),
                                'category': getattr(self, 'category', ''),  # ⭐追加: categoryを追加⭐
                                'uploader': getattr(self, 'uploader', ''),  # ⭐追加: uploaderを追加⭐
                                'date': getattr(self, 'date', ''),  # ⭐追加: dateを追加⭐
                                'rating': getattr(self, 'rating', '')  # ⭐追加: ratingを追加⭐
                            },
                            page,
                            os.path.basename(image_url),
                            ext.lstrip('.'),
                            absolute_page=absolute_page  # ⭐追加: 絶対ページ番号を渡す⭐
                        )
                    else:
                        # {}がない場合は文字列をそのまま使用
                        filename = first_page_format
                    
                    # 無効文字のサニタイズ
                    filename = self.sanitize_filename(filename)
                    return os.path.join(save_folder, filename + ext)
            
            # 通常の命名処理
            if save_name_option == "Original":
                filename = os.path.splitext(os.path.basename(image_url))[0]
            elif save_name_option == "simple_number":
                # 1から始まる連番: 1, 2, 3...
                filename = str(page)  # 1ベースのまま使用
            elif save_name_option == "padded_number":
                # 001から始まる連番: 001, 002, 003...
                filename = f"{page:03d}"  # 1ベースのまま使用
            elif save_name_option == "custom_name" and custom_name_format:
                # カスタム命名でも{}の有無をチェック
                if '{' in custom_name_format and '}' in custom_name_format:
                    filename = self._format_filename_template(
                        custom_name_format,
                        {
                            'title': manga_title,  # <h1>から取得したタイトル
                            'page_title': getattr(self, 'html_title', ''),  # ⭐追加: <title>タグから取得したタイトル⭐
                            'artist': artist,
                            'parody': parody,
                            'character': character,
                            'group': group,
                            'page': page,
                            'gid': getattr(self, 'gid', ''),
                            'token': getattr(self, 'token', ''),
                            'category': getattr(self, 'category', ''),  # ⭐追加: categoryを追加⭐
                            'uploader': getattr(self, 'uploader', ''),  # ⭐追加: uploaderを追加⭐
                            'date': getattr(self, 'date', ''),  # ⭐追加: dateを追加⭐
                            'rating': getattr(self, 'rating', '')  # ⭐追加: ratingを追加⭐
                        },
                        page,
                        os.path.basename(image_url),
                        ext.lstrip('.'),
                        absolute_page=absolute_page  # ⭐追加: 絶対ページ番号を渡す⭐
                    )
                else:
                    # {}がない場合は文字列をそのまま使用
                    filename = custom_name_format
            else:
                filename = f"page_{page:03d}"
            
            # サニタイズ
            filename = self.sanitize_filename(filename)
            return os.path.join(save_folder, filename + ext)

        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"保存パス決定エラー: {e}", "error")
            fallback_filename = f"image_{page:03d}{ext}"
            return os.path.join(save_folder, fallback_filename)

    def _format_filename_template(
        self,
        template: str,
        metadata: Dict[str, Any],
        page_num: int = 1,
        original_filename: str = "",
        ext: str = "",
        absolute_page: Optional[int] = None
    ) -> str:
        """
        ファイル名テンプレートをフォーマット
        
        Args:
            template: テンプレート文字列
            metadata: メタデータ辞書
            page_num: 相対ページ番号
            original_filename: 元のファイル名
            ext: 拡張子
            absolute_page: 絶対ページ番号（オプション）
            
        Returns:
            フォーマット済みファイル名
        """
        try:
            # ⭐追加: 絶対ページ番号を取得（指定されていない場合は計算）⭐
            if absolute_page is None:
                absolute_page = self._get_absolute_page_number(page_num)
            
            # DLリスト進行状況を含む変数辞書
            format_dict = {
                'title': str(metadata.get('title', '')),  # <h1>から取得したタイトル
                'page_title': str(metadata.get('page_title', '')),  # ⭐追加: <title>タグから取得したタイトル⭐
                'page': int(page_num),
                'absolute_page': int(absolute_page),  # ⭐追加: 絶対ページ番号⭐
                'artist': str(metadata.get('artist', '')),
                'parody': str(metadata.get('parody', '')),
                'character': str(metadata.get('character', '')),
                'group': str(metadata.get('group', '')),
                'language': str(metadata.get('language', '')),
                'category': str(metadata.get('category', '')),
                'uploader': str(metadata.get('uploader', '')),
                'gid': str(metadata.get('gid', '')),
                'token': str(metadata.get('token', '')),
                'date': str(metadata.get('date', '')),
                'rating': str(metadata.get('rating', '')),
                'pages': str(metadata.get('pages', '')),
                'filesize': str(metadata.get('filesize', '')),
                'tags': str(metadata.get('tags', '')),
                'ext': str(ext),
                'original_filename': str(original_filename),
                'dl_index': int(getattr(self.parent, 'current_url_index', 1)),  # DLリスト進行番号（1ベース）
                'dl_count': int(len(getattr(self.parent, 'url_list', [])) if hasattr(self.parent, 'url_list') else 1)   # DLリスト総数
            }
            
            # ⭐重要: ギャラリーのカテゴリ（Cosplay, Non-Hなど）を先に設定⭐
            # all_extracted_tagsの'category'はタグのカテゴリ（female, maleなど）なので、ギャラリーのカテゴリとは別物
            # ギャラリーのカテゴリはmetadataから取得したものを優先
            gallery_category = metadata.get('category', '')
            if gallery_category:
                format_dict['category'] = gallery_category
            
            # 抽出された全タグを追加（_first記法は削除、_1, _2形式のみサポート）
            if hasattr(self, 'all_extracted_tags') and self.all_extracted_tags:
                for category, tags in self.all_extracted_tags.items():
                    # ⭐修正: 'category'キーはギャラリーのカテゴリとして既に設定されているため、スキップ⭐
                    if category == 'category':
                        # タグのカテゴリは別のキー名を使用（既存の互換性のため）
                        # format_dict['category']はギャラリーのカテゴリ（Cosplay, Non-Hなど）として保持
                        continue
                    # カテゴリ名を変数として追加
                    format_dict[category] = ', '.join([tag['name'] for tag in tags])
                    
                    # 全てのタグ（既存の互換性のため）
                    if tags:
                        format_dict[f"{category}_all"] = ', '.join([tag['name'] for tag in tags])
            
            # タグ変数の高度な処理（インデックス指定、区切り文字、文字数制限対応）
            if hasattr(self, 'all_extracted_tags') and self.all_extracted_tags:
                # タグ区切り文字と最大文字数を取得
                tag_delimiter = getattr(self.parent, 'tag_delimiter', ', ')
                tag_max_length = getattr(self.parent, 'tag_max_length', 0)
                
                for category, tags in self.all_extracted_tags.items():
                    tag_names = [tag['name'] for tag in tags]
                    
                    # 全てのタグ（設定した区切り文字で結合）
                    all_tags_str = tag_delimiter.join(tag_names)
                    if tag_max_length > 0 and len(all_tags_str) > tag_max_length:
                        all_tags_str = all_tags_str[:tag_max_length]
                    format_dict[category] = all_tags_str
                    
                    # インデックス指定（{female_1}, {female_2}など、最大20個まで）
                    # _first記法は削除し、_1, _2形式のみサポート
                    for i in range(1, min(len(tag_names) + 1, 21)):
                        format_dict[f"{category}_{i}"] = tag_names[i-1] if i <= len(tag_names) else ''
                    
                    # 全てのタグ（既存の互換性のため）
                    format_dict[f"{category}_all"] = all_tags_str
                
                # 特定のタグカテゴリを明示的に追加（既存コードとの互換性のため）
                # femaleタグ
                if 'female' in self.all_extracted_tags:
                    female_tags = [tag['name'] for tag in self.all_extracted_tags['female']]
                    female_delimiter = tag_delimiter
                    female_all = female_delimiter.join(female_tags)
                    if tag_max_length > 0 and len(female_all) > tag_max_length:
                        female_all = female_all[:tag_max_length]
                    format_dict['female'] = female_all
                    # _first記法は削除
                    for i in range(1, min(len(female_tags) + 1, 21)):
                        format_dict[f'female_{i}'] = female_tags[i-1] if i <= len(female_tags) else ''
                else:
                    format_dict['female'] = ''
                    for i in range(1, 21):
                        format_dict[f'female_{i}'] = ''
                
                # cosplayerタグ
                if 'cosplayer' in self.all_extracted_tags:
                    cosplayer_tags = [tag['name'] for tag in self.all_extracted_tags['cosplayer']]
                    cosplayer_delimiter = tag_delimiter
                    cosplayer_all = cosplayer_delimiter.join(cosplayer_tags)
                    if tag_max_length > 0 and len(cosplayer_all) > tag_max_length:
                        cosplayer_all = cosplayer_all[:tag_max_length]
                    format_dict['cosplayer'] = cosplayer_all
                    # _first記法は削除
                    for i in range(1, min(len(cosplayer_tags) + 1, 21)):
                        format_dict[f'cosplayer_{i}'] = cosplayer_tags[i-1] if i <= len(cosplayer_tags) else ''
                else:
                    format_dict['cosplayer'] = ''
                    for i in range(1, 21):
                        format_dict[f'cosplayer_{i}'] = ''
                
                # otherタグ
                if 'other' in self.all_extracted_tags:
                    other_tags = [tag['name'] for tag in self.all_extracted_tags['other']]
                    other_delimiter = tag_delimiter
                    other_all = other_delimiter.join(other_tags)
                    if tag_max_length > 0 and len(other_all) > tag_max_length:
                        other_all = other_all[:tag_max_length]
                    format_dict['other'] = other_all
                    # _first記法は削除
                    for i in range(1, min(len(other_tags) + 1, 21)):
                        format_dict[f'other_{i}'] = other_tags[i-1] if i <= len(other_tags) else ''
                else:
                    format_dict['other'] = ''
                    for i in range(1, 21):
                        format_dict[f'other_{i}'] = ''
                
                # その他のタグカテゴリも同様に処理
                for category in ['male', 'artist', 'character', 'parody', 'group', 'language', 'category']:
                    # ⭐修正: 'category'キーはギャラリーのカテゴリとして既に設定されているため、スキップ⭐
                    if category == 'category':
                        # タグのカテゴリは別のキー名を使用（既存の互換性のため）
                        # format_dict['category']はギャラリーのカテゴリ（Cosplay, Non-Hなど）として保持
                        continue
                    if category in self.all_extracted_tags:
                        category_tags = [tag['name'] for tag in self.all_extracted_tags[category]]
                        category_delimiter = tag_delimiter
                        category_all = category_delimiter.join(category_tags)
                        if tag_max_length > 0 and len(category_all) > tag_max_length:
                            category_all = category_all[:tag_max_length]
                        format_dict[category] = category_all
                        # インデックス指定
                        for i in range(1, min(len(category_tags) + 1, 21)):
                            format_dict[f'{category}_{i}'] = category_tags[i-1] if i <= len(category_tags) else ''
                    else:
                        format_dict[category] = ''
                        for i in range(1, 21):
                            format_dict[f'{category}_{i}'] = ''
            
            formatted = template.format(**format_dict)
            
            # ⭐重要: カスタム命名使用時にログ出力⭐
            if template != 'Original':
                self.session_manager.ui_bridge.post_log(f"カスタム命名適用: テンプレート='{template}' → 結果='{formatted}'", "info")
            
            # 無効な文字を置換
            import re
            invalid_chars = r'[\\/:*?"<>|]'
            formatted = re.sub(invalid_chars, '_', formatted)
            
            return formatted
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ファイル名フォーマットエラー: {e}", "error")
            return f"file_{page_num}"
    
    def _format_folder_name(self, template: str, gallery_pages: Dict[str, Any], 
                           page_num: int = 0) -> str:
        """
        フォルダ名をテンプレートからフォーマット
        
        Args:
            template: フォルダ名テンプレート（例: "{artist}_{title}"）
            gallery_pages: ギャラリーページ情報辞書
            page_num: ページ番号（フォルダ名では通常0）
        
        Returns:
            str: フォーマットされたフォルダ名
        """
        try:
            # ギャラリーメタデータを取得
            metadata = {
                'title': gallery_pages.get('title', ''),
                'artist': gallery_pages.get('artist', ''),
                'parody': gallery_pages.get('parody', ''),
                'character': gallery_pages.get('character', ''),
                'group': gallery_pages.get('group', ''),
                'category': gallery_pages.get('category', ''),
                'uploader': gallery_pages.get('uploader', ''),
                'gid': gallery_pages.get('gid', ''),
                'token': gallery_pages.get('token', ''),
                'date': gallery_pages.get('date', ''),
                'rating': gallery_pages.get('rating', ''),
                'pages': gallery_pages.get('pages', ''),
                'filesize': gallery_pages.get('filesize', ''),
            }
            
            # _format_filename_templateを使用してフォルダ名を生成
            folder_name = self._format_filename_template(
                template, metadata, page_num, "", ""
            )
            
            return folder_name
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"フォルダ名フォーマットエラー: {e}", "error")
            # エラー時はタイトルをそのまま返す
            return gallery_pages.get('title', 'gallery')
    
    def sanitize_filename(self, filename: str) -> str:
        """
        ファイル名の無効文字を置換（文字列変換対応）
        
        Args:
            filename: 元のファイル名
            
        Returns:
            サニタイズされたファイル名
        """
        return self.validation_manager.sanitize_filename(filename)

    # ========== 画像ダウンロード・保存メソッド（オリジナルから移植） ==========
    
    def _cleanup_temp_file(self, temp_path: str) -> None:
        """
        一時ファイルの安全な削除
        
        Args:
            temp_path: 一時ファイルパス
        """
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"一時ファイルの削除に失敗: {e}", "error")

    def _check_if_animated(self, image_path: str) -> bool:
        """
        アニメーション画像かチェック
        
        Args:
            image_path: 画像ファイルパス
            
        Returns:
            アニメーションの場合True
        """
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return hasattr(img, 'is_animated') and img.is_animated
        except:
            return False

    def _save_image_data(self, image_data: bytes, save_path: str, 
                        save_format_option: str, original_url: Optional[str] = None) -> bool:
        """
        画像データを保存する共通処理
        
        Args:
            image_data: 画像バイナリデータ
            save_path: 保存パス
            save_format_option: 保存形式オプション
            original_url: 元のURL（オプション）
            
        Returns:
            成功時True
        """
        temp_path = save_path + '.tmp'
        
        try:
            # 保存先フォルダの存在確認と作成
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 既存ファイルチェック
            if os.path.exists(save_path):
                new_path = self._handle_duplicate_file(save_path, 0)
                if not new_path:
                    return True
                save_path = new_path
                temp_path = save_path + '.tmp'
            
            # JPG形式で保存する場合の処理
            if save_format_option == "JPG":
                try:
                    from PIL import Image
                    from io import BytesIO
                    
                    with Image.open(BytesIO(image_data)) as img:
                        # RGBモードに変換
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            bg = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                            img = bg
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        quality = self.parent.jpg_quality.get() if hasattr(self.parent, 'jpg_quality') else 85
                        with open(temp_path, 'wb') as f:
                            img.save(f, 'JPEG', quality=quality)
                        self.session_manager.ui_bridge.post_log(f"JPG形式で保存（品質: {quality}%）: {os.path.basename(save_path)}")
                        
                except Exception as jpg_error:
                    self.session_manager.ui_bridge.post_log(f"JPG変換エラー: {jpg_error}, 通常の方法で保存します。")
                    with open(temp_path, 'wb') as f:
                        f.write(image_data)
            else:
                print(f"[DEBUG] core/downloader.py _save_image_data: open({temp_path}, 'wb')直前")
                self.session_manager.ui_bridge.post_log(f"[DEBUG] core/downloader.py _save_image_data: open({temp_path}, 'wb')直前")
                with open(temp_path, 'wb') as f:
                    f.write(image_data)
                print(f"[DEBUG] core/downloader.py _save_image_data: open({temp_path}, 'wb')直後")
                self.session_manager.ui_bridge.post_log(f"[DEBUG] core/downloader.py _save_image_data: open({temp_path}, 'wb')直後")
            
            # 一時ファイルを本来のファイル名に移動
            if os.path.exists(temp_path):
                if os.path.exists(save_path):
                    os.remove(save_path)
                os.rename(temp_path, save_path)
            else:
                raise DownloadErrorException(f"一時ファイルが見つかりません: {temp_path}")
            
            # アニメーション画像の処理
            if (save_format_option != "Original" and 
                hasattr(self.parent, 'preserve_animation') and 
                self.parent.preserve_animation.get() and
                original_url):
                
                if self._check_if_animated(save_path):
                    original_ext = os.path.splitext(original_url.split('?')[0])[1]
                    if original_ext:
                        base_path = os.path.splitext(save_path)[0]
                        new_save_path = base_path + original_ext
                        if save_path != new_save_path:
                            if os.path.exists(new_save_path):
                                os.remove(new_save_path)
                            os.rename(save_path, new_save_path)
                            self.session_manager.ui_bridge.post_log(f"アニメーション画像の形式を保持: {os.path.basename(new_save_path)}")
                            save_path = new_save_path
            
            return save_path
        except Exception as e:
            print(f"[DEBUG] core/downloader.py _save_image_data: Exception発生: {e}")
            self.session_manager.ui_bridge.post_log(f"[DEBUG] core/downloader.py _save_image_data: Exception発生: {e}")
            self._cleanup_temp_file(temp_path)
            raise DownloadErrorException(f"画像保存エラー: {e}")
        except BaseException as e:
            print(f"[DEBUG] core/downloader.py _save_image_data: BaseException発生: {e}")
            self.session_manager.ui_bridge.post_log(f"[DEBUG] core/downloader.py _save_image_data: BaseException発生: {e}")
            self._cleanup_temp_file(temp_path)
            raise

    def download_and_save_image(
        self,
        image_url: str,
        save_path: str,
        save_format_option: str,
        options: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        画像をダウンロードして保存（高度なオプション対応版）
        
        Args:
            image_url: 画像URL
            save_path: 保存先パス
            save_format_option: 保存形式オプション
            options: ダウンロードオプション
            
        Returns:
            成功時True
        """
        # オプションの取得
        if options is None:
            options = self._get_current_options()
        
        # ⭐修正: 常時Seleniumオプションを独立してチェック（変数名修正）⭐
        always_use_selenium = False
        if hasattr(self.parent, 'selenium_always_enabled') and hasattr(self.parent.selenium_always_enabled, 'get'):
            always_use_selenium = self.parent.selenium_always_enabled.get()
        
        # ⭐修正: httpxオプションを独立してチェック⭐
        httpx_enabled = options.get('httpx_enabled', False)
        
        # ⭐修正: 常時Seleniumまたはhttpxが有効な場合は、advanced_options_enabledに関わらず使用⭐
        if always_use_selenium or httpx_enabled or options.get('advanced_options_enabled', False):
            return self._download_with_advanced_options(image_url, save_path, save_format_option, options)
        else:
            return self._download_standard(image_url, save_path, save_format_option)

    def _download_with_advanced_options(
        self,
        image_url: str,
        save_path: str,
        save_format_option: str,
        options: Dict[str, Any]
    ) -> bool:
        """
        高度なオプション対応のダウンロード方式
        
        Args:
            image_url: 画像URL
            save_path: 保存先パス
            save_format_option: 保存形式オプション
            options: ダウンロードオプション
            
        Returns:
            成功時True
        """
        try:
            # ⭐修正: 常時Seleniumオプションをチェック（変数名修正）⭐
            selenium_enabled = False
            if hasattr(self.parent, 'selenium_always_enabled') and hasattr(self.parent.selenium_always_enabled, 'get'):
                selenium_enabled = self.parent.selenium_always_enabled.get()
            
            # ⭐最新のSelenium状態を取得（リアルタイム反映）⭐
            # 注: selenium_always_enabledは常時Seleniumとして使用されている
            # エラー時のSelenium自動適用は selenium_fallback_enabled で管理
            current_selenium_enabled = selenium_enabled  # 常時Seleniumと同じ
            
            # 常時Seleniumが有効な場合は優先的に使用
            if selenium_enabled or current_selenium_enabled:
                if selenium_enabled:
                    self.session_manager.ui_bridge.post_log("【常時Selenium】常時Seleniumオプションが有効です")
                self.session_manager.ui_bridge.post_log("【Selenium】Seleniumを使用してダウンロード")
                return self._download_with_selenium(image_url, save_path, save_format_option, options)
            
            # httpxが有効な場合
            elif options.get('httpx_enabled', False):
                self.session_manager.ui_bridge.post_log("【httpx】httpxを使用してダウンロード")
                return self._download_with_httpx(image_url, save_path, save_format_option, options)
            
            # User-Agent偽装が有効な場合
            elif options.get('user_agent_spoofing_enabled', False):
                self.session_manager.ui_bridge.post_log("【User-Agent】User-Agent偽装を使用してダウンロード")
                return self._download_with_user_agent_spoofing(image_url, save_path, save_format_option, options)
            
            # デフォルトは標準ダウンロード
            else:
                # self.session_manager.ui_bridge.post_log("【標準】標準ダウンロード方式を使用")
                return self._download_standard(image_url, save_path, save_format_option)
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"高度なオプション対応ダウンロードエラー: {e}", "error")
            # エラー時は標準ダウンロードにフォールバック
            return self._download_standard(image_url, save_path, save_format_option)

    def _download_with_selenium(self, image_url: str, save_path: str, 
                                save_format_option: str, options: Dict[str, Any]) -> bool:
        """
        Seleniumを使用したダウンロード
        
        Args:
            image_url: 画像URL
            save_path: 保存パス
            save_format_option: 保存形式オプション
            options: ダウンロードオプション
            
        Returns:
            成功時True
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            import base64
            
            # Chromeドライバーの設定
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # ドライバーの取得
            driver_path = ChromeDriverManager().install()
            service = Service(driver_path)
            
            # ブラウザの起動
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                # 画像URLにアクセス
                driver.get(image_url)
                
                # 画像のbase64データを取得
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
                    # base64データをデコード
                    image_data = base64.b64decode(image_data_b64)
                    
                    # 保存処理
                    result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                    if result is True:
                        self.session_manager.ui_bridge.post_log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                    elif result:
                        self.session_manager.ui_bridge.post_log(f"Selenium画像保存完了: {os.path.basename(result)}")
                        
                        # ⭐修正: リサイズ処理を実行⭐
                        if hasattr(self, 'image_processor') and result != True:
                            try:
                                self.image_processor.process_image_resize(
                                    result, None, 0, None, self._get_resize_values_safely()
                                )
                            except Exception as resize_error:
                                self.session_manager.ui_bridge.post_log(f"リサイズ処理エラー: {resize_error}", "warning")
                        
                        # ⭐ダウンロード成功時にエラーフラグをリセット⭐
                        # エラーカウントのリセットはenhanced_error_handlerで管理される
                        if hasattr(self, 'error_occurred'):
                            self.error_occurred = False
                    return result
                else:
                    raise Exception("画像データの取得に失敗しました")
                    
            finally:
                driver.quit()
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"Seleniumダウンロードエラー: {e}", "error")
            # ⭐修正: Selenium失敗時の処理はenhanced_error_handlerで管理される⭐
            raise DownloadErrorException(f"Seleniumダウンロードエラー: {e}")

    def _download_with_httpx(self, image_url: str, save_path: str, 
                            save_format_option: str, options: Dict[str, Any]) -> bool:
        """
        httpxを使用したダウンロード
        
        Args:
            image_url: 画像URL
            save_path: 保存パス
            save_format_option: 保存形式オプション
            options: ダウンロードオプション
            
        Returns:
            成功時True
        """
        try:
            import httpx
            
            # httpxクライアントの設定
            client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                http2=True
            )
            
            try:
                # 画像をダウンロード
                response = client.get(image_url)
                response.raise_for_status()
                image_data = response.content
                
                # 保存処理
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:
                    self.session_manager.ui_bridge.post_log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                elif result:
                    # ⭐修正: リサイズ処理を実行⭐
                    if hasattr(self, 'image_processor') and result != True:
                        try:
                            self.image_processor.process_image_resize(
                                result, None, 0, None, self._get_resize_values_safely()
                            )
                        except Exception as resize_error:
                            self.session_manager.ui_bridge.post_log(f"リサイズ処理エラー: {resize_error}", "warning")
                return result
                
            finally:
                client.close()
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"httpxダウンロードエラー: {e}", "error")
            raise DownloadErrorException(f"httpxダウンロードエラー: {e}")

    def _download_with_user_agent_spoofing(self, image_url: str, save_path: str, 
                                           save_format_option: str, options: Dict[str, Any]) -> bool:
        """
        User-Agent偽装を使用したダウンロード
        
        Args:
            image_url: 画像URL
            save_path: 保存パス
            save_format_option: 保存形式オプション
            options: ダウンロードオプション
            
        Returns:
            成功時True
        """
        try:
            # カスタムUser-Agentを設定
            custom_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # カスタムセッションでダウンロード
            with self.session_manager.http_client.get(image_url, headers=custom_headers, timeout=30, stream=True) as response:
                response.raise_for_status()
                image_data = response.content
                
                # 保存処理
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:
                    self.session_manager.ui_bridge.post_log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                elif result:
                    self.session_manager.ui_bridge.post_log(f"User-Agent偽装画像保存完了: {os.path.basename(result)}")
                    
                    # ⭐修正: リサイズ処理を実行⭐
                    if hasattr(self, 'image_processor') and result != True:
                        try:
                            self.image_processor.process_image_resize(
                                result, None, 0, None, self._get_resize_values_safely()
                            )
                        except Exception as resize_error:
                            self.session_manager.ui_bridge.post_log(f"リサイズ処理エラー: {resize_error}", "warning")
                    
                    # エラーフラグをリセット
                    if hasattr(self, 'error_occurred'):
                        self.error_occurred = False
                return result
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"User-Agent偽装ダウンロードエラー: {e}", "error")
            raise DownloadErrorException(f"User-Agent偽装ダウンロードエラー: {e}")

    def _download_standard(self, image_url: str, save_path: str, save_format_option: str) -> bool:
        """
        標準ダウンロード方式（既存の実装）
        
        Args:
            image_url: 画像URL
            save_path: 保存パス
            save_format_option: 保存形式オプション
            
        Returns:
            成功時True
        """
        # パス長チェックと修正
        try:
            if os.name == 'nt':  # Windowsの場合
                # 実際のパス長をチェック
                real_length = len(os.path.abspath(save_path))
                MAX_PATH_LENGTH = getattr(self.parent, 'MAX_PATH_LENGTH', 240)
                if real_length > MAX_PATH_LENGTH:
                    base, ext = os.path.splitext(save_path)
                    max_base_length = MAX_PATH_LENGTH - len(ext) - 1
                    save_path = base[:max_base_length] + ext
                    self.session_manager.ui_bridge.post_log(f"警告: パス名が長すぎるため短縮されました: {os.path.basename(save_path)}", "warning")
        except:
            pass  # パス処理でエラーが発生した場合は元のパスを使用

        # ディスク容量チェック
        try:
            import psutil
            free_space = psutil.disk_usage(os.path.dirname(save_path)).free / (1024 * 1024)
            DISK_SPACE_WARNING_MB = getattr(self.parent, 'DISK_SPACE_WARNING_MB', 100)
            if free_space < DISK_SPACE_WARNING_MB:
                error_msg = f"ディスク容量が不足しています（必要: {DISK_SPACE_WARNING_MB}MB, 残り: {free_space:.1f}MB）"
                self.session_manager.ui_bridge.post_log(error_msg, "error")
                error = DownloadErrorException(error_msg)
                raise error
        except ImportError:
            pass  # psutilが利用できない場合は容量チェックをスキップ
        except Exception as e:
            if not isinstance(e, DownloadErrorException):
                self.session_manager.ui_bridge.post_log(f"ディスク容量チェック中にエラーが発生: {str(e)}", "warning")

        # メモリ使用量チェック
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            MEMORY_WARNING_THRESHOLD_MB = getattr(self.parent, 'MEMORY_WARNING_THRESHOLD_MB', 500)
            if memory_mb > MEMORY_WARNING_THRESHOLD_MB:
                self.session_manager.ui_bridge.post_log(f"警告: メモリ使用量が高くなっています ({memory_mb:.1f}MB)", "warning")
        except:
            pass  # psutilが利用できない場合は静かに失敗

        temp_path = save_path + '.tmp'
        response = None
        img = None
        
        try:
            # 保存先フォルダの存在確認と作成
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    self.session_manager.ui_bridge.post_log(f"削除された保存先フォルダを再作成: {save_dir}")
                except Exception as folder_error:
                    raise FolderMissingException(
                        f"保存先フォルダの再作成に失敗: {folder_error}", 
                        save_dir, 
                        getattr(self, 'current_gallery_url', '')
                    )

            # 既存ファイルチェック
            if os.path.exists(save_path):
                new_path = self._handle_duplicate_file(save_path, 0)
                if not new_path:
                    self.session_manager.ui_bridge.post_log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                    return True
                save_path = new_path
                temp_path = save_path + '.tmp'

            # 画像ダウンロード - with文でリソース管理
            with self.session_manager.http_client.get(image_url, timeout=30, stream=True) as response:
                response.raise_for_status()
                image_data = response.content
                # 標準の保存処理を使用
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:  # スキップされた場合
                    # スキップ時はログを出力しない（情報量を減らす）
                    pass
                elif result:  # 保存パスが返された場合
                    # ⭐修正: リサイズ処理を実行⭐
                    if hasattr(self, 'image_processor') and result != True:
                        try:
                            self.image_processor.process_image_resize(
                                result, None, 0, None, self._get_resize_values_safely()
                            )
                        except Exception as resize_error:
                            self.session_manager.ui_bridge.post_log(f"リサイズ処理エラー: {resize_error}", "warning")
                    
                    # ⭐ダウンロード成功時にエラーフラグをリセット⭐
                    # エラーカウントのリセットはenhanced_error_handlerで管理される
                    if hasattr(self, 'error_occurred'):
                        self.error_occurred = False
                return result

        except requests.exceptions.RequestException as req_err:
            error_msg = f"画像ダウンロードエラー: {req_err}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            self._cleanup_temp_file(temp_path)
            raise DownloadErrorException(error_msg)

        except Exception as e:
            error_msg = f"画像保存エラー: {e}"
            self.session_manager.ui_bridge.post_log(error_msg, "error")
            self._cleanup_temp_file(temp_path)
            raise DownloadErrorException(error_msg)
    
    def create_save_folder(self, root_folder_path: str, base_foldername: str, 
                          duplicate_mode: str) -> str:
        """
        保存フォルダ作成
        
        Args:
            root_folder_path: ルートフォルダパス
            base_foldername: ベースフォルダ名
            duplicate_mode: 重複モード
            
        Returns:
            作成されたフォルダパス
        """
        try:
            import shutil
            # フォルダ名決定
            folder_path = os.path.join(root_folder_path, base_foldername)
            
            # リスタート時は既存のフォルダを使用
            if getattr(self, '_is_restart', False) and os.path.exists(folder_path):
                self.session_manager.ui_bridge.post_log(f"リスタート: 既存のフォルダを使用します: {base_foldername}")
                return folder_path

            # 復帰ポイントからの再開時も既存フォルダを優先（URLが一致している場合のみ、StateManager経由）
            current_url = self.state_manager.get_current_gallery_url()
            if current_url:
                resume_info = self.state_manager.get_resume_point(current_url)
                if resume_info:
                    resume_folder = resume_info.get('folder', '')
                    if resume_folder and os.path.exists(resume_folder):
                        self.session_manager.ui_bridge.post_log(f"復帰ポイント: 既存のフォルダを使用します: {os.path.basename(resume_folder)}")
                        return resume_folder
            
            # フォルダ作成ロジック
            if os.path.exists(folder_path):
                # 重複時の処理
                if duplicate_mode == "skip":
                    # 既存フォルダは正常系として再利用（レジューム時の誤スキップ防止）
                    self.session_manager.ui_bridge.post_log(f"フォルダが既に存在するため再利用: {base_foldername}")
                    # last_download_folder 更新を呼び出し元で行うため、そのまま返却
                    return folder_path
                elif duplicate_mode == "overwrite":
                    self.session_manager.ui_bridge.post_log(f"既存のフォルダを上書きします: {base_foldername}")
                    try:
                        shutil.rmtree(folder_path)  # フォルダを削除
                        os.makedirs(folder_path)  # フォルダを再作成
                        self.session_manager.ui_bridge.post_log(f"フォルダを上書き作成しました: {base_foldername}")
                    except Exception as e:
                        self.session_manager.ui_bridge.post_log(f"フォルダの上書きに失敗しました: {e}", "error")
                        raise
                else:  # rename
                    counter = 1
                    while os.path.exists(folder_path):
                        new_foldername = f"{base_foldername}({counter})"
                        folder_path = os.path.join(root_folder_path, new_foldername)
                        counter += 1
                    os.makedirs(folder_path)
            else:
                # フォルダが存在しない場合は新規作成
                os.makedirs(folder_path)
                self.session_manager.ui_bridge.post_log(f"📁 フォルダを作成: {base_foldername}")
                
            return folder_path

        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"フォルダ作成エラー: {e}")
            return None
    
    # ========================================
    # ⭐Phase4続き: エラーハンドリングのリファクタリング⭐
    # 214行のメソッドを複数の小メソッドに分割
    # ========================================
    
    def _get_error_retry_info(self, image_page_url: str) -> tuple:
        """エラーリトライ情報を取得
        
        Returns:
            tuple: (retry_count, max_retry_count, can_retry, context_retry_count)
        """
        retry_count = self.get_retry_count(image_page_url) if image_page_url else 0
        if not image_page_url:
            self.session_manager.ui_bridge.post_log("[エラーハンドリング] 画像ページURLが取得できませんでした", "warning")
        
        max_retry_count = 3
        if hasattr(self.parent, 'max_retry_count'):
            try:
                max_retry_count = int(self.parent.max_retry_count.get()) if hasattr(self.parent.max_retry_count, 'get') else int(self.parent.max_retry_count)
            except (ValueError, TypeError):
                max_retry_count = 3
        
        can_retry = retry_count < max_retry_count
        context_retry_count = max_retry_count if not can_retry else retry_count
        
        return retry_count, max_retry_count, can_retry, context_retry_count
    
    def _create_error_context(self, url: str, image_page_url: str, context_retry_count: int) -> Any:
        """エラーコンテキストを作成 (Factory pattern使用)"""
        from core.errors.error_types import DownloadContext, ErrorContextFactory
        
        stage_data = getattr(self, 'stage_data', {})
        image_url_from_stage = stage_data.get('image_url', '')
        if not image_url_from_stage:
            current_image_url = getattr(self, 'current_image_url', '')
            if current_image_url:
                image_url_from_stage = current_image_url
        
        context_url = image_url_from_stage if image_url_from_stage else url
        
        # DTOを使用してコンテキスト情報を構築
        download_ctx = DownloadContext(
            url=context_url,
            page_num=getattr(self, 'current_page', 0),
            total_pages=0,  # 不明な場合は0
            gallery_id=getattr(self, 'current_gallery_id', ''),
            retry_count=context_retry_count,
            consecutive_errors=getattr(self, 'consecutive_errors', 0),
            stage=getattr(self, 'current_stage', 'download'),
            selenium_enabled=getattr(self.parent, 'selenium_enabled', False).get() if hasattr(self.parent, 'selenium_enabled') else False,
            stage_data=stage_data
        )
        
        # Factoryを使用してErrorContextを生成
        context = ErrorContextFactory.create_for_image_download(download_ctx)
        
        # 追加のコンテキスト情報を設定
        context.image_page_url = image_page_url
        
        return context
    
    def _handle_selenium_success(self, context: Any, url: str) -> str:
        """Selenium成功時の処理"""
        self.session_manager.ui_bridge.post_log("🎯 Selenium成功: リトライカウントリセット + 次のページに進みます", "info")
        
        if context.image_page_url and hasattr(self, 'reset_retry_count'):
            self.reset_retry_count(context.image_page_url)
            self.session_manager.ui_bridge.post_log(f"✅ リトライカウントリセット完了: {context.image_page_url}", "info")
        
        normalized_url = self.parent.normalize_url(url) if hasattr(self.parent, 'normalize_url') else url
        if hasattr(self.parent.state_manager, 'clear_resume_point'):
            self.parent.state_manager.clear_resume_point(normalized_url)
            self.session_manager.ui_bridge.post_log("✅ 復帰ポイントクリア完了", "info")
        
        self.state_manager.download_state.error_occurred = False
        self.selenium_success_flag = True
        return "continue"
    
    def _save_error_resume_point(self, url: str, image_page_url: str) -> None:
        """
        エラー時の復帰ポイントを保存
        
        Args:
            url: ギャラリーURL
            image_page_url: 画像ページURL
        """
        if hasattr(self, 'current_save_folder') and self.current_save_folder:
            current_page = getattr(self, 'current_page', 1)
            normalized_url = self.parent.normalize_url(url) if hasattr(self.parent, 'normalize_url') else url
            current_stage = getattr(self, 'current_stage', 'image_download')
            current_sub_stage = getattr(self, 'current_sub_stage', 'before')
            self._save_resume_point(normalized_url, current_page, self.current_save_folder, 
                                   stage=current_stage, sub_stage=current_sub_stage,
                                   reason="error", image_page_url=image_page_url)
    
    def _handle_error_result(self, result: str, url: str, image_page_url: str) -> str:
        """エラー処理結果のハンドリング"""
        if hasattr(result, 'value'):
            result = result.value
        
        if result == "continue":
            self.state_manager.download_state.error_occurred = False
            return "continue"
        elif result == "skip_image":
            self.session_manager.ui_bridge.post_log(f"画像スキップ: {url}", "warning")
            self._save_error_resume_point(url, image_page_url)
            return "skip_image"
        elif result == "skip_url":
            self.session_manager.ui_bridge.post_log(f"URLスキップ: {url}", "warning")
            self._save_error_resume_point(url, image_page_url)
            # ⭐修正: StateManager経由でステータス更新⭐
            normalized_url = self.parent.normalize_url(url)
            self.state_manager.set_url_status(normalized_url, 'skipped')
            return "skip_url"
        elif result == "pause":
            self.session_manager.ui_bridge.post_log(f"一時停止: {url}", "info")
            self.state_manager.download_state.error_occurred = False
            if hasattr(self, '_error_resume_info'):
                self._error_resume_info = {}
            self._save_error_resume_point(url, image_page_url)
            return "pause"
        elif result == "abort":
            self.session_manager.ui_bridge.post_log(f"ダウンロード中止: {url}", "error")
            # ⭐修正: StateManager経由でステータス更新⭐
            normalized_url = self.parent.normalize_url(url)
            self.state_manager.set_url_status(normalized_url, 'error')
            return "abort"
        elif result == "manual":
            self.session_manager.ui_bridge.post_log(f"手動確認が必要（レジュームOFFのため中断）: {url}", "warning")
            return "pause"
        else:
            self.session_manager.ui_bridge.post_log(f"不明なエラー処理結果: {result}", "error")
            return "skip"
    
    def _handle_error_fallback(self, url: str, error: Exception) -> None:
        """フォールバックエラー処理"""
        self.session_manager.ui_bridge.post_log(f"【エラー処理】開始: {url}")
        error_message = str(error)
        self.session_manager.ui_bridge.post_log(f"ダウンロードエラー: {error_message}", "error")
        
        normalized_url = self.parent.normalize_url(url)
        self.state_manager.set_url_status(normalized_url, 'error')
        self.state_manager.set_paused(True)
        
        # GUI更新
        try:
            if hasattr(self.parent, 'progress_panel'):
                current_page = getattr(self, 'current_page', 0)
                current_total = getattr(self, 'current_total', 1)
                download_range_info_for_error = getattr(self, 'current_download_range_info', None)
                error_url_index = None
                if hasattr(self.parent, 'current_url_index'):
                    error_url_index = self.parent.current_url_index
                elif hasattr(self, 'state_manager'):
                    error_url_index = self.state_manager.get_current_url_index()
                self.parent.root.after(0, lambda url=normalized_url, status="状態: エラー", page=current_page, total=current_total, dr_info=download_range_info_for_error, idx=error_url_index: 
                    self.update_current_progress(page, total, status, url, download_range_info=dr_info, url_index=idx))
        except Exception:
            pass
        
        # エラー復帰ポイント保存
        if hasattr(self, 'current_save_folder') and self.current_save_folder:
            current_page = getattr(self, 'current_page', 1)
            current_stage = getattr(self, 'current_stage', 'image_download')
            current_sub_stage = getattr(self, 'current_sub_stage', 'before')
            self._save_resume_point(normalized_url, current_page, self.current_save_folder, 
                                   stage=current_stage, sub_stage=current_sub_stage,
                                   reason="error")
        
        self.parent.root.after(0, self.parent._update_gui_for_error)
    
    def _handle_download_error(self, url: str, error: Exception) -> Optional[str]:
        """
        ダウンロードエラー処理（⭐Phase4: リファクタリング済み⭐）
        
        Args:
            url: エラーが発生したURL
            error: 発生した例外
            
        Returns:
            エラーハンドリング結果（'continue', 'skip', 'pause'など）
        """
        try:
            self.session_manager.ui_bridge.post_log(f"[エラーハンドリング] _handle_download_error開始: url={url}", "info")
            self.state_manager.download_state.error_occurred = True
            
            if hasattr(self.parent, 'enhanced_error_handler'):
                image_page_url = getattr(self, 'current_image_page_url', '') or getattr(self.parent, 'current_image_page_url', '')
                
                # リトライ情報取得
                retry_count, max_retry_count, can_retry, context_retry_count = self._get_error_retry_info(image_page_url)
                # リトライ情報取得
                retry_count, max_retry_count, can_retry, context_retry_count = self._get_error_retry_info(image_page_url)
                
                # エラーコンテキスト作成
                context = self._create_error_context(url, image_page_url, context_retry_count)
                
                # エラーハンドリング実行
                result = self.parent.enhanced_error_handler.handle_error(error, context)
                
                # Selenium成功時の特別処理
                if result == "continue" and hasattr(context, 'is_selenium_success') and context.is_selenium_success:
                    return self._handle_selenium_success(context, url)
                
                # 通常のエラー結果処理
                return self._handle_error_result(result, url, image_page_url)
            else:
                # フォールバック処理
                self._handle_error_fallback(url, error)
        
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"[エラーハンドリング] _handle_download_errorで例外発生: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"[エラーハンドリング] 例外詳細: {traceback.format_exc()}", "error")
            return "abort"
    
    def resume_download(self) -> None:
        """
        ⭐統合版: SessionManager経由でダウンロードを再開⭐
        スレッドを維持したまま、セッション状態をREADYに戻して再開
        """
        try:
            self.session_manager.ui_bridge.post_log("🔄 ダウンロード再開処理を開始", "info")
            
            # 現在のタスクがない場合は作成
            if not self.current_task:
                # エラー情報またはStateManagerから復元
                url = self.error_info.get('url') or self.state_manager.get_current_gallery_url()
                page = self.error_info.get('page', 0)
                
                if not url:
                    self.session_manager.ui_bridge.post_log("再開するURLが見つかりません", "warning")
                    return
                
                self.current_task = DownloadTask()
                self.current_task.url = url
                self.current_task.current_page = page
                self.session_manager.ui_bridge.post_log(f"[DEBUG] タスクを作成: URL={url}, page={page}", "debug")
            
            # SessionManagerを使用して再開
            result = self.session_manager.resume_current_task(self.current_task)
            
            # 結果に応じて処理
            if result == TaskResult.SUCCESS:
                self.session_manager.ui_bridge.post_log("✅ タスクが正常に再開されました", "info")
                self.error_info['has_error'] = False
                self.state_manager.set_paused(False)
                return
            elif result == TaskResult.SKIP:
                self.session_manager.ui_bridge.post_log("⚠️ タスクはスキップされました", "warning")
                self.error_info['has_error'] = False
                self.state_manager.set_paused(False)
                return
            else:  # FATAL
                self.session_manager.ui_bridge.post_log("❌ タスクの再開に失敗しました", "error")
                return
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ダウンロード再開エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"エラー詳細: {traceback.format_exc()}", "error")
    
    def skip_current_url(self) -> None:
        """
        ⭐統合版: SessionManager経由で現在のURLをスキップ⭐
        """
        try:
            self.session_manager.ui_bridge.post_log("⏭️ URL スキップ処理を開始", "info")
            
            # 現在のタスクまたはURLを取得
            url = None
            if self.current_task:
                url = self.current_task.url
            elif hasattr(self, 'current_gallery_url') and self.current_gallery_url:
                url = self.current_gallery_url
            else:
                url = self.state_manager.get_current_gallery_url()
            
            if not url:
                self.session_manager.ui_bridge.post_log("スキップするURLが見つかりません", "warning")
                return
            
            # SessionManagerを使用してスキップ
            result = self.session_manager.skip_current_task(url)
            
            # 結果に応じて処理
            if result == TaskResult.SUCCESS or result == TaskResult.SKIP:
                self.session_manager.ui_bridge.post_log(f"✅ URLがスキップされました: {url}", "info")
                self.error_info['has_error'] = False
                self.state_manager.set_url_status(url, "skipped")
                # 次のURLへ進む
                self._start_next_download()
            else:  # FATAL
                self.session_manager.ui_bridge.post_log(f"❌ URLのスキップに失敗しました: {url}", "error")
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"URLスキップエラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"エラー詳細: {traceback.format_exc()}", "error")
    
    def restart_current_url(self) -> None:
        """
        現在のURLをリスタート
        """
        try:
            # ⭐追加: リスタート時にキャッシュをクリア（最初から再取得）⭐
            if hasattr(self, 'cached_gallery_info'):
                self.cached_gallery_info.clear()
            
            # ⭐修正: リスタート時に正しいURLを取得（優先順位: current_gallery_url > GUI > キャッシュ）⭐
            restart_url = None
            
            # 優先1: current_gallery_urlを使用（DL範囲が不正で中断した場合など）
            if hasattr(self, 'current_gallery_url') and self.current_gallery_url:
                restart_url = self.current_gallery_url
                self.session_manager.ui_bridge.post_log(f"リスタート処理開始: {restart_url} (current_gallery_urlから取得)")
            
            # 優先2: GUIから現在のURLを取得
            if not restart_url:
                current_url_index = self.state_manager.get_current_url_index()
                if current_url_index is not None:
                    # ⭐GUIのurl_panelから現在の行のURLを取得⭐
                    if hasattr(self.parent, 'url_panel') and hasattr(self.parent.url_panel, '_get_url_at_line'):
                        # 行番号は1から開始（current_url_indexは0から開始）
                        line_number = current_url_index + 1
                        restart_url = self.parent.url_panel._get_url_at_line(line_number)
                        
                        if restart_url:
                            self.session_manager.ui_bridge.post_log(f"リスタート処理開始: {restart_url} (GUIから取得)")
                            # ⭐重要: current_gallery_urlも更新（古い値を上書き）⭐
                            self.current_gallery_url = restart_url
                        else:
                            self.session_manager.ui_bridge.post_log(f"[ERROR] リスタート失敗: 行{line_number}にURLが見つかりません", "error")
                    else:
                        self.session_manager.ui_bridge.post_log(f"[ERROR] リスタート失敗: url_panelが利用できません", "error")
            
            # 最終フォールバック: URLステータスからpaused状態のURLを取得
            if not restart_url:
                # paused状態のURLを探す
                url_statuses = self.state_manager.download_state.url_status
                for url, status in url_statuses.items():
                    if status == 'paused':
                        restart_url = url
                        self.current_gallery_url = url
                        self.session_manager.ui_bridge.post_log(f"リスタート処理開始: {restart_url} (paused状態のURLから取得)")
                        break
            
            if not restart_url:
                self.session_manager.ui_bridge.post_log("[ERROR] リスタート失敗: URLが取得できません", "error")
                return

            
            # ⭐修正: StateManager経由でリスタート要求を設定⭐
            self.state_manager.set_restart_requested_url(restart_url)
            
            # 状態をリセット（一時停止状態も解除）
            self.state_manager.set_paused(False)
            self.state_manager.set_pause_requested(False)  # ⭐追加: pause_requestedフラグをクリア⭐
            # ⭐修正: StateManager経由でスキップ要求をクリア⭐
            self.state_manager.set_skip_requested_url(None)
            
            # ⭐重要: リスタート時はダウンロード実行状態を設定⭐
            self.state_manager.set_download_running(True)
            if hasattr(self.parent, 'is_running'):
                self.parent.is_running = True
            
            # ⭐修正: StateManager経由でstop_flagをクリア⭐
            self.state_manager.reset_stop_flag()
            
            # ⭐修正: StateManager経由で既存のダウンロードスレッドを終了⭐
            download_thread = self.state_manager.get_download_thread()
            if download_thread:
                # ⭐修正: FutureオブジェクトかThreadオブジェクトかをチェック⭐
                import threading
                from concurrent.futures import Future
                
                if isinstance(download_thread, threading.Thread):
                    if download_thread.is_alive():
                        self.session_manager.ui_bridge.post_log("リスタート処理: 現在のダウンロードスレッドを終了します", "info")
                        # ⭐修正: StateManager経由でstop_flagを設定⭐
                        self.state_manager.set_stop_flag()
                        try:
                            download_thread.join(timeout=3)  # 3秒待機
                            if download_thread.is_alive():
                                self.session_manager.ui_bridge.post_log("リスタート処理: スレッド終了を待機中...", "warning")
                                download_thread.join(timeout=2)  # 追加で2秒待機
                        except Exception as e:
                            self.session_manager.ui_bridge.post_log(f"リスタート処理: スレッド終了待機エラー: {e}", "warning")
                elif isinstance(download_thread, Future):
                    # Futureオブジェクトの場合はキャンセルを試みる
                    if not download_thread.done():
                        self.session_manager.ui_bridge.post_log("リスタート処理: 現在のダウンロードタスクをキャンセルします", "info")
                        self.state_manager.set_stop_flag()
                        download_thread.cancel()
                        try:
                            download_thread.result(timeout=3)  # 3秒待機
                        except Exception as e:
                            self.session_manager.ui_bridge.post_log(f"リスタート処理: タスクキャンセル待機エラー: {e}", "warning")
                
                # ⭐修正: StateManager経由でスレッド参照をクリア⭐
                self.state_manager.set_download_thread(None)
            
            # ⭐重要: リスタート時に正しいcurrent_url_indexを取得（restart_urlから）⭐
            normalized_restart_url = self.parent.normalize_url(restart_url)
            restart_url_index = self.state_manager.get_url_index_by_url(normalized_restart_url)
            if restart_url_index is None:
                # URLから取得できない場合は、GUIから取得を試みる
                if hasattr(self.parent, 'url_panel') and hasattr(self.parent.url_panel, '_get_url_at_line'):
                    for i in range(1, 1000):  # 最大1000行まで検索
                        url_at_line = self.parent.url_panel._get_url_at_line(i)
                        if url_at_line and self.parent.normalize_url(url_at_line) == normalized_restart_url:
                            restart_url_index = i - 1  # 行番号は1から、インデックスは0から
                            break
            
            # ⭐重要: リスタート時に復帰ポイントをクリア（最初から再開、StateManager経由）⭐
            # DL範囲が無効でDLが止まった場合、古い復帰ポイントが残っている可能性があるため、必ずクリア
            resume_info = self.state_manager.get_resume_point(normalized_restart_url)
            if resume_info:
                # リスタート時は復帰ポイントをクリアして最初から再開
                self.state_manager.clear_resume_point(normalized_restart_url)
            
            # ⭐追加: DLリストのGUIを更新（ステータスと進捗をリセット）⭐
            if hasattr(self.parent, 'download_list_widget'):
                try:
                    # ステータスを'pending'に戻す
                    self.parent.download_list_widget.update_status(normalized_restart_url, 'pending')
                    # 進捗を0にリセット
                    self.parent.download_list_widget.update_progress(normalized_restart_url, 0, 0)
                    self.session_manager.ui_bridge.post_log(f"DLリストをリセットしました: {normalized_restart_url[:50]}", "info")
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(f"DLリストリセットエラー: {e}", "error")
            
            # 現在のオプションからダウンロード範囲を取得
            current_options = self._get_current_options()
            if current_options.get('download_range_enabled', False):
                start_page = current_options.get('download_range_start', '')
                if start_page:
                    try:
                        range_start = int(start_page)
                        # リスタート用の復帰ポイントを作成（範囲の開始ページから）
                        # ⭐重要: restart_url_indexを使用（resume_infoから取得しない）⭐
                        self._save_resume_point(
                            url=restart_url,
                            page=1,  # 範囲内の相対ページ1から開始
                            folder=resume_info.get('folder', '') if resume_info else '',
                            reason='restart',
                            current_url_index=restart_url_index if restart_url_index is not None else 0
                        )
                    except (ValueError, TypeError) as e:
                        self.session_manager.ui_bridge.post_log(f"[WARNING] リスタート範囲解析エラー: {e}", "warning")
            
            # URL状態をdownloadingに戻す
            self.state_manager.set_url_status(restart_url, "downloading")
            
            # ⭐重要: current_url_indexを正しく設定（restart_urlから取得したインデックスを使用）⭐
            if restart_url_index is not None:
                self.state_manager.set_current_url_index(restart_url_index)
            
            # ⭐追加: リスタート時にcurrent_download_range_infoをクリア（新しい範囲で再計算するため）⭐
            if hasattr(self, 'current_download_range_info'):
                delattr(self, 'current_download_range_info')
            
            # ⭐追加: プログレスバーをリセット⭐
            current_url_index = self.state_manager.get_url_index_by_url(restart_url)
            if current_url_index is not None:
                self.state_manager.update_progress_bar_state(
                    current_url_index,
                    current=0,
                    total=None,  # totalは保持
                    status="状態: ダウンロード中"
                )
            
            # プログレスをリセット
            self.state_manager.set_progress(0, 0)
            
            # ⭐削除: URL背景色更新はStateManagerリスナー経由で自動更新されるため不要⭐
            # self.parent.root.after(0, self.parent.url_panel.update_url_background, restart_url)
            
            # オプションキャッシュをクリア（再読み込み用）
            if hasattr(self, '_cached_options'):
                delattr(self, '_cached_options')
            
            # ダウンロードを再開（オプションを取得してから実行）
            self.parent.root.after(100, self._restart_download_with_options, restart_url)
            
            self.session_manager.ui_bridge.post_log(f"リスタート処理完了: {restart_url}")
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"リスタート処理エラー: {e}", "error")
    
    def _restart_download_with_options(self, restart_url: str) -> None:
        """
        オプションを取得してリスタートダウンロードを実行
        
        Args:
            restart_url: リスタート対象URL
        """
        try:
            # リスタートフラグを設定（ループ脱出ポイントで検出）
            # ⭐修正: StateManager経由でリスタート要求を設定⭐
            self.state_manager.set_restart_requested_url(restart_url)
            
            # 既存のスレッドに停止信号を送信（非同期的）
            # ⭐修正: StateManager経由でダウンロードスレッドを確認⭐
            download_thread = self.state_manager.get_download_thread()
            if download_thread and download_thread.is_alive():
                self.session_manager.ui_bridge.post_log("既存のダウンロードスレッドに停止信号を送信...")
                # ⭐修正: StateManager経由でstop_flagを設定⭐
                self.state_manager.set_stop_flag()
                
                # スレッドの自然な終了を待機（ブロッキングしない）
                def check_thread_termination():
                    # ⭐修正: StateManager経由でダウンロードスレッドを確認⭐
                    download_thread = self.state_manager.get_download_thread()
                    if download_thread and download_thread.is_alive():
                        # まだ生きている場合は再チェック
                        self.parent.root.after(100, check_thread_termination)
                    else:
                        # スレッドが終了したら新しいダウンロードを開始
                        self._start_restart_download(restart_url)
                
                # 非同期でスレッド終了を監視
                self.parent.root.after(100, check_thread_termination)
            else:
                # スレッドが存在しない場合は即座に開始
                self._start_restart_download(restart_url)
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"リスタート処理エラー: {e}", "error")
    
    def _start_restart_download(self, restart_url: str) -> None:
        """
        リスタートダウンロードを実際に開始
        
        Args:
            restart_url: リスタート対象URL
        """
        try:
            # スレッド状態をクリア
            # ⭐修正: StateManager経由でスレッド状態をクリア⭐
            self.state_manager.set_download_thread(None)
            self.state_manager.set_current_thread_id(None)
            self.state_manager.reset_stop_flag()
            # ⭐修正: StateManager経由でリスタート要求をクリア⭐
            self.state_manager.set_restart_requested_url(None)
            
            # 状態をリセット
            self.state_manager.set_paused(False)
            self.state_manager.set_paused(False)
            self.state_manager.set_download_running(True)
            
            # オプションを取得
            options = self._get_current_options()
            if not options:
                self.session_manager.ui_bridge.post_log("リスタート用オプション取得に失敗しました", "error")
                return
            
            # リスタート時に復帰ポイントを追加（全ての処理の最初に）
            self._save_resume_point(restart_url, 1, "", "restart", "initial", None, "restart")
            
            # ⭐修正: AsyncExecutor.execute_in_thread()を使用してThreadPoolExecutorでスレッド数を制限⭐
            future = self.parent.async_executor.execute_in_thread(
                self._download_url_thread,
                restart_url, options
            )
            # FutureオブジェクトをStateManagerに保存
            # self.state_manager.set_download_thread(future)
            self.session_manager.ui_bridge.post_log(f"リスタートダウンロードを開始しました: {restart_url}")
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"リスタートダウンロード開始エラー: {e}", "error")
    
    def _set_incomplete_urls_background(self) -> None:
        """未完了のURLの背景色を薄い赤色に設定
        
        Note:
            アプリ終了時に未完了状態のURLを視覚的に表現
        """
        try:
            # 全URLを取得
            content = self.parent.url_text.get("1.0", tk.END)
            urls = self.parent._parse_urls_from_text(content)
            
            for url in urls:
                normalized_url = self.parent.normalize_url(url)
                if normalized_url:
                    # URLの状態を確認
                    url_status = self.parent.url_status.get(normalized_url, 'pending')
                    
                    # 未完了（pending, downloading, paused, error）の場合は薄い赤色に設定
                    if url_status in ['pending', 'downloading', 'paused', 'error']:
                        # ⭐修正: StateManager経由で状態を設定（リスナー経由で自動更新）⭐
                        self.state_manager.set_url_status(normalized_url, 'incomplete')
                        self.parent.url_status[normalized_url] = 'incomplete'
                        # ⭐削除: URL背景色更新はStateManagerリスナー経由で自動更新されるため不要⭐
                        # self.parent.root.after(0, self.parent.url_panel.update_url_background, normalized_url)
                        
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"未完了URL背景色設定エラー: {e}", "error")
    
    def _handle_skip_folder_prefix(self, url: str) -> None:
        """
        スキップ時のフォルダ接頭辞処理
        
        Args:
            url: ギャラリーURL
        """
        try:
            # スキップ時の特別な処理は現在実装していない
            # 必要に応じて後で実装
            self.session_manager.ui_bridge.post_log(f"スキップ時のフォルダ処理: {url}", "debug")
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"スキップフォルダ処理エラー: {e}", "error")
    
    def _create_skip_placeholder_file(self, save_folder: str, page_num: int, 
                                      image_page_url: Optional[str] = None) -> None:
        """スキップ時の代替ファイル作成（インターネットショートカット）"""
        try:
            # スキップ時の代替ファイル名（ページ数、インターネットショートカット形式）
            base_filename = f"{page_num}"
            placeholder_filename = f"{base_filename}.url"
            placeholder_path = os.path.join(save_folder, placeholder_filename)
            
            # 重複ファイル対応: 既に存在する場合は連番を付ける
            counter = 1
            while os.path.exists(placeholder_path):
                placeholder_filename = f"{base_filename}({counter}).url"
                placeholder_path = os.path.join(save_folder, placeholder_filename)
                counter += 1
            
            # インターネットショートカットファイルを作成
            with open(placeholder_path, 'w', encoding='utf-8') as f:
                f.write("[InternetShortcut]\n")
                if image_page_url:
                    f.write(f"URL={image_page_url}\n")
                else:
                    f.write(f"URL=\n")
                f.write(f"; スキップされた画像 (ページ {page_num})\n")
                f.write(f"; スキップ日時: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            self.session_manager.ui_bridge.post_log(f"スキップ代替ファイル作成: {placeholder_filename} (URL: {image_page_url or 'なし'})")
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"スキップ代替ファイル作成エラー: {e}", "error")

    def _handle_network_error_with_retry(self, url: str, error: Exception, 
                                         max_retries: int = 3, base_delay: int = 5) -> bool:
        """
        ネットワークエラー時の自動復帰処理
        
        Args:
            url: テストするURL
            error: 発生したエラー
            max_retries: 最大リトライ回数
            base_delay: 基本待機時間（秒）
            
        Returns:
            復帰成功時True
        """
        self.session_manager.ui_bridge.post_log(f"ネットワークエラー検出: {error}")
        self.session_manager.ui_bridge.post_log("自動復帰を試行します...")
        
        for attempt in range(max_retries):
            try:
                # 指数バックオフで待機
                delay = base_delay * (2 ** attempt)
                self.session_manager.ui_bridge.post_log(f"復帰試行 {attempt + 1}/{max_retries}: {delay}秒待機中...")
                time.sleep(delay)
                
                # 接続テスト
                test_response = self.session_manager.http_client.get(url, timeout=10)
                if test_response.status_code == 200:
                    self.session_manager.ui_bridge.post_log(f"ネットワーク復帰成功: 試行 {attempt + 1}")
                    return True
                    
            except Exception as retry_error:
                self.session_manager.ui_bridge.post_log(f"復帰試行 {attempt + 1} 失敗: {retry_error}")
                continue
        
        self.session_manager.ui_bridge.post_log("ネットワーク復帰に失敗しました")
        return False
    
    def get_thumbnail_url(self, gallery_url: str) -> Optional[str]:
        """
        ギャラリーの最初のサムネイル画像のURLを取得（gd1要素のbackground URL方式）
        
        Args:
            gallery_url: ギャラリーURL
            
        Returns:
            サムネイルURLまたはNone
        """
        try:
            # サムネイルURL取得開始
            
            # ギャラリーページを取得
            response = self.session_manager.http_client.get(gallery_url, timeout=30)
            response.raise_for_status()
            html = response.text
            
            # gd1要素のbackground URLを取得
            # <div id="gd1"><div style="...background:transparent url(XXX)...">
            gd1_pattern = re.compile(r'<div id="gd1"[^>]*>.*?background:\s*transparent\s+url\(([^)]+)\)', re.DOTALL | re.IGNORECASE)
            gd1_match = gd1_pattern.search(html)
            if gd1_match:
                thumbnail_url = gd1_match.group(1)
                # サムネイルURL取得完了(gd1)
                return thumbnail_url
            
            # フォールバック: 通常のimgタグから取得
            img_pattern = re.compile(r'<img[^>]+(?:data-)?src="([^"]+\.(?:webp|jpe?g|png|gif))"', re.IGNORECASE)
            img_match = img_pattern.search(html)
            if img_match:
                thumbnail_url = img_match.group(1)
                # サムネイルURL取得完了(img)
                return thumbnail_url
            
            # パターンマッチに失敗した場合、HTMLの一部をログに出力
            # サムネイルURLが見つかりませんでした
            return None
                
        except Exception as e:
            # サムネイルURL取得エラー
            return None
    
    def _extract_all_tags(self, html: str) -> Dict[str, List[Dict[str, str]]]:
        """HTMLから全タグを抽出
        
        Args:
            html: HTML文字列
            
        Returns:
            タグ情報の辞書（カテゴリ別）
        """
        try:
            # タグ抽出の正規表現
            pattern_tags = re.compile(r'id="ta_([^:]+):([^"]+)"[^>]*>([^<]+)</a>')
            tags = [(m.group(1), m.group(2), m.group(3)) for m in pattern_tags.finditer(html)]
            
            # タグを辞書形式で整理
            tag_dict = {}
            for category, tag_id, tag_name in tags:
                # カテゴリ別にタグを整理
                if category not in tag_dict:
                    tag_dict[category] = []
                tag_dict[category].append({
                    'id': tag_id,
                    'name': tag_name,
                    'full_tag': f"{category}:{tag_name}"
                })
            
            return tag_dict
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"タグ抽出エラー: {e}", "error")
            return {}
    
    def _update_metadata_with_tags(self, all_tags: Dict[str, List[Dict[str, str]]]) -> None:
        """
        抽出されたタグでメタデータを更新
        
        Args:
            all_tags: タグ情報の辞書
        """
        try:
            # 既存のメタデータを更新
            if hasattr(self, 'artist') and 'artist' in all_tags:
                self.artist = ', '.join([tag['name'] for tag in all_tags['artist']])
            
            if hasattr(self, 'parody') and 'parody' in all_tags:
                self.parody = ', '.join([tag['name'] for tag in all_tags['parody']])
            
            if hasattr(self, 'character') and 'character' in all_tags:
                self.character = ', '.join([tag['name'] for tag in all_tags['character']])
            
            if hasattr(self, 'group') and 'group' in all_tags:
                self.group = ', '.join([tag['name'] for tag in all_tags['group']])
            
            # 新しいタグカテゴリを追加
            for category, tags in all_tags.items():
                if category not in ['artist', 'parody', 'character', 'group']:
                    # 新しいカテゴリのタグを保存
                    if not hasattr(self, 'additional_tags'):
                        self.additional_tags = {}
                    self.additional_tags[category] = [tag['name'] for tag in tags]
            
            # 全タグを保存（カスタム命名用）
            self.all_extracted_tags = all_tags
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"メタデータ更新エラー: {e}", "error")
    
    def _extract_comprehensive_metadata(self) -> Dict[str, Any]:
        """
        包括的なメタデータを抽出（空のデータは除外）
        
        Returns:
            メタデータ辞書
        """
        try:
            comprehensive_data: Dict[str, Any] = {}
            
            # 基本的な属性をチェック
            basic_attributes = [
                'current_gallery_title', 'current_save_folder', 'current_gallery_url',
                'artist', 'parody', 'character', 'group', 'language', 'category',
                'uploader', 'gid', 'token', 'date', 'rating', 'filesize'
            ]
            
            for attr in basic_attributes:
                value = getattr(self, attr, None)
                if value and str(value).strip() and str(value).strip() != 'Unknown':
                    comprehensive_data[attr] = str(value).strip()
            
            # タグ情報をチェック
            if hasattr(self, 'all_extracted_tags') and self.all_extracted_tags:
                comprehensive_data['all_extracted_tags'] = self.all_extracted_tags
            
            if hasattr(self, 'additional_tags') and self.additional_tags:
                comprehensive_data['additional_tags'] = self.additional_tags
            
            # ダウンロードオプションを追加
            if hasattr(self.parent, 'wait_time'):
                comprehensive_data['download_options'] = {
                    'wait_time': self.parent.wait_time.get(),
                    'sleep_value': self.parent.sleep_value.get(),
                    'save_format': self.parent.save_format.get(),
                    'save_name': self.parent.save_name.get(),
                    'folder_path': self.parent.folder_var.get(),
                }
            
            # 現在のURL情報を追加
            if hasattr(self.parent, 'current_url_index'):
                comprehensive_data['current_url_index'] = self.parent.current_url_index
            
            if hasattr(self.parent, 'url_list'):
                comprehensive_data['total_urls'] = len(self.parent.url_list)
            
            # タイムスタンプを追加
            comprehensive_data['extraction_timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            return comprehensive_data
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"包括的メタデータ抽出エラー: {e}", "error")
            return {}
    
    def _filter_empty_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        空のデータをフィルタリングして返す
        
        Args:
            data: 元データ辞書
            
        Returns:
            フィルタリング済みデータ辞書
        """
        try:
            filtered_data: Dict[str, Any] = {}
            
            for key, value in data.items():
                # 値が存在し、空でない場合のみ追加
                if value is not None:
                    if isinstance(value, (str, int, float)):
                        # 文字列、数値の場合
                        if str(value).strip() and str(value).strip() != 'Unknown':
                            filtered_data[key] = value
                    elif isinstance(value, (dict, list)):
                        # 辞書、リストの場合
                        if value:  # 空でない場合のみ
                            filtered_data[key] = value
                    elif isinstance(value, bool):
                        # ブール値は常に追加
                        filtered_data[key] = value
                    else:
                        # その他の型は文字列化してチェック
                        str_value = str(value).strip()
                        if str_value and str_value != 'Unknown':
                            filtered_data[key] = value
            
            return filtered_data
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"空データフィルタリングエラー: {e}", "error")
            return data  # エラー時は元のデータを返す
    
    def _log_download_options(self, options: Dict[str, Any]) -> None:
        """
        ダウンロードオプション情報をログ出力
        
        Args:
            options: オプション辞書
        """
        try:
            self.session_manager.ui_bridge.post_log("=== ダウンロードオプション ===", "info")
            
            # 基本設定
            self.session_manager.ui_bridge.post_log(f"保存フォルダ: {options.get('folder_path', '')}", "info")
            self.session_manager.ui_bridge.post_log(f"待機時間: {options.get('wait_time', 1.0)}秒", "info")
            self.session_manager.ui_bridge.post_log(f"スリープ時間: {options.get('sleep_value', 0.5)}秒", "info")
            
            # ファイル名・拡張子設定
            save_format = options.get('save_format', 'Original')
            rename_option = options.get('rename_option', 'Original')
            self.session_manager.ui_bridge.post_log(f"保存形式: {save_format}", "info")
            self.session_manager.ui_bridge.post_log(f"ファイル名設定: {rename_option}", "info")
            
            # 文字列置換
            if options.get('string_replacement', False):
                from_str = options.get('string_replacement_from', '')
                to_str = options.get('string_replacement_to', '')
                self.session_manager.ui_bridge.post_log(f"文字列置換: '{from_str}' → '{to_str}'", "info")
            
            # 拡張子変更
            if options.get('extension_change', False):
                from_ext = options.get('extension_from', '')
                to_ext = options.get('extension_to', '')
                self.session_manager.ui_bridge.post_log(f"拡張子変更: '{from_ext}' → '{to_ext}'", "info")
            
            # 圧縮設定
            if options.get('compression', False):
                quality = options.get('compression_quality', 85)
                format_type = options.get('compression_format', 'JPEG')
                self.session_manager.ui_bridge.post_log(f"圧縮設定: {format_type} (品質: {quality}%)", "info")
            
            # ダウンロード範囲（有効な場合のみ表示）
            if options.get('download_range_enabled', False):
                start_range = options.get('download_range_start', '')
                end_range = options.get('download_range_end', '')
                if start_range or end_range:
                    range_str = f"{start_range}〜{end_range}" if end_range else f"{start_range}〜最後まで"
                    self.session_manager.ui_bridge.post_log(f"ダウンロード範囲: {range_str}", "info")
            
            # エラー処理設定（最新設計：Context-Aware自動エラーハンドリング）
            smart_error_handling = options.get('smart_error_handling', True)
            if smart_error_handling:
                base_retry = options.get('base_retry_count', 5)
                base_wait = options.get('base_wait_time', 3)
                circuit_breaker = options.get('circuit_breaker_threshold', 5)
                selenium_auto = options.get('selenium_enabled', True)
                self.session_manager.ui_bridge.post_log(
                    f"エラー処理: Context-Aware自動ハンドリング "
                    f"(基準リトライ: {base_retry}回, 基準待機: {base_wait}秒, "
                    f"Circuit Breaker: {circuit_breaker}回, Selenium自動適用: {'ON' if selenium_auto else 'OFF'})",
                    "info"
                )
            else:
                # レガシー設定（互換性のため保持）
                resume_option = options.get('resume_option', 'manual')
                retry_count = options.get('retry_count', 3)
                retry_delay = options.get('retry_delay', 5)
                self.session_manager.ui_bridge.post_log(
                    f"エラー処理: {resume_option} (リトライ: {retry_count}回, 間隔: {retry_delay}秒)",
                    "info"
                )
            
            # Selenium設定
            if options.get('use_selenium', False):
                selenium_retry = options.get('selenium_retry_count', 3)
                selenium_delay = options.get('selenium_retry_delay', 10)
                selenium_failure = options.get('selenium_failure_option', 'skip_image')
                self.session_manager.ui_bridge.post_log(f"Selenium使用: リトライ{selenium_retry}回, 間隔{selenium_delay}秒, 失敗時{selenium_failure}", "info")
            
            # その他の設定
            if options.get('rename_incomplete_folder', False):
                self.session_manager.ui_bridge.post_log("未完了フォルダリネーム: 有効", "info")
            
            if options.get('progress_separate_window_enabled', False):
                auto_scroll = options.get('progress_separate_window_auto_scroll', True)
                self.session_manager.ui_bridge.post_log(f"プログレス別ウィンドウ: 有効 (自動スクロール: {'ON' if auto_scroll else 'OFF'})", "info")
            
            self.session_manager.ui_bridge.post_log("========================", "info")
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"オプション情報ログ出力エラー: {e}", "error")
    
    def _calculate_total_pages_for_resume(self, resume_info: Dict[str, Any], 
                                          current_options: Dict[str, Any]) -> Optional[int]:
        """
        復帰時の総ページ数を統一的に計算
        
        Args:
            resume_info: 再開情報
            current_options: 現在のオプション
            
        Returns:
            計算された総ページ数またはNone
        """
        try:
            if not resume_info:
                return None
            
            # ダウンロード範囲設定の確認
            new_range_enabled = current_options.get('download_range_enabled', False)
            
            # 範囲設定が有効でない場合は再計算しない
            if not new_range_enabled:
                return None
            
            # 新しい範囲に基づいて総ページ数を計算
            new_range_start_str = current_options.get('download_range_start', '')
            new_range_end_str = current_options.get('download_range_end', '')
            
            if not new_range_start_str:
                return None
            
            try:
                new_range_start = int(new_range_start_str)
                new_range_end = int(new_range_end_str) if new_range_end_str else None
            except (ValueError, TypeError) as e:
                self.session_manager.ui_bridge.post_log(f"[WARNING] 新しい範囲の解析エラー: {e}", "warning")
                return None
            
            # ⭐修正: ギャラリー全体の総ページ数を取得（復帰ポイントから、範囲適用前の元のページ数を使用）⭐
            # gallery_metadata['total_pages']は範囲適用後のページ数になっている可能性があるため、
            # gallery_infoから元のページ数を取得する
            gallery_total_pages = 0
            gallery_info = resume_info.get('gallery_info')
            if gallery_info and 'original_total' in gallery_info:
                # 範囲適用前の元の総ページ数を使用
                gallery_total_pages = gallery_info['original_total']
            elif gallery_info and 'original_total_images' in gallery_info:
                # original_total_imagesから取得
                gallery_total_pages = gallery_info['original_total_images']
            else:
                # フォールバック: gallery_metadataから取得
                gallery_total_pages = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
            
            if gallery_total_pages <= 0:
                return None
            
            if new_range_start > gallery_total_pages:
                # ⭐修正: 範囲開始がギャラリー全体のページ数を超えている場合、既存のページ数を保持⭐
                # 0を返すとページ数がリセットされるため、既存のページ数を返す
                existing_total = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
                if existing_total > 0:
                    self.session_manager.ui_bridge.post_log(f"[WARNING] 範囲開始({new_range_start})がギャラリー全体({gallery_total_pages})を超えています。既存のページ数({existing_total})を保持します。")
                    return existing_total
                else:
                    self.session_manager.ui_bridge.post_log(f"[WARNING] 範囲開始({new_range_start})がギャラリー全体({gallery_total_pages})を超えています")
                    return None  # 0ではなくNoneを返す（ページ数再計算をスキップ）
            elif new_range_end:
                new_total_pages = min(new_range_end, gallery_total_pages) - new_range_start + 1
            else:
                new_total_pages = gallery_total_pages - new_range_start + 1
            
            # 負の値にならないよう調整
            new_total_pages = max(0, new_total_pages)
            
            self.session_manager.ui_bridge.post_log(f"[DEBUG] 新しい範囲に基づく総ページ数計算: ギャラリー全体={gallery_total_pages}, 新範囲={new_range_start}-{new_range_end}, 新総ページ数={new_total_pages}")
            
            return new_total_pages
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"[ERROR] ページ数再計算エラー: {e}", "error")
            return None
    
    # ⭐削除: _update_progress_unified（既にupdate_current_progressに統合済み）⭐
    # プログレス更新は update_current_progress() に統一され、
    # StateManager.update_progress_bar_state() 経由でGUI層に通知される

