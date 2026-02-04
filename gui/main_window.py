# -*- coding: utf-8 -*-
"""
E-Hentai Downloader - メインウィンドウ
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import json
import re
from tkinterdnd2 import DND_FILES

from typing import Callable, Any, List
from tkinter import Event

from gui.components.url_panel import EHDownloaderUrlPanel
from gui.components.progress_panel import EHDownloaderProgressPanel
from gui.components.options_panel import EHDownloaderOptionsPanel
from gui.components.download_list_widget import DownloadListWidget
from core.downloader import EHDownloaderCore
from core.managers.state_manager import StateManager
from core.communication.async_executor import AsyncExecutor
from core.interfaces import IStateManager, IAsyncExecutor
from gui.managers.options_manager import OptionsManager
# error_handler削除済み - 使用されていませんでした

class EHDownloader:
    def on_progress_updated(self, url_index, data):
        """StateManagerからの進捗更新通知でフットバー進捗・経過時間を自動更新"""
        try:
            # 進捗数・総数はStateManagerから即時取得（重くならない）
            completed = self.state_manager.get_completed_url_count() if hasattr(self, 'state_manager') else 0
            total = self.state_manager.get_total_url_count() if hasattr(self, 'state_manager') else 0
            self.update_footer_progress(completed, total)
            # 経過時間（全体DL開始からの秒数）
            elapsed = 0
            if hasattr(self, 'sequence_start_time') and self.sequence_start_time:
                import time
                elapsed = int(time.time() - self.sequence_start_time)
            self.update_footer_elapsed_time(elapsed)
        except Exception as e:
            pass  # ログ不要
    SETTINGS_FILENAME = "ehd_settings.json"
    
    # 同名ファイル・フォルダ処理の言語マッピング
    DUPLICATE_MODE_MAPPING = {
        # 日本語 → 英語
        "同名ファイルに上書き保存": "overwrite",
        "新しいファイル名で保存 (例: file(1).jpg)": "rename", 
        "スキップ": "skip",
        "同名フォルダに上書き保存": "overwrite",
        "新しいフォルダ名で保存 (例: Folder(1))": "rename",
        "そのギャラリーからのDLをスキップ": "skip"
    }
    
    DUPLICATE_MODE_REVERSE = {v: k for k, v in DUPLICATE_MODE_MAPPING.items()}
    
    # デフォルト値の一箇所集約（わかりやすい辞書として規定）
    DEFAULT_VALUES = {
        # === ウィンドウ設定 ===
        'window_state': "normal",            # ウィンドウ状態（normal/maximized/iconic）
        
        # === 基本設定 ===
        'wait_time': "0.5",                  # ページ間待機時間（秒）
        'sleep_value': "0.5",                # 画像間待機時間（秒）
        'save_format': "Original",           # 保存形式（Original/JPEG/PNG/WebP）
        'save_name': "Original",             # ファイル名形式（Original/Custom）
        'custom_name': "{artist}_{title}_{page}",  # カスタムファイル名テンプレート
        
        # === リサイズ設定 ===
        'resize_enabled': "off",             # リサイズ機能（off/on）
        'resize_mode': "縦幅上限",           # リサイズモード（縦幅上限/横幅上限/短辺上限/長辺上限/パーセント/統一サイズ）
        'resize_values': {                   # リサイズ値のデフォルト
            'height': "1024",
            'width': "1024", 
            'short': "1024",
            'long': "1024",
            'percentage': "80",
            'unified': "1600"
        },
        'interpolation_mode': "三次補完（画質優先）",  # 補間モード
        'sharpness_value': "1.5",            # シャープネス値（1-2の範囲）
        'keep_original': True,               # オリジナルファイル保持
        'resize_filename_enabled': False,    # リサイズファイル名変更
        'resized_subdir_name': "resized",    # リサイズサブディレクトリ名
        'resized_prefix': "",                # リサイズファイル接頭辞
        'resized_suffix': "_resized",        # リサイズファイル接尾辞
        'resize_save_location': "child",     # リサイズ保存場所（child/parent）
        
        # === フォルダ・ファイル管理 ===
        'duplicate_folder_mode': "rename",   # 重複フォルダ処理（rename/overwrite/skip）
        'duplicate_file_mode': "overwrite",  # 重複ファイル処理（overwrite/rename/skip）
        'rename_incomplete_folder': False,   # 未完了フォルダリネーム
        'incomplete_folder_prefix': "[INCOMPLETE]_",  # 未完了フォルダ接頭辞
        'folder_name_mode': "h1_priority",   # フォルダ名モード（h1_priority/custom）
        'custom_folder_name': "{artist}_{title}",  # カスタムフォルダ名テンプレート
        
        # === 圧縮設定 ===
        'compression_enabled': "off",        # 圧縮機能（off/on）
        'compression_format': "ZIP",         # 圧縮形式（ZIP/7Z/TAR）
        'compression_delete_original': False,  # 圧縮後オリジナル削除
        
        # === エラー処理・再開設定 ===
        'error_handling_enabled': True,           # エラー処理のON/OFF
        'error_handling_mode': "auto_resume",     # エラー処理モード（manual/auto_resume）
        'auto_resume_delay': "5",            # 自動再開遅延（秒）
        'retry_delay_increment': "10",       # リトライ遅延増分（秒）
        'max_retry_delay': "60",             # 最大リトライ遅延（秒）
        'max_retry_count': "3",              # 最大リトライ回数
        'retry_limit_action': "selenium_retry",        # ⭐修正: デフォルト値を"selenium_retry"に変更（Selenium安全弁を有効化）⭐
        'selenium_scope': "1",                         # Selenium有効範囲（ページ数）
        'selenium_failure_action': "manual_resume",    # Selenium失敗時の動作（skip_url/skip_image/manual_resume）
        
        # === ページ・ファイル命名設定 ===
        'first_page_use_title': False,       # 1ページ目タイトル使用
        'first_page_naming_enabled': False,  # 1ページ目命名機能
        'first_page_naming_format': "title", # 1ページ目命名形式（title/number）
        'skip_count': "10",                  # スキップカウント
        'skip_after_count_enabled': False,   # カウント後スキップ機能
        
        # === 画像品質設定 ===
        'jpg_quality': 85,                   # JPEG品質（1-100）
        'preserve_animation': True,          # アニメーション保持
        
        # === 文字列変換設定 ===
        'string_conversion_enabled': False,  # 文字列変換機能
        'string_conversion_rules': [],       # 文字列変換ルール
        
        # === マルチスレッド設定 ===
        'multithread_enabled': "off",        # マルチスレッド機能（off/on）
        'multithread_count': 3,              # スレッド数
        
        # === 高度なオプション ===
        'advanced_options_enabled': False,   # 高度なオプション表示
        'user_agent_spoofing_enabled': False,  # User-Agent偽装
        'httpx_enabled': False,              # HTTPX使用
        'selenium_enabled': False,           # Selenium使用
        'selenium_session_retry_enabled': False,  # Seleniumセッションリトライ
        'selenium_persistent_enabled': False,     # Selenium永続化
        'selenium_page_retry_enabled': False,     # Seleniumページリトライ
        'selenium_mode': 'session',               # Seleniumリトライモード
        'download_range_enabled': False,          # ダウンロード範囲オプション
        'download_range_mode': '1行目のURLのみ',    # ダウンロード範囲モード
        'download_range_start': '',               # 開始ページ
        'download_range_end': '',                 # 終了ページ
        'error_handling_enabled': True,           # エラー処理の有効/無効
        'thumbnail_display_enabled': "off",       # サムネイル表示の有効/無効
        'progress_separate_window_enabled': False, # ダウンロードマネージャー起動の有効/無効
        # Seleniumオプション設定
        'selenium_options_enabled': True,         # Seleniumオプション全体のON/OFF（既定値: ON）
        'selenium_minimal_options': True,         # 最小限のオプションで起動（競合回避用）（既定値: ON）
        'selenium_manager_enabled': False,        # Selenium Managerを使用
        'selenium_stop_chrome_background': False, # Chromeのバックグラウンドプロセスを停止
        'selenium_custom_paths_enabled': False,  # カスタムパス指定機能のON/OFF
        'selenium_driver_path': "",               # ChromeDriverパス（空欄は自動検出）
        'selenium_chrome_path': "",               # Chromeパス（空欄は自動検出）
        'selenium_cleanup_temp': False,           # 一時ディレクトリをクリーンアップ（通常DLでも使用）
        'selenium_use_registry_version': True,    # レジストリからChromeバージョンを取得
        # Seleniumテストモード設定
        'selenium_test_minimal_options': False,   # 最小限のオプションで起動
        'selenium_test_no_headless': False        # ヘッドレスモードを無効化
    }
    
    STATE_KEYS = [ # Reflects variables to be saved/loaded
        'window_geometry', 'window_state', 'folder_path', 'wait_time', 'sleep_value',
        'save_format', 'save_name', 'custom_name', 'cookies_var',
        'resize_mode', 'resize_values', 'keep_original', 'keep_unresized', 'save_resized_subdir',
        'resized_subdir_name', 'resized_prefix', 'resized_suffix',
        'resize_filename_enabled', 'resize_save_location',
        'duplicate_folder_mode', 'initial_error_mode', 'error_handling_mode',
        'rename_incomplete_folder', 'incomplete_folder_prefix',
        'compression_enabled', 'compression_format', 'compression_delete_original', 'compression_delete_folder',
        'auto_resume_enabled', 'auto_resume_delay', 'retry_delay_increment',
        'max_retry_delay', 'max_retry_mode', 'max_retry_count', 'retry_limit_action',
        'selenium_scope', 'selenium_failure_action',
        'url_list_content', 'current_url_index', 'url_status',
        'log_content', 'total_elapsed_seconds',
        # 新規追加
        'folder_name_mode', 'custom_folder_name', 'first_page_naming_enabled', 
        'first_page_naming_format', 'duplicate_file_mode', 'skip_count',
        'skip_after_count_enabled',
        # 文字列変換オプション
        'string_conversion_enabled', 'string_conversion_rules',
        # JPG品質設定
        'jpg_quality',
        # 高度なオプション（エラー回避）
        'advanced_options_enabled', 'user_agent_spoofing_enabled', 'httpx_enabled', 
        'selenium_enabled', 'selenium_session_retry_enabled', 'selenium_persistent_enabled', 'selenium_page_retry_enabled', 'selenium_mode',
        'download_range_enabled', 'download_range_mode', 'download_range_start', 'download_range_end', 'error_handling_enabled',
        # 表示オプション
        'thumbnail_display_enabled', 'progress_separate_window_enabled',
        # 軽度エラーのタイムラグ設定
        'light_error_delay',
        # Seleniumオプション設定
        'selenium_options_enabled', 'selenium_minimal_options', 'selenium_manager_enabled', 'selenium_stop_chrome_background',
        'selenium_custom_paths_enabled', 'selenium_driver_path', 'selenium_chrome_path', 'selenium_cleanup_temp',
        'selenium_use_registry_version',
        # Seleniumテストモード設定
        'selenium_test_minimal_options', 'selenium_test_no_headless',
        # ダウンロード情報保存オプション
        'dl_log_enabled', 'dl_log_individual_save', 'dl_log_batch_save', 'dl_log_file_format',
        # 同名フォルダ処理とSSL設定
        'duplicate_file_mode', 'always_ssl_security_level',
        # 強化されたエラーハンドリング設定
        'enhanced_error_handling_enabled', 'enhanced_error_mode', 'retry_strategy',
        'enhanced_max_retry_count', 'enhanced_retry_delay', 'enhanced_max_delay',
                'enhanced_resume_age_hours', 'retry_limit_action',
        # ⭐修正: Seleniumオプションを分離⭐
        'selenium_always_enabled', 'selenium_fallback_enabled', 'selenium_use_for_page_info',
        'selenium_timeout',
        # 設定ファイル保存場所
        # カスタムディレクトリ機能を削除
        # 'current_gallery_url', 'current_image_page_url', 'current_save_folder', 'gallery_metadata'
        # These are typically volatile runtime states, not persisted unless specifically needed for resume.
    ]
    MIN_PANE_HEIGHT = 200 # Minimum height for panes
    
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        from app_info import APP_NAME, VERSION_STRING
        self.root.title(f"{APP_NAME} {VERSION_STRING}")
        self.root.geometry("1630x1380")  # ウィンドウ全体の幅を50px増加、高さを50px減少
        self.root.state('normal')  # ウィンドウを通常状態で表示
        
        # スタイル設定
        self.style = ttk.Style()
        self.style.configure('BigButton.TButton', font=('Arial', 10, 'bold'))
        self.style.configure('MediumButton.TButton', font=('Arial', 9))
        
        # 状態管理
        self.state_manager = StateManager()
        # ⭐修正: max_workers=1でスレッド数を1に制限（1URLずつ順次処理）⭐
        self.async_executor = AsyncExecutor(self.root, max_workers=1)
        
        # ⭐削除: self.sessionは不要（http_clientがスレッドローカルで管理）⭐
        # import requests
        # self.session = requests.Session()
        
        # プログレス表示関連
        self.progress_visible = False
        self.progress_cleanup_needed = False
        self.progress_bars = []
        self.progress_update_lock = threading.Lock()
        
        # Folder path
        import os
        self.folder_path = os.path.join(os.path.expanduser("~"), "Documents")  # 保存ディレクトリのパス（初期値：UserのDocuments）
        
        # Time tracking
        self.sequence_start_time = None
        self.current_download_start_time = None
        self.total_elapsed_seconds = 0
        self.last_elapsed_update_time = None
        self.elapsed_time_timer_id = None
        
        # ダウンロード状態（StateManagerで管理）
        # self.is_running と self.paused は削除（StateManager経由で取得）
        self.current_url_index = 0
        self.url_status = {}
        
        # 連打防止フラグ
        self._pause_processing = False
        self._resume_processing = False
        self._skip_processing = False
        
        # 現在のページとフォルダ情報
        self.current_image_page_url = ""
        self.current_save_folder = ""
        
        # ロック
        self.lock = threading.Lock()
        
        # コンポーネント初期化
        self._initialize_tkinter_variables()
        self._create_menu_bar()  # メニューバーを先に作成
        self._create_gui()
        
        # settings_backup_managerを先に初期化
        # self.log("settings_backup_manager初期化開始", "debug")  # DEBUG: 起動時のログを整理
        try:
            from core.managers.settings_backup_manager import SettingsBackupManager
            # self.log("SettingsBackupManagerインポート完了", "debug")  # DEBUG: 起動時のログを整理
            self.settings_backup_manager = SettingsBackupManager(self)
            # self.log(f"settings_backup_manager初期化完了: {hasattr(self, 'settings_backup_manager')}", "debug")  # DEBUG: 起動時のログを整理
        except Exception as e:
            self.log(f"settings_backup_manager初期化エラー: {e}", "error")
            import traceback
            self.log(f"詳細エラー: {traceback.format_exc()}", "error")
            # フォールバック用のダミーオブジェクトを作成
            self.settings_backup_manager = None
        
        # 統合エラーレジュームマネージャーの初期化（コンポーネント初期化前に必要）
        from core.errors.unified_error_resume_manager import UnifiedErrorResumeManager
        self.unified_error_resume_manager = UnifiedErrorResumeManager(
            self,  # IStateManager
            self,  # ILogger
            self,  # IGUIOperations
            self   # IFileOperations
        )
        
        # Controllerの初期化
        from gui.controllers.download_controller import DownloadController
        from gui.controllers.preset_controller import PresetController
        from gui.controllers.backup_controller import BackupController
        from gui.controllers.folder_controller import FolderController
        
        self.download_controller = DownloadController(self)
        self.preset_controller = PresetController(self)
        self.backup_controller = BackupController(self)
        self.folder_controller = FolderController(self)
        
        # コンポーネント初期化（エラーハンドリング付き）
        try:
            self._initialize_components()
            # self.log("_initialize_components完了", "debug")  # DEBUG: 起動時のログを整理
        except Exception as e:
            self.log(f"_initialize_componentsエラー: {e}", "error")
            import traceback
            self.log(f"詳細エラー: {traceback.format_exc()}", "error")
        
        # 設定読み込み（settings_backup_manager初期化後）
        # self.log(f"load_settings_and_state呼び出し前: settings_backup_manager存在={hasattr(self, 'settings_backup_manager')}", "debug")  # DEBUG: 起動時のログを整理
        self.load_settings_and_state()
        
        # ⭐追加: プログレスバー状態マネージャーの初期化⭐
        from core.managers.progress_state_manager import ProgressStateManager
        self.progress_state_manager = ProgressStateManager()
        
        # ⭐削除: プログレスバー状態の復元機能を削除⭐
        # プログレスバー情報は外部ファイルに保存しないため、復元も不要
        
        # ⭐Phase 2: StateManagerのオブザーバーとして登録⭐
        if hasattr(self, 'state_manager'):
            self.state_manager.attach_observer(self)
            self.log("[Observer] StateManagerに登録しました", "debug")
        
        # ⭐重要: 設定読み込み後に自動同期を設定⭐
        if hasattr(self, 'options_manager'):
            self.options_manager.setup_auto_sync()
            self.log("[OptionsManager] 自動同期を設定しました", "debug")
        
        # 強化されたエラーハンドラーの初期化
        from core.errors.enhanced_error_handler import EnhancedErrorHandler
        self.enhanced_error_handler = EnhancedErrorHandler(
            self,  # IStateManager
            self,  # ILogger
            self,  # IGUIOperations
            self,  # IFileOperations
            self   # IAsyncExecutor
        )
        
        # error_handler削除済み - enhanced_error_handlerに統合されました
        
        # ユーザー操作の監視を開始
        self._start_user_operation_monitoring()
        
        # ⭐DEBUG: EHDownloader初期化完了⭐
        print("[MAIN_WINDOW] ========== EHDownloader.__init__完了 ==========")
    
    def _start_user_operation_monitoring(self) -> None:
        """ユーザー操作の監視を開始"""
        try:
            # ボタンイベントの監視を設定
            self._setup_button_monitoring()
            
            # キーボードショートカットの監視を設定
            self._setup_keyboard_monitoring()
            
            # self.log("ユーザー操作監視を開始しました", "debug")  # DEBUG: 起動時のログを整理
            
        except Exception as e:
            self.log(f"ユーザー操作監視開始エラー: {e}", "error")
    
    def _setup_button_monitoring(self) -> None:
        """ボタンイベントの監視を設定"""
        try:
            # 既存のボタンイベントを拡張
            if hasattr(self, 'start_button'):
                original_command = self.start_button.cget('command')
                self.start_button.config(command=lambda: self._handle_button_click('start', original_command))
            
            if hasattr(self, 'pause_button'):
                original_command = self.pause_button.cget('command')
                self.pause_button.config(command=lambda: self._handle_button_click('pause', original_command))
            
            if hasattr(self, 'stop_button'):
                original_command = self.stop_button.cget('command')
                self.stop_button.config(command=lambda: self._handle_button_click('stop', original_command))
                
        except Exception as e:
            self.log(f"ボタン監視設定エラー: {e}", "error")
    
    def _setup_keyboard_monitoring(self) -> None:
        """キーボードショートカットの監視を設定"""
        try:
            # キーボードショートカットの設定
            self.root.bind('<Control-s>', lambda e: self._handle_keyboard_shortcut('start'))
            self.root.bind('<Control-p>', lambda e: self._handle_keyboard_shortcut('pause'))
            self.root.bind('<Control-q>', lambda e: self._handle_keyboard_shortcut('stop'))
            self.root.bind('<Escape>', lambda e: self._handle_keyboard_shortcut('escape'))
            
        except Exception as e:
            self.log(f"キーボード監視設定エラー: {e}", "error")
    
    def _handle_button_click(self, operation: str, original_command: Callable) -> None:
        """ボタンクリックの処理"""
        try:
            # ユーザー操作を登録
            if hasattr(self, 'enhanced_error_handler'):
                self.enhanced_error_handler.register_user_operation(operation)
            
            # 元のコマンドを実行
            if original_command:
                original_command()
                
        except Exception as e:
            self.log(f"ボタンクリック処理エラー: {e}", "error")
    
    def _handle_keyboard_shortcut(self, operation: str) -> None:
        """キーボードショートカットの処理"""
        try:
            # ユーザー操作を登録
            if hasattr(self, 'enhanced_error_handler'):
                self.enhanced_error_handler.register_user_operation(operation)
            
            # 操作に応じた処理
            is_running = self.downloader_core.state_manager.is_download_running() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            if operation == 'start' and not is_running:
                self.start_download_sequence()
            elif operation == 'pause' and is_running:
                self.pause_download()
            elif operation == 'stop' and is_running:
                self.stop_download()
            elif operation == 'escape':
                if is_running:
                    self.stop_download()
                else:
                    self.root.quit()
                    
        except Exception as e:
            self.log(f"キーボードショートカット処理エラー: {e}", "error")
    
    def _update_button_states_unified(self, state: str) -> None:
        """GUIボタン状態の統一管理
        
        Args:
            state: 状態名
                - 'idle': アイドル状態（ダウンロード前）
                - 'downloading': ダウンロード中
                - 'paused': 一時停止中
                - 'error': エラー発生
                - 'completed': 完了
        
        Note:
            全てのエラー/リスタート/レジュームパターンで統一的に適用
        """
        try:
            # メインウィンドウのボタン状態を更新
            if state == 'idle':
                if hasattr(self, 'start_button'):
                    self.start_button.config(state='normal', text='ダウンロード')
                if hasattr(self, 'pause_button'):
                    self.pause_button.config(state='disabled')
                if hasattr(self, 'stop_button'):
                    self.stop_button.config(state='disabled')
                if hasattr(self, 'clear_button'):
                    self.clear_button.config(state='normal')
            elif state == 'downloading':
                if hasattr(self, 'start_button'):
                    self.start_button.config(state='disabled')
                if hasattr(self, 'pause_button'):
                    self.pause_button.config(state='normal')
                if hasattr(self, 'stop_button'):
                    self.stop_button.config(state='normal')
                if hasattr(self, 'clear_button'):
                    self.clear_button.config(state='disabled')
            elif state == 'paused':
                if hasattr(self, 'start_button'):
                    self.start_button.config(state='normal', text='再開')
                if hasattr(self, 'pause_button'):
                    self.pause_button.config(state='disabled')
                if hasattr(self, 'stop_button'):
                    self.stop_button.config(state='normal')
                if hasattr(self, 'clear_button'):
                    self.clear_button.config(state='disabled')
            elif state == 'error':
                # エラー時はリスタート可能な状態
                if hasattr(self, 'start_button'):
                    self.start_button.config(state='normal', text='リスタート')
                if hasattr(self, 'pause_button'):
                    self.pause_button.config(state='disabled')
                if hasattr(self, 'stop_button'):
                    self.stop_button.config(state='normal')
                if hasattr(self, 'clear_button'):
                    self.clear_button.config(state='normal')
            elif state == 'completed':
                if hasattr(self, 'start_button'):
                    self.start_button.config(state='normal', text='ダウンロード')
                if hasattr(self, 'pause_button'):
                    self.pause_button.config(state='disabled')
                if hasattr(self, 'stop_button'):
                    self.stop_button.config(state='disabled')
                if hasattr(self, 'clear_button'):
                    self.clear_button.config(state='normal')
            
            # ⭐追加: ダウンロードマネージャーのボタン状態も更新⭐
            if hasattr(self, 'progress_panel') and hasattr(self.progress_panel, 'progress_manager'):
                progress_manager = self.progress_panel.progress_manager
                if progress_manager and progress_manager.separate_view:
                    progress_manager.separate_view.update_button_states(state)
        except Exception as e:
            self.log(f"ボタン状態更新エラー: {e}", "error")
        
        # バックアップマネージャーを初期化
        from core.managers.backup_manager import DownloadBackupManager
        self.backup_manager = DownloadBackupManager(self)
        
        # settings_backup_managerは__init__内で初期化済み
        
        # 設定ファイル保存場所の初期化
        # カスタムディレクトリ機能を削除
        
        # 起動時のログ
        try:
            from app_info import STARTUP_MESSAGE
            self.log(STARTUP_MESSAGE, "info")
        except ImportError:
            from app_info import STARTUP_MESSAGE
            self.log(STARTUP_MESSAGE, "info")
        
        # 設定読み込みは__init__内で実行済み
        
        # 起動時にGUI状態を更新
        self.root.after(100, self._update_gui_state_from_thread)
        
        # ⭐起動時にGUIとオプション値を強制同期⭐
        self.root.after(200, self._sync_gui_with_internal_state)
        
        # 起動時の設定自動読み込みは不要（load_settings_and_stateで完了済み）
    
    def _initialize_tkinter_variables(self) -> None:
        """Tkinter変数を初期化"""
        import os
        # ⭐folder_varは空で初期化（load_settings_and_stateで設定される）⭐
        self.folder_var = tk.StringVar(value="")
        
        # ⭐プロフェッショナル設計: OptionsManagerで全オプションを一元管理⭐
        self.options_manager = OptionsManager(self)
        # ⭐注: setup_auto_sync()はload_settings_and_state()の後に呼び出す⭐
        self.window_state = tk.StringVar(value="normal")
        self.wait_time = tk.StringVar(value="0.5")
        self.sleep_value = tk.StringVar(value="0.5")
        self.save_format = tk.StringVar(value="Original")
        self.save_name = tk.StringVar(value="Original")
        self.custom_name = tk.StringVar(value="{artist}_{title}_{page}")
        self.resize_enabled = tk.StringVar(value="off")
        self.resize_mode = tk.StringVar(value="縦幅上限")
        
        # エラー処理モード
        self.initial_error_mode = tk.StringVar(value="manual")
        # ⭐実用的な設計: シンプルな自動エラーハンドリング⭐
        self.smart_error_handling = tk.BooleanVar(value=True)  # デフォルトON
        self.circuit_breaker_threshold = tk.IntVar(value=5)  # 5回連続エラーで自動停止
        self.selenium_mode = tk.StringVar(value="session")  # 1ギャラリー有効
        
        # ⭐旧設定との互換性維持⭐
        self.error_handling_mode = tk.StringVar(value="auto_resume")
        self.error_handling_enabled = tk.BooleanVar(value=True)  # エラー処理のON/OFF
        self.auto_resume_enabled = tk.BooleanVar(value=True)  # 自動再開オプションの有効/無効
        # 個別のリサイズ変数は削除（resize_values辞書を使用）
        self.interpolation_mode = tk.StringVar(value="三次補完（画質優先）")
        self.sharpness_value = tk.StringVar(value="1.5")
        self.keep_original = tk.BooleanVar(value=True)
        self.keep_unresized = tk.BooleanVar(value=False)
        self.resize_quality = tk.StringVar(value="85")
        self.resize_filename_enabled = tk.BooleanVar(value=False)
        self.resized_subdir_name = tk.StringVar(value="resized")
        self.resized_prefix = tk.StringVar(value="")
        self.resized_suffix = tk.StringVar(value="_resized")
        self.resize_save_location = tk.StringVar(value="child")
        self.duplicate_folder_mode = tk.StringVar(value="rename")
        self.rename_incomplete_folder = tk.BooleanVar(value=False)
        self.incomplete_folder_prefix = tk.StringVar(value="[INCOMPLETE]_")
        self.compression_enabled = tk.StringVar(value="off")
        self.compression_format = tk.StringVar(value="ZIP")
        self.compression_delete_original = tk.BooleanVar(value=False)
        self.auto_resume_delay = tk.StringVar(value="5")
        self.retry_delay_increment = tk.StringVar(value="10")
        self.max_retry_delay = tk.StringVar(value="60")
        self.max_retry_count = tk.StringVar(value="3")
        self.retry_limit_action = tk.StringVar(value="selenium_retry")
        self.selenium_scope = tk.StringVar(value="1")
        self.selenium_failure_action = tk.StringVar(value="manual_resume")
        self.first_page_use_title = tk.BooleanVar(value=False)
        self.multithread_enabled = tk.StringVar(value="off")
        self.multithread_count = tk.IntVar(value=3)
        self.preserve_animation = tk.BooleanVar(value=True)
        self.folder_name_mode = tk.StringVar(value="h1_priority")
        self.custom_folder_name = tk.StringVar(value="{artist}_{title}")
        self.first_page_naming_enabled = tk.BooleanVar(value=False)
        self.first_page_naming_format = tk.StringVar(value="title")
        
        # 統合エラー処理オプション
        self.integrated_error_handling_enabled = tk.BooleanVar(value=False)
        self.wait_for_auto_recovery = tk.BooleanVar(value=True)
        self.resume_option = tk.StringVar(value="auto_resume_with_countermeasures")
        self.lower_security_level = tk.BooleanVar(value=False)
        self.skip_certificate_verify = tk.BooleanVar(value=False)
        self.use_custom_ssl = tk.BooleanVar(value=False)
        self.use_proxy = tk.BooleanVar(value=False)
        self.change_dns_server = tk.BooleanVar(value=False)
        self.spoof_user_agent = tk.BooleanVar(value=False)
        self.extend_connection_timeout = tk.BooleanVar(value=False)
        self.custom_ssl_config = tk.StringVar(value="")
        self.proxy_config = tk.StringVar(value="")
        self.dns_server = tk.StringVar(value="8.8.8.8")
        self.user_agent = tk.StringVar(value="Mozilla/5.0")
        
        # 常時SSL設定オプション
        self.always_ssl_security_level = tk.BooleanVar(value=False)  # 常時SSLセキュリティレベル1
        
        # プロキシ設定詳細
        self.proxy_usage_mode = tk.StringVar(value="error_retry_only")  # プロキシ使用モード
        self.proxy_server = tk.StringVar(value="")
        self.proxy_port = tk.StringVar(value="8080")
        self.proxy_username = tk.StringVar(value="")
        self.proxy_password = tk.StringVar(value="")
        
        # カスタムSSL設定詳細
        self.custom_ssl_config_file = tk.StringVar(value="")
        self.duplicate_file_mode = tk.StringVar(value="overwrite")
        self.skip_count = tk.StringVar(value="10")
        self.skip_after_count_enabled = tk.BooleanVar(value=False)
        self.jpg_quality = tk.IntVar(value=85)
        self.string_conversion_enabled = tk.BooleanVar(value=False)
        self.advanced_options_enabled = tk.BooleanVar(value=True)
        self.user_agent_spoofing_enabled = tk.BooleanVar(value=False)
        self.httpx_enabled = tk.BooleanVar(value=False)
        # ⭐重要: selenium_enabledはここのみで定義⭐
        self.selenium_enabled = tk.BooleanVar(value=False)
        self.selenium_session_retry_enabled = tk.BooleanVar(value=False)
        self.selenium_persistent_enabled = tk.BooleanVar(value=False)
        self.thumbnail_display_enabled = tk.StringVar(value="off")
        self.selenium_page_retry_enabled = tk.BooleanVar(value=False)
        self.selenium_mode = tk.StringVar(value="session")  # Seleniumリトライモード
        self.progress_separate_window_enabled = tk.BooleanVar(value=False)  # プログレスバーの別ウィンドウ表示
        
        # 軽度エラーウェイト設定は削除されました（シンプル化のため）
        
        # ダウンロード範囲オプション
        self.download_range_enabled = tk.BooleanVar(value=False)  # ダウンロード範囲オプション
        self.download_range_mode = tk.StringVar(value="1行目のURLのみ")  # ダウンロード範囲モード
        self.download_range_start = tk.StringVar(value="")  # 開始ページ
        self.download_range_end = tk.StringVar(value="")  # 終了ページ（空文字は最後まで）
        self.error_handling_enabled = tk.BooleanVar(value=True)  # エラー処理の有効/無効
        
        # プログレスバー表示制限オプション
        self.progress_display_limit_enabled = tk.BooleanVar(value=True)
        self.progress_retention_count = tk.StringVar(value="100")
        
        # プログレスバーログ保存オプション
        self.progress_backup_enabled = tk.BooleanVar(value=False)
        self.gallery_info_backup = tk.BooleanVar(value=True)
        self.backup_file_format = tk.StringVar(value="HTML")
        
        # DLログ保存オプション
        self.dl_log_enabled = tk.BooleanVar(value=False)
        self.dl_log_method = tk.StringVar(value="individual")
        
        # 統合エラー処理関連の変数
        self.integrated_error_handling_enabled = tk.BooleanVar(value=False)
        self.wait_for_auto_recovery = tk.BooleanVar(value=True)
        self.resume_option = tk.StringVar(value="auto_resume_with_countermeasures")
        self.lower_security_level = tk.BooleanVar(value=False)
        self.skip_certificate_verify = tk.BooleanVar(value=False)
        self.use_custom_ssl = tk.BooleanVar(value=False)
        self.use_proxy = tk.BooleanVar(value=False)
        
        # プログレスバー表示用の総ページ数
        self.current_total_pages = 0
        self.last_progress_total = 0  # 前回の総ページ数を保持
        
        # ダウンロード情報保存オプション
        self.dl_log_individual_save = tk.BooleanVar(value=False)
        self.dl_log_batch_save = tk.BooleanVar(value=False)
        self.dl_log_file_format = tk.StringVar(value="HTML")
        
        # 強化されたエラーハンドリング設定
        self.enhanced_error_handling_enabled = tk.BooleanVar(value=True)
        self.enhanced_error_mode = tk.StringVar(value="auto_resume")
        self.retry_strategy = tk.StringVar(value="linear")
        self.enhanced_max_retry_count = tk.StringVar(value="3")
        self.enhanced_retry_delay = tk.StringVar(value="5")
        self.enhanced_max_delay = tk.StringVar(value="300")
        self.enhanced_resume_age_hours = tk.StringVar(value="24")
        
        # ⭐修正: Seleniumオプションを明確に分離⭐
        self.selenium_always_enabled = tk.BooleanVar(value=False)  # 常時Selenium使用（全ページで使用）
        self.selenium_fallback_enabled = tk.BooleanVar(value=False)  # エラー時Selenium自動適用（リトライ上限後）
        self.selenium_use_for_page_info = tk.BooleanVar(value=False)  # ページ情報取得にもSeleniumを使う
        self.selenium_timeout = tk.StringVar(value="60")
        self.retry_limit_action = tk.StringVar(value="pause")
        
        # Seleniumオプション設定
        self.selenium_options_enabled = tk.BooleanVar(value=True)  # 既定値: ON
        self.selenium_minimal_options = tk.BooleanVar(value=True)   # 既定値: ON
        self.selenium_manager_enabled = tk.BooleanVar(value=False)
        self.selenium_stop_chrome_background = tk.BooleanVar(value=False)
        self.selenium_custom_paths_enabled = tk.BooleanVar(value=False)
        self.selenium_driver_path = tk.StringVar(value="")
        self.selenium_chrome_path = tk.StringVar(value="")
        self.selenium_cleanup_temp = tk.BooleanVar(value=False)
        self.selenium_use_registry_version = tk.BooleanVar(value=True)
        self.selenium_minimal_options = tk.BooleanVar(value=False)
        
        # Seleniumテストモード設定
        self.selenium_test_minimal_options = tk.BooleanVar(value=False)
        self.selenium_test_no_headless = tk.BooleanVar(value=False)
        
        # 設定ファイル保存場所
        # カスタムディレクトリ機能を削除
        
        # resize_values辞書（各値はtkinter StringVar）
        self.resize_values = {
            'height': tk.StringVar(value="1024"),
            'width': tk.StringVar(value="1024"),
            'short': tk.StringVar(value="1024"),
            'long': tk.StringVar(value="1024"),
            'percentage': tk.StringVar(value="80"),
            'unified': tk.StringVar(value="1600")
        }
        
        # 文字列変換ルール
        self.string_conversion_rules = []
        
        # クッキー
        self.cookies_var = tk.StringVar()
        
        # タグ変数設定（デフォルト値: 半角スペース、チェックON）
        self.tag_delimiter = " "
        self.tag_max_length = 0
        self.use_space_in_delimiter = True
        
        # URLリストとログ
        self.url_list_content = ""
        self.log_content = ""
    
    def _create_gui(self) -> None:
        """GUIを作成"""
        # メインパネル（tk.PanedWindowを使用してスプリットバーを確実に表示）
        self.main_v_pane = tk.PanedWindow(self.root, orient="vertical", sashwidth=3, sashrelief="raised")
        self.main_v_pane.pack(fill="both", expand=True, padx=5, pady=(5, 0))
        
        # ⭐追加: フッター（ステータスバー）⭐
        self.footer_frame = tk.Frame(self.root, relief=tk.SUNKEN, borderwidth=1)
        self.footer_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))
        
        # 左側: DL進捗
        self.footer_progress_label = tk.Label(
            self.footer_frame, 
            text="DL進捗: 0/0 (0%)", 
            anchor=tk.W,
            padx=10
        )
        self.footer_progress_label.pack(side=tk.LEFT)
        
        # 右側: 経過時間
        self.footer_elapsed_label = tk.Label(
            self.footer_frame, 
            text="経過時間: 00:00", 
            anchor=tk.E,
            padx=10
        )
        self.footer_elapsed_label.pack(side=tk.RIGHT)
        
        # 上部水平パネル
        self.top_h_pane = tk.PanedWindow(self.main_v_pane, orient="horizontal", sashwidth=3, sashrelief="raised")
        self.main_v_pane.add(self.top_h_pane, height=800)  # DLリストとオプションパネルの表示エリアを300px増加
        
        # ⭐修正: DLリストの初期幅を60%に設定（after()で遅延実行）⭐
        def set_initial_pane_widths() -> None:
            try:
                # ⭐修正: ウィンドウが完全に表示されるまで待機⭐
                self.root.update_idletasks()
                
                # ウィンドウ全体の幅を取得
                total_width = self.root.winfo_width()
                
                # ⭐修正: 幅が1px以下の場合は再試行⭐
                if total_width <= 1:
                    self.log(f"[DEBUG] ウィンドウ幅が不正（{total_width}px）、500ms後に再試行", "info")
                    self.root.after(500, set_initial_pane_widths)
                    return
                
                # DLリストの幅を60%に設定
                dl_list_width = int(total_width * 0.6)
                self.top_h_pane.sash_place(0, dl_list_width, 0)
                self.log(f"[DEBUG] パネル初期幅設定: 全体={total_width}px, DLリスト={dl_list_width}px (60%)", "info")
            except Exception as e:
                self.log(f"パネル初期幅設定エラー: {e}", "warning")
        
        # 500ms後に初期幅を設定（ウィンドウが完全に表示されてから）
        self.root.after(500, set_initial_pane_widths)
        
        # 左側パネル（URL入力）
        self.left_pane = tk.PanedWindow(self.top_h_pane, orient="vertical", sashwidth=3, sashrelief="raised")
        self.top_h_pane.add(self.left_pane)
        
        # 右側パネル（オプション）
        self.right_pane = tk.PanedWindow(self.top_h_pane, orient="vertical", sashwidth=3, sashrelief="raised")
        self.top_h_pane.add(self.right_pane)
        
        # 下部パネル（ログ）
        self.bottom_pane = tk.PanedWindow(self.main_v_pane, orient="vertical", sashwidth=3, sashrelief="raised")
        self.main_v_pane.add(self.bottom_pane)
    
    def _initialize_components(self) -> None:
        """コンポーネントを初期化"""
        # URLパネル
        self.url_panel = EHDownloaderUrlPanel(self)
        self.url_panel.create_url_panel(self.left_pane)
        self.url_text = self.url_panel.url_text
        
        # ⭐フェーズ2: Treeview統合（並行表示）⭐
        # URL正規化関数
        def normalize_url(url: str) -> str:
            """URLを正規化（末尾スラッシュ統一、クエリパラメータ除去）"""
            url = url.strip()
            # クエリパラメータを除去
            if '?' in url:
                url = url.split('?')[0]
            # 末尾スラッシュを統一
            return url.rstrip('/') + '/'
        
        # DownloadListWidgetを初期化
        self.download_list_widget = DownloadListWidget(self.left_pane, normalize_url)
        self.download_list_widget.view.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        # ⭐追加: StateManagerにDownloadListControllerを設定（DLリスト背景色更新用）⭐
        if hasattr(self, 'state_manager') and hasattr(self.download_list_widget, 'controller'):
            self.state_manager.download_list_controller = self.download_list_widget.controller
        
        # ⭐Phase 1: ThreadSafeUIBridgeを初期化・設定（段階的改善）⭐
        from core.communication.ui_bridge import ThreadSafeUIBridge
        self.ui_bridge = ThreadSafeUIBridge(self.root)
        self.download_list_widget.view.ui_bridge = self.ui_bridge
        
        # ⭐追加: parent_windowを設定（launch_parserボタン用）⭐
        self.download_list_widget.view.parent_window = self
        
        # プログレスパネル
        self.progress_panel = EHDownloaderProgressPanel(self)
        
        # ⭐Phase 1.5: ProgressPanelにui_bridgeを設定⭐
        self.progress_panel.ui_bridge = self.ui_bridge
        self.progress_panel.create_log_panel(self.bottom_pane)
        self.log_text = self.progress_panel.log_text
        
        # オプションパネル
        self.options_panel = EHDownloaderOptionsPanel(self)
        
        # ⭐Phase 1.5: OptionsPanelにui_bridgeを設定⭐
        self.options_panel.ui_bridge = self.ui_bridge
        
        self.options_panel.create_options_panel(self.right_pane)
        
        # ⭐修正: StateManagerインスタンスを統一（downloader_coreと共有）⭐
        # ダウンローダーコア（StateManagerを共有）
        self.downloader_core = EHDownloaderCore(self, self.state_manager)
        print("[MAIN_WINDOW] EHDownloaderCore生成完了")
        
        # ⭐追加: StateManagerの状態変更リスナーを設定（downloader_core初期化後）⭐
        if hasattr(self.progress_panel, '_setup_state_listeners'):
            self.progress_panel._setup_state_listeners()
        print("[MAIN_WINDOW] ProgressPanel state listeners設定完了")
        
        # ⭐修正: StateManagerのオブザーバー登録（downloader_core初期化後）⭐
        if hasattr(self.progress_panel, '_setup_state_manager_observer'):
            self.progress_panel._setup_state_manager_observer()
        print("[MAIN_WINDOW] ProgressPanel StateManager observer設定完了")
        
        # URLユーティリティ
        from utils.url_utils import EHDownloaderUrlUtils
        self.url_utils = EHDownloaderUrlUtils(self)
        self.url_utils.url_text = self.url_text
        self.url_utils.log = self.log_text
        print("[MAIN_WINDOW] URL utils初期化完了")
        
        # ウィンドウクローズハンドラを設定
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        print("[MAIN_WINDOW] Window close handler設定完了")
        
        # ウィンドウ状態変更の監視
        self.root.bind("<Map>", self._on_window_map)
        self.root.bind("<Unmap>", self._on_window_unmap)
        self.root.bind("<Configure>", self._on_window_configure)
        print("[MAIN_WINDOW] Window bindings設定完了")
        
        # ⭐削除: プログレスバー復元機能を削除⭐
        # self.root.after(500, self._restore_progress_bars_on_startup)
        print("[MAIN_WINDOW] ========== _initialize_components完了 ==========")
    
    def _on_window_map(self, event: Event) -> None:
        """ウィンドウが表示されたときの処理"""
        try:
            current_state = self.root.state()
            if current_state != self.window_state.get():
                self.window_state.set(current_state)
        except Exception as e:
            pass  # エラーは無視
    
    def _on_window_unmap(self, event: Event) -> None:
        """ウィンドウが非表示になったときの処理"""
        try:
            current_state = self.root.state()
            if current_state != self.window_state.get():
                self.window_state.set(current_state)
        except Exception as e:
            pass  # エラーは無視
    
    def _on_window_configure(self, event: Event) -> None:
        """ウィンドウサイズ・位置変更時の処理"""
        try:
            # ウィンドウ自体のサイズ変更のみを対象とする
            if event.widget == self.root:
                # デバウンス処理（連続する変更を抑制）
                if hasattr(self, '_configure_timer'):
                    self.root.after_cancel(self._configure_timer)
                
                self._configure_timer = self.root.after(1000, self._save_window_geometry)
        except Exception as e:
            self.log(f"ウィンドウ設定変更処理エラー: {e}", "error")
    
    def _save_window_geometry(self) -> None:
        """ウィンドウのサイズ・位置を保存"""
        try:
            # 設定保存を削除（ウィンドウクローズ時のみ保存するため）
            # self.save_settings_and_state()  # 削除
            pass  # 何もしない
        except Exception as e:
            self.log(f"ウィンドウ設定保存エラー: {e}", "error")
    
    # ⭐削除: プログレスバー復元メソッドを削除⭐
    # プログレスバー情報は外部ファイルに保存しないため、復元も不要
    # def _restore_progress_bars_on_startup(self): ...
    
    def update_footer_progress(self, completed: int, total: int) -> None:
        """フッターのDL進捗を更新"""
        try:
            if hasattr(self, 'footer_progress_label'):
                percentage = int((completed / total * 100)) if total > 0 else 0
                self.footer_progress_label.config(text=f"DL進捗: {completed}/{total} ({percentage}%)")
        except Exception as e:
            pass  # エラーは無視
    
    def update_footer_elapsed_time(self, elapsed_seconds: float) -> None:
        """フッターの経過時間を更新"""
        try:
            if hasattr(self, 'footer_elapsed_label'):
                minutes = int(elapsed_seconds // 60)
                seconds = int(elapsed_seconds % 60)
                self.footer_elapsed_label.config(text=f"経過時間: {minutes:02d}:{seconds:02d}")
        except Exception as e:
            pass  # エラーは無視
    
    def log(self, message: str, level: str = "info", to_file_only: bool = False) -> None:
        """ログを出力"""
        if hasattr(self, 'log_text') and self.log_text:
            # ログテキストを一時的に編集可能にする
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} [{level.upper()}] {message}\n")
            self.log_text.see(tk.END)
            # ログテキストを再び編集不可にする
            self.log_text.config(state='disabled')
        
    def start_download_sequence(self) -> None:
        """ダウンロードシーケンスを開始（Controllerに委譲）"""
        self.download_controller.start_download_sequence()
            

    
    # ⭐削除: 重複メソッドを削除（_update_gui_for_*に統合）⭐
    
    def _parse_urls_from_text(self, text: str) -> List[str]:
        """テキストからURLをパースする"""
        urls = []
        
        for line in text.splitlines():
            line = line.strip()
            
            # @マークやマーカーを除去
            line = re.sub(r'^@', '', line)
            line = re.sub(r'\u200B?\(リサイズ完了\)', '', line)
            line = re.sub(r'\u200B?（圧縮完了）', '', line)
            
            if line and self._is_valid_eh_url(line):
                # 個別画像ページURLの場合は正規化せずにそのまま渡す
                if re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', line):
                    urls.append(line)  # 個別画像ページURLはそのまま
                else:
                    normalized = self.normalize_url(line)
                    if normalized:
                        urls.append(normalized)
        
        return urls


    def pause_download(self) -> None:
        """ダウンロードを中断（download_controllerに委譲）"""
        if hasattr(self, 'download_controller'):
            self.download_controller.pause_download()
            # ⭐追加: ボタン状態を更新⭐
            self._update_button_states_unified('paused')
        else:
            self.log("中断機能が利用できません", "warning")
    
    def resume_download(self) -> None:
        """ダウンロードを再開"""
        # 連打防止: 再開処理中は無効化
        if hasattr(self, '_resume_processing') and self._resume_processing:
            self.log("再開処理中です。しばらくお待ちください。", "warning")
            return
        
        self._resume_processing = True
        
        try:
            # ダウンロード再開処理
            
            # オプションを読み込み
            self._load_options_for_download()
            
            # エラー状態からの再開も可能にする
            is_running = self.downloader_core.state_manager.is_download_running() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            is_paused = self.downloader_core.state_manager.is_paused() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            if (is_running and is_paused) or (not is_running and is_paused):
                # エラー状態からの再開の場合は、is_runningをTrueに設定
                if not is_running and is_paused:
                    if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                        self.downloader_core.state_manager.set_download_running(True)
                
                # ダウンロードを実際に再開（pausedフラグをクリアする前に実行）
                if hasattr(self, 'downloader_core'):
                    # downloader_coreの存在確認
                    
                    # downloader_coreのpausedフラグを確認・設定
                    if hasattr(self.downloader_core, 'paused'):
                        # downloader_coreのpausedフラグを確認
                        if not self.downloader_core.paused:
                            self.downloader_core.paused = True
                            # downloader_coreのpausedフラグを設定
                    
                    # 中断されたダウンロードを再開（復帰ポイントを使用）
                    if hasattr(self.downloader_core, 'resume_download'):
                        # downloader_coreのresume_downloadを呼び出し
                        try:
                            self.downloader_core.resume_download()
                            self.log("中断されたダウンロードを再開しました")
                        except Exception as e:
                            self.log(f"ダウンロード再開エラー: {e}", "error")
                            import traceback
                            self.log(f"エラー詳細: {traceback.format_exc()}", "error")
                    else:
                        self.log("再開機能が利用できません", "error")
                else:
                    self.log("ダウンローダーが初期化されていません", "error")
                
                # ⭐修正: pausedフラグのクリアをコメントアウト⭐
                # resume_download()内でpausedフラグをチェックしているため、
                # 呼び出し前にクリアすると再開処理がスキップされる
                # resume_download()内で既にクリアされているため、ここでは不要
                # if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                #     self.downloader_core.state_manager.set_paused(False)
                
                # ⭐追加: 中断時間を累積（再開時に中断時間を記録）⭐
                if hasattr(self, 'progress_panel'):
                    import time
                    if hasattr(self.progress_panel, 'download_pause_start_time') and self.progress_panel.download_pause_start_time:
                        pause_duration = time.time() - self.progress_panel.download_pause_start_time
                        if not hasattr(self.progress_panel, 'total_paused_time'):
                            self.progress_panel.total_paused_time = 0
                        self.progress_panel.total_paused_time += pause_duration
                        self.progress_panel.download_pause_start_time = None  # リセット
                
                # 中断要求フラグをクリア
                if hasattr(self, 'downloader_core'):
                    self.downloader_core.pause_requested = False
                    # 完了チェックスキップフラグもクリア
                    if hasattr(self.downloader_core, 'skip_completion_check'):
                        self.downloader_core.skip_completion_check = False
                    # その他のフラグもクリア
                    if hasattr(self.downloader_core, 'restart_requested'):
                        self.downloader_core.restart_requested = False
                    if hasattr(self.downloader_core, 'restart_url'):
                        self.downloader_core.restart_url = None
                    # エラーフラグもクリア（再開時はエラー状態をリセット）
                    if hasattr(self.downloader_core, 'error_occurred'):
                        self.downloader_core.error_occurred = False
                
                # StateManagerにも状態を反映
                if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                    self.downloader_core.state_manager.set_download_running(True)
                    self.downloader_core.state_manager.set_paused(False)
                    
                    # 現在のURLの状態をdownloadingに戻す
                    if hasattr(self.downloader_core, 'current_gallery_url') and self.downloader_core.current_gallery_url:
                        self.downloader_core.state_manager.set_url_status(self.downloader_core.current_gallery_url, 'downloading')
                    
                    # StateManagerを再開状態に設定
                
                # GUIを更新（StateManagerの状態を同期しないように直接更新）
                self._update_gui_for_running()
                
                # URL背景色を更新（現在のURLのみ）
                if hasattr(self, 'url_panel') and hasattr(self.downloader_core, 'current_gallery_url') and self.downloader_core.current_gallery_url:
                    self.url_panel.update_url_background(self.downloader_core.current_gallery_url)
                
                self.log("ダウンロードを再開しました", "info")
                
                # ⭐追加: ボタン状態を更新⭐
                self._update_button_states_unified('downloading')
                
                # ボタン状態は_update_gui_state_from_thread()内で更新される
                # 明示的にGUI状態を更新
                self.root.after(0, self._update_gui_state_from_thread)
            else:
                # 再開条件が満たされていません
                pass
        finally:
            # 再開処理完了フラグをクリア（少し遅延）
            def clear_resume_flag() -> None:
                import time  # ⭐修正: timeモジュールをインポート⭐
                time.sleep(0.5)  # 0.5秒後にフラグをクリア
                self._resume_processing = False
            threading.Thread(target=clear_resume_flag, daemon=True).start()


    def stop_download(self) -> None:
        """ダウンロードを停止（Controllerに委譲）"""
        self.download_controller.stop_download()


    def resume_from_pause_or_error(self) -> None:
        """一時停止またはエラー状態から再開"""
        is_running = self.downloader_core.state_manager.is_download_running()
        is_paused = self.downloader_core.state_manager.is_paused()
        
        if is_running and not is_paused:
            # 実行中（中断状態でない）
            self._update_gui_for_running()
        elif is_paused:
            # 中断中
            self._update_gui_for_paused()
        else:
            # アイドル状態
            self._update_gui_for_idle()


    def skip_current_download(self) -> None:
        """現在のURLをスキップ（手動スキップ専用メソッドを使用）"""
        # 連打防止: スキップ処理中は無効化
        if hasattr(self, '_skip_processing') and self._skip_processing:
            self.log("スキップ処理中です。しばらくお待ちください。", "warning")
            return
        
        self._skip_processing = True
        
        try:
            is_running = self.downloader_core.state_manager.is_download_running() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            if not is_running:
                self.log("ダウンロードは実行中ではありません", "warning")
                return

            # 手動スキップ専用メソッドを呼び出し
            success = self.download_controller.skip_current_download_manual()
            if success:
                self.log("現在のURLをスキップしました", "info")
            else:
                self.log("スキップ処理に失敗しました", "error")
                
        finally:
            # スキップ処理完了フラグをクリア（少し遅延）
            def clear_skip_flag() -> None:
                time.sleep(0.5)  # 0.5秒後にフラグをクリア
                self._skip_processing = False
            threading.Thread(target=clear_skip_flag, daemon=True).start()

    def _handle_drop(self, event: Any) -> None:
        """ドラッグ&ドロップ処理（URLファイル、バックアップフォルダ対応）"""
        try:
            # Windowsのドラッグ&ドロップ形式を処理
            files = []
            
            # 方法1: 波括弧で囲まれたパスを処理
            if '{' in event.data and '}' in event.data:
                import re
                # 波括弧で囲まれたパスを抽出
                pattern = r'\{([^}]+)\}'
                matches = re.findall(pattern, event.data)
                files.extend(matches)
            
            # 方法2: クォートで囲まれたパスを処理
            if '"' in event.data:
                import re
                # クォートで囲まれたパスを抽出
                pattern = r'"([^"]+)"'
                quoted_matches = re.findall(pattern, event.data)
                files.extend(quoted_matches)
            
            # 方法3: 単純なスペース分割（フォールバック）
            if not files:
                # スペースで分割する前に、既存のファイルパスをチェック
                potential_files = event.data.split()
                for potential_file in potential_files:
                    # ファイルまたはフォルダが存在するかチェック
                    if os.path.exists(potential_file):
                        files.append(potential_file)
                    else:
                        # 存在しない場合は、前のパスと結合してチェック
                        if files:
                            combined_path = files[-1] + ' ' + potential_file
                            if os.path.exists(combined_path):
                                files[-1] = combined_path
                            else:
                                files.append(potential_file)
                        else:
                            files.append(potential_file)
            
            # 重複を除去
            files = list(dict.fromkeys(files))
            
            for file_path in files:
                # ファイルパスをクリーンアップ
                file_path = file_path.strip('{}"')
                
                # バックアップフォルダかチェック
                if os.path.isdir(file_path):
                    # バックアップフォルダの可能性をチェック
                    resume_point_file = os.path.join(file_path, "resume_points.json")
                    url_list_file = os.path.join(file_path, "url_list.txt")
                    
                    if os.path.exists(resume_point_file) or os.path.exists(url_list_file):
                        # バックアップフォルダとして復元
                        from tkinter import messagebox
                        response = messagebox.askyesno(
                            "バックアップフォルダ検出",
                            f"バックアップフォルダが検出されました:\n{file_path}\n\nバックアップから復元しますか？"
                        )
                        if response:
                            self._restore_backup_from_path(file_path)
                    else:
                        self.log(f"バックアップフォルダではありません: {file_path}", "warning")
                
                elif os.path.isfile(file_path):
                    # ファイルの内容を読み込んでURLリストに追加
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if self.url_text.get("1.0", tk.END).strip():
                                self.url_text.insert(tk.END, "\n")
                            self.url_text.insert(tk.END, content)
                        self.log(f"ドラッグ&ドロップ: URLファイルを追加しました", "info")
                    except Exception as e:
                        self.log(f"ファイル読み込みエラー: {e}", "error")
                else:
                    self.log(f"ファイルまたはフォルダが見つかりません: {file_path}", "error")
        except Exception as e:
            self.log(f"ドラッグ&ドロップエラー: {e}", "error")
    def _restore_backup_from_path(self, backup_path: str) -> None:
        """指定されたパスからバックアップを復元 - Controllerに委譲"""
        self.backup_controller.restore_backup_from_path(backup_path)


    def restore_from_backup(self, backup_path: str) -> None:
        """バックアップから状態を復元"""
        try:
            # 実行中なら停止
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'stop_flag'):
                self.downloader_core.stop_flag.set()

            settings_backup = os.path.join(backup_path, "settings.json")
            url_list_backup = os.path.join(backup_path, "url_list.txt")
            current_log_backup = os.path.join(backup_path, "current_log.txt")
            resume_point_backup = os.path.join(backup_path, "resume_points.json")

            restored_files = []

            # 1. 設定ファイルを復元
            if os.path.exists(settings_backup):
                try:
                    self._load_settings_from_file(settings_backup)
                    restored_files.append("設定ファイル")
                except Exception as e:
                    self.log(f"設定ファイルの復元に失敗: {e}", "warning")

            # 2. URLリストを復元
            if os.path.exists(url_list_backup):
                try:
                    with open(url_list_backup, 'r', encoding='utf-8') as f:
                        url_content = f.read()

                    self.url_text.delete("1.0", tk.END)
                    if url_content.strip():
                        self.url_text.insert("1.0", url_content)

                    restored_files.append("URLリスト")
                except Exception as e:
                    self.log(f"URLリストの復元に失敗: {e}", "warning")

            # 3. ログファイルを復元
            if os.path.exists(current_log_backup):
                try:
                    with open(current_log_backup, 'r', encoding='utf-8') as f:
                        log_content = f.read()

                    self.log_text.config(state='normal')
                    self.log_text.delete("1.0", tk.END)
                    self.log_text.insert("1.0", log_content)
                    self.log_text.config(state='disabled')

                    restored_files.append("ログファイル")
                except Exception as e:
                    self.log(f"ログファイルの復元に失敗: {e}", "warning")

            # 4. 再開ポイント・状態を復元
            if os.path.exists(resume_point_backup):
                try:
                    with open(resume_point_backup, 'r', encoding='utf-8') as f:
                        state_data = json.load(f)

                    download_state = state_data.get("download_state", {})
                    was_running = download_state.get("is_running", False)
                    was_paused = download_state.get("paused", False)

                    if was_running or was_paused:
                        if hasattr(self.downloader_core, "state_manager"):
                            self.downloader_core.state_manager.set_download_running(False)
                            self.downloader_core.state_manager.set_paused(True)
                        self.log("バックアップ: ダウンロードは中断状態として復元されました", "info")

                    self.url_status = download_state.get("url_status", {})
                    self.current_url_index = download_state.get("current_url_index", 0)

                    if hasattr(self, "downloader_core"):
                        if "resume_points" in state_data:
                            self.resume_points = state_data["resume_points"]
                            if self.resume_points:
                                _, resume_data = next(iter(self.resume_points.items()))
                                self.downloader_core.resume_point = resume_data

                        if "managed_folders" in state_data:
                            self.downloader_core.managed_folders = state_data["managed_folders"]

                        if "incomplete_urls" in state_data:
                            self.downloader_core.incomplete_urls = set(state_data["incomplete_urls"])

                        if "completion_state" in state_data:
                            cs = state_data["completion_state"]
                            self.downloader_core._sequence_complete_executed = cs.get("sequence_complete_executed", False)
                            self.downloader_core.current_gallery_url = cs.get("current_gallery_url")
                            self.downloader_core.current_image_page_url = cs.get("current_image_page_url")
                            self.downloader_core.current_save_folder = cs.get("current_save_folder")
                            self.downloader_core.current_page = cs.get("current_page", 0)
                            self.downloader_core.current_total = cs.get("current_total", 0)
                            self.downloader_core.error_occurred = cs.get("error_occurred", False)
                            self.downloader_core.gallery_completed = cs.get("gallery_completed", False)
                            self.downloader_core.skip_completion_check = cs.get("skip_completion_check", False)
                            self.downloader_core._flags_restored_from_backup = True

                        if "selenium_state" in state_data:
                            ss = state_data["selenium_state"]
                            self.downloader_core.selenium_enabled_for_retry = ss.get("enabled_for_retry", False)
                            self.downloader_core.selenium_scope = ss.get("scope", "page")
                            self.downloader_core.selenium_enabled_url = ss.get("enabled_url")

                        if "compression_state" in state_data:
                            cps = state_data["compression_state"]
                            self.downloader_core._compression_in_progress = cps.get("in_progress", False)
                            self.downloader_core._compression_target_folder = cps.get("target_folder")
                            self.downloader_core._compression_target_url = cps.get("target_url")

                        if hasattr(self.downloader_core, "state_manager"):
                            sm = self.downloader_core.state_manager
                            sm.set_download_running(False)
                            sm.set_paused(True)
                            sm.set_current_url_index(self.current_url_index)

                    self._restore_gui_from_state()

                    if hasattr(self, "url_panel"):
                        self.root.after(100, self.url_panel._update_all_url_backgrounds)

                    if getattr(self.downloader_core, "_compression_in_progress", False):
                        self.log("バックアップ復元: 圧縮状態をリセットしました", "info")
                        self.downloader_core._compression_in_progress = False
                        self.downloader_core._compression_target_folder = None
                        self.downloader_core._compression_target_url = None

                    self.root.after(200, self._update_gui_state_from_thread)

                    restored_files.append("再開ポイント・ダウンロード状態")

                except Exception as e:
                    self.log(f"再開ポイントの復元に失敗: {e}", "warning")

            if restored_files:
                self.log(f"バックアップから復元: {', '.join(restored_files)}")
                messagebox.showinfo(
                    "復元完了",
                    "ドラッグ&ドロップでバックアップを復元しました:\n"
                    + "\n".join(restored_files)
                    + "\n\nダウンロードは中断状態として復元されました。\n再開ボタンで続きからダウンロードできます。"
                )
            else:
                messagebox.showwarning("復元失敗", "バックアップファイルが見つかりませんでした。")

        except Exception as e:
            self.log(f"バックアップ復元エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの復元に失敗しました:\n{e}")


    def open_current_image_page(self) -> None:
        """現在の画像ページを開く"""
        try:
            current_url = None

            if hasattr(self, "downloader_core") and hasattr(self.downloader_core, "current_image_page_url"):
                current_url = self.downloader_core.current_image_page_url
            elif hasattr(self, "current_image_page_url"):
                current_url = self.current_image_page_url

            if current_url:
                import webbrowser
                webbrowser.open(current_url)
                self.log(f"ブラウザでURLを開きました: {current_url}", "info")
            else:
                self.log("現在の画像ページURLが設定されていません", "warning")

        except Exception as e:
            self.log(f"画像ページを開くエラー: {e}", "error")


    def open_current_download_folder(self) -> None:
        """現在のダウンロードフォルダを開く"""
        self.folder_controller.open_current_download_folder()


    def browse_folder(self) -> None:
        """フォルダを選択（Controllerに委譲）"""
        self.folder_controller.browse_folder()


    def open_download_folder(self, folder_path: str = None) -> None:
        """指定フォルダを開く - Controllerに委譲"""
        if folder_path:
            self.folder_controller.open_folder(folder_path)
        else:
            self.folder_controller.open_download_folder()


    def clear_all_gui_and_state(self) -> None:
        """GUIと状態をクリア（旧メソッド、clear_all_dataに委譲）"""
        self.clear_all_data()
    
    def _convert_duplicate_mode_to_english(self, japanese_value: str) -> str:
        """日本語の同名処理モードを英語に変換"""
        # 既に英語の場合はそのまま返す
        if japanese_value in ['overwrite', 'rename', 'skip']:
            return japanese_value
        # 日本語の場合は英語に変換
        return self.DUPLICATE_MODE_MAPPING.get(japanese_value, japanese_value)
    
    def _convert_duplicate_mode_to_japanese(self, english_value: str) -> str:
        """英語の同名処理モードを日本語に変換"""
        # 既に日本語の場合はそのまま返す
        if english_value in self.DUPLICATE_MODE_MAPPING:
            return english_value
        # 英語の場合は日本語に変換
        return self.DUPLICATE_MODE_REVERSE.get(english_value, english_value)


    def save_settings_and_state(self) -> None:
        """設定と状態を保存"""
        try:
            # 統合設定構造で保存
            unified_settings = {
                'main_app': {},
                'parser': {},
                'torrent_manager': {},
                'download_manager': {}
            }
            
            # メインアプリの設定を準備
            # ウィンドウ状態
            unified_settings['main_app']['window_geometry'] = self.root.geometry()
            unified_settings['main_app']['window_state'] = self.window_state.get()
            
            # ⭐修正: PanedWindowのサッシュ位置を保存⭐
            try:
                # sash_coord()で各サッシュの位置を取得（tk.PanedWindow用）
                if hasattr(self.main_v_pane, 'sash_coord'):
                    unified_settings['main_app']['sash_pos_v'] = self.main_v_pane.sash_coord(0)[1]
                if hasattr(self.top_h_pane, 'sash_coord'):
                    unified_settings['main_app']['sash_pos_h'] = self.top_h_pane.sash_coord(0)[0]
            except Exception as e:
                self.log(f"PanedWindow位置保存エラー: {e}", "warning")

            # フォルダパス
            unified_settings['main_app']['folder_path'] = self.folder_var.get()

            # ⭐自動シリアライズ: STATE_KEYSに含まれる変数を自動的に保存⭐
            # 各設定値を保存（ウィンドウ状態とフォルダパスは既に保存済みなのでスキップ）
            skip_keys = {'window_geometry', 'folder_path', 'resize_values'}
            for key in self.STATE_KEYS:
                if key not in skip_keys and hasattr(self, key):
                    attr = getattr(self, key)
                    try:
                        # ⭐自動シリアライズ: 変数の型に応じて自動的に値を取得⭐
                        if hasattr(attr, 'get') and not isinstance(attr, dict):
                            value = attr.get()
                            
                            # ⭐重要: 同名処理モードは英語値で保存⭐
                            if key in ['duplicate_file_mode', 'duplicate_folder_mode']:
                                value = self._convert_duplicate_mode_to_english(value)
                            
                            unified_settings['main_app'][key] = value
                        elif isinstance(attr, (str, int, float, bool, type(None))):
                            # プリミティブ型の場合はそのまま保存
                            unified_settings['main_app'][key] = attr
                        elif isinstance(attr, dict):
                            # 辞書型の場合はそのまま保存（resize_valuesは別途処理）
                            if key != 'resize_values':
                                unified_settings['main_app'][key] = attr
                        else:
                            # その他の型の場合は文字列に変換して保存
                            unified_settings['main_app'][key] = str(attr)
                    except Exception as e:
                        # エラーが発生した場合はスキップ（既存の設計を破壊しない）
                        self.log(f"設定保存エラー ({key}): {e}", "warning")
                        continue
            
            # resize_valuesの保存
            if hasattr(self, 'resize_values') and isinstance(self.resize_values, dict):
                resize_values_dict = {}
                for key, value in self.resize_values.items():
                    if hasattr(value, 'get'):
                        resize_values_dict[key] = value.get()
                    else:
                        resize_values_dict[key] = value
                unified_settings['main_app']['resize_values'] = resize_values_dict
            
            # パーサー関連の設定を保存
            # パーサーインスタンスから最新の設定を取得
            if hasattr(self, '_parser_instance') and self._parser_instance is not None:
                try:
                    if hasattr(self._parser_instance, '_collect_parser_settings'):
                        parser_settings = self._parser_instance._collect_parser_settings()
                        if hasattr(self, 'parser_settings'):
                            self.parser_settings.update(parser_settings)
                        else:
                            self.parser_settings = parser_settings
                except Exception as e:
                    self.log(f"パーサー設定取得エラー: {e}", "error")
            
            if hasattr(self, 'parser_settings') and self.parser_settings:
                unified_settings['parser'] = self.parser_settings
            elif hasattr(self, 'url_panel') and hasattr(self.url_panel, 'parser_settings'):
                unified_settings['parser'] = self.url_panel.parser_settings

            # ダウンロードマネージャーの設定を保存
            if hasattr(self, 'download_manager_settings') and self.download_manager_settings:
                unified_settings['download_manager'] = self.download_manager_settings
            elif hasattr(self, 'progress_panel'):
                download_manager_settings = {
                    'window_geometry': getattr(self.progress_panel, 'separate_window_geometry', '700x800'),
                    'auto_scroll_enabled': getattr(self.progress_panel, 'auto_scroll_enabled', False)
                }
                unified_settings['download_manager'] = download_manager_settings

            # Torrentマネージャーの設定を保存
            if hasattr(self, 'torrent_manager_settings') and self.torrent_manager_settings:
                unified_settings['torrent_manager'] = self.torrent_manager_settings
            elif hasattr(self, 'torrent_manager'):
                torrent_settings = {
                    'window_geometry': getattr(self.torrent_manager, 'window_geometry', '670x1100+100+100'),
                    'save_directory': getattr(self.torrent_manager, 'torrent_save_directory', ''),
                    'page_wait_time': getattr(self.torrent_manager, 'page_wait_time', 1.0),
                    'error_handling': getattr(self.torrent_manager, 'error_handling', '中断'),
                    'torrent_selection': getattr(self.torrent_manager, 'torrent_selection', '並び順で最下部'),
                    'duplicate_file_mode': getattr(self.torrent_manager, 'duplicate_file_mode', 'rename'),
                    'filtering_enabled': getattr(self.torrent_manager, 'filtering_enabled', False),
                    'filtering_size': getattr(self.torrent_manager, 'filtering_size', 600),
                    'filtering_action': getattr(self.torrent_manager, 'filtering_action', 'max_only')
                }
                unified_settings['torrent_manager'] = torrent_settings

            # バックアップ設定を保存
            backup_settings = {}
            if hasattr(self, 'progress_retention_count'):
                backup_settings['progress_retention_count'] = self.progress_retention_count.get()
            if hasattr(self, 'backup_enabled'):
                backup_settings['backup_enabled'] = self.backup_enabled.get()
            if hasattr(self, 'download_info_backup'):
                backup_settings['download_info_backup'] = self.download_info_backup.get()
            if hasattr(self, 'backup_file_format'):
                backup_settings['backup_file_format'] = self.backup_file_format.get()
            if hasattr(self, 'backup_save_location'):
                backup_settings['backup_save_location'] = self.backup_save_location.get()
            if hasattr(self, 'custom_backup_path'):
                backup_settings['custom_backup_path'] = self.custom_backup_path.get()
            if hasattr(self, 'auto_backup'):
                backup_settings['auto_backup'] = self.auto_backup.get()
            
            if backup_settings:
                unified_settings['main_app']['backup_settings'] = backup_settings
            
            # プログレスバー表示制限オプション
            if hasattr(self, 'progress_display_limit_enabled'):
                unified_settings['main_app']['progress_display_limit_enabled'] = self.progress_display_limit_enabled.get()
            if hasattr(self, 'progress_retention_count'):
                unified_settings['main_app']['progress_retention_count'] = self.progress_retention_count.get()
            
            # プログレスバーログ保存オプション
            if hasattr(self, 'progress_backup_enabled'):
                unified_settings['main_app']['progress_backup_enabled'] = self.progress_backup_enabled.get()
            if hasattr(self, 'gallery_info_backup'):
                unified_settings['main_app']['gallery_info_backup'] = self.gallery_info_backup.get()
            if hasattr(self, 'backup_file_format'):
                unified_settings['main_app']['backup_file_format'] = self.backup_file_format.get()
            
            # DLログ保存オプション
            if hasattr(self, 'dl_log_enabled'):
                unified_settings['main_app']['dl_log_enabled'] = self.dl_log_enabled.get()
            if hasattr(self, 'dl_log_method'):
                unified_settings['main_app']['dl_log_method'] = self.dl_log_method.get()
            
            # 統合エラー処理関連の変数
            if hasattr(self, 'integrated_error_handling_enabled'):
                unified_settings['main_app']['integrated_error_handling_enabled'] = self.integrated_error_handling_enabled.get()
            if hasattr(self, 'wait_for_auto_recovery'):
                unified_settings['main_app']['wait_for_auto_recovery'] = self.wait_for_auto_recovery.get()
            if hasattr(self, 'resume_option'):
                unified_settings['main_app']['resume_option'] = self.resume_option.get()
            if hasattr(self, 'lower_security_level'):
                unified_settings['main_app']['lower_security_level'] = self.lower_security_level.get()
            if hasattr(self, 'skip_certificate_verify'):
                unified_settings['main_app']['skip_certificate_verify'] = self.skip_certificate_verify.get()
            if hasattr(self, 'use_custom_ssl'):
                unified_settings['main_app']['use_custom_ssl'] = self.use_custom_ssl.get()
            if hasattr(self, 'use_proxy'):
                unified_settings['main_app']['use_proxy'] = self.use_proxy.get()
            
            # プロキシ設定詳細
            if hasattr(self, 'proxy_usage_mode'):
                unified_settings['main_app']['proxy_usage_mode'] = self.proxy_usage_mode.get()
            if hasattr(self, 'proxy_server'):
                unified_settings['main_app']['proxy_server'] = self.proxy_server.get()
            if hasattr(self, 'proxy_port'):
                unified_settings['main_app']['proxy_port'] = self.proxy_port.get()
            if hasattr(self, 'proxy_username'):
                unified_settings['main_app']['proxy_username'] = self.proxy_username.get()
            if hasattr(self, 'proxy_password'):
                unified_settings['main_app']['proxy_password'] = self.proxy_password.get()
            
            # カスタムSSL設定詳細
            if hasattr(self, 'custom_ssl_config_file'):
                unified_settings['main_app']['custom_ssl_config_file'] = self.custom_ssl_config_file.get()
            
            # タグ変数設定を保存
            if hasattr(self, 'tag_delimiter'):
                unified_settings['main_app']['tag_delimiter'] = self.tag_delimiter
            if hasattr(self, 'tag_max_length'):
                unified_settings['main_app']['tag_max_length'] = self.tag_max_length
            if hasattr(self, 'use_space_in_delimiter'):
                unified_settings['main_app']['use_space_in_delimiter'] = self.use_space_in_delimiter
            
            # カスタムディレクトリ機能を削除

            # 設定ファイル保存場所を更新
            # 設定ファイルは常に同じディレクトリに保存
            success = self.settings_backup_manager.save_settings(unified_settings)
            
            if not success:
                self.log("設定保存に失敗しました", "error")
            else:
                self.log("設定を保存しました", "info")
        except Exception as e:
            self.log(f"設定保存エラー: {e}", "error")


    def load_settings_and_state(self) -> None:
        """設定と状態を読み込み"""
        try:
            # settings_backup_managerの存在チェック
            if not hasattr(self, 'settings_backup_manager') or self.settings_backup_manager is None:
                self.log("settings_backup_managerが初期化されていません。初期化をスキップします。", "warning")
                return
            
            # 設定ファイルは常に同じディレクトリから読み込み
            settings = self.settings_backup_manager.load_settings()
            # ⭐簡潔化: 完了ログは downloader.py で表示されるため削除⭐
            
            # 新しい構造のみをサポート
            if isinstance(settings, dict) and 'main_app' in settings:
                main_app_settings = settings.get('main_app', {})
                self.parser_settings = settings.get('parser', {})
                self.torrent_manager_settings = settings.get('torrent_manager', {})
                self.download_manager_settings = settings.get('download_manager', {})
                settings = main_app_settings
            else:
                # 新しい構造でない場合はエラー
                self.log("設定ファイルが新しい構造ではありません。デフォルト設定を使用します。", "error")
                self.parser_settings = {}
                self.torrent_manager_settings = {}
                self.download_manager_settings = {}
                return

            # ウィンドウ状態を復元（遅延実行）
            def restore_window_state():
                try:
                    if 'window_geometry' in settings:
                        self.root.geometry(settings['window_geometry'])
                    if 'window_state' in settings and settings['window_state'] != 'iconic':
                        self.root.state(settings['window_state'])
                        self.window_state.set(settings['window_state'])
                    
                    # ⭐修正: PanedWindowのサッシュ位置を復元⭐
                    if 'sash_pos_v' in settings:
                        try:
                            self.main_v_pane.sash_place(0, 0, settings['sash_pos_v'])
                        except Exception as e:
                            self.log(f"垂直パネル位置復元エラー: {e}", "warning")
                    if 'sash_pos_h' in settings:
                        try:
                            self.top_h_pane.sash_place(0, settings['sash_pos_h'], 0)
                        except Exception as e:
                            self.log(f"水平パネル位置復元エラー: {e}", "warning")
                except Exception as e:
                    self.log(f"ウィンドウ状態復元エラー: {e}", "error")
            
            # 100ms後にウィンドウ状態を復元
            self.root.after(100, restore_window_state)

            # フォルダパスを復元（シンプル化）
            if 'folder_path' in settings and settings['folder_path']:
                folder_path = settings['folder_path']
                # ⭐追加: 保存ディレクトリが存在しない場合は作成⭐
                if not os.path.exists(folder_path):
                    try:
                        os.makedirs(folder_path, exist_ok=True)
                        self.log(f"保存ディレクトリを作成しました: {folder_path}", "info")
                    except Exception as e:
                        self.log(f"保存ディレクトリの作成に失敗しました: {e}", "error")
                        # デフォルト値を使用
                        folder_path = os.path.join(os.path.expanduser("~"), "Documents")
                        try:
                            os.makedirs(folder_path, exist_ok=True)
                        except Exception:
                            pass
                self.folder_var.set(folder_path)
            else:
                # デフォルト値を設定
                default_folder = os.path.join(os.path.expanduser("~"), "Documents")
                try:
                    os.makedirs(default_folder, exist_ok=True)
                except Exception:
                    pass
                self.folder_var.set(default_folder)
            
            # ⭐削除: folder_path手動同期はfolder_varトレースで自動実行⭐
            # self.folder_path = self.folder_var.get()  # 不要

            # resize_valuesの特別な処理
            if 'resize_values' in settings and isinstance(settings['resize_values'], dict):
                # Settings.jsonからresize_valuesを読み込み
                for key, value in settings['resize_values'].items():
                    if key in self.resize_values and hasattr(self.resize_values[key], 'set'):
                        try:
                            self.resize_values[key].set(str(value))
                            # resize_valuesを設定
                        except Exception as e:
                            self.log(f"resize_values[{key}]設定エラー: {e}", "warning")
                    else:
                        # resize_valuesの設定をスキップ
                        pass
            else:
                # Settings.jsonにresize_valuesがありません
                pass
            
            # ⭐自動シリアライズ: STATE_KEYSに含まれる変数を自動的に読み込み⭐
            # 各設定値を復元（ウィンドウ状態とフォルダパスは既に処理済みなのでスキップ）
            skip_keys = {'window_geometry', 'folder_path', 'resize_values'}
            for key in self.STATE_KEYS:
                if key not in skip_keys and key in settings and hasattr(self, key):
                    try:
                        attr = getattr(self, key)
                        value = settings[key]
                        
                        # ⭐重要: 同名処理モードは日本語値に変換して設定⭐
                        if key in ['duplicate_file_mode', 'duplicate_folder_mode']:
                            value = self._convert_duplicate_mode_to_japanese(value)
                        
                        # ⭐追加: retry_limit_actionの古い形式を新しい形式に変換⭐
                        if key == 'retry_limit_action':
                            # 古い形式の値を新しい形式に変換
                            old_to_new_mapping = {
                                "SeleniumをONにしてリトライ": "selenium_retry",  # 日本語表示値
                                "skip": "skip_image",  # 旧形式
                                "abort": "pause",  # 旧形式
                            }
                            if value in old_to_new_mapping:
                                value = old_to_new_mapping[value]
                            # 新しい形式の値でない場合は、デフォルト値を使用
                            if value not in ["pause", "skip_image", "skip_url", "selenium_retry"]:
                                value = "selenium_retry"  # デフォルト値（Selenium安全弁を有効化）
                        
                        # ⭐自動シリアライズ: 変数の型に応じて自動的に値を設定⭐
                        if hasattr(attr, 'set'):
                            # StringVar, BooleanVar, IntVar等の場合
                            attr.set(value)
                        elif isinstance(attr, dict) and isinstance(value, dict):
                            # 辞書型の場合はマージ（既存の設計を保持）
                            attr.update(value)
                        else:
                            # その他の型の場合は直接設定
                            setattr(self, key, value)
                    except Exception as e:
                        # エラーが発生した場合はスキップ（既存の設計を破壊しない）
                        self.log(f"設定読み込みエラー ({key}): {e}", "warning")
                        continue
            
            # タグ変数設定を読み込み
            if 'tag_delimiter' in settings:
                self.tag_delimiter = settings['tag_delimiter']
            else:
                self.tag_delimiter = " "  # デフォルト値
            if 'tag_max_length' in settings:
                self.tag_max_length = settings['tag_max_length']
            else:
                self.tag_max_length = 0  # デフォルト値
            if 'use_space_in_delimiter' in settings:
                self.use_space_in_delimiter = settings['use_space_in_delimiter']
            else:
                self.use_space_in_delimiter = True  # デフォルト値
            
            # 統合設定ファイルから各コンポーネントの設定を復元
            original_settings = self.settings_backup_manager.load_settings()
            
            # パーサー関連の設定を復元（パーサー起動時に一任するため、ここでは設定のみ保存）
            if 'parser' in original_settings and hasattr(self, 'url_panel'):
                self.url_panel.parser_settings = original_settings['parser']
                # パーサー設定のGUI反映はパーサー起動時に一任（二重表示を避けるため）
                # if hasattr(self.url_panel, '_apply_parser_settings'):
                #     self.url_panel._apply_parser_settings()

            # ダウンロードマネージャーの設定を復元
            if 'download_manager' in original_settings and hasattr(self, 'progress_panel'):
                dm_settings = original_settings['download_manager']
                if 'window_geometry' in dm_settings:
                    self.progress_panel.separate_window_geometry = dm_settings['window_geometry']
                if 'auto_scroll_enabled' in dm_settings:
                    self.progress_panel.auto_scroll_enabled = dm_settings['auto_scroll_enabled']

            # Torrentマネージャーの設定を復元
            if 'torrent_manager' in original_settings and hasattr(self, 'torrent_manager'):
                tm_settings = original_settings['torrent_manager']
                if 'window_geometry' in tm_settings:
                    self.torrent_manager.window_geometry = tm_settings['window_geometry']
                if 'save_directory' in tm_settings:
                    self.torrent_manager.torrent_save_directory = tm_settings['save_directory']
                if 'page_wait_time' in tm_settings:
                    self.torrent_manager.page_wait_time = tm_settings['page_wait_time']
                if 'error_handling' in tm_settings:
                    self.torrent_manager.error_handling = tm_settings['error_handling']
                if 'torrent_selection' in tm_settings:
                    self.torrent_manager.torrent_selection = tm_settings['torrent_selection']
                if 'duplicate_file_mode' in tm_settings:
                    self.torrent_manager.duplicate_file_mode = tm_settings['duplicate_file_mode']
                if 'filtering_enabled' in tm_settings:
                    self.torrent_manager.filtering_enabled = tm_settings['filtering_enabled']
                if 'filtering_size' in tm_settings:
                    self.torrent_manager.filtering_size = tm_settings['filtering_size']
                if 'filtering_action' in tm_settings:
                    self.torrent_manager.filtering_action = tm_settings['filtering_action']

            # バックアップ設定を復元
            if 'backup_settings' in settings:
                backup_settings = settings['backup_settings']
                if 'progress_retention_count' in backup_settings and hasattr(self, 'progress_retention_count'):
                    self.progress_retention_count.set(backup_settings['progress_retention_count'])
                if 'backup_enabled' in backup_settings and hasattr(self, 'backup_enabled'):
                    self.backup_enabled.set(backup_settings['backup_enabled'])
                if 'download_info_backup' in backup_settings and hasattr(self, 'download_info_backup'):
                    self.download_info_backup.set(backup_settings['download_info_backup'])
                if 'backup_file_format' in backup_settings and hasattr(self, 'backup_file_format'):
                    self.backup_file_format.set(backup_settings['backup_file_format'])
                if 'backup_save_location' in backup_settings and hasattr(self, 'backup_save_location'):
                    self.backup_save_location.set(backup_settings['backup_save_location'])
                if 'custom_backup_path' in backup_settings and hasattr(self, 'custom_backup_path'):
                    self.custom_backup_path.set(backup_settings['custom_backup_path'])
                if 'auto_backup' in backup_settings and hasattr(self, 'auto_backup'):
                    self.auto_backup.set(backup_settings['auto_backup'])
                
                # バックアップマネージャーの設定を更新
                if hasattr(self, 'backup_manager'):
                    self.backup_manager.update_settings(backup_settings)
            
            # ⭐修正: 設定読み込み後にプレースホルダーを再設定（グレー表示を防ぐ）⭐
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, 'download_range_start_entry') and hasattr(self.options_panel, 'download_range_end_entry'):
                # ダウンロード範囲の入力フォームのプレースホルダーを再設定
                self.root.after(100, lambda: self.options_panel._setup_placeholder(
                    self.options_panel.download_range_start_entry, "空欄は0"))
                self.root.after(100, lambda: self.options_panel._setup_placeholder(
                    self.options_panel.download_range_end_entry, "空欄は∞"))
            
            # プログレスバー表示制限オプション
            if 'progress_display_limit_enabled' in settings and hasattr(self, 'progress_display_limit_enabled'):
                self.progress_display_limit_enabled.set(settings['progress_display_limit_enabled'])
            if 'progress_retention_count' in settings and hasattr(self, 'progress_retention_count'):
                self.progress_retention_count.set(settings['progress_retention_count'])
            
            # プログレスバーログ保存オプション
            if 'progress_backup_enabled' in settings and hasattr(self, 'progress_backup_enabled'):
                self.progress_backup_enabled.set(settings['progress_backup_enabled'])
            if 'gallery_info_backup' in settings and hasattr(self, 'gallery_info_backup'):
                self.gallery_info_backup.set(settings['gallery_info_backup'])
            
            # 統合エラーレジューム管理の状態を更新（設定読み込み後）
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, '_update_enhanced_error_options'):
                self.root.after(100, self.options_panel._update_enhanced_error_options)
            if 'backup_file_format' in settings and hasattr(self, 'backup_file_format'):
                self.backup_file_format.set(settings['backup_file_format'])
            
            # DLログ保存オプション
            if 'dl_log_enabled' in settings and hasattr(self, 'dl_log_enabled'):
                self.dl_log_enabled.set(settings['dl_log_enabled'])
            if 'dl_log_method' in settings and hasattr(self, 'dl_log_method'):
                self.dl_log_method.set(settings['dl_log_method'])
            
            # 統合エラー処理関連の変数
            if 'integrated_error_handling_enabled' in settings and hasattr(self, 'integrated_error_handling_enabled'):
                self.integrated_error_handling_enabled.set(settings['integrated_error_handling_enabled'])
            if 'wait_for_auto_recovery' in settings and hasattr(self, 'wait_for_auto_recovery'):
                self.wait_for_auto_recovery.set(settings['wait_for_auto_recovery'])
            if 'resume_option' in settings and hasattr(self, 'resume_option'):
                self.resume_option.set(settings['resume_option'])
            if 'lower_security_level' in settings and hasattr(self, 'lower_security_level'):
                self.lower_security_level.set(settings['lower_security_level'])
            if 'skip_certificate_verify' in settings and hasattr(self, 'skip_certificate_verify'):
                self.skip_certificate_verify.set(settings['skip_certificate_verify'])
            if 'use_custom_ssl' in settings and hasattr(self, 'use_custom_ssl'):
                self.use_custom_ssl.set(settings['use_custom_ssl'])
            if 'use_proxy' in settings and hasattr(self, 'use_proxy'):
                self.use_proxy.set(settings['use_proxy'])
            
            # プロキシ設定詳細
            if 'proxy_usage_mode' in settings and hasattr(self, 'proxy_usage_mode'):
                self.proxy_usage_mode.set(settings['proxy_usage_mode'])
            if 'proxy_server' in settings and hasattr(self, 'proxy_server'):
                self.proxy_server.set(settings['proxy_server'])
            if 'proxy_port' in settings and hasattr(self, 'proxy_port'):
                self.proxy_port.set(settings['proxy_port'])
            if 'proxy_username' in settings and hasattr(self, 'proxy_username'):
                self.proxy_username.set(settings['proxy_username'])
            if 'proxy_password' in settings and hasattr(self, 'proxy_password'):
                self.proxy_password.set(settings['proxy_password'])
            
            # カスタムSSL設定詳細
            if 'custom_ssl_config_file' in settings and hasattr(self, 'custom_ssl_config_file'):
                self.custom_ssl_config_file.set(settings['custom_ssl_config_file'])
            
            # カスタムディレクトリ機能を削除

            # デフォルト値の適用（設定ファイルに存在しない項目）
            self._apply_default_values(settings)

            # 設定読み込み完了ログ
            self.log("設定読み込みが完了しました", "info")

            # オプションパネルの状態更新（設定読み込み後）
            if hasattr(self, 'options_panel'):
                self.root.after(200, self._update_options_panel_state)
                # ⭐重要: プレースホルダー表示を更新⭐
                self.root.after(300, self._update_placeholders)
                # ⭐重要: 高度なオプションの状態を更新⭐
                self.root.after(500, self._sync_gui_with_internal_state)
            else:
                # ⭐設定ファイルがない場合もデフォルト値を設定⭐
                default_folder = os.path.join(os.path.expanduser("~"), "Documents")
                self.folder_var.set(default_folder)
                self.folder_path = default_folder
                
                # デフォルト値を適用
                self._apply_default_values({})
                
                self.log(f"設定ファイルが見つかりません。デフォルト設定を使用します。(保存先: {default_folder})", "info")
        except Exception as e:
            self.log(f"設定読み込みエラー: {e}", "error")

    def _apply_default_values(self, settings: dict) -> None:
        """設定ファイルに存在しない項目にデフォルト値を適用"""
        try:
            for key, default_value in self.DEFAULT_VALUES.items():
                if key not in settings and hasattr(self, key):
                    attr = getattr(self, key)
                    if hasattr(attr, 'set'):
                        attr.set(default_value)
                    else:
                        setattr(self, key, default_value)
        except Exception as e:
            self.log(f"デフォルト値適用エラー: {e}", "error")
    
    def _update_placeholders(self) -> None:
        """プレースホルダー表示を更新"""
        try:
            if hasattr(self, 'options_panel'):

                # -----------------------------
                # 開始番号プレースホルダー
                # -----------------------------
                if hasattr(self.options_panel, 'download_range_start_entry'):
                    start_entry = self.options_panel.download_range_start_entry
                    start_var = self.download_range_start

                    # textvariable が空ならプレースホルダー表示
                    if start_var and (not start_var.get() or start_var.get() == ""):
                        current_text = start_entry.get()

                        if not current_text or current_text in ("", "空欄は0"):
                            start_entry.delete(0, tk.END)
                            start_entry.insert(0, "空欄は0")
                            start_entry.config(foreground="#999999")

                        # Entry にプレースホルダーが入っている間は textvariable を空に固定
                        start_var.set("")

                # -----------------------------
                # 終了番号プレースホルダー
                # -----------------------------
                if hasattr(self.options_panel, 'download_range_end_entry'):
                    end_entry = self.options_panel.download_range_end_entry
                    end_var = self.download_range_end

                    if end_var and (not end_var.get() or end_var.get() == ""):
                        current_text = end_entry.get()

                        if not current_text or current_text in ("", "空欄は∞"):
                            end_entry.delete(0, tk.END)
                            end_entry.insert(0, "空欄は∞")
                            end_entry.config(foreground="#999999")

                        end_var.set("")

        except Exception as e:
            self.log(f"プレースホルダー更新エラー: {e}", "error")

    def _update_options_panel_state(self) -> None:
        """オプションパネルの状態を更新"""
        try:
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, 'state_manager'):
                # 各オプションの状態更新メソッドを呼び出し
                if hasattr(self.options_panel.state_manager, '_update_resize_options_state'):
                    self.options_panel.state_manager._update_resize_options_state()
                if hasattr(self.options_panel.state_manager, '_update_advanced_options_state'):
                    self.options_panel.state_manager._update_advanced_options_state()
                if hasattr(self.options_panel.state_manager, '_update_incomplete_folder_options_state'):
                    self.options_panel.state_manager._update_incomplete_folder_options_state()
                if hasattr(self.options_panel.state_manager, '_update_string_conversion_state'):
                    self.options_panel.state_manager._update_string_conversion_state()
                if hasattr(self.options_panel.state_manager, '_update_auto_resume_options_state'):
                    self.options_panel.state_manager._update_auto_resume_options_state()
                if hasattr(self.options_panel.state_manager, '_update_compression_options_state'):
                    self.options_panel.state_manager._update_compression_options_state()
                if hasattr(self.options_panel.state_manager, '_update_folder_name_state'):
                    self.options_panel.state_manager._update_folder_name_state()
                if hasattr(self.options_panel.state_manager, '_update_first_page_naming_state'):
                    self.options_panel.state_manager._update_first_page_naming_state()
                if hasattr(self.options_panel.state_manager, '_update_skip_count_state'):
                    self.options_panel.state_manager._update_skip_count_state()
                if hasattr(self.options_panel.state_manager, '_update_custom_name_entry_state'):
                    self.options_panel.state_manager._update_custom_name_entry_state()
                # オプションパネルの状態を更新しました
            else:
                self.log("オプションパネルまたはstate_managerが見つかりません", "warning")
        except Exception as e:
            self.log(f"オプションパネル状態更新エラー: {e}", "error")

    def _apply_current_options(self) -> None:
        """現在のオプションを反映させる"""
        try:
            self.log("オプションを反映させました", "info")
            messagebox.showinfo("オプション反映", "現在のオプションを反映させました。")
            
        except Exception as e:
            messagebox.showerror("エラー", f"オプション反映エラー: {e}")
            self.log(f"オプション反映エラー: {e}", "error")

    def _load_options_for_download(self) -> None:
        """ダウンロードプロセス用のオプション読み込み"""
        try:
            # サムネイル表示の即座反映
            if hasattr(self, 'url_panel'):
                self.url_panel._update_thumbnail_display_state()
            
            # ⭐修正: ログを削除（不要な情報）⭐
            # self.log("ダウンロード用オプションを読み込みました", "info")
            
        except Exception as e:
            self.log(f"ダウンロード用オプション読み込みエラー: {e}", "error")

    def on_closing(self) -> None:
            """アプリケーション終了時の処理"""
            try:
                # ⭐Phase 2: オブザーバー登録解除⭐
                if hasattr(self, 'state_manager'):
                    self.state_manager.detach_observer(self)
                
                # on_closing 開始
                
                # 未完了フォルダのリネーム処理（確認ダイアログ付き）
                if hasattr(self, 'downloader_core') and self.downloader_core:
                    # downloader_coreが存在します
                    self._handle_incomplete_folders_on_exit()
                else:
                    # downloader_coreが存在しません
                    pass
                
                # 他のウィンドウの設定保存
                if hasattr(self, 'progress_panel') and self.progress_panel:
                    if hasattr(self.progress_panel, '_save_separate_window_settings'):
                        self.progress_panel._save_separate_window_settings()
                
                if hasattr(self, 'torrent_manager') and self.torrent_manager:
                    if hasattr(self.torrent_manager, '_save_window_settings'):
                        self.torrent_manager._save_window_settings()
                
                if hasattr(self, 'parser') and self.parser:
                    if hasattr(self.parser, '_save_parser_settings'):
                        self.parser._save_parser_settings()
                
                # ⭐ウィンドウ終了時の一括保存処理⭐
                self._save_batch_on_exit()
                
                # ⭐追加: プログレスバー状態の保存または破棄⭐
                self._handle_progress_bars_on_exit()
                
                # ⭐追加: ダウンロードスレッドの停止⭐
                if hasattr(self, 'downloader_core') and self.downloader_core:
                    # ダウンロード停止
                    if hasattr(self.downloader_core, 'state_manager'):
                        self.downloader_core.state_manager.set_download_running(False)
                        stop_flag = self.downloader_core.state_manager.get_stop_flag()
                        stop_flag.set()
                    
                    # HttpClientのクリーンアップ
                    if hasattr(self.downloader_core, 'session_manager'):
                        session_manager = self.downloader_core.session_manager
                        if hasattr(session_manager, 'http_client'):
                            try:
                                session_manager.http_client.close()
                                self.log("✅ HttpClientをクローズしました", "info")
                            except Exception as e:
                                self.log(f"HttpClientクローズエラー: {e}", "error")
                    
                    # ⭐追加: EventBusの停止⭐
                    if hasattr(self.downloader_core, 'event_bus'):
                        try:
                            self.downloader_core.event_bus.stop()
                            self.log("✅ EventBusを停止しました", "info")
                        except Exception as e:
                            self.log(f"EventBus停止エラー: {e}", "error")
                
                # 設定保存を開始
                self.save_settings_and_state()
                
                # ウィンドウを破棄します
                self.root.destroy()

            except Exception as e:
                print(f"終了処理エラー: {e}")
                import traceback
                print(f"エラー詳細: {traceback.format_exc()}")
                # エラーが起きてもウィンドウは確実に閉じる
                if hasattr(self, 'root'):
                    self.root.destroy()

    def _save_batch_on_exit(self) -> None:
        """ウィンドウ終了時の一括保存処理"""
        try:
            # 一括保存が有効な場合のみ実行
            if not hasattr(self, 'dl_log_batch_save') or not self.dl_log_batch_save.get():
                return
            
            # ⭐修正: メソッドが存在する場合のみ実行⭐
            if hasattr(self, 'downloader_core') and self.downloader_core and hasattr(self.downloader_core, '_save_batch_to_parent_directory'):
                self.downloader_core._save_batch_to_parent_directory()
                self.log("📝 ウィンドウ終了時の一括保存を実行しました")
            
        except Exception as e:
            self.log(f"ウィンドウ終了時一括保存エラー: {e}", "error")
    
    def _save_batch_on_clear(self) -> None:
        """クリア時の一括保存処理"""
        try:
            # 一括保存が有効な場合のみ実行
            if not hasattr(self, 'dl_log_batch_save') or not self.dl_log_batch_save.get():
                return
            
            # ⭐修正: メソッドが存在する場合のみ実行⭐
            if hasattr(self, 'downloader_core') and self.downloader_core and hasattr(self.downloader_core, '_save_batch_to_parent_directory'):
                self.downloader_core._save_batch_to_parent_directory()
                self.log("📝 クリア時の一括保存を実行しました")
            
        except Exception as e:
            self.log(f"クリア時一括保存エラー: {e}", "error")
    
    def _handle_incomplete_folders_on_exit(self) -> None:
        """アプリ終了時の未完了フォルダ処理（確認ダイアログ付き）"""
        try:
            # _handle_incomplete_folders_on_exit 開始
            
            # 未完了フォルダリネーム機能が有効でない場合はスキップ
            if not hasattr(self, 'rename_incomplete_folder'):
                # rename_incomplete_folder属性が存在しません
                return
            
            if not self.rename_incomplete_folder.get():
                # 未完了フォルダリネーム機能が無効です
                return
            
            # 未完了フォルダリネーム機能が有効です
            
            # 未完了フォルダが存在しない場合はスキップ
            if not hasattr(self.downloader_core, 'incomplete_folders'):
                # downloader_core.incomplete_folders属性が存在しません。初期化します。
                self.downloader_core.incomplete_folders = set()
                return
            
            if not self.downloader_core.incomplete_folders:
                # 未完了フォルダが存在しません
                return
            
            # 未完了フォルダ数確認
            
            # 未完了フォルダの一覧を取得
            incomplete_folders = list(self.downloader_core.incomplete_folders)
            if not incomplete_folders:
                # 未完了フォルダの一覧が空です
                return
            
            # 未完了フォルダ一覧確認
            
            # 確認ダイアログを表示
            from tkinter import messagebox
            
            folder_list = "\n".join([f"・{os.path.basename(folder)}" for folder in incomplete_folders[:5]])
            if len(incomplete_folders) > 5:
                folder_list += f"\n・他{len(incomplete_folders) - 5}件..."
            
            # 確認ダイアログを表示します
            
            
            response = messagebox.askyesno(
                "未完了フォルダのリネーム",
                f"以下の未完了フォルダに接頭辞を付けますか？\n\n{folder_list}\n\n"
                f"接頭辞: {self.incomplete_folder_prefix.get()}\n\n"
                f"「はい」を選択すると、これらのフォルダに接頭辞が追加されます。"
            )
            
            # ダイアログの応答確認
            
            if response:
                # リネーム処理を実行します
                self.downloader_core.rename_incomplete_folders_on_exit()
            else:
                # リネーム処理をスキップします
                self.log("未完了フォルダのリネームをスキップしました", "info")
                
        except Exception as e:
            self.log(f"未完了フォルダ処理エラー: {e}", "error")
            import traceback
            self.log(f"エラー詳細: {traceback.format_exc()}", "error")
    
    def _handle_progress_bars_on_exit(self) -> None:
        """終了時のプログレスバー状態処理（保存または破棄）"""
        try:
            # 破棄オプションがONの場合はファイルを削除
            if hasattr(self, 'discard_progress_on_exit') and self.discard_progress_on_exit.get():
                if hasattr(self, 'progress_state_manager'):
                    if self.progress_state_manager.delete_progress_bars_file():
                        self.log("プログレスバー状態を破棄しました", "info")
                    else:
                        self.log("プログレスバー状態の破棄に失敗しました", "warning")
                return
            
            # 破棄オプションがOFFの場合は保存
            if hasattr(self, 'progress_state_manager') and hasattr(self, 'progress_panel'):
                # プログレスパネルから現在の状態を取得
                progress_bars = self.progress_panel._get_progress_bars() if hasattr(self.progress_panel, '_get_progress_bars') else {}
                
                if progress_bars:
                    if self.progress_state_manager.save_progress_bars(progress_bars):
                        self.log(f"プログレスバー状態を保存しました（{len(progress_bars)}件）", "info")
                    else:
                        self.log("プログレスバー状態の保存に失敗しました", "warning")
        except Exception as e:
            self.log(f"プログレスバー状態処理エラー: {e}", "error")
            import traceback
            self.log(f"エラー詳細: {traceback.format_exc()}", "error")

    def _handle_incomplete_folders_on_clear(self) -> None:
        """クリア時の未完了フォルダ処理（確認ダイアログ付き）"""
        try:
            from tkinter import messagebox
            
            # 未完了フォルダリネーム機能が有効でない場合はスキップ
            if not hasattr(self, 'rename_incomplete_folder'):
                # rename_incomplete_folder属性が存在しません
                return
            
            # ⭐防御的コーディング: BooleanVarかboolかを判定⭐
            rename_var = self.rename_incomplete_folder
            if hasattr(rename_var, 'get'):
                is_enabled = rename_var.get()
            else:
                is_enabled = rename_var
            
            if not is_enabled:
                # 未完了フォルダリネーム機能が無効です
                return
            
            # 未完了フォルダリネーム機能が有効です
            
            # 未完了フォルダが存在しない場合はスキップ
            if not hasattr(self.downloader_core, 'incomplete_folders'):
                # downloader_core.incomplete_folders属性が存在しません。初期化します。
                self.downloader_core.incomplete_folders = set()
                return
            
            if not self.downloader_core.incomplete_folders:
                # 未完了フォルダが存在しません
                return
            
            # 未完了フォルダの一覧を作成
            incomplete_folders = list(self.downloader_core.incomplete_folders)
            # フォルダ一覧を表示用に整形
            folder_list = "\n".join([f"• {os.path.basename(folder)}" for folder in incomplete_folders])
            
            # 確認ダイアログを表示
            response = messagebox.askyesno(
                "未完了フォルダのリネーム",
                f"クリアを実行する前に、以下の未完了フォルダに接頭辞を付けますか？\n\n{folder_list}\n\n"
                f"接頭辞: {self.incomplete_folder_prefix.get()}\n\n"
                f"「はい」を選択すると、これらのフォルダに接頭辞が追加されます。"
            )
            
            if response:
                self.downloader_core.rename_incomplete_folders_on_exit()
                self.log("未完了フォルダのリネームを実行しました", "info")
            else:
                self.log("未完了フォルダのリネームをスキップしました", "info")
                
        except Exception as e:
            self.log(f"未完了フォルダ処理エラー: {e}", "error")
    
    def launch_parser(self) -> None:
        """パーサーを起動"""
        try:
            # パーサーが既に起動している場合は前面に表示
            if hasattr(self, '_parser_instance') and self._parser_instance is not None:
                try:
                    # ウィンドウがまだ存在するかチェック
                    self._parser_instance.root.winfo_exists()
                    self._parser_instance.root.lift()
                    self._parser_instance.root.focus_force()
                    return
                except tk.TclError:
                    # ウィンドウが既に破棄されている場合
                    self._parser_instance = None
                except Exception:
                    # その他のエラーの場合
                    self._parser_instance = None
            
            # 新しいパーサーウィンドウを作成
            self.log("パーサーウィンドウを作成中...")
            from parser.eh_parser import SearchResultParser
            parser_window = tk.Toplevel(self.root)
            parser_window.title("検索結果パーサー")
            parser_window.geometry("1200x800")
            
            self.log("パーサーインスタンスを作成中...")
            # パーサーインスタンスを作成（parentを渡す）
            try:
                parser = SearchResultParser(parser_window, parent=self)
            except Exception as parser_error:
                self.log(f"パーサーインスタンス作成エラー: {parser_error}", "error")
                parser_window.destroy()
                return
            
            self.log("パーサー設定中...")
            # URL出力コールバックを設定
            parser.output_urls = self._receive_urls_from_parser
            
            # パーサーインスタンスを保存
            self._parser_instance = parser
            
            # ウィンドウクローズハンドラを設定（パーサーインスタンス経由で）
            self._parser_instance.root.protocol("WM_DELETE_WINDOW", self._on_parser_close)
            
            self.log("検索結果パーサーを起動しました")
            
        except Exception as e:
            self.log(f"パーサー起動エラー: {e}", "error")
            import traceback
            traceback.print_exc()
            messagebox.showerror("エラー", f"パーサーの起動に失敗しました: {e}")

    def _receive_urls_from_parser(self, urls):
        """パーサーからURLを受け取る"""
        try:
            if urls:
                # Treeview対応: download_list_widgetにURLを追加
                if hasattr(self, 'download_list_widget'):
                    self.download_list_widget.add_urls(urls)
                    self.log(f"パーサーから{len(urls)}個のURLをDLリストに追加しました")
                else:
                    # フォールバック: 古い実装（url_text）
                    current_text = self.url_text.get("1.0", tk.END).strip()
                    if current_text:
                        new_text = current_text + "\n" + "\n".join(urls)
                    else:
                        new_text = "\n".join(urls)
                    self.url_text.delete("1.0", tk.END)
                    self.url_text.insert("1.0", new_text)
                    self.log(f"パーサーから{len(urls)}個のURLを受け取りました")
                
                # メインウィンドウをアクティブにする
                self.root.after(100, self._activate_main_window)
        except Exception as e:
            self.log(f"URL受信エラー: {e}", "error")
    
    def _activate_main_window(self):
        """メインウィンドウをアクティブにする"""
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception as e:
            self.log(f"メインウィンドウアクティブ化エラー: {e}", "error")

    def _on_parser_close(self):
        """パーサーウィンドウが閉じられた時の処理"""
        try:
            if hasattr(self, '_parser_instance') and self._parser_instance is not None:
                # パーサー設定を保存
                try:
                    if hasattr(self._parser_instance, '_collect_parser_settings'):
                        settings = self._parser_instance._collect_parser_settings()
                        if hasattr(self, 'parser_settings'):
                            self.parser_settings.update(settings)
                        else:
                            self.parser_settings = settings
                except Exception as save_error:
                    self.log(f"パーサー設定保存エラー: {save_error}", "error")
                
                # パーサーの終了処理を実行
                try:
                    self._parser_instance._on_closing()
                except Exception as close_error:
                    self.log(f"パーサー終了処理エラー: {close_error}", "error")
                
                self._parser_instance.root.destroy()
                self._parser_instance = None
        except Exception as e:
            self.log(f"パーサークローズエラー: {e}", "error")
    
    # デリゲーションメソッド
    def _update_gui_for_running(self):
        """実行中のGUI更新"""
        if hasattr(self, 'options_panel'):
            self.options_panel._update_gui_for_running()
    
    def _update_gui_for_idle(self):
        """アイドル状態のGUI更新"""
        if hasattr(self, 'options_panel'):
            self.options_panel._update_gui_for_idle()
    
    def _update_gui_for_error(self):
        """エラー状態のGUI更新"""
        try:
            # エラー時はダウンロード状態をリセット（StateManager経由）
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                self.downloader_core.state_manager.set_download_running(False)
                self.downloader_core.state_manager.set_paused(True)  # エラー時は中断状態として扱う
                self.downloader_core.state_manager.set_paused(True)
            
            # GUIを更新
            if hasattr(self, 'options_panel'):
                self.options_panel._update_gui_for_error()
                
        except Exception as e:
            self.log(f"エラー状態GUI更新エラー: {e}", "error")
    
    def _update_gui_for_paused(self):
        """一時停止状態のGUI更新"""
        if hasattr(self, 'options_panel'):
            self.options_panel._update_gui_for_paused()
    
    def _update_gui_state_from_thread(self):
        """スレッド状態からGUI状態を更新（頻度制限版）"""
        try:
            # 更新頻度制限（100ms間隔）
            if not hasattr(self, '_last_gui_update_time'):
                self._last_gui_update_time = 0
            
            current_time = time.time()
            if current_time - self._last_gui_update_time < 0.1:  # 100ms間隔
                return
            
            self._last_gui_update_time = current_time
            
            # StateManagerから状態を取得
            is_running = False
            is_paused = False
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                is_running = self.downloader_core.state_manager.is_download_running()
                is_paused = self.downloader_core.state_manager.is_paused()
            
            # 状態に応じてGUIを更新
            if is_running and not is_paused:
                # GUI状態: 実行中
                self._update_gui_for_running()
            elif is_paused:
                # GUI状態: 一時停止
                self._update_gui_for_paused()
            else:
                # GUI状態: アイドル
                self._update_gui_for_idle()
            
            # サブウィンドウのボタン状態も更新
            if hasattr(self, 'progress_panel'):
                self.progress_panel._update_separate_window_button_states()
                
        except Exception as e:
            self.log(f"GUI状態更新エラー: {e}", "error")
            # エラー時はアイドル状態にフォールバック
            try:
                self._update_gui_for_idle()
            except:
                pass  # フォールバック失敗時は何もしない
    
    def update_progress_display(self, url, current, total, title_override=None, status_text_override=None, download_range_info=None):
        """プログレス表示を更新"""
        if hasattr(self, 'progress_panel'):
            self.progress_panel.update_progress_display(url, current, total, title_override, status_text_override, download_range_info=download_range_info)
    
    def show_current_progress_bar(self):
        """現在のプログレスバーを表示"""
        if hasattr(self, 'progress_panel'):
            self.progress_panel.show_current_progress_bar()
    
    def update_current_progress(self, current, total, status="", url=None, download_range_info=None, url_index=None):
        """現在のプログレスを更新"""
        if hasattr(self, 'progress_panel'):
            # ⭐修正: URLが指定されていない場合はcurrent_gallery_urlを使用⭐
            if not url and hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'current_gallery_url') and self.downloader_core.current_gallery_url:
                url = self.downloader_core.current_gallery_url
            
            # ⭐追加: url_indexが指定されていない場合はcurrent_url_indexを取得⭐
            if url_index is None:
                if hasattr(self, 'current_url_index'):
                    url_index = self.current_url_index
                elif hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                    url_index = self.downloader_core.state_manager.get_current_url_index()
            
            self.progress_panel.update_current_progress(current, total, status, url, download_range_info=download_range_info, url_index=url_index)
    
    def update_progress_title(self, url, title):
        """プログレスタイトルを更新"""
        if hasattr(self, 'progress_panel'):
            # ⭐追加: url_indexを取得して渡す⭐
            url_index = None
            if hasattr(self, 'current_url_index'):
                url_index = self.current_url_index
            elif hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                url_index = self.downloader_core.state_manager.get_current_url_index()
            self.progress_panel.update_progress_title(url, title, url_index=url_index)
    
    def _on_sequence_complete(self):
        """シーケンス完了時の処理"""
        try:
            # ダウンロード状態をリセット（StateManager経由）
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                self.downloader_core.state_manager.set_download_running(False)
                self.downloader_core.state_manager.set_paused(False)
            # GUIを更新
            self._update_gui_state_from_thread()
            
            # ダウンローダーコアの完了処理を実行
            if hasattr(self, 'downloader_core'):
                self.downloader_core._on_sequence_complete()
            
            # 経過時間タイマーを停止
            if hasattr(self, 'progress_panel'):
                self.progress_panel._stop_elapsed_time_timer()
                
            self.log("ダウンロードシーケンスが完了しました", "info")
                
        except Exception as e:
            self.log(f"シーケンス完了処理エラー: {e}", "error")
    
    def _handle_download_completion(self, url, save_folder, options):
        """ダウンロード完了処理"""
        if hasattr(self, 'downloader_core'):
            self.downloader_core._handle_download_completion(url, save_folder, options)
    
    def _handle_folder_missing_error(self, url, folder_error):
        """フォルダ削除エラー処理"""
        if hasattr(self, 'downloader_core'):
            self.downloader_core._handle_folder_missing_error(url, folder_error)

    def show_custom_folder_name_hint(self):
        """保存フォルダ名カスタムのヒントを表示（PyQtダイアログ版）"""
        try:
            from gui.dialogs.custom_name_dialog import CustomNameDialog, PYQT5_AVAILABLE
            import tkinter as tk
            from tkinter import messagebox

            if PYQT5_AVAILABLE:
                # PyQt5ダイアログを使用
                current_template = self.custom_folder_name.get() if hasattr(self, 'custom_folder_name') else ""

                # ⭐修正: QApplicationインスタンスを安全に取得または作成⭐
                from PyQt5.QtWidgets import QApplication
                import sys

                # 既存のQApplicationインスタンスを取得
                app = QApplication.instance()
                if app is None:
                    # sys.argvを渡さず空リストで作成（Tkinterとの競合回避）
                    app = QApplication([])

                # タグ変数設定を読み込み
                tag_delimiter = getattr(self, 'tag_delimiter', " ")
                tag_max_length = getattr(self, 'tag_max_length', 0)
                use_space_in_delimiter = getattr(self, 'use_space_in_delimiter', True)

                dialog = CustomNameDialog(
                    None,
                    dialog_type="folder",
                    current_template=current_template,
                    tag_delimiter=tag_delimiter,
                    tag_max_length=tag_max_length,
                    use_space_in_delimiter=use_space_in_delimiter
                )

                # 変数が挿入されたときの処理
                def on_variable_inserted(variable):
                    def update_tkinter_widget():
                        try:
                            if hasattr(self, 'custom_folder_name_entry'):
                                current_text = self.custom_folder_name.get()
                                cursor_pos = self.custom_folder_name_entry.index(tk.INSERT)
                                new_text = current_text[:cursor_pos] + variable + current_text[cursor_pos:]
                                self.custom_folder_name.set(new_text)
                                # カーソル位置を更新
                                new_cursor_pos = cursor_pos + len(variable)
                                self.custom_folder_name_entry.icursor(new_cursor_pos)
                                # テンプレート表示を更新
                                dialog.set_current_template(new_text)
                        except Exception as e:
                            self.log(f"変数挿入時のTkinter更新エラー: {e}", "error")

                    self.root.after(0, update_tkinter_widget)

                # テンプレート出力の処理
                def on_template_output(template):
                    def update_tkinter_widget():
                        try:
                            if hasattr(self, 'custom_folder_name'):
                                self.custom_folder_name.set(template)
                                if hasattr(self, 'custom_folder_name_entry'):
                                    self.custom_folder_name_entry.delete(0, tk.END)
                                    self.custom_folder_name_entry.insert(0, template)
                                    self.custom_folder_name_entry.update_idletasks()
                        except Exception as e:
                            self.log(f"テンプレート出力時のTkinter更新エラー: {e}", "error")

                    self.root.after(0, update_tkinter_widget)

                dialog.variable_inserted.connect(on_variable_inserted)
                dialog.template_output.connect(on_template_output)
                dialog.exec_()

                # タグ変数設定を保存
                self.tag_delimiter = dialog.get_tag_delimiter()
                self.tag_max_length = dialog.get_tag_max_length()
                self.use_space_in_delimiter = dialog.get_use_space_in_delimiter()

            else:
                # PyQt5が利用できない場合は従来のTkinter表示を使用
                messagebox.showinfo(
                    "カスタムフォルダ名命名について",
                    "使用可能な変数（フォルダ名）:\n"
                    "・{title}: ギャラリータイトル\n"
                    "・{artist}: アーティスト名\n"
                    "・{parody}: パロディ名\n"
                    "・{character}: キャラクター名\n"
                    "・{group}: グループ名\n"
                    "・{language}: 言語\n"
                    "・{category}: カテゴリ\n"
                    "・{uploader}: アップローダー\n"
                    "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
                    "・{token}: トークン\n"
                    "・{date}: 投稿日 (YYYY-MM-DD)\n"
                    "・{rating}: 評価\n"
                    "・{pages}: ページ数\n"
                    "・{filesize}: ファイルサイズ\n"
                    "・{tags}: タグ（スペース区切り）\n"
                    "・{female}: femaleタグ（カンマ区切り）\n"
                    "・{female_first}: 最初のfemaleタグ\n"
                    "・{female_1}: 1番目のfemaleタグ\n"
                    "・{female_2}: 2番目のfemaleタグ\n"
                    "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
                    "・{cosplayer_first}: 最初のcosplayerタグ\n"
                    "・{other}: otherタグ（カンマ区切り）\n"
                    "・{other_first}: 最初のotherタグ\n"
                    "・{dl_index}: DLリスト進行番号（1ベース）\n"
                    "・{dl_count}: DLリスト総数\n\n"
                    "例:\n"
                    "・{title}\n"
                    "・{artist}_{title}\n"
                    "・[{category}] {title}\n"
                    "・{date}_{gid}_{title}\n"
                    "・{artist} - {title} [{language}]\n"
                    "・{dl_index:02d}_{title}\n\n"
                    "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。"
                )

        except Exception as e:
            self.log(f"カスタムフォルダ名ヒント表示エラー: {e}", "error")
            # フォールバック: 従来のTkinter表示
            messagebox.showinfo(
                "カスタムフォルダ名命名について",
                "使用可能な変数（フォルダ名）:\n"
                "・{title}: ギャラリータイトル\n"
                "・{artist}: アーティスト名\n"
                "・{parody}: パロディ名\n"
                "・{character}: キャラクター名\n"
                "・{group}: グループ名\n"
                "・{language}: 言語\n"
                "・{category}: カテゴリ\n"
                "・{uploader}: アップローダー\n"
                "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
                "・{token}: トークン\n"
                "・{date}: 投稿日 (YYYY-MM-DD)\n"
                "・{rating}: 評価\n"
                "・{pages}: ページ数\n"
                "・{filesize}: ファイルサイズ\n"
                "・{tags}: タグ（スペース区切り）\n"
                "・{female}: femaleタグ（カンマ区切り）\n"
                "・{female_first}: 最初のfemaleタグ\n"
                "・{female_1}: 1番目のfemaleタグ\n"
                "・{female_2}: 2番目のfemaleタグ\n"
                "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
                "・{cosplayer_first}: 最初のcosplayerタグ\n"
                "・{other}: otherタグ（カンマ区切り）\n"
                "・{other_first}: 最初のotherタグ\n"
                "・{dl_index}: DLリスト進行番号（1ベース）\n"
                "・{dl_count}: DLリスト総数\n\n"
                "例:\n"
                "・{title}\n"
                "・{artist}_{title}\n"
                "・[{category}] {title}\n"
                "・{date}_{gid}_{title}\n"
                "・{artist} - {title} [{language}]\n"
                "・{dl_index:02d}_{title}\n\n"
                "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。"
            )
            
    def show_custom_name_hint(self):
        """カスタムファイル名のヒントを表示（PyQtダイアログ版）"""
        try:
            from gui.dialogs.custom_name_dialog import CustomNameDialog, PYQT5_AVAILABLE
            import tkinter as tk
            from tkinter import messagebox

            if PYQT5_AVAILABLE:
                # PyQt5ダイアログを使用
                current_template = self.custom_name.get() if hasattr(self, 'custom_name') else ""

                # ⭐修正: QApplicationインスタンスを安全に取得または作成⭐
                from PyQt5.QtWidgets import QApplication
                import sys

                # 既存のQApplicationインスタンスを取得
                app = QApplication.instance()
                if app is None:
                    app = QApplication([])  # sys.argvを渡さず空リストで作成

                # タグ変数設定を読み込み
                tag_delimiter = getattr(self, 'tag_delimiter', " ")
                tag_max_length = getattr(self, 'tag_max_length', 0)
                use_space_in_delimiter = getattr(self, 'use_space_in_delimiter', True)

                dialog = CustomNameDialog(
                    None,
                    dialog_type="file",
                    current_template=current_template,
                    tag_delimiter=tag_delimiter,
                    tag_max_length=tag_max_length,
                    use_space_in_delimiter=use_space_in_delimiter
                )

                # 変数が挿入されたときの処理
                def on_variable_inserted(variable):
                    def update_tkinter_widget():
                        try:
                            if hasattr(self, 'custom_name_entry'):
                                current_text = self.custom_name.get()
                                cursor_pos = self.custom_name_entry.index(tk.INSERT)
                                new_text = current_text[:cursor_pos] + variable + current_text[cursor_pos:]
                                self.custom_name.set(new_text)
                                new_cursor_pos = cursor_pos + len(variable)
                                self.custom_name_entry.icursor(new_cursor_pos)
                                dialog.set_current_template(new_text)
                        except Exception as e:
                            self.log(f"変数挿入時のTkinter更新エラー: {e}", "error")

                    self.root.after(0, update_tkinter_widget)

                # テンプレート出力の処理
                def on_template_output(template):
                    def update_tkinter_widget():
                        try:
                            if hasattr(self, 'custom_name'):
                                self.custom_name.set(template)
                                if hasattr(self, 'custom_name_entry'):
                                    self.custom_name_entry.delete(0, tk.END)
                                    self.custom_name_entry.insert(0, template)
                                    self.custom_name_entry.update_idletasks()
                        except Exception as e:
                            self.log(f"テンプレート出力時のTkinter更新エラー: {e}", "error")

                    self.root.after(0, update_tkinter_widget)

                dialog.variable_inserted.connect(on_variable_inserted)
                dialog.template_output.connect(on_template_output)
                dialog.exec_()

                # タグ変数設定を保存
                self.tag_delimiter = dialog.get_tag_delimiter()
                self.tag_max_length = dialog.get_tag_max_length()
                self.use_space_in_delimiter = dialog.get_use_space_in_delimiter()

            else:
                # PyQt5が利用できない場合は従来のTkinter表示
                basic_vars = (
                    "使用可能な変数（ファイル名）:\n"
                    "【基本情報】\n"
                    "・{title}: ギャラリータイトル\n"
                    "・{page}: ページ番号\n"
                    "・{page:02d}: ページ番号（2桁0埋め）\n"
                    "・{page:03d}: ページ番号（3桁0埋め）\n"
                    "・{ext}: 拡張子\n"
                    "・{original_filename}: 元のファイル名（拡張子なし）\n"
                    "・{dl_index}: DLリスト進行番号（1ベース）\n"
                    "・{dl_count}: DLリスト総数\n\n"
                    "【メタデータ】\n"
                    "・{artist}: アーティスト名\n"
                    "・{parody}: パロディ名\n"
                    "・{character}: キャラクター名\n"
                    "・{group}: グループ名\n"
                    "・{language}: 言語\n"
                    "・{category}: カテゴリ\n"
                    "・{uploader}: アップローダー\n"
                    "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
                    "・{token}: トークン\n"
                    "・{date}: 投稿日 (YYYY-MM-DD)\n"
                    "・{rating}: 評価\n"
                    "・{pages}: ページ数\n"
                    "・{filesize}: ファイルサイズ\n"
                    "・{tags}: タグ（スペース区切り）\n"
                    "・{female}: femaleタグ（カンマ区切り）\n"
                    "・{female_first}: 最初のfemaleタグ\n"
                    "・{female_1}: 1番目のfemaleタグ\n"
                    "・{female_2}: 2番目のfemaleタグ\n"
                    "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
                    "・{cosplayer_first}: 最初のcosplayerタグ\n"
                    "・{other}: otherタグ（カンマ区切り）\n"
                    "・{other_first}: 最初のotherタグ\n\n"
                )

                examples = (
                    "【使用例】\n"
                    "・{title}_{page:03d}\n"
                    "・{gid}_{page:02d}_{title}\n"
                    "・[{artist}] {title} - {page:03d}\n"
                    "・{artist}/{title}/{page:03d}\n"
                    "・{category} - {title} ({page:03d})\n"
                    "・{date}_{page:03d}_{original_filename}\n"
                    "・{dl_index:02d}_{page:03d}\n\n"
                    "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。"
                )

                messagebox.showinfo("カスタム命名について", basic_vars + examples)

        except Exception as e:
            self.log(f"カスタムファイル名ヒント表示エラー: {e}", "error")
            # フォールバック: 従来のTkinter表示
            messagebox.showinfo(
                "カスタム命名について",
                "使用可能な変数（ファイル名）:\n"
                "【基本情報】\n"
                "・{title}: ギャラリータイトル（<h1>から取得）\n"
                "・{page_title}: ページタイトル（<title>タグから取得）\n"
                "・{page}: ページ番号\n"
                "・{page:02d}: ページ番号（2桁0埋め）\n"
                "・{page:03d}: ページ番号（3桁0埋め）\n"
                "・{ext}: 拡張子\n"
                "・{original_filename}: 元のファイル名（拡張子なし）\n"
                "・{dl_index}: DLリスト進行番号（1ベース）\n"
                "・{dl_count}: DLリスト総数\n\n"
                "【メタデータ】\n"
                "・{artist}: アーティスト名\n"
                "・{parody}: パロディ名\n"
                "・{character}: キャラクター名\n"
                "・{group}: グループ名\n"
                "・{language}: 言語\n"
                "・{category}: カテゴリ\n"
                "・{uploader}: アップローダー\n"
                "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
                "・{token}: トークン\n"
                "・{date}: 投稿日 (YYYY-MM-DD)\n"
                "・{rating}: 評価\n"
                "・{pages}: ページ数\n"
                "・{filesize}: ファイルサイズ\n"
                "・{tags}: タグ（スペース区切り）\n"
                "・{female}: femaleタグ（カンマ区切り）\n"
                "・{female_first}: 最初のfemaleタグ\n"
                "・{female_1}: 1番目のfemaleタグ\n"
                "・{female_2}: 2番目のfemaleタグ\n"
                "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
                "・{cosplayer_first}: 最初のcosplayerタグ\n"
                "・{other}: otherタグ（カンマ区切り）\n"
                "・{other_first}: 最初のotherタグ\n\n"
                "【使用例】\n"
                "・{title}_{page:03d}\n"
                "・{gid}_{page:02d}_{title}\n"
                "・[{artist}] {title} - {page:03d}\n"
                "・{artist}/{title}/{page:03d}\n"
                "・{category} - {title} ({page:03d})\n"
                "・{date}_{page:03d}_{original_filename}\n"
                "・{dl_index:02d}_{page:03d}\n\n"
                "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。"
            )

    def _is_valid_eh_url(self, url):
        """有効なE-Hentai/ExHentaiのURLかチェック（改善版）"""
        if not url or not isinstance(url, str):
            return False
            
        url = url.strip()
        
        # @で始まるURLの処理
        if url.startswith('@'):
            url = url[1:]
        
        # 基本的なURL形式チェック
        if not url.startswith(('http://', 'https://')):
            return False
        
        # e-hentai.orgまたはexhentai.orgを含むかチェック
        if 'e-hentai.org' in url or 'exhentai.org' in url:
            # ギャラリーURLのパターン（/g/または/s/）
            if '/g/' in url or '/s/' in url:
                return True
        
        return False

    def _reset_to_defaults(self):
        """デフォルト設定に戻す（警告付き）"""
        result = messagebox.askyesno("確認", "すべての設定をデフォルト値に戻しますか？\n（保存先パスは保持されます）")
        if result:
            # デフォルト値の一箇所集約を使用
            self.wait_time.set(self.DEFAULT_VALUES['wait_time'])
            self.sleep_value.set(self.DEFAULT_VALUES['sleep_value'])
            self.save_format.set(self.DEFAULT_VALUES['save_format'])
            self.save_name.set(self.DEFAULT_VALUES['save_name'])
            self.custom_name.set(self.DEFAULT_VALUES['custom_name'])
            self.resize_enabled.set(self.DEFAULT_VALUES['resize_enabled'])
            self.resize_mode.set(self.DEFAULT_VALUES['resize_mode'])
            
            # リサイズ値をデフォルトに戻す
            self.resize_values["height"].set("1024")
            self.resize_values["width"].set("1024")
            self.resize_values["short"].set("1024")
            self.resize_values["long"].set("1024")
            self.resize_values["percentage"].set("80")
            self.resize_values["unified"].set("1600")
            
            # 補完モードとシャープネスをデフォルトに戻す
            self.interpolation_mode.set(self.DEFAULT_VALUES['interpolation_mode'])
            self.sharpness_value.set(self.DEFAULT_VALUES['sharpness_value'])
            
            # その他の設定をデフォルトに戻す
            self.keep_original.set(self.DEFAULT_VALUES['keep_original'])
            self.resize_filename_enabled.set(self.DEFAULT_VALUES['resize_filename_enabled'])
            self.resized_subdir_name.set(self.DEFAULT_VALUES['resized_subdir_name'])
            self.resized_prefix.set(self.DEFAULT_VALUES['resized_prefix'])
            self.resized_suffix.set(self.DEFAULT_VALUES['resized_suffix'])
            self.resize_save_location.set(self.DEFAULT_VALUES['resize_save_location'])
            self.duplicate_folder_mode.set(self.DEFAULT_VALUES['duplicate_folder_mode'])
            self.rename_incomplete_folder.set(self.DEFAULT_VALUES['rename_incomplete_folder'])
            self.incomplete_folder_prefix.set(self.DEFAULT_VALUES['incomplete_folder_prefix'])
            self.compression_enabled.set(self.DEFAULT_VALUES['compression_enabled'])
            self.compression_format.set(self.DEFAULT_VALUES['compression_format'])
            self.compression_delete_original.set(self.DEFAULT_VALUES['compression_delete_original'])
            self.error_handling_mode.set(self.DEFAULT_VALUES['error_handling_mode'])
            self.auto_resume_delay.set(self.DEFAULT_VALUES['auto_resume_delay'])
            self.retry_delay_increment.set(self.DEFAULT_VALUES['retry_delay_increment'])
            self.max_retry_delay.set(self.DEFAULT_VALUES['max_retry_delay'])
            self.max_retry_count.set(self.DEFAULT_VALUES['max_retry_count'])
            self.retry_limit_action.set(self.DEFAULT_VALUES['retry_limit_action'])
            self.first_page_use_title.set(self.DEFAULT_VALUES['first_page_use_title'])
            self.multithread_enabled.set(self.DEFAULT_VALUES['multithread_enabled'])
            self.multithread_count.set(self.DEFAULT_VALUES['multithread_count'])
            self.preserve_animation.set(self.DEFAULT_VALUES['preserve_animation'])
            self.folder_name_mode.set(self.DEFAULT_VALUES['folder_name_mode'])
            self.custom_folder_name.set(self.DEFAULT_VALUES['custom_folder_name'])
            self.first_page_naming_enabled.set(self.DEFAULT_VALUES['first_page_naming_enabled'])
            self.first_page_naming_format.set(self.DEFAULT_VALUES['first_page_naming_format'])
            self.duplicate_file_mode.set(self.DEFAULT_VALUES['duplicate_file_mode'])
            self.skip_count.set(self.DEFAULT_VALUES['skip_count'])
            self.skip_after_count_enabled.set(self.DEFAULT_VALUES['skip_after_count_enabled'])
            self.jpg_quality.set(self.DEFAULT_VALUES['jpg_quality'])
            self.string_conversion_enabled.set(self.DEFAULT_VALUES['string_conversion_enabled'])
            self.advanced_options_enabled.set(self.DEFAULT_VALUES['advanced_options_enabled'])
            self.user_agent_spoofing_enabled.set(self.DEFAULT_VALUES['user_agent_spoofing_enabled'])
            self.httpx_enabled.set(self.DEFAULT_VALUES['httpx_enabled'])
            self.selenium_enabled.set(self.DEFAULT_VALUES['selenium_enabled'])
            self.selenium_session_retry_enabled.set(self.DEFAULT_VALUES['selenium_session_retry_enabled'])
            self.selenium_persistent_enabled.set(self.DEFAULT_VALUES['selenium_persistent_enabled'])
            self.selenium_page_retry_enabled.set(self.DEFAULT_VALUES['selenium_page_retry_enabled'])
            self.selenium_mode.set(self.DEFAULT_VALUES['selenium_mode'])
            self.retry_limit_action.set(self.DEFAULT_VALUES['retry_limit_action'])
            self.download_range_enabled.set(self.DEFAULT_VALUES['download_range_enabled'])
            self.download_range_mode.set(self.DEFAULT_VALUES['download_range_mode'])
            self.download_range_start.set(self.DEFAULT_VALUES['download_range_start'])
            self.download_range_end.set(self.DEFAULT_VALUES['download_range_end'])
            
            # 統合エラーレジューム管理のデフォルト値
            if hasattr(self, 'enhanced_error_handling_enabled'):
                self.enhanced_error_handling_enabled.set(True)  # デフォルトはON
            if hasattr(self, 'enhanced_error_mode'):
                self.enhanced_error_mode.set("auto_resume")
            if hasattr(self, 'retry_strategy'):
                self.retry_strategy.set("exponential")
            if hasattr(self, 'enhanced_max_retry_count'):
                self.enhanced_max_retry_count.set("3")
            if hasattr(self, 'enhanced_retry_delay'):
                self.enhanced_retry_delay.set("5")
            if hasattr(self, 'enhanced_max_delay'):
                self.enhanced_max_delay.set("300")
            if hasattr(self, 'enhanced_resume_age_hours'):
                self.enhanced_resume_age_hours.set("24")
            if hasattr(self, 'selenium_fallback_enabled'):
                self.selenium_fallback_enabled.set(True)
            if hasattr(self, 'selenium_timeout'):
                self.selenium_timeout.set("60")
            
            # 統合エラーレジューム管理の状態を更新
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, '_update_enhanced_error_options'):
                self.options_panel._update_enhanced_error_options()
            
            # 文字列変換ルールをクリア
            if hasattr(self, 'string_conversion_rules'):
                self.string_conversion_rules.clear()
            
            messagebox.showinfo("完了", "デフォルト設定に戻しました。")

    def _save_current_options(self):
        """現在のオプション設定をプリセットとして保存 - Controllerに委譲"""
        self.preset_controller.save_current_options()

    def _sync_gui_with_internal_state(self):
        """起動時にGUIと内部オプション値を強制同期"""
        try:
            # GUIと内部オプションを同期中
            # self.log("GUI状態同期を開始します", "debug")  # DEBUG: 起動時のログを整理

            # ⭐削除: folder_varトレースで自動同期されるため手動同期不要⭐
            # フォルダパスはfolder_varの変更時に自動的に同期される

            # オプションパネルの状態を更新
            if hasattr(self, 'options_panel'):
                self._update_options_panel_state()

                # 高度なオプションの状態を更新
                if hasattr(self.options_panel, '_update_advanced_options_state'):
                    self.options_panel._update_advanced_options_state()

                # エラー統計とレジュームポイントを更新
                if hasattr(self.options_panel, '_update_error_statistics'):
                    self.options_panel._update_error_statistics()
                if hasattr(self.options_panel, '_update_resume_points'):
                    self.options_panel._update_resume_points()

            # Seleniumオプションを同期
            if hasattr(self, 'selenium_enabled') and hasattr(self.options_panel, '_update_selenium_gui_state'):
                self.options_panel._update_selenium_gui_state()

            # エラー処理オプションを同期
            if hasattr(self.options_panel, 'update_error_handling_grayout'):
                self.options_panel.update_error_handling_grayout()

            # Seleniumオプションの状態を同期
            if hasattr(self.options_panel, '_update_selenium_options_state'):
                self.options_panel._update_selenium_options_state()

            # Torrentマネージャーの設定を同期
            if hasattr(self, 'torrent_manager') and hasattr(self.torrent_manager, '_sync_internal_to_gui'):
                self.torrent_manager._sync_internal_to_gui()

            self.log("GUI状態同期が完了しました", "info")

        except Exception as e:
            self.log(f"GUI状態同期エラー: {e}", "error")


    def _auto_save_settings(self):
        """アプリ終了時に設定を自動保存"""
        try:
            settings = {}

            # ウィンドウサイズと位置
            settings['window_geometry'] = self.root.geometry()
            settings['window_state'] = self.root.state()

            # フォルダパス
            # ⭐OptionsManager経由で全オプションを保存⭐
            if hasattr(self, 'options_manager'):
                all_options = self.options_manager.get_all_options()
                settings.update(all_options)
            else:
                # フォールバック（従来の方法）
                settings['folder_path'] = self.folder_var.get()

            # 各設定値を保存
            for key in self.STATE_KEYS:
                if hasattr(self, key):
                    attr = getattr(self, key)
                    if hasattr(attr, 'get'):
                        try:
                            settings[key] = attr.get()
                        except Exception:
                            settings[key] = None
                    else:
                        settings[key] = attr

            with open("default_settings.json", 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.log(f"自動設定保存エラー: {e}", "error")


    def _apply_settings(self, settings):
        """設定を適用"""
        try:
            # ウィンドウサイズと位置
            if settings.get('window_geometry'):
                self.root.geometry(settings['window_geometry'])
            if settings.get('window_state'):
                self.root.state(settings['window_state'])

            # フォルダパス
            if 'folder_path' in settings:
                # ⭐OptionsManager経由で全オプションを読み込み⭐
                if hasattr(self, 'options_manager'):
                    for opt_name, opt_value in settings.items():
                        self.options_manager.set_option_value(opt_name, opt_value)
                else:
                    # フォールバック（従来の方法）
                    self.folder_var.set(settings['folder_path'])

            # resize_valuesの特別な処理
            if isinstance(settings.get('resize_values'), dict):
                for key, value in settings['resize_values'].items():
                    if key in self.resize_values and hasattr(self.resize_values[key], 'set'):
                        try:
                            self.resize_values[key].set(str(value))
                        except Exception as e:
                            self.log(f"resize_values[{key}]設定エラー: {e}", "warning")

            for key, value in settings.items():
                if key in ['window_geometry', 'window_state', 'folder_path', 'resize_values']:
                    continue

                # E-Hentai用：同名ファイル処理はリネーム固定
                if key == 'duplicate_file_mode':
                    self.duplicate_file_mode.set('rename')
                    continue

                if hasattr(self, key):
                    attr = getattr(self, key)
                    if hasattr(attr, 'set'):
                        try:
                            attr.set(value)
                        except Exception as e:
                            self.log(f"設定[{key}]適用エラー: {e}", "warning")
                    else:
                        try:
                            setattr(self, key, value)
                        except Exception as e:
                            self.log(f"設定[{key}]属性設定エラー: {e}", "warning")

        except Exception as e:
            self.log(f"設定適用エラー: {e}", "error")


    def _load_saved_options(self):
        """保存された設定プリセットをロード（Controllerに委譲）"""
        self.preset_controller.load_saved_options()

    def _show_driver_info(self):
        """Chromeドライバ情報を表示（ChromeDriverとChromeのバージョンのみ）"""
        def show_info_thread():
            try:
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                import subprocess
                import os
                import winreg
                
                self.log("【Chromeドライバ】ドライバ情報を確認中...")
                
                # Chromeのバージョンを取得（レジストリから取得を優先）
                chrome_version = None
                chrome_binary_path = None
                
                try:
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                        winreg.CloseKey(key)
                        chrome_version = f"Google Chrome {chrome_version_reg}"
                        try:
                            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                            chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                            winreg.CloseKey(key)
                            if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                chrome_binary_path = chrome_binary_path_reg
                        except:
                            pass
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                            winreg.CloseKey(key)
                            chrome_version = f"Google Chrome {chrome_version_reg}"
                            try:
                                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                                chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                                winreg.CloseKey(key)
                                if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                    chrome_binary_path = chrome_binary_path_reg
                            except:
                                pass
                        except:
                            pass
                except:
                    pass
                
                # レジストリから取得できなかった場合、標準パスから検索
                if not chrome_binary_path:
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                    ]
                    for chrome_path in chrome_paths:
                        if os.path.exists(chrome_path):
                            chrome_binary_path = chrome_path
                            if not chrome_version:
                                try:
                                    result = subprocess.run([chrome_path, '--version'], 
                                                           capture_output=True, text=True, timeout=5)
                                    if result.returncode == 0:
                                        version_output = result.stdout.strip()
                                        if '既存のブラウザ' not in version_output and 'セッション' not in version_output:
                                            chrome_version = version_output
                                except:
                                    pass
                            break
                
                if chrome_version:
                    self.log(f"【Chromeドライバ】Chromeバージョン: {chrome_version.strip()}")
                else:
                    self.log("【Chromeドライバ】Chromeバージョンの取得に失敗しました", "warning")
                
                if chrome_binary_path:
                    self.log(f"【Chromeドライバ】Chromeパス: {chrome_binary_path}")
                else:
                    self.log("【Chromeドライバ】Chromeパスの取得に失敗しました", "warning")
                    
                # ChromeDriverパスを取得
                try:
                    driver_path = ChromeDriverManager().install()
                    driver_path = os.path.normpath(driver_path)
                    self.log(f"【Chromeドライバ】ChromeDriverパス: {driver_path}")
                    
                    # ドライバの詳細情報を取得
                    service = Service(driver_path)
                    self.log(f"【Chromeドライバ】ChromeDriverサービスパス: {service.path}")
                    
                    # 情報をまとめて表示
                    info_text = f"ChromeDriver情報:\n"
                    info_text += f"  パス: {driver_path}\n"
                    if chrome_version:
                        info_text += f"\nChrome情報:\n"
                        info_text += f"  バージョン: {chrome_version.strip()}\n"
                        if chrome_binary_path:
                            info_text += f"  パス: {chrome_binary_path}"
                    
                    messagebox.showinfo("ChromeDriver情報", info_text)
                    
                except Exception as driver_error:
                    self.log(f"【Chromeドライバ】ドライバ情報取得エラー: {driver_error}", "error")
                    messagebox.showerror("エラー", f"ChromeDriver情報取得中にエラーが発生しました:\n{driver_error}")
                    
            except ImportError:
                self.log("【Chromeドライバ】必要なライブラリがインストールされていません", "error")
                messagebox.showerror(
                    "エラー", 
                    "Seleniumライブラリがインストールされていません。\n"
                    "pip install selenium webdriver-manager でインストールしてください。"
                )
            except Exception as e:
                self.log(f"Chromeドライバ情報表示エラー: {e}", "error")
                messagebox.showerror("エラー", f"ドライバ情報表示中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=show_info_thread, daemon=True).start()

    def _remove_driver(self):
        """ChromeDriverを削除"""
        def remove_driver_thread():
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                import os
                
                result = messagebox.askyesno(
                    "ChromeDriver削除", 
                    "現在のChromeDriverを削除しますか？\n"
                    "削除後は次回使用時に自動的に再インストールされます。"
                )
                
                if result:
                    self.log("【Chromeドライバ】ドライバ削除を開始...")
                    
                    try:
                        # ドライバパスを取得
                        driver_path = ChromeDriverManager().install()
                        driver_path = os.path.normpath(driver_path)
                        
                        # ドライバファイルを削除
                        if os.path.exists(driver_path):
                            os.remove(driver_path)
                            self.log(f"【Chromeドライバ】ドライバを削除しました: {driver_path}")
                            messagebox.showinfo("完了", "ChromeDriverを削除しました")
                        else:
                            self.log("【Chromeドライバ】ドライバファイルが見つかりませんでした", "warning")
                            messagebox.showwarning("警告", "ドライバファイルが見つかりませんでした")
                            
                    except Exception as driver_error:
                        self.log(f"【Chromeドライバ】ドライバ削除エラー: {driver_error}", "error")
                        messagebox.showerror("エラー", f"ドライバ削除中にエラーが発生しました:\n{driver_error}")
                else:
                    self.log("【Chromeドライバ】ドライバ削除がキャンセルされました")
                    
            except ImportError:
                self.log("【Chromeドライバ】必要なライブラリがインストールされていません", "error")
                messagebox.showerror(
                    "エラー", 
                    "Seleniumライブラリがインストールされていません。\n"
                    "pip install selenium webdriver-manager でインストールしてください。"
                )
            except Exception as e:
                self.log(f"Chromeドライバ削除エラー: {e}", "error")
                messagebox.showerror("エラー", f"ドライバ削除中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=remove_driver_thread, daemon=True).start()

    def _update_selenium_software(self):
        """Seleniumソフトを更新/インストール"""
        def update_software_thread():
            try:
                import subprocess
                import sys
                
                self.log("【Selenium】Seleniumのインストール状況を確認中...")
                
                # Seleniumがインストールされているか確認
                selenium_installed = False
                selenium_version = None
                try:
                    import selenium
                    selenium_installed = True
                    try:
                        selenium_version = selenium.__version__
                    except:
                        try:
                            from selenium import webdriver
                            selenium_version = webdriver.__version__
                        except:
                            selenium_version = "不明"
                except ImportError:
                    selenium_installed = False
                
                if selenium_installed:
                    action_text = "更新"
                    message_text = f"Seleniumを最新版に更新します。\n\n現在のバージョン: {selenium_version}\n\n更新しますか？"
                else:
                    action_text = "インストール"
                    message_text = f"Seleniumがインストールされていません。\n\nインストールしますか？"
                
                result = messagebox.askyesno(
                    f"Selenium{action_text}",
                    message_text
                )
                
                if not result:
                    self.log(f"【Selenium】ソフト{action_text}がキャンセルされました")
                    return
                
                # pipでインストール/更新
                self.log(f"【Selenium】ソフトを{action_text}中...")
                if selenium_installed:
                    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "selenium"]
                else:
                    cmd = [sys.executable, "-m", "pip", "install", "selenium"]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    # 新しいバージョンを確認
                    try:
                        import selenium
                        new_version = selenium.__version__
                        self.log(f"【Selenium】ソフトの{action_text}が完了しました（バージョン: {new_version}）")
                        messagebox.showinfo("完了", 
                            f"Seleniumの{action_text}が完了しました。\n\n"
                            f"バージョン: {new_version}")
                    except:
                        self.log(f"【Selenium】ソフトの{action_text}が完了しました")
                        messagebox.showinfo("完了", f"Seleniumの{action_text}が完了しました。")
                else:
                    error_msg = result.stderr or result.stdout
                    self.log(f"【Selenium】ソフト{action_text}エラー: {error_msg}", "error")
                    messagebox.showerror("エラー", 
                        f"Seleniumの{action_text}中にエラーが発生しました:\n{error_msg}")
                        
            except Exception as e:
                self.log(f"Seleniumソフト{action_text}エラー: {e}", "error")
                messagebox.showerror("エラー", f"Seleniumソフト{action_text}中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=update_software_thread, daemon=True).start()
    
    def _show_selenium_info(self):
        """Seleniumソフト情報を表示"""
        def show_info_thread():
            try:
                import selenium
                
                self.log("【Selenium】ソフト情報を確認中...")
                
                try:
                    selenium_version = selenium.__version__
                except:
                    try:
                        from selenium import webdriver
                        selenium_version = webdriver.__version__
                    except:
                        selenium_version = "不明"
                
                info_text = f"Seleniumバージョン: {selenium_version}"
                self.log(f"【Selenium】{info_text}")
                messagebox.showinfo("Selenium情報", info_text)
                
            except ImportError:
                self.log("【Selenium】Seleniumがインストールされていません", "error")
                messagebox.showwarning("警告", "Seleniumがインストールされていません。\n「ソフト更新」ボタンでインストールできます。")
            except Exception as e:
                self.log(f"Seleniumソフト情報表示エラー: {e}", "error")
                messagebox.showerror("エラー", f"Seleniumソフト情報表示中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=show_info_thread, daemon=True).start()
    
    def _remove_selenium_software(self):
        """Seleniumソフトを削除"""
        def remove_software_thread():
            try:
                import subprocess
                import sys
                
                result = messagebox.askyesno(
                    "Selenium削除",
                    "Seleniumパッケージをアンインストールします。\n\n"
                    "この操作は取り消せません。\n\n"
                    "削除しますか？"
                )
                
                if not result:
                    self.log("【Selenium】ソフト削除がキャンセルされました")
                    return
                
                self.log("【Selenium】ソフトを削除中...")
                cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "selenium"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    self.log("【Selenium】ソフトの削除が完了しました")
                    messagebox.showinfo("完了", "Seleniumの削除が完了しました。")
                else:
                    error_msg = result.stderr or result.stdout
                    self.log(f"【Selenium】ソフト削除エラー: {error_msg}", "error")
                    messagebox.showerror("エラー", 
                        f"Seleniumの削除中にエラーが発生しました:\n{error_msg}")
                        
            except Exception as e:
                self.log(f"Seleniumソフト削除エラー: {e}", "error")
                messagebox.showerror("エラー", f"Seleniumソフト削除中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=remove_software_thread, daemon=True).start()
    
    def _update_chrome_driver(self):
        """Chromeドライバを更新/インストール（現在のChromeのバージョンに完全に適合したドライバをインストール）"""
        def update_driver_thread():
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options
                from webdriver_manager.chrome import ChromeDriverManager
                import subprocess
                import os
                import winreg
                
                # Chromeのバージョンを確認（レジストリから取得を優先）
                self.log("【Chromeドライバ】Chromeのバージョンを確認中...")
                chrome_version = None
                chrome_binary_path = None
                
                # レジストリからバージョンを取得
                try:
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                        winreg.CloseKey(key)
                        chrome_version = f"Google Chrome {chrome_version_reg}"
                        # レジストリからパスも取得
                        try:
                            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                            chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                            winreg.CloseKey(key)
                            if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                chrome_binary_path = chrome_binary_path_reg
                        except:
                            pass
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                            winreg.CloseKey(key)
                            chrome_version = f"Google Chrome {chrome_version_reg}"
                            # レジストリからパスも取得
                            try:
                                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                                chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                                winreg.CloseKey(key)
                                if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                    chrome_binary_path = chrome_binary_path_reg
                            except:
                                pass
                        except:
                            pass
                except:
                    pass
                
                # レジストリから取得できなかった場合、標準パスから検索
                if not chrome_binary_path:
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                    ]
                    for chrome_path in chrome_paths:
                        if os.path.exists(chrome_path):
                            chrome_binary_path = chrome_path
                            if not chrome_version:
                                try:
                                    result = subprocess.run([chrome_path, '--version'], 
                                                           capture_output=True, text=True, timeout=5)
                                    if result.returncode == 0:
                                        version_output = result.stdout.strip()
                                        if '既存のブラウザ' not in version_output and 'セッション' not in version_output:
                                            chrome_version = version_output
                                except:
                                    pass
                            break
                
                if not chrome_version or not chrome_binary_path:
                    self.log("【Chromeドライバ】Chromeがインストールされていません", "error")
                    messagebox.showerror("エラー", "Chromeがインストールされていません。\nChromeをインストールしてから再試行してください。")
                    return
                
                chrome_version_clean = chrome_version.strip()
                self.log(f"【Chromeドライバ】Chromeバージョン: {chrome_version_clean}")
                
                # 既存のドライバがインストールされているか確認
                driver_installed = False
                current_driver_path = None
                try:
                    cache_path = os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver")
                    if os.path.exists(cache_path):
                        for root, dirs, files in os.walk(cache_path):
                            for file in files:
                                if file == "chromedriver.exe" or file == "chromedriver":
                                    current_driver_path = os.path.join(root, file)
                                    driver_installed = True
                                    break
                            if driver_installed:
                                break
                except:
                    pass
                
                # ダイアログを表示
                if driver_installed:
                    action_text = "更新"
                    message_text = f"現在のChromeのバージョンに完全に適合したChromeDriverに更新します。\n\nChromeバージョン: {chrome_version_clean}\n現在のドライバパス: {current_driver_path or '不明'}\n\nドライバを更新しますか？"
                else:
                    action_text = "インストール"
                    message_text = f"現在のChromeのバージョンに完全に適合したChromeDriverをインストールします。\n\nChromeバージョン: {chrome_version_clean}\n\nドライバをインストールしますか？"
                
                result = messagebox.askyesno(
                    f"ChromeDriver{action_text}",
                    message_text
                )
                
                if not result:
                    self.log(f"【Chromeドライバ】ドライバ{action_text}がキャンセルされました")
                    return
                
                # ドライバのインストール/更新
                # ⭐重要: ChromeDriverManager().install()は自動的に現在のChromeバージョンに適合したドライバをインストールします⭐
                self.log(f"【Chromeドライバ】ドライバを{action_text}中（現在のChromeバージョンに適合したものをインストール）...")
                driver_path = ChromeDriverManager().install()
                driver_path = os.path.normpath(driver_path)
                
                self.log(f"【Chromeドライバ】ドライバパス: {driver_path}")
                
                # ドライバの動作確認
                chrome_options = Options()
                if chrome_binary_path:
                    chrome_options.binary_location = chrome_binary_path
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-position=-32000,-32000")  # 画面外に配置
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-logging")
                chrome_options.add_argument("--log-level=3")  # ログを最小限に
                
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # 動作確認
                driver.get("about:blank")
                window_handles = driver.window_handles
                if not window_handles:
                    driver.quit()
                    raise Exception("Chromeウィンドウが開きませんでした")
                
                driver.quit()
                
                self.log(f"【Chromeドライバ】ドライバの{action_text}が完了しました")
                messagebox.showinfo("完了", 
                    f"ChromeDriverの{action_text}が完了しました。\n\n"
                    f"Chromeバージョン: {chrome_version_clean}\n"
                    f"ドライバパス: {driver_path}\n\n"
                    f"ドライバは正常に動作しています。")
                    
            except ImportError:
                self.log("【Chromeドライバ】必要なライブラリがインストールされていません", "error")
                messagebox.showerror(
                    "エラー", 
                    "Seleniumライブラリがインストールされていません。\n"
                    "pip install selenium webdriver-manager でインストールしてください。"
                )
            except Exception as e:
                self.log(f"Chromeドライバ{action_text}エラー: {e}", "error")
                messagebox.showerror("エラー", f"Chromeドライバ{action_text}中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=update_driver_thread, daemon=True).start()
    
    def _test_selenium_launch(self):
        """Seleniumを起動して最小限の操作をテスト"""
        def test_thread():
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                from selenium.webdriver.chrome.options import Options
                from webdriver_manager.chrome import ChromeDriverManager
                import subprocess
                import os
                import tempfile
                import time
                import socket
                import random
                import shutil
                
                self.log("【Seleniumテスト】テストを開始します...")
                
                # Chromeのバージョンを確認
                # ⭐改善: Chromeバージョン取得を改善（レジストリから取得を優先）⭐
                # Chromeのシングルインスタンス機能により、`chrome.exe --version`を実行すると
                # 既存のChromeプロセス（バックグラウンドプロセスを含む）に接続しようとします。
                # バックグラウンドプロセス（Chromeの自動更新プロセスなど）が起動している場合、
                # 「既存のブラウザ セッションで開いています。」というメッセージが返されます。
                # そのため、レジストリからバージョンを取得する方法を優先します。
                chrome_version = None
                chrome_binary_path = None
                
                # レジストリからバージョンを取得（優先）
                try:
                    import winreg
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                        winreg.CloseKey(key)
                        chrome_version = f"Google Chrome {chrome_version_reg}"
                        # レジストリからパスも取得
                        try:
                            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                            chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                            winreg.CloseKey(key)
                            if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                chrome_binary_path = chrome_binary_path_reg
                        except:
                            pass
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            chrome_version_reg, _ = winreg.QueryValueEx(key, "version")
                            winreg.CloseKey(key)
                            chrome_version = f"Google Chrome {chrome_version_reg}"
                            # レジストリからパスも取得
                            try:
                                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                                chrome_binary_path_reg, _ = winreg.QueryValueEx(key, "path")
                                winreg.CloseKey(key)
                                if chrome_binary_path_reg and os.path.exists(chrome_binary_path_reg):
                                    chrome_binary_path = chrome_binary_path_reg
                            except:
                                pass
                        except:
                            pass
                except:
                    pass
                
                # レジストリから取得できなかった場合、`--version`コマンドを試行
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                ]
                
                if not chrome_binary_path:
                    for chrome_path in chrome_paths:
                        if os.path.exists(chrome_path):
                            chrome_binary_path = chrome_path
                            break
                
                if not chrome_version:
                    for chrome_path in chrome_paths:
                        if os.path.exists(chrome_path):
                            try:
                                result = subprocess.run([chrome_path, '--version'], 
                                                       capture_output=True, text=True, timeout=5)
                                if result.returncode == 0:
                                    version_output = result.stdout.strip()
                                    # 「既存のブラウザ セッションで開いています。」というメッセージを除外
                                    if '既存のブラウザ' not in version_output and 'セッション' not in version_output:
                                        chrome_version = version_output
                                        if not chrome_binary_path:
                                            chrome_binary_path = chrome_path
                                        break
                            except:
                                continue
                
                if not chrome_binary_path:
                    self.log("【Seleniumテスト】Chromeがインストールされていません", "error")
                    messagebox.showerror("エラー", "Chromeがインストールされていません。\nChromeをインストールしてから再試行してください。")
                    return
                
                self.log(f"【Seleniumテスト】Chromeバージョン: {chrome_version.strip()}")
                
                # テストモード設定を取得
                test_minimal = getattr(self, 'selenium_test_minimal_options', None)
                test_minimal = test_minimal.get() if test_minimal and hasattr(test_minimal, 'get') else False
                
                test_no_headless = getattr(self, 'selenium_test_no_headless', None)
                test_no_headless = test_no_headless.get() if test_no_headless and hasattr(test_no_headless, 'get') else False
                
                cleanup_temp = getattr(self, 'selenium_cleanup_temp', None)
                cleanup_temp = cleanup_temp.get() if cleanup_temp and hasattr(cleanup_temp, 'get') else True
                
                # 一時ディレクトリのクリーンアップ
                if cleanup_temp:
                    temp_dir = tempfile.gettempdir()
                    try:
                        for item in os.listdir(temp_dir):
                            item_path = os.path.join(temp_dir, item)
                            if os.path.isdir(item_path) and item.startswith('selenium_chrome_'):
                                try:
                                    shutil.rmtree(item_path, ignore_errors=True)
                                    self.log(f"【Seleniumテスト】古い一時ディレクトリを削除しました: {item_path}", "debug")
                                except Exception:
                                    pass
                    except Exception as e:
                        self.log(f"【Seleniumテスト】一時ディレクトリのクリーンアップ中にエラー: {e}", "debug")
                
                # ChromeDriverを取得（カスタムパスが指定されている場合はそれを使用）
                custom_driver_path = getattr(self, 'selenium_driver_path', None)
                if custom_driver_path and hasattr(custom_driver_path, 'get'):
                    custom_path = custom_driver_path.get().strip()
                    if custom_path and os.path.exists(custom_path):
                        driver_path = os.path.normpath(custom_path)
                        self.log(f"【Seleniumテスト】カスタムChromeDriverパスを使用: {driver_path}")
                    else:
                        self.log("【Seleniumテスト】指定されたChromeDriverパスが見つかりません。自動検出を使用します。", "warning")
                        driver_path = ChromeDriverManager().install()
                        driver_path = os.path.normpath(driver_path)
                        self.log(f"【Seleniumテスト】ChromeDriverパス（自動検出）: {driver_path}")
                else:
                    self.log("【Seleniumテスト】ChromeDriverを取得中...")
                    driver_path = ChromeDriverManager().install()
                    driver_path = os.path.normpath(driver_path)
                    self.log(f"【Seleniumテスト】ChromeDriverパス: {driver_path}")
                
                # Chromeオプションの設定
                chrome_options = Options()
                if chrome_binary_path:
                    chrome_options.binary_location = chrome_binary_path
                
                # ユーザーデータディレクトリ
                user_data_dir = os.path.join(tempfile.gettempdir(), f"selenium_test_{os.getpid()}_{int(time.time() * 1000)}")
                os.makedirs(user_data_dir, exist_ok=True)
                chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
                
                # リモートデバッグポート
                remote_debugging_port = None
                for _ in range(10):
                    port = random.randint(9000, 9999)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.1)
                    try:
                        result = sock.connect_ex(('127.0.0.1', port))
                        sock.close()
                        if result != 0:
                            remote_debugging_port = port
                            break
                    except Exception:
                        sock.close()
                        remote_debugging_port = port
                        break
                
                if remote_debugging_port is None:
                    remote_debugging_port = 9222
                
                chrome_options.add_argument(f"--remote-debugging-port={remote_debugging_port}")
                
                # テストモードに応じてオプションを設定
                if test_minimal:
                    if not test_no_headless:
                        chrome_options.add_argument("--headless")
                    chrome_options.add_argument("--no-sandbox")
                else:
                    if not test_no_headless:
                        chrome_options.add_argument("--headless")
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument("--disable-dev-shm-usage")
                    chrome_options.add_argument("--disable-gpu")
                    chrome_options.add_argument("--window-size=1920,1080")
                
                # ドライバーを起動
                self.log("【Seleniumテスト】Chromeを起動中...")
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                try:
                    # ウィンドウハンドルの確認
                    time.sleep(0.5)
                    handles = driver.window_handles
                    if not handles:
                        raise Exception("Chromeウィンドウが開いていません")
                    
                    self.log(f"【Seleniumテスト】Chromeが正常に起動しました（ウィンドウ数: {len(handles)}）")
                    
                    # 最小限の操作をテスト
                    self.log("【Seleniumテスト】テストページにアクセス中...")
                    driver.get("about:blank")
                    time.sleep(0.5)
                    
                    current_url = driver.current_url
                    self.log(f"【Seleniumテスト】現在のURL: {current_url}")
                    
                    # タイトルを取得
                    title = driver.title
                    self.log(f"【Seleniumテスト】ページタイトル: {title}")
                    
                    self.log("【Seleniumテスト】✅ テストが正常に完了しました")
                    messagebox.showinfo("テスト完了", 
                        f"Seleniumテストが正常に完了しました。\n\n"
                        f"Chromeバージョン: {chrome_version.strip()}\n"
                        f"ChromeDriverパス: {driver_path}\n"
                        f"ウィンドウ数: {len(handles)}\n"
                        f"現在のURL: {current_url}\n\n"
                        f"Chromeは正常に起動しています。")
                    
                except Exception as test_error:
                    self.log(f"【Seleniumテスト】テスト中にエラー: {test_error}", "error")
                    messagebox.showerror("テストエラー", 
                        f"Seleniumテスト中にエラーが発生しました:\n\n{test_error}\n\n"
                        f"詳細はログを確認してください。")
                finally:
                    try:
                        driver.quit()
                        self.log("【Seleniumテスト】Chromeを終了しました")
                    except Exception as e:
                        self.log(f"【Seleniumテスト】Chrome終了エラー: {e}", "warning")
                    
                    # 一時ディレクトリをクリーンアップ
                    try:
                        if os.path.exists(user_data_dir):
                            shutil.rmtree(user_data_dir, ignore_errors=True)
                    except:
                        pass
                        
            except ImportError:
                self.log("【Seleniumテスト】必要なライブラリがインストールされていません", "error")
                messagebox.showerror("エラー", 
                    "Seleniumライブラリがインストールされていません。\n"
                    "pip install selenium webdriver-manager でインストールしてください。")
            except Exception as e:
                self.log(f"【Seleniumテスト】テストエラー: {e}", "error")
                messagebox.showerror("エラー", f"Seleniumテスト中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=test_thread, daemon=True).start()
    
    def _auto_detect_selenium_paths(self):
        """ChromeDriverとChromeのパスを自動検出して入力"""
        def detect_paths_thread():
            try:
                import os
                import winreg
                from webdriver_manager.chrome import ChromeDriverManager
                
                self.log("【Selenium】パスを自動検出中...")
                
                # ChromeDriverパスの検出
                driver_path = None
                try:
                    driver_path = ChromeDriverManager().install()
                    driver_path = os.path.normpath(driver_path)
                    if driver_path and os.path.exists(driver_path):
                        self.selenium_driver_path.set(driver_path)
                        self.log(f"【Selenium】ChromeDriverパスを検出: {driver_path}")
                    else:
                        self.log("【Selenium】ChromeDriverパスの検出に失敗しました", "warning")
                except Exception as e:
                    self.log(f"【Selenium】ChromeDriverパス検出エラー: {e}", "warning")
                
                # Chromeパスの検出
                chrome_path = None
                try:
                    # レジストリから取得を優先
                    try:
                        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
                        chrome_path, _ = winreg.QueryValueEx(key, "path")
                        winreg.CloseKey(key)
                    except:
                        try:
                            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon")
                            chrome_path, _ = winreg.QueryValueEx(key, "path")
                            winreg.CloseKey(key)
                        except:
                            pass
                    
                    # レジストリから取得できなかった場合、標準パスから検索
                    if not chrome_path or not os.path.exists(chrome_path):
                        chrome_paths = [
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                        ]
                        for path in chrome_paths:
                            if os.path.exists(path):
                                chrome_path = path
                                break
                    
                    if chrome_path and os.path.exists(chrome_path):
                        self.selenium_chrome_path.set(chrome_path)
                        self.log(f"【Selenium】Chromeパスを検出: {chrome_path}")
                    else:
                        self.log("【Selenium】Chromeパスの検出に失敗しました", "warning")
                except Exception as e:
                    self.log(f"【Selenium】Chromeパス検出エラー: {e}", "warning")
                
                if driver_path and chrome_path:
                    messagebox.showinfo("完了", 
                        f"パスの自動検出が完了しました。\n\n"
                        f"ChromeDriver: {driver_path}\n"
                        f"Chrome: {chrome_path}")
                elif driver_path or chrome_path:
                    messagebox.showwarning("部分的な検出", 
                        f"一部のパスのみ検出できました。\n\n"
                        f"ChromeDriver: {driver_path or '検出失敗'}\n"
                        f"Chrome: {chrome_path or '検出失敗'}")
                else:
                    messagebox.showerror("エラー", "パスの自動検出に失敗しました。\n手動でパスを指定してください。")
                    
            except Exception as e:
                self.log(f"Seleniumパス自動検出エラー: {e}", "error")
                messagebox.showerror("エラー", f"パス自動検出中にエラーが発生しました:\n{e}")
        
        # 非同期で実行
        threading.Thread(target=detect_paths_thread, daemon=True).start()
    
    def _set_url_incomplete_style(self, url):
        """URL不完全スタイル設定"""
        if hasattr(self, 'url_panel'):
            # url_panelのupdate_url_backgroundメソッドを使用
            self.url_panel.update_url_background(url)
    
    def _update_all_url_backgrounds(self):
        """全URL背景更新"""
        if hasattr(self, 'url_panel'):
            self.url_panel._update_all_url_backgrounds()
    
    def _start_compression_task(self, folder_path, url=None):
        """圧縮タスク開始"""
        if hasattr(self, 'downloader_core'):
            self.downloader_core._start_compression_task(folder_path, url)
    
    def update_url_background(self, url):
        """
        URL背景更新（Treeview統合版）
        
        ⭐フェーズ3: Treeviewのステータス更新を優先⭐
        """
        # Treeviewのステータス更新を優先
        if hasattr(self, 'download_list_widget'):
            # StateManagerからステータスを取得
            normalized_url = self.normalize_url(url)
            url_status = self.state_manager.get_url_status(normalized_url)
            
            # ステータスに応じてTreeviewを更新
            if url_status == 'completed':
                self.download_list_widget.update_status(url, "completed")
            elif url_status == 'skipped':
                self.download_list_widget.update_status(url, "skipped")
            elif url_status == 'error':
                self.download_list_widget.update_status(url, "error")
            elif url_status == 'downloading':
                self.download_list_widget.update_status(url, "downloading")
        
        # 既存のTextウィジェットも更新（並行動作）
        if hasattr(self, 'url_panel'):
            return self.url_panel.update_url_background(url)
    
    def normalize_url(self, url):
        """URL正規化"""
        if hasattr(self, 'url_utils'):
            return self.url_utils.normalize_url(url)
    
    def _handle_download_error(self, url, error):
        """ダウンロードエラー処理"""
        if hasattr(self, 'downloader_core'):
            self.downloader_core._handle_download_error(url, error)
    
    def get_manga_title(self, soup):
        """マンガタイトルの取得（日本語優先）"""
        try:
            # 日本語タイトルを優先的に取得
            jp_title_elem = soup.find('h1', {'id': 'gj'})
            if jp_title_elem:
                jp_title = jp_title_elem.text.strip()
                if jp_title:
                    return self.sanitize_filename(jp_title)
            
            # 日本語タイトルがない場合は英語タイトル
            en_title_elem = soup.find('h1', {'id': 'gn'})
            if en_title_elem:
                en_title = en_title_elem.text.strip()
                if en_title:
                    return self.sanitize_filename(en_title)
            
            return "Unknown Title"
        except Exception as e:
            self.log(f"タイトル取得エラー: {e}", "error")
            return "Unknown Title"
    
    def _create_menu_bar(self):
        """メニューバーを作成"""
        try:
            menubar = tk.Menu(self.root)
            self.root.config(menu=menubar)
            
            # ファイルメニュー
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="ファイル", menu=file_menu)
            file_menu.add_command(label="バックアップ作成", command=self._create_backup)
            file_menu.add_command(label="バックアップから復元", command=self._restore_from_backup)
            file_menu.add_separator()
            file_menu.add_command(label="設定プリセット保存", command=self._save_current_options)
            file_menu.add_command(label="設定プリセット読み込み", command=self._load_saved_options)
            file_menu.add_separator()
            file_menu.add_command(label="未完了URLのみバックアップ", command=self._backup_incomplete_urls)
            file_menu.add_separator()
            file_menu.add_command(label="終了", command=self.on_closing)
            
            # ヘルプメニュー
            help_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="ヘルプ", menu=help_menu)
            help_menu.add_command(label="システム情報", command=self._show_system_info)
            help_menu.add_command(label="アバウト", command=self._show_about_dialog)
            
        except Exception as e:
            print(f"メニューバー作成エラー: {e}")

    def sanitize_filename(self, filename):
        """ファイル名の無効文字を置換（文字列変換対応）"""
        try:
            if not filename:
                return "untitled"
            
            # 文字列変換ルールを適用
            if hasattr(self, 'string_conversion_enabled') and self.string_conversion_enabled.get():
                filename = self._apply_string_conversion(filename)
            
            # 既存の無効文字置換処理
            import re
            invalid_chars = r'[\\/:*?"<>|]'
            filename = re.sub(invalid_chars, '_', filename)
            
            # 連続するアンダースコースを単一に
            filename = re.sub(r'_+', '_', filename)
            
            # 先頭・末尾のドットやスペースを削除
            filename = filename.strip(' .')
            
            return filename or "untitled"
                
        except Exception as e:
            self.log(f"ファイル名変換エラー: {e}", "error")
            return "untitled"
    
    # ========== バックアップシステム ==========
    
    def _create_backup(self):
        """拡張バックアップの作成（再開ポイント、URL状態、ダウンロード進捗を含む）"""
        try:
            from datetime import datetime
            from tkinter import filedialog, messagebox
            import json
            import shutil
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f"backup_{timestamp}"
            
            backup_path = filedialog.askdirectory(title="バックアップ保存先を選択")
            if not backup_path:
                return
            
            # メインウィンドウのフォーカスを維持
            self.root.focus_force()

            full_backup_path = os.path.join(backup_path, backup_dir)
            os.makedirs(full_backup_path, exist_ok=True)
            
            # 1. 設定ファイルをバックアップ
            settings_path = self.SETTINGS_FILENAME
            if os.path.exists(settings_path):
                shutil.copy2(settings_path, os.path.join(full_backup_path, "settings.json"))
            
            # 2. URLリストをバックアップ
            url_content = self.url_text.get("1.0", tk.END).strip()
            if url_content:
                url_list_path = os.path.join(full_backup_path, "url_list.txt")
                with open(url_list_path, 'w', encoding='utf-8') as f:
                    f.write(url_content)
            
            # 3. ログをバックアップ
            log_content = self.log_text.get("1.0", tk.END)
            log_file_path = os.path.join(full_backup_path, "current_log.txt")
            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            # 4. **拡張: 再開ポイントとURL状態をバックアップ**
            # StateManagerから状態を取得
            is_running = self.downloader_core.state_manager.is_download_running() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            is_paused = self.downloader_core.state_manager.is_paused() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            url_status = self.downloader_core.state_manager.download_state.url_status if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else {}
            state_data = {
                'download_state': {
                    'is_running': is_running,
                    'paused': is_paused,
                    'current_url_index': self.current_url_index if hasattr(self, 'current_url_index') else 0,
                    'url_status': dict(url_status) if url_status else {}
                },
                'resume_points': {},
                'managed_folders': {},
                'incomplete_urls': [],
                'timestamp': time.time()
            }
            
            # ダウンローダーコアから再開ポイントを取得
            if hasattr(self, 'downloader_core'):
                # resume_point（単数形）からresume_points（複数形）を作成
                if hasattr(self.downloader_core, 'resume_point') and self.downloader_core.resume_point:
                    # 単一のresume_pointを辞書形式に変換
                    url = self.downloader_core.resume_point.get('url', '')
                    if url:
                        state_data['resume_points'] = {url: self.downloader_core.resume_point}
                elif hasattr(self.downloader_core, 'resume_points'):
                    state_data['resume_points'] = dict(self.downloader_core.resume_points)
                if hasattr(self.downloader_core, 'managed_folders'):
                    state_data['managed_folders'] = dict(self.downloader_core.managed_folders)
                if hasattr(self.downloader_core, 'incomplete_urls'):
                    state_data['incomplete_urls'] = list(self.downloader_core.incomplete_urls)
                
                # 完了状態の追跡を追加
                state_data['completion_state'] = {
                    'sequence_complete_executed': getattr(self.downloader_core, '_sequence_complete_executed', False),
                    'current_gallery_url': getattr(self.downloader_core, 'current_gallery_url', None),
                    'current_image_page_url': getattr(self.downloader_core, 'current_image_page_url', None),
                    'current_save_folder': getattr(self.downloader_core, 'current_save_folder', None),
                    'current_page': getattr(self.downloader_core, 'current_page', 0),
                    'current_total': getattr(self.downloader_core, 'current_total', 0),
                    # ⭐重要フラグを追加⭐
                    'error_occurred': getattr(self.downloader_core, 'error_occurred', False),
                    'gallery_completed': getattr(self.downloader_core, 'gallery_completed', False),
                    'skip_completion_check': getattr(self.downloader_core, 'skip_completion_check', False)
                }
                
                # Selenium状態の追跡を追加
                state_data['selenium_state'] = {
                    'enabled_for_retry': getattr(self.downloader_core, 'selenium_enabled_for_retry', False),
                    'scope': getattr(self.downloader_core, 'selenium_scope', 'page'),
                    'enabled_url': getattr(self.downloader_core, 'selenium_enabled_url', None)
                }
                
                # 圧縮状態の追跡を追加
                state_data['compression_state'] = {
                    'in_progress': getattr(self.downloader_core, '_compression_in_progress', False),
                    'target_folder': getattr(self.downloader_core, '_compression_target_folder', None),
                    'target_url': getattr(self.downloader_core, '_compression_target_url', None)
                }
            
            # 再開ポイントファイルに保存
            resume_point_path = os.path.join(full_backup_path, "resume_points.json")
            with open(resume_point_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            
            # 5. 未完了URLのみをバックアップ（Treeview対応）
            incomplete_urls = []
            if hasattr(self, 'download_list_widget'):
                # ⭐修正: DLリスト（Treeview）から取得⭐
                all_items = self.download_list_widget.controller.get_all_items()
                for item in all_items:
                    if item.status.value not in ["completed", "skipped"]:
                        incomplete_urls.append(item.url)
            elif url_content:
                # フォールバック: Textウィジェットから取得
                urls = self._parse_urls_from_text(url_content)
                for url in urls:
                    # ⭐修正: StateManagerから取得⭐
                    if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                        status = self.downloader_core.state_manager.get_url_status(url)
                    else:
                        status = self.url_status.get(url, "") if hasattr(self, 'url_status') else ""
                    if status not in ["completed", "skipped"]:
                        incomplete_urls.append(url)
            
            if incomplete_urls:
                incomplete_urls_path = os.path.join(full_backup_path, "incomplete_urls.txt")
                with open(incomplete_urls_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(incomplete_urls))
            
            self.log(f"バックアップ作成完了: {full_backup_path}")
            messagebox.showinfo("バックアップ完了", 
                f"バックアップを作成しました:\n{full_backup_path}\n\n"
                f"含まれる内容:\n"
                f"- 設定ファイル\n"
                f"- URLリスト ({len(url_content.split(chr(10)))}件)\n"
                f"- 未完了URLリスト ({len(incomplete_urls)}件)\n"
                f"- ログファイル\n"
                f"- 再開ポイント・ダウンロード状態")
            
        except Exception as e:
            self.log(f"バックアップ作成エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの作成に失敗しました:\n{e}")
    
    def _restore_from_backup(self):
        """拡張バックアップからの復元（再開ポイント、URL状態、ダウンロード進捗を復元）"""
        try:
            from tkinter import filedialog, messagebox
            import json
            
            backup_path = filedialog.askdirectory(title="バックアップフォルダを選択")
            if not backup_path:
                return

            # ダウンロード実行中の場合は警告
            is_running = self.downloader_core.state_manager.is_download_running() if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager') else False
            if is_running:
                response = messagebox.askyesno(
                    "警告",
                    "ダウンロード実行中です。バックアップを復元するとダウンロードが中断されます。\n続行しますか？"
                )
                if not response:
                    return
                
                # ダウンロード停止
                if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                    self.downloader_core.state_manager.set_download_running(False)
                    self.downloader_core.state_manager.set_paused(True)
                if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'stop_flag'):
                    self.downloader_core.stop_flag.set()
            
            settings_backup = os.path.join(backup_path, "settings.json")
            url_list_backup = os.path.join(backup_path, "url_list.txt")
            current_log_backup = os.path.join(backup_path, "current_log.txt")
            resume_point_backup = os.path.join(backup_path, "resume_points.json")
            
            restored_files = []
            
            # 1. 設定ファイルを復元
            if os.path.exists(settings_backup):
                try:
                    self._load_settings_from_file(settings_backup)
                    restored_files.append("設定ファイル")
                except Exception as e:
                    self.log(f"設定ファイルの復元に失敗: {e}", "warning")
            
            # 2. URLリストを復元
            if os.path.exists(url_list_backup):
                try:
                    with open(url_list_backup, 'r', encoding='utf-8') as f:
                        url_content = f.read()
                    
                    self.url_text.delete("1.0", tk.END)
                    if url_content.strip():
                        self.url_text.insert("1.0", url_content)
                    
                    restored_files.append("URLリスト")
                except Exception as e:
                    self.log(f"URLリストの復元に失敗: {e}", "warning")
            
            # 3. ログファイルを復元
            if os.path.exists(current_log_backup):
                try:
                    with open(current_log_backup, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    self.log_text.config(state='normal')
                    self.log_text.delete("1.0", tk.END)
                    self.log_text.insert("1.0", log_content)
                    self.log_text.config(state='disabled')
                    restored_files.append("ログファイル")
                except Exception as e:
                    self.log(f"ログファイルの復元に失敗: {e}", "warning")
            
            # 4. **拡張: 再開ポイントとURL状態を復元**
            if os.path.exists(resume_point_backup):
                try:
                    with open(resume_point_backup, 'r', encoding='utf-8') as f:
                        state_data = json.load(f)
                    
                    # ダウンロード状態を中断状態として復元
                    download_state = state_data.get('download_state', {})
                    was_running = download_state.get('is_running', False)
                    was_paused = download_state.get('paused', False)
                    
                    # エラー状態または実行中だった場合は中断状態として復元
                    if was_running or was_paused:
                        # StateManagerの状態を復元
                        if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                            self.downloader_core.state_manager.set_download_running(False)
                            self.downloader_core.state_manager.set_paused(True)
                        self.log("バックアップ: ダウンロードが中断状態として復元されました", "info")
                            # StateManager状態を復元
                    
                    # URL状態を復元
                    self.url_status = download_state.get('url_status', {})
                    self.current_url_index = download_state.get('current_url_index', 0)
                    
                    # ダウンローダーコアに再開ポイントを復元
                    if hasattr(self, 'downloader_core'):
                        if 'resume_points' in state_data:
                            # resume_points（複数形）からresume_point（単数形）を作成
                            resume_points = state_data['resume_points']
                            if resume_points:
                                # 最初の復帰ポイントを使用
                                url, resume_data = next(iter(resume_points.items()))
                                self.downloader_core.resume_point = resume_data
                                # resume_point復元
                            # parentにもresume_pointsを設定（resume_downloadで参照されるため）
                            self.resume_points = state_data['resume_points']
                            # resume_points復元
                        if 'managed_folders' in state_data:
                            self.downloader_core.managed_folders = state_data['managed_folders']
                        if 'incomplete_urls' in state_data:
                            self.downloader_core.incomplete_urls = set(state_data['incomplete_urls'])
                        
                        # StateManagerにも状態を反映
                        if hasattr(self.downloader_core, 'state_manager'):
                            # ⭐修正: StateManagerから取得（既にStateManagerで管理されているため不要）⭐
                            # StateManagerが既にurl_statusを管理しているため、復元は不要
                            self.downloader_core.state_manager.set_current_url_index(self.current_url_index)
                    
                    # GUIを復元（スレッド状態から）
                    self._restore_gui_from_state()
                    
                    # URL背景色を更新
                    if hasattr(self, 'url_panel'):
                        self.root.after(100, self.url_panel._update_all_url_backgrounds)
                    
                    # 圧縮状態の特別処理
                    if hasattr(self, 'downloader_core') and getattr(self.downloader_core, '_compression_in_progress', False):
                        self.log("バックアップ復元: 圧縮処理が実行中でした。圧縮状態をリセットします。", "info")
                        self.downloader_core._compression_in_progress = False
                        self.downloader_core._compression_target_folder = None
                        self.downloader_core._compression_target_url = None
                    
                    # GUI状態を更新（再開ボタンを有効にするため）
                    self.root.after(200, self._update_gui_state_from_thread)
                    
                    restored_files.append("再開ポイント・ダウンロード状態")
                except Exception as e:
                    self.log(f"再開ポイントの復元に失敗: {e}", "warning")
            
            if restored_files:
                self.log(f"バックアップから復元: {', '.join(restored_files)}")
                messagebox.showinfo("復元完了", 
                    f"以下のファイルを復元しました:\n{chr(10).join(restored_files)}\n\n"
                    f"ダウンロードは中断状態として復元されました。\n"
                    f"再開ボタンで続きからダウンロードできます。")
            else:
                messagebox.showwarning("復元失敗", "バックアップファイルが見つかりませんでした。")
            
        except Exception as e:
            self.log(f"バックアップ復元エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの復元に失敗しました:\n{e}")
    
    def _restore_gui_from_state(self):
        """スレッド状態からGUIを復元"""
        try:
            # スレッド状態からGUI状態を更新
            self._update_gui_state_from_thread()
            
            # プログレスバーは現在の状態に応じて表示/非表示
            # （再開時に自動的に更新されるため、ここでは何もしない）
            
        except Exception as e:
            self.log(f"GUI復元エラー: {e}", "error")
    
    def clear_all_data(self):
        """全データをクリア（初期状態に戻す）"""
        try:
            from tkinter import messagebox
            import time
            
            # ⭐1. ダウンロード中なら即座に強制停止⭐
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                state_manager = self.downloader_core.state_manager
                download_thread = state_manager.get_download_thread()
                
                # ⭐修正: FutureオブジェクトとThreadオブジェクトの両方に対応⭐
                is_running = False
                if download_thread:
                    if hasattr(download_thread, '_state'):  # Future object
                        is_running = (download_thread._state == 'RUNNING')
                    elif hasattr(download_thread, 'is_alive'):  # Thread object
                        is_running = download_thread.is_alive()
                
                if is_running:
                    self.log("⚠️ ダウンロードを強制停止しています...", "warning")
                    
                    # 停止フラグを設定（メソッド経由）
                    state_manager.set_download_running(False)
                    state_manager.set_paused(False)
                    state_manager.set_stop_flag()
                    
                    # スレッド参照を即座に破棄（バックグラウンドで終了）
                    state_manager.set_download_thread(None)
                    self.log("✅ ダウンロードスレッドを強制停止しました", "info")
                    
                    # GUIを即座に更新（アイドル状態に）
                    if hasattr(self, '_update_gui_for_idle'):
                        self._update_gui_for_idle()
            
            # ⭐2. 確認ダイアログ⭐
            response = messagebox.askyesno(
                "確認",
                "全てのデータをクリアしますか？\n\n"
                "- URLリスト\n"
                "- ダウンロード状態\n"
                "- プログレスバー\n"
                "- ログ\n\n"
                "この操作は元に戻せません。"
            )
            
            if not response:
                return
            
            # URLリストをクリア
            if hasattr(self, 'url_text'):
                self.url_text.delete("1.0", tk.END)
            
            # ⭐追加: DLリストをクリア（force=Trueで完了済みURLも削除）⭐
            if hasattr(self, 'download_list_widget'):
                try:
                    deleted_count = self.download_list_widget.clear_all(force=True)
                    self.log(f"✅ DLリストをクリアしました（{deleted_count}件削除）", "info")
                except Exception as e:
                    self.log(f"DLリストクリアエラー: {e}", "error")
            
            # プログレスバーをクリア
            if hasattr(self, 'progress_panel'):
                try:
                    self.progress_panel.clear_all_progress_bars()
                except Exception as e:
                    self.log(f"プログレスバークリアエラー: {e}", "error")
            
            # ログをクリア（エラー発生前のメッセージも含めて）
            if hasattr(self, 'log_text'):
                self.log_text.config(state='normal')
                self.log_text.delete("1.0", tk.END)
                self.log_text.config(state='disabled')
            
            # ⭐状態管理をクリア（StateManager経由）⭐
            if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                state_manager = self.downloader_core.state_manager
                
                # フラグ類をリセット
                state_manager.set_download_running(False)
                state_manager.set_paused(False)
                state_manager.set_pause_requested(False)
                state_manager.set_current_url_index(0)
                state_manager.set_skip_requested_url(None)
                state_manager.set_restart_requested_url(None)
                state_manager.reset_stop_flag()
                state_manager.set_download_thread(None)
                
                # 状態データをクリア
                with state_manager._state_lock:
                    state_manager.download_state.url_status.clear()
                    state_manager.download_state.url_incomplete_flags.clear()
                    state_manager.download_state.progress_bars.clear()
                    state_manager.download_state.resume_points.clear()
                    state_manager.download_state.current_resume_point_url = None
                    state_manager.download_state.elapsed_time_start = None
                    state_manager.download_state.elapsed_time_paused_start = None
                    state_manager.download_state.total_elapsed_seconds = 0.0
                    state_manager.download_state.total_paused_time = 0.0
            
            # 後方互換性のため self.url_status もクリア
            self.url_status = {}
            self.current_url_index = 0
            
            # ダウンローダーコアの状態をクリア（必要最小限）
            if hasattr(self, 'downloader_core'):
                # フォルダ管理
                if hasattr(self.downloader_core, 'managed_folders'):
                    self.downloader_core.managed_folders = {}
                if hasattr(self.downloader_core, 'incomplete_folders'):
                    self.downloader_core.incomplete_folders = set()
                if hasattr(self.downloader_core, 'renamed_folders'):
                    self.downloader_core.renamed_folders = set()
                
                # 現在のダウンロード情報をクリア
                if hasattr(self.downloader_core, 'current_save_folder'):
                    self.downloader_core.current_save_folder = None
                if hasattr(self.downloader_core, 'current_gallery_title'):
                    self.downloader_core.current_gallery_title = None
                if hasattr(self.downloader_core, 'current_gallery_url'):
                    self.downloader_core.current_gallery_url = None
                
                # エラー関連のフラグをクリア
                if hasattr(self.downloader_core, 'skip_completion_check'):
                    self.downloader_core.skip_completion_check = False
                if hasattr(self.downloader_core, 'gallery_completed'):
                    self.downloader_core.gallery_completed = False
                if hasattr(self.downloader_core, 'error_occurred'):
                    self.downloader_core.error_occurred = False
            
            # URL背景色をクリア
            if hasattr(self, 'url_panel'):
                try:
                    self.url_panel._update_all_url_backgrounds()
                except Exception as e:
                    self.log(f"URL背景色クリアエラー: {e}", "error")
            
            # フッター情報をリセット
            if hasattr(self, 'footer_panel'):
                try:
                    # 経過時間をリセット
                    if hasattr(self.footer_panel, 'elapsed_label'):
                        self.footer_panel.elapsed_label.config(text="経過時間: 00:00:00")
                    # URL進捗をリセット
                    if hasattr(self.footer_panel, 'url_progress_label'):
                        self.footer_panel.url_progress_label.config(text="URL進捗: 0/0")
                except Exception as e:
                    self.log(f"フッター情報リセットエラー: {e}", "error")
            
            # GUI状態を更新（アイドル状態に）
            if hasattr(self, '_update_gui_for_idle'):
                self._update_gui_for_idle()
            
            # ⭐追加: クリア時のプログレスバー状態破棄⭐
            if hasattr(self, 'discard_progress_on_exit') and self.discard_progress_on_exit.get():
                if hasattr(self, 'progress_state_manager'):
                    if self.progress_state_manager.delete_progress_bars_file():
                        self.log("プログレスバー状態を破棄しました（クリア実行）", "info")
            
            self.log("✅ 全データをクリアしました", "info")
            
        except Exception as e:
            self.log(f"⚠️ クリア処理エラー: {e}", "error")
            import traceback
            traceback.print_exc()
    
    def _backup_incomplete_urls(self):
        """未完了URLのみをバックアップ（Treeview対応）"""
        try:
            from tkinter import filedialog, messagebox
            from datetime import datetime
            
            # ⭐修正: DLリスト（Treeview）から未完了URLを収集⭐
            incomplete_urls = []
            
            if hasattr(self, 'download_list_widget'):
                # Treeviewから取得
                all_items = self.download_list_widget.controller.get_all_items()
                for item in all_items:
                    # completed, skipped以外のステータスを未完了とみなす
                    if item.status.value not in ["completed", "skipped"]:
                        incomplete_urls.append(item.url)
            else:
                # フォールバック: Textウィジェットから取得
                content = self.url_text.get("1.0", tk.END)
                urls = self._parse_urls_from_text(content)
                
                for url in urls:
                    # StateManagerから状態を取得
                    if hasattr(self, 'downloader_core') and hasattr(self.downloader_core, 'state_manager'):
                        status = self.downloader_core.state_manager.get_url_status(url)
                    else:
                        status = self.url_status.get(url, "") if hasattr(self, 'url_status') else ""
                    
                    if status not in ["completed", "skipped"]:
                        incomplete_urls.append(url)
            
            if not incomplete_urls:
                messagebox.showinfo("情報", "未完了のURLはありません。")
                return

            # 保存先を選択
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"incomplete_urls_{timestamp}.txt"
            file_path = filedialog.asksaveasfilename(
                title="未完了URLの保存",
                defaultextension=".txt",
                filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")],
                initialfile=default_filename
            )
            
            if not file_path:
                return
            
            # ファイルに保存
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(incomplete_urls))
            
            self.log(f"未完了URLをバックアップ: {file_path} ({len(incomplete_urls)}件)")
            messagebox.showinfo("バックアップ完了", 
                f"未完了URLをバックアップしました:\n{file_path}\n\n件数: {len(incomplete_urls)}件")
            
        except Exception as e:
            self.log(f"未完了URLバックアップエラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの作成に失敗しました:\n{e}")
    
    def _get_system_info(self):
        """システム情報を取得"""
        try:
            import platform
            import sys
            
            info = {
                'platform': platform.platform(),
                'python_version': sys.version,
                'tkinter_version': tk.Tcl().eval('info patchlevel'),
                'requests_version': self._get_requests_version(),
                'pil_version': self._get_pil_version()
            }
            
            return info
            
        except Exception as e:
            self.log(f"システム情報取得エラー: {e}", "error")
            return {}
    
    def _get_requests_version(self):
        """requestsのバージョンを取得"""
        try:
            import requests
            return getattr(requests, '__version__', 'Unknown')
        except ImportError:
            return 'Not installed'
    
    def _get_pil_version(self):
        """PILのバージョンを取得"""
        try:
            from PIL import Image
            return getattr(Image, '__version__', 'Unknown')
        except ImportError:
            return 'Not installed'
    
    def _show_system_info(self):
        """システム情報を表示"""
        try:
            from tkinter import messagebox
            
            info = self._get_system_info()
            info_text = "\n".join([f"{k}: {v}" for k, v in info.items()])
            messagebox.showinfo("システム情報", info_text)
            
        except Exception as e:
            self.log(f"システム情報表示エラー: {e}", "error")
    
    def _show_about_dialog(self):
        """アバウトダイアログを表示（ハイパーリンク対応）"""
        try:
            import webbrowser
            
            # 新しいウィンドウを作成
            about_window = tk.Toplevel(self.root)
            about_window.title("E-Hentai ダウンローダーについて")
            about_window.geometry("600x700")  # 縦幅を100px増加（600→700）
            about_window.resizable(True, True)
            
            # メインフレーム
            main_frame = tk.Frame(about_window)
            main_frame.pack(fill="both", expand=True, padx=30, pady=30)
            
            # タイトル
            from app_info import APP_NAME, VERSION_STRING
            title_label = tk.Label(main_frame, text=f"{APP_NAME} {VERSION_STRING}", 
                                 font=("Arial", 18, "bold"))
            title_label.pack(pady=(0, 20))
            
            # 説明テキスト
            from app_info import APP_DESCRIPTION
            desc_text = f"""{APP_DESCRIPTION}
