# -*- coding: utf-8 -*-
"""
TorrentファイルDLマネージャーコンポーネント
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from config.settings import ToolTip

class TorrentDownloadManager:
    def __init__(self, parent):
        self.parent = parent
        self.window = None
        self.is_running = False
        self.is_paused = False
        self.download_thread = None
        self.pause_event = threading.Event()
        self.stop_flag = threading.Event()
        
        # 設定ファイルのパス
        self.settings_file = "ehd_settings.json"
        
        # ウィンドウ設定のデフォルト値
        self._default_window_geometry = "670x1100+100+100"
        self.window_geometry = self._default_window_geometry
        self.window_state = "normal"
        
        # デフォルト設定
        self._default_torrent_save_directory = os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")
        self._default_page_wait_time = 1.0
        self._default_error_handling = "中断"
        self._default_torrent_selection = "並び順で最下部"
        self._default_duplicate_file_mode = "rename"  # デフォルトはリネーム（連番）
        
        # フィルタリング設定のデフォルト値
        self._default_filtering_enabled = False
        self._default_filtering_size = 600  # MB
        self._default_filtering_action = "max_only"
        
        # 内部設定値（初期化は設定読み込み時に行う）
        self.torrent_save_directory = None
        self.page_wait_time = None
        self.error_handling = None
        self.torrent_selection = None
        self.duplicate_file_mode = None
        
        # フィルタリング設定の内部値
        self.filtering_enabled = None
        self.filtering_size = None
        self.filtering_action = None
        
        # ダウンロード状態管理
        self.current_url_index = 0
        
        # GUI変数（初期化は後で行う）
        self.torrent_save_dir_var = None
        self.page_wait_var = None
        self.error_handling_var = None
        self.torrent_selection_var = None
        self.duplicate_file_mode_var = None
        
        # フィルタリング設定のGUI変数
        self.filtering_enabled_var = None
        self.filtering_size_var = None
        self.filtering_action_var = None
        
        # データ
        self.torrent_data = []
        self.resume_points = {}
        self.current_index = 0
        self.completed_count = 0
        self.total_count = 0
        
        # スキップ処理中フラグ
        self._skip_processing = False
        
        # セレクションオプション
        self.selection_options = [
            "並び順で最下部",
            "並び順で最上部", 
            "サイズ最大",
            "サイズ最小",
            "投稿日が最新",
            "DL数最大",
            "seeds最大",
            "peers最大"
        ]
        
        # エラー処理オプション
        self.error_options = [
            "中断",
            "そのURLをスキップ",
            "SeleniumをONにして1度だけ再試行"
        ]
        
        # ツールチップテキスト
        self.tooltip_texts = {
            'save_directory': 'Torrentファイルの保存先ディレクトリを指定します。',
            'page_wait': 'ページ遷移時の待機時間（秒）を指定します。サーバーに負荷をかけないよう適切な値を設定してください。',
            'error_handling': 'ダウンロードエラーが発生した場合の処理方法を選択します。',
            'torrent_selection': '複数のTorrentファイルが存在する場合の選択方法を指定します。',
            'duplicate_file_mode': '同名のTorrentファイルが既に存在する場合の処理方法を選択します。\n・上書き: 既存ファイルを上書き保存\n・リネーム（連番）: ファイル名に連番を付けて保存\n・スキップ: 同名ファイルはスキップして次のURLに進む',
            'filtering': 'Torrentファイルのサイズでフィルタリングを行います。\n・最大容量のものだけDL: 指定容量以上の最大サイズファイルのみ\n・最大容量のファイルと選択したファイルを両方DL: 最大サイズファイルと選択したファイル\n・容量以上のファイルを全てDL: 指定容量以上の全ファイル'
        }
    
    def show_window(self):
        """Torrentマネージャーウィンドウを表示"""
        if self.window is None or not self.window.winfo_exists():
            self._create_window()
        else:
            self.window.lift()
            self.window.focus_force()
    
    def _create_window(self):
        """ウィンドウを作成"""
        self.window = tk.Toplevel(self.parent.root)
        self.window.title("TorrentファイルDLマネージャー")
        
        # ウィンドウ設定を復元
        self._load_window_settings()
        
        self.window.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # ウィンドウフォーカスを設定（grab_setは削除）
        self.window.focus_force()
        
        # メインフレーム
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # ヘッダー
        self._create_header(main_frame)
        
        # 設定エリア
        self._create_settings_area(main_frame)
        
        # メインエリア（URLリスト）
        self._create_main_area(main_frame)
        
        # フッター（ログ）
        self._create_footer(main_frame)
        
        # 初期状態設定
        self._toggle_buttons_state(False)
        
        # 設定を読み込み（GUI作成後）
        self._load_settings()
    
    def _create_header(self, parent):
        """ヘッダーエリアを作成"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 5))
        
        # 左側のボタン
        left_frame = ttk.Frame(header_frame)
        left_frame.pack(side="left")
        
        self.execute_btn = ttk.Button(left_frame, text="実行", command=self._start_download)
        self.execute_btn.pack(side="left", padx=(0, 5))
        
        self.pause_btn = ttk.Button(left_frame, text="中断", command=self._pause_download)
        self.pause_btn.pack(side="left", padx=(0, 5))
        
        self.skip_btn = ttk.Button(left_frame, text="スキップ", command=self._skip_current, state="normal")
        self.skip_btn.pack(side="left", padx=(0, 5))
        
        # 右側のボタン
        right_frame = ttk.Frame(header_frame)
        right_frame.pack(side="right")
        
        self.clear_btn = ttk.Button(right_frame, text="クリア", command=self._clear_data)
        self.clear_btn.pack(side="left")
    
    def _create_settings_area(self, parent):
        """設定エリアを作成"""
        settings_frame = ttk.LabelFrame(parent, text="設定")
        settings_frame.pack(fill="x", pady=(0, 5))
        
        # 保存先ディレクトリ
        dir_frame = ttk.Frame(settings_frame)
        dir_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(dir_frame, text="保存先:").pack(side="left")
        self.torrent_save_dir_var = tk.StringVar()
        self.torrent_save_dir_entry = ttk.Entry(dir_frame, textvariable=self.torrent_save_dir_var, width=40)
        self.torrent_save_dir_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))
        ToolTip(self.torrent_save_dir_entry, self.tooltip_texts['save_directory'])
        
        open_btn = ttk.Button(dir_frame, text="開く", command=self._open_directory, width=6)
        open_btn.pack(side="right", padx=(0, 5))
        ToolTip(open_btn, "現在設定されている保存先ディレクトリを開きます")
        
        self.select_dir_btn = ttk.Button(dir_frame, text="参照", command=self._select_directory, width=6)
        self.select_dir_btn.pack(side="right")
        ToolTip(self.select_dir_btn, "保存先ディレクトリを選択します")
        
        # ページ遷移Wait
        wait_frame = ttk.Frame(settings_frame)
        wait_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(wait_frame, text="Wait(s):").pack(side="left")
        self.page_wait_var = tk.StringVar()
        self.page_wait_entry = ttk.Entry(wait_frame, textvariable=self.page_wait_var, width=10)
        self.page_wait_entry.pack(side="left", padx=(5, 0))
        ToolTip(self.page_wait_entry, self.tooltip_texts['page_wait'])
        
        # エラー時処理
        error_frame = ttk.Frame(settings_frame)
        error_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(error_frame, text="エラー時:").pack(side="left")
        self.error_handling_var = tk.StringVar()
        self.error_handling_combo = ttk.Combobox(error_frame, textvariable=self.error_handling_var, values=self.error_options, state="readonly", width=20)
        self.error_handling_combo.pack(side="left", padx=(5, 0))
        ToolTip(self.error_handling_combo, self.tooltip_texts['error_handling'])
        
        # Torrent選択
        selection_frame = ttk.Frame(settings_frame)
        selection_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(selection_frame, text="選択:").pack(side="left")
        self.torrent_selection_var = tk.StringVar()
        self.torrent_selection_combo = ttk.Combobox(selection_frame, textvariable=self.torrent_selection_var, values=self.selection_options, state="readonly", width=20)
        self.torrent_selection_combo.pack(side="left", padx=(5, 0))
        ToolTip(self.torrent_selection_combo, self.tooltip_texts['torrent_selection'])
        
        # 同名ファイル処理設定
        duplicate_file_frame = ttk.Frame(settings_frame)
        duplicate_file_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(duplicate_file_frame, text="同名ファイル処理:").pack(side="left")
        self.duplicate_file_mode_var = tk.StringVar()
        self.duplicate_file_combo = ttk.Combobox(duplicate_file_frame, textvariable=self.duplicate_file_mode_var, 
                                           values=["上書き", "リネーム（連番）", "スキップ"], 
                                           state="readonly", width=15)
        self.duplicate_file_combo.pack(side="left", padx=(5, 0))
        ToolTip(self.duplicate_file_combo, self.tooltip_texts['duplicate_file_mode'])
        
        # 選択変更時の処理
        def on_duplicate_file_change(event):
            selection = self.duplicate_file_combo.current()
            if selection == 0:
                self.duplicate_file_mode = "overwrite"
            elif selection == 1:
                self.duplicate_file_mode = "rename"
            elif selection == 2:
                self.duplicate_file_mode = "skip"
            self._sync_gui_to_internal()
        
        self.duplicate_file_combo.bind('<<ComboboxSelected>>', on_duplicate_file_change)
        
        # フィルタリング設定（同名ファイル処理の下に追加）
        filtering_frame = ttk.Frame(settings_frame)
        filtering_frame.pack(fill="x", padx=5, pady=2)
        
        # 1行目: タイトルと有効チェックボックス
        filtering_row1 = ttk.Frame(filtering_frame)
        filtering_row1.pack(fill="x")
        
        ttk.Label(filtering_row1, text="フィルタリング:").pack(side="left")
        
        # 有効ラジオボタン
        self.filtering_enabled_var = tk.BooleanVar()
        self.filtering_enabled_cb = ttk.Checkbutton(filtering_row1, text="有効", 
                                             variable=self.filtering_enabled_var)
        self.filtering_enabled_cb.pack(side="left", padx=(5, 10))
        ToolTip(self.filtering_enabled_cb, self.tooltip_texts['filtering'])
        
        # 容量入力フォーム
        ttk.Label(filtering_row1, text="容量:").pack(side="left")
        self.filtering_size_var = tk.StringVar(value="600")
        self.filtering_size_entry = ttk.Entry(filtering_row1, textvariable=self.filtering_size_var, width=8)
        self.filtering_size_entry.pack(side="left", padx=(5, 5))
        ttk.Label(filtering_row1, text="MB以上のファイルがある時:").pack(side="left", padx=(0, 5))
        
        # 2行目: セレクトBOX（改行）
        filtering_row2 = ttk.Frame(filtering_frame)
        filtering_row2.pack(fill="x", pady=(2, 0))
        
        self.filtering_action_var = tk.StringVar(value="最大容量のものだけDL")
        self.filtering_action_combo = ttk.Combobox(filtering_row2, textvariable=self.filtering_action_var,
                                            values=["最大容量のものだけDL", "最大容量のファイルと選択したファイルを両方DL", "容量以上のファイルを全てDL"],
                                            state="readonly", width=38)  # 横幅を1.5倍に（25→38）
        self.filtering_action_combo.pack(side="left", padx=(0, 0))
        
        # 選択変更時の処理
        def on_filtering_action_change(event):
            selection = self.filtering_action_combo.current()
            if selection == 0:
                self.filtering_action = "max_only"
            elif selection == 1:
                self.filtering_action = "max_and_selected"
            elif selection == 2:
                self.filtering_action = "all_above"
            self._sync_gui_to_internal()
        
        self.filtering_action_combo.bind('<<ComboboxSelected>>', on_filtering_action_change)
        
        # チェック外しボタンを設定パネルの最下部に追加
        uncheck_button_frame = ttk.Frame(settings_frame)
        uncheck_button_frame.pack(fill="x", padx=5, pady=(10, 5))
        
        # DL完了したギャラリーに対応する検索結果パーサーのチェックを外すボタン
        self.uncheck_button = ttk.Button(uncheck_button_frame, text="DL完了したギャラリーに対応する検索結果パーサーのチェックを外す",
                                        command=self._uncheck_successful_downloads)
        self.uncheck_button.pack(fill="x")
    
    def _create_main_area(self, parent):
        """メインエリア（URLリスト）を作成"""
        # ヘッダーフレーム（プログレス表示用）
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill="x", pady=(0, 5))
        
        main_area_frame = ttk.LabelFrame(header_frame, text="URLリスト")
        main_area_frame.pack(fill="x")
        
        # プログレス表示
        progress_frame = ttk.Frame(main_area_frame)
        progress_frame.pack(fill="x", padx=5, pady=2)
        
        self.progress_label = ttk.Label(progress_frame, text="完了: 0/0")
        self.progress_label.pack(side="right")
        
        # スクロール可能なリスト
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, pady=(0, 5))
        
        # Treeview（ハイパーリンク対応）
        columns = ("Title", "URL", "Status")
        self.url_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        # 列の設定
        self.url_tree.heading("Title", text="タイトル")
        self.url_tree.heading("URL", text="ギャラリーURL")
        self.url_tree.heading("Status", text="状態")
        self.url_tree.column("Title", width=200)
        self.url_tree.column("URL", width=300)
        self.url_tree.column("Status", width=80)
        
        # スクロールバー
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.url_tree.yview)
        self.url_tree.configure(yscrollcommand=scrollbar.set)
        
        # ハイパーリンクスタイル（ttk.Treeviewではunderlineは使用不可）
        self.url_tree.tag_configure("hyperlink", foreground="blue")
        
        # クリックイベント
        self.url_tree.bind("<Button-1>", self._on_url_click)
        
        self.url_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    
    def _create_footer(self, parent):
        """フッター（ログ）を作成"""
        footer_frame = ttk.LabelFrame(parent, text="ログ")
        footer_frame.pack(fill="x")
        
        # ログテキストエリア
        log_frame = ttk.Frame(footer_frame)
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.log_text = tk.Text(log_frame, height=6, bg="#f0f0f0")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")
    
    def _toggle_buttons_state(self, is_running):
        """ボタンの状態を更新"""
        if is_running:
            self.execute_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")
            self.skip_btn.configure(state="normal")  # 実行中は有効
        elif self.is_paused:
            self.execute_btn.configure(state="disabled")
            self.pause_btn.configure(state="disabled")
            self.skip_btn.configure(state="normal")  # 中断中も有効
        else:
            self.execute_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")
            self.skip_btn.configure(state="disabled")  # アイドル時は無効
        
        # 設定パネルの全要素の制御
        running_or_paused = is_running or self.is_paused
        
        # 保存先ディレクトリボタン
        if hasattr(self, 'select_dir_btn'):
            self.select_dir_btn.config(state="normal" if not running_or_paused else "disabled")
        
        # ページ待機時間
        if hasattr(self, 'page_wait_entry'):
            self.page_wait_entry.config(state="normal" if not running_or_paused else "disabled")
        
        # エラー処理
        if hasattr(self, 'error_handling_combo'):
            self.error_handling_combo.config(state="normal" if not running_or_paused else "disabled")
        
        # Torrent選択
        if hasattr(self, 'torrent_selection_combo'):
            self.torrent_selection_combo.config(state="normal" if not running_or_paused else "disabled")
        
        # 同名ファイル処理
        if hasattr(self, 'duplicate_file_combo'):
            self.duplicate_file_combo.config(state="normal" if not running_or_paused else "disabled")
        
        # フィルタリングオプションの制御
        if hasattr(self, 'filtering_enabled_cb'):
            self.filtering_enabled_cb.config(state="normal" if not running_or_paused else "disabled")
        if hasattr(self, 'filtering_size_entry'):
            self.filtering_size_entry.config(state="normal" if not running_or_paused else "disabled")
        if hasattr(self, 'filtering_action_combo'):
            self.filtering_action_combo.config(state="normal" if not running_or_paused else "disabled")
    
    def _select_directory(self):
        """保存先ディレクトリを選択（遅延保存版）"""
        directory = filedialog.askdirectory(parent=self.window)
        if directory:
            # 内部値を直接更新
            self.torrent_save_directory = directory
            # GUIに同期
            if self.torrent_save_dir_var:
                self.torrent_save_dir_var.set(directory)
            
            # 設定保存を遅延（5秒後）
            if hasattr(self, '_save_timer'):
                self.window.after_cancel(self._save_timer)
            self._save_timer = self.window.after(5000, self._save_settings)
    
    def _start_download(self):
        """ダウンロードを開始"""
        if not self.torrent_data:
            messagebox.showwarning("警告", "ダウンロードするURLがありません")
            return
        
        # 既存のダウンロードが完了している場合は状態をクリア
        if not self.is_running and not self.is_paused:
            self._clear_download_state()
        
        # 設定を同期
        self._sync_gui_to_internal()
        
        # 設定を保存
        self._save_settings()
        
        # ダウンロード開始
        self.is_running = True
        self.is_paused = False
        self.stop_flag.clear()
        self.pause_event.clear()
        
        self._toggle_buttons_state(self.is_running)
        self._log(f"STARTED: {len(self.torrent_data)} URLs")
        
        # 現在の設定をログに出力
        self._log(f"設定: 保存先={self.torrent_save_directory}, Wait={self.page_wait_time}s, エラー処理={self.error_handling}, 選択={self.torrent_selection}, 同名ファイル処理={self.duplicate_file_mode}")
        
        # ダウンロードスレッドを開始
        self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
        self.download_thread.start()
    
    def _clear_download_state(self):
        """ダウンロード状態をクリア"""
        # 全URLの状態をリセット（成功状態は保持）
        for i, torrent_data in enumerate(self.torrent_data):
            current_status = torrent_data.get('status', '')
            # 成功状態の場合は保持、それ以外はリセット
            if current_status not in ['succeeded', 'completed', 'success']:
                torrent_data['status'] = 'pending'
                torrent_data['progress'] = 0
                torrent_data['error_message'] = ''
        
        # URLリストの表示を更新（成功状態は保持）
        for i in range(len(self.torrent_data)):
            current_status = self.torrent_data[i].get('status', '')
            if current_status not in ['succeeded', 'completed', 'success']:
                self._update_url_status(i, 'pending')
        
        # 完了カウンターをリセット
        self.completed_count = 0
        
        # 現在のURLインデックスをリセット
        self.current_index = 0
        
        self._log("ダウンロード状態をクリアしました")
    
    def _pause_download(self):
        """ダウンロードを中断"""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.stop_flag.set()  # スレッドを終了させる
            self._log("PAUSED")
            
            # 現在のURLの状態を「中断」に更新
            if 0 <= self.current_index < len(self.torrent_data):
                self._update_url_status(self.current_index, "paused")
            
            # ボタン状態を更新
            self._toggle_buttons_state(False)
    
    
    
    def _clear_data(self):
        """データをクリア"""
        if self.is_running:
            messagebox.showwarning("警告", "ダウンロード実行中はクリアできません")
            return
        
        self.torrent_data = []
        self.resume_points = {}
        self.current_index = 0
        # Treeviewのアイテムをクリア
        for item in self.url_tree.get_children():
            self.url_tree.delete(item)
        self.log_text.delete(1.0, tk.END)
        self._log("データをクリアしました")
    
    def _get_default_directory(self):
        """デフォルトディレクトリを取得"""
        return os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")
    
    def _sync_gui_to_internal(self):
        """GUIの値を内部値に同期"""
        if self.torrent_save_dir_var:
            directory = self.torrent_save_dir_var.get().strip()
            if directory:
                self.torrent_save_directory = directory
            else:
                self.torrent_save_directory = self._default_torrent_save_directory
        else:
            self.torrent_save_directory = self._default_torrent_save_directory
            
        if self.page_wait_var:
            try:
                self.page_wait_time = float(self.page_wait_var.get())
            except (ValueError, TypeError):
                self.page_wait_time = self._default_page_wait_time
        else:
            self.page_wait_time = self._default_page_wait_time
            
        if self.error_handling_var:
            self.error_handling = self.error_handling_var.get()
        else:
            self.error_handling = self._default_error_handling
            
        if self.torrent_selection_var:
            self.torrent_selection = self.torrent_selection_var.get()
        else:
            self.torrent_selection = self._default_torrent_selection
            
        if self.duplicate_file_mode_var:
            # GUI変数から内部値への変換
            gui_value = self.duplicate_file_mode_var.get()
            if gui_value == "上書き":
                self.duplicate_file_mode = "overwrite"
            elif gui_value == "リネーム（連番）":
                self.duplicate_file_mode = "rename"
            elif gui_value == "スキップ":
                self.duplicate_file_mode = "skip"
            else:
                self.duplicate_file_mode = self._default_duplicate_file_mode
        else:
            self.duplicate_file_mode = self._default_duplicate_file_mode
        
        # フィルタリング設定の同期
        if self.filtering_enabled_var:
            self.filtering_enabled = self.filtering_enabled_var.get()
        else:
            self.filtering_enabled = self._default_filtering_enabled
            
        if self.filtering_size_var:
            try:
                self.filtering_size = int(self.filtering_size_var.get())
            except (ValueError, TypeError):
                self.filtering_size = self._default_filtering_size
        else:
            self.filtering_size = self._default_filtering_size
            
        if self.filtering_action_combo:
            selection = self.filtering_action_combo.current()
            self._log(f"フィルタリング選択インデックス: {selection}")
            if selection == 0:
                self.filtering_action = "max_only"
            elif selection == 1:
                self.filtering_action = "max_and_selected"
            elif selection == 2:
                self.filtering_action = "all_above"
            else:
                self._log(f"未知の選択インデックス: {selection}, デフォルト値を使用")
                self.filtering_action = self._default_filtering_action
        else:
            self._log("フィルタリングComboboxが初期化されていません")
            self.filtering_action = self._default_filtering_action
    
    def _sync_internal_to_gui(self):
        """内部値をGUIに同期（親から設定を受け取る）"""
        try:
            # 親から設定を受け取る（独自読み込みは削除）
            if hasattr(self.parent, 'torrent_manager_settings') and self.parent.torrent_manager_settings:
                tm_settings = self.parent.torrent_manager_settings
                
                # 内部値に設定を反映
                if 'save_directory' in tm_settings:
                    self.torrent_save_directory = tm_settings['save_directory']
                if 'page_wait_time' in tm_settings:
                    self.page_wait_time = tm_settings['page_wait_time']
                if 'error_handling' in tm_settings:
                    self.error_handling = tm_settings['error_handling']
                if 'torrent_selection' in tm_settings:
                    self.torrent_selection = tm_settings['torrent_selection']
                if 'duplicate_file_mode' in tm_settings:
                    self.duplicate_file_mode = tm_settings['duplicate_file_mode']
                if 'filtering_enabled' in tm_settings:
                    self.filtering_enabled = tm_settings['filtering_enabled']
                if 'filtering_size' in tm_settings:
                    self.filtering_size = tm_settings['filtering_size']
                if 'filtering_action' in tm_settings:
                    self.filtering_action = tm_settings['filtering_action']
                
                self.parent.log("Torrentマネージャー設定を読み込みました", "debug")
            
            # GUIに同期
            if self.torrent_save_dir_var:
                self.torrent_save_dir_var.set(self.torrent_save_directory or self._default_torrent_save_directory)
            if self.page_wait_var:
                self.page_wait_var.set(str(self.page_wait_time or self._default_page_wait_time))
            if self.error_handling_var:
                self.error_handling_var.set(self.error_handling or self._default_error_handling)
            if self.torrent_selection_var:
                self.torrent_selection_var.set(self.torrent_selection or self._default_torrent_selection)
            if self.duplicate_file_mode_var:
                # 内部値からGUI変数への変換
                internal_value = self.duplicate_file_mode or self._default_duplicate_file_mode
                if internal_value == "overwrite":
                    self.duplicate_file_mode_var.set("上書き")
                elif internal_value == "rename":
                    self.duplicate_file_mode_var.set("リネーム（連番）")
                elif internal_value == "skip":
                    self.duplicate_file_mode_var.set("スキップ")
                else:
                    self.duplicate_file_mode_var.set("リネーム（連番）")  # デフォルト
            
            # フィルタリング設定の同期
            if self.filtering_enabled_var:
                self.filtering_enabled_var.set(self.filtering_enabled or self._default_filtering_enabled)
            if self.filtering_size_var:
                self.filtering_size_var.set(str(self.filtering_size or self._default_filtering_size))
            if self.filtering_action_var and self.filtering_action_combo:
                # 内部値を日本語の表示値に変換
                internal_value = self.filtering_action or self._default_filtering_action
            if internal_value == "max_only":
                self.filtering_action_var.set("最大容量のものだけDL")
                self.filtering_action_combo.current(0)
            elif internal_value == "max_and_selected":
                self.filtering_action_var.set("最大容量のファイルと選択したファイルを両方DL")
                self.filtering_action_combo.current(1)
            elif internal_value == "all_above":
                self.filtering_action_var.set("容量以上のファイルを全てDL")
                self.filtering_action_combo.current(2)
            else:
                self.filtering_action_var.set("最大容量のものだけDL")  # デフォルト
                self.filtering_action_combo.current(0)
        except Exception as e:
            self._log(f"設定同期エラー: {e}", "error")
    
    def _download_worker(self):
        """ダウンロードワーカースレッド"""
        try:
            # 中断されたURLから再開
            start_index = self.current_index
            
            for i in range(start_index, len(self.torrent_data)):
                if self.stop_flag.is_set():
                    break
                
                data = self.torrent_data[i]
                current_status = data.get('status', '')
                
                # 成功状態のURLはスキップ
                if current_status in ['succeeded', 'completed', 'success']:
                    self._log(f"URL{i+1} は既に成功済み - スキップ")
                    continue
                
                self.current_index = i
                self._update_url_status(i, "downloading")
                
                try:
                    result = self._download_single_torrent(data, i)
                    if result == True or result == "succeeded":
                        self._update_url_status(i, "succeeded")
                        self.completed_count += 1
                        self._update_progress()
                        self._log(f"URL{i+1} SUCCESS")
                    elif result == "inappropriate":
                        # フィルタリングによる不適として処理
                        self._update_url_status(i, "inappropriate")
                        self._log(f"URL{i+1} INAPPROPRIATE")
                    else:
                        # 中断フラグチェック（中断による失敗かどうかを判定）
                        if self.stop_flag.is_set():
                            self._log(f"URL{i+1}: 中断により停止")
                            self._update_url_status(i, "paused")
                            break
                        else:
                            self._update_url_status(i, "failed")
                            self._log(f"URL{i+1} ERROR: Download failed")
                            
                            # エラー処理前にWait
                            if self.page_wait_time > 0:
                                self._log(f"URL{i+1}: エラー処理前に{self.page_wait_time}秒待機")
                                time.sleep(self.page_wait_time)
                            
                            # エラー処理
                            if self.error_handling == "そのURLをスキップ":
                                self._update_url_status(i, "skipped")
                                continue
                            elif self.error_handling == "SeleniumをONにして1度だけ再試行":
                                # Selenium再試行（簡易実装）
                                try:
                                    success = self._download_with_selenium(data, i)
                                    if success:
                                        self._update_url_status(i, "succeeded")
                                        self.completed_count += 1
                                        self._update_progress()
                                        self._log(f"URL{i+1} SUCCESS (Selenium retry)")
                                    else:
                                        self._update_url_status(i, "failed")
                                        self._log(f"URL{i+1} ERROR: Selenium retry failed")
                                except Exception as selenium_error:
                                    self._update_url_status(i, "failed")
                                    self._log(f"URL{i+1} ERROR: Selenium retry failed - {str(selenium_error)}")
                            else:  # 中断
                                self._log("Download interrupted due to error")
                                break
                        
                except Exception as e:
                    self._update_url_status(i, "failed")
                    self._log(f"URL{i+1} ERROR: {str(e)}")
                    
                    # エラー処理
                    if self.error_handling == "そのURLをスキップ":
                        self._update_url_status(i, "skipped")
                        continue
                    elif self.error_handling == "SeleniumをONにして1度だけ再試行":
                        # Selenium再試行（簡易実装）
                        try:
                            success = self._download_with_selenium(data, i)
                            if success:
                                self._update_url_status(i, "succeeded")
                                self.completed_count += 1
                                self._update_progress()
                                self._log(f"URL{i+1} SUCCESS (Selenium retry)")
                            else:
                                self._update_url_status(i, "failed")
                                self._log(f"URL{i+1} ERROR: Selenium retry failed")
                        except Exception as selenium_error:
                            self._update_url_status(i, "failed")
                            self._log(f"URL{i+1} ERROR: Selenium retry failed - {str(selenium_error)}")
                    else:  # 中断
                        self._log("Download interrupted due to error")
                        break
                
                # 待機時間
                time.sleep(self.page_wait_time)
            
            # 完了処理の条件を緩和
            # 完了チェック
            if (not self.stop_flag.is_set() and 
                self.current_index >= len(self.torrent_data)):  # 全てのURLを処理した場合
                self._log("ALL DONE. Open folder?")
                if self.window:
                    self.window.after(0, self._show_completion_dialog)
            else:
                # 完了条件未満足
                pass
            
        except Exception as e:
            self._log(f"Download worker error: {str(e)}")
        finally:
            self.is_running = False
            self.is_paused = False
            if self.window:
                self.window.after(0, lambda: self._toggle_buttons_state(False))
    
    def _download_single_torrent(self, data, index):
        """単一のTorrentファイルをダウンロード"""
        try:
            # 中断フラグチェック
            if self.stop_flag.is_set():
                return False
            
            # 中断チェック（pause_event）
            if self.pause_event.is_set():
                return False
            
            # 復帰ポイントを作成
            self._create_resume_point(data, index)
            
            # ギャラリーページにアクセス
            response = requests.get(data['source_url'], timeout=30)
            response.raise_for_status()
            
            # コンテンツ警告処理
            if "Content Warning" in response.text or "Offensive For Everyone" in response.text:
                self._log(f"URL{index+1}: コンテンツ警告検出")
                # 警告承諾処理
                post_data = {'apply_warning': 'Apply Warning'}
                response = requests.post(data['source_url'], data=post_data, timeout=20)
                response.raise_for_status()
                self._log(f"URL{index+1}: 警告を承諾しました")
                
                # 警告承諾後は通常のDLメソッドを使用
                self._log(f"URL{index+1}: 警告承諾後、通常のDLメソッドを使用")
                return self._download_with_normal_method(data, index, response)
            
            # 復帰ポイント更新（ページ移動後）
            self._update_resume_point(index, 'gallery_page_loaded')
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # 待機
            time.sleep(self.page_wait_time)
            
            # 共通のTorrent処理を実行
            return self._process_torrent_download(data, index, response)
            
        except Exception as e:
            self._log(f"URL{index+1} Download error: {str(e)}")
            return False
    
    def _create_resume_point(self, data, index):
        """復帰ポイントを作成"""
        self.resume_points[index] = {
            'data': data,
            'index': index,
            'timestamp': time.time(),
            'stage': 'start'  # 開始時点
        }
    
    def _update_resume_point(self, index, stage):
        """復帰ポイントを更新"""
        if index in self.resume_points:
            self.resume_points[index]['stage'] = stage
            self.resume_points[index]['timestamp'] = time.time()
    
    def _get_resume_point(self, index):
        """復帰ポイントを取得"""
        return self.resume_points.get(index, None)
    
    def _find_torrent_links(self, html):
        """HTMLからTorrentリンクを検索"""
        patterns = [
            # 既存のパターン（gallerytorrents.php）
            r'https://e-hentai\.org/gallerytorrents\.php\?gid=\d+&amp;t=[0-9a-f]+',
            r'https://e-hentai\.org/gallerytorrents\.php\?gid=\d+&t=[0-9a-f]+',
            # ギャラリーページ用のパターン（href属性から抽出）
            r'href="(https://e-hentai\.org/gallerytorrents\.php\?gid=\d+&amp;t=[0-9a-f]+)"',
            r'href="(https://e-hentai\.org/gallerytorrents\.php\?gid=\d+&t=[0-9a-f]+)"',
            # 新しいパターン（直接Torrentファイル）
            r'https://ehtracker\.org/get/\d+/[a-f0-9]+\.torrent',
            r'https://ehtracker\.org/get/\d+/[a-f0-9-]+/[a-f0-9]+\.torrent',
            # 古いTorrent用のパターン（href属性から抽出）
            r'href="(https://ehtracker\.org/get/\d+/[^"]+\.torrent)"'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                # href属性の場合は最初のグループを取得
                if pattern.startswith('href='):
                    matches = [match for match in matches if match]
                self._log(f"Torrentリンク検索: パターン'{pattern}'で{len(matches)}個のリンクを発見")
                return matches
        
        self._log("Torrentリンク検索: どのパターンでもリンクが見つかりませんでした")
        return []
    
    def _extract_torrent_info(self, html):
        """Torrent情報を抽出"""
        # 古いTorrentページの検出
        if "There are no up-to-date torrents" in html:
            self._log("古いTorrentのみ利用可能")
            return self._extract_outdated_torrents(html)
        
        pattern = re.compile(
            r'Posted:</span>\s*<span[^>]*>([^<]+)</span>.*?'
            r'Size:</span>\s*([^<]+)</td>.*?'
            r'Seeds:</span>\s*(\d+)</td>.*?'
            r'Peers:</span>\s*(\d+)</td>.*?'
            r'Downloads:</span>\s*(\d+)</td>.*?'
            r'Uploader:</span>\s*([^<]+)</td>.*?'
            r'<a href="(https://ehtracker\.org/get/[^"]+\.torrent)".*?>([^<]+)</a>',
            re.S
        )
        
        results = []
        for match in pattern.findall(html):
            info = {
                "posted": match[0],
                "size": match[1],
                "seeds": int(match[2]),
                "peers": int(match[3]),
                "downloads": int(match[4]),
                "uploader": match[5].strip(),
                "torrent_url": match[6],
                "filename": match[7]
            }
            results.append(info)
        
        return results
    
    def _extract_outdated_torrents(self, html):
        """古いTorrent情報を抽出"""
        torrents = []
        # 古いTorrentのリンクとファイル名を抽出
        pattern = r'<a href="(https://ehtracker\.org/get/\d+/[^"]+\.torrent)".*?>([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        if not matches:
            self._log("古いTorrent: リンクが見つかりませんでした")
            return torrents
        
        for link, filename in matches:
            torrents.append({
                'posted': 'Unknown',
                'size': 'Unknown',
                'seeds': 'Unknown',
                'peers': 'Unknown',
                'downloads': 'Unknown',
                'uploader': 'Unknown',
                'torrent_url': link,
                'filename': filename.strip(),
                'is_outdated': True
            })
        
        self._log(f"古いTorrent: {len(torrents)}個のリンクを発見")
        return torrents
    
    def _select_torrent_candidate(self, candidates):
        """Torrent候補から選択"""
        if not candidates:
            return None
        
        mode = self.torrent_selection
        
        if mode == "並び順で最下部":
            return candidates[-1]
        elif mode == "並び順で最上部":
            return candidates[0]
        elif mode == "サイズ最大":
            return max(candidates, key=lambda c: self._size_to_bytes(c["size"]))
        elif mode == "サイズ最小":
            return min(candidates, key=lambda c: self._size_to_bytes(c["size"]))
        elif mode == "投稿日が最新":
            return max(candidates, key=lambda c: self._parse_datetime(c["posted"]))
        elif mode == "DL数最大":
            return max(candidates, key=lambda c: c["downloads"])
        elif mode == "seeds最大":
            return max(candidates, key=lambda c: c["seeds"])
        elif mode == "peers最大":
            return max(candidates, key=lambda c: c["peers"])
        else:
            return candidates[0]
    
    def _size_to_bytes(self, size_str):
        """サイズ文字列をバイト数に変換（MiB対応版）"""
        try:
            # より柔軟な正規表現パターン
            import re
            # 数値の後に単位が続くパターン（スペースなしも対応）
            patterns = [
                r'([\d.]+)\s*(MiB|MB|GB|KB)',  # スペースあり
                r'([\d.]+)(MiB|MB|GB|KB)',     # スペースなし
                r'([\d.]+)\s*(B)',             # バイト単位
            ]
            
            for pattern in patterns:
                match = re.search(pattern, size_str, re.IGNORECASE)
                if match:
                    value = float(match.group(1))
                    unit = match.group(2).upper()
                    
                    if unit == 'B':
                        result = value
                    elif unit == 'KB':
                        result = value * 1024
                    elif unit in ['MB', 'MIB']:
                        result = value * 1024 * 1024
                    elif unit == 'GB':
                        result = value * 1024 * 1024 * 1024
                    else:
                        result = 0
                    
                    return result
            
            # マッチしない場合はデフォルト値を返す（0ではなく適切な値）
            return 1024 * 1024  # 1MBをデフォルト値として返す
            
        except Exception as e:
            self._log(f"サイズ解析エラー: {size_str} - {e}")
            return 1024 * 1024  # エラー時も1MBをデフォルト値として返す
    
    def _parse_datetime(self, date_str):
        """日時文字列をパース"""
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M")
        except:
            return datetime.min
    
    def _handle_duplicate_torrent_file(self, filepath):
        """同名Torrentファイルの処理"""
        if not os.path.exists(filepath):
            return filepath
        
        mode = self.duplicate_file_mode or self._default_duplicate_file_mode
        self._log(f"同名ファイル処理モード: {mode}")
        
        if mode == "skip":
            self._log(f"同名ファイルが存在するためスキップします: {os.path.basename(filepath)}")
            return None
        elif mode == "overwrite":
            self._log(f"同名ファイルを上書きします: {os.path.basename(filepath)}")
            return filepath
        else:  # rename
            base, ext = os.path.splitext(filepath)
            counter = 1
            new_path = filepath
            
            while os.path.exists(new_path):
                new_path = f"{base}({counter}){ext}"
                counter += 1
            
            self._log(f"ファイル名を変更します: {os.path.basename(filepath)} → {os.path.basename(new_path)}")
            return new_path
    
    def _safe_download_torrent(self, torrent_url, timeout=30):
        """安全なTorrentファイルダウンロード"""
        try:
            # リクエストサイズ制限
            response = requests.get(torrent_url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # ファイルサイズチェック（例：10MB制限）
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB
                raise Exception(f"ファイルサイズが大きすぎます: {content_length} bytes")
            
            # チャンクごとに読み込み
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
                    # メモリ使用量制限
                    if len(content) > 10 * 1024 * 1024:  # 10MB
                        raise Exception("ファイルサイズが大きすぎます")
            
            return content
            
        except requests.exceptions.Timeout:
            raise Exception("ダウンロードタイムアウト")
        except requests.exceptions.RequestException as e:
            raise Exception(f"ダウンロードエラー: {e}")
        except Exception as e:
            raise Exception(f"予期しないエラー: {e}")
    
    def _download_with_selenium(self, data, index):
        """Seleniumを使用してダウンロード"""
        # 簡易実装（実際のSelenium処理は省略）
        return False
    
    def _update_url_status(self, index, status):
        """URLの状態を更新"""
        def update_ui():
            if index < len(self.url_tree.get_children()):
                # 状態の日本語表示
                status_texts = {
                    'pending': '待機中',
                    'downloading': 'ダウンロード中',
                    'succeeded': '完了',
                    'failed': '失敗',
                    'skipped': 'スキップ',
                    'paused': '中断'
                }
                status_text = status_texts.get(status, status)
                
                # 背景色を更新
                colors = {
                    'pending': 'white',
                    'downloading': 'yellow',
                    'succeeded': 'lightblue',
                    'failed': 'lightcoral',
                    'skipped': 'lightgray',
                    'paused': 'orange'
                }
                color = colors.get(status, 'white')
                # Treeviewでは背景色設定が制限されるため、タグで管理
                items = self.url_tree.get_children()
                if index < len(items):
                    item = items[index]
                    values = list(self.url_tree.item(item, 'values'))
                    if len(values) >= 3:
                        values[2] = status_text  # 状態列を更新
                        self.url_tree.item(item, values=values)
                    
                    if status == "downloading":
                        self.url_tree.item(item, tags=("downloading",))
                    elif status == "succeeded":
                        self.url_tree.item(item, tags=("succeeded",))
                    elif status == "failed":
                        self.url_tree.item(item, tags=("failed",))
                    elif status == "skipped":
                        self.url_tree.item(item, tags=("skipped",))
                    elif status == "paused":
                        self.url_tree.item(item, tags=("paused",))
        
        if self.window:
            self.window.after(0, update_ui)
    
    def _log(self, message):
        """ログを出力"""
        def log_ui():
            try:
                if self.window and self.log_text:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_message = f"[{timestamp}] {message}\n"
                    self.log_text.insert(tk.END, log_message)
                    self.log_text.see(tk.END)
            except Exception as e:
                print(f"ログ表示エラー: {e}")
        
        if self.window:
            self.window.after(0, log_ui)
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")
    
    def _show_completion_dialog(self):
        """完了ダイアログを表示"""
        result = messagebox.askyesno("完了", "DLフォルダを開きますか？")
        if result:
            # GUI変数の値を使用（入力フォームの値と一致させる）
            if self.torrent_save_dir_var:
                directory = self.torrent_save_dir_var.get().strip()
            else:
                directory = self.torrent_save_directory or self._default_torrent_save_directory
            
            if directory:
                try:
                    import subprocess
                    import platform
                    if platform.system() == "Windows":
                        subprocess.run(["explorer", directory])
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", directory])
                    else:  # Linux
                        subprocess.run(["xdg-open", directory])
                except Exception as e:
                    self._log(f"完了ダイアログでディレクトリを開けませんでした: {e}")
    
    def _on_closing(self):
        """ウィンドウが閉じられる時の処理"""
        if self.is_running:
            result = messagebox.askyesno("確認", "ダウンロード実行中です。終了しますか？")
            if not result:
                return
        
        # 設定を保存
        self._save_settings()
        
        # ウィンドウ設定を保存
        self._save_window_settings()
        
        self.stop_flag.set()
        if self.download_thread and self.download_thread.is_alive():
            self.download_thread.join(timeout=1.0)
        
        self.window.destroy()
        self.window = None
    
    def set_torrent_data(self, data_list):
        """Torrentデータを設定"""
        self.torrent_data = data_list
        self.total_count = len(data_list)
        self.completed_count = 0
        
        # url_treeが存在するかチェック
        if not hasattr(self, 'url_tree') or self.url_tree is None:
            self._log("エラー: url_treeが初期化されていません")
            return
            
        # 既存のアイテムをクリア
        for item in self.url_tree.get_children():
            self.url_tree.delete(item)
        
        for i, data in enumerate(data_list):
            url = data.get('source_url', 'Unknown')
            # ギャラリーIDを取得
            gallery_id = data.get('gallery_id', 'Unknown')
            # タイトルを取得（パーサーから渡されたデータから）
            title = data.get('title', f'Gallery {gallery_id}')
            
            # Treeviewにアイテムを追加
            item_id = self.url_tree.insert("", "end", values=(title, url, "待機中"), tags=("hyperlink",))
            self._update_url_status(i, "pending")
        
        self._log(f"Torrentデータを設定しました: {len(data_list)}件")
        self._update_progress()
    
    def _on_url_click(self, event):
        """URLクリックイベント"""
        item = self.url_tree.selection()[0] if self.url_tree.selection() else None
        if item:
            values = self.url_tree.item(item, 'values')
            if values and len(values) > 1:
                url = values[1]  # URL列（2番目）
                if url.startswith('http'):
                    import webbrowser
                    webbrowser.open(url)
    
    def _open_directory(self):
        """保存先ディレクトリを開く"""
        # GUI変数の値を使用（入力フォームの値と一致させる）
        if self.torrent_save_dir_var:
            directory = self.torrent_save_dir_var.get().strip()
        else:
            directory = self.torrent_save_directory or self._default_torrent_save_directory
            
        if not directory:
            self._log("保存先ディレクトリが設定されていません")
            return
        
        # ディレクトリが存在しない場合は作成
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                self._log(f"ディレクトリを作成しました: {directory}")
            except Exception as e:
                self._log(f"ディレクトリ作成エラー: {e}")
                return
        
        # ディレクトリを開く
        try:
            import subprocess
            import platform
            if platform.system() == "Windows":
                # まずos.startfileを試行（最も確実）
                try:
                    os.startfile(directory)
                    return  # 成功したら終了
                except Exception:
                    # 代替手段としてexplorerを試行
                    subprocess.run(["explorer", directory])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", directory])
            else:  # Linux
                subprocess.run(["xdg-open", directory])
        except Exception as e:
            self._log(f"ディレクトリを開けませんでした: {e}")
    
    def _skip_current(self):
        """現在のダウンロードをスキップ（手動スキップ専用メソッドを使用）"""
        # 連打防止: スキップ処理中は無効化
        if hasattr(self, '_skip_processing') and self._skip_processing:
            self._log("スキップ処理中です。しばらくお待ちください。")
            return
        
        self._skip_processing = True
        
        try:
            # 親の手動スキップ専用メソッドを呼び出し
            if hasattr(self.parent, 'skip_current_download_manual'):
                success = self.parent.skip_current_download_manual()
                if success:
                    self._log("URLをスキップしました")
                    # ダウンロードマネージャー固有の処理
                    if self.current_index < len(self.torrent_data):
                        self._update_url_status(self.current_index, "skipped")
                        self._update_progress()
                        self.current_index += 1
                else:
                    self._log("スキップ処理に失敗しました")
            else:
                # フォールバック: 既存の処理
                self._log("手動スキップ専用メソッドが見つかりません。既存の処理を使用します。")
                # スキップボタンが押されました
                
                if self.current_index < len(self.torrent_data):
                    self._log(f"URL {self.current_index + 1} をスキップします")
                    self._update_url_status(self.current_index, "skipped")
                    # completed_countは増加させない（実際にダウンロードが完了した場合のみ増加）
                    self._update_progress()
                    self.current_index += 1
                    
                    # 中断状態の場合は新しいスレッドで再開
                    if self.is_paused:
                        self.is_paused = False
                        self.stop_flag.clear()
                        self.pause_event.clear()
                        self._log("RESUMED")
                        
                        self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
                        self.download_thread.start()
                        self._toggle_buttons_state(True)
                    elif self.is_running:
                        # 実行中の場合はスレッドを停止して新しいスレッドで再開
                        self.stop_flag.set()
                        self._log("現在のスレッドを停止して再開します")
                        
                        def restart_download():
                            time.sleep(0.2)  # スレッド終了を待つ時間を延長
                            if not self.stop_flag.is_set():  # 再度スキップされていないかチェック
                                self.stop_flag.clear()
                                self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
                                self.download_thread.start()
                                self._toggle_buttons_state(True)
                        
                        threading.Thread(target=restart_download, daemon=True).start()
                    else:
                        self._log("アイドル状態のため、スキップのみ実行")
                else:
                    self._log("スキップするURLがありません")
        finally:
            # スキップ処理完了フラグをクリア（少し遅延）
            def clear_skip_flag():
                time.sleep(0.5)  # 0.5秒後にフラグをクリア
                self._skip_processing = False
            threading.Thread(target=clear_skip_flag, daemon=True).start()
    
    def _update_progress(self):
        """プログレス表示を更新"""
        def update_ui():
            try:
                if self.window and hasattr(self, 'progress_label') and self.progress_label:
                    self.progress_label.config(text=f"完了: {self.completed_count}/{self.total_count}")
            except Exception as e:
                print(f"プログレス更新エラー: {e}")
        
        if self.window:
            self.window.after(0, update_ui)
    
    def _update_url_status(self, index, status):
        """URLの状態を更新"""
        # torrent_dataの状態も更新
        if 0 <= index < len(self.torrent_data):
            self.torrent_data[index]['status'] = status
        
        if not hasattr(self, 'url_tree') or not self.url_tree:
            return
            
        items = self.url_tree.get_children()
        if 0 <= index < len(items):
            item = items[index]
            values = list(self.url_tree.item(item, 'values'))
            
            # 状態に応じてテキストと色を変更
            status_text = {
                "pending": "待機中",
                "downloading": "ダウンロード中",
                "succeeded": "完了",
                "failed": "失敗",
                "skipped": "スキップ",
                "inappropriate": "不適"
            }.get(status, "不明")
            
            values[2] = status_text  # Status列（3番目）
            self.url_tree.item(item, values=values)
            
            # タグで状態を管理（ttk.Treeviewでは色設定が制限される）
            if status == "downloading":
                self.url_tree.item(item, tags=("downloading", "hyperlink"))
            elif status == "succeeded":
                self.url_tree.item(item, tags=("succeeded", "hyperlink"))
            elif status == "failed":
                self.url_tree.item(item, tags=("failed", "hyperlink"))
            elif status == "skipped":
                self.url_tree.item(item, tags=("skipped", "hyperlink"))
            elif status == "inappropriate":
                self.url_tree.item(item, tags=("inappropriate", "hyperlink"))
            else:
                self.url_tree.item(item, tags=("hyperlink",))
    
    def _filter_torrents_by_size(self, torrents, size_mb, action):
        """Torrentファイルをサイズでフィルタリング（バイト数ベース）"""
        try:
            # MBをバイト数に変換
            size_bytes = size_mb * 1024 * 1024
            filtered_torrents = []
            
            for i, torrent in enumerate(torrents):
                # サイズ文字列をバイト数に変換（既存のメソッドを再利用）
                size_str = torrent.get('size', '0 MiB')
                torrent_size_bytes = self._size_to_bytes(size_str)
                
                if torrent_size_bytes >= size_bytes:
                    if action == "max_only":
                        # 最大容量のものだけDL
                        if not filtered_torrents:
                            filtered_torrents = [torrent]
                        else:
                            # 既存の最大サイズと比較（バイト数で）
                            existing_size_str = filtered_torrents[0].get('size', '0 MiB')
                            existing_size_bytes = self._size_to_bytes(existing_size_str)
                            if torrent_size_bytes > existing_size_bytes:
                                filtered_torrents = [torrent]
                            elif torrent_size_bytes == existing_size_bytes:
                                filtered_torrents.append(torrent)
                    elif action == "max_and_selected":
                        # 容量以上のファイルを全てDL（max_and_selectedはall_aboveと同じ動作）
                        filtered_torrents.append(torrent)
                    elif action == "all_above":
                        # 容量以上のファイルを全てDL
                        filtered_torrents.append(torrent)
                    else:
                        # デフォルト処理（all_aboveと同じ）
                        filtered_torrents.append(torrent)
            
            return filtered_torrents
        except Exception as e:
            self._log(f"フィルタリングエラー: {e}")
            return torrents
    
    def _load_window_settings(self):
        """ウィンドウ設定を読み込み"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    unified_settings = json.load(f)
                
                # 統合された設定からトーレントマネージャーの設定を取得
                settings = unified_settings.get('torrent_manager', {})
                window_geometry = settings.get("window_geometry", self._default_window_geometry)
                
                # ウィンドウのサイズと位置を設定
                self.window.geometry(window_geometry)
            else:
                # デフォルト設定を使用
                self.window.geometry(self._default_window_geometry)
        except Exception as e:
            self._log(f"ウィンドウ設定読み込みエラー: {e}")
            # エラー時はデフォルト設定を使用
            self.window.geometry(self._default_window_geometry)
    
    def _save_window_settings(self):
        """ウィンドウ設定を保存"""
        try:
            if self.window and self.window.winfo_exists():
                # 現在のウィンドウのサイズと位置を取得
                geometry = self.window.geometry()
                
                # 統合された設定ファイルに保存
                unified_settings = {}
                if os.path.exists(self.settings_file):
                    try:
                        with open(self.settings_file, 'r', encoding='utf-8') as f:
                            unified_settings = json.load(f)
                    except:
                        unified_settings = {}
                
                # トーレントマネージャーの設定を取得または作成
                if 'torrent_manager' not in unified_settings:
                    unified_settings['torrent_manager'] = {}
                
                unified_settings['torrent_manager']['window_geometry'] = geometry
                
                # ウィンドウの状態も保存
                try:
                    state = self.window.state()
                    unified_settings['torrent_manager']['window_state'] = state
                except:
                    unified_settings['torrent_manager']['window_state'] = "normal"
                
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(unified_settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"ウィンドウ設定保存エラー: {e}")
    
    def _uncheck_successful_downloads(self):
        """DLに成功したファイルの検索結果パーサーのチェックを外す"""
        try:
            # パーサーインスタンスを取得（現在のパーサーインスタンスを使用）
            # TorrentDownloadManagerはパーサーから呼び出されるため、self.parentがパーサーインスタンス
            parser = self.parent
            
            # パーサーがSearchResultParserのインスタンスかチェック
            if not hasattr(parser, 'tree') or not hasattr(parser, 'checked_items'):
                self._log("検索結果パーサーが正しく初期化されていません")
                return
            
            # パーサーウィンドウが存在するかチェック
            try:
                parser.root.winfo_exists()
            except tk.TclError:
                self._log("検索結果パーサーのウィンドウが存在しません")
                return
            
            # DLに成功したギャラリーIDのリストを作成
            successful_gallery_ids = []
            
            # DLに成功したギャラリーを取得（複数のステータスをチェック）
            for i, torrent_data in enumerate(self.torrent_data):
                status = torrent_data.get('status', '')
                self._log(f"URL{i+1} ステータス: '{status}'")
                
                # 'succeeded', 'completed', 'success' など複数の成功ステータスをチェック
                if status in ['succeeded', 'completed', 'success']:
                    gallery_id = torrent_data.get('gallery_id', '')
                    self._log(f"URL{i+1} ギャラリーID: '{gallery_id}'")
                    if gallery_id and gallery_id != 'Unknown':
                        successful_gallery_ids.append(gallery_id)
                        self._log(f"URL{i+1} 成功ギャラリーID追加: {gallery_id}")
                    else:
                        self._log(f"URL{i+1} ギャラリーIDが無効: '{gallery_id}'")
            
            if not successful_gallery_ids:
                self._log("DLに成功したファイルがありません")
                return
            
            # パーサーのチェックを外す（ギャラリーIDベースでマッチング）
            unchecked_count = 0
            self._log(f"パーサーの全アイテム数: {len(parser.tree.get_children())}")
            self._log(f"パーサーのチェック済みアイテム数: {len(parser.checked_items)}")
            
            for item_id in parser.tree.get_children():
                values = parser.tree.item(item_id, 'values')
                if len(values) >= 10:
                    url = values[9]
                    # URLからギャラリーIDを抽出
                    gallery_id = self._extract_gallery_id_from_url(url)
                    
                    # デバッグログを追加
                    self._log(f"パーサーアイテム {item_id}: URL={url}, ギャラリーID={gallery_id}")
                    self._log(f"成功ギャラリーID一覧: {list(successful_gallery_ids)}")
                    
                    if gallery_id in successful_gallery_ids:
                        # TreeViewのSelect列の状態を確認
                        current_value = parser.tree.set(item_id, "Select")
                        self._log(f"マッチング成功: ギャラリーID={gallery_id}, チェック状態='{current_value}'")
                        
                        if current_value == "✓":  # チェックされている場合
                            # チェックを外す
                            parser.tree.set(item_id, "Select", "")
                            parser.tree.item(item_id, tags=())
                            parser.checked_items.discard(item_id)
                            unchecked_count += 1
                            self._log(f"チェックを外しました: ギャラリーID={gallery_id}")
                        else:
                            self._log(f"既にチェックが外されています: ギャラリーID={gallery_id}")
                    else:
                        self._log(f"マッチング失敗: ギャラリーID={gallery_id} は成功リストにありません")
            
            self._log(f"検索結果パーサーから{unchecked_count}個のチェックを外しました")
            
        except Exception as e:
            self._log(f"チェック外しエラー: {e}")
    
    def _extract_gallery_id_from_url(self, url):
        """URLからギャラリーIDを抽出"""
        try:
            import re
            # e-hentai.org/g/数字/文字列/ の形式からギャラリーIDを抽出
            match = re.search(r'/g/(\d+)/', url)
            if match:
                return int(match.group(1))  # 文字列を整数に変換
            return None
        except Exception as e:
            self._log(f"ギャラリーID抽出エラー: {e}")
            return None
    
    def _download_single_torrent_simple(self, torrent, index, file_num, total_files):
        """単一のTorrentファイルをダウンロード（シンプル版）"""
        try:
            # Torrentファイルをダウンロード（安全な処理）
            torrent_content = self._safe_download_torrent(torrent['torrent_url'], timeout=30)
            if torrent_content is None:
                self._log(f"URL{index+1}: ファイル{file_num}のTorrentダウンロードに失敗")
                return False
            
            # ファイル名を安全に生成
            filename = torrent.get('filename', f'torrent_{file_num}.torrent')
            
            # 拡張子を確実に保持
            if not filename.endswith('.torrent'):
                filename += '.torrent'
            
            # ファイル名の安全化
            filename = self._sanitize_filename(filename)
            
            if total_files > 1:
                # 複数ファイルの場合は番号を付ける
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{file_num}{ext}"
            
            # ファイルを保存（安全な処理）
            save_path = os.path.join(self.torrent_save_directory, filename)
            
            # ダウンロード内容の検証
            if not torrent_content or len(torrent_content) == 0:
                self._log(f"URL{index+1}: ファイル{file_num}のダウンロード内容が空です")
                return False
            
            # Torrentファイルの基本検証
            if not torrent_content.startswith(b'd') and not torrent_content.startswith(b'l'):
                self._log(f"URL{index+1}: ファイル{file_num}の無効なTorrentファイル形式です")
                return False
            
            # 一時ファイルに保存してから移動
            temp_path = save_path + ".tmp"
            with open(temp_path, 'wb') as f:
                f.write(torrent_content)
            
            # ファイルサイズの検証
            if os.path.getsize(temp_path) != len(torrent_content):
                self._log(f"URL{index+1}: ファイル{file_num}のファイルサイズが一致しません")
                os.remove(temp_path)
                return False
            
            # ファイル移動
            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(temp_path, save_path)
            
            # 最終検証
            if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                self._log(f"URL{index+1}: ファイル{file_num}の保存に失敗しました")
                return False
            
            self._log(f"URL{index+1}: ファイル{file_num} - {filename} をダウンロード完了 ({len(torrent_content)} bytes)")
            return True
            
        except Exception as e:
            self._log(f"URL{index+1}: ファイル{file_num}のDLエラー: {e}")
            return False
    
    def _sanitize_filename(self, filename):
        """ファイル名を安全化"""
        import re
        import unicodedata
        
        # Unicode正規化
        filename = unicodedata.normalize('NFC', filename)
        
        # 危険な文字を除去
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # 制御文字を除去
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '_', filename)
        
        # 先頭・末尾の空白とドットを除去
        filename = filename.strip(' .')
        
        # 空の場合はデフォルト名を使用
        if not filename:
            filename = "unknown"
        
        # 長すぎる場合は短縮
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:190] + ext
        
        # Windows予約名を回避
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
        name_without_ext = os.path.splitext(filename)[0].upper()
        if name_without_ext in reserved_names:
            filename = f"_{filename}"
        
        return filename
    
    def _extract_filename_from_url(self, url):
        """URLからファイル名を抽出"""
        try:
            # URLの最後の部分からファイル名を抽出
            filename = url.split('/')[-1]
            # クエリパラメータを除去
            if '?' in filename:
                filename = filename.split('?')[0]
            # デコード
            import urllib.parse
            filename = urllib.parse.unquote(filename)
            return filename
        except Exception as e:
            self._log(f"ファイル名抽出エラー: {e}")
            return "unknown.torrent"
    
    def _download_with_normal_method(self, data, index, response):
        """通常のDLメソッド（Content Warning承諾後用）"""
        try:
            # 待機
            time.sleep(self.page_wait_time)
            
            # 共通のTorrent処理を実行
            return self._process_torrent_download(data, index, response)
            
        except Exception as e:
            self._log(f"URL{index+1} Download error: {e}")
            return False
    
    def _process_torrent_download(self, data, index, response):
        """共通のTorrent処理（通常処理とContent Warning承諾後処理で共有）"""
        try:
            # Torrentページのリンクを検索
            torrent_links = self._find_torrent_links(response.text)
            
            # Content Warning承諾後の場合、ギャラリーIDとトークンから直接URLを構築
            if not torrent_links:
                self._log(f"URL{index+1}: ギャラリーページにTorrentリンクが含まれていません")
                # ページ内容の一部をログに出力（デバッグ用）
                page_preview = response.text[:1000] if len(response.text) > 1000 else response.text
                self._log(f"URL{index+1}: ページ内容プレビュー: {page_preview}")
                
                # Content Warning承諾後の場合、URLから直接TorrentページURLを構築
                torrent_url = self._construct_torrent_url_from_gallery_url(data['source_url'])
                if torrent_url:
                    self._log(f"URL{index+1}: Content Warning承諾後のため、直接TorrentページURLを構築: {torrent_url}")
                    torrent_links = [torrent_url]
                else:
                    self._log(f"URL{index+1}: TorrentページURLの構築に失敗")
                    return False
            
            if not torrent_links:
                self._log(f"URL{index+1}: Torrentリンクが見つかりません")
                return False
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # Torrentページにアクセス
            torrent_page_url = torrent_links[0].replace("&amp;", "&")
            torrent_response = requests.get(torrent_page_url, timeout=30)
            torrent_response.raise_for_status()
            
            # 復帰ポイント更新（Torrentページ移動後）
            self._update_resume_point(index, 'torrent_page_loaded')
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # Torrent情報を抽出
            torrent_candidates = self._extract_torrent_info(torrent_response.text)
            if not torrent_candidates:
                self._log(f"URL{index+1}: Torrent候補が見つかりません")
                return False
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # 候補から選択
            selected_torrent = self._select_torrent_candidate(torrent_candidates)
            if not selected_torrent:
                self._log(f"URL{index+1}: Torrent候補の選択に失敗")
                return False
            
            # フィルタリング処理
            action_display = {
                "max_only": "最大容量のものだけDL",
                "max_and_selected": "最大容量のファイルと選択したファイルを両方DL", 
                "all_above": "容量以上のファイルを全てDL"
            }.get(self.filtering_action, self.filtering_action)
            if self.filtering_enabled:
                filtered_torrents = self._filter_torrents_by_size(torrent_candidates, self.filtering_size, self.filtering_action)
                self._log(f"URL{index+1}: フィルタリング結果 - 候補数={len(torrent_candidates)}, フィルタ後={len(filtered_torrents)}")
                if not filtered_torrents:
                    self._log(f"URL{index+1}: フィルタリング条件に合致するTorrentがありません")
                    self._update_url_status(index, "inappropriate")
                    return "inappropriate"  # フィルタリングによる不適として処理
                # フィルタリング後の候補を処理
                if len(filtered_torrents) == 1:
                    # 1つの場合は通常の選択処理
                    selected_torrent = filtered_torrents[0]
                elif (self.filtering_action == "all_above" or self.filtering_action == "max_and_selected") and len(filtered_torrents) > 1:
                    # 複数ファイルを順次DL（all_aboveの場合のみ）
                    self._log(f"URL{index+1}: 複数ファイル({len(filtered_torrents)}個)を順次DL開始")
                    success_count = 0
                    for i, torrent in enumerate(filtered_torrents):
                        self._log(f"URL{index+1}: ファイル{i+1}/{len(filtered_torrents)}をDL中")
                        result = self._download_single_torrent_simple(torrent, index, i+1, len(filtered_torrents))
                        if result:
                            success_count += 1
                        else:
                            self._log(f"URL{index+1}: ファイル{i+1}のDLに失敗")
                    
                    if success_count > 0:
                        self._log(f"URL{index+1}: {success_count}/{len(filtered_torrents)}個のファイルをDL完了")
                        return "succeeded"
                    else:
                        self._log(f"URL{index+1}: 全てのファイルのDLに失敗")
                        return False
                else:
                    # その他の場合は最初の1つを選択
                    selected_torrent = filtered_torrents[0]
                    self._log(f"URL{index+1}: 複数候補({len(filtered_torrents)}個)から最初の1つを選択")
                
                if not selected_torrent:
                    self._log(f"URL{index+1}: フィルタリング後のTorrent候補の選択に失敗")
                    self._update_url_status(index, "inappropriate")
                    return "inappropriate"  # フィルタリングによる不適として処理
            
            # 復帰ポイント更新（Torrent選択後）
            self._update_resume_point(index, 'torrent_selected')
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # Torrentファイルをダウンロード（安全な処理）
            torrent_content = self._safe_download_torrent(selected_torrent['torrent_url'], timeout=30)
            if torrent_content is None:
                self._log(f"URL{index+1}: Torrentファイルのダウンロードに失敗しました")
                return False
            
            # 復帰ポイント更新（ダウンロード前）
            self._update_resume_point(index, 'download_ready')
            
            # 中断フラグチェック
            if self.stop_flag.is_set() or self.pause_event.is_set():
                return False
            
            # ファイルを保存（安全な処理）
            filename = selected_torrent['filename']
            if not filename.endswith('.torrent'):
                filename += '.torrent'
            
            # ファイル名を安全化
            filename = self._sanitize_filename(filename)
            
            # 保存ディレクトリが存在しない場合は作成
            if not os.path.exists(self.torrent_save_directory):
                try:
                    os.makedirs(self.torrent_save_directory, exist_ok=True)
                    self._log(f"保存ディレクトリを作成しました: {self.torrent_save_directory}")
                except Exception as e:
                    self._log(f"保存ディレクトリ作成エラー: {e}")
                    return False
            
            filepath = os.path.join(self.torrent_save_directory, filename)
            
            # 同名ファイル処理
            final_filepath = self._handle_duplicate_torrent_file(filepath)
            if final_filepath is None:  # スキップの場合
                self._log(f"URL{index+1}: 同名ファイルのためスキップしました")
                return True  # スキップは成功として扱う
            
            # 安全なファイル保存
            try:
                # ダウンロード内容の検証
                if not torrent_content or len(torrent_content) == 0:
                    self._log(f"URL{index+1}: ダウンロード内容が空です")
                    return False
                
                # Torrentファイルの基本検証（Bencode形式の確認）
                if not torrent_content.startswith(b'd') and not torrent_content.startswith(b'l'):
                    self._log(f"URL{index+1}: 無効なTorrentファイル形式です")
                    return False
                
                # 一時ファイルに保存してから移動（アトミック操作）
                temp_filepath = final_filepath + ".tmp"
                with open(temp_filepath, 'wb') as f:
                    f.write(torrent_content)
                
                # ファイルサイズの検証
                if os.path.getsize(temp_filepath) != len(torrent_content):
                    self._log(f"URL{index+1}: ファイルサイズが一致しません")
                    os.remove(temp_filepath)
                    return False
                
                # ファイル移動（アトミック操作）
                if os.path.exists(final_filepath):
                    os.remove(final_filepath)
                os.rename(temp_filepath, final_filepath)
                
                # 最終検証
                if not os.path.exists(final_filepath) or os.path.getsize(final_filepath) == 0:
                    self._log(f"URL{index+1}: ファイル保存に失敗しました")
                    return False
                
                self._log(f"URL{index+1}: {os.path.basename(final_filepath)} をダウンロード完了 ({len(torrent_content)} bytes)")
                return True
                
            except Exception as e:
                # 一時ファイルのクリーンアップ
                if 'temp_filepath' in locals() and os.path.exists(temp_filepath):
                    try:
                        os.remove(temp_filepath)
                    except:
                        pass
                self._log(f"URL{index+1}: ファイル保存エラー: {e}")
                return False
            
            # 復帰ポイント更新（ダウンロード完了後）
            self._update_resume_point(index, 'download_completed')
            
        except Exception as e:
            self._log(f"URL{index+1} Torrent processing error: {str(e)}")
            return False
    
    def _construct_torrent_url_from_gallery_url(self, gallery_url):
        """ギャラリーURLからTorrentページURLを構築"""
        try:
            # ギャラリーURLの形式: https://e-hentai.org/g/3592504/77c9aad506/
            # TorrentページURLの形式: https://e-hentai.org/gallerytorrents.php?gid=3592504&t=77c9aad506
            
            import re
            pattern = r'https://e-hentai\.org/g/(\d+)/([0-9a-f]+)/?'
            match = re.match(pattern, gallery_url)
            
            if match:
                gid = match.group(1)
                token = match.group(2)
                torrent_url = f"https://e-hentai.org/gallerytorrents.php?gid={gid}&t={token}"
                return torrent_url
            else:
                self._log(f"ギャラリーURLの解析に失敗: {gallery_url}")
                return None
                
        except Exception as e:
            self._log(f"TorrentページURL構築エラー: {e}")
            return None
    
    def _save_settings(self):
        """設定を保存（無効化）"""
        # メインウィンドウ経由で保存されるため、ここでは何もしない
        pass
    
    def _load_settings(self):
        """設定を読み込み"""
        try:
            # デフォルト値を内部値に設定
            self.torrent_save_directory = self._default_torrent_save_directory
            self.page_wait_time = self._default_page_wait_time
            self.error_handling = self._default_error_handling
            self.torrent_selection = self._default_torrent_selection
            self.duplicate_file_mode = self._default_duplicate_file_mode
            self.filtering_enabled = self._default_filtering_enabled
            self.filtering_size = self._default_filtering_size
            self.filtering_action = self._default_filtering_action
            
            settings = {}
            
            # ⭐修正: parentから設定を取得（優先）⭐
            if self.parent and hasattr(self.parent, 'torrent_manager_settings') and self.parent.torrent_manager_settings:
                settings = self.parent.torrent_manager_settings.copy()
                self._log("[DEBUG] parentからTorrentマネージャー設定を取得しました")
            elif os.path.exists(self.settings_file):
                # ⭐修正: ehd_settings.jsonから直接読み込み⭐
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    unified_settings = json.load(f)
                
                # 統合された設定からトーレントマネージャーの設定を取得
                settings = unified_settings.get('torrent_manager', {})
                self._log("[DEBUG] ehd_settings.jsonからTorrentマネージャー設定を読み込みました")
                
            if settings:
                # 設定を内部値に適用
                self.torrent_save_directory = settings.get("save_directory", self._default_torrent_save_directory)
                self.page_wait_time = settings.get("page_wait_time", self._default_page_wait_time)
                self.error_handling = settings.get("error_handling", self._default_error_handling)
                self.torrent_selection = settings.get("torrent_selection", self._default_torrent_selection)
                self.duplicate_file_mode = settings.get("duplicate_file_mode", self._default_duplicate_file_mode)
                self.filtering_enabled = settings.get("filtering_enabled", self._default_filtering_enabled)
                self.filtering_size = settings.get("filtering_size", self._default_filtering_size)
                self.filtering_action = settings.get("filtering_action", self._default_filtering_action)
                
                # ウィンドウの状態を復元
                if "window_geometry" in settings and settings["window_geometry"]:
                    self.window_geometry = settings["window_geometry"]
                if "window_state" in settings and settings["window_state"]:
                    self.window_state = settings["window_state"]
                else:
                    self.window_state = settings.get("window_state", "normal")
            
            # GUI変数が存在する場合は同期
            if hasattr(self, 'torrent_save_dir_var') and self.torrent_save_dir_var:
                self._sync_internal_to_gui()
                
        except Exception as e:
            self._log(f"設定読み込みエラー: {e}")
            # エラー時はデフォルト値を使用
            self.torrent_save_directory = self._default_torrent_save_directory
            self.page_wait_time = self._default_page_wait_time
            self.error_handling = self._default_error_handling
            self.torrent_selection = self._default_torrent_selection
            self.duplicate_file_mode = self._default_duplicate_file_mode
            self.filtering_enabled = self._default_filtering_enabled
            self.filtering_size = self._default_filtering_size
            self.filtering_action = self._default_filtering_action
