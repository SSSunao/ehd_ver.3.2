"""
プログレスパネル - 後方互換性レイヤー

旧システムのAPIを維持しつつ、新しいProgressManagerに委譲する。
これにより、main_window.pyを最小限の変更で統合できる。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, Dict, Any, Callable
import time

from gui.components.progress import ProgressManager


class EHDownloaderProgressPanel:
    """
    プログレスパネル（互換性レイヤー）
    
    旧APIを維持しつつ、内部では新しいProgressManagerを使用
    """
    
    def __init__(self, parent):
        """
        Args:
            parent: メインウィンドウインスタンス
        """
        self.parent = parent
        self.root = parent.root
        
        # UI Bridge（後で設定される）
        self.ui_bridge = None
        
        # ログ関連
        self.log_text: Optional[scrolledtext.ScrolledText] = None
        self.log_frame: Optional[tk.Frame] = None
        
        # 経過時間タイマー
        self.elapsed_time_timer = None
        self.current_download_start_time = None
        
        # ダウンロードマネージャー設定
        self.separate_window_geometry = '800x600'
        self.auto_scroll_enabled = True
        
        # 中断時間管理
        self.download_pause_start_time = None
        self.total_paused_time = 0
        
        # ProgressManager（後で初期化）
        self.progress_manager: Optional[ProgressManager] = None
    
    def _ensure_progress_manager(self):
        """ProgressManagerを遅延初期化"""
        if self.progress_manager is not None:
            return
        
        # downloader_coreが初期化されるまで待つ
        if not hasattr(self.parent, 'downloader_core'):
            return
        
        if not hasattr(self.parent, 'main_v_pane'):
            return
        
        # ProgressManagerを初期化
        self.progress_manager = ProgressManager(
            parent_window=self.parent,  # main_windowインスタンスを渡す
            main_v_pane=self.parent.main_v_pane,
            bottom_pane=self.parent.bottom_pane,
            state_manager=self.parent.downloader_core.state_manager,
            managed_folders_getter=lambda: getattr(self.parent.downloader_core, 'managed_folders', {}),
            log_callback=self.log
        )
        
        # オプションから最大表示数を設定
        max_display = 100  # デフォルト値
        if hasattr(self.parent, 'progress_retention_count'):
            try:
                max_display = int(self.parent.progress_retention_count.get())
            except:
                max_display = 100
        
        self.progress_manager.set_max_display_count(max_display)
    
    # ===============================================
    # ログパネル関連（既存機能を維持）
    # ===============================================
    
    def create_log_panel(self, parent_pane):
        """ログパネルを作成"""
        self.log_frame = tk.Frame(parent_pane)
        parent_pane.add(self.log_frame, height=150)
        
        # ログタイトル
        log_label = tk.Label(
            self.log_frame,
            text="ログ",
            font=("", 10, "bold")
        )
        log_label.pack(anchor=tk.W, padx=5, pady=2)
        
        # ログテキストエリア
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame,
            height=8,
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
    
    def log(self, message: str, level: str = "info", to_file_only: bool = False):
        """
        ログ出力
        
        Args:
            message: ログメッセージ
            level: ログレベル（info/warning/error/debug）
            to_file_only: Trueの場合、ファイルのみに出力
        """
        # タイムスタンプ付きメッセージ
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] [{level.upper()}] {message}"
        
        # コンソールに出力
        print(formatted_message)
        
        # GUIに出力
        if not to_file_only and self.log_text:
            def _log_to_gui():
                try:
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, formatted_message + "\n")
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                except Exception as e:
                    print(f"ログ出力エラー: {e}")
            
            # メインスレッドで実行
            if self.root:
                self.root.after(0, _log_to_gui)
    
    # ===============================================
    # プログレス更新関連（ProgressManagerに委譲）
    # ===============================================
    
    def update_progress_display(
        self,
        url: str,
        current: int,
        total: int,
        title_override: Optional[str] = None,
        status_text_override: Optional[str] = None,
        download_range_info: Optional[Dict] = None
    ):
        """プログレス表示を更新（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # url_indexを取得
        url_index = self._get_url_index_from_url(url)
        if url_index is None:
            return
        
        # StateManagerを更新（ProgressManagerが自動的にGUIを更新）
        if hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            
            # 既存のデータを取得
            existing_data = state_manager.get_progress_bar(url_index) or {}
            
            # 更新
            updated_data = {
                **existing_data,
                'current': current,
                'total': total,
                'url': url
            }
            
            if title_override:
                updated_data['title'] = title_override
            
            if status_text_override:
                updated_data['status'] = status_text_override
            
            if download_range_info:
                updated_data['download_range_info'] = download_range_info
            
            state_manager.set_progress_bar(url_index, updated_data)
    
    def update_current_progress(
        self,
        current: int,
        total: int,
        status: str = "",
        url: Optional[str] = None,
        download_range_info: Optional[Dict] = None,
        url_index: Optional[int] = None
    ):
        """現在のプログレスを更新（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # url_indexを取得
        if url_index is None:
            if url:
                url_index = self._get_url_index_from_url(url)
            elif hasattr(self.parent, 'current_url_index'):
                url_index = self.parent.current_url_index
            elif hasattr(self.parent, 'downloader_core'):
                url_index = self.parent.downloader_core.state_manager.get_current_url_index()
        
        if url_index is None:
            return
        
        # StateManagerを更新
        if hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            
            # 既存のデータを取得
            existing_data = state_manager.get_progress_bar(url_index) or {}
            
            # 更新
            updated_data = {
                **existing_data,
                'current': current,
                'total': total
            }
            
            if url:
                updated_data['url'] = url
            
            if status:
                updated_data['status'] = status
            
            if download_range_info:
                updated_data['download_range_info'] = download_range_info
            
            state_manager.set_progress_bar(url_index, updated_data)
    
    def update_progress_title(self, url: str, title: str, url_index: Optional[int] = None):
        """プログレスタイトルを更新（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # url_indexを取得
        if url_index is None:
            url_index = self._get_url_index_from_url(url)
        
        if url_index is None:
            return
        
        # StateManagerを更新
        if hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            
            # 既存のデータを取得
            existing_data = state_manager.get_progress_bar(url_index) or {}
            
            # タイトルを更新
            updated_data = {
                **existing_data,
                'url': url,
                'title': title
            }
            
            state_manager.set_progress_bar(url_index, updated_data)
    
    def show_current_progress_bar(self):
        """現在のプログレスバーを表示（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # 最新のプログレスバーを表示（ProgressManagerが自動的に処理）
        # StateManagerが更新されれば自動的に表示される
        pass
    
    def hide_current_progress_bar(self):
        """現在のプログレスバーを非表示（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if self.progress_manager:
            self.progress_manager.main_view.hide()
    
    def clear_all_progress_bars(self):
        """全てのプログレスバーをクリア（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if self.progress_manager:
            self.progress_manager.clear_all()
    
    def switch_progress_display_mode(self):
        """ダウンロードマネージャーの表示/非表示を切り替え（互換性メソッド）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        if self.progress_manager.is_separate_window_open():
            self.progress_manager.hide_separate_window()
        else:
            self.progress_manager.show_separate_window()
    
    # ===============================================
    # 設定関連（互換性メソッド）
    # ===============================================
    
    def _save_separate_window_settings(self):
        """ダウンロードマネージャーの設定を保存"""
        # 設定はProgressManagerが自動的に管理
        pass
    
    def _update_separate_window_button_states(self):
        """ダウンロードマネージャーのボタン状態を更新"""
        # ボタン状態はProgressManagerが自動的に管理
        pass
    
    # ===============================================
    # StateManager連携（互換性メソッド）
    # ===============================================
    
    def _setup_state_listeners(self):
        """StateManagerのリスナーを設定"""
        self._ensure_progress_manager()
        
        # ProgressManagerが自動的にリスナーを設定
        pass
    
    def _setup_state_manager_observer(self):
        """StateManagerのオブザーバーを設定"""
        self._ensure_progress_manager()
        
        # ProgressManagerが自動的にオブザーバーを設定
        pass
    
    def _setup_progress_tracker_observer(self):
        """ProgressTrackerのオブザーバーを設定"""
        # 新システムではStateManagerが一元管理
        pass
    
    # ===============================================
    # タイマー関連（互換性メソッド）
    # ===============================================
    
    def _start_elapsed_time_timer(self):
        """経過時間タイマーを開始"""
        self.current_download_start_time = time.time()
    
    def _stop_elapsed_time_timer(self):
        """経過時間タイマーを停止"""
        self.elapsed_time_timer = None
        self.current_download_start_time = None
    
    def reset_current_download_start_time(self):
        """ダウンロード開始時間をリセット"""
        self.current_download_start_time = None
    
    # ===============================================
    # 復元関連（互換性メソッド）
    # ===============================================
    
    def restore_progress_bars_from_state(self):
        """StateManagerからプログレスバーを復元"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # StateManagerから全てのプログレスバーを取得
        if hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            all_progress = state_manager.get_all_progress_bars()
            
            # 各プログレスバーを更新
            for url_index in all_progress.keys():
                self.progress_manager.update_progress(url_index)
    
    def _get_progress_bars(self) -> Dict[int, Dict]:
        """全てのプログレスバーを取得"""
        if not hasattr(self.parent, 'downloader_core'):
            return {}
        
        return self.parent.downloader_core.state_manager.get_all_progress_bars()
    
    def _get_progress_bar(self, url_index: int) -> Optional[Dict]:
        """指定されたurl_indexのプログレスバーを取得"""
        if not hasattr(self.parent, 'downloader_core'):
            return None
        
        return self.parent.downloader_core.state_manager.get_progress_bar(url_index)
    
    # ===============================================
    # ユーティリティメソッド
    # ===============================================
    
    def _get_url_index_from_url(self, url: str) -> Optional[int]:
        """URLからurl_indexを取得"""
        if not hasattr(self.parent, 'downloader_core'):
            return None
        
        state_manager = self.parent.downloader_core.state_manager
        all_progress = state_manager.get_all_progress_bars()
        
        # 正規化URLで比較
        if hasattr(self.parent, 'normalize_url'):
            normalized_url = self.parent.normalize_url(url)
        else:
            normalized_url = url
        
        for url_idx, progress in all_progress.items():
            progress_url = progress.get('url', '')
            if progress_url:
                if hasattr(self.parent, 'normalize_url'):
                    normalized_progress_url = self.parent.normalize_url(progress_url)
                else:
                    normalized_progress_url = progress_url
                
                if normalized_progress_url == normalized_url or progress_url == url:
                    return url_idx
        
        return None
    
    # ===============================================
    # 後方互換性のための追加メソッド
    # ===============================================
    
    def update_url_progress(self, completed: int, total: int):
        """URL進捗を更新（互換性メソッド、機能なし）"""
        pass
    
    def update_elapsed_time(self, elapsed_seconds: float):
        """経過時間を更新（互換性メソッド、機能なし）"""
        pass
    
    def set_url_status(self, url: str, status: str):
        """URL状態を設定（互換性メソッド）"""
        url_index = self._get_url_index_from_url(url)
        if url_index is not None and hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            existing_data = state_manager.get_progress_bar(url_index) or {}
            updated_data = {**existing_data, 'url': url, 'status': status}
            state_manager.set_progress_bar(url_index, updated_data)
    
    def update_progress_status(self, status_type: str, details: str = "", url: Optional[str] = None, url_index: Optional[int] = None):
        """プログレス状態を更新（互換性メソッド）"""
        if url_index is None and url:
            url_index = self._get_url_index_from_url(url)
        
        if url_index is not None and hasattr(self.parent, 'downloader_core'):
            state_manager = self.parent.downloader_core.state_manager
            existing_data = state_manager.get_progress_bar(url_index) or {}
            updated_data = {
                **existing_data,
                'status': f"{status_type}: {details}" if details else status_type
            }
            if url:
                updated_data['url'] = url
            state_manager.set_progress_bar(url_index, updated_data)
    
    def preserve_skipped_progress_bar(self, url: str):
        """スキップされたプログレスバーを保持（互換性メソッド）"""
        self.set_url_status(url, "スキップ")
    
    def update_url_background(self, url: str):
        """URL背景色を更新（互換性メソッド、機能なし）"""
        pass
    
    def update_display_limit(self):
        """表示制限を更新（オプション変更時に呼ばれる）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return
        
        # オプションから最大表示数を取得
        max_display = 100  # デフォルト値
        if hasattr(self.parent, 'progress_retention_count'):
            try:
                max_display = int(self.parent.progress_retention_count.get())
            except:
                max_display = 100
        
        self.progress_manager.set_max_display_count(max_display)
    
    # ===============================================
    # ダウンロードマネージャー関連（互換性メソッド）
    # ===============================================
    
    @property
    def separate_window(self):
        """ダウンロードマネージャーのウィンドウ（互換性プロパティ）"""
        self._ensure_progress_manager()
        
        if not self.progress_manager:
            return None
        
        if self.progress_manager.is_separate_window_open():
            return self.progress_manager.separate_view
        return None