常識の範囲内でお使いください。
過度なアクセスを行うとIP禁止になる恐れがあるのでご注意ください。

AIに下駄履かせてもらって色々作ります。
制作：ひびかん🐸 (hibikan_frog)

業スー愛好家。
コーヒー代をいただけると元気が出ます☕"""
            
            desc_label = tk.Label(main_frame, text=desc_text, justify="left", 
                                font=("Arial", 11), wraplength=500)
            desc_label.pack(pady=(0, 20))
            
            # リンクフレーム
            link_frame = tk.Frame(main_frame)
            link_frame.pack(pady=(0, 20), fill="x")
            
            # Noteリンク
            note_frame = tk.Frame(link_frame)
            note_frame.pack(fill="x", pady=(0, 15))
            
            note_label = tk.Label(note_frame, text="Note:", font=("Arial", 12, "bold"))
            note_label.pack(anchor="w")
            
            note_link = tk.Label(note_frame, text="https://note.com/hibikan_frog", 
                               fg="blue", cursor="hand2", font=("Arial", 11, "underline"))
            note_link.pack(anchor="w", pady=(5, 0))
            note_link.bind("<Button-1>", lambda e: webbrowser.open("https://note.com/hibikan_frog"))
            
            # ⭐重要: Noteリンクが表示されることを確認⭐
            self.log("Noteリンクを表示しました", "info")
            
            # Buy Me a Coffeeリンク
            coffee_frame = tk.Frame(link_frame)
            coffee_frame.pack(fill="x")
            
            coffee_label = tk.Label(coffee_frame, text="Buy Me a Coffee:", font=("Arial", 12, "bold"))
            coffee_label.pack(anchor="w")
            
            coffee_link = tk.Label(coffee_frame, text="https://buymeacoffee.com/hibikan_frog", 
                                 fg="blue", cursor="hand2", font=("Arial", 11, "underline"))
            coffee_link.pack(anchor="w", pady=(5, 0))
            coffee_link.bind("<Button-1>", lambda e: webbrowser.open("https://buymeacoffee.com/hibikan_frog"))
            
            # 著作権情報
            copyright_label = tk.Label(main_frame, text="© 2025 E-Hentai Downloader Project", 
                                     font=("Arial", 10), fg="gray")
            copyright_label.pack(pady=(10, 0))
            
            # 閉じるボタン
            close_button = tk.Button(main_frame, text="閉じる", command=about_window.destroy,
                                   font=("Arial", 11), width=10)
            close_button.pack(pady=(20, 0))
            
            # ウィンドウを中央に配置
            about_window.transient(self.root)
            about_window.grab_set()
            
            # ウィンドウを中央に配置
            about_window.update_idletasks()
            x = (about_window.winfo_screenwidth() // 2) - (about_window.winfo_width() // 2)
            y = (about_window.winfo_screenheight() // 2) - (about_window.winfo_height() // 2)
            about_window.geometry(f"+{x}+{y}")
            
        except Exception as e:
            self.log(f"アバウトダイアログ表示エラー: {e}", "error")
    
    def _apply_string_conversion(self, text):
        """文字列変換ルールを適用"""
        try:
            if not hasattr(self, 'string_conversion_enabled') or not self.string_conversion_enabled.get():
                return text
            
            # デフォルトルールを適用
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, 'default_enabled_var'):
                if self.options_panel.default_enabled_var.get():
                    find_text = self.options_panel.default_find_var.get()
                    replace_text = self.options_panel.default_replace_var.get()
                    if find_text and find_text in text:
                        text = text.replace(find_text, replace_text)
                        self.log(f"文字列置換: '{find_text}' -> '{replace_text}'", "debug")
            
            # 追加ルールを適用
            if hasattr(self, 'options_panel') and hasattr(self.options_panel, 'conversion_rules'):
                # ⭐型チェック: リストでない場合はスキップ⭐
                if isinstance(self.options_panel.conversion_rules, list):
                    for rule in self.options_panel.conversion_rules:
                        # ⭐ルール自体もdictかチェック⭐
                        if not isinstance(rule, dict):
                            continue
                        if rule.get('enabled', False):
                            find_text = rule.get('find', '')
                            replace_text = rule.get('replace', '')
                            if find_text and find_text in text:
                                text = text.replace(find_text, replace_text)
                                self.log(f"文字列置換: '{find_text}' -> '{replace_text}'", "debug")
            
            return text
            
        except Exception as e:
            self.log(f"文字列変換エラー: {e}", "error")
            return text    
    # ============================================
    # ⭐Phase 2: Observerパターン実装⭐
    # ============================================
    
    def on_progress_updated(self, url_index: int, data: dict):
        """
        StateManagerからのプログレス更新通知を受け取る
        
        Args:
            url_index: 更新されたプログレスバーのインデックス
            data: 更新データ（current, total, title, status, download_range_info, url）
        """
        try:
            # GUIスレッドで実行するようにスケジュール
            def update_gui():
                try:
                    # プログレスパネル更新
                    if hasattr(self, 'progress_panel'):
                        # progress_panelの更新メソッドを呼び出す
                        if hasattr(self.progress_panel, 'update_progress_bar_from_state'):
                            self.progress_panel.update_progress_bar_from_state(url_index, data)
                    
                    # DLリスト更新
                    if hasattr(self, 'download_list_widget') and data.get('url'):
                        current = data.get('current', 0)
                        total = data.get('total', 0)
                        if current is not None and total is not None:
                            self.download_list_widget.update_progress(data['url'], current, total)
                        # ステータス更新
                        if data.get('status'):
                            self.download_list_widget.update_status(data['url'], 'downloading')
                except Exception as e:
                    self.log(f"GUI更新エラー: {e}", "error")
            
            # GUIスレッドでの実行をスケジュール
            if hasattr(self, 'root'):
                self.root.after(0, update_gui)
        except Exception as e:
            self.log(f"プログレス更新通知エラー: {e}", "error")
    
    def on_status_changed(self, data: dict):
        """
        StateManagerからのステータス変更通知を受け取る
        
        Args:
            data: ステータスデータ
        """
        try:
            # 必要に応じてGUI更新処理を実装
            pass
        except Exception as e:
            self.log(f"ステータス変更通知エラー: {e}", "error")