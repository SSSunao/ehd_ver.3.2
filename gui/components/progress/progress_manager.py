"""
プログレスバー管理のFacade（統一インターフェース）

責任:
1. 外部から見たシンプルなAPI提供
2. メインウィンドウ/ダウンロードマネージャーの切り替え管理
3. StateManagerとの通信
4. イベントリスナーの登録

設計原則:
- Facade Pattern: 複雑な内部処理を隠蔽
- Single Source of Truth: StateManagerからのみデータ取得
- Fail-Fast: 不正な状態は即座にエラー
"""

import tkinter as tk
from typing import Optional, Dict, Any, Callable
import webbrowser
import subprocess
import os
import sys

from .progress_data import ProgressInfo
from .main_window_view import MainWindowView
from .separate_window_view import SeparateWindowView


class ProgressManager:
    """
    プログレスバー管理のFacade
    
    外部から見たシンプルなAPI:
    - update_progress(url_index)
    - show_separate_window()
    - hide_separate_window()
    - set_max_display(count)
    """
    
    def __init__(
        self,
        parent_window: Any,  # tk.Tk or main_window instance
        main_v_pane: tk.PanedWindow,
        bottom_pane: tk.Widget,
        state_manager: Any,  # core.managers.state_manager.StateManager
        managed_folders_getter: Callable[[], Dict[str, str]],
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Args:
            parent_window: 親ウィンドウまたはメインウィンドウインスタンス
            main_v_pane: メインの垂直PanedWindow
            bottom_pane: 下部ペイン
            state_manager: StateManagerインスタンス
            managed_folders_getter: URL -> 保存フォルダを取得する関数
            log_callback: ログ出力コールバック
        """
        self.parent = parent_window
        # Tkウィンドウを取得
        if hasattr(parent_window, 'root'):
            self.root = parent_window.root
        else:
            self.root = parent_window
        
        self.state_manager = state_manager
        self.managed_folders_getter = managed_folders_getter
        self.log = log_callback or self._default_log
        
        # 最大表示数（オプションから取得）
        self.max_display_count = 10
        
        # View
        self.main_view = MainWindowView(
            main_v_pane=main_v_pane,
            bottom_pane=bottom_pane,
            on_folder_click=self._on_folder_click,
            on_url_click=self._on_url_click
        )
        
        self.separate_view: Optional[SeparateWindowView] = None
        
        # StateManagerのリスナーを登録
        self._setup_listeners()
    
    def _default_log(self, message: str, level: str = "info"):
        """デフォルトのログ出力"""
        print(f"[{level.upper()}] {message}")
    
    def _setup_listeners(self):
        """StateManagerのイベントリスナーを登録"""
        # ⭐修正: StateManagerのObserverとして登録⭐
        if hasattr(self.state_manager, 'attach_observer'):
            self.state_manager.attach_observer(self)
            self.log("[ProgressManager] StateManagerにObserverとして登録しました", "debug")
        else:
            self.log("[ProgressManager] StateManagerにattach_observerメソッドがありません", "warning")
    
    def on_progress_updated(self, url_index: int, data: Dict[str, Any]):
        """
        StateManagerからのプログレス更新通知（Observerインターフェース）
        
        Args:
            url_index: URLインデックス
            data: プログレスデータ {'current': int, 'total': int, 'title': str, 'status': str, ...}
        """
        try:
            if url_index is None:
                self.log("プログレス更新: url_indexがNone", "warning")
                return
            
            # ⭐DEBUG: Observer受信のログ⭐
            self.log(
                f"[DEBUG] Observer受信: url_index={url_index}, current={data.get('current')}/{data.get('total')}, status={data.get('status')}",
                "debug"
            )
            
            # GUIスレッドで実行
            def update_gui():
                try:
                    self.update_progress(url_index)
                except Exception as e:
                    self.log(f"プログレス更新エラー: {e}", "error")
                    import traceback
                    self.log(f"詳細: {traceback.format_exc()}", "error")
            
            # ⭐修正: GUIスレッドで実行⭐
            if hasattr(self.root, 'after'):
                self.root.after(0, update_gui)
            else:
                update_gui()
        except Exception as e:
            self.log(f"プログレス更新スケジュールエラー: {e}", "error")
    
    def update_progress(self, url_index: int):
        """
        プログレスバーを更新（メインAPI）
        
        ⭐Phase 2: DownloadSessionから情報を取得⭐
        
        Args:
            url_index: URLインデックス
        """
        try:
            # ⭐優先: DownloadSessionから取得⭐
            session = self.state_manager.session_repository.get(url_index)
            if session:
                # DownloadSessionからProgressInfoを生成
                progress_info = ProgressInfo.from_session(session)
            else:
                # フォールバック: StateManagerから取得（後方互換性）
                raw_data = self.state_manager.get_progress_bar(url_index)
                if not raw_data:
                    self.log(f"プログレス情報が見つかりません: url_index={url_index}", "warning")
                    return
                
                # 型安全なデータオブジェクトに変換
                progress_info = ProgressInfo.from_dict(url_index, raw_data)
            
            # 保存フォルダを取得
            managed_folders = self.managed_folders_getter()
            save_folder = managed_folders.get(progress_info.url)
            
            # ⭐修正: progress_separate_window_enabledとウィンドウの状態を厳密にチェック⭐
            separate_enabled = (
                hasattr(self.parent, 'progress_separate_window_enabled') 
                and self.parent.progress_separate_window_enabled.get() == True
            )
            
            # ⭐追加: デバッグログ⭐
            if separate_enabled:
                self.log(f"[DEBUG] ダウンロードマネージャーが有効: is_open={self.is_separate_window_open()}", "debug")
            
            # ⭐修正: ダウンロードマネージャーが明示的に有効でかつ開いている場合のみ更新⭐
            if separate_enabled and self.is_separate_window_open():
                # メインウィンドウを非表示
                self.main_view.hide()
                
                # ダウンロードマネージャーを更新
                self.separate_view.update_progress(
                    progress_info,
                    save_folder,
                    self.max_display_count
                )
            else:
                # ⭐メインウィンドウに指定されたurl_indexのプログレスバーを表示⭐
                # ⭐追加: ダウンロードマネージャーが開いていたら閉じる⭐
                if self.is_separate_window_open() and not separate_enabled:
                    self.log("[DEBUG] ダウンロードマネージャーが無効なのに開いているため、閉じます", "debug")
                    self.hide_separate_window()
                
                self._update_main_window_with_priority(url_index)
        
        except Exception as e:
            self.log(f"プログレス更新失敗: {e}", "error")
            import traceback
            self.log(f"詳細: {traceback.format_exc()}", "error")
    
    def _update_main_window_with_priority(self, priority_url_index: int):
        """
        メインウィンドウにプログレスバーを表示（優先度付き）
        
        Args:
            priority_url_index: 優先的に表示するurl_index
        """
        try:
            # 全てのプログレスバーを取得
            all_progress = self.state_manager.get_all_progress_bars()
            if not all_progress:
                return
            
            # ⭐修正: 共通メソッドを使用⭐
            latest_index = self._find_latest_active_index(all_progress)
            
            # 優先url_indexが指定されており、それがアクティブな場合は優先
            if priority_url_index in all_progress:
                # 優先url_indexの状態を確認
                progress_bar = all_progress[priority_url_index]
                if hasattr(progress_bar, 'status'):
                    status = progress_bar.status
                elif isinstance(progress_bar, dict):
                    status = progress_bar.get('status', '')
                else:
                    status = ''
                
                # アクティブな状態なら優先表示
                if status in ['ダウンロード中', '待機中', '中断', 'downloading', 'pending', 'paused']:
                    display_index = priority_url_index
                else:
                    display_index = latest_index
            else:
                display_index = latest_index
            
            if display_index is None:
                return
            
            # プログレスバーを表示
            raw_data = self.state_manager.get_progress_bar(display_index)
            if not raw_data:
                return
            
            progress_info = ProgressInfo.from_dict(display_index, raw_data)
            managed_folders = self.managed_folders_getter()
            save_folder = managed_folders.get(progress_info.url)
            
            self.main_view.show(progress_info, save_folder)
        
        except Exception as e:
            self.log(f"メインウィンドウ更新エラー: {e}", "error")
            import traceback
            self.log(f"詳細: {traceback.format_exc()}", "error")
    
    def _update_main_window_latest(self):
        """メインウィンドウに最新のプログレスバーを表示"""
        try:
            # 全てのプログレスバーを取得
            all_progress = self.state_manager.get_all_progress_bars()
            if not all_progress:
                return
            
            # 最新のアクティブなプログレスバーを選択
            latest_index = self._find_latest_active_index(all_progress)
            if latest_index is None:
                return
            
            # プログレスバーを表示
            raw_data = self.state_manager.get_progress_bar(latest_index)
            if not raw_data:
                self.log(f"プログレス情報取得失敗: url_index={latest_index}", "warning")
                return
            
            progress_info = ProgressInfo.from_dict(latest_index, raw_data)
            managed_folders = self.managed_folders_getter()
            save_folder = managed_folders.get(progress_info.url)
            
            self.main_view.show(progress_info, save_folder)
        
        except Exception as e:
            self.log(f"メインウィンドウ更新エラー: {e}", "error")
            import traceback
            self.log(f"詳細: {traceback.format_exc()}", "error")
    
    def _find_latest_active_index(self, all_progress: Dict[int, Any]) -> Optional[int]:
        """
        最新のアクティブなurl_indexを取得
        
        Args:
            all_progress: 全てのプログレスバー（ProgressBarオブジェクトまたは辞書）
            
        Returns:
            最新のアクティブなurl_index、なければNone
        """
        active_indices = []
        for url_index, progress_bar in all_progress.items():
            # ⭐修正: ProgressBarオブジェクトまたは辞書の両方に対応⭐
            if hasattr(progress_bar, 'status'):
                status = progress_bar.status
            elif isinstance(progress_bar, dict):
                status = progress_bar.get('status', '')
            else:
                continue
            
            if status in ['ダウンロード中', '待機中', '中断', 'downloading', 'pending', 'paused']:
                active_indices.append(url_index)
        
        # アクティブなものがない場合は最大インデックス
        if not active_indices:
            return max(all_progress.keys()) if all_progress else None
        else:
            return max(active_indices)
    
    def show_separate_window(self):
        """ダウンロードマネージャーを表示"""
        if not self.separate_view or not self.separate_view.is_open():
            # 新規作成
            self.separate_view = SeparateWindowView(
                parent_window=self.root,  # Tkウィンドウを渡す
                on_pause_click=self._on_pause_click,
                on_resume_click=self._on_resume_click,
                on_skip_click=self._on_skip_click,
                on_restart_click=self._on_restart_click,
                on_refresh_click=self._on_refresh_click,
                on_folder_click=self._on_folder_click,
                on_url_click=self._on_url_click,
                on_close=self._on_separate_window_close
            )
            
            # ⭐修正: progress_separate_window_enabledをTrueに設定⭐
            if hasattr(self.parent, 'progress_separate_window_enabled'):
                self.parent.progress_separate_window_enabled.set(True)
            
            # ⭐修正: ダウンロードマネージャーボタンの状態を更新⭐
            if hasattr(self.parent, 'options_panel') and hasattr(self.parent.options_panel, '_update_download_manager_button_state'):
                self.parent.options_panel._update_download_manager_button_state()
            
            # 全てのプログレスバーを表示
            self.refresh_separate_window()
        else:
            # 既存のウィンドウを表示
            self.separate_view.show()
        
        # メインウィンドウのプログレスバーを非表示
        self.main_view.hide()
    
    def hide_separate_window(self):
        """ダウンロードマネージャーを非表示"""
        if self.separate_view:
            self.separate_view.hide()
        
        # ⭐修正: progress_separate_window_enabledをFalseに設定⭐
        if hasattr(self.parent, 'progress_separate_window_enabled'):
            self.parent.progress_separate_window_enabled.set(False)
        
        # ⭐修正: ダウンロードマネージャーボタンの状態を更新⭐
        if hasattr(self.parent, 'options_panel') and hasattr(self.parent.options_panel, '_update_download_manager_button_state'):
            self.parent.options_panel._update_download_manager_button_state()
        
        # メインウィンドウのプログレスバーを表示
        self._update_main_window_latest()
    
    def is_separate_window_open(self) -> bool:
        """ダウンロードマネージャーが開いているか"""
        return (
            self.separate_view is not None
            and self.separate_view.is_open()
        )
    
    def refresh_separate_window(self):
        """ダウンロードマネージャーの全プログレスバーを最新情報で更新
        
        ⭐Phase 2: DownloadSessionから情報を取得⭐
        """
        if not self.is_separate_window_open():
            return
        
        try:
            # ⭐優先: DownloadSessionRepositoryから取得⭐
            all_sessions = self.state_manager.session_repository.get_all()
            
            # ProgressInfoに変換
            progress_list = []
            for url_index, session in all_sessions.items():
                # DownloadSessionからProgressInfoを生成
                progress_info = ProgressInfo.from_session(session)
                progress_list.append(progress_info)
            
            # ⭐フォールバック: セッションが空の場合は従来の方法⭐
            if not progress_list:
                all_progress = self.state_manager.get_all_progress_bars()
                for url_index in all_progress.keys():
                    # ⭐修正: get_progress_bar()を使って辞書形式で取得⭐
                    raw_data = self.state_manager.get_progress_bar(url_index)
                    if raw_data:
                        progress_info = ProgressInfo.from_dict(url_index, raw_data)
                        progress_list.append(progress_info)
            
            # url_indexでソート
            progress_list.sort(key=lambda p: p.url_index)
            
            # 表示制限を適用
            if len(progress_list) > self.max_display_count:
                progress_list = progress_list[-self.max_display_count:]
            
            # 更新
            managed_folders = self.managed_folders_getter()
            self.separate_view.refresh_all(progress_list, managed_folders)
        
        except Exception as e:
            self.log(f"ダウンロードマネージャー更新エラー: {e}", "error")
    
    def set_max_display_count(self, count: int):
        """
        最大表示数を設定（即座に反映）
        
        Args:
            count: 最大表示数
        """
        if count <= 0:
            self.log(f"不正な表示数: {count}", "warning")
            return
        
        self.max_display_count = count
        
        # ダウンロードマネージャーが開いている場合は再表示
        if self.is_separate_window_open():
            self.refresh_separate_window()
    
    def clear_all(self):
        """全てのプログレスバーをクリア"""
        self.main_view.hide()
        
        if self.separate_view:
            for widget in self.separate_view.widgets.values():
                widget.destroy()
            self.separate_view.widgets.clear()
    
    # コールバック実装
    
    def _on_folder_click(self, url_index: int):
        """フォルダボタンクリック時の処理"""
        try:
            # プログレス情報を取得
            raw_data = self.state_manager.get_progress_bar(url_index)
            if not raw_data:
                return
            
            progress_info = ProgressInfo.from_dict(url_index, raw_data)
            
            # 保存フォルダを取得
            managed_folders = self.managed_folders_getter()
            save_folder = managed_folders.get(progress_info.url)
            
            if not save_folder or not os.path.exists(save_folder):
                self.log(f"フォルダが見つかりません: {save_folder}", "warning")
                return
            
            # フォルダを開く
            if sys.platform == 'win32':
                os.startfile(save_folder)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', save_folder])
            else:
                subprocess.Popen(['xdg-open', save_folder])
        
        except Exception as e:
            self.log(f"フォルダを開けませんでした: {e}", "error")
    
    def _on_url_click(self, url: str):
        """URLクリック時の処理"""
        try:
            webbrowser.open(url)
        except Exception as e:
            self.log(f"URLを開けませんでした: {e}", "error")
    
    def _on_pause_click(self):
        """中断ボタンクリック"""
        try:
            # ⭐修正: parentは直接main_windowを指している⭐
            if hasattr(self.parent, 'pause_download'):
                self.parent.pause_download()
            else:
                self.log("中断機能が利用できません", "warning")
        except Exception as e:
            self.log(f"中断エラー: {e}", "error")
    
    def _on_resume_click(self):
        """再開ボタンクリック"""
        try:
            # ⭐修正: parentは直接main_windowを指している⭐
            if hasattr(self.parent, 'resume_download'):
                self.parent.resume_download()
            else:
                self.log("再開機能が利用できません", "warning")
        except Exception as e:
            self.log(f"再開エラー: {e}", "error")
    
    def _on_skip_click(self):
        """スキップボタンクリック"""
        try:
            # ⭐修正: parent.parentを使用（main_windowへのアクセス）⭐
            main_window = self.parent.parent if hasattr(self.parent, 'parent') else self.parent
            if hasattr(main_window, 'skip_current_download'):
                main_window.skip_current_download()
            else:
                self.log("スキップ機能が利用できません", "warning")
        except Exception as e:
            self.log(f"スキップエラー: {e}", "error")
    
    def _on_restart_click(self):
        """リスタートボタンクリック"""
        try:
            # ⭐修正: parent.parentを使用（main_windowへのアクセス）⭐
            main_window = self.parent.parent if hasattr(self.parent, 'parent') else self.parent
            if hasattr(main_window, 'restart_download'):
                main_window.restart_download()
            else:
                self.log("リスタート機能が利用できません", "warning")
        except Exception as e:
            self.log(f"リスタートエラー: {e}", "error")
    
    def _on_refresh_click(self):
        """GUI更新ボタンクリック"""
        self.refresh_separate_window()
    
    def _on_separate_window_close(self):
        """ダウンロードマネージャークローズ時の処理"""
        self.separate_view = None
        
        # ⭐修正: progress_separate_window_enabledをFalseに設定⭐
        if hasattr(self.parent, 'progress_separate_window_enabled'):
            self.parent.progress_separate_window_enabled.set(False)
        
        # ⭐修正: ダウンロードマネージャーボタンの状態を更新⭐
        if hasattr(self.parent, 'options_panel') and hasattr(self.parent.options_panel, '_update_download_manager_button_state'):
            self.parent.options_panel._update_download_manager_button_state()
        
        # メインウィンドウのプログレスバーを表示
        self._update_main_window_latest()

