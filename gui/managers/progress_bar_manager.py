# -*- coding: utf-8 -*-
"""
ProgressBarManager - プログレスバー管理の一元化

責任範囲:
- プログレスバーの生成・更新・削除
- メインウィンドウ/ダウンロードマネージャーの両対応
- StateManagerをSingle Source of Truthとして使用
"""

import tkinter as tk
from tkinter import ttk
import time
from typing import Dict, Any, Optional, List
import os


class ProgressBarManager:
    """プログレスバー管理クラス
    
    40+メソッドを10メソッド以下に削減し、責任を明確化。
    """
    
    def __init__(self, parent, state_manager, main_container=None):
        """初期化
        
        Args:
            parent: EHDownloaderインスタンス
            state_manager: StateManagerインスタンス（Single Source of Truth）
            main_container: メインウィンドウのプログレスバーコンテナ
        """
        self.parent = parent
        self.state_manager = state_manager
        self.main_container = main_container
        
        # メインウィンドウのプログレスバーウィジェット
        self.main_widgets = None
        
        # ダウンロードマネージャーのプログレスバーウィジェット
        # {url_index: {'bar', 'status', 'title', 'frame', ...}}
        self.separate_widgets = {}
        
        # ダウンロードマネージャーウィンドウ
        self.separate_window = None
        self.separate_window_scrollable_frame = None
        
        # 現在アクティブなurl_index（メインウィンドウ表示用）
        self.active_url_index = -1
    
    def ensure_progress_bar(self, url_index: int) -> Dict[str, Any]:
        """プログレスバーを確実に取得（なければ作成）
        
        Args:
            url_index: URLインデックス
            
        Returns:
            Dict: プログレスバーウィジェット情報
        """
        # StateManagerから最新情報を取得
        progress_info = self.state_manager.get_progress_bar(url_index)
        if not progress_info:
            # StateManagerにプログレスバーが存在しない場合は作成
            url = self._get_url_for_index(url_index)
            if url:
                progress_info = self.state_manager.create_progress_bar(
                    url=url,
                    url_index=url_index
                )
        
        # ダウンロードマネージャーウィンドウが開いている場合
        if self.separate_window and self.separate_window.winfo_exists():
            if url_index not in self.separate_widgets:
                self._create_separate_window_widgets(url_index, progress_info)
            return self.separate_widgets[url_index]
        
        # メインウィンドウの場合
        if not self.main_widgets:
            self._create_main_window_widgets()
        
        self.active_url_index = url_index
        return self.main_widgets
    
    def update_progress_bar(self, url_index: int, current: int = None, total: int = None, 
                          status: str = None, title: str = None):
        """プログレスバーを更新（単一メソッド）
        
        Args:
            url_index: URLインデックス
            current: 現在のページ数
            total: 総ページ数
            status: ステータステキスト
            title: タイトル
        """
        # StateManagerを更新
        update_data = {}
        if current is not None:
            update_data['current'] = int(current)
        if total is not None:
            update_data['total'] = int(total)
        if status is not None:
            update_data['status'] = str(status)
        if title is not None:
            update_data['title'] = str(title)
        
        if update_data:
            self.state_manager.update_progress_bar_state(url_index, **update_data)
        
        # StateManagerから最新情報を取得
        progress_info = self.state_manager.get_progress_bar(url_index)
        if not progress_info:
            return
        
        # GUIウィジェットを更新
        self._update_widgets(url_index, progress_info)
    
    def remove_progress_bar(self, url_index: int):
        """プログレスバーを削除
        
        Args:
            url_index: URLインデックス
        """
        # StateManagerから削除
        self.state_manager.remove_progress_bar(url_index)
        
        # ダウンロードマネージャーのウィジェットを削除
        if url_index in self.separate_widgets:
            widgets = self.separate_widgets[url_index]
            if 'frame' in widgets and widgets['frame']:
                try:
                    widgets['frame'].destroy()
                except:
                    pass
            del self.separate_widgets[url_index]
        
        # メインウィンドウのアクティブインデックスをクリア
        if self.active_url_index == url_index:
            self.active_url_index = -1
            if self.main_widgets:
                self._clear_main_window_widgets()
    
    def get_progress_bar(self, url_index: int) -> Optional[Dict[str, Any]]:
        """プログレスバー情報を取得
        
        Args:
            url_index: URLインデックス
            
        Returns:
            Optional[Dict]: プログレスバー情報（StateManagerから取得）
        """
        return self.state_manager.get_progress_bar(url_index)
    
    def get_all_progress_bars(self) -> Dict[int, Dict[str, Any]]:
        """すべてのプログレスバー情報を取得
        
        Returns:
            Dict: {url_index: progress_info}
        """
        return self.state_manager.get_all_progress_bars()
    
    def open_download_manager(self):
        """ダウンロードマネージャーウィンドウを開く"""
        if self.separate_window and self.separate_window.winfo_exists():
            self.separate_window.lift()
            return
        
        # ウィンドウ作成
        self.separate_window = tk.Toplevel(self.parent.root)
        self.separate_window.title("ダウンロードマネージャー")
        self.separate_window.geometry("800x600")
        
        # スクロール可能なフレーム作成
        canvas = tk.Canvas(self.separate_window)
        scrollbar = ttk.Scrollbar(self.separate_window, orient="vertical", command=canvas.yview)
        self.separate_window_scrollable_frame = ttk.Frame(canvas)
        
        self.separate_window_scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.separate_window_scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 既存のプログレスバーを表示
        self._rebuild_separate_window()
        
        # ウィンドウが閉じられたときの処理
        self.separate_window.protocol("WM_DELETE_WINDOW", self.close_download_manager)
    
    def close_download_manager(self):
        """ダウンロードマネージャーウィンドウを閉じる"""
        if self.separate_window:
            # ウィジェット情報をクリア
            self.separate_widgets.clear()
            self.separate_window_scrollable_frame = None
            
            try:
                self.separate_window.destroy()
            except:
                pass
            self.separate_window = None
    
    # ========================================
    # 内部メソッド（プライベート）
    # ========================================
    
    def _create_main_window_widgets(self):
        """メインウィンドウのプログレスバーウィジェットを作成"""
        if not self.main_container:
            return
        
        # フレーム作成
        frame = ttk.Frame(self.main_container)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # タイトルラベル
        title_label = ttk.Label(frame, text="準備中...", font=("", 10, "bold"))
        title_label.pack(anchor=tk.W, pady=(0, 2))
        
        # プログレスバー
        progress_bar = ttk.Progressbar(frame, mode='determinate')
        progress_bar.pack(fill=tk.X, pady=(0, 2))
        
        # ステータスラベル
        status_label = ttk.Label(frame, text="状態: 待機中", font=("", 9))
        status_label.pack(anchor=tk.W)
        
        self.main_widgets = {
            'frame': frame,
            'title': title_label,
            'bar': progress_bar,
            'status': status_label
        }
    
    def _create_separate_window_widgets(self, url_index: int, progress_info: Dict[str, Any]):
        """ダウンロードマネージャーのプログレスバーウィジェットを作成
        
        Args:
            url_index: URLインデックス
            progress_info: プログレスバー情報
        """
        if not self.separate_window_scrollable_frame:
            return
        
        # フレーム作成
        frame = ttk.LabelFrame(self.separate_window_scrollable_frame, text=f"#{url_index + 1}")
        frame.pack(fill=tk.X, padx=5, pady=2)
        
        # タイトルラベル
        title_text = progress_info.get('title', '準備中...')
        title_label = ttk.Label(frame, text=title_text, font=("", 9, "bold"))
        title_label.pack(anchor=tk.W, padx=5, pady=(2, 2))
        
        # プログレスバー
        progress_bar = ttk.Progressbar(frame, mode='determinate')
        progress_bar.pack(fill=tk.X, padx=5, pady=(0, 2))
        
        # ステータスラベル
        status_text = progress_info.get('status', '状態: 待機中')
        status_label = ttk.Label(frame, text=status_text, font=("", 8))
        status_label.pack(anchor=tk.W, padx=5, pady=(0, 2))
        
        self.separate_widgets[url_index] = {
            'frame': frame,
            'title': title_label,
            'bar': progress_bar,
            'status': status_label,
            'url_index': url_index
        }
    
    def _update_widgets(self, url_index: int, progress_info: Dict[str, Any]):
        """ウィジェットを更新
        
        Args:
            url_index: URLインデックス
            progress_info: プログレスバー情報
        """
        current = progress_info.get('current', 0)
        total = progress_info.get('total', 0)
        title = progress_info.get('title', '準備中...')
        status = progress_info.get('status', '状態: 待機中')
        
        # 型安全性確保
        try:
            current = int(current)
            total = int(total)
        except (ValueError, TypeError):
            current = 0
            total = 0
        
        if not isinstance(title, str):
            title = '準備中...'
        if not isinstance(status, str):
            status = '状態: 待機中'
        
        # プログレス計算
        progress_percent = (current / total * 100) if total > 0 else 0
        
        # ダウンロードマネージャーウィンドウの更新
        if url_index in self.separate_widgets:
            widgets = self.separate_widgets[url_index]
            try:
                if widgets['bar']:
                    widgets['bar']['maximum'] = total
                    widgets['bar']['value'] = current
                if widgets['title']:
                    widgets['title'].config(text=title)
                if widgets['status']:
                    widgets['status'].config(text=status)
            except tk.TclError:
                pass
        
        # メインウィンドウの更新（アクティブな場合のみ）
        if url_index == self.active_url_index and self.main_widgets:
            try:
                if self.main_widgets['bar']:
                    self.main_widgets['bar']['maximum'] = total
                    self.main_widgets['bar']['value'] = current
                if self.main_widgets['title']:
                    self.main_widgets['title'].config(text=title)
                if self.main_widgets['status']:
                    self.main_widgets['status'].config(text=status)
            except tk.TclError:
                pass
    
    def _clear_main_window_widgets(self):
        """メインウィンドウのプログレスバーをクリア"""
        if not self.main_widgets:
            return
        
        try:
            if self.main_widgets['bar']:
                self.main_widgets['bar']['value'] = 0
            if self.main_widgets['title']:
                self.main_widgets['title'].config(text="準備中...")
            if self.main_widgets['status']:
                self.main_widgets['status'].config(text="状態: 待機中")
        except tk.TclError:
            pass
    
    def _rebuild_separate_window(self):
        """ダウンロードマネージャーウィンドウを再構築"""
        if not self.separate_window_scrollable_frame:
            return
        
        # 既存のウィジェットをクリア
        for widgets in self.separate_widgets.values():
            if 'frame' in widgets and widgets['frame']:
                try:
                    widgets['frame'].destroy()
                except:
                    pass
        self.separate_widgets.clear()
        
        # StateManagerからすべてのプログレスバーを取得して再作成
        all_progress = self.state_manager.get_all_progress_bars()
        for url_index in sorted(all_progress.keys()):
            progress_info = all_progress[url_index]
            self._create_separate_window_widgets(url_index, progress_info)
            self._update_widgets(url_index, progress_info)
    
    def _get_url_for_index(self, url_index: int) -> Optional[str]:
        """インデックスからURLを取得
        
        Args:
            url_index: URLインデックス
            
        Returns:
            Optional[str]: URL
        """
        try:
            if hasattr(self.parent, 'url_text'):
                urls = self.parent.url_text.get("1.0", tk.END).strip().split('\n')
                if 0 <= url_index < len(urls):
                    return urls[url_index].strip()
        except:
            pass
        return None
