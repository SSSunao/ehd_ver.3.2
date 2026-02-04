"""
単一プログレスバーWidget（再利用可能）

責任:
1. 1つのプログレスバーのGUI要素を管理
2. データの表示のみ（ロジックなし）
3. メインウィンドウ/ダウンロードマネージャー両方で使用可能
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable
import os
import webbrowser

from .progress_data import ProgressInfo


class ProgressWidget:
    """
    単一プログレスバーWidget
    
    設計原則:
    - 純粋なView（データ表示のみ）
    - 状態を持たない（Stateless）
    - 再利用可能
    """
    
    def __init__(
        self,
        parent: tk.Widget,
        show_number: bool = False,
        url_index: Optional[int] = None,
        on_folder_click: Optional[Callable[[int], None]] = None,
        on_url_click: Optional[Callable[[str], None]] = None,
    ):
        """
        Args:
            parent: 親Widget
            show_number: URL番号を表示するか
            url_index: URLインデックス（フレームタイトル用）
            on_folder_click: フォルダボタンクリック時のコールバック
            on_url_click: URLクリック時のコールバック
        """
        self.parent = parent
        self.show_number = show_number
        self.url_index = url_index
        self.on_folder_click = on_folder_click
        self.on_url_click = on_url_click
        
        # GUI要素
        self.frame: Optional[ttk.LabelFrame] = None
        self.title_label: Optional[tk.Label] = None
        self.status_label: Optional[tk.Label] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.folder_button: Optional[ttk.Button] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Widget群を作成"""
        # ⭐修正: オリジナルに合わせてLabelFrameを使用⭐
        frame_text = ""
        if self.show_number and self.url_index is not None:
            frame_text = f"ダウンロード進捗 ({self.url_index + 1})"
        else:
            frame_text = "現在のダウンロード進捗"
        
        # ⭐修正: ttk.LabelFrameで細くて薄い灰色の線で囲む⭐
        self.frame = ttk.LabelFrame(self.parent, text=frame_text, relief=tk.GROOVE, borderwidth=1)
        
        # ⭐修正: PanedWindowに直接追加する場合はpackを呼ばない⭐
        if not isinstance(self.parent, tk.PanedWindow):
            self.frame.pack(fill=tk.X, expand=False, padx=5, pady=3)
        
        # 上部フレーム（タイトル + フォルダボタン）
        top_frame = tk.Frame(self.frame)
        top_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        # ⭐修正: タイトルラベル - 太字を解除、通常の書体に⭐
        self.title_label = tk.Label(
            top_frame,
            text="準備中...",
            anchor=tk.W,
            font=("Arial", 9),  # ⭐修正: "bold"を削除⭐
            fg="black",
            cursor="hand2"
        )
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ⭐修正: フォルダボタン - ttk.Buttonに戻す⭐
        self.folder_button = ttk.Button(
            top_frame,
            text="📁",
            width=3,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.folder_button.pack(side=tk.RIGHT, padx=2)
        
        # ⭐修正: ステータスラベル - フォントサイズを8に（オリジナルに合わせる）⭐
        self.status_label = tk.Label(
            self.frame,
            text="状態: 待機中",
            anchor=tk.W,
            font=("", 8)
        )
        self.status_label.pack(fill=tk.X, padx=5, pady=(2, 0))
        
        # プログレスバー
        self.progress_bar = ttk.Progressbar(
            self.frame,
            orient=tk.HORIZONTAL,
            length=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, padx=5, pady=(2, 5))
    
    def update(self, progress_info: ProgressInfo, save_folder: Optional[str] = None):
        """
        プログレスバーを更新
        
        Args:
            progress_info: プログレス情報（Immutable）
            save_folder: 保存フォルダパス（Noneの場合はボタン無効化）
        """
        if not self.frame or not self.frame.winfo_exists():
            return
        
        # ⭐修正: タイトル更新 - 数値は削除（フレームタイトルに表示済み）⭐
        display_text = progress_info.display_title
        self.title_label.config(text=display_text)
        
        # URLリンク設定
        self._setup_url_link(progress_info.url, progress_info.display_title)
        
        # ステータス更新
        self.status_label.config(text=progress_info.build_status_text())
        
        # プログレスバー更新
        self.progress_bar['value'] = progress_info.progress_percent
        
        # フォルダボタン更新
        self._update_folder_button(progress_info.url_index, save_folder)
    
    def _setup_url_link(self, url: str, title: str):
        """URLリンクを設定"""
        if not url or title == "準備中...":
            # リンクを無効化
            self.title_label.unbind("<Button-1>")
            self.title_label.unbind("<Enter>")
            self.title_label.unbind("<Leave>")
            self.title_label.config(fg="black", cursor="arrow")
            return
        
        # リンクを有効化
        def on_click(event):
            if self.on_url_click:
                self.on_url_click(url)
        
        self.title_label.bind("<Button-1>", on_click)
        self.title_label.bind("<Enter>", lambda e: self.title_label.config(fg="blue"))
        self.title_label.bind("<Leave>", lambda e: self.title_label.config(fg="black"))
        self.title_label.config(cursor="hand2")
    
    def _update_folder_button(self, url_index: int, save_folder: Optional[str]):
        """フォルダボタンの状態を更新"""
        if save_folder and os.path.exists(save_folder):
            self.folder_button.config(state=tk.NORMAL)
            
            def on_click():
                if self.on_folder_click:
                    self.on_folder_click(url_index)
            
            # 既存のバインディングを削除
            self.folder_button.config(command=on_click)
        else:
            self.folder_button.config(state=tk.DISABLED)
    
    def destroy(self):
        """Widgetを破棄"""
        if self.frame and self.frame.winfo_exists():
            self.frame.destroy()

