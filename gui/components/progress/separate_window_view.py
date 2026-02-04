"""
ダウンロードマネージャー（別ウィンドウ）のView

責任:
1. 複数のプログレスバーを縦に並べて表示
2. 表示制限数に従って古いものから削除
3. トップパネルのボタン管理
4. オートスクロール機能
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Callable, List
import os
import json

from .progress_data import ProgressInfo
from .progress_widget import ProgressWidget


class SeparateWindowView:
    """
    ダウンロードマネージャーのView
    
    設計原則:
    - 複数のプログレスバーを管理
    - 表示制限を尊重
    - オートスクロール対応
    """
    
    def __init__(
        self,
        parent_window: tk.Tk,
        on_pause_click: Optional[Callable[[], None]] = None,
        on_resume_click: Optional[Callable[[], None]] = None,
        on_skip_click: Optional[Callable[[], None]] = None,
        on_restart_click: Optional[Callable[[], None]] = None,
        on_refresh_click: Optional[Callable[[], None]] = None,
        on_folder_click: Optional[Callable[[int], None]] = None,
        on_url_click: Optional[Callable[[str], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ):
        """
        Args:
            parent_window: 親ウィンドウ
            on_pause_click: 中断ボタンクリック時のコールバック
            on_resume_click: 再開ボタンクリック時のコールバック
            on_skip_click: スキップボタンクリック時のコールバック
            on_restart_click: リスタートボタンクリック時のコールバック
            on_refresh_click: 更新ボタンクリック時のコールバック
            on_folder_click: フォルダボタンクリック時のコールバック
            on_url_click: URLクリック時のコールバック
            on_close: ウィンドウクローズ時のコールバック
        """
        self.parent = parent_window
        self.on_pause_click = on_pause_click
        self.on_resume_click = on_resume_click
        self.on_skip_click = on_skip_click
        self.on_restart_click = on_restart_click
        self.on_refresh_click = on_refresh_click
        self.on_folder_click = on_folder_click
        self.on_url_click = on_url_click
        self.on_close = on_close
        
        # 別ウィンドウ
        self.window: Optional[tk.Toplevel] = None
        
        # プログレスバーWidget群（url_index -> ProgressWidget）
        self.widgets: Dict[int, ProgressWidget] = {}
        
        # オートスクロール設定
        self.auto_scroll_enabled = True
        
        # GUI要素
        self.canvas: Optional[tk.Canvas] = None
        self.scrollbar: Optional[ttk.Scrollbar] = None
        self.scroll_frame: Optional[tk.Frame] = None
        self.auto_scroll_button: Optional[tk.Button] = None
        
        self._create_window()
    
    def _create_window(self):
        """別ウィンドウを作成"""
        self.window = tk.Toplevel(self.parent)
        self.window.title("ダウンロードマネージャー")
        
        # ⭐修正: ウィンドウサイズと位置を復元（デフォルトは画面の75%幅）⭐
        geometry = self._load_window_geometry()
        if geometry:
            self.window.geometry(geometry)
        else:
            # デフォルトサイズを画面の75%に設定
            screen_width = self.parent.winfo_screenwidth()
            screen_height = self.parent.winfo_screenheight()
            window_width = int(screen_width * 0.75)
            window_height = int(screen_height * 0.75)
            self.window.geometry(f"{window_width}x{window_height}")
        
        # ⭐追加: ウィンドウ設定変更時に保存⭐
        self.window.bind('<Configure>', self._on_window_configure)
        
        # クローズイベント
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        # トップパネル
        self._create_top_panel()
        
        # スクロール可能なプログレスバーエリア
        self._create_scroll_area()
    
    def _create_top_panel(self):
        """トップパネルを作成（ボタン群）"""
        top_frame = tk.Frame(self.window)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 左側のボタン
        left_frame = tk.Frame(top_frame)
        left_frame.pack(side=tk.LEFT)
        
        # ⭐修正: ボタンの参照を保持⭐
        self.pause_button = tk.Button(
            left_frame,
            text="⏸ 中断",
            command=self.on_pause_click
        )
        self.pause_button.pack(side=tk.LEFT, padx=2)
        
        self.resume_button = tk.Button(
            left_frame,
            text="▶ 再開",
            command=self.on_resume_click
        )
        self.resume_button.pack(side=tk.LEFT, padx=2)
        
        self.refresh_button = tk.Button(
            left_frame,
            text="🔄 GUI更新",
            command=self.on_refresh_click
        )
        self.refresh_button.pack(side=tk.LEFT, padx=2)
        
        # 右側のボタン
        right_frame = tk.Frame(top_frame)
        right_frame.pack(side=tk.RIGHT)
        
        self.restart_button = tk.Button(
            right_frame,
            text="🔁 リスタート",
            command=self.on_restart_click
        )
        self.restart_button.pack(side=tk.LEFT, padx=2)
        
        self.skip_button = tk.Button(
            right_frame,
            text="⏭ スキップ",
            command=self.on_skip_click
        )
        self.skip_button.pack(side=tk.LEFT, padx=2)
        
        # オートスクロールボタン（トグル）
        self.auto_scroll_button = tk.Button(
            right_frame,
            text="📜 オートスクロール",
            relief=tk.SUNKEN,  # 初期状態は有効
            command=self._toggle_auto_scroll
        )
        self.auto_scroll_button.pack(side=tk.LEFT, padx=2)
    
    def update_button_states(self, state: str) -> None:
        """ボタン状態を更新
        
        Args:
            state: 状態名
                - 'idle': アイドル状態
                - 'downloading': ダウンロード中
                - 'paused': 一時停止中
                - 'error': エラー発生
                - 'completed': 完了
        """
        try:
            if state == 'idle':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='disabled')
            elif state == 'downloading':
                self.pause_button.config(state='normal')
                self.resume_button.config(state='disabled')
            elif state == 'paused':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='normal')
            elif state == 'error':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='normal')
            elif state == 'completed':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='disabled')
        except Exception as e:
            print(f"ダウンロードマネージャーボタン状態更新エラー: {e}")
    
    def _create_scroll_area(self):
        """スクロール可能なプログレスバーエリアを作成"""
        # スクロールバー付きCanvas
        scroll_container = tk.Frame(self.window)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(scroll_container)
        self.scrollbar = ttk.Scrollbar(
            scroll_container,
            orient=tk.VERTICAL,
            command=self.canvas.yview
        )
        
        self.scroll_frame = tk.Frame(self.canvas)
        
        # ⭐修正: スクロールフレームをCanvasに配置（幅を100%に）⭐
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor=tk.NW)
        self.canvas.config(yscrollcommand=self.scrollbar.set)
        
        # 配置
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ⭐修正: Canvas幅変更時にscroll_frameの幅を調整⭐
        def on_canvas_configure(event):
            # Canvasの幅に合わせてscroll_frameの幅を設定
            canvas_width = event.width
            self.canvas.itemconfig(self.canvas_window, width=canvas_width)
        
        self.canvas.bind('<Configure>', on_canvas_configure)
        
        # ⭐修正: スクロール領域の更新⭐
        def on_frame_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        self.scroll_frame.bind("<Configure>", on_frame_configure)
    
    def update_progress(
        self,
        progress_info: ProgressInfo,
        save_folder: Optional[str] = None,
        max_display: int = 10
    ):
        """
        プログレスバーを更新
        
        Args:
            progress_info: プログレス情報
            save_folder: 保存フォルダパス
            max_display: 最大表示数
        """
        url_index = progress_info.url_index
        
        # 既存のWidgetがあれば更新
        if url_index in self.widgets:
            widget = self.widgets[url_index]
            if widget.frame and widget.frame.winfo_exists():
                widget.update(progress_info, save_folder)
                self._auto_scroll()
                return
        
        # 新規作成
        widget = ProgressWidget(
            parent=self.scroll_frame,
            show_number=True,
            url_index=url_index,  # ⭐追加: url_indexを渡す⭐
            on_folder_click=self.on_folder_click,
            on_url_click=self.on_url_click
        )
        widget.update(progress_info, save_folder)
        self.widgets[url_index] = widget
        
        # 表示制限チェック
        self._apply_display_limit(max_display)
        
        # オートスクロール
        self._auto_scroll()
    
    def refresh_all(self, progress_list: List[ProgressInfo], managed_folders: Dict[str, str]):
        """
        全てのプログレスバーを最新情報で更新
        
        Args:
            progress_list: プログレス情報のリスト
            managed_folders: URL -> 保存フォルダのマッピング
        """
        # 既存のWidgetを全て破棄
        for widget in self.widgets.values():
            widget.destroy()
        self.widgets.clear()
        
        # 再作成
        for progress_info in progress_list:
            save_folder = managed_folders.get(progress_info.url)
            widget = ProgressWidget(
                parent=self.scroll_frame,
                show_number=True,
                url_index=progress_info.url_index,  # ⭐追加: url_indexを渡す⭐
                on_folder_click=self.on_folder_click,
                on_url_click=self.on_url_click
            )
            widget.update(progress_info, save_folder)
            self.widgets[progress_info.url_index] = widget
    
    def _apply_display_limit(self, max_display: int):
        """
        表示制限を適用（古いものから削除）
        
        Args:
            max_display: 最大表示数
        """
        if len(self.widgets) <= max_display:
            return
        
        # url_indexでソート（小さい方が古い）
        sorted_indices = sorted(self.widgets.keys())
        
        # 削除対象
        to_remove = sorted_indices[:len(self.widgets) - max_display]
        
        for url_index in to_remove:
            widget = self.widgets.pop(url_index)
            widget.destroy()
    
    def _toggle_auto_scroll(self):
        """オートスクロールのON/OFF切り替え"""
        self.auto_scroll_enabled = not self.auto_scroll_enabled
        
        # ボタンの見た目を変更
        if self.auto_scroll_enabled:
            self.auto_scroll_button.config(relief=tk.SUNKEN)
        else:
            self.auto_scroll_button.config(relief=tk.RAISED)
    
    def _auto_scroll(self):
        """オートスクロール実行"""
        if not self.auto_scroll_enabled:
            return
        
        if self.canvas:
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(1.0)  # 最下部に移動
    
    def _load_window_geometry(self) -> Optional[str]:
        """ウィンドウのジオメトリを読み込む"""
        try:
            config_file = "download_manager_window.json"
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('geometry')
        except Exception:
            pass
        return None
    
    def _save_window_geometry(self):
        """ウィンドウのジオメトリを保存"""
        try:
            if self.window and self.window.winfo_exists():
                geometry = self.window.geometry()
                config_file = "download_manager_window.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump({'geometry': geometry}, f)
        except Exception:
            pass
    
    def _on_window_configure(self, event):
        """ウィンドウ設定変更時の処理"""
        # ウィンドウが移動またはリサイズされた場合、保存
        if event.widget == self.window:
            self._save_window_geometry()
    
    def _on_window_close(self):
        """ウィンドウクローズ時の処理"""
        # ⭐追加: ウィンドウサイズと位置を保存⭐
        self._save_window_geometry()
        
        if self.on_close:
            self.on_close()
        
        # Widgetを全て破棄
        for widget in self.widgets.values():
            widget.destroy()
        self.widgets.clear()
        
        # ウィンドウを破棄
        if self.window:
            self.window.destroy()
            self.window = None
    
    def is_open(self) -> bool:
        """ウィンドウが開いているか"""
        return self.window is not None and self.window.winfo_exists()
    
    def show(self):
        """ウィンドウを表示"""
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
        else:
            self._create_window()
    
    def hide(self):
        """ウィンドウを非表示（⭐修正: 破棄する⭐）"""
        if self.window and self.window.winfo_exists():
            # ⭐追加: ウィンドウサイズと位置を保存⭐
            self._save_window_geometry()
            
            # ⭐修正: widgetを全て破棄⭐
            for widget in self.widgets.values():
                widget.destroy()
            self.widgets.clear()
            
            # ⭐修正: ウィンドウを破棄⭐
            self.window.destroy()
            self.window = None
    
    def update_button_states(self, state: str):
        """
        ボタン状態を更新（メインウィンドウと統一）
        
        Args:
            state: 状態名
                - 'idle': アイドル状態（ダウンロード前）
                - 'downloading': ダウンロード中
                - 'paused': 一時停止中
                - 'error': エラー発生
                - 'completed': 完了
        """
        if not self.is_open():
            return
        
        try:
            if state == 'idle':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='disabled')
                self.restart_button.config(state='disabled')
                self.skip_button.config(state='disabled')
            elif state == 'downloading':
                self.pause_button.config(state='normal')
                self.resume_button.config(state='disabled')
                self.restart_button.config(state='normal')
                self.skip_button.config(state='normal')
            elif state == 'paused':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='normal')
                self.restart_button.config(state='normal')
                self.skip_button.config(state='normal')
            elif state == 'error':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='disabled')
                self.restart_button.config(state='normal')
                self.skip_button.config(state='normal')
            elif state == 'completed':
                self.pause_button.config(state='disabled')
                self.resume_button.config(state='disabled')
                self.restart_button.config(state='disabled')
                self.skip_button.config(state='disabled')
        except Exception as e:
            pass  # ウィンドウが破棄されている場合はエラーを無視

