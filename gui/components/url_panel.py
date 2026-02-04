# -*- coding: utf-8 -*-
"""
URL panel component for EH Downloader
"""


import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import json
import re
import webbrowser
from config.settings import *
from config.constants import *
from config.settings import ToolTip
from core.models.download_session import DownloadStatus

class EHDownloaderUrlPanel:
    def __init__(self, parent):
        self.parent = parent
        
        # パーサー設定のデフォルト値
        self.parser_settings = {
            "target_count": 25,
            "page_wait_time": 2.0,
            "auto_thumb": False,
            "thumb_wait_time": 0.3,
            "cache_size": 500,
            "disable_thumb": False,
            "parse_mode": "DBに追加",
            "window_geometry": "1x1+0+0",
            "window_state": "normal"
        }
        
        # URL背景色更新の安定化
        self.url_bg_update_pending = {}  # 更新待ちのURL
        self.url_bg_update_timer = None  # 更新タイマー
        
        # URLパネル用のTIPSテキスト
        self.url_tooltip_texts = {
            'parser_button': 'E-Hentaiの検索結果ページからギャラリーURLを自動抽出してDLリストを作成します。検索結果URL、取得数、ページ待機時間などを設定できます。',
            'url_text': 'ダウンロードするギャラリーのURLを1行に1つずつ入力してください。E-HentaiのギャラリーページのURLを入力します。',
            'backup_load': '以前に保存したバックアップファイルから設定とURLリストを復元します。',
            'backup_save': '現在の設定とURLリストをバックアップファイルとして保存します。',
            'url_parse': 'URLリストの解析を実行し、各URLの有効性をチェックします。',
            'parse_output': '解析結果をテキストファイルとして出力します。',
            'torrent_manager': 'Torrentファイルのダウンロードを管理します。E-HentaiのTorrent機能を使用する場合に便利です。',
            'continue_parse': '前回の解析を続行します。中断された解析から再開できます。'
        }
        
    def create_url_panel(self, parent_pane):
        """URL入力パネルを作成"""
        url_frame = ttk.LabelFrame(parent_pane, text="DLリスト（URL）")
        parent_pane.add(url_frame)
        url_frame.grid_rowconfigure(1, weight=1)
        url_frame.grid_columnconfigure(0, weight=1)

        parser_button = ttk.Button(url_frame, text="検索結果からDLリストの作成", command=self.parent.launch_parser)
        parser_button.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        ToolTip(parser_button, self.url_tooltip_texts['parser_button'])

        self.url_text = tk.Text(url_frame, wrap="none", width=49, height=15, undo=True)  # 幅を120px増加（37→49）
        self.url_text.grid(row=1, column=0, sticky="nsew")
        ToolTip(self.url_text, self.url_tooltip_texts['url_text'])

        # ドラッグ&ドロップ機能
        try:
            import tkinterdnd2
            if hasattr(tkinterdnd2, 'DND_FILES') and hasattr(self.url_text, 'drop_target_register'):
                self.url_text.drop_target_register(tkinterdnd2.DND_FILES, tkinterdnd2.DND_TEXT)
                self.url_text.dnd_bind('<<Drop>>', self.parent._handle_drop)
        except Exception as e:
            print(f"DnD initialization failed: {e}")

        url_scrollbar_y = ttk.Scrollbar(url_frame, orient="vertical", command=self.url_text.yview)
        url_scrollbar_y.grid(row=1, column=1, sticky="ns")
        self.url_text.config(yscrollcommand=url_scrollbar_y.set)

        url_scrollbar_x = ttk.Scrollbar(url_frame, orient="horizontal", command=self.url_text.xview)
        url_scrollbar_x.grid(row=2, column=0, sticky="ew")
        self.url_text.config(xscrollcommand=url_scrollbar_x.set)

        # コンテキストメニュー
        self.url_text_context_menu = tk.Menu(self.parent.root, tearoff=0)
        self.url_text_context_menu.add_command(label="切り取り", command=self.cut_url)
        self.url_text_context_menu.add_command(label="コピー", command=self.copy_url)
        self.url_text_context_menu.add_command(label="貼り付け", command=self.paste_url)
        self.url_text_context_menu.add_separator()
        self.url_text_context_menu.add_command(label="選択行を削除", command=self.delete_selected_lines)
        self.url_text_context_menu.add_command(label="すべて選択", command=lambda: self.url_text.tag_add(tk.SEL, "1.0", tk.END))
        self.url_text_context_menu.add_separator()
        self.url_text_context_menu.add_command(label="選択したURLを開く", command=self.open_url_from_context)

        self._setup_url_text_bindings()
    

    
    def open_url_from_context(self):
        """コンテキストメニューからURLを開く"""
        try:
            if self.url_text.tag_ranges(tk.SEL):
                selected_text = self.url_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
                if selected_text:
                    webbrowser.open(selected_text)
                    self.parent.log(f"ブラウザでURLを開きました: {selected_text}")
        except Exception as e:
            self.parent.log(f"URLを開くエラー: {e}", "error")
    
    def _show_url_context_menu(self, event):
        """URLコンテキストメニューを表示"""
        try:
            self.url_text_context_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            self.parent.log(f"コンテキストメニューエラー: {e}", "error")
        
    def _setup_url_text_bindings(self):
        """URLテキストのバインディング設定"""
        # 右クリックコンテキストメニュー
        self.url_text.bind("<Button-3>", self._show_url_context_menu)
        
        # 左クリック（選択時のプレースホルダー削除）
        self.url_text.bind("<Button-1>", self._on_url_click)
        
        # フォーカスイン・アウト
        self.url_text.bind("<FocusIn>", self._on_url_text_focus_in)
        self.url_text.bind("<FocusOut>", self._on_url_text_focus_out)
        
        # キー入力
        self.url_text.bind("<KeyPress>", self._on_url_keypress)
        
        # テキスト変更監視
        self.url_text.bind("<<Modified>>", self._on_url_text_modified)
        
        # キーバインド
        self.url_text.bind("<Control-z>", lambda e: self.url_text.edit_undo())
        self.url_text.bind("<Control-y>", lambda e: self.url_text.edit_redo())
        self.url_text.bind("<Control-a>", self._select_all_url_text)
        
        # コンテキストメニューの作成
        if not hasattr(self, 'url_text_context_menu'):
            self.url_text_context_menu = tk.Menu(self.parent.root, tearoff=0)
            self.url_text_context_menu.add_command(label="切り取り", command=self.cut_url)
            self.url_text_context_menu.add_command(label="コピー", command=self.copy_url)
            self.url_text_context_menu.add_command(label="貼り付け", command=self.paste_url)
            self.url_text_context_menu.add_separator()
            self.url_text_context_menu.add_command(label="選択行を削除", command=self.delete_selected_lines)
            self.url_text_context_menu.add_command(label="すべて選択", command=lambda: self.url_text.tag_add(tk.SEL, "1.0", tk.END))
            self.url_text_context_menu.add_separator()
            self.url_text_context_menu.add_command(label="選択したURLを開く", command=self.open_url_from_context)

    def _on_url_click(self, event):
        """URLテキストクリック時の処理"""
        # クリック位置にカーソルを移動する前にプレースホルダをクリア
        if hasattr(self.url_text, 'placeholder_active') and self.url_text.placeholder_active:
            self._clear_url_placeholder()

    def _on_url_keypress(self, event):
        """URLテキストキー押下時の処理"""
        # キー入力前にプレースホルダをクリア
        if hasattr(self.url_text, 'placeholder_active') and self.url_text.placeholder_active:
            self._clear_url_placeholder()
        
        # ダウンロード進行中の行の編集を制限
        if self._is_editing_restricted_line(event):
            return "break"  # イベントをキャンセル（入力無効）

    def _on_url_text_focus_in(self, event):
        """URLテキストフォーカスイン時の処理"""
        # プレースホルダーがアクティブな場合はクリア
        if hasattr(self.url_text, 'placeholder_active') and self.url_text.placeholder_active:
            self._clear_url_placeholder()

    def _on_url_text_focus_out(self, event):
        """URLテキストフォーカスアウト時の処理"""
        # テキストが空の場合のみプレースホルダを再設定
        content = self.url_text.get("1.0", tk.END).strip()
        if not content:
            self._setup_url_placeholder()

    def _clear_url_placeholder(self):
        """URLプレースホルダーをクリア"""
        if hasattr(self, 'url_text') and hasattr(self.url_text, 'placeholder_active') and self.url_text.placeholder_active:
            self.url_text.delete("1.0", tk.END)
            self.url_text.config(fg='black')
            self.url_text.placeholder_active = False

    def _is_editing_restricted_line(self, event):
        """編集制限が必要な行かどうかをチェック"""
        try:
            # 現在のカーソル位置を取得
            index = self.url_text.index(tk.INSERT)
            line, col = map(int, index.split('.'))
            
            # ダウンロードが実行中でない場合は制限なし
            if not hasattr(self.parent, 'downloader_core') or not self.parent.downloader_core.state_manager.is_download_running():
                return False
            
            # 現在処理中のURLの行番号を取得
            current_url_index = self.parent.downloader_core.state_manager.get_current_url_index()

            # 現在の行が処理済みまたは処理中の場合は編集禁止
            if line <= current_url_index + 1:  # +1は行番号が1から始まるため
                # エラー状態のURLは編集可能にする
                if line == current_url_index + 1:  # 現在のURLの行
                    # 現在のURLの状態をチェック
                    current_url = self._get_url_at_line(line)
                    if current_url:
                        normalized_url = self.parent.normalize_url(current_url)
                        url_status = self.parent.downloader_core.state_manager.download_state.url_status.get(normalized_url, DownloadStatus.WAITING)
                        # 文字列→Enum変換（後方互換）
                        if not isinstance(url_status, DownloadStatus):
                            try:
                                url_status = DownloadStatus(url_status)
                            except Exception:
                                url_status = DownloadStatus.WAITING
                        if url_status == DownloadStatus.ERROR:
                            return False  # エラー状態のURLは編集可能
                return True

            return False
        except Exception as e:
            self.parent.log(f"編集制限チェックエラー: {e}", "error")
            return False

    def _get_url_at_line(self, line):
        """指定された行のURLを取得"""
        try:
            line_text = self.url_text.get(f"{line}.0", f"{line}.end")
            return line_text.strip()
        except Exception:
            return None

    def _check_url_placeholder(self):
        """URLプレースホルダーの状態をチェック（無効化）"""
        # プレースホルダー機能を削除したため何もしない
        pass

    def _setup_url_placeholder(self):
        """URLテキストのプレースホルダー設定（削除）"""
        # プレースホルダー機能を削除
        pass

    def _load_settings_from_file(self, file_path):
        """指定されたファイルから設定を読み込み、GUIに反映"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # 設定をGUIに反映
            for key in self.STATE_KEYS:
                if key in settings and hasattr(self, key):
                    if isinstance(getattr(self, key), (tk.StringVar, tk.BooleanVar, tk.IntVar)):
                        getattr(self, key).set(settings[key])
                    else:
                        setattr(self, key, settings[key])
            
            # 特別な処理が必要な項目
            if 'window_geometry' in settings:
                self.parent.root.geometry(settings['window_geometry'])
            
            if 'sash_pos_v' in settings and hasattr(self, 'main_v_pane'):
                self.main_v_pane.sashpos(0, settings['sash_pos_v'])
            
            if 'sash_pos_h' in settings and hasattr(self, 'top_h_pane'):
                self.top_h_pane.sashpos(0, settings['sash_pos_h'])
            
            # 文字列変換ルールの復元
            if 'string_conversion_rules' in settings:
                self._restore_conversion_rules(settings['string_conversion_rules'])
            
            # リサイズ設定の復元
            if 'resize_values' in settings:
                self._restore_resize_values(settings['resize_values'])
                
        except Exception as e:
            raise Exception(f"設定ファイルの読み込みに失敗: {e}")

    def _apply_parser_settings(self):
        """パーサー設定をGUIに反映（親から設定を受け取る）"""
        try:
            # 親から設定を受け取る（独自読み込みは削除）
            if hasattr(self.parent, 'parser_settings') and self.parent.parser_settings:
                parser_settings = self.parent.parser_settings
                
                # GUIに設定を反映
                if hasattr(self, 'target_count_var') and 'target_count' in parser_settings:
                    self.target_count_var.set(parser_settings['target_count'])
                
                if hasattr(self, 'page_wait_time_var') and 'page_wait_time' in parser_settings:
                    self.page_wait_time_var.set(parser_settings['page_wait_time'])
                
                if hasattr(self, 'auto_thumb_var') and 'auto_thumb' in parser_settings:
                    self.auto_thumb_var.set(parser_settings['auto_thumb'])
                
                if hasattr(self, 'thumb_wait_time_var') and 'thumb_wait_time' in parser_settings:
                    self.thumb_wait_time_var.set(parser_settings['thumb_wait_time'])
                
                if hasattr(self, 'cache_size_var') and 'cache_size' in parser_settings:
                    self.cache_size_var.set(parser_settings['cache_size'])
                
                if hasattr(self, 'disable_thumb_var') and 'disable_thumb' in parser_settings:
                    self.disable_thumb_var.set(parser_settings['disable_thumb'])
                
                if hasattr(self, 'parse_mode_var') and 'parse_mode' in parser_settings:
                    self.parse_mode_var.set(parser_settings['parse_mode'])
                
                # パーサー設定のGUI反映はパーサー起動時に一任するため、ここではログを出力しない
                # self.parent.log("パーサー設定をGUIに反映しました", "info")
            else:
                self.parent.log("パーサー設定が見つかりません", "warning")
                
        except Exception as e:
            self.parent.log(f"パーサー設定適用エラー: {e}", "error")

    def _restore_conversion_rules(self, rules_data):
        """文字列変換ルールを復元"""
        try:
            # 既存のルールをクリア
            for widget in self.conversion_rules_container.winfo_children():
                widget.destroy()
            
            # ルールを復元
            for rule_data in rules_data:
                self._add_conversion_rule(
                    enabled=rule_data.get('enabled', True),
                    find_str=rule_data.get('find_str', ''),
                    replace_str=rule_data.get('replace_str', '')
                )
        except Exception as e:
            print(f"文字列変換ルールの復元に失敗: {e}")

    def _restore_resize_values(self, resize_data):
        """リサイズ設定を復元"""
        try:
            if isinstance(resize_data, dict) and hasattr(self.parent, 'resize_values'):
                # main_windowのresize_values辞書を更新
                for key, value in resize_data.items():
                    if key in self.parent.resize_values:
                        self.parent.resize_values[key].set(value)
        except Exception as e:
            print(f"リサイズ設定の復元に失敗: {e}")

    def _process_backup_folder(self, folder_path):
        """バックアップフォルダを処理"""
        try:
            settings_backup = os.path.join(folder_path, "settings.json")
            url_list_backup = os.path.join(folder_path, "url_list.txt")
            current_log_backup = os.path.join(folder_path, "current_log.txt")
            
            restored_files = []
            
            # 設定ファイルを復元
            if os.path.exists(settings_backup):
                try:
                    self._load_settings_from_file(settings_backup)
                    restored_files.append("設定ファイル")
                except Exception as e:
                    self.parent.log(f"設定ファイルの復元に失敗: {e}", "warning")
            
            # URLリストを復元（正しい順序で）
            if os.path.exists(url_list_backup):
                try:
                    with open(url_list_backup, 'r', encoding='utf-8') as f:
                        url_content = f.read()
                    
                    # URLを正しい順序で復元（元の順序を保持）
                    urls = []
                    for line in url_content.split('\n'):
                        line = line.strip()
                        if line:
                            urls.append(line)
                    
                    # 現在のURLリストをクリアして新しいURLを追加
                    self.url_text.delete("1.0", tk.END)
                    if urls:
                        self.url_text.insert("1.0", "\n".join(urls) + "\n")
                    
                    restored_files.append("URLリスト")
                except Exception as e:
                    self.parent.log(f"URLリストの復元に失敗: {e}", "warning")
            
            # ログファイルを復元
            if os.path.exists(current_log_backup):
                try:
                    with open(current_log_backup, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    self.parent.log_text.delete("1.0", tk.END)
                    self.parent.log_text.insert("1.0", log_content)
                    restored_files.append("ログファイル")
                except Exception as e:
                    self.parent.log(f"ログファイルの復元に失敗: {e}", "warning")
            
            if restored_files:
                self.parent.log(f"バックアップフォルダから復元: {', '.join(restored_files)}")
                return {'type': 'backup', 'success': True, 'files': restored_files}
            else:
                self.parent.log("バックアップフォルダに有効なファイルが見つかりませんでした。", "warning")
                return []
                
        except Exception as e:
            self.parent.log(f"バックアップフォルダ処理エラー: {e}", "warning")
            return []

    def _process_dropped_file(self, file_path):
        """ドロップされたファイルを処理してURLを抽出"""
        try:
            # ディレクトリの場合（バックアップフォルダ）
            if os.path.isdir(file_path):
                return self._process_backup_folder(file_path)
            
            # ファイルの拡張子をチェック
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # 設定ファイル（.json）の場合
            if file_ext == '.json':
                try:
                    # 設定ファイルとして読み込み
                    self._load_settings_from_file(file_path)
                    self.parent.log(f"設定ファイルを読み込みました: {file_path}")
                    return {'type': 'settings', 'success': True}
                except Exception as e:
                    self.parent.log(f"設定ファイルの読み込みに失敗しました: {file_path} - {e}", "warning")
                    return []
            
            # テキストファイルの場合
            elif file_ext in ['.txt', '.log', '.csv']:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return self.parent._parse_urls_from_text(content)
                except UnicodeDecodeError:
                    # UTF-8で読み込めない場合は他のエンコーディングを試す
                    try:
                        with open(file_path, 'r', encoding='shift_jis') as f:
                            content = f.read()
                        return self.parent._parse_urls_from_text(content)
                    except:
                        self.parent.log(f"ファイルの読み込みに失敗しました: {file_path}", "warning")
                        return []
                except Exception as e:
                    self.parent.log(f"ファイル処理エラー: {e}", "warning")
                    return []
            
            # その他のファイルの場合はファイルパスをURLとして扱う
            else:
                # ファイルパスがURLの形式かチェック
                if self.parent._is_valid_eh_url(file_path):
                    return [file_path]
                else:
                    self.parent.log(f"サポートされていないファイル形式です: {file_path}", "warning")
                    return []
                    
        except Exception as e:
            self.parent.log(f"ファイル処理エラー: {e}", "warning")
            return []

    def _handle_drop(self, event):
        """ドロップイベント処理"""
        try:
            # ドロップされたデータを取得
            dropped_data = event.data
            
            # ファイルパスとURLを分離
            lines = []
            settings_loaded = False
            backup_loaded = False
            
            if dropped_data.startswith('{') and dropped_data.endswith('}'):
                # 複数ファイルの場合
                file_paths = dropped_data[1:-1].split('} {')
                for file_path in file_paths:
                    result = self._process_dropped_file(file_path)
                    if isinstance(result, dict):
                        if result.get('type') == 'settings':
                            settings_loaded = True
                        elif result.get('type') == 'backup':
                            backup_loaded = True
                    elif isinstance(result, list):
                        lines.extend(result)
            else:
                # 単一ファイルまたはテキストの場合
                if os.path.isfile(dropped_data) or os.path.isdir(dropped_data):
                    result = self._process_dropped_file(dropped_data)
                    if isinstance(result, dict):
                        if result.get('type') == 'settings':
                            settings_loaded = True
                        elif result.get('type') == 'backup':
                            backup_loaded = True
                    elif isinstance(result, list):
                        lines.extend(result)
                else:
                    # テキストとして処理（URLの可能性）
                    extracted_urls = self.parent._parse_urls_from_text(dropped_data)
                    if extracted_urls:
                        lines.extend(extracted_urls)
                        self.parent.log(f"ドロップされたテキストから{len(extracted_urls)}個の有効なURLを抽出しました。")
                    else:
                        self.parent.log("ドロップされたテキストから有効なURLが見つかりませんでした。", "warning")
            
            # 設定ファイルまたはバックアップフォルダが読み込まれた場合はURL追加処理をスキップ
            if settings_loaded or backup_loaded:
                return
            
            # URLテキストに追加
            if lines:
                current_content = self.url_text.get("1.0", tk.END).strip()
                
                # 最後の文字がある行の次の行から追加する位置を決定
                if not current_content:
                    # 空の場合は最初から追加
                    self.url_text.delete("1.0", tk.END)
                    insert_position = "1.0"
                else:
                    # 既存のテキストがある場合、最後の文字がある行の次の行から追加
                    lines_content = current_content.split('\n')
                    last_non_empty_line = 0
                    
                    # 最後の文字がある行を探す
                    for i, line in enumerate(lines_content):
                        if line.strip():  # 空でない行
                            last_non_empty_line = i + 1  # 1ベースの行番号
                    
                    # 最後の文字がある行の次の行の位置を計算
                    insert_position = f"{last_non_empty_line + 1}.0"
                    
                    # 最後の行が空でない場合は改行を追加
                    if last_non_empty_line > 0 and not lines_content[-1].strip():
                        # 最後の行が空の場合は改行不要
                        pass
                    else:
                        # 最後の行に文字がある場合は改行を追加
                        self.url_text.insert(tk.END, "\n")
                
                # 新しいURLを追加
                added_count = 0
                for line in lines:
                    if line.strip():
                        self.url_text.insert(insert_position, line.strip() + "\n")
                        added_count += 1
                
                # テキスト色を通常に戻す
                self.url_text.config(fg='black')
                
                # 成功ログ
                if added_count > 0:
                    self.parent.log(f"ドラッグ＆ドロップ: {added_count}個のURLを追加しました。")
                else:
                    self.parent.log("ドラッグ＆ドロップ: 有効なURLが見つかりませんでした。", "warning")
            else:
                self.parent.log("ドラッグ＆ドロップ: 追加可能なURLが見つかりませんでした。", "warning")
                
        except Exception as e:
            self.parent.log(f"ドラッグ＆ドロップエラー: {e}", "error")

    def cut_url(self):
        """URLテキスト切り取り"""
        try:
            if self.url_text.tag_ranges(tk.SEL):
                self.url_text.event_generate("<<Cut>>")
        except tk.TclError:
            pass

    def copy_url(self):
        """URLテキストコピー"""
        try:
            if self.url_text.tag_ranges(tk.SEL):
                self.url_text.event_generate("<<Copy>>")
        except tk.TclError:
            pass

    def paste_url(self):
        """URLテキスト貼り付け"""
        try:
            # クリップボードからテキストを取得
            clipboard_text = self.parent.root.clipboard_get()
            
            if clipboard_text:
                # クリップボードのテキストからURLを抽出
                extracted_urls = self.parent._parse_urls_from_text(clipboard_text)
                
                if extracted_urls:
                    # 有効なURLが見つかった場合
                    current_content = self.url_text.get("1.0", tk.END).strip()
                    
                    # 現在のテキストが空の場合
                    if not current_content:
                        self.url_text.delete("1.0", tk.END)
                    else:
                        # 既存のテキストがある場合は改行を追加
                        self.url_text.insert(tk.INSERT, "\n")
                    
                    # 抽出されたURLを挿入
                    for url in extracted_urls:
                        self.url_text.insert(tk.INSERT, url + "\n")
                    
                    self.url_text.config(fg='black')
                    self.parent.log(f"クリップボードから{len(extracted_urls)}個のURLを貼り付けました。")
                    
                else:
                    # 有効なURLが見つからない場合は通常の貼り付け
                    self.url_text.event_generate("<<Paste>>")
                    self.parent.log("テキストを貼り付けましたが、有効なURLは見つかりませんでした。", "warning")
            else:
                # 通常の貼り付け処理
                self.url_text.event_generate("<<Paste>>")
            
            # プレースホルダの状態をチェック
            self._check_url_placeholder()
            
        except tk.TclError:
            # クリップボードが空の場合など
            pass
        except Exception as e:
            self.parent.log(f"貼り付けエラー: {e}", "error")

    def delete_selected_lines(self):
        """選択行削除"""
        try:
            if self.url_text.tag_ranges(tk.SEL):
                # 選択範囲の行を取得
                start_line = int(self.url_text.index(tk.SEL_FIRST).split('.')[0])
                end_line = int(self.url_text.index(tk.SEL_LAST).split('.')[0])
                
                # 行単位で削除
                self.url_text.delete(f"{start_line}.0", f"{end_line + 1}.0")
            else:
                # カーソル位置の行を削除
                current_line = int(self.url_text.index(tk.INSERT).split('.')[0])
                self.url_text.delete(f"{current_line}.0", f"{current_line + 1}.0")
        except Exception as e:
            self.parent.log(f"行削除エラー: {e}", "error")

    def open_url_from_context(self):
        """コンテキストメニューからURL開く"""
        try:
            if self.url_text.tag_ranges(tk.SEL):
                selected_text = self.url_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
            else:
                # カーソル位置の行を取得
                current_line = int(self.url_text.index(tk.INSERT).split('.')[0])
                selected_text = self.url_text.get(f"{current_line}.0", f"{current_line}.end").strip()
            
            if selected_text and self.parent._is_valid_eh_url(selected_text):
                webbrowser.open(selected_text)
                self.parent.log(f"ブラウザでURLを開きました: {selected_text}")
            else:
                messagebox.showwarning("無効なURL", "選択されたテキストは有効なURLではありません。")
                
        except Exception as e:
            self.parent.log(f"URL開くエラー: {e}", "error")

    def _show_url_context_menu(self, event):
        """URLテキストのコンテキストメニュー表示"""
        try:
            self.url_text_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.url_text_context_menu.grab_release()

    def _select_all_url_text(self, event):
        """URLテキスト全選択"""
        self.url_text.tag_add(tk.SEL, "1.0", tk.END)
        return "break"

    def _on_url_text_modified(self, event):
        """URLテキスト変更時の処理"""
        # プレースホルダー機能を削除したため、特別な処理は不要
        self.url_text.edit_modified(False)
        
        # ハイパーリンクを更新（遅延実行で重複を防ぐ）
        if hasattr(self, '_hyperlink_update_timer'):
            self.parent.root.after_cancel(self._hyperlink_update_timer)
        self._hyperlink_update_timer = self.parent.root.after(500, self._setup_hyperlinks)

    def _add_resize_complete_marker(self, url_key):
        """リサイズ完了マーカーを追加"""
        try:
            if not url_key:
                return
            
            content = self.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            
            # URLを含む行を検索
            normalized_url = self.normalize_url(url_key)
            if not normalized_url:
                return
            
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                raw_url_part = line_stripped.split("(")[0].strip()
                current_url = self.normalize_url(raw_url_part)
                
                if current_url == normalized_url:
                    # 既にマーカーがある場合は追加しない
                    if "(リサイズ完了)" in line_stripped:
                        continue
                    
                    # マーカーを追加（ゼロ幅スペースを使用）
                    line_start_index = f"{i+1}.0"
                    original_text_end_index = f"{i+1}.{len(raw_url_part)}"
                    
                    # マーカーを追加
                    self.url_text.insert(original_text_end_index, "\u200B(リサイズ完了)")
                    
                    # マーカー部分のタグ付け
                    marker_text = "(リサイズ完了)"
                    marker_start_display_index = f"{i+1}.{len(raw_url_part) + 1}"
                    marker_end_display_index = f"{i+1}.{len(raw_url_part) + 1 + len(marker_text)}"
                    
                    self.url_text.tag_add("resize_marker", marker_start_display_index, marker_end_display_index)
                    self.url_text.tag_config("resize_marker", 
                                           foreground="green", 
                                           selectforeground="green",
                                           selectbackground=self.url_text.cget("background"))
                    
                    # 元のURL部分にハイパーリンクを再確認・設定
                    self.url_text.tag_remove("hyperlink", line_start_index, f"{i+1}.end")
                    if self.parent._is_valid_eh_url(raw_url_part):
                        self.url_text.tag_add("hyperlink", line_start_index, original_text_end_index)
                        self.url_text.tag_config("hyperlink", foreground="blue", underline=True)
                    
                    # 背景色を更新
                    self.update_url_background(url_key)
                    break
            
            # 全てのURLの背景色を更新
            self._update_all_url_backgrounds()
            
        except Exception as e:
            self.parent.log(f"リサイズ完了マーカー追加エラー: {e}", "error")

    def _add_compression_complete_marker(self, url_key):
        """URLの右側に（圧縮完了）マーカーを追加（現在処理中の行のみ）"""
        try:
            # 現在のURL indexを取得
            current_url_index = 0
            if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
                current_url_index = self.parent.downloader_core.state_manager.get_current_url_index()
            
            content = self.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            # url_key は normalize_url されたものか、フォルダパスの場合がある
            
            # 現在処理中の行を特定
            target_line = None
            url_line_count = 0
            for i, line_text in enumerate(lines):
                line_stripped = line_text.strip()
                if not line_stripped:
                    continue
                # マーカーや他のテキストを除いた純粋なURL部分で比較
                raw_url_part = line_stripped.split("（")[0].strip()
                # 不可視文字を除去（ゼロ幅スペース等）
                try:
                    raw_url_part = raw_url_part.replace("\u200b", "").replace("\ufeff", "")
                except Exception:
                    pass
                
                # キーがURLの場合とフォルダパスの場合で比較対象を切り替え
                current_line_key = self.parent.normalize_url(raw_url_part) if self.parent._is_valid_eh_url(raw_url_part) else raw_url_part

                if current_line_key == url_key:
                    # 同じURLが複数ある場合、current_url_indexに対応する行を選択
                    if url_line_count == current_url_index:
                        target_line = i
                        break
                    url_line_count += 1
            
            if target_line is None:
                # 圧縮マーカー追加失敗
                return
            
            line_text = lines[target_line]
            if "（圧縮完了）" not in line_text: # マーカーがまだない場合
                raw_url_part = line_text.strip().split("（")[0].strip()
                try:
                    raw_url_part = raw_url_part.replace("\u200b", "").replace("\ufeff", "")
                except Exception:
                    pass
                line_start_index = f"{target_line+1}.0"
                # 元のテキスト（URL部分）の実際の終了位置を正確に把握
                original_text_end_index = f"{target_line+1}.{len(raw_url_part)}"
                
                # マーカーを追加（ゼロ幅スペースを使用）
                self.url_text.insert(original_text_end_index, "\u200B（圧縮完了）")
                
                # マーカー部分のタグ付け
                marker_text = "（圧縮完了）"
                # マーカーの開始位置は元のテキストの直後（+1はゼロ幅スペース分）
                marker_start_display_index = f"{target_line+1}.{len(raw_url_part) + 1}" 
                marker_end_display_index = f"{target_line+1}.{len(raw_url_part) + 1 + len(marker_text)}"
                
                self.url_text.tag_add("compression_marker", marker_start_display_index, marker_end_display_index)
                self.url_text.tag_config("compression_marker", 
                                        foreground="green", 
                                        background="#E0F6FF",  # 薄い青色（DL成功時と同じ色）
                                        selectforeground="green", # 選択時の文字色
                                        selectbackground="#E0F6FF") # 選択時も薄い青色
                
                # 元のURL部分にハイパーリンクを再確認・設定 (マーカー部分は含めない)
                # 既存のハイパーリンクがあれば一度削除し、URL部分にのみ再設定
                self.url_text.tag_remove("hyperlink", line_start_index, f"{target_line+1}.end") # 行全体のハイパーリンクを一旦クリア
                if self.parent._is_valid_eh_url(raw_url_part): # 有効なURLならハイパーリンク設定
                    self.url_text.tag_add("hyperlink", line_start_index, original_text_end_index)
                    self.url_text.tag_config("hyperlink", foreground="blue", underline=True)
                
                self.parent.log(f"圧縮完了マーカーを追加: {url_key}")
                        
        except Exception as e:
            self.parent.log(f"圧縮完了マーカー追加エラー ({url_key}): {e}", "error")

    def sanitize_filename(self, filename):
        """ファイル名の無効文字を置換（文字列変換対応）"""
        try:
            if not filename:
                return "untitled"
            
            # 文字列変換ルールを適用
            if hasattr(self, 'string_conversion_enabled') and self.string_conversion_enabled.get():
                filename = self._apply_string_conversion(filename)
            
            # 既存の無効文字置換処理
            invalid_chars = r'[\\/:*?"<>|]'
            filename = re.sub(invalid_chars, '_', filename)
            
            # 連続するアンダースコースを単一に
            filename = re.sub(r'_+', '_', filename)
            
            # 先頭・末尾のドットやスペースを削除
            filename = filename.strip(' .')
            
            return filename or "untitled"
            
        except Exception as e:
            self.parent.log(f"ファイル名変換エラー: {e}", "error")
            return "untitled"

    def _setup_hyperlinks(self):
        """URLテキストにハイパーリンク機能を追加"""
        try:
            content = self.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            
            # 既存のハイパーリンクタグを削除
            self.url_text.tag_delete("hyperlink")
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line and self.parent._is_valid_eh_url(line):
                    line_start = f"{i+1}.0"
                    line_end = f"{i+1}.end"
                    
                    # ハイパーリンクタグを追加
                    self.url_text.tag_add("hyperlink", line_start, line_end)
                    self.url_text.tag_config("hyperlink", 
                                            foreground="blue", 
                                            underline=True)
            
            # クリックイベントをバインド
            def on_hyperlink_click(event):
                try:
                    # クリックされた位置の行を取得
                    line_index = self.url_text.index(tk.INSERT).split('.')[0]
                    line_text = self.url_text.get(f"{line_index}.0", f"{line_index}.end").strip()
                    
                    # URLが有効な場合、ブラウザで開く
                    if self.parent._is_valid_eh_url(line_text):
                        import webbrowser
                        webbrowser.open(line_text)
                        self.parent.log(f"ブラウザでURLを開きました: {line_text}")
                        
                except Exception as e:
                    self.parent.log(f"ハイパーリンククリックエラー: {e}", "error")
            
            self.url_text.tag_bind("hyperlink", "<Button-1>", on_hyperlink_click)
            
            # サムネイル表示機能（マウスホバー）
            if self.parent.thumbnail_display_enabled.get() == "on":
                self.url_text.bind("<Motion>", self._on_url_motion)
                self.url_text.bind("<Leave>", self._on_url_leave)
            
        except Exception as e:
                self.parent.log(f"ハイパーリンク設定エラー: {e}", "error")
    
    def _update_all_url_backgrounds(self):
        """全てのURLの背景色を一括で更新"""
        try:
            if not self.url_text:
                return
            
            content = self.url_text.get("1.0", tk.END)
            urls = self.parent._parse_urls_from_text(content)
            # 重複を除去
            unique_urls = list(dict.fromkeys(urls))
            for url in unique_urls:
                self.update_url_background(url)
        except Exception as e:
            if hasattr(self.parent, 'log'):
                self.parent.log(f"全URL背景色更新エラー: {e}", "warning")

    def get_total_line_count_fast(self):
        """行数を高速で取得（O(1)処理）"""
        try:
            # Tkinterのcount()メソッドを使用
            line_count = int(self.url_text.count("1.0", tk.END, "lines")[0])
            return line_count
        except:
            return 0

    def get_valid_url_count_fast(self):
        """有効なURL数を高速で取得"""
        try:
            # 全行数を取得
            total_lines = self.get_total_line_count_fast()
            
            # 有効なURL行のみをカウント（最適化版）
            valid_count = 0
            for i in range(1, total_lines + 1):
                line_text = self.url_text.get(f"{i}.0", f"{i}.end").strip()
                if line_text and self.parent._is_valid_eh_url(line_text):
                    valid_count += 1
            
            return valid_count
        except:
            return 0

    def _find_url_line_fast(self, url):
        """URLの行番号を高速で検索"""
        try:
            normalized_url = self.parent.normalize_url(url)
            if not normalized_url:
                return None
            
            # 現在のURLインデックスから逆算
            if hasattr(self.parent, 'downloader_core'):
                current_index = self.parent.downloader_core.state_manager.get_current_url_index()
                # 現在の行周辺を優先的にチェック
                for offset in range(-5, 6):  # 前後5行をチェック
                    check_line = current_index + offset + 1
                    if check_line > 0:
                        line_text = self.url_text.get(f"{check_line}.0", f"{check_line}.end").strip()
                        if line_text and self.parent.normalize_url(line_text) == normalized_url:
                            return check_line
            
            return None
        except:
            return None

    def update_url_background(self, url):
        """URLの背景色を状態に応じて更新（安定化版）"""
        if not url or not self.url_text:
            return
        
        # 正規化されたURLを取得
        normalized_url = self.parent.normalize_url(url)
        if not normalized_url:
            return
        
        # スレッドセーフな更新
        def safe_update():
            try:
                # デバウンス: 更新待ちリストに追加
                self.url_bg_update_pending[normalized_url] = True
                
                # 既存のタイマーをキャンセル
                if self.url_bg_update_timer:
                    self.parent.root.after_cancel(self.url_bg_update_timer)
                
                # 新しいタイマーを設定（200ms後に実行）
                self.url_bg_update_timer = self.parent.root.after(200, self._process_pending_url_updates)
            except Exception as e:
                pass  # エラーは無視
        
        # メインスレッドで実行
        if threading.current_thread() == threading.main_thread():
            safe_update()
        else:
            self.parent.root.after(0, safe_update)
    
    def _process_pending_url_updates(self):
        """待機中のURL背景色更新を一括処理"""
        if not self.url_bg_update_pending:
            return
        
        try:
            # 更新対象を取得してクリア
            pending_urls = list(self.url_bg_update_pending.keys())
            self.url_bg_update_pending.clear()
            
            # 各URLの背景色を更新
            for normalized_url in pending_urls:
                self._update_url_background_immediate(normalized_url)
                
        except Exception as e:
            pass  # エラーは無視
        finally:
            self.url_bg_update_timer = None
    
    def _update_url_background_immediate(self, url):
        """URLの背景色を即座に更新（内部メソッド）"""
        try:
            # 高速検索を試行
            target_line = self._find_url_line_fast(url)

            # 高速検索で見つからない場合は従来の方法を使用
            if target_line is None:
                # URLテキスト全体を取得（フォールバック）
                content = self.url_text.get("1.0", tk.END)
                lines = content.split('\n')

                # URLを含む行を検索（正規化URLでも検索）
                target_line = -1

                for i, line in enumerate(lines):
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    raw_url_part = line_stripped.split("(")[0].strip()  # マーカーを除いたURL部分
                    current_url = self.parent.normalize_url(raw_url_part)

                    if current_url == url:
                        target_line = i + 1  # tkinterは1ベース
                        break

            if target_line == -1:
                return

            # ⭐修正: StateManager経由でURLの状態を取得（一元管理）⭐
            if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
                url_status = self.parent.downloader_core.state_manager.get_url_status(url)
            else:
                # フォールバック: 従来の方法
                url_status = getattr(self.parent, 'url_status', {}).get(url, DownloadStatus.WAITING)
            # 文字列→Enum変換（後方互換）
            if not isinstance(url_status, DownloadStatus):
                try:
                    url_status = DownloadStatus(url_status)
                except Exception:
                    url_status = DownloadStatus.WAITING

            # 状態に応じた背景色を設定
            # ⭐修正: skippedのチェックをcompletedの前に配置（スキップ時は常に薄いグレー）⭐
            if url_status == DownloadStatus.DOWNLOADING:
                bg_color = "#FFFACD"  # 薄い黄色（DL中）
            elif url_status == DownloadStatus.SKIPPED:
                bg_color = "#F0F0F0"  # 薄いグレー（スキップ済み）- 優先度最高
            elif url_status == DownloadStatus.PAUSED:
                bg_color = "#F0F0F0"  # 薄いグレー（中断）
            elif url_status == DownloadStatus.ERROR:
                bg_color = "#FFE4E1"  # 薄い赤色（エラー）
            elif url_status == DownloadStatus.COMPLETED:
                # ⭐修正: completedでも、スキップされたURLの場合は薄いグレーにする⭐
                if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
                    actual_status = self.parent.downloader_core.state_manager.get_url_status(url)
                    if not isinstance(actual_status, DownloadStatus):
                        try:
                            actual_status = DownloadStatus(actual_status)
                        except Exception:
                            actual_status = DownloadStatus.WAITING
                    if actual_status == DownloadStatus.SKIPPED:
                        bg_color = "#F0F0F0"  # 薄いグレー（スキップ済み）
                    else:
                        bg_color = "#E0F6FF"  # 薄い青色（完了）
                else:
                    bg_color = "#E0F6FF"  # 薄い青色（完了）
            # DownloadStatusに「未完了」相当がなければ、ここで追加分岐
            else:
                # デフォルト（未処理）
                bg_color = "white"

            # 既存のタグを完全に削除
            existing_tags = self.url_text.tag_names(f"{target_line}.0")
            for tag in existing_tags:
                if tag.startswith("url_bg_"):
                    self.url_text.tag_delete(tag)

            # 新しいタグを設定
            tag_name = f"url_bg_{target_line}"
            line_start = f"{target_line}.0"
            line_end = f"{target_line}.end"

            # 新しいタグを適用
            self.url_text.tag_configure(tag_name, background=bg_color)
            self.url_text.tag_add(tag_name, line_start, line_end)

        except Exception as e:
            pass  # エラーは無視
    
    def _on_url_motion(self, event):
        """URLにマウスが移動した時の処理"""
        try:
            if self.parent.thumbnail_display_enabled.get() != "on":
                return
                
            # マウス位置の行を取得
            line_index = self.url_text.index(f"@{event.x},{event.y}").split('.')[0]
            line_text = self.url_text.get(f"{line_index}.0", f"{line_index}.end").strip()
            
            # URLが有効な場合、サムネイルを表示
            if self.parent._is_valid_eh_url(line_text):
                # 同じURLのポップアップが表示されている場合はスキップ
                if (hasattr(self, 'thumbnail_window') and self.thumbnail_window and 
                    hasattr(self.thumbnail_window, "current_url") and 
                    self.thumbnail_window.current_url == line_text):
                    return
                    
                # サムネイルを表示
                self._show_thumbnail(line_text, event.x_root, event.y_root)
                
        except Exception as e:
            self.parent.log(f"URLモーションエラー: {e}", "error")
    
    def _on_url_leave(self, event):
        """URLからマウスが離れた時の処理"""
        try:
            self._hide_thumbnail()
        except Exception as e:
            self.parent.log(f"URLリーブエラー: {e}", "error")
    
    def _show_thumbnail(self, url, x, y):
        """サムネイル画像を表示（非同期）"""
        try:
            # 既存のサムネイルウィンドウを閉じる
            self._hide_thumbnail()
            
            # ギャラリーURLを正規化
            import re
            if re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', url):
                # 個別画像ページURLの場合は、ギャラリーURLに変換
                gallery_url = self._convert_individual_page_to_gallery_url(url)
            else:
                gallery_url = self.parent.normalize_url(url)
            
            if not gallery_url:
                return
            
            # サムネイルウィンドウを作成
            self.thumbnail_window = tk.Toplevel(self.parent.root)
            self.thumbnail_window.overrideredirect(True)
            self.thumbnail_window.geometry(f"+{x+15}+{y+10}")
            self.thumbnail_window.attributes('-topmost', True)
            self.thumbnail_window.current_url = url
            
            # ポップアップフレームの作成
            popup_frame = tk.Frame(self.thumbnail_window, borderwidth=1, relief="solid")
            popup_frame.pack(fill=tk.BOTH, expand=True)
            
            # 読み込み中表示
            loading_label = tk.Label(popup_frame, text="読み込み中...", font=("Arial", 12))
            loading_label.pack(expand=True)
            
            # 非同期でサムネイルを取得・表示
            import threading
            thread = threading.Thread(
                target=self._fetch_and_display_thumbnail_async,
                args=(gallery_url, loading_label, popup_frame),
                daemon=True
            )
            thread.start()
            
        except Exception as e:
            self.parent.log(f"サムネイル表示エラー: {e}", "error")
    
    def _hide_thumbnail(self):
        """サムネイル画像を非表示"""
        try:
            if hasattr(self, 'thumbnail_window') and self.thumbnail_window:
                self.thumbnail_window.destroy()
                self.thumbnail_window = None
        except Exception as e:
            self.parent.log(f"サムネイル非表示エラー: {e}", "error")
    
    def _update_thumbnail_display_state(self):
        """サムネイル表示状態を更新"""
        try:
            if self.parent.thumbnail_display_enabled.get() == "on":
                # サムネイル表示がONの場合はイベントバインディングを追加
                self.url_text.bind("<Motion>", self._on_url_motion)
                self.url_text.bind("<Leave>", self._on_url_leave)
            else:
                # サムネイル表示がOFFの場合は既存のサムネイルを非表示し、イベントバインディングを削除
                self._hide_thumbnail()
                self.url_text.unbind("<Motion>")
                self.url_text.unbind("<Leave>")
        except Exception as e:
            self.parent.log(f"サムネイル表示状態更新エラー: {e}", "error")
    
    def _convert_individual_page_to_gallery_url(self, individual_url):
        """個別画像ページURLをギャラリーURLに変換"""
        try:
            import re
            match = re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', individual_url)
            if match:
                domain, token, gid, page_num = match.groups()
                return f"https://{domain}.org/g/{gid}/{token}/"
            return None
        except Exception as e:
            self.parent.log(f"個別ページURL変換エラー: {e}", "error")
            return None
    
    def _get_thumbnail_url(self, gallery_url):
        """ギャラリーのサムネイルURLを取得（gd1要素のbackground URL方式）"""
        try:
            import requests
            import re
            
            # ギャラリーページを取得
            response = requests.get(gallery_url, timeout=10)
            response.raise_for_status()
            html = response.text
            
            # gd1要素のbackground URLを取得
            # <div id="gd1"><div style="...background:transparent url(XXX)...">
            gd1_pattern = re.compile(r'<div id="gd1"[^>]*>.*?background:\s*transparent\s+url\(([^)]+)\)', re.DOTALL | re.IGNORECASE)
            gd1_match = gd1_pattern.search(html)
            if gd1_match:
                return gd1_match.group(1)
            
            # フォールバック: 通常のimgタグから取得
            img_pattern = re.compile(r'<img[^>]+(?:data-)?src="([^"]+\.(?:webp|jpe?g|png|gif))"', re.IGNORECASE)
            img_match = img_pattern.search(html)
            if img_match:
                return img_match.group(1)
            
            return None
        except Exception as e:
            self.parent.log(f"サムネイルURL取得エラー: {e}", "error")
            return None
    
    def _fetch_and_display_thumbnail_async(self, gallery_url, loading_label, popup_frame):
        """非同期でサムネイルを取得・表示"""
        try:
            # サムネイルURLを取得
            thumbnail_url = self._get_thumbnail_url(gallery_url)
            if not thumbnail_url:
                self.parent.root.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, error="サムネイルURLが取得できませんでした"))
                return
            
            # 画像をダウンロード
            import requests
            response = requests.get(thumbnail_url, timeout=10)
            response.raise_for_status()
            
            # 画像を処理
            from PIL import Image, ImageTk
            import io
            image = Image.open(io.BytesIO(response.content))
            image.thumbnail((300, 300), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            # GUIスレッドで表示
            self.parent.root.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, image=photo))
            
        except Exception as e:
            # サムネイル取得エラーは無視（デバッグログに表示しない）
            self.parent.root.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, error=f"取得エラー: {e}"))
    
    def _update_thumbnail_content(self, loading_label, popup_frame, image=None, error=None):
        """サムネイルウィンドウの内容を更新"""
        try:
            # ウィンドウの存在チェックを強化
            if not hasattr(self, 'thumbnail_window') or not self.thumbnail_window:
                return
            
            # ウィンドウが破棄されていないかチェック
            try:
                self.thumbnail_window.winfo_exists()
            except tk.TclError:
                # ウィンドウが破棄されている場合は処理を中断
                return
            
            # フレームの存在チェック
            try:
                popup_frame.winfo_exists()
            except tk.TclError:
                # フレームが破棄されている場合は処理を中断
                return
                
            # 読み込み中ラベルを削除
            try:
                loading_label.pack_forget()
            except tk.TclError:
                # ラベルが破棄されている場合は無視
                pass
            
            if image:
                # 画像を表示
                image_label = tk.Label(popup_frame, image=image)
                image_label.image = image  # 参照を保持
                image_label.pack(expand=True)
                
                # マウスイベントを設定
                popup_frame.bind("<Leave>", lambda e: self._hide_thumbnail())
            elif error:
                # エラーメッセージを表示
                error_label = tk.Label(popup_frame, text=error, font=("Arial", 10), fg="red")
                error_label.pack(expand=True)
                
        except Exception as e:
            # サムネイルウィンドウの破棄エラーは無視（デバッグログに表示しない）
            pass