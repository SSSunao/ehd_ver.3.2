# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox, Spinbox, filedialog
import json
import tkinter.font as tkFont
import requests
import threading
import time
import re
import traceback
import webbrowser
import io
from PIL import Image, ImageTk
from queue import Queue, Empty
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import os
from datetime import datetime
import ssl
from config.settings import ToolTip

class SearchResultParser:

    def __init__(self, root, parent=None):
        self.root = root
        self.parent = parent  # 親ウィンドウへの参照（オプション）
        # ウィンドウのタイトルとサイズは親ウィンドウ側で設定される

        # URL出力関連の変数
        self.output_urls = None  # URLを出力するためのコールバック関数
        self._has_output_urls = False  # URLが出力されたかどうかを追跡

        # --- Threading Control ---
        self.stop_event = threading.Event()
        self.parsing_thread = None
        self.thumbnail_download_thread = None
        self.thumbnail_queue = Queue()
        self.thumbnail_cache = {}
        self.thumbnail_cache_order = []  # キャッシュの順序を保持
        self.stop_thumbnail_downloader = threading.Event()
        self.is_parsing = False  # 解析中フラグを追加
        self.current_thread_target = 0  # 現在のスレッドの目標数を保持

        # スキップカウントの初期化
        self.skip_count_var = tk.IntVar(value=0)

        # URL出力関連の変数
        self.output_urls = None  # URLを出力するためのコールバック関数
        self._has_output_urls = False  # URLが出力されたかどうかを追跡

        self.thumbnail_popup = None
        self.thumbnail_image = None
        
        # --- Selection Management ---
        self.checked_items = set()  # チェックボックス状態の保存用
        self.hidden_items = set()  # 非表示アイテムの保存用
        self.checkboxes = []  # チェックボックスウィジェットのリスト
        self.checkbox_vars = []  # チェックボックス変数のリスト

        # --- URL Open Management ---
        self.url_open_message_shown = False  # URLを開く際のメッセージ表示フラグ

        # --- Logging Setup ---
        log_frame = ttk.Frame(self.root, padding="5")
        log_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0))
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, bg="lightgrey")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.log("アプリケーションを初期化しました。")

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="準備完了")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, before=log_frame)

        # --- Last URL Frame ---
        last_url_frame = ttk.Frame(self.root, padding="5")
        last_url_frame.pack(fill=tk.X, side=tk.BOTTOM, before=log_frame)

        # フィルター関連の初期化
        self.filter_conditions = {}
        self.total_pages_var = tk.StringVar(value="取得ページ総数: 0")
        self.selected_pages_var = tk.StringVar(value="選択: 0/0")
        
        ttk.Label(last_url_frame, text="最後の探索URL:").pack(side=tk.LEFT)
        self.last_url_var = tk.StringVar()
        self.last_url_entry = ttk.Entry(last_url_frame, textvariable=self.last_url_var, width=70, state="readonly")
        self.last_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.continue_button = ttk.Button(last_url_frame, text="続きから解析", 
                                        command=self.continue_from_last_url, state=tk.DISABLED)
        self.continue_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.continue_button, "前回の解析を続行します。中断された解析から再開できます。")

        # --- Requests Session with SSL Configuration ---
        self.session = requests.Session()
        # SSL設定を緩和してE-Hentaiとの互換性を確保
        self.session.mount('https://', requests.adapters.HTTPAdapter())
        
        # SSL Context設定
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
            'Referer': 'https://e-hentai.org/'
        })
        self.session.cookies.set('nw', '1', domain='.e-hentai.org')
        self.session.cookies.set('nw', '1', domain='.exhentai.org')
        self.session.cookies.set('sl', 'dm_2', domain='.e-hentai.org') # Ensure Extended list mode

        # --- Data Storage ---
        self.gallery_data = []
        self.processed_urls = set()  # URLの重複チェック用（後方互換性）
        self.processed_galleries = set()  # ID+トークンによる重複チェック用
        self.last_gallery_id = None  # 最後に処理したギャラリーのID
        self.last_gallery_token = None  # 最後に処理したギャラリーのトークン

        # フィルタリング状態の管理を改善
        self.filter_states = {}  # 各行のフィルタリング状態を管理
        self.filter_history = []  # フィルター適用履歴

        self.create_gui()
        self.start_thumbnail_downloader()
        self.disable_filter_area()  # 初期状態でフィルターエリアを無効化

        # ウィンドウクローズハンドラは親ウィンドウ側で設定される
        # self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # ウィンドウサイズ・位置変更の監視
        self.root.bind("<Configure>", self._on_window_configure)
        
        # 設定読み込み
        self._load_parser_settings()

    def create_tooltip(self, widget, text):
        """ツールチップを作成"""
        tooltip = ToolTip(widget, text)
        return tooltip

    def _on_closing(self):
        """Handle window close event."""
        self.log("アプリケーション終了処理...")
        
        # 設定を保存
        self._save_parser_settings()
        
        self.stop_event.set()
        self.stop_thumbnail_downloader.set()
        self.thumbnail_queue.put(None)

        # キャッシュクリア
        self.thumbnail_cache.clear()
        self.thumbnail_cache_order.clear()

        if self.parsing_thread and self.parsing_thread.is_alive():
            self.parsing_thread.join(timeout=0.5)
        if self.thumbnail_download_thread and self.thumbnail_download_thread.is_alive():
            self.thumbnail_download_thread.join(timeout=0.5)

        self.root.destroy()

    def _save_parser_settings(self):
        """パーサー設定を保存（無効化）"""
        # メインウィンドウ経由で保存されるため、ここでは何もしない
        pass
    
    def _collect_parser_settings(self):
        """パーサー設定を収集して返す（メインウィンドウから呼ばれる）"""
        try:
            settings = {}
            
            # ウィンドウの状態
            try:
                settings["window_geometry"] = self.root.geometry()
            except:
                settings["window_geometry"] = "800x600+200+200"
            
            try:
                settings["window_state"] = self.root.state()
            except:
                settings["window_state"] = "normal"
            
            # 検索URL
            if hasattr(self, 'search_url_var') and self.search_url_var:
                settings["search_url"] = self.search_url_var.get()
            
            # 取得数
            if hasattr(self, 'target_count_var') and self.target_count_var:
                settings["target_count"] = self.target_count_var.get()
            
            # ページ待機時間
            if hasattr(self, 'page_wait_time_var') and self.page_wait_time_var:
                settings["page_wait_time"] = self.page_wait_time_var.get()
            
            # サムネイル自動取得
            if hasattr(self, 'auto_thumb_var') and self.auto_thumb_var:
                settings["auto_thumb"] = self.auto_thumb_var.get()
            
            # サムネイル待機時間
            if hasattr(self, 'thumb_wait_time_var') and self.thumb_wait_time_var:
                settings["thumb_wait_time"] = self.thumb_wait_time_var.get()
            
            # キャッシュサイズ
            if hasattr(self, 'cache_size_var') and self.cache_size_var:
                settings["cache_size"] = self.cache_size_var.get()
            
            # サムネイル無効化
            if hasattr(self, 'disable_thumb_var') and self.disable_thumb_var:
                settings["disable_thumb"] = self.disable_thumb_var.get()
            
            # 解析モード
            if hasattr(self, 'parse_mode_var') and self.parse_mode_var:
                settings["parse_mode"] = self.parse_mode_var.get()
            
            # フィルタ条件
            if hasattr(self, 'filter_conditions'):
                settings["filter_conditions"] = dict(self.filter_conditions)
            
            # スキップ数
            if hasattr(self, 'skip_count_var') and self.skip_count_var:
                settings["skip_count"] = self.skip_count_var.get()
            
            # チェックボックス状態は保存しない（常に空で開始）
            # if hasattr(self, 'checked_items'):
            #     settings["checked_items"] = list(self.checked_items)
            
            # 非表示アイテム
            if hasattr(self, 'hidden_items'):
                settings["hidden_items"] = list(self.hidden_items)
            
            # フィルタリング設定
            if hasattr(self, 'filter_enabled_var') and self.filter_enabled_var:
                settings["filter_enabled"] = self.filter_enabled_var.get()
            
            if hasattr(self, 'filter_artist_var') and self.filter_artist_var:
                settings["filter_artist"] = self.filter_artist_var.get()
            
            if hasattr(self, 'filter_parody_var') and self.filter_parody_var:
                settings["filter_parody"] = self.filter_parody_var.get()
            
            if hasattr(self, 'filter_character_var') and self.filter_character_var:
                settings["filter_character"] = self.filter_character_var.get()
            
            if hasattr(self, 'filter_group_var') and self.filter_group_var:
                settings["filter_group"] = self.filter_group_var.get()
            
            if hasattr(self, 'filter_language_var') and self.filter_language_var:
                settings["filter_language"] = self.filter_language_var.get()
            
            if hasattr(self, 'filter_category_var') and self.filter_category_var:
                settings["filter_category"] = self.filter_category_var.get()
            
            return settings
            
        except Exception as e:
            self.log(f"パーサー設定収集エラー: {e}")
            return {}

    def _load_parser_settings(self):
        """パーサー設定を読み込み"""
        try:
            settings = {}

            # ⭐優先: parent から設定を取得
            if self.parent and hasattr(self.parent, 'parser_settings') and self.parent.parser_settings:
                settings = self.parent.parser_settings.copy()
                self.log("[DEBUG] parentからパーサー設定を取得しました")

            else:
                # ⭐次: ehd_settings.json
                if os.path.exists("ehd_settings.json"):
                    with open("ehd_settings.json", 'r', encoding='utf-8') as f:
                        unified_settings = json.load(f)
                    settings = unified_settings.get('parser', {})
                    self.log("[DEBUG] ehd_settings.jsonからパーサー設定を読み込みました")

                # ⭐フォールバック: unified_settings.json
                elif os.path.exists("unified_settings.json"):
                    with open("unified_settings.json", 'r', encoding='utf-8') as f:
                        unified_settings = json.load(f)
                    settings = unified_settings.get('parser', {})
                    self.log("[DEBUG] unified_settings.jsonからパーサー設定を読み込みました")

                # ⭐最終フォールバック: parser_settings.json（古い）
                elif os.path.exists("parser_settings.json"):
                    with open("parser_settings.json", 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                    self.log("[DEBUG] parser_settings.jsonからパーサー設定を読み込みました")

            # --- ウィンドウ状態の復元 ---
            if "window_geometry" in settings and settings["window_geometry"] != "1x1+0+0":
                self.root.geometry(settings["window_geometry"])
                self.log(f"[DEBUG] ウィンドウサイズ・位置復元: {settings['window_geometry']}")

            if "window_state" in settings:
                self.root.state(settings["window_state"])
                self.log(f"[DEBUG] ウィンドウ状態復元: {settings['window_state']}")

            # GUI 要素構築後に適用
            self.root.after(100, lambda: self._apply_loaded_settings(settings))

            self.log("パーサー設定を読み込みました")

        except Exception as e:
            self.log(f"設定読み込みエラー: {e}")

    def _on_window_configure(self, event):
        """ウィンドウサイズ・位置変更時の処理"""
        try:
            # ウィンドウ自体のサイズ変更のみを対象とする
            if event.widget == self.root:
                # デバウンス処理（連続する変更を抑制）
                if hasattr(self, '_configure_timer'):
                    self.root.after_cancel(self._configure_timer)
                
                self._configure_timer = self.root.after(1000, self._save_parser_settings)
        except Exception as e:
            self.log(f"ウィンドウ設定変更処理エラー: {e}")

    def _apply_loaded_settings(self, settings):
        """読み込んだ設定をGUIに適用"""
        try:
            self.log("[DEBUG] パーサー設定をGUIに適用中...")
            
            # 検索URL
            if "search_url" in settings and hasattr(self, 'search_url_var'):
                self.search_url_var.set(settings["search_url"])
                self.log(f"[DEBUG] 検索URL復元: {settings['search_url']}")
            elif "search_url" in settings:
                # search_url_varが存在しない場合は作成
                self.search_url_var = tk.StringVar(value=settings["search_url"])
                self.url_entry.config(textvariable=self.search_url_var)
                self.log(f"[DEBUG] 検索URL復元（新規作成）: {settings['search_url']}")
            
            # 取得数
            if "target_count" in settings and hasattr(self, 'target_count_var'):
                self.target_count_var.set(settings["target_count"])
                self.log(f"[DEBUG] 取得数復元: {settings['target_count']}")
            
            # ページ待機時間
            if "page_wait_time" in settings and hasattr(self, 'page_wait_time_var'):
                self.page_wait_time_var.set(settings["page_wait_time"])
                self.log(f"[DEBUG] ページ待機時間復元: {settings['page_wait_time']}")
            
            # サムネイル自動取得
            if "auto_thumb" in settings and hasattr(self, 'auto_thumb_var'):
                self.auto_thumb_var.set(settings["auto_thumb"])
                self.log(f"[DEBUG] サムネイル自動取得復元: {settings['auto_thumb']}")
            
            # サムネイル待機時間
            if "thumb_wait_time" in settings and hasattr(self, 'thumb_wait_time_var'):
                self.thumb_wait_time_var.set(settings["thumb_wait_time"])
                self.log(f"[DEBUG] サムネイル待機時間復元: {settings['thumb_wait_time']}")
            
            # キャッシュサイズ
            if "cache_size" in settings and hasattr(self, 'cache_size_var'):
                self.cache_size_var.set(settings["cache_size"])
                self.log(f"[DEBUG] キャッシュサイズ復元: {settings['cache_size']}")
            
            # サムネイル無効化
            if "disable_thumb" in settings and hasattr(self, 'disable_thumb_var'):
                self.disable_thumb_var.set(settings["disable_thumb"])
                self.log(f"[DEBUG] サムネイル無効化復元: {settings['disable_thumb']}")
            
            # 解析モード
            if "parse_mode" in settings and hasattr(self, 'parse_mode_var'):
                self.parse_mode_var.set(settings["parse_mode"])
                self.log(f"[DEBUG] 解析モード復元: {settings['parse_mode']}")
            
            # フィルタ条件
            if "filter_conditions" in settings and hasattr(self, 'filter_conditions'):
                self.filter_conditions.update(settings["filter_conditions"])
                self.log(f"[DEBUG] フィルタ条件復元: {settings['filter_conditions']}")
            
            # スキップ数
            if "skip_count" in settings and hasattr(self, 'skip_count_var'):
                self.skip_count_var.set(settings["skip_count"])
                self.log(f"[DEBUG] スキップ数復元: {settings['skip_count']}")
            
            # 設定適用後にGUI要素の状態を更新
            if hasattr(self, 'on_auto_thumb_changed'):
                self.on_auto_thumb_changed()
            if hasattr(self, 'on_disable_thumb_changed'):
                self.on_disable_thumb_changed()
            
            # 追加設定の復元
            # チェックボックス状態は復元しない（常に空で開始）
            # if "checked_items" in settings and hasattr(self, 'checked_items'):
            #     self.checked_items = set(settings["checked_items"])
            #     self.log(f"[DEBUG] チェックボックス状態復元: {len(self.checked_items)}個")
            
            if "hidden_items" in settings and hasattr(self, 'hidden_items'):
                self.hidden_items = set(settings["hidden_items"])
                self.log(f"[DEBUG] 非表示アイテム復元: {len(self.hidden_items)}個")
            
            # フィルタリング設定
            if "filter_enabled" in settings and hasattr(self, 'filter_enabled_var'):
                self.filter_enabled_var.set(settings["filter_enabled"])
                self.log(f"[DEBUG] フィルタリング有効復元: {settings['filter_enabled']}")
            
            if "filter_artist" in settings and hasattr(self, 'filter_artist_var'):
                self.filter_artist_var.set(settings["filter_artist"])
                self.log(f"[DEBUG] アーティストフィルター復元: {settings['filter_artist']}")
            
            if "filter_parody" in settings and hasattr(self, 'filter_parody_var'):
                self.filter_parody_var.set(settings["filter_parody"])
                self.log(f"[DEBUG] パロディフィルター復元: {settings['filter_parody']}")
            
            if "filter_character" in settings and hasattr(self, 'filter_character_var'):
                self.filter_character_var.set(settings["filter_character"])
                self.log(f"[DEBUG] キャラクターフィルター復元: {settings['filter_character']}")
            
            if "filter_group" in settings and hasattr(self, 'filter_group_var'):
                self.filter_group_var.set(settings["filter_group"])
                self.log(f"[DEBUG] グループフィルター復元: {settings['filter_group']}")
            
            if "filter_language" in settings and hasattr(self, 'filter_language_var'):
                self.filter_language_var.set(settings["filter_language"])
                self.log(f"[DEBUG] 言語フィルター復元: {settings['filter_language']}")
            
            if "filter_category" in settings and hasattr(self, 'filter_category_var'):
                self.filter_category_var.set(settings["filter_category"])
                self.log(f"[DEBUG] カテゴリーフィルター復元: {settings['filter_category']}")
            
            self.log("[DEBUG] パーサー設定のGUI適用完了")
                
        except Exception as e:
            self.log(f"設定適用エラー: {e}")

    def log(self, message):
        """Append message to the log area"""
        if not hasattr(self, 'log_text') or not self.log_text.winfo_exists():
             print(f"Log (GUI Error): {message}")
             return
        try:
            self.root.after(0, self._log_to_widget, message)
        except Exception as e:
            print(f"Log scheduling error: {e}")

    def _log_to_widget(self, message):
        """Actual writing to the Text widget (runs in GUI thread)"""
        try:
            if not self.log_text.winfo_exists(): return
            current_time = time.strftime('%H:%M:%S')
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{current_time} - {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception as e:
            current_time = time.strftime('%H:%M:%S')
            print(f"{current_time} - Log Widget Error: {e} | Original Msg: {message}")

    def create_gui(self):
        # --- Top Frame ---
        top_frame = ttk.Frame(self.root, padding="5")
        top_frame.pack(fill=tk.X, side=tk.TOP)

        # Row 1: URL, Skip Count, Target, Page Wait
        row1_frame = ttk.Frame(top_frame)
        row1_frame.pack(fill=tk.X, pady=(0, 5))
        search_url_label = ttk.Label(row1_frame, text="検索結果URL:")
        search_url_label.pack(side=tk.LEFT, padx=(0, 5))
        self.create_tooltip(search_url_label, "E-Hentaiの検索結果ページのURLを入力します。検索条件を設定した後、このURLをコピーして使用してください。")
        
        self.url_entry = ttk.Entry(row1_frame, width=55)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.url_entry.insert(0, "https://e-hentai.org/?")
        self.create_tooltip(self.url_entry, "E-Hentaiの検索結果ページのURLを入力します。検索条件を設定した後、このURLをコピーして使用してください。")
        
        # 検索URL用のStringVarを作成（設定保存・読み込み用）
        self.search_url_var = tk.StringVar(value="https://e-hentai.org/?")
        self.url_entry.config(textvariable=self.search_url_var)
        
        # リンクを開くボタン
        self.open_url_button = ttk.Button(row1_frame, text="リンクを開く", command=self.open_current_url)
        self.open_url_button.pack(side=tk.LEFT, padx=(0, 5))
        self.create_tooltip(self.open_url_button, "現在入力されているURLをブラウザで開きます。")
        
        # ギャラリーの取得数
        target_label = ttk.Label(row1_frame, text="ギャラリーの取得数:")
        target_label.pack(side=tk.LEFT, padx=(5, 0))
        self.create_tooltip(target_label, "取得するギャラリーの数を指定します")
        self.target_count_var = tk.IntVar(value=25)
        self.target_count_spinbox = Spinbox(row1_frame, from_=1, to=9999, width=6, textvariable=self.target_count_var)
        self.target_count_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        self.create_tooltip(self.target_count_spinbox, "取得するギャラリーの数を指定します。検索結果から指定した数だけURLを抽出します。")
        
        # ページWait
        page_wait_label = ttk.Label(row1_frame, text="ページWait(s):")
        page_wait_label.pack(side=tk.LEFT, padx=(5, 0))
        self.create_tooltip(page_wait_label, "次のページを取得するまでの待機時間（秒）を指定します")
        self.page_wait_time_var = tk.DoubleVar(value=2.0)
        self.page_wait_time_spinbox = Spinbox(row1_frame, from_=0.5, to=60.0, increment=0.5, width=4, textvariable=self.page_wait_time_var, format="%.1f")
        self.page_wait_time_spinbox.pack(side=tk.LEFT, padx=(0, 10))
        self.create_tooltip(self.page_wait_time_spinbox, "検索結果ページを移動する際の待機時間（秒）を指定します。サーバーに負荷をかけないよう適切な値を設定してください。")

        # Row 2: Thumbnail Options and Buttons
        row2_frame = ttk.Frame(top_frame)
        row2_frame.pack(fill=tk.X)

        # 左カラム（サムネイル関連）
        left_column = ttk.Frame(row2_frame)
        left_column.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # サムネイル関連の上段フレーム
        thumb_top_frame = ttk.Frame(left_column)
        thumb_top_frame.pack(fill=tk.X)

        self.auto_thumb_var = tk.BooleanVar(value=False)
        self.auto_thumb_check = ttk.Checkbutton(thumb_top_frame, text="サムネイル自動取得", 
                                            variable=self.auto_thumb_var,
                                            command=self.on_auto_thumb_changed)
        self.auto_thumb_check.pack(side=tk.LEFT, padx=(0, 5))
        self.create_tooltip(self.auto_thumb_check, "解析時に自動的にサムネイルを取得します。\nチェックを入れると、キャッシュ上限まで1度だけ自動取得します")

        thumb_wait_label = ttk.Label(thumb_top_frame, text="サムネイルWait(s):")
        thumb_wait_label.pack(side=tk.LEFT, padx=(0, 0))
        self.create_tooltip(thumb_wait_label, "サムネイル取得時の待機時間を設定します（秒）")
        self.thumb_wait_time_var = tk.DoubleVar(value=0.3)
        self.thumb_wait_time_spinbox = Spinbox(thumb_top_frame, from_=0.1, to=10.0, increment=0.1, width=4, textvariable=self.thumb_wait_time_var, format="%.1f")
        self.thumb_wait_time_spinbox.pack(side=tk.LEFT, padx=(0, 10))

        # キャッシュサイズ制限
        cache_size_label = ttk.Label(thumb_top_frame, text="キャッシュ上限(MB):")
        cache_size_label.pack(side=tk.LEFT)
        self.create_tooltip(cache_size_label, "サムネイルキャッシュの最大サイズを設定します（MB）。\n上限に達すると古いキャッシュから自動的に削除されます")
        self.cache_size_var = tk.IntVar(value=500)
        self.cache_size_spinbox = Spinbox(thumb_top_frame, from_=0, to=2000, increment=100, width=5, textvariable=self.cache_size_var)
        self.cache_size_spinbox.pack(side=tk.LEFT, padx=(0, 5))

        # 現在のキャッシュ使用量
        self.current_cache_var = tk.StringVar(value="使用中: 0MB")
        cache_usage_label = ttk.Label(thumb_top_frame, textvariable=self.current_cache_var)
        cache_usage_label.pack(side=tk.LEFT, padx=(0, 5))
        self.create_tooltip(cache_usage_label, "現在のキャッシュ使用量を表示します")

        # キャッシュクリアボタン
        self.clear_cache_btn = ttk.Button(thumb_top_frame, text="キャッシュクリア", command=self.clear_cache)
        self.clear_cache_btn.pack(side=tk.LEFT)
        self.create_tooltip(self.clear_cache_btn, "現在のサムネイルキャッシュをすべて削除します")

        # サムネイル関連の下段フレーム
        thumb_bottom_frame = ttk.Frame(left_column)
        thumb_bottom_frame.pack(fill=tk.X)

        # サムネイル取得無効化のチェックボックス
        self.disable_thumb_var = tk.BooleanVar(value=False)
        self.disable_thumb_check = ttk.Checkbutton(thumb_bottom_frame, text="サムネイルを取得しない", 
                                               variable=self.disable_thumb_var,
                                               command=self.on_disable_thumb_changed)
        self.disable_thumb_check.pack(side=tk.LEFT)
        self.create_tooltip(self.disable_thumb_check, "チェックを入れると、マウスホバー時のサムネイル取得を無効化します")

        # 右カラム（ボタン）
        right_column = ttk.Frame(row2_frame)
        right_column.pack(side=tk.RIGHT)

        # 上段ボタン群
        top_button_frame = ttk.Frame(right_column)
        top_button_frame.pack(side=tk.TOP, pady=(0, 5))

        self.stop_button = ttk.Button(top_button_frame, text="中断", command=self.stop_parsing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.stop_button, "現在実行中の解析を中断します。")

        self.resume_button = ttk.Button(top_button_frame, text="再開", command=self.resume_parsing, state=tk.DISABLED)
        self.resume_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.resume_button, "中断された解析を再開します。")

        self.clear_button = ttk.Button(top_button_frame, text="クリア", command=self.clear_data)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.clear_button, "現在の解析結果とデータをクリアします。")

        # 下段ボタン群
        bottom_button_frame = ttk.Frame(right_column)
        bottom_button_frame.pack(side=tk.TOP, anchor=tk.E)  # anchor=tk.Eを追加して右寄せ

        self.load_backup_button = ttk.Button(bottom_button_frame, text="バックアップ読み込み", command=self.load_data)
        self.load_backup_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.load_backup_button, "以前に保存したバックアップファイルから設定とURLリストを復元します。")

        self.save_backup_button = ttk.Button(bottom_button_frame, text="バックアップ保存", command=self.save_data)
        self.save_backup_button.pack(side=tk.LEFT, padx=5)
        self.create_tooltip(self.save_backup_button, "現在の設定とURLリストをバックアップファイルとして保存します。")

        # 中央ボタンエリア（新規追加）
        center_button_area = ttk.Frame(self.root)
        center_button_area.pack(fill=tk.X, padx=5, pady=(5, 0))

        # URL解析ボタン用のフレーム
        export_button_frame = ttk.Frame(center_button_area)
        export_button_frame.pack(fill=tk.X)
        
        # ボタンを中央に配置するための左右スペーサー
        ttk.Label(export_button_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 大きなフォントを設定
        export_font = tkFont.Font(size=14, weight="bold")
        button_style = ttk.Style()
        button_style.configure("Export.TButton", font=export_font)
        
        # 解析モード選択
        self.parse_mode_var = tk.StringVar(value="DBに追加")
        self.parse_mode_combo = ttk.Combobox(export_button_frame, textvariable=self.parse_mode_var,
                                           values=["DBに追加", "DBをクリアしてから追加"],
                                           width=20, state="readonly")
        
        # URL解析実行ボタン
        self.parse_button = ttk.Button(export_button_frame, text="URL解析を実行", 
                                     command=self.start_parsing_new,
                                     width=20, style="Export.TButton")
        self.parse_button.pack(side=tk.LEFT, pady=5, padx=(0, 5))
        self.create_tooltip(self.parse_button, "URLリストの解析を実行し、各URLの有効性をチェックします。")
        
        # モード選択コンボボックス
        self.parse_mode_combo.pack(side=tk.LEFT, pady=5, padx=5)
        self.create_tooltip(self.parse_mode_combo, "解析モードを選択します。「DBに追加」はデータベースに保存、「DBをクリアしてから追加」は既存データをクリアしてから保存します。")
        
        # 解析結果出力ボタン
        self.output_button = ttk.Button(export_button_frame, text="解析結果を出力", 
                                      command=self.export_results,
                                      width=20, style="Export.TButton", state=tk.DISABLED)
        self.output_button.pack(side=tk.LEFT, pady=5, padx=(5, 0))
        self.create_tooltip(self.output_button, "解析結果をテキストファイルとして出力します。")
        
        ttk.Label(export_button_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 下段ボタンフレーム（Torrentマネージャーボタン用）
        bottom_button_frame = ttk.Frame(center_button_area)
        bottom_button_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 左側スペーサー
        ttk.Label(bottom_button_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # TorrentファイルDLマネージャー起動ボタン（下側の右端に配置）
        self.torrent_manager_button = ttk.Button(bottom_button_frame, text="TorrentファイルDLマネージャー起動", 
                                               command=self._launch_torrent_manager,
                                               state=tk.DISABLED)
        self.torrent_manager_button.pack(side=tk.RIGHT, pady=5, padx=(5, 0))
        self.create_tooltip(self.torrent_manager_button, "Torrentファイルのダウンロードを管理します。E-HentaiのTorrent機能を使用する場合に便利です。")

        # フィルターエリア
        filter_container = ttk.Frame(self.root)
        filter_container.pack(fill=tk.X, padx=5, pady=(0, 5))

        # フィルターヘッダー
        filter_header = ttk.Frame(filter_container)
        filter_header.pack(fill=tk.X)
        
        # フィルタータイトルとトグルボタンを含むフレーム
        title_frame = ttk.Frame(filter_header)
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(title_frame, text="フィルタリング").pack(side=tk.LEFT)
        
        self.filter_visible = tk.BooleanVar(value=False)  # デフォルトで非表示
        self.toggle_filter_btn = ttk.Button(title_frame, text="表示▼", width=8, command=self.toggle_filter_area)
        self.toggle_filter_btn.pack(side=tk.LEFT, padx=(10, 0))

        # フィルターフレーム（余白なし）
        self.filter_frame = ttk.Frame(filter_container)

        # フィルターの内容を実装
        # ... (フィルターの実装部分は変更なし) ...

        # フィルターボタン（右下に配置）
        button_frame_filter = ttk.Frame(self.filter_frame)
        button_frame_filter.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        ttk.Label(button_frame_filter).pack(side=tk.LEFT, fill=tk.X, expand=True)  # スペーサー
        
        # フィルター適用ボタン
        self.apply_filter_button = ttk.Button(button_frame_filter, text="フィルター適用",
                                            command=self.apply_advanced_filters, state=tk.DISABLED)
        self.apply_filter_button.pack(side=tk.RIGHT)
        
        # 入力値クリアボタン
        self.clear_filter_input_btn = ttk.Button(button_frame_filter, text="入力値クリア",
                                               command=self.clear_filter_inputs)
        self.clear_filter_input_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # データ表示エリアのコンテナ
        data_container = ttk.Frame(self.root)
        data_container.pack(fill=tk.BOTH, expand=True)

        # フィルター用の変数
        self.filter_vars = {
            'title_whitelist': tk.StringVar(),
            'title_blacklist': tk.StringVar(),
            'tags_whitelist': tk.StringVar(),
            'tags_blacklist': tk.StringVar(),
            'date_value': tk.StringVar(),
            'date_condition': tk.StringVar(value='以前'),
            'pages_value': tk.StringVar(),
            'pages_condition': tk.StringVar(value='以上'),
            'category_whitelist': tk.StringVar(),  # カテゴリフィルター用
            'category_blacklist': tk.StringVar(),  # カテゴリフィルター用
            'uploader_whitelist': tk.StringVar(),  # Uploaderフィルター用
            'uploader_blacklist': tk.StringVar(),  # Uploaderフィルター用
            'number_value': tk.StringVar(),        # 番号フィルター用
            'number_condition': tk.StringVar(value='以上'),  # 番号フィルター用
            'rating_value': tk.StringVar(),        # 評価フィルター用
            'rating_condition': tk.StringVar(value='以上')   # 評価フィルター用
        }
        
        # フィルタリング関連のGUI変数を初期化（設定保存・読み込み用）
        self.filter_enabled_var = tk.BooleanVar(value=False)
        self.filter_artist_var = tk.StringVar(value="")
        self.filter_parody_var = tk.StringVar(value="")
        self.filter_character_var = tk.StringVar(value="")
        self.filter_group_var = tk.StringVar(value="")
        self.filter_language_var = tk.StringVar(value="")
        self.filter_category_var = tk.StringVar(value="")

        # フィルターフレームの幅を固定
        label_width = 8  # ラベルの幅を統一
        list_label_width = 12  # リストラベルの幅を統一

        # タイトルフィルター
        title_frame = ttk.Frame(self.filter_frame)
        title_frame.pack(fill=tk.X, pady=2)
        ttk.Label(title_frame, text="タイトル", width=label_width, anchor='w').pack(side=tk.LEFT)
        whitelist_label = ttk.Label(title_frame, text=": ホワイトリスト", width=list_label_width)
        whitelist_label.pack(side=tk.LEFT)
        self.create_tooltip(whitelist_label, "カンマ(,)または読点(、)で区切って複数のキーワードを指定できます\n指定したキーワードを含むタイトルのみを表示します")
        self.title_white_entry = ttk.Entry(title_frame, textvariable=self.filter_vars['title_whitelist'])
        self.title_white_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        blacklist_label = ttk.Label(title_frame, text="ブラックリスト", width=list_label_width)
        blacklist_label.pack(side=tk.LEFT)
        self.create_tooltip(blacklist_label, "カンマ(,)または読点(、)で区切って複数のキーワードを指定できます\n指定したキーワードを含むタイトルを除外します")
        self.title_black_entry = ttk.Entry(title_frame, textvariable=self.filter_vars['title_blacklist'])
        self.title_black_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # タグフィルター
        tags_frame = ttk.Frame(self.filter_frame)
        tags_frame.pack(fill=tk.X, pady=2)
        ttk.Label(tags_frame, text="タグ", width=label_width, anchor='w').pack(side=tk.LEFT)
        ttk.Label(tags_frame, text=": ホワイトリスト", width=list_label_width).pack(side=tk.LEFT)
        self.tags_white_entry = ttk.Entry(tags_frame, textvariable=self.filter_vars['tags_whitelist'])
        self.tags_white_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(tags_frame, text="ブラックリスト", width=list_label_width).pack(side=tk.LEFT)
        self.tags_black_entry = ttk.Entry(tags_frame, textvariable=self.filter_vars['tags_blacklist'])
        self.tags_black_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # カテゴリフィルター
        category_frame = ttk.Frame(self.filter_frame)
        category_frame.pack(fill=tk.X, pady=2)
        ttk.Label(category_frame, text="カテゴリ", width=label_width, anchor='w').pack(side=tk.LEFT)
        ttk.Label(category_frame, text=": ホワイトリスト", width=list_label_width).pack(side=tk.LEFT)
        self.category_white_entry = ttk.Entry(category_frame, textvariable=self.filter_vars['category_whitelist'])
        self.category_white_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(category_frame, text="ブラックリスト", width=list_label_width).pack(side=tk.LEFT)
        self.category_black_entry = ttk.Entry(category_frame, textvariable=self.filter_vars['category_blacklist'])
        self.category_black_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Uploaderフィルター
        uploader_frame = ttk.Frame(self.filter_frame)
        uploader_frame.pack(fill=tk.X, pady=2)
        ttk.Label(uploader_frame, text="Uploader", width=label_width, anchor='w').pack(side=tk.LEFT)
        ttk.Label(uploader_frame, text=": ホワイトリスト", width=list_label_width).pack(side=tk.LEFT)
        self.uploader_white_entry = ttk.Entry(uploader_frame, textvariable=self.filter_vars['uploader_whitelist'])
        self.uploader_white_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Label(uploader_frame, text="ブラックリスト", width=list_label_width).pack(side=tk.LEFT)
        self.uploader_black_entry = ttk.Entry(uploader_frame, textvariable=self.filter_vars['uploader_blacklist'])
        self.uploader_black_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # 日付とページ数フィルター
        conditions_frame = ttk.Frame(self.filter_frame)
        conditions_frame.pack(fill=tk.X, pady=2)

        # 投稿日フィルター
        ttk.Label(conditions_frame, text="投稿日:", width=label_width, anchor='w').pack(side=tk.LEFT)
        self.date_entry = ttk.Entry(conditions_frame, textvariable=self.filter_vars['date_value'], width=20)
        self.date_entry.pack(side=tk.LEFT, padx=5)
        self.date_combo = ttk.Combobox(conditions_frame, textvariable=self.filter_vars['date_condition'],
                                     values=['以前', '以後'], width=6, state='readonly')
        self.date_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.create_tooltip(self.date_entry, "日付の形式: YYYY-MM-DD HH:MM\n例: 2023-01-01 00:00")
        # プレースホルダーを設定
        self.date_entry.insert(0, "例: 2025-07-07 7")
        self.date_entry.configure(foreground='gray')
        self.date_entry.bind("<FocusIn>", self.on_date_entry_focus_in)
        self.date_entry.bind("<FocusOut>", self.on_date_entry_focus_out)

        # ページ数フィルター
        ttk.Label(conditions_frame, text="ページ数:", width=label_width, anchor='w').pack(side=tk.LEFT)
        self.pages_entry = ttk.Entry(conditions_frame, textvariable=self.filter_vars['pages_value'], width=8)
        self.pages_entry.pack(side=tk.LEFT, padx=5)
        self.pages_combo = ttk.Combobox(conditions_frame, textvariable=self.filter_vars['pages_condition'],
                                      values=['以上', '以下'], width=6, state='readonly')
        self.pages_combo.pack(side=tk.LEFT, padx=(0, 20))

        # 番号フィルター
        ttk.Label(conditions_frame, text="番号:", width=label_width, anchor='w').pack(side=tk.LEFT)
        self.number_entry = ttk.Entry(conditions_frame, textvariable=self.filter_vars['number_value'], width=8)
        self.number_entry.pack(side=tk.LEFT, padx=5)
        self.number_combo = ttk.Combobox(conditions_frame, textvariable=self.filter_vars['number_condition'],
                                      values=['以上', '以下'], width=6, state='readonly')
        self.number_combo.pack(side=tk.LEFT, padx=(0, 20))

        # 評価フィルター
        ttk.Label(conditions_frame, text="評価:", width=label_width, anchor='w').pack(side=tk.LEFT)
        self.rating_entry = ttk.Entry(conditions_frame, textvariable=self.filter_vars['rating_value'], width=8)
        self.rating_entry.pack(side=tk.LEFT, padx=5)
        self.rating_combo = ttk.Combobox(conditions_frame, textvariable=self.filter_vars['rating_condition'],
                                      values=['以上', '以下'], width=6, state='readonly')
        self.rating_combo.pack(side=tk.LEFT, padx=(0, 20))

        # ボタンフレーム（チェックボックス用）
        button_frame = ttk.Frame(data_container)
        button_frame.pack(fill=tk.X, pady=(10, 5))  # 上側に10pxスペースを追加
        
        # 左側のボタン
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)
        self.check_all_btn = ttk.Button(left_buttons, text="すべて✓", command=self.check_all_items)
        self.check_all_btn.pack(side=tk.LEFT, padx=5)
        self.uncheck_all_btn = ttk.Button(left_buttons, text="すべてOFF", command=self.uncheck_all_items)
        self.uncheck_all_btn.pack(side=tk.LEFT)

        # 右側のボタン
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)
        self.reset_filter_btn = ttk.Button(right_buttons, text="フィルタリング解除", command=self.reset_advanced_filters)
        self.reset_filter_btn.pack(side=tk.RIGHT, padx=5)

        # ページ数表示（中央）
        self.total_pages_var = tk.StringVar(value="取得ページ総数: 0")
        self.selected_pages_var = tk.StringVar(value="選択: 0/0")
        ttk.Label(button_frame, textvariable=self.total_pages_var).pack(side=tk.LEFT, padx=(20, 10))
        ttk.Label(button_frame, textvariable=self.selected_pages_var).pack(side=tk.LEFT)

        # Treeviewのコンテナ
        tree_frame = ttk.Frame(data_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Treeviewのセットアップ
        CHECKBOX_CHECKED = "☒"
        CHECKBOX_UNCHECKED = "☐"
        columns = ("Select", "Number", "Title", "Genre", "Date", "Pages", "Rating", "Uploader", "Tags", "URL", "Torrent", "ThumbnailURL")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        
        # ⭐修正: checked_itemsを確実に空のsetで初期化（デバッグログ追加）⭐
        self.checked_items = set()  # チェックボックス状態の保存用
        print(f"[DEBUG] Parser: checked_items initialized as empty set: {self.checked_items}")
        
        self.hidden_items = set()  # 非表示アイテムの保存用
        self.filter_conditions = {
            'category': {'exclude': None, 'include': None},
            'uploader': {'exclude': None, 'include': None}
        }
        
        # イベントバインド
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self.hide_thumbnail_popup(delay=100))
        self.tree.bind("<space>", self.toggle_selected_items)  # スペースキー
        self.tree.bind("<Return>", self.toggle_selected_items)  # エンターキー

        # --- Font Setup ---
        try:
            default_font = tkFont.nametofont("TkDefaultFont")
            self.hyperlink_font = tkFont.Font(font=default_font)
            self.hyperlink_font.configure(underline=True)
            self.tree.tag_configure("hyperlink", foreground="blue", font=self.hyperlink_font)
        except tk.TclError:
            print("Warning: Could not create underlined font.")
            self.tree.tag_configure("hyperlink", foreground="blue")

        # Headings & Columns Setup
        headings_widths = {
            "Select": ("✓", 30, tk.NO, tk.CENTER),
            "Number": ("番号", 50, tk.NO, tk.E),
            "Title": ("タイトル", 280, tk.YES, tk.W),
            "Genre": ("カテゴリ", 80, tk.NO, tk.W),
            "Date": ("投稿日", 85, tk.NO, tk.W),
            "Pages": ("P数", 40, tk.NO, tk.E),
            "Rating": ("評価", 40, tk.NO, tk.E),
            "Uploader": ("Uploader", 100, tk.NO, tk.W),
            "Tags": ("主要タグ", 180, tk.YES, tk.W),
            "URL": ("ギャラリーURL", 150, tk.YES, tk.W),
            "Torrent": ("Torrent", 50, tk.NO, tk.W),
            "ThumbnailURL": ("サムネイルURL", 200, tk.NO, tk.W)
        }

        # ソート用の変数を初期化
        self.sort_column = None  # 現在のソート列
        self.sort_reverse = False  # ソート順（昇順/降順）

        for col, (text, width, stretch, anchor) in headings_widths.items():
            self.tree.heading(col, text=text, anchor=anchor,
                            command=lambda c=col: self.sort_treeview(c))
            self.tree.column(col, width=width, stretch=stretch, anchor=anchor)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        
        # スクロールバーの設定
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.configure(command=self.tree.yview)
        
        # ウィジェットの配置
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # イベントバインド
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Motion>", self.on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self.hide_thumbnail_popup(delay=100))
        self.tree.bind("<space>", self.toggle_selected_items)  # スペースキー
        self.tree.bind("<Return>", self.toggle_selected_items)  # エンターキー

        # スタイル設定
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)  # チェックボックス用に行の高さを調整
        style.map("Treeview",
                 foreground=[("selected", "black")],
                 background=[("selected", "white")])  # 選択時の背景色を白に変更
        self.tree.tag_configure("checked", background="#CCE5FF")  # チェック用の薄い青色

        # 右クリックメニュー
        self.category_menu = tk.Menu(self.root, tearoff=0)
        self.category_menu.add_command(label="除外", command=lambda: self.filter_category("exclude"))
        self.category_menu.add_command(label="抽出", command=lambda: self.filter_category("include"))
        self.category_menu.add_separator()
        self.category_menu.add_command(label="コピー", command=lambda: self.copy_current_cell("Genre"))

        self.uploader_menu = tk.Menu(self.root, tearoff=0)
        self.uploader_menu.add_command(label="除外", command=lambda: self.filter_uploader("exclude"))
        self.uploader_menu.add_command(label="抽出", command=lambda: self.filter_uploader("include"))
        self.uploader_menu.add_separator()
        self.uploader_menu.add_command(label="コピー", command=lambda: self.copy_current_cell("Uploader"))

        self.rating_menu = tk.Menu(self.root, tearoff=0)
        self.rating_menu.add_command(label="除外", command=lambda: self.filter_rating("exclude"))
        self.rating_menu.add_command(label="抽出", command=lambda: self.filter_rating("include"))
        self.rating_menu.add_separator()
        self.rating_menu.add_command(label="コピー", command=lambda: self.copy_current_cell("Rating"))

        # コピーメニューは各メニューに追加
        for menu in [self.category_menu, self.uploader_menu, self.rating_menu]:
            menu.add_separator()
            menu.add_command(label="コピー", command=lambda m=menu: self.copy_to_clipboard(self.tree.selection()[0], self.get_column_name_from_menu(m)))

    def set_status(self, message):
        """Update status bar message"""
        if hasattr(self, 'status_var'):
             try:
                  self.root.after(0, lambda msg=message: self.status_var.set(msg))
             except Exception as e:
                  print(f"Error setting status: {e}")

    def start_parsing_new(self):
        """新しい解析開始メソッド"""
        url = self.url_entry.get().strip()
        
        # URLの空チェック
        if not url:
            messagebox.showwarning("警告", "URLが空です。", parent=self.root)
            return
            
        # モード確認
        mode = self.parse_mode_var.get()
        
        if mode == "DBをクリアしてから追加":
            if self.gallery_data:
                response = messagebox.askyesno(
                    "確認",
                    "現在のデータベースをクリアしてから解析を始めますが、よろしいですか？",
                    parent=self.root
                )
                if not response:
                    return
            self.clear_database_internal()
        
        # 解析開始
        self.start_parsing_internal(url)

    def clear_database_internal(self):
        """データベースの内部クリア処理"""
        self.gallery_data.clear()
        self.processed_urls.clear()
        self.processed_galleries.clear()
        self.checked_items.clear()
        self.hidden_items.clear()
        self.last_gallery_id = None
        self.last_gallery_token = None
        self.filter_history.clear()
        self.filter_states.clear()
        self._has_output_urls = False
        
        # Treeview をクリア
        self.tree.delete(*self.tree.get_children())
        
        # ステータス更新
        self.total_pages_var.set("取得ページ総数: 0")
        self.selected_pages_var.set("選択: 0/0")
        
        # ボタン状態更新
        self.output_button.configure(state=tk.DISABLED)
        self.continue_button.configure(state=tk.DISABLED)

    def start_parsing_internal(self, url):
        """内部解析処理"""
        # ボタン状態変更
        self.parse_button.configure(text="解析中……", state=tk.DISABLED)
        self.output_button.configure(text="解析中……", state=tk.DISABLED)
        self.parse_mode_combo.configure(state=tk.DISABLED)
        
        # 解析処理
        page_wait_time = self.page_wait_time_var.get()
        self.current_thread_target = self.target_count_var.get()
        
        # 2000件以上の場合、警告を表示
        if self.current_thread_target > 2000 and not hasattr(self, '_large_data_warning_shown'):
            response = messagebox.askokcancel(
                "警告",
                "2000件以上のデータを取得しようとしています。\n"
                "大量のデータ取得は以下の影響がある可能性があります：\n"
                "・処理時間の増加\n"
                "・メモリ使用量の増加\n"
                "・E-Hentaiサーバーへの負荷\n\n"
                "続行しますか？",
                parent=self.root
            )
            if not response:
                self._reset_parsing_buttons()
                return
            self._large_data_warning_shown = True
        
        self.log(f"解析開始: {url} (目標: {self.current_thread_target}, ページWait: {page_wait_time}s)")
        
        # ⭐追加: 解析開始時に選択状態をクリア⭐
        self.checked_items.clear()
        self.log("[DEBUG] 解析開始時に選択状態をクリアしました")
        
        # 関連ウィジェットをグレーアウト
        self.stop_button.config(state=tk.NORMAL)
        self.resume_button.config(state=tk.DISABLED)
        self.disable_filter_area()
        self.stop_event.clear()
        self.stop_thumbnail_downloader.clear()
        self.is_parsing = True

        self.set_status("解析準備中...")
        
        # サムネイルダウンローダーの準備
        while not self.thumbnail_queue.empty():
            try: self.thumbnail_queue.get_nowait()
            except Empty: break

        if not self.thumbnail_download_thread or not self.thumbnail_download_thread.is_alive():
            self.start_thumbnail_downloader()

        # 解析スレッド開始
        self.parsing_thread = threading.Thread(target=self._fetch_and_parse_new,
                                            args=(url, self.current_thread_target, page_wait_time),
                                            daemon=True)
        self.parsing_thread.start()

    def _reset_parsing_buttons(self):
        """解析ボタンの状態をリセット"""
        self.parse_button.configure(text="URL解析を実行", state=tk.NORMAL)
        if self.gallery_data:
            self.output_button.configure(text="解析結果を出力", state=tk.NORMAL)
        else:
            self.output_button.configure(text="解析結果を出力", state=tk.DISABLED)
        self.parse_mode_combo.configure(state="readonly")

    def resume_parsing(self):
        """中断された解析を再開"""
        if not self.last_url_var.get():
            self.log("再開可能な解析情報がありません。")
            return

        # 選択状態をリセット
        self.checked_items.clear()
        self.update_status()
        
        # 継続解析時は最後のギャラリー情報をクリア
        self.last_gallery_id = None
        self.last_gallery_token = None
        
        # 直接内部解析処理を呼び出し
        self.start_parsing_internal(self.last_url_var.get())

    def stop_parsing(self):
        """解析を中断"""
        if self.parsing_thread and self.parsing_thread.is_alive():
            self.log("解析中断...")
            self.set_status("中断中...")
            self.stop_event.set()
            self.stop_button.config(state=tk.DISABLED)
            self.resume_button.config(state=tk.NORMAL)
            self.is_parsing = False
            
            # 中断時に目標数の進捗を保持
            self.target_count_var.set(self.current_thread_target)
            
            # ボタン状態をリセット
            self._reset_parsing_buttons()

            # データがある場合のみフィルターエリアを有効化
            if self.gallery_data:
                self.enable_filter_area()
            else:
                self.disable_filter_area()
        else:
            self.log("アクティブな解析スレッドはありません。")

    def start_thumbnail_downloader(self):
        """Starts the background thread for downloading thumbnails."""
        self.stop_thumbnail_downloader.clear()
        self.thumbnail_download_thread = threading.Thread(target=self._thumbnail_downloader_worker, daemon=True)
        self.thumbnail_download_thread.start()
        self.log("サムネイルダウンローダー起動")

    def _thumbnail_downloader_worker(self):
        """Worker thread processing the thumbnail download queue."""
        self.log("サムネイルダウンローダー稼働中")
        last_download_time = 0
        
        while not self.stop_thumbnail_downloader.is_set():
            try:
                url = self.thumbnail_queue.get(timeout=1)
                if url is None: break
                
                # キャッシュチェックとスキップ
                if url in self.thumbnail_cache or self.stop_thumbnail_downloader.is_set():
                    self.thumbnail_queue.task_done()
                    continue
                
                # インターバル制御
                thumb_wait_time = self.thumb_wait_time_var.get()
                current_time = time.time()
                time_since_last = current_time - last_download_time
                if time_since_last < thumb_wait_time:
                    time.sleep(thumb_wait_time - time_since_last)
                
                if self.stop_thumbnail_downloader.is_set(): break
                
                try:
                    # サムネイル取得
                    response = self.session.get(url, timeout=8, stream=True)
                    response.raise_for_status()
                    image_data = io.BytesIO(response.content)
                    
                    # 画像の検証と最適化
                    try:
                        image = Image.open(image_data)
                        image.verify()
                        image_data.seek(0)
                        
                        # 画像をメモリ効率の良いサイズに変換
                        image = Image.open(image_data)
                        image.thumbnail((300, 400), Image.Resampling.LANCZOS)
                        optimized_data = io.BytesIO()
                        image.save(optimized_data, format=image.format, optimize=True)
                        optimized_data.seek(0)
                        
                        # キャッシュに保存
                        self.thumbnail_cache[url] = optimized_data
                        self.manage_thumbnail_cache(url)  # キャッシュ管理を実行
                        last_download_time = time.time()
                        self.log(f"サムネイル取得成功: {url}")
                        
                        # キャッシュに保存して終了
                        self.thumbnail_cache[url] = optimized_data
                        self.manage_thumbnail_cache(url)
                        
                    except Exception as e:
                        self.log(f"サムネイル検証/最適化エラー ({url}): {e}")
                        self.thumbnail_cache[url] = None
                        
                except Exception as e:
                    self.log(f"サムネイル取得エラー ({url}): {e}")
                    self.thumbnail_cache[url] = None
                finally:
                    self.thumbnail_queue.task_done()
                    
            except Empty:
                continue
            except Exception as e:
                self.log(f"サムネイルダウンローダー致命的エラー: {e}")
                traceback.print_exc()
                time.sleep(5)
                
        self.log("サムネイルダウンローダー停止")

    def manage_thumbnail_cache(self, url=None):
        """サムネイルキャッシュを管理"""
        if url and url not in self.thumbnail_cache_order:
            self.thumbnail_cache_order.append(url)
        
        # キャッシュサイズの計算と制限
        total_size = 0
        urls_to_remove = []
        
        for cached_url in self.thumbnail_cache_order:
            if cached_url in self.thumbnail_cache and self.thumbnail_cache[cached_url]:
                data_size = len(self.thumbnail_cache[cached_url].getvalue()) / (1024 * 1024)  # MBに変換
                total_size += data_size
                
                # キャッシュ上限を超えた場合、古いものから削除リストに追加
                if total_size > self.cache_size_var.get():
                    urls_to_remove.append(cached_url)
        
        # 古いキャッシュを削除
        for remove_url in urls_to_remove:
            if remove_url in self.thumbnail_cache:
                del self.thumbnail_cache[remove_url]
            if remove_url in self.thumbnail_cache_order:
                self.thumbnail_cache_order.remove(remove_url)
        
        self.current_cache_var.set(f"使用中: {total_size:.1f}MB")

    def update_cache_status(self):
        """キャッシュ状態を更新"""
        total_size = 0
        for data in self.thumbnail_cache.values():
            if data:
                total_size += len(data.getvalue()) / (1024 * 1024)  # バイトをMBに変換
        self.current_cache_var.set(f"使用中:{total_size:.1f}MB")

    def on_auto_thumb_changed(self):
        """サムネイル自動取得のチェックボックス状態変更時の処理"""
        if self.auto_thumb_var.get():
            # キャッシュ上限までの一括取得を実行
            cache_limit = self.cache_size_var.get()
            current_cache_size = sum(len(data.getvalue()) if data else 0 
                                   for data in self.thumbnail_cache.values()) / (1024 * 1024)
            remaining_space = max(0, cache_limit - current_cache_size)
            
            # 残りスペースに応じて取得可能な数を計算（1サムネイル平均0.5MB と仮定）
            estimated_thumbs = int(remaining_space / 0.5)
            if estimated_thumbs > 0:
                self.log(f"サムネイル自動取得を開始します（最大 {estimated_thumbs} 件）")
                count = 0
                for item in self.tree.get_children():
                    if count >= estimated_thumbs:
                        break
                    values = self.tree.item(item)['values']
                    thumb_index = self.tree["columns"].index("ThumbnailURL")
                    if len(values) > thumb_index:
                        thumb_url = values[thumb_index]
                        if thumb_url and thumb_url.startswith('http') and thumb_url not in self.thumbnail_cache:
                            self.thumbnail_queue.put(thumb_url)
                            count += 1
                self.log(f"サムネイル取得をキューに追加: {count} 件")
            else:
                self.log("キャッシュ容量が不足しているため、新規サムネイルは取得できません")
        else:
            # キューをクリアして自動取得を停止
            while not self.thumbnail_queue.empty():
                try:
                    self.thumbnail_queue.get_nowait()
                except Empty:
                    break
            self.log("サムネイル自動取得を無効化しました")


    def enforce_inline_dm_l(self, url):
        """URL に必ず ?inline_set=dm_l を付与（既に inline_set があれば置換）"""
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query['inline_set'] = ['dm_l']
            new_query = urlencode(query, doseq=True)
            new_url = urlunparse(parsed._replace(query=new_query))
            return new_url
        except Exception as e:
            self.log(f"URL整形エラー: {e}")
            # エラーが発生した場合は元のURLを返す
            return url
    
    def normalize_url_for_output(self, url):
        """URLから ?inline_set=dm_l 接尾辞を削除して正規化"""
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            
            # inline_set=dm_l を削除
            if 'inline_set' in query and 'dm_l' in query['inline_set']:
                query['inline_set'].remove('dm_l')
                # inline_setが空になった場合は削除
                if not query['inline_set']:
                    del query['inline_set']
            
            # 新しいクエリ文字列を構築
            if query:
                new_query = urlencode(query, doseq=True)
                normalized_url = urlunparse(parsed._replace(query=new_query))
            else:
                # クエリが空の場合はクエリ部分を削除
                normalized_url = urlunparse(parsed._replace(query=''))
            
            return normalized_url
        except Exception as e:
            self.log(f"URL正規化エラー: {e}")
            # エラーが発生した場合は元のURLを返す
            return url

    def _fetch_and_parse_new(self, base_url, target_count, page_wait_time):
        """
        新しい解析ロジック: 必ず ?inline_set=dm_l を付与し、
        gl2c および gl1e に対応したギャラリーブロック抽出。
        """
        current_url = self.enforce_inline_dm_l(base_url)
        total_parsed_count = 0
        current_thread_count = 0
        page_number = 1
        
        try:
            while not self.stop_event.is_set():
                if current_thread_count >= self.current_thread_target:
                    self.log(f"目標数 ({self.current_thread_target}) に到達しました。解析終了。")
                    break

                self.last_url_var.set(current_url)

                if page_number > 1:
                    self.set_status(f"次のページ ({page_number}) へ待機中 ({page_wait_time}s)...")
                    time.sleep(page_wait_time)

                if self.stop_event.is_set():
                    break

                self.set_status(f"ページ {page_number} 取得中...")
                self.log(f"ページ {page_number}: {current_url}")

                # 自動再開オプション適用のページ取得
                response = self._fetch_page_with_auto_resume(current_url, page_number)
                if not response:
                    self.log(f"ページ取得に失敗しました: {current_url}")
                    self.set_status(f"ページ取得失敗 (ページ {page_number})")
                    self.root.after(0, self._handle_parsing_error, "ページ取得に失敗しました。")
                    break

                html_content = response.text
                self.log(f"HTML取得成功 (サイズ: {len(html_content)} bytes)")

                if "<title>Content Warning</title>" in html_content:
                    self.log("コンテンツ警告ページ検出。処理中断。")
                    self.root.after(0, self._handle_parsing_error, "コンテンツ警告ページが検出されました。")
                    break

                self.set_status(f"ページ {page_number} 解析中...")

                # ギャラリーブロック抽出（<tr> 単位）
                all_tr_blocks = re.findall(r'<tr[\s\S]*?>[\s\S]*?</tr>', html_content)
                self.log(f"ページ {page_number}: 総TRブロック数: {len(all_tr_blocks)}")

                gallery_blocks = []
                for tr_block in all_tr_blocks:
                    if ('gl2c' in tr_block and 'href="/g/' in tr_block) or ('href="https://e-hentai.org/g/' in tr_block):
                        gallery_blocks.append(tr_block)

                self.log(f"ページ {page_number}: ギャラリーブロック数: {len(gallery_blocks)}")
                #if gallery_blocks:
                #    self.log(f"最初のギャラリーブロック: {gallery_blocks[0][:300]}...")
                #else:
                #    self.log("ギャラリーブロックが見つかりませんでした。")

                # ギャラリーブロックの解析
                newly_added_this_page = 0
                valid_blocks = 0

                for i, block_html in enumerate(gallery_blocks):
                    if self.stop_event.is_set() or current_thread_count >= self.current_thread_target:
                        break

                    parsed_info = self._parse_gallery_entry_strict_user_regex(
                        block_html,
                        len(self.gallery_data) + newly_added_this_page
                    )

                    if parsed_info and parsed_info.get('url'):
                        valid_blocks += 1
                        gallery_url = parsed_info['url']
                        gallery_id = parsed_info.get('id')
                        gallery_token = parsed_info.get('token')
                        
                        # ID+トークンによる重複チェック（より正確）
                        gallery_key = f"{gallery_id}_{gallery_token}"
                        if gallery_key not in self.processed_galleries:
                            self.gallery_data.append(parsed_info)
                            self.processed_galleries.add(gallery_key)
                            self.processed_urls.add(gallery_url)  # 後方互換性のため
                            newly_added_this_page += 1
                            current_thread_count += 1

                            self.last_gallery_id = parsed_info['id']
                            self.last_gallery_token = parsed_info['token']

                            if self.auto_thumb_var.get():
                                thumbnail_url = parsed_info.get("thumbnail")
                                if thumbnail_url and thumbnail_url not in self.thumbnail_cache:
                                    self.thumbnail_queue.put(thumbnail_url)

                            if current_thread_count % 10 == 0:
                                self.set_status(
                                    f"解析中 ({current_thread_count}/{self.current_thread_target}, 合計: {len(self.gallery_data)})..."
                                )
                    else:
                        self.log(f"ブロック {i} は解析結果なしでスキップ。")

                self.log(f"ページ {page_number}: {newly_added_this_page} 件の新規ギャラリーを追加（有効ブロック: {valid_blocks}/{len(gallery_blocks)}）")
                
                if valid_blocks == 0:
                    self.log(f"ページ {page_number}: 有効なギャラリーブロックが見つかりません。次のページへ。")
                    next_match = re.search(r'<a id="unext" href="(.*?)">Next &gt;</a>', html_content)
                    if next_match:
                        next_url = next_match.group(1).replace('&amp;', '&')
                        if next_url.startswith('/'):
                            parsed_current = urlparse(current_url)
                            next_url = f"{parsed_current.scheme}://{parsed_current.netloc}{next_url}"
                        current_url = self.enforce_inline_dm_l(next_url)
                        page_number += 1
                        self.log(f"次のページURL: {next_url}")
                        continue
                    else:
                        self.log("Nextボタンが見つかりませんでした。最終ページです。")
                        break

                self.root.after(0, self._update_result_list)

                if self.stop_event.is_set() or current_thread_count >= self.current_thread_target:
                    break

                # 次のページを検索
                next_match = re.search(r'<a id="unext" href="(.*?)">Next &gt;</a>', html_content)
                if next_match:
                    next_url = next_match.group(1).replace('&amp;', '&')
                    if next_url.startswith('/'):
                        parsed_current = urlparse(current_url)
                        next_url = f"{parsed_current.scheme}://{parsed_current.netloc}{next_url}"
                    current_url = self.enforce_inline_dm_l(next_url)
                    page_number += 1
                    self.log(f"次のページURL: {next_url}")
                else:
                    self.log("Nextボタンが見つかりませんでした。最終ページです。")
                    break

        except Exception as e:
            self.log(f"予期せぬ解析エラー: {e}\n{traceback.format_exc()}")
            self.root.after(0, self._handle_parsing_error, f"解析エラー: {e}")
        finally:
            final_count = len(self.gallery_data)
            self.root.after(0, self._finalize_parsing, final_count, current_thread_count)

    def _handle_parsing_error(self, error_message):
        """解析エラーの処理"""
        self.set_status(f"エラー: {error_message}")
        messagebox.showerror("解析エラー", error_message, parent=self.root)
        self._reset_parsing_buttons()
        self.stop_button.config(state=tk.DISABLED)
        self.resume_button.config(state=tk.NORMAL if self.last_url_var.get() else tk.DISABLED)
        self.is_parsing = False
        if self.gallery_data:
            self.enable_filter_area()

    def _finalize_parsing(self, final_count, current_thread_count):
        """解析完了時の処理"""
        self._reset_parsing_buttons()
        self.stop_button.config(state=tk.DISABLED)
        self.continue_button.config(state=tk.NORMAL if self.last_url_var.get() else tk.DISABLED)
        self.is_parsing = False

        # 最終ステータス更新
        if self.stop_event.is_set():
            self.set_status(f"中止 ({final_count}件)")
        elif current_thread_count >= self.current_thread_target:
            self.set_status(f"目標数達成 ({final_count}件)")
        else:
            self.set_status(f"完了: {final_count} 件")

        if self.gallery_data:
            self.enable_filter_area()
        
        self.log(f"解析処理終了。総取得数: {final_count}")
        self.parsing_thread = None

    def _fetch_page_with_auto_resume(self, url, page_number):
        """自動再開オプション適用のページ取得（無限ループ防止付き）"""
        try:
            # 自動再開オプションの設定を取得（修正版）
            # error_handling_modeが"auto_resume"の場合は自動再開を有効にする
            error_handling_mode = getattr(self.root, 'error_handling_mode', None)
            if error_handling_mode and hasattr(error_handling_mode, 'get'):
                auto_resume_enabled = (error_handling_mode.get() == "auto_resume")
            else:
                auto_resume_enabled = False
                
            auto_resume_delay = getattr(self.root, 'auto_resume_delay', 5)
            
            # StringVarから値を安全に取得（最大10回制限付き）
            max_retry_count_var = getattr(self.root, 'max_retry_count', None)
            if max_retry_count_var and hasattr(max_retry_count_var, 'get'):
                try:
                    max_retry_count = int(max_retry_count_var.get())
                    # 最大10回に制限
                    if max_retry_count > 10:
                        max_retry_count = 10
                        self.log("リトライ回数が10回を超えているため、10回に制限しました", "warning")
                    elif max_retry_count <= 0:
                        max_retry_count = 3  # デフォルト値
                except (ValueError, TypeError):
                    max_retry_count = 3  # デフォルト値
            else:
                max_retry_count = 3  # デフォルト値
                
            retry_limit_action = getattr(self.root, 'retry_limit_action', 'selenium_retry')
            
            # リトライが0の場合は即座にリトライ上限達成時オプションに移行
            if max_retry_count == 0:
                self.log("リトライ回数が0のため、即座にリトライ上限達成時オプションを実行します")
                if retry_limit_action == 'selenium_retry':
                    return self._fetch_page_with_selenium(url)
                else:
                    self.log(f"リトライ上限達成: {retry_limit_action}", "error")
                    return None
            
            retry_count = 0
            
            # 無限ループ防止: 最大試行回数制限
            max_total_attempts = 15  # リトライ + Selenium試行を含む総試行回数
            total_attempts = 0
            
            while retry_count < max_retry_count and total_attempts < max_total_attempts:
                total_attempts += 1
                
                try:
                    # 常時エラー回避オプションの適用
                    self._apply_error_avoidance_options()
                    
                    # 通常のページ取得
                    response = self.session.get(url, timeout=30)
                    response.raise_for_status()
                    
                    self.log(f"ページ取得完了: ステータスコード {response.status_code}")
                    return response
                    
                except requests.exceptions.RequestException as e:
                    retry_count += 1
                    self.log(f"ページ取得エラー (試行 {retry_count}/{max_retry_count}, 総試行 {total_attempts}/{max_total_attempts}): {e}")
                    
                    # 無限ループ防止チェック
                    if total_attempts >= max_total_attempts:
                        self.log("無限ループ防止: 最大試行回数に達しました。処理を中断します。", "error")
                        return None
                    
                    if retry_count < max_retry_count:
                        # 自動再開オプションが有効な場合のみ待機
                        if auto_resume_enabled:
                            wait_time = auto_resume_delay * retry_count
                            self.log(f"自動再開: {wait_time}秒待機後、再試行します")
                            time.sleep(wait_time)
                        else:
                            # 自動再開が無効な場合は即座にSeleniumを試行
                            return self._fetch_page_with_selenium(url)
                    else:
                        # 最終試行失敗 - リトライ上限達成時オプションを実行
                        if retry_limit_action == 'selenium_retry':
                            return self._fetch_page_with_selenium(url)
                        else:
                            self.log(f"リトライ上限達成: {retry_limit_action}", "error")
                            return None
                            
                except Exception as e:
                    self.log(f"予期しないエラー: {e}", "error")
                    return None
            
            return None
            
        except Exception as e:
            self.log(f"ページ取得処理エラー: {e}", "error")
            return None

    def _fetch_page_with_selenium(self, url):
        """Seleniumを使用したページ取得"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            self.log("Seleniumを使用してページを取得中...")
            
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
                
                html_content = driver.page_source
                self.log("Seleniumページ取得成功")
                
                # requests.Responseオブジェクトを模擬
                class MockResponse:
                    def __init__(self, text, status_code=200):
                        self.text = text
                        self.status_code = status_code
                
                return MockResponse(html_content)
                
            finally:
                driver.quit()
                
        except Exception as e:
            self.log(f"Seleniumページ取得エラー: {e}", "error")
            return None

    def _apply_error_avoidance_options(self):
        """常時エラー回避オプションの適用"""
        try:
            # SSL設定の適用
            if getattr(self.root, 'ssl_security_level_enabled', False):
                self._configure_ssl_settings()
                
            # User-Agent偽装の適用
            if getattr(self.root, 'user_agent_spoofing_enabled', False):
                self._apply_user_agent_spoofing()
                
        except Exception as e:
            self.log(f"エラー回避オプション適用エラー: {e}", "error")

    def _configure_ssl_settings(self):
        """SSL設定の適用"""
        try:
            import ssl
            from requests.adapters import HTTPAdapter
            from urllib3.util.ssl_ import create_urllib3_context
            
            # SSL設定を適用
            context = create_urllib3_context()
            context.set_ciphers('DEFAULT@SECLEVEL=1')
            
            # アダプターを作成してセッションにマウント
            class CustomHTTPAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    kwargs['ssl_context'] = context
                    return super().init_poolmanager(*args, **kwargs)
            
            adapter = CustomHTTPAdapter()
            self.session.mount('https://', adapter)
            
            self.log("SSL設定を適用しました")
            
        except Exception as e:
            self.log(f"SSL設定適用エラー: {e}", "error")

    def _apply_user_agent_spoofing(self):
        """User-Agent偽装の適用"""
        try:
            import random
            
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
            ]
            
            user_agent = random.choice(user_agents)
            self.session.headers.update({'User-Agent': user_agent})
            
            self.log(f"User-Agent偽装を適用: {user_agent[:50]}...")
            
        except Exception as e:
            self.log(f"User-Agent偽装適用エラー: {e}", "error")

    def _parse_gallery_entry_strict_user_regex(self, block, index):
        """
        Parses a single gallery TR HTML string using regex patterns for all fields,
        including tags extraction via regex (no BeautifulSoup).
        強制的に ?inline_set=dm_l 付きURLを使用。
        """
        gallery = {}
        try:
            # ギャラリーURL (Fundamental)
            url_match = re.search(r'<a href="(https://e-hentai\.org/g/(\d+)/([a-z0-9]+)/)"', block)
            if not url_match:
                self.log(f"ブロック {index}: URL抽出失敗。スキップ。")
                return None
            
            url_raw = url_match.group(1)
            gallery['url'] = self.enforce_inline_dm_l(url_raw)
            gallery['id'] = url_match.group(2)
            gallery['token'] = url_match.group(3)

            # タイトル
            title_match = re.search(r'<div class="glink">(.*?)</div>', block, re.DOTALL)
            gallery['title'] = title_match.group(1).strip() if title_match else None

            # サムネイル
            thumb_match = re.search(r'<img[^>]+(?:data-)?src="([^"]+\.(?:webp|jpe?g|png|gif))"', block)
            gallery['thumbnail'] = thumb_match.group(1) if thumb_match else None

            # カテゴリ
            cat_match = re.search(r'<div class="cn ct[a-zA-Z0-9]+" .*?>(Doujinshi|Manga|Artist CG|Game CG|Western|Non-H|Image Set|Cosplay|Asian Porn|Misc)</div>', block)
            gallery['genre'] = cat_match.group(1).strip() if cat_match else None

            # 投稿日
            posted_match = re.search(r'id="posted(?:_pop)?_\d+">([\d\- :]+)</div>', block)
            gallery['date'] = posted_match.group(1) if posted_match else None

            # ページ数
            pages_match = re.search(r'(\d+)\s*pages', block)
            gallery['pages'] = int(pages_match.group(1)) if pages_match else None

            # 投稿者
            uploader_match = re.search(r'<a href="https://e-hentai\.org/uploader/[^"]+">([^<]+)</a>', block)
            gallery['uploader'] = uploader_match.group(1) if uploader_match else None

            # タグ
            tag_matches = []
            gl3c_pattern = re.compile(r'<td[^>]*class="gl3c glname"[^>]*>(.*?)</td>', re.DOTALL)
            gl3c_match = gl3c_pattern.search(block)

            if gl3c_match:
                gl3c_content = gl3c_match.group(1)
                #self.log(f"ブロック {index}: gl3c_content抽出成功、長さ: {len(gl3c_content)}")
                
                title_pattern = re.compile(r'<div[^>]*class="gt"[^>]*title="([^"]+)"[^>]*>', re.DOTALL)
                for title_match in title_pattern.finditer(gl3c_content):
                    title_value = title_match.group(1).strip()
                    if title_value:
                        tag_matches.append(title_value)
                        #self.log(f"ブロック {index}: titleタグ追加: {title_value}")
                
                div_pattern = re.compile(r'<div[^>]*class="gt"[^>]*>([^<]+)</div>', re.DOTALL)
                for div_match in div_pattern.finditer(gl3c_content):
                    div_text = div_match.group(1).strip()
                    if div_text:
                        tag_matches.append(div_text)
                        #self.log(f"ブロック {index}: divタグ追加: {div_text}")
            else:
                self.log(f"ブロック {index}: gl3c glname要素が見つかりませんでした")

            gallery['tags'] = tag_matches
            
            # お気に入り度
            fav_match = re.search(
                r'style="background-position:\s*(-?\d+)px\s*(-?\d+)px',
                block
            )
            gallery['favorite_score'] = None
            if fav_match:
                x_pos = int(fav_match.group(1))
                y_pos = int(fav_match.group(2))
                x_map = {
                    0: 5,
                    -16: 4,
                    -32: 3,
                    -48: 2,
                    -64: 1,
                    -80: 0
                }
                base = x_map.get(x_pos)
                if base is not None:
                    if y_pos == -1:
                        gallery['favorite_score'] = float(base)
                    elif y_pos == -21:
                        gallery['favorite_score'] = float(base) - 0.5
            elif 'ir ir_ucho' in block or 'class="ir ir_disabled"' in block:
                gallery['favorite_score'] = 'N/A'

            # トレントURL
            torrent_match = re.search(r'<a href="(https://e-hentai\.org/gallerytorrents\.php\?gid=\d+&amp;t=[a-z0-9]+)"', block)
            gallery['torrent'] = torrent_match.group(1).replace('&amp;', '&') if torrent_match else None

            return gallery

        except Exception as e:
            self.log(f"ブロック解析エラー (Index {index}, Strict User Regex): {e}")
            return None

    def _update_result_list(self):
        """Treeviewの更新"""
        # ページ数表示の更新
        total_pages = len(self.gallery_data)
        visible_pages = len(self.tree.get_children())
        selected_pages = len(self.checked_items)
        self.total_pages_var.set(f"取得ページ総数: {total_pages}")
        self.selected_pages_var.set(f"選択: {selected_pages}/{visible_pages}")

        # フィルターエリアと出力ボタンを有効化
        self.enable_filter_area()
        self.apply_filter_button.configure(state='normal')
        if self.gallery_data:
            self.output_button.configure(state='normal')
            self.torrent_manager_button.configure(state='normal')
        
        yview = self.tree.yview()
        selected_items = self.tree.selection()

        current_items = {self.tree.item(item, 'values')[9]: item 
                        for item in self.tree.get_children() 
                        if len(self.tree.item(item, 'values')) > 9}

        for idx, item_data in enumerate(self.gallery_data):
            if not item_data or not item_data.get("url"):
                continue

            gallery_url = item_data.get("url")

            values = [
                "✓" if gallery_url in self.checked_items else "",  # Select列
                str(idx + 1),  # Number列（1から始まる連番）
                item_data.get("title", "N/A"),
                item_data.get("genre", "N/A"),
                item_data.get("date", "N/A"),
                item_data.get("pages", "N/A"),
                f"{item_data.get('favorite_score', 'N/A')}",
                item_data.get("uploader", "N/A"),
                ", ".join(item_data.get("tags", []))[:100] + ("..." if len(item_data.get("tags", [])) > 3 else ""),
                gallery_url,
                "あり" if item_data.get('torrent') else "なし",
                item_data.get("thumbnail", "N/A")
            ]
            
            if gallery_url in current_items:
                item_id = current_items[gallery_url]
                self.tree.item(item_id, values=values)
                if gallery_url in self.checked_items:
                    self.tree.item(item_id, tags=("checked",))
            else:
                item_id = self.tree.insert("", tk.END, values=values)
                if gallery_url in self.checked_items:
                    self.tree.item(item_id, tags=("checked",))

        # 表示数を更新（解析完了時）
        self.update_status()
                
        try:
            if yview and len(yview) == 2:
                self.tree.yview_moveto(yview[0])
            if selected_items:
                self.tree.selection_set(selected_items)
        except Exception:
            pass

    def on_tree_double_click(self, event):
        """Handle double-clicks on the Treeview to open gallery URLs."""
        item_id = self.tree.focus()
        if not item_id: return
        column_id_str = self.tree.identify_column(event.x)

        if column_id_str == '#8': # URL column
             try:
                 item_values = self.tree.item(item_id, 'values')
                 if item_values and len(item_values) > 7:
                     url = item_values[7]
                     if url and url.startswith('http'):
                         self.log(f"ブラウザでURLを開きます: {url}")
                         webbrowser.open_new_tab(url)
             except Exception as e:
                 self.log(f"URLを開けません: {e}")

    def on_tree_motion(self, event):
        """Handle mouse motion over the Treeview"""
        # サムネイル取得が無効化されている場合は何もしない
        if self.disable_thumb_var.get():
            return

        region = self.tree.identify("region", event.x, event.y)
        item_id = self.tree.identify_row(event.y)
        column_id_str = self.tree.identify_column(event.x)

        if region == "cell" and item_id:
            # タイトル列またはサムネイルURL列の場合
            column_name = self.tree.column(column_id_str, "id")
            if column_name in ("Title", "ThumbnailURL"):  # Title or ThumbnailURL column
                try:
                    item_values = self.tree.item(item_id, 'values')
                    column_index = self.tree["columns"].index("ThumbnailURL")
                    if item_values and len(item_values) > column_index:
                        thumb_url = item_values[column_index]  # Get ThumbnailURL by column name
                        if thumb_url and thumb_url.startswith('http'):
                            # 同じURLのポップアップが表示されている場合はスキップ
                            if (self.thumbnail_popup and self.thumbnail_popup.winfo_exists() and 
                                hasattr(self.thumbnail_popup, "current_url") and 
                                self.thumbnail_popup.current_url == thumb_url):
                                return
                                
                            # キャッシュにある場合は即時表示、なければダウンロードキューに追加
                            self._cancel_pending_timers()
                            self.hide_thumbnail_popup()
                            self._pending_thumb_url = thumb_url
                            self._pending_thumb_x = event.x_root
                            self._pending_thumb_y = event.y_root
                            
                            if thumb_url in self.thumbnail_cache:
                                self._show_popup_after_id = self.root.after(100, self._trigger_show_thumbnail_popup)
                            else:
                                self.thumbnail_queue.put(thumb_url)
                                self._show_popup_after_id = self.root.after(350, self._trigger_show_thumbnail_popup)
                            return
                except Exception as e:
                    self.log(f"サムネイル表示エラー: {e}")
                    pass

        self._cancel_pending_timers(cancel_show=True)
        self.hide_thumbnail_popup(delay=100)

    def _cancel_pending_timers(self, cancel_show=True, cancel_hide=True):
         if cancel_show and hasattr(self, '_show_popup_after_id'):
             after_id = getattr(self, '_show_popup_after_id', None)
             if after_id:
                 try: self.root.after_cancel(after_id)
                 except: pass
             if hasattr(self, '_pending_thumb_url'): del self._pending_thumb_url
             if hasattr(self, '_pending_thumb_x'): del self._pending_thumb_x
             if hasattr(self, '_pending_thumb_y'): del self._pending_thumb_y
             if hasattr(self, '_show_popup_after_id'): del self._show_popup_after_id
         if cancel_hide and hasattr(self, '_hide_popup_after_id'):
             after_id = getattr(self, '_hide_popup_after_id', None)
             if after_id:
                 try: self.root.after_cancel(after_id)
                 except: pass
             if hasattr(self, '_hide_popup_after_id'): del self._hide_popup_after_id

    def _trigger_show_thumbnail_popup(self):
        if hasattr(self, '_pending_thumb_url'):
            url = getattr(self, '_pending_thumb_url', None)
            x = getattr(self, '_pending_thumb_x', None)
            y = getattr(self, '_pending_thumb_y', None)
            if hasattr(self, '_pending_thumb_url'): del self._pending_thumb_url
            if hasattr(self, '_pending_thumb_x'): del self._pending_thumb_x
            if hasattr(self, '_pending_thumb_y'): del self._pending_thumb_y
            if hasattr(self, '_show_popup_after_id'): del self._show_popup_after_id
            if url and x is not None and y is not None:
                self.show_thumbnail_popup(url, x, y)

    def show_thumbnail_popup(self, url, x, y):
        """サムネイルポップアップを表示"""
        self.hide_thumbnail_popup()
        
        # ポップアップウィンドウの作成
        self.thumbnail_popup = tk.Toplevel(self.root)
        self.thumbnail_popup.overrideredirect(True)
        self.thumbnail_popup.geometry(f"+{x+15}+{y+10}")
        self.thumbnail_popup.attributes("-topmost", True)
        self.thumbnail_popup.current_url = url
        
        # ポップアップフレームの作成
        popup_frame = ttk.Frame(self.thumbnail_popup, borderwidth=1, relief="solid")
        popup_frame.pack(fill=tk.BOTH, expand=True)
        
        # キャッシュチェック
        if url in self.thumbnail_cache:
            cached_data = self.thumbnail_cache[url]
            if cached_data:
                try:
                    cached_data.seek(0)
                    image = Image.open(cached_data)
                    max_width, max_height = 300, 400
                    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    self.thumbnail_image = ImageTk.PhotoImage(image)
                    image_label = ttk.Label(popup_frame, image=self.thumbnail_image)
                    image_label.pack()
                    popup_frame.bind("<Leave>", lambda e: self.hide_thumbnail_popup(delay=150))
                except Exception as e:
                    self._update_thumbnail_popup_content(None, popup_frame, error=f"表示エラー: {e}")
            else:
                self._update_thumbnail_popup_content(None, popup_frame, error="キャッシュ済エラー")
        else:
            # 読み込み中表示
            loading_label = ttk.Label(popup_frame, text="読込中...", padding=5)
            loading_label.pack()
            self.thumbnail_popup.update_idletasks()
            
            # 非同期でサムネイル取得
            thread = threading.Thread(target=self._fetch_and_display_thumbnail_on_hover, 
                                   args=(url, loading_label, popup_frame), 
                                   daemon=True)
            thread.start()

    def _fetch_and_display_thumbnail_on_hover(self, url, placeholder_widget, parent_widget):
        """ホバー時のサムネイル取得と表示を処理"""
        
        try:
            # サムネイル取得
            response = self.session.get(url, timeout=5, stream=True)
            response.raise_for_status()
            image_data = io.BytesIO(response.content)
            
            # 画像の検証と最適化
            try:
                image = Image.open(image_data)
                image.verify()
                image_data.seek(0)
                
                # 画像をメモリ効率の良いサイズに変換
                image = Image.open(image_data)
                image.thumbnail((300, 400), Image.Resampling.LANCZOS)
                optimized_data = io.BytesIO()
                image.save(optimized_data, format=image.format, optimize=True)
                optimized_data.seek(0)
                
                # キャッシュに保存
                self.thumbnail_cache[url] = optimized_data
                
                # GUIスレッドで表示
                self.root.after(0, lambda: self._display_optimized_thumbnail(optimized_data, placeholder_widget, parent_widget))
                
            except Exception as e:
                self.log(f"サムネイル検証/最適化エラー ({url}): {e}")
                self.thumbnail_cache[url] = None
                self.root.after(0, lambda: self._update_thumbnail_popup_content(placeholder_widget, parent_widget, error="画像処理エラー"))
                
        except Exception as e:
            self.log(f"サムネイル取得エラー ({url}): {e}")
            self.thumbnail_cache[url] = None
            self.root.after(0, lambda: self._update_thumbnail_popup_content(placeholder_widget, parent_widget, error="取得エラー"))

    def _display_optimized_thumbnail(self, image_data, placeholder_widget, parent_widget):
        """最適化されたサムネイルを表示"""
        try:
            if not parent_widget.winfo_exists(): return
            
            # プレースホルダーを削除
            if placeholder_widget: placeholder_widget.pack_forget()
            
            # 画像を表示
            image = Image.open(image_data)
            self.thumbnail_image = ImageTk.PhotoImage(image)
            image_label = ttk.Label(parent_widget, image=self.thumbnail_image)
            image_label.pack()
            
            # マウスイベントを設定
            parent_widget.bind("<Leave>", lambda e: self.hide_thumbnail_popup(delay=150))
            
        except Exception as e:
            # サムネイル表示エラーは無視（デバッグログに表示しない）
            self._update_thumbnail_popup_content(placeholder_widget, parent_widget, error="表示エラー")

    def _update_thumbnail_popup_content(self, placeholder_widget, parent_widget, error="エラー"):
         try:
             if not parent_widget.winfo_exists(): return
             if placeholder_widget: placeholder_widget.pack_forget()
             error_label = ttk.Label(parent_widget, text=error, padding=5, foreground="red")
             error_label.pack()
             self._cancel_pending_timers(cancel_show=False, cancel_hide=True)
             self._hide_popup_after_id = self.root.after(1500, self.hide_thumbnail_popup)
         except Exception: pass

    def hide_thumbnail_popup(self, event=None, delay=0):
        self._cancel_pending_timers(cancel_show=True)
        def _destroy():
            self._cancel_pending_timers(cancel_show=False, cancel_hide=True)
            if self.thumbnail_popup and self.thumbnail_popup.winfo_exists():
                self.thumbnail_popup.destroy()
            self.thumbnail_popup = None
            self.thumbnail_image = None
        if delay > 0:
            if not hasattr(self, '_hide_popup_after_id'):
                self._hide_popup_after_id = self.root.after(delay, _destroy)
        else:
             _destroy()

    def save_data(self):
        """データをバックアップ保存"""
        try:
            from datetime import datetime
            
            # タイムスタンプ付きのデフォルトファイル名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f'gallery_backup_{timestamp}.json'
            
            save_data = {
                # ギャラリーデータ（選択状態は保存しない）
                'gallery_data': self.gallery_data,
                # ⭐削除: checked_itemsは保存しない⭐
                'hidden_items': list(self.hidden_items),
                
                # フィルター関連
                'filter_conditions': self.filter_conditions,
                'filter_history': self.filter_history,
                'filter_states': self.filter_states,
                'filter_vars': {
                    'title_whitelist': self.filter_vars['title_whitelist'].get(),
                    'title_blacklist': self.filter_vars['title_blacklist'].get(),
                    'tags_whitelist': self.filter_vars['tags_whitelist'].get(),
                    'tags_blacklist': self.filter_vars['tags_blacklist'].get(),
                    'date_value': self.filter_vars['date_value'].get(),
                    'date_condition': self.filter_vars['date_condition'].get(),
                    'pages_value': self.filter_vars['pages_value'].get(),
                    'pages_condition': self.filter_vars['pages_condition'].get(),
                    'category_whitelist': self.filter_vars['category_whitelist'].get(),
                    'category_blacklist': self.filter_vars['category_blacklist'].get(),
                    'uploader_whitelist': self.filter_vars['uploader_whitelist'].get(),
                    'uploader_blacklist': self.filter_vars['uploader_blacklist'].get(),
                    'number_value': self.filter_vars['number_value'].get(),
                    'number_condition': self.filter_vars['number_condition'].get(),
                    'rating_value': self.filter_vars['rating_value'].get(),
                    'rating_condition': self.filter_vars['rating_condition'].get()
                },
                
                # URL関連
                'last_url': self.last_url_var.get(),
                'last_gallery_id': self.last_gallery_id,
                'last_gallery_token': self.last_gallery_token,
                
                # 設定値
                'settings': {
                    'auto_thumb': self.auto_thumb_var.get(),
                    'thumb_wait': self.thumb_wait_time_var.get(),
                    'cache_size': self.cache_size_var.get(),
                    'page_wait': self.page_wait_time_var.get(),
                    'target_count': self.target_count_var.get(),
                    'skip_count': self.skip_count_var.get(),
                    'disable_thumb': self.disable_thumb_var.get()
                }
            }
            
            file_path = filedialog.asksaveasfilename(
                initialfile=default_filename,
                defaultextension=".json",
                filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")],
                title="バックアップの保存"
            )
            
            # パーサーウィンドウのフォーカスを維持
            self.root.focus_force()
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
                self.log(f"データを保存しました: {file_path}")
                
        except Exception as e:
            self.log(f"保存エラー: {e}")
            messagebox.showerror("エラー", f"保存に失敗しました: {e}", parent=self.root)

    def continue_from_last_url(self):
        """最後のURLから継続"""
        if not self.last_url_var.get():
            self.log("再開可能な解析情報がありません。")
            return
            
        # 確認メッセージを表示
        response = messagebox.askyesnocancel(
            "確認",
            "最後のURLから解析を継続します。\n\n" +
            "「はい」: 現在のデータベースに追加\n" +
            "「いいえ」: データベースをクリアして新規解析\n" +
            "「キャンセル」: 解析を行わない",
            parent=self.root
        )
        
        if response is None:  # キャンセル
            return
            
        if not response:  # いいえ（データベースをクリア）
            self.clear_database_internal()
        else:  # はい（データベースに追加）
            # 選択状態のみリセット
            self.checked_items.clear()
            self.update_status()
            
        # URLを入力フィールドに設定してから解析開始
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, self.last_url_var.get())
        self.start_parsing_internal(self.last_url_var.get())

    def load_data(self):
        """バックアップからデータを読み込み"""
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("JSONファイル", "*.json"), ("すべてのファイル", "*.*")],
                title="バックアップの読み込み"
            )
            
            if file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    save_data = json.load(f)
                
                # ギャラリーデータと選択状態の復元
                self.gallery_data = save_data['gallery_data']
                # ⭐修正: checked_itemsは復元せず、常に空のsetで初期化⭐
                # self.checked_items = set(save_data['checked_items'])  # 削除
                self.checked_items = set()  # 常に空で初期化
                print(f"[DEBUG] Parser: load_data()でchecked_itemsを空に初期化: {self.checked_items}")
                
                self.hidden_items = set(save_data['hidden_items'])
                
                # フィルター関連の復元
                self.filter_conditions = save_data['filter_conditions']
                self.filter_history = save_data.get('filter_history', [])
                self.filter_states = save_data.get('filter_states', {})
                
                # フィルター変数の復元
                if 'filter_vars' in save_data:
                    for key, value in save_data['filter_vars'].items():
                        if key in self.filter_vars:
                            self.filter_vars[key].set(value)
                
                # URL関連の復元
                self.last_url_var.set(save_data.get('last_url', ''))
                self.last_gallery_id = save_data.get('last_gallery_id')
                self.last_gallery_token = save_data.get('last_gallery_token')
                
                # 設定値の復元
                if 'settings' in save_data:
                    settings = save_data['settings']
                    self.auto_thumb_var.set(settings.get('auto_thumb', False))
                    self.thumb_wait_time_var.set(settings.get('thumb_wait', 0.3))
                    self.cache_size_var.set(settings.get('cache_size', 500))
                    self.page_wait_time_var.set(settings.get('page_wait', 2.0))
                    self.target_count_var.set(settings.get('target_count', 10))
                    self.skip_count_var.set(settings.get('skip_count', 0))
                    self.disable_thumb_var.set(settings.get('disable_thumb', False))
                
                # Treeviewの更新
                self._update_result_list()
                self.log(f"データを読み込みました: {file_path}")
                
                # ボタン状態の更新
                if self.gallery_data:
                    self.output_button.configure(
                        text="解析結果を出力",
                        state=tk.NORMAL,
                        command=self.export_results
                    )
                    self.enable_filter_area()
                    self.apply_filter_button.configure(state='normal')
                
        except Exception as e:
            self.log(f"読み込みエラー: {e}")
            messagebox.showerror("エラー", f"読み込みに失敗しました: {e}", parent=self.root)

    def toggle_item_selection(self, item_id):
        """アイテムのチェック状態を切り替え"""
        if not item_id:
            return
        
        self.log(f"[DEBUG] toggle_item_selection: item_id={item_id}")
        self.log(f"[DEBUG] 現在のchecked_items: {self.checked_items}")
            
        if item_id in self.checked_items:
            self.checked_items.discard(item_id)
            self.tree.set(item_id, "Select", "")
            self.tree.item(item_id, tags=())
            self.log(f"[DEBUG] チェック解除: {item_id}")
        else:
            self.checked_items.add(item_id)
            self.tree.set(item_id, "Select", "✓")
            self.tree.item(item_id, tags=("checked",))
            self.log(f"[DEBUG] チェック設定: {item_id}")
        
        # チェック状態の更新
        visible_pages = len(self.tree.get_children())
        selected_pages = len(self.checked_items)
        self.selected_pages_var.set(f"選択: {selected_pages}/{visible_pages}")
        self.log(f"[DEBUG] 更新後のchecked_items: {self.checked_items}")

    def toggle_selected_items(self, event=None):
        """選択された項目のチェック状態を切り替え"""
        if not self.tree.selection():
            return
            
        for item in self.tree.selection():
            self.toggle_item_selection(item)

    def show_context_menu(self, event):
        """右クリックメニューを表示（重複メニュー項目を修正）"""
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        
        if region == "cell" and item:
            # 現在の選択を保存
            self.tree.selection_set(item)
            column_name = self.tree.column(column, "id")
            
            # Select列とNumber列以外の場合
            if column_name not in ["Select", "Number"]:
                menu = None
                if column_name == "Genre":  # カテゴリ列
                    menu = tk.Menu(self.root, tearoff=0)
                    menu.add_command(label="除外", command=lambda: self.filter_category("exclude"))
                    menu.add_command(label="抽出", command=lambda: self.filter_category("include"))
                    menu.add_separator()
                    menu.add_command(label="コピー", command=lambda: self.copy_to_clipboard(item, column_name))
                elif column_name == "Uploader":  # Uploader列
                    menu = tk.Menu(self.root, tearoff=0)
                    menu.add_command(label="除外", command=lambda: self.filter_uploader("exclude"))
                    menu.add_command(label="抽出", command=lambda: self.filter_uploader("include"))
                    menu.add_separator()
                    menu.add_command(label="コピー", command=lambda: self.copy_to_clipboard(item, column_name))
                elif column_name == "Rating":  # Rating列
                    menu = tk.Menu(self.root, tearoff=0)
                    menu.add_command(label="除外", command=lambda: self.filter_rating("exclude"))
                    menu.add_command(label="抽出", command=lambda: self.filter_rating("include"))
                    menu.add_separator()
                    menu.add_command(label="コピー", command=lambda: self.copy_to_clipboard(item, column_name))
                else:
                    # 通常のコピーメニュー
                    menu = tk.Menu(self.root, tearoff=0)
                    menu.add_command(label="コピー", command=lambda: self.copy_to_clipboard(item, column_name))

                if menu:
                    menu.post(event.x_root, event.y_root)

    def copy_to_clipboard(self, item, column_name):
        """選択したセルの内容をクリップボードにコピー"""
        try:
            column_index = self.tree["columns"].index(column_name)
            value = self.tree.item(item)['values'][column_index]
            self.root.clipboard_clear()
            self.root.clipboard_append(str(value))
            self.log(f"{column_name}の内容をクリップボードにコピーしました")
        except Exception as e:
            self.log(f"コピーエラー: {e}")

    def apply_filters(self):
        """フィルターを適用"""
        # 全アイテムを一旦表示
        for item in self.hidden_items:
            self.tree.reattach(item, '', 'end')
        self.hidden_items.clear()

        # フィルタリング実行
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            category = values[2]  # Genre列
            uploader = values[6]  # Uploader列

            should_hide = False

            # カテゴリフィルター
            if self.filter_conditions['category']['exclude'] and category == self.filter_conditions['category']['exclude']:
                should_hide = True
            elif self.filter_conditions['category']['include'] and category != self.filter_conditions['category']['include']:
                should_hide = True

            # Uploaderフィルター
            if self.filter_conditions['uploader']['exclude'] and uploader == self.filter_conditions['uploader']['exclude']:
                should_hide = True
            elif self.filter_conditions['uploader']['include'] and uploader != self.filter_conditions['uploader']['include']:
                should_hide = True

            if should_hide:
                self.tree.detach(item)
                self.hidden_items.add(item)

        self.update_status()

    def apply_filter(self, column_index, value, mode):
        """フィルターを適用（状態を記録）"""
        filter_info = {
            'column_index': column_index,
            'value': value,
            'mode': mode,
            'affected_items': set()
        }
        
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            if len(values) > column_index:
                item_value = str(values[column_index])
                
                # フィルター条件に一致するかチェック
                if mode == "exclude" and item_value == value:
                    self.tree.detach(item)
                    self.hidden_items.add(item)
                    filter_info['affected_items'].add(item)
                elif mode == "include" and item_value != value:
                    self.tree.detach(item)
                    self.hidden_items.add(item)
                    filter_info['affected_items'].add(item)

        # フィルター履歴に追加
        self.filter_history.append(filter_info)
        self.update_status()

    def filter_category(self, mode):
        """カテゴリによるフィルタリング"""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        # 選択されたカテゴリを取得
        item = selected_items[0]
        genre_index = self.tree["columns"].index("Genre")
        category = self.tree.item(item)['values'][genre_index]  # Genre列

        # フィルタ条件を更新
        if mode == "exclude":
            self.filter_conditions['category']['exclude'] = category
            self.filter_conditions['category']['include'] = None
            self.log(f"カテゴリ '{category}' を除外")
        else:  # include
            self.filter_conditions['category']['include'] = category
            self.filter_conditions['category']['exclude'] = None
            self.log(f"カテゴリ '{category}' を抽出")

        # 共通フィルタリング関数を呼び出し
        self.apply_filter(genre_index, category, mode)
        self.update_status()

    def filter_uploader(self, mode):
        """Uploaderによるフィルタリング"""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        # 選択されたUploaderを取得
        item = selected_items[0]
        uploader_index = self.tree["columns"].index("Uploader")
        uploader = self.tree.item(item)['values'][uploader_index]  # Uploader列

        # フィルタ条件を更新
        if mode == "exclude":
            self.filter_conditions['uploader']['exclude'] = uploader
            self.filter_conditions['uploader']['include'] = None
            self.log(f"Uploader '{uploader}' を除外")
        else:  # include
            self.filter_conditions['uploader']['include'] = uploader
            self.filter_conditions['uploader']['exclude'] = None
            self.log(f"Uploader '{uploader}' を抽出")

        # 共通フィルタリング関数を呼び出し
        self.apply_filter(uploader_index, uploader, mode)
        self.update_status()

    def validate_date(self, value):
        """日付入力の検証（YYYY-MM-DD HH形式）"""
        if not value or value == "例: 2024-01-01":  # 空またはプレースホルダーの場合は許可
            return True
        
        import re
        # 数字のみ、または年月日時の各部分を入力可能に
        if re.match(r'^\d{0,4}$', value):  # 年の入力中
            return True
        if re.match(r'^\d{4}-\d{0,2}$', value):  # 月の入力中
            return True
        if re.match(r'^\d{4}-\d{1,2}-\d{0,2}$', value):  # 日の入力中
            return True
        if re.match(r'^\d{4}-\d{1,2}-\d{1,2} \d{0,2}$', value):  # 時の入力中
            return True
            
        # 完成形のチェック
        if re.match(r'^\d{4}(-\d{1,2}(-\d{1,2}( \d{1,2})?)?)?$', value):
            try:
                parts = value.split('-')
                if len(parts) >= 1:
                    year = int(parts[0])
                    if not (1900 <= year <= 2100):
                        return False
                if len(parts) >= 2:
                    month = int(parts[1])
                    if not (1 <= month <= 12):
                        return False
                if len(parts) >= 3:
                    day_parts = parts[2].split()
                    day = int(day_parts[0])
                    if not (1 <= day <= 31):
                        return False
                    if len(day_parts) > 1:
                        hour = int(day_parts[1])
                        if not (0 <= hour <= 23):
                            return False
                return True
            except ValueError:
                return False
        return False

    def on_date_entry_focus_in(self, event):
        """日付入力フィールドにフォーカスが当たった時の処理"""
        current_text = self.date_entry.get()
        if current_text.startswith("例:"):
            self.date_entry.delete(0, tk.END)
            self.date_entry.configure(foreground='black')

    def on_date_entry_focus_out(self, event):
        """日付入力フィールドからフォーカスが外れた時の処理"""
        if not self.date_entry.get():
            self.date_entry.insert(0, "例: 2025-07-07 7")
            self.date_entry.configure(foreground='gray')

    def format_filter_date(self, date_str):
        """フィルター用の日付を整形"""
        if not date_str or date_str.startswith("例:"):
            return None
            
        try:
            # 入力パターンの判定と処理
            parts = date_str.split('-')
            if len(parts) == 1:  # 年のみ (例: 2024)
                year = int(parts[0])
                return f"{year:04d}-01-01 00:00"
                
            elif len(parts) == 2:  # 年と月 (例: 2024-1)
                year = int(parts[0])
                month = int(parts[1])
                return f"{year:04d}-{month:02d}-01 00:00"
                
            elif len(parts) == 3:  # 年月日 (例: 2024-1-10) または 年月日時 (例: 2024-1-3 12)
                year = int(parts[0])
                month = int(parts[1])
                
                # 日付部分に時間が含まれているかチェック
                if ' ' in parts[2]:
                    day_time = parts[2].split()
                    day = int(day_time[0])
                    hour = int(day_time[1])
                    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:00"
                else:
                    day = int(parts[2])
                    return f"{year:04d}-{month:02d}-{day:02d} 00:00"
                    
        except (ValueError, IndexError):
            return None
        return None

    def disable_filter_area(self):
        """フィルターエリアを無効化"""
        def disable_widgets(container):
            for child in container.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Button, ttk.Combobox)):
                    # 「表示」ボタンは常に有効
                    if child != self.toggle_filter_btn:
                        child.configure(state='disabled')
                elif isinstance(child, ttk.Frame):
                    disable_widgets(child)

        # フィルターエリア全体を無効化（非表示状態でも）
        disable_widgets(self.filter_frame)
        self.apply_filter_button.configure(state='disabled')
        self.clear_filter_input_btn.configure(state='disabled')

    def enable_filter_area(self):
        """フィルターエリアを有効化"""
        def enable_widgets(container):
            for child in container.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.configure(state='normal')
                elif isinstance(child, ttk.Button):
                    child.configure(state='normal')
                elif isinstance(child, ttk.Combobox):
                    child.configure(state='readonly')
                elif isinstance(child, ttk.Frame):
                    enable_widgets(child)

        # フィルターエリア全体を有効化（非表示状態でも）
        enable_widgets(self.filter_frame)
        self.toggle_filter_btn.configure(state='normal')
        self.apply_filter_button.configure(state='normal')
        self.clear_filter_input_btn.configure(state='normal')

    def apply_advanced_filters(self):
        """高度なフィルターを適用"""
        # フィルター条件の取得（カンマと読点で区切り）
        def split_filter_text(text):
            return set(filter(None, re.split(r'[,、]+', text.strip())))
            
        title_white = split_filter_text(self.filter_vars['title_whitelist'].get())
        title_black = split_filter_text(self.filter_vars['title_blacklist'].get())
        tags_white = split_filter_text(self.filter_vars['tags_whitelist'].get())
        tags_black = split_filter_text(self.filter_vars['tags_blacklist'].get())
        
        date_value = self.format_filter_date(self.filter_vars['date_value'].get())
        date_condition = self.filter_vars['date_condition'].get()
        pages_value = self.filter_vars['pages_value'].get()
        pages_condition = self.filter_vars['pages_condition'].get()
        
        # カテゴリとUploaderのフィルター条件
        category_white = split_filter_text(self.filter_vars['category_whitelist'].get())
        category_black = split_filter_text(self.filter_vars['category_blacklist'].get())
        uploader_white = split_filter_text(self.filter_vars['uploader_whitelist'].get())
        uploader_black = split_filter_text(self.filter_vars['uploader_blacklist'].get())
        
        # 番号フィルター条件
        number_value = self.filter_vars['number_value'].get()
        number_condition = self.filter_vars['number_condition'].get()
        
        # 評価フィルター条件
        rating_value = self.filter_vars['rating_value'].get()
        rating_condition = self.filter_vars['rating_condition'].get()

        # 全アイテムを一旦表示
        for item in self.hidden_items:
            self.tree.reattach(item, '', 'end')
        self.hidden_items.clear()

        # フィルタリング実行
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            if len(values) < 12:  # 必要な列数をチェック
                continue
                
            number = values[1]  # Number列
            title = values[2]   # Title列
            category = values[3]  # Genre列
            date = values[4]    # Date列
            pages = values[5]   # Pages列
            rating = values[6]  # Rating列
            uploader = values[7]  # Uploader列
            tags = values[8]    # Tags列

            should_hide = False

            # 番号フィルター
            if number_value and number != 'N/A':
                try:
                    number_num = int(number)
                    number_filter = int(number_value)
                    if number_condition == '以上' and number_num < number_filter:
                        should_hide = True
                    elif number_condition == '以下' and number_num > number_filter:
                        should_hide = True
                except ValueError:
                    pass

            # 評価フィルター
            if rating_value and rating != 'N/A':
                try:
                    rating_num = float(rating)
                    rating_filter = float(rating_value)
                    if rating_condition == '以上' and rating_num < rating_filter:
                        should_hide = True
                    elif rating_condition == '以下' and rating_num > rating_filter:
                        should_hide = True
                except ValueError:
                    pass

            # タイトルフィルター
            if title_white and not any(w.lower() in title.lower() for w in title_white):
                should_hide = True
            if title_black and any(b.lower() in title.lower() for b in title_black):
                should_hide = True

            # カテゴリフィルター
            if category_white and not any(w.lower() in category.lower() for w in category_white):
                should_hide = True
            if category_black and any(b.lower() in category.lower() for b in category_black):
                should_hide = True

            # 日付フィルター
            if date_value and date != 'N/A':
                try:
                    from datetime import datetime
                    item_date = datetime.strptime(date, '%Y-%m-%d %H:%M')
                    filter_date = datetime.strptime(date_value, '%Y-%m-%d %H:%M')
                    if date_condition == '以前' and item_date > filter_date:
                        should_hide = True
                    elif date_condition == '以後' and item_date < filter_date:
                        should_hide = True
                except ValueError:
                    pass

            # ページ数フィルター
            if pages_value and pages != 'N/A':
                try:
                    pages_num = int(pages)
                    pages_filter = int(pages_value)
                    if pages_condition == '以上' and pages_num < pages_filter:
                        should_hide = True
                    elif pages_condition == '以下' and pages_num > pages_filter:
                        should_hide = True
                except ValueError:
                    pass

            # Uploaderフィルター
            if uploader_white and not any(w.lower() in uploader.lower() for w in uploader_white):
                should_hide = True
            if uploader_black and any(b.lower() in uploader.lower() for b in uploader_black):
                should_hide = True

            # タグフィルター
            if tags_white and not any(w.lower() in tags.lower() for w in tags_white):
                should_hide = True
            if tags_black and any(b.lower() in tags.lower() for b in tags_black):
                should_hide = True

            if should_hide:
                self.tree.detach(item)
                self.hidden_items.add(item)

        self.update_status()

    def reset_advanced_filters(self):
        """フィルタリングをリセット（履歴ベース）"""
        # 非表示になっているアイテムをすべて再表示
        for item in list(self.hidden_items):
            if self.tree.exists(item):
                self.tree.reattach(item, '', 'end')
                # チェック状態を維持
                if item in self.checked_items:
                    self.tree.set(item, "Select", "✓")
                    self.tree.item(item, tags=("checked",))

        # フィルター状態をリセット
        self.hidden_items.clear()
        self.filter_history.clear()
        self.filter_conditions = {
            'category': {'exclude': None, 'include': None},
            'uploader': {'exclude': None, 'include': None},
            'rating': {'exclude': None, 'include': None}
        }

        self.update_status()
        self.log("フィルタリングを解除しました")

    def hide_none_ratings(self):
        """評価がNoneのアイテムを非表示にする"""
        self.apply_filter(7, 'N/A', "exclude")  # Rating列
        self.log("評価がNoneのアイテムを非表示にしました")
        self.update_status()

    def show_none_ratings(self):
        """評価がNoneのアイテムを表示する（他のフィルターで非表示になっているものは除く）"""
        # 現在のフィルター条件を確認
        category_exclude = self.filter_conditions['category']['exclude']
        category_include = self.filter_conditions['category']['include']
        uploader_exclude = self.filter_conditions['uploader']['exclude']
        uploader_include = self.filter_conditions['uploader']['include']

        for item in list(self.hidden_items):
            values = self.tree.item(item)['values']
            if values[6] != 'N/A':  # Rating列がN/A以外なら次へ
                continue

            # 他のフィルターに引っかかっていないかチェック
            should_show = True
            if category_exclude and values[2] == category_exclude:
                should_show = False
            if category_include and values[2] != category_include:
                should_show = False
            if uploader_exclude and values[6] == uploader_exclude:
                should_show = False
            if uploader_include and values[6] != uploader_include:
                should_show = False

            if should_show:
                self.tree.reattach(item, '', 'end')
                self.hidden_items.discard(item)

        self.log("評価がNoneのアイテムを表示しました（他のフィルターの影響を除く）")
        self.update_status()

    def update_status(self):
        """ステータスを更新"""
        visible_pages = len(self.tree.get_children())
        selected_pages = len(self.checked_items)
        self.selected_pages_var.set(f"選択: {selected_pages}/{visible_pages}")

    def clear_data(self):
        """データをクリア"""
        if messagebox.askyesno("確認", "本当にすべてのデータをクリアしますか？", parent=self.root):
            self.clear_database_internal()
            self.last_url_var.set("")
            self.continue_button.config(state=tk.DISABLED)
            self.log("データをクリアしました。")
            self.disable_filter_area()  # フィルターエリアを無効化

    def check_all_items(self):
        """すべての項目をチェック"""
        for item in self.tree.get_children():
            self.checked_items.add(item)
            self.tree.set(item, "Select", "✓")
            self.tree.item(item, tags=("checked",))
        # 選択状態の更新
        visible_pages = len(self.tree.get_children())
        self.selected_pages_var.set(f"選択: {visible_pages}/{visible_pages}")

    def uncheck_all_items(self):
        """すべての項目のチェックを解除"""
        self.checked_items.clear()
        for item in self.tree.get_children():
            self.tree.set(item, "Select", "")
            self.tree.item(item, tags=())
        # 選択状態の更新
        visible_pages = len(self.tree.get_children())
        self.selected_pages_var.set(f"選択: 0/{visible_pages}")

    def toggle_filter_area(self):
        """フィルターエリアの表示/非表示を切り替え"""
        if self.filter_visible.get():
            self.filter_frame.pack_forget()
            self.toggle_filter_btn.configure(text="表示▼")
        else:
            self.filter_frame.pack(fill=tk.X, pady=(0, 5))
            self.toggle_filter_btn.configure(text="隠す▲")
        self.filter_visible.set(not self.filter_visible.get())

    def on_tree_click(self, event):
        """Treeviewのクリックイベントを処理"""
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        
        self.log(f"[DEBUG] TreeViewクリック: region={region}, column={column}, item={item}")
        
        if region == "cell" and item:
            # Select列またはタイトル・カテゴリ・投稿日・P数・評価・Uploader・主要タグ列のクリック
            if column in ("#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8"):
                self.log(f"[DEBUG] チェックボックス列クリック: {column}")
                self.toggle_item_selection(item)
                return "break"  # イベントの伝播を停止
            elif column == "#10":  # ギャラリーURL列
                try:
                    item_values = self.tree.item(item, 'values')
                    if item_values and len(item_values) > 9:
                        url = item_values[9]  # URL列のインデックス
                        if url and url.startswith('http'):
                            self.open_url_with_confirmation(url)
                            return "break"
                except Exception as e:
                    self.log(f"URLを開けません: {e}")

    def clear_cache(self):
        """キャッシュをクリア"""
        self.thumbnail_cache.clear()
        self.thumbnail_cache_order.clear()
        self.update_cache_status()
        self.log("サムネイルキャッシュをクリアしました")

    def sort_treeview(self, col):
        """Treeviewの列でソート
        Args:
            col (str): ソートする列の名前
        """
        # 同じ列が選択された場合、ソート順を反転
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        # 現在の項目を取得
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]

        # ソート
        try:
            # 数値列の場合
            if col in ["Number", "Pages", "Rating"]:
                # N/Aは最後にソート
                items.sort(key=lambda x: float(x[0]) if x[0] != 'N/A' else float('inf'), reverse=self.sort_reverse)
            # 日付列の場合
            elif col == "Date":
                from datetime import datetime
                def parse_date(date_str):
                    try:
                        return datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                    except ValueError:
                        return datetime.max
                items.sort(key=lambda x: parse_date(x[0]), reverse=self.sort_reverse)
            # その他の列は文字列としてソート
            else:
                items.sort(key=lambda x: x[0].lower(), reverse=self.sort_reverse)
        except Exception as e:
            self.log(f"ソートエラー: {e}")
            return

        # 項目を並び替え
        for index, (val, item) in enumerate(items):
            try:
                self.tree.move(item, '', index)
                # チェック状態を維持
                if item in self.checked_items:
                    self.tree.item(item, tags=("checked",))
            except tk.TclError:
                continue

        # ヘッダーテキストを更新
        headings_widths = {
            "Select": "✓",
            "Number": "番号",
            "Title": "タイトル",
            "Genre": "カテゴリ",
            "Date": "投稿日",
            "Pages": "P数",
            "Rating": "評価",
            "Uploader": "Uploader",
            "Tags": "主要タグ",
            "URL": "ギャラリーURL",
            "Torrent": "Torrent",
            "ThumbnailURL": "サムネイルURL"
        }
        
        # すべての列のヘッダーを元に戻し、ソート中の列のみ矢印を表示
        for col_name in self.tree["columns"]:
            if col_name == col:
                self.tree.heading(col_name, text=f"{headings_widths[col_name]} {'↓' if self.sort_reverse else '↑'}")
            else:
                self.tree.heading(col_name, text=headings_widths[col_name])

    def update_cache_status(self):
        """キャッシュ状態を更新"""
        cache_limit = self.cache_size_var.get()
        current_cache = len(self.thumbnail_cache)
        self.current_cache_var.set(f"使用中: {current_cache}/{cache_limit}")

    def export_results(self):
        """解析結果を出力する"""
        self.output_to_downloader()

    def filter_rating(self, mode):
        """評価によるフィルタリング"""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        # 選択された評価を取得
        item = selected_items[0]
        rating_index = self.tree["columns"].index("Rating")
        rating = self.tree.item(item)['values'][rating_index]

        # フィルタ条件を更新
        if mode == "exclude":
            self.filter_conditions['rating'] = {'exclude': rating, 'include': None}
            self.log(f"評価 '{rating}' を除外")
        else:  # include
            self.filter_conditions['rating'] = {'include': rating, 'exclude': None}
            self.log(f"評価 '{rating}' を抽出")

        # フィルタリングを適用
        self.apply_filter(rating_index, rating, mode)
        self.update_status()

    def on_disable_thumb_changed(self):
        """サムネイル取得無効化の状態変更時の処理"""
        disabled = self.disable_thumb_var.get()
        
        # 関連するウィジェットの状態を更新
        widgets_to_toggle = [
            self.auto_thumb_check,
            self.thumb_wait_time_spinbox,
            self.cache_size_spinbox,
            self.clear_cache_btn
        ]
        
        for widget in widgets_to_toggle:
            widget.configure(state='disabled' if disabled else 'normal')
        
        if disabled:
            # サムネイル自動取得をOFFにする
            self.auto_thumb_var.set(False)
            self.on_auto_thumb_changed()
            self.log("サムネイル取得を無効化しました")
        else:
            self.log("サムネイル取得を有効化しました")

    def clear_filter_inputs(self):
        """フィルター入力値をクリア"""
        if not messagebox.askyesno("確認", "フィルターの入力値をクリアしますか？", parent=self.root):
            return
            
        self.filter_vars['title_whitelist'].set('')
        self.filter_vars['title_blacklist'].set('')
        self.filter_vars['tags_whitelist'].set('')
        self.filter_vars['tags_blacklist'].set('')
        self.filter_vars['date_value'].set('')
        self.filter_vars['pages_value'].set('')
        self.filter_vars['category_whitelist'].set('')
        self.filter_vars['category_blacklist'].set('')
        self.filter_vars['uploader_whitelist'].set('')
        self.filter_vars['uploader_blacklist'].set('')
        self.filter_vars['number_value'].set('')
        self.filter_vars['number_condition'].set('以上')
        self.filter_vars['rating_value'].set('')
        self.filter_vars['rating_condition'].set('以上')
        self.log("フィルターの入力値をクリアしました")

    def get_column_name_from_menu(self, menu, event):
        """メニューから選択されたカラム名を取得"""
        item = menu.post(event.x_root, event.y_root)
        if item:
            return self.tree.identify_column(item)
        return None

    def copy_current_cell(self, column_name):
        """現在選択されているセルの内容をコピー"""
        selected = self.tree.selection()
        if selected:
            self.copy_to_clipboard(selected[0], column_name)



    def output_to_downloader(self):
        """チェックされたURLをダウンローダーに出力（TreeViewの表示順を保持、URL正規化）"""
        # ⭐デバッグ: checked_itemsの内容を確認⭐
        print(f"[DEBUG] output_to_downloader: checked_items={self.checked_items}")
        print(f"[DEBUG] output_to_downloader: checked_items count={len(self.checked_items)}")
        
        # チェックされたアイテムがあるか確認
        if not self.checked_items:
            messagebox.showwarning("警告", "出力するURLが選択されていません。", parent=self.root)
            return

        # URLが既に出力済みの場合は確認ダイアログを表示
        if self._has_output_urls:
            response = messagebox.askyesno(
                "確認", 
                "既に現在のDBから出力はされています。それでも出力を行いますか？",
                parent=self.root
            )
            if not response:
                return

        # 出力コールバックが設定されているか確認
        if not self.output_urls:
            messagebox.showwarning("警告", "出力先が設定されていません。", parent=self.root)
            return

        # TreeViewの表示順を保持してチェックされたアイテムからURLを取得
        urls = []
        
        # TreeViewの全アイテムを順番に取得（表示順を保持）
        all_items = self.tree.get_children()
        
        # 表示順にチェックされたアイテムのURLを取得
        for item_id in all_items:
            if item_id in self.checked_items:
                values = self.tree.item(item_id)['values']
                if values and len(values) > 9:  # URL列は10番目のカラム（インデックス9）
                    url = values[9]  # 修正：インデックス2（Title）ではなく9（URL）を使用
                    if url and url.strip():
                        # URLを正規化（?inline_set=dm_l を削除）
                        normalized_url = self.normalize_url_for_output(url.strip())
                        urls.append(normalized_url)

        # URLを出力
        if urls:
            try:
                self.output_urls(urls)
                self._has_output_urls = True
                self.log(f"{len(urls)}件のURLを出力しました（TreeViewの表示順を保持、URL正規化済み）。")
                # E-H Downloaderをアクティブにするため、出力成功時のメッセージは表示しない
            except Exception as e:
                self.log(f"URL出力エラー: {str(e)}")
                messagebox.showerror("エラー", f"URLの出力に失敗しました: {str(e)}", parent=self.root)
        else:
            self.log("出力するURLが見つかりませんでした。")
            messagebox.showwarning("警告", "出力するURLが見つかりませんでした。", parent=self.root)

    def open_current_url(self):
        """現在入力されているURLを開く"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("警告", "URLが入力されていません。", parent=self.root)
            return
        self.open_url_with_confirmation(url)

    def open_url_with_confirmation(self, url):
        """URLを確認ダイアログ付きで開く"""
        if not self.url_open_message_shown:
            response = messagebox.askyesno(
                "確認", 
                "外部ブラウザでURLを開きますか？\n\nはい(Y) - 開く\nいいえ(N) - キャンセル", 
                parent=self.root
            )
            if response:
                webbrowser.open_new_tab(url)
                self.url_open_message_shown = True
        else:
            webbrowser.open_new_tab(url)
    
    def _launch_torrent_manager(self):
        """TorrentファイルDLマネージャーを起動"""
        try:
            # 確認ダイアログ
            response = messagebox.askyesno(
                "確認", 
                "現在選択されているギャラリーの中からTorrentファイルをDLマネージャに出力", 
                parent=self.root
            )
            
            if not response:
                return
            
            # チェックが入っているギャラリーを取得
            checked_galleries = self._get_checked_galleries()
            if not checked_galleries:
                messagebox.showwarning("警告", "チェックが入っているギャラリーがありません", parent=self.root)
                return
            
            # Torrentの有無をチェック（簡易版：ギャラリーデータから確認）
            galleries_with_torrent = self._filter_galleries_with_torrent(checked_galleries)
            if not galleries_with_torrent:
                messagebox.showwarning("警告", "チェック済みギャラリーにTorrentファイルがありません", parent=self.root)
                return
            
            self.log(f"Torrentファイルがあるギャラリー: {len(galleries_with_torrent)}件")
            
            # Torrentマネージャーを起動
            from gui.components.torrent_manager import TorrentDownloadManager
            if not hasattr(self, 'torrent_manager'):
                self.torrent_manager = TorrentDownloadManager(self)
            
            # ウィンドウを先に表示（UI要素を初期化）
            self.torrent_manager.show_window()
            
            # データを設定
            self.torrent_manager.set_torrent_data(galleries_with_torrent)
            
        except Exception as e:
            self.log(f"Torrentマネージャー起動エラー: {str(e)}")
            messagebox.showerror("エラー", f"Torrentマネージャーの起動に失敗しました: {str(e)}", parent=self.root)
    
    def _get_checked_galleries(self):
        """チェックが入っているギャラリーを取得（✔がされているもののみ）"""
        checked_galleries = []
        
        try:
            # デバッグ情報を出力
            self.log(f"[DEBUG] checked_items: {self.checked_items}")
            self.log(f"[DEBUG] checked_items数: {len(self.checked_items)}")
            
            # ⭐修正: checked_itemsが空の場合、早期リターン（空配列）⭐
            if not self.checked_items:
                self.log(f"[WARNING] チェック済みアイテムがありません（checked_items is empty）")
                return checked_galleries  # 空配列を返す
            
            # 全TreeViewアイテムをチェック
            all_items = self.tree.get_children()
            self.log(f"[DEBUG] 全TreeViewアイテム数: {len(all_items)}")
            
            for item_id in all_items:
                values = self.tree.item(item_id, 'values')
                self.log(f"[DEBUG] アイテム {item_id}: values={values}")
                if len(values) >= 10:  # URL列（インデックス9）まで必要
                    url = values[9]  # URL列（正しいインデックス）
                    is_checked = item_id in self.checked_items
                    self.log(f"[DEBUG] アイテム {item_id}: URL={url}, チェック状態={is_checked}")
                    
                    # ⭐修正: is_checked=Trueの場合のみ追加（必須条件）⭐
                    if is_checked and url and self._is_valid_gallery_url(url):
                        # タイトル情報を取得
                        title = values[2] if len(values) > 2 else f'Gallery {self._extract_gallery_id(url)}'
                        checked_galleries.append({
                            'source_url': url,
                            'gallery_id': self._extract_gallery_id(url),
                            'title': title
                        })
                        self.log(f"[DEBUG] チェック済みギャラリー追加: {url}")
            
            self.log(f"[DEBUG] 最終チェック済みギャラリー数: {len(checked_galleries)}")
            
        except Exception as e:
            self.log(f"チェック済みギャラリー取得エラー: {str(e)}")
            import traceback
            self.log(f"エラー詳細: {traceback.format_exc()}")
        
        return checked_galleries
    
    def _is_valid_gallery_url(self, url):
        """有効なギャラリーURLかチェック"""
        return 'e-hentai.org/g/' in url or 'exhentai.org/g/' in url
    
    def _extract_gallery_id(self, url):
        """URLからギャラリーIDを抽出"""
        try:
            match = re.search(r'/g/(\d+)/', url)
            if match:
                return int(match.group(1))
        except:
            pass
        return None
    
    def _filter_galleries_with_torrent(self, galleries):
        """Torrentファイルがあるギャラリーのみをフィルタリング"""
        galleries_with_torrent = []
        
        try:
            for gallery in galleries:
                # ギャラリーデータからTorrent情報を確認
                if self._has_torrent_in_gallery_data(gallery['source_url']):
                    galleries_with_torrent.append(gallery)
                    self.log(f"[DEBUG] Torrentあり: {gallery['source_url']}")
                else:
                    self.log(f"[DEBUG] Torrentなし: {gallery['source_url']}")
        except Exception as e:
            self.log(f"Torrentフィルタリングエラー: {str(e)}")
        
        return galleries_with_torrent
    
    def _has_torrent_in_gallery_data(self, url):
        """ギャラリーデータにTorrent情報があるかチェック"""
        try:
            # ギャラリーデータから該当URLのエントリを検索
            for gallery_data in self.gallery_data:
                if gallery_data.get('url') == url:
                    # Torrent情報があるかチェック
                    torrent_info = gallery_data.get('torrent')
                    if torrent_info and torrent_info.strip():
                        return True
            return False
        except Exception as e:
            self.log(f"Torrent情報チェックエラー: {str(e)}")
            return False

class ToolTip:
    """ツールチップウィジェット"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.id = None
        self.tw = None

    def enter(self, event=None):
        """マウスが入ったときの処理"""
        self.schedule()

    def leave(self, event=None):
        """マウスが出たときの処理"""
        self.unschedule()
        self.hide()

    def schedule(self):
        """ツールチップ表示のスケジュール"""
        self.unschedule()
        self.id = self.widget.after(500, self.show)

    def unschedule(self):
        """スケジュールのキャンセル"""
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def show(self):
        """ツールチップを表示"""
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + self.widget.winfo_width()
        y = y + cy + self.widget.winfo_rooty() + 25
        
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        label = ttk.Label(self.tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide(self):
        """ツールチップを非表示"""
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except ImportError: pass
    except Exception as e: print(f"DPI Awareness Error: {e}")

    root = tk.Tk()
    app = SearchResultParser(root)
    root.mainloop()
