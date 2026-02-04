"""
メインウィンドウのプログレスバーView

責任:
1. メインウィンドウに最新のプログレスバーを1つだけ表示
2. プログレスバーコンテナの表示/非表示管理
3. 純粋なView（ロジックなし）
"""

import tkinter as tk
from typing import Optional, Callable

from .progress_data import ProgressInfo
from .progress_widget import ProgressWidget


class MainWindowView:
    """
    メインウィンドウのプログレスバーView
    
    設計原則:
    - 最新のプログレスバーのみ表示
    - 状態を最小限に保つ
    - 純粋なView（データ表示のみ）
    """
    
    def __init__(
        self,
        main_v_pane: tk.PanedWindow,
        bottom_pane: tk.Widget,
        on_folder_click: Optional[Callable[[int], None]] = None,
        on_url_click: Optional[Callable[[str], None]] = None,
    ):
        """
        Args:
            main_v_pane: メインの垂直PanedWindow
            bottom_pane: 下部ペイン（プログレスバーはこの前に挿入）
            on_folder_click: フォルダボタンクリック時のコールバック
            on_url_click: URLクリック時のコールバック
        """
        self.main_v_pane = main_v_pane
        self.bottom_pane = bottom_pane
        self.on_folder_click = on_folder_click
        self.on_url_click = on_url_click
        
        # 現在表示中のWidget
        self.current_widget: Optional[ProgressWidget] = None
        
        # 表示中のurl_index（重複更新を防ぐ）
        self.current_url_index: Optional[int] = None
    
    def show(self, progress_info: ProgressInfo, save_folder: Optional[str] = None):
        """
        プログレスバーを表示/更新
        
        Args:
            progress_info: プログレス情報
            save_folder: 保存フォルダパス
        """
        # Widgetが存在しない場合は作成
        if not self.current_widget or not self.current_widget.frame or not self.current_widget.frame.winfo_exists():
            # ⭐修正: main_v_paneを直接親として渡す（二重フレームを避ける）⭐
            self.current_widget = ProgressWidget(
                parent=self.main_v_pane,
                show_number=False,
                url_index=None,  # ⭐追加: メインウィンドウでは番号不要⭐
                on_folder_click=self.on_folder_click,
                on_url_click=self.on_url_click
            )
            
            # ⭐WidgetのframeをPanedWindowに追加⭐
            if self.current_widget.frame not in self.main_v_pane.panes():
                self.main_v_pane.add(
                    self.current_widget.frame,
                    height=150,
                    before=self.bottom_pane
                )
        
        # 更新
        self.current_widget.update(progress_info, save_folder)
        self.current_url_index = progress_info.url_index
    
    def hide(self):
        """プログレスバーを非表示"""
        if self.current_widget and self.current_widget.frame:
            # PanedWindowから削除
            if self.current_widget.frame in self.main_v_pane.panes():
                self.main_v_pane.forget(self.current_widget.frame)
            
            # Widgetを破棄
            self.current_widget.destroy()
            self.current_widget = None
        
        self.current_url_index = None
    
    def is_visible(self) -> bool:
        """プログレスバーが表示されているか"""
        return (
            self.current_widget is not None
            and self.current_widget.frame is not None
            and self.current_widget.frame.winfo_exists()
            and self.current_widget.frame in self.main_v_pane.panes()
        )

