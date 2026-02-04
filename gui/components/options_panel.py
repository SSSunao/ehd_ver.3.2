# -*- coding: utf-8 -*-
"""
Options panel component for EH Downloader
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import json
from datetime import datetime
from config.settings import ToolTip
from config.constants import *

# ツールチップのテキスト定義
TOOLTIP_TEXTS = {
    # 基本設定
    'wait_time': 'ページ移動時の待機時間（秒）\nサーバー負荷軽減のため0.5秒以上推奨',
    'sleep_value': '画像ダウンロード間の待機時間（秒）\nサーバー負荷軽減のため0.5秒以上推奨',
    'save_format': '画像保存形式\n• Original: 元の形式を維持\n• JPEG/PNG/WebP: 指定形式に変換',
    'save_name': 'ファイル名の形式\n• Original: 元のファイル名\n• Page Number: ページ番号のみ\n• Custom: カスタムテンプレート',
    'custom_name': 'ファイル名テンプレート\n使用可能な変数:\n• {page}: ページ番号\n• {artist}: 作者名\n• {title}: 作品タイトル\n• {parody}: パロディ元\n• {character}: キャラクター名\n• {group}: サークル名',
    # フォルダ設定
    'folder_path': '画像保存先フォルダ\n各ギャラリーはこのフォルダ内に\nサブフォルダとして作成されます',
    'custom_folder_name': 'フォルダ名テンプレート\n使用可能な変数:\n• {artist}: 作者名\n• {title}: 作品タイトル\n• {parody}: パロディ元\n• {character}: キャラクター名\n• {group}: サークル名',
    'first_page_naming': '1ページ目の特別な名前\n表紙として"cover"や"title"を\n設定するのに便利です',
    'incomplete_folder': '未完了フォルダの接頭辞\n中断・エラー・スキップされた\nフォルダを識別しやすくします',
    'compression_format': 'ZIP圧縮機能\nダウンロード完了後に\nフォルダをZIP形式で圧縮します',
    'compression_delete_original': '圧縮後の元フォルダ削除\n• ON: 圧縮後に元フォルダを削除\n• OFF: フォルダとZIP両方を保持',
    'sharpness': 'リサイズ後の画像をシャープにする強度（0-100）。50推奨。高すぎるとノイズが目立ちます。',
    'resize_save_location': 'リサイズ画像の保存場所。"元の場所に上書き": 元画像を置き換え、"サブフォルダに保存": 別フォルダに保存（元画像も保持）',
    'keep_unresized': 'ONの場合、リサイズ不要な画像（既に指定サイズ以下）もリサイズ対象として処理します。',
    'auto_resume_delay': 'エラー後、自動再試行するまでの待機時間（秒）。サーバー負荷軽減のため適切な値を設定してください。',
    'retry_delay_increment': '再試行ごとに待機時間を増やす秒数。例: 5秒ずつ増やすと、1回目5秒、2回目10秒、3回目15秒と待機。',
    'max_retry_delay': '再試行時の最大待機時間（秒）。これ以上は待機時間が増えません。',
    'selenium_session_retry': 'セッションエラー（画像が見つからない等）が発生した際、Seleniumを有効化して再試行します。',
    'selenium_persistent': 'ダウンロード中、常にSeleniumを有効にします。通常は自動切り替えをお勧めします。',
    'selenium_page_retry': 'ページ取得エラーの際もSeleniumを使用して再試行します。強力ですが動作が遅くなります。',
    'string_conversion': '文字列変換ルールを適用します。特定の文字列を別の文字列に置換できます（例: NGワードの削除）。',
    'folder_name_mode': 'フォルダ名の決定方法。h1_priority: H1タグ優先、title_priority: Titleタグ優先、custom: カスタムテンプレート',
    'custom_folder_name': 'フォルダ名のカスタムテンプレート。使用可能な変数: {artist}, {title}, {parody}, {character}, {group}',
    'duplicate_folder_mode': '同名フォルダが存在する場合の処理。rename: 連番を付けて新規作成、overwrite: 上書き',
    'duplicate_file_mode': 'E-Hentai Galleriesには同名ファイルが同じギャラリーに含まれる可能性があるので変更不可。新しいファイル名で保存(例:file(1).jpg)のみ有効。',
    'skip_after_count': '指定回数連続でスキップが発生した場合、そのギャラリー全体をスキップして次のURLに進みます',
    'incomplete_folder': 'ダウンロードが中断・エラー・スキップされたフォルダに接頭辞を付けます',
    'compression': 'ダウンロード完了後にフォルダをZIP形式で圧縮します',
    
    # 画像編集
    'resize_mode': 'リサイズモード。off: リサイズしない、縦幅上限/横幅上限/長辺上限/短辺下限: 指定サイズに調整',
    'interpolation_mode': 'リサイズ時の補間方法。画質優先: 高品質だが低速、バランス: 品質と速度のバランス、速度優先: 高速だが低品質',
    'jpg_quality': 'JPEG保存時の画質（1-100）。高いほど高画質だがファイルサイズが大きくなります',
    'preserve_animation': 'アニメーションGIFやAPNGの動きを保持します。オフにすると静止画として保存されます',
    'keep_original': 'リサイズ後も元の画像を保持します',
    'keep_unresized': 'リサイズ不要な画像も処理対象に含めます',
    
    # 高度なオプション
    'smart_error_handling': '⭐自動エラーハンドリング（推奨）\n• ON: エラー種別を自動判断して最適処理\n• OFF: エラー発生時に手動再開が必要\n\n【自動処理例】\n・タイムアウト → 5回自動リトライ（指数バックオフ）\n・403禁止 → 即座にSelenium試行\n・404不存在 → 画像スキップ\n・ディスク満杯 → ダウンロード中止',
    'max_retry_count': '最大リトライ回数（3～10回推奨）\nエラー種別により自動調整されます\n例: タイムアウト5回、レート制限10回',
    'circuit_breaker_threshold': 'Circuit Breaker閾値\n連続エラーがこの回数に達すると\n自動停止して60秒後に再開を試みます',
    'multithread': 'マルチスレッドダウンロード。複数の画像を同時にダウンロードして高速化します',
    'user_agent_spoofing': 'ブラウザになりすましてアクセスします。簡単なブロック回避に効果的です',
    'httpx': 'よりブラウザに近い通信(HTTP/2)を行います。TLSエラー対策にもなります',
    'selenium': '本物のブラウザを自動操作してダウンロードします。Chromeが必要です',
    
    # リサイズ詳細設定
    'resize_height': '縦幅上限モード: この値以上の高さの画像を縮小します',
    'resize_width': '横幅上限モード: この値以上の幅の画像を縮小します',
    'resize_short': '短辺下限モード: 短辺がこの値未満の画像を拡大します',
    'resize_long': '長辺上限モード: 長辺がこの値以上の画像を縮小します',
    'resize_percentage': 'パーセントモード: 元サイズの指定%に縮小します（例: 80%）',
    'resize_unified': '統一サイズモード: 長辺をこの値に統一します',
    'sharpness_value': 'リサイズ後に適用するシャープネス強度（0-100）。推奨値: 50',
    'resized_prefix': 'リサイズ後のファイル名の前に付ける接頭辞',
    'resized_suffix': 'リサイズ後のファイル名の後ろに付ける接尾辞',
    'resized_subdir_name': 'リサイズ画像を保存するサブディレクトリ名',
    
    # ボタン
    'start_btn': 'ダウンロード開始\nURLリストのすべてのギャラリーを\n順次ダウンロードします',
    'pause_btn': 'ダウンロード中断\n現在のダウンロードを一時停止\n再開ボタンで続きから再開可能',
    'resume_btn': 'ダウンロード再開\n中断されたダウンロードを\n続きから再開します',
    'restart_btn': 'ギャラリー再開\nエラー発生時にそのギャラリーを\n最初からやり直します',
    'skip_btn': 'ギャラリースキップ\n現在のギャラリーをスキップして\n次のURLに進みます',
    'clear_btn': 'データクリア\nURLリスト、ログ、ダウンロード状態を\nすべてクリアします',
    'open_page_btn': '画像ページを開く\n現在ダウンロード中の画像ページを\nブラウザで開きます',
    'open_folder_btn': '保存フォルダを開く\n現在ダウンロード中のギャラリーの\nフォルダをエクスプローラーで開きます',
    # パーサー関連
    'search_url': '検索結果URL\nE-Hentaiの検索結果ページのURL\n検索条件設定後にコピーして使用',
    'gallery_count': '取得ギャラリー数\n検索結果から指定した数だけ\nURLを抽出します',
    'page_wait': 'ページ移動待機時間（秒）\n検索結果ページ移動時の待機時間\nサーバー負荷軽減のため適切な値を設定',
    'auto_thumb': 'サムネイル自動取得\n各ギャラリーのサムネイル画像を\n自動で取得・保存します',
    'thumb_wait': 'サムネイル取得待機時間（秒）\nサムネイル画像取得時の待機時間',
    'cache_size': 'キャッシュサイズ\n取得データをメモリに保持する量\nメモリ使用量を制御します',
    'disable_thumb': 'サムネイル取得無効化\nメモリ使用量を削減したい場合に\n使用します',
    'parse_mode': '解析モード\n• DBに追加: データベースに保存\n• リスト出力: テキストファイルに出力',
    'backup_load': 'バックアップ復元\n以前に保存したバックアップファイルから\n設定とURLリストを復元します',
    'backup_save': 'バックアップ保存\n現在の設定とURLリストを\nバックアップファイルとして保存します',
    'url_parse': 'URL解析実行\nURLリストの解析を実行し\n各URLの有効性をチェックします',
    'parse_output': '解析結果出力\n解析結果をテキストファイルとして\n出力します',
    'torrent_manager': 'Torrent管理\nTorrentファイルのダウンロードを管理\nE-HentaiのTorrent機能に便利',
    'continue_parse': '解析続行\n前回の解析を続行\n中断された解析から再開できます',
}

class OptionsStateManager:
    """オプション状態管理クラス（集約化）"""
    
    def __init__(self, parent):
        self.parent = parent
        self._setup_state_bindings()
    
    def _setup_state_bindings(self):
        """状態更新のイベントバインディングを設定"""
        try:
            # リサイズ設定
            self.parent.resize_enabled.trace_add('write', self._update_resize_options_state)
            # 高度なオプション
            self.parent.advanced_options_enabled.trace_add('write', self._update_advanced_options_state)
            # 未完了フォルダリネーム
            self.parent.rename_incomplete_folder.trace_add('write', self._update_incomplete_folder_options_state)
            # 文字列変換
            self.parent.string_conversion_enabled.trace_add('write', self._update_string_conversion_state)
            # 自動再開
            self.parent.error_handling_mode.trace_add('write', self._update_auto_resume_options_state)
            self.parent.error_handling_enabled.trace_add('write', self._update_auto_resume_options_state)
            if hasattr(self.parent, 'retry_limit_action'):
                self.parent.retry_limit_action.trace_add('write', self._update_auto_resume_options_state)
            # 起動時に自動再開オプションの状態を更新
            self.parent.root.after(100, self._update_auto_resume_options_state)
            self.parent.root.after(200, self._update_auto_resume_options_state)
            # ⭐追加: 起動時にページ情報Seleniumオプションの状態を更新⭐
            if hasattr(self.parent, 'options_panel'):
                self.parent.root.after(300, lambda: self.parent.options_panel._update_page_info_selenium_state() if hasattr(self.parent.options_panel, '_update_page_info_selenium_state') else None)
            # 圧縮設定
            self.parent.compression_enabled.trace_add('write', self._update_compression_options_state)
            # フォルダ名設定
            self.parent.folder_name_mode.trace_add('write', self._update_folder_name_state)
            # 1ページ目命名
            self.parent.first_page_naming_enabled.trace_add('write', self._update_first_page_naming_state)
            # スキップ回数
            self.parent.skip_after_count_enabled.trace_add('write', self._update_skip_count_state)
            # カスタム名設定
            self.parent.save_name.trace_add('write', self._update_custom_name_entry_state)
        except Exception as e:
            print(f"状態バインディング設定エラー: {e}")
    
    def _register_grayout_option(self, var_name, widgets, value_map=None, extra_check=None, recursive=False):
        """共通のグレーアウトオプション登録ヘルパー"""
        def update_grayout(*args):
            try:
                # 変数値取得
                var = getattr(self.parent, var_name)
                value = var.get() if hasattr(var, 'get') else var
                
                # value_mapがあれば変換
                if value_map:
                    is_enabled = value_map.get(value, bool(value))
                else:
                    is_enabled = bool(value)
                
                # extra_checkがあれば追加判定
                if extra_check and callable(extra_check):
                    is_enabled = extra_check(is_enabled)
                
                state = 'normal' if is_enabled else 'disabled'
                
                # ウィジェット更新
                for widget in widgets:
                    if recursive:
                        self._set_widget_state_recursive(widget, state)
                    else:
                        if hasattr(widget, 'config'):
                            widget.config(state=state)
            except Exception as e:
                self.parent.log(f"{var_name}グレーアウト更新エラー: {e}", "debug")
        
        # 初期状態設定
        self.parent.root.after(100, update_grayout)
        
        # 変更時コールバック
        var = getattr(self.parent, var_name)
        if hasattr(var, 'trace'):
            var.trace('w', update_grayout)
    
    def _check_download_range_state(self, is_enabled):
        """ダウンロード範囲の特殊チェック"""
        # ダウンロード中チェック
        if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
            if self.parent.downloader_core.state_manager.is_download_running():
                return False
        
        # エラー処理中チェック
        if hasattr(self.parent, 'enhanced_error_handler') and self.parent.enhanced_error_handler:
            if self.parent.enhanced_error_handler.is_error_handling_active():
                return False
        
        # DL範囲が不正で中断している場合は編集可能
        if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
            url_statuses = self.parent.downloader_core.state_manager.download_state.url_status
            for url, status in url_statuses.items():
                if status == 'paused':
                    resume_info = self.parent.downloader_core.state_manager.get_resume_point(url)
                    if resume_info and resume_info.get('reason') == 'range_invalid':
                        return is_enabled
        
        return is_enabled
    
    def _set_widget_state_recursive(self, widget, state):
        """再帰的にウィジェット状態を設定"""
        try:
            if hasattr(widget, 'config'):
                widget.config(state=state)
        except tk.TclError:
            pass
        
        if hasattr(widget, 'winfo_children'):
            for child in widget.winfo_children():
                self._set_widget_state_recursive(child, state)
    
    def _update_resize_options_state(self, *args):
        """リサイズオプション状態を更新（集約版）"""
        try:
            # 防御的コーディング: resize_enabledがStringVarか文字列かを判定
            resize_var = self.parent.resize_enabled
            if hasattr(resize_var, 'get'):
                enabled = resize_var.get() == "on"
            else:
                enabled = resize_var == "on"  # 既に文字列の場合
            # リサイズ詳細は常に表示
        except Exception as e:
            self.parent.log(f"リサイズオプション状態更新エラー: {e}", "error")
    
    def _update_advanced_options_state(self, *args):
        """高度なオプション状態を更新（修正版）"""
        try:
            enabled = self.parent.advanced_options_enabled.get()
            # 常時エラー対策オプションは常に表示（レジュームタブに移動予定）
            if hasattr(self, 'advanced_content_frame'):
                # 常時エラー対策オプションは常に有効
                state = 'normal'
                self._set_widget_state_recursive(self.advanced_content_frame, state)
        except Exception as e:
            self.parent.log(f"高度なオプション状態更新エラー: {e}", "error")
    
    def _update_incomplete_folder_options_state(self, *args):
        """未完了フォルダオプション状態を更新（集約版）"""
        try:
            # 防御的コーディング: rename_incomplete_folderがBooleanVarかboolかを判定
            incomplete_var = self.parent.rename_incomplete_folder
            if hasattr(incomplete_var, 'get'):
                enabled = incomplete_var.get()
            else:
                enabled = incomplete_var  # 既にboolの場合
            # 常に有効にする
            if hasattr(self.parent, 'incomplete_folder_prefix_entry'):
                self.parent.incomplete_folder_prefix_entry.config(state='normal')
        except Exception as e:
            self.parent.log(f"未完了フォルダオプション状態更新エラー: {e}", "error")
    
    def _update_string_conversion_state(self, *args):
        """文字列変換状態を更新（集約版）"""
        try:
            enabled = self.parent.string_conversion_enabled.get()
            # 常に表示する
        except Exception as e:
            self.parent.log(f"文字列変換状態更新エラー: {e}", "error")
    
    def _update_auto_resume_options_state(self, *args):
        """自動再開オプション状態を更新（修正版）"""
        try:
            # エラー処理がOFFのとき、枠内の要素をグレーアウト
            error_handling_enabled = self.parent.error_handling_enabled.get()
            
            # ⭐修正: 保存されたウィジェット参照を使用⭐
            if hasattr(self.parent, 'options_panel') and hasattr(self.parent.options_panel, 'resume_option_widgets'):
                is_enabled = error_handling_enabled
                state = 'normal' if is_enabled else 'disabled'
                
                # 保存されたウィジェットの状態を更新
                for widget in self.parent.options_panel.resume_option_widgets:
                    try:
                        if hasattr(widget, 'config'):
                            widget.config(state=state)
                        elif hasattr(widget, 'configure'):
                            widget.configure(state=state)
                    except Exception as e:
                        # エラーは無視（ウィジェットが存在しない場合など）
                        pass
        except Exception as e:
            # エラーは無視
            pass
    
    def _update_compression_options_state(self, *args):
        """圧縮オプション状態を更新（集約版）"""
        try:
            # 防御的コーディング: compression_enabledがStringVarか文字列かを判定
            comp_var = self.parent.compression_enabled
            if hasattr(comp_var, 'get'):
                enabled = comp_var.get() == "on"
            else:
                enabled = comp_var == "on"  # 既に文字列の場合
            if hasattr(self.parent, 'compression_delete_original_cb'):
                self.parent.compression_delete_original_cb.config(state='normal' if enabled else 'disabled')
        except Exception as e:
            self.parent.log(f"圧縮オプション状態更新エラー: {e}", "error")
    
    def _update_folder_name_state(self, *args):
        """フォルダ名状態を更新（集約版）"""
        try:
            if hasattr(self.parent, 'custom_folder_name_entry'):
                state = 'normal' if self.parent.folder_name_mode.get() == "custom" else 'disabled'
                self.parent.custom_folder_name_entry.config(state=state)
        except Exception as e:
            self.parent.log(f"フォルダ名状態更新エラー: {e}", "error")
    
    def _update_first_page_naming_state(self, *args):
        """1ページ目命名状態を更新（集約版）"""
        try:
            if hasattr(self.parent, 'first_page_naming_entry'):
                state = 'normal' if self.parent.first_page_naming_enabled.get() else 'disabled'
                self.parent.first_page_naming_entry.config(state=state)
        except Exception as e:
            self.parent.log(f"1ページ目命名状態更新エラー: {e}", "error")
    
    def _update_skip_count_state(self, *args):
        """スキップ回数状態を更新（集約版）"""
        try:
            if hasattr(self.parent, 'skip_count_entry'):
                skip_enabled = (hasattr(self.parent, 'skip_after_count_enabled') and self.parent.skip_after_count_enabled.get()) or \
                              (hasattr(self.parent, 'duplicate_file_mode') and self.parent.duplicate_file_mode.get() == 'skip')
                state = 'normal' if skip_enabled else 'disabled'
                self.parent.skip_count_entry.config(state=state)
        except Exception as e:
            self.parent.log(f"スキップ回数状態更新エラー: {e}", "error")
    
    def _update_custom_name_entry_state(self, *args):
        """カスタム名入力状態を更新（集約版）"""
        try:
            if hasattr(self.parent, 'custom_name_entry'):
                enabled = self.parent.save_name.get() == "custom_name"
                self.parent.custom_name_entry.config(state='normal' if enabled else 'disabled')
        except Exception as e:
            self.parent.log(f"カスタム名入力状態更新エラー: {e}", "error")

class EHDownloaderOptionsPanel:
    def __init__(self, parent):
        self.parent = parent
        self.ui_bridge = None  # ⭐Phase 1.5: ThreadSafeUIBridge参照⭐
        # 状態管理クラスを初期化
        self.state_manager = OptionsStateManager(parent)
        # 文字列変換ルールのリストを初期化
        
        # オプション背景色管理システム
        self.option_frames = {}  # オプション変数名 -> フレームのマッピング
        
        # オプション詳細項目グレーアウト管理システム
        self.option_detail_items = {}  # オプション変数名 -> 詳細項目のリスト
        self.string_conversion_rules = []
    
    def _update_gui_for_running(self):
        """実行中のGUI更新"""
        try:
            # 実行ボタン → 実行中はグレーアウト
            if hasattr(self, 'start_btn'):
                self.start_btn.config(state='disabled')
            # 中断ボタン → 実行中のみ有効
            if hasattr(self, 'pause_btn'):
                self.pause_btn.config(state='normal')
            # 再開ボタン → 実行中は無効
            if hasattr(self, 'resume_btn'):
                self.resume_btn.config(state='disabled')
            # リスタート・スキップ → 実行中は有効
            if hasattr(self, 'restart_btn'):
                self.restart_btn.config(state='normal')
            if hasattr(self, 'skip_btn'):
                self.skip_btn.config(state='normal')
            # クリア → 常に操作可能
            if hasattr(self, 'clear_btn'):
                self.clear_btn.config(state='normal')
            # ページを開く・フォルダを開く → 実行中は有効
            if hasattr(self, 'open_page_btn'):
                self.open_page_btn.config(state='normal')
            if hasattr(self, 'open_folder_btn'):
                self.open_folder_btn.config(state='normal')
        except Exception as e:
            self.parent.log(f"GUI更新エラー (running): {e}", "error")
    
    def _update_gui_for_idle(self):
        """アイドル時GUI更新"""
        try:
            # 実行ボタン → アイドル時は有効
            if hasattr(self, 'start_btn'):
                self.start_btn.config(state='normal')
            # 中断ボタン → 実行中以外はグレーアウト
            if hasattr(self, 'pause_btn'):
                self.pause_btn.config(state='disabled')
            # 再開ボタン → 中断状態以外はグレーアウト
            if hasattr(self, 'resume_btn'):
                self.resume_btn.config(state='disabled')
            # リスタート・スキップ → 初期状態ではグレーアウト
            if hasattr(self, 'restart_btn'):
                self.restart_btn.config(state='disabled')
            if hasattr(self, 'skip_btn'):
                self.skip_btn.config(state='disabled')
            # クリア → 常に操作可能
            if hasattr(self, 'clear_btn'):
                self.clear_btn.config(state='normal')
            # ページを開く・フォルダを開く → アイドル時も有効（最後の状態を保持）
            if hasattr(self, 'open_page_btn'):
                self.open_page_btn.config(state='normal')
            if hasattr(self, 'open_folder_btn'):
                self.open_folder_btn.config(state='normal')
        except Exception as e:
            self.parent.log(f"GUI更新エラー (idle): {e}", "error")
    
    def _update_gui_for_error(self):
        """エラー状態のGUI更新（中断状態として扱う）"""
        try:
            # 実行ボタン → エラー時は無効
            if hasattr(self, 'start_btn'):
                self.start_btn.config(state='disabled')
            # 中断ボタン → エラー時は無効
            if hasattr(self, 'pause_btn'):
                self.pause_btn.config(state='disabled')
            # 再開ボタン → 中断状態では有効
            if hasattr(self, 'resume_btn'):
                self.resume_btn.config(state='normal')
            # リスタート・スキップ → エラー時は有効
            if hasattr(self, 'restart_btn'):
                self.restart_btn.config(state='normal')
            if hasattr(self, 'skip_btn'):
                self.skip_btn.config(state='normal')
            # クリア → 常に操作可能
            if hasattr(self, 'clear_btn'):
                self.clear_btn.config(state='normal')
            # ページを開く・フォルダを開く → エラー時は有効（最後の状態を保持）
            if hasattr(self, 'open_page_btn'):
                self.open_page_btn.config(state='normal')
            if hasattr(self, 'open_folder_btn'):
                self.open_folder_btn.config(state='normal')
        except Exception as e:
            self.parent.log(f"GUI更新エラー (error): {e}", "error")
    
    def _update_gui_for_paused(self):
        """一時停止状態のGUI更新"""
        try:
            # 実行ボタン → 一時停止時は無効
            if hasattr(self, 'start_btn'):
                self.start_btn.config(state='disabled')
            # 中断ボタン → 一時停止時は無効
            if hasattr(self, 'pause_btn'):
                self.pause_btn.config(state='disabled')
            # 再開ボタン → 中断状態では有効
            if hasattr(self, 'resume_btn'):
                self.resume_btn.config(state='normal')
            # リスタート・スキップ → 一時停止時は有効
            if hasattr(self, 'restart_btn'):
                self.restart_btn.config(state='normal')
            if hasattr(self, 'skip_btn'):
                self.skip_btn.config(state='normal')
            # クリア → 常に操作可能
            if hasattr(self, 'clear_btn'):
                self.clear_btn.config(state='normal')
            # ページを開く・フォルダを開く → 一時停止時は有効（最後の状態を保持）
            if hasattr(self, 'open_page_btn'):
                self.open_page_btn.config(state='normal')
            if hasattr(self, 'open_folder_btn'):
                self.open_folder_btn.config(state='normal')
        except Exception as e:
            self.parent.log(f"GUI更新エラー (paused): {e}", "error")
    
    def _toggle_download_manager(self):
        """ダウンロードマネージャー起動のON/OFFを切り替え"""
        current_state = self.parent.progress_separate_window_enabled.get()
        new_state = not current_state
        self.parent.progress_separate_window_enabled.set(new_state)
        
        # ⭐修正: 新しい状態に応じてウィンドウを表示/非表示⭐
        if hasattr(self.parent, 'progress_panel') and hasattr(self.parent.progress_panel, 'progress_manager'):
            progress_manager = self.parent.progress_panel.progress_manager
            if progress_manager:
                if new_state:
                    # ONにする: ダウンロードマネージャーを表示
                    progress_manager.show_separate_window()
                else:
                    # OFFにする: ダウンロードマネージャーを非表示
                    progress_manager.hide_separate_window()
        
        self._update_download_manager_button_state()
    
    def _update_download_manager_button_state(self):
        """ダウンロードマネージャーボタンの状態を更新"""
        if hasattr(self, 'download_manager_toggle_btn'):
            # ⭐修正: progress_separate_window_enabledの状態でボタン表示を制御⭐
            enabled = hasattr(self.parent, 'progress_separate_window_enabled') and self.parent.progress_separate_window_enabled.get()
            
            # 有効になっている場合: 濃い灰色
            if enabled:
                # ウィンドウが存在する場合: 濃い灰色
                self.download_manager_toggle_btn.configure(
                    bg="#808080",  # 濃い灰色
                    fg="white",
                    relief="raised"
                )
            else:
                # ウィンドウが存在しない場合: 通常の背景色
                self.download_manager_toggle_btn.configure(
                    bg="SystemButtonFace",
                    fg="black",
                    relief="raised"
                )
        
    def create_options_panel(self, parent_pane):
        """オプションパネルを作成"""
        options_container = ttk.Frame(parent_pane)
        parent_pane.add(options_container)
        options_container.grid_rowconfigure(1, weight=1)
        options_container.grid_columnconfigure(0, weight=1)

        # ボタンフレーム
        button_frame = ttk.Frame(options_container)
        button_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        button_frame.grid_columnconfigure(1, weight=1)

        left_button_frame = ttk.Frame(button_frame)
        left_button_frame.grid(row=0, column=0, sticky="nw")

        self.start_btn = ttk.Button(left_button_frame, text="実行", command=self.parent.start_download_sequence, style="BigButton.TButton")
        self.start_btn.config(width=12)
        self.start_btn.grid(row=0, column=0, padx=5, pady=2, sticky="n")
        ToolTip(self.start_btn, TOOLTIP_TEXTS['start_btn'])

        pause_resume_frame = ttk.Frame(button_frame)
        pause_resume_frame.grid(row=0, column=1, sticky="nw", padx=(10,0))

        self.pause_btn = ttk.Button(pause_resume_frame, text="中断", command=lambda: self.parent.download_controller.pause_download(), state='disabled', width=9, style="MediumButton.TButton")
        self.pause_btn.grid(row=0, column=0, padx=2, pady=2, sticky="n")
        ToolTip(self.pause_btn, TOOLTIP_TEXTS['pause_btn'])
        
        self.resume_btn = ttk.Button(pause_resume_frame, text="再開", command=lambda: self.parent.download_controller.resume_download(), state='disabled', width=9, style="MediumButton.TButton")
        self.resume_btn.grid(row=0, column=1, padx=2, pady=2, sticky="n")
        ToolTip(self.resume_btn, TOOLTIP_TEXTS['resume_btn'])

        right_button_frame = ttk.Frame(button_frame)
        right_button_frame.grid(row=0, column=2, sticky="e")

        action_button_frame = ttk.Frame(right_button_frame)
        action_button_frame.grid(row=0, column=0, sticky="e", padx=5, pady=2)
        self.restart_btn = ttk.Button(action_button_frame, text="リスタート", command=lambda: self.parent.download_controller.restart_download(), state='disabled', width=12)
        self.restart_btn.pack(side="left", padx=2)
        ToolTip(self.restart_btn, TOOLTIP_TEXTS['restart_btn'])
        
        self.skip_btn = ttk.Button(action_button_frame, text="スキップ", command=self.parent.skip_current_download, state='disabled', width=12)
        self.skip_btn.pack(side="left", padx=2)
        ToolTip(self.skip_btn, TOOLTIP_TEXTS['skip_btn'])
        
        self.clear_btn = ttk.Button(action_button_frame, text="クリア", command=self.parent.clear_all_data, width=12)
        self.clear_btn.pack(side="left", padx=2)
        ToolTip(self.clear_btn, TOOLTIP_TEXTS['clear_btn'])

        open_button_frame = ttk.Frame(right_button_frame)
        open_button_frame.grid(row=1, column=0, sticky="e", padx=5, pady=2)
        self.open_page_btn = ttk.Button(open_button_frame, text="ページを開く", command=self.parent.open_current_image_page, state='disabled', width=12)
        self.open_page_btn.pack(side="left", padx=2)
        ToolTip(self.open_page_btn, TOOLTIP_TEXTS['open_page_btn'])
        
        self.open_folder_btn = ttk.Button(open_button_frame, text="フォルダを開く", command=self.parent.open_current_download_folder, state='disabled', width=12)
        self.open_folder_btn.pack(side="left", padx=2)
        ToolTip(self.open_folder_btn, TOOLTIP_TEXTS['open_folder_btn'])

        # タブ構造のオプション設定エリア
        self.options_notebook = ttk.Notebook(options_container)
        self.options_notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=0)
        
        # 各タブを作成
        self._create_basic_settings_tab()
        self._create_image_editing_tab()
        self._create_resume_tab()  # 旧「高度なオプション」→「レジューム」
        self._create_other_tab()   # 新規追加
        
        # 設定ボタンフレーム（オプションパネル内の右下に配置）
        settings_button_frame = ttk.Frame(options_container)
        settings_button_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        settings_button_frame.grid_columnconfigure(0, weight=1)
        
        # 右寄せでボタンを配置
        settings_buttons = ttk.Frame(settings_button_frame)
        settings_buttons.grid(row=0, column=0, sticky="e")
        
        ttk.Button(settings_buttons, text="デフォルトに戻す", command=self.parent._reset_to_defaults, width=15).grid(row=0, column=0, padx=2)
        
        # ダウンロードマネージャーボタンを追加
        self.download_manager_toggle_btn = tk.Button(settings_buttons, text="ダウンロードマネージャー", 
                                                   command=self._toggle_download_manager, width=20,
                                                   relief="raised", bg="SystemButtonFace")
        self.download_manager_toggle_btn.grid(row=0, column=1, padx=2)
        
        # 初期状態を設定
        self._update_download_manager_button_state()
    
    def _create_basic_settings_tab(self):
        """基本設定タブを作成"""
        # 基本設定タブ
        basic_tab = ttk.Frame(self.options_notebook)
        self.options_notebook.add(basic_tab, text="基本設定")
        
        # スクロール可能なフレーム
        basic_scrollable_frame = ttk.Frame(basic_tab)
        basic_scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.basic_canvas = tk.Canvas(basic_scrollable_frame, borderwidth=0, highlightthickness=0)
        self.basic_canvas.pack(side="left", fill="both", expand=True)
        basic_scrollbar_y = ttk.Scrollbar(basic_scrollable_frame, orient="vertical", command=self.basic_canvas.yview)
        basic_scrollbar_y.pack(side="right", fill="y")
        self.basic_canvas.configure(yscrollcommand=basic_scrollbar_y.set)
        
        self.basic_frame_inner = ttk.Frame(self.basic_canvas)
        self.basic_canvas.create_window((0, 0), window=self.basic_frame_inner, anchor="nw")
        
        # スクロール機能の設定
        self._setup_basic_scroll_functionality()
        
        # 基本設定の内容を作成
        self._create_basic_settings_content()
    
    def _create_image_editing_tab(self):
        """特殊設定タブを作成"""
        # 特殊設定タブ
        image_tab = ttk.Frame(self.options_notebook)
        self.options_notebook.add(image_tab, text="特殊設定")
        
        # スクロール可能なフレーム
        image_scrollable_frame = ttk.Frame(image_tab)
        image_scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.image_canvas = tk.Canvas(image_scrollable_frame, borderwidth=0, highlightthickness=0)
        self.image_canvas.pack(side="left", fill="both", expand=True)
        image_scrollbar_y = ttk.Scrollbar(image_scrollable_frame, orient="vertical", command=self.image_canvas.yview)
        image_scrollbar_y.pack(side="right", fill="y")
        self.image_canvas.configure(yscrollcommand=image_scrollbar_y.set)
        
        self.image_frame_inner = ttk.Frame(self.image_canvas)
        self.image_canvas.create_window((0, 0), window=self.image_frame_inner, anchor="nw")
        
        # スクロール機能の設定
        self._setup_image_scroll_functionality()
        
        # 特殊設定の内容を作成
        self._create_image_editing_content()
    
    def _create_resume_tab(self):
        """レジュームタブを作成（旧「高度なオプション」）"""
        # レジュームタブ
        resume_tab = ttk.Frame(self.options_notebook)
        self.options_notebook.add(resume_tab, text="レジューム")
        
        # スクロール可能なフレーム
        resume_scrollable_frame = ttk.Frame(resume_tab)
        resume_scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.resume_canvas = tk.Canvas(resume_scrollable_frame, borderwidth=0, highlightthickness=0)
        self.resume_canvas.pack(side="left", fill="both", expand=True)
        resume_scrollbar_y = ttk.Scrollbar(resume_scrollable_frame, orient="vertical", command=self.resume_canvas.yview)
        resume_scrollbar_y.pack(side="right", fill="y")
        self.resume_canvas.configure(yscrollcommand=resume_scrollbar_y.set)
        
        self.resume_frame_inner = ttk.Frame(self.resume_canvas)
        self.resume_canvas.create_window((0, 0), window=self.resume_frame_inner, anchor="nw")
        
        # スクロール機能の設定
        self._setup_resume_scroll_functionality()
        
        # レジュームタブの内容を作成
        self._create_resume_content()
    
    def _setup_basic_scroll_functionality(self):
        """基本設定タブのスクロール機能を設定"""
        def _configure_scroll_region(event):
            self.basic_canvas.configure(scrollregion=self.basic_canvas.bbox("all"))
            canvas_width = event.width
            # ウィンドウが存在する場合のみ幅を設定
            canvas_items = self.basic_canvas.find_all()
            if canvas_items:
                self.basic_canvas.itemconfig(canvas_items[0], width=canvas_width)

        def _on_mousewheel(event):
            if event.delta:
                self.basic_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            else:
                if event.num == 4:
                    self.basic_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.basic_canvas.yview_scroll(1, "units")

        def bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_mousewheel_recursive(child)

        self.basic_frame_inner.bind("<Configure>", _configure_scroll_region)
        self.basic_canvas.bind("<Configure>", _configure_scroll_region)
        self.basic_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.basic_canvas.bind("<Button-4>", _on_mousewheel)
        self.basic_canvas.bind("<Button-5>", _on_mousewheel)
        bind_mousewheel_recursive(self.basic_frame_inner)
    
    def _setup_image_scroll_functionality(self):
        """特殊設定タブのスクロール機能を設定"""
        def _configure_scroll_region(event):
            self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))
            canvas_width = event.width
            # ウィンドウが存在する場合のみ幅を設定
            canvas_items = self.image_canvas.find_all()
            if canvas_items:
                self.image_canvas.itemconfig(canvas_items[0], width=canvas_width)

        def _on_mousewheel(event):
            if event.delta:
                self.image_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            else:
                if event.num == 4:
                    self.image_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.image_canvas.yview_scroll(1, "units")

        def bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_mousewheel_recursive(child)

        self.image_frame_inner.bind("<Configure>", _configure_scroll_region)
        self.image_canvas.bind("<Configure>", _configure_scroll_region)
        self.image_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.image_canvas.bind("<Button-4>", _on_mousewheel)
        self.image_canvas.bind("<Button-5>", _on_mousewheel)
        bind_mousewheel_recursive(self.image_frame_inner)
    
    def _setup_resume_scroll_functionality(self):
        """レジュームタブのスクロール機能を設定"""
        def _configure_scroll_region(event):
            self.resume_canvas.configure(scrollregion=self.resume_canvas.bbox("all"))
            canvas_width = event.width
            # ウィンドウが存在する場合のみ幅を設定
            canvas_items = self.resume_canvas.find_all()
            if canvas_items:
                self.resume_canvas.itemconfig(canvas_items[0], width=canvas_width)

        def _on_mousewheel(event):
            if event.delta:
                self.resume_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            else:
                if event.num == 4:
                    self.resume_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.resume_canvas.yview_scroll(1, "units")

        def bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_mousewheel_recursive(child)

        self.resume_frame_inner.bind("<Configure>", _configure_scroll_region)
        self.resume_canvas.bind("<Configure>", _configure_scroll_region)
        self.resume_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.resume_canvas.bind("<Button-4>", _on_mousewheel)
        self.resume_canvas.bind("<Button-5>", _on_mousewheel)
        bind_mousewheel_recursive(self.resume_frame_inner)
    
    def _create_other_tab(self):
        """その他タブを作成"""
        # その他タブ
        other_tab = ttk.Frame(self.options_notebook)
        self.options_notebook.add(other_tab, text="その他")
        
        # スクロール可能なフレーム
        other_scrollable_frame = ttk.Frame(other_tab)
        other_scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.other_canvas = tk.Canvas(other_scrollable_frame, borderwidth=0, highlightthickness=0)
        self.other_canvas.pack(side="left", fill="both", expand=True)
        other_scrollbar_y = ttk.Scrollbar(other_scrollable_frame, orient="vertical", command=self.other_canvas.yview)
        other_scrollbar_y.pack(side="right", fill="y")
        self.other_canvas.configure(yscrollcommand=other_scrollbar_y.set)
        
        self.other_frame_inner = ttk.Frame(self.other_canvas)
        self.other_canvas.create_window((0, 0), window=self.other_frame_inner, anchor="nw")
        
        # スクロール機能の設定
        self._setup_other_scroll_functionality()
        
        # その他タブの内容を作成
        self._create_other_content()
    
    def _setup_other_scroll_functionality(self):
        """その他タブのスクロール機能を設定"""
        def _configure_scroll_region(event):
            self.other_canvas.configure(scrollregion=self.other_canvas.bbox("all"))
            canvas_width = event.width
            # ウィンドウが存在する場合のみ幅を設定
            canvas_items = self.other_canvas.find_all()
            if canvas_items:
                self.other_canvas.itemconfig(canvas_items[0], width=canvas_width)

        def _on_mousewheel(event):
            if event.delta:
                self.other_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            else:
                if event.num == 4:
                    self.other_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.other_canvas.yview_scroll(1, "units")

        def bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)
            widget.bind("<Button-5>", _on_mousewheel)
            for child in widget.winfo_children():
                bind_mousewheel_recursive(child)

        self.other_frame_inner.bind("<Configure>", _configure_scroll_region)
        self.other_canvas.bind("<Configure>", _configure_scroll_region)
        self.other_canvas.bind("<MouseWheel>", _on_mousewheel)
        self.other_canvas.bind("<Button-4>", _on_mousewheel)
        self.other_canvas.bind("<Button-5>", _on_mousewheel)
        bind_mousewheel_recursive(self.other_frame_inner)
    
    def _create_other_content(self):
        """その他タブの内容を作成"""
        # 左右のフレームを水平に配置（幅を450pxに固定）
        columns_frame = ttk.Frame(self.other_frame_inner)
        columns_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # 各カラムを450pxの固定幅に設定
        columns_frame.grid_columnconfigure(0, weight=0, minsize=450)
        columns_frame.grid_columnconfigure(1, weight=0, minsize=450)
        
        # 左右のカラムを作成（450px固定幅）
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        left_column.grid_columnconfigure(0, weight=1)
        
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        right_column.grid_columnconfigure(0, weight=1)
        
        # 左カラム: DLリストのサムネイル表示、プログレスバーの表示制限
        self._create_other_left_column(left_column)
        
        # 右カラム: プログレスバーのログ保存、DLログの保存
        self._create_other_right_column(right_column)
    
    def _create_other_left_column(self, parent):
        """その他タブの左カラムを作成"""
        # DLリストのサムネイル表示とプログレスバーの表示制限は右カラムに移動したため、左カラムは空
        
        # Selenium管理
        selenium_management_frame = ttk.LabelFrame(parent, text="Selenium管理")
        selenium_management_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        # Selenium説明文
        selenium_desc = ttk.Label(selenium_management_frame, text="本物のブラウザを自動操作してダウンロードします。\nChromeブラウザとChromeDriverが必要です。", 
                                 foreground="blue", font=("Tahoma", 8))
        selenium_desc.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        # Selenium管理フレーム
        selenium_soft_frame = ttk.LabelFrame(selenium_management_frame, text="Selenium")
        selenium_soft_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        selenium_buttons_frame = ttk.Frame(selenium_soft_frame)
        selenium_buttons_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        
        # ソフト更新ボタン
        selenium_update_btn = ttk.Button(selenium_buttons_frame, text="ソフト更新", 
                                         command=self.parent._update_selenium_software, width=12)
        selenium_update_btn.grid(row=0, column=0, padx=2, pady=2)
        ToolTip(selenium_update_btn, "Seleniumをインストールまたは最新版に更新します。\n未インストールの場合はインストール、インストール済みの場合は最新版に更新します。")
        
        # ソフト情報ボタン
        selenium_info_btn = ttk.Button(selenium_buttons_frame, text="ソフト情報", 
                                      command=self.parent._show_selenium_info, width=12)
        selenium_info_btn.grid(row=0, column=1, padx=2, pady=2)
        ToolTip(selenium_info_btn, "現在のSeleniumのバージョンを表示します。")
        
        # ソフト削除ボタン
        selenium_remove_btn = ttk.Button(selenium_buttons_frame, text="ソフト削除", 
                                         command=self.parent._remove_selenium_software, width=12)
        selenium_remove_btn.grid(row=0, column=2, padx=2, pady=2)
        ToolTip(selenium_remove_btn, "Seleniumパッケージをアンインストールします。")
        
        # Chromeドライバ管理フレーム
        chrome_driver_frame = ttk.LabelFrame(selenium_management_frame, text="Chromeドライバ")
        chrome_driver_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        driver_buttons_frame = ttk.Frame(chrome_driver_frame)
        driver_buttons_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        
        # ドライバ更新ボタン
        update_btn = ttk.Button(driver_buttons_frame, text="ドライバ更新", 
                               command=self.parent._update_chrome_driver, width=12)
        update_btn.grid(row=0, column=0, padx=2, pady=2)
        ToolTip(update_btn, "現在のChromeのバージョンに完全に適合したChromeDriverをインストールします。\n最新版ではなく、現在のChromeバージョンに対応したものをインストールします。")
        
        # ドライバ情報ボタン
        info_btn = ttk.Button(driver_buttons_frame, text="ドライバ情報", 
                             command=self.parent._show_driver_info, width=12)
        info_btn.grid(row=0, column=1, padx=2, pady=2)
        ToolTip(info_btn, "現在のChromeDriverとChromeのバージョンを表示します。")
        
        # ドライバ削除ボタン
        remove_btn = ttk.Button(driver_buttons_frame, text="ドライバ削除", 
                               command=self.parent._remove_driver, width=12)
        remove_btn.grid(row=0, column=2, padx=2, pady=2)
        ToolTip(remove_btn, "ChromeDriverファイルを削除します。")

        # Seleniumオプション
        selenium_options_frame = ttk.LabelFrame(parent, text="Seleniumオプション")
        selenium_options_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        
        # Seleniumオプション全体のON/OFF
        if not hasattr(self.parent, 'selenium_options_enabled'):
            self.parent.selenium_options_enabled = tk.BooleanVar(value=False)
        selenium_options_onoff_frame = ttk.Frame(selenium_options_frame)
        selenium_options_onoff_frame.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        # ON/OFFフレームへの参照を保持
        self.selenium_options_onoff_frame = selenium_options_onoff_frame
        ttk.Radiobutton(selenium_options_onoff_frame, text="OFF", value=False,
                       variable=self.parent.selenium_options_enabled,
                       command=self._update_selenium_options_state).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(selenium_options_onoff_frame, text="ON", value=True,
                       variable=self.parent.selenium_options_enabled,
                       command=self._update_selenium_options_state).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        ToolTip(selenium_options_onoff_frame, "Seleniumオプション全体の有効/無効を切り替えます。\nOFFの場合は以下のすべてのオプションが無効化されます。")
        
        # Seleniumオプションフレームへの参照を保持（後で状態更新に使用）
        self.selenium_options_frame = selenium_options_frame
        
        # ⭐追加: 最小限のオプションで起動（競合回避用）⭐
        if not hasattr(self.parent, 'selenium_minimal_options'):
            self.parent.selenium_minimal_options = tk.BooleanVar(value=False)
        minimal_options_check = ttk.Checkbutton(selenium_options_frame, text="最小限のオプションで起動（推奨:競合回避用）", 
                                               variable=self.parent.selenium_minimal_options)
        minimal_options_check.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ToolTip(minimal_options_check, "最小限のChromeオプションで起動します（古いバージョンと同じシンプルな実装）。\n--user-data-dirや--remote-debugging-portを使用せず、既存のChromeプロセスとの競合を避けます。\n起動エラーが発生する場合に有効です。")
        
        # Selenium Managerを使用するオプション
        if not hasattr(self.parent, 'selenium_manager_enabled'):
            self.parent.selenium_manager_enabled = tk.BooleanVar(value=False)
        selenium_manager_check = ttk.Checkbutton(selenium_options_frame, text="Selenium Managerを使用", 
                                                 variable=self.parent.selenium_manager_enabled)
        selenium_manager_check.grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ToolTip(selenium_manager_check, "Selenium 4.6以降のSelenium Managerを使用してChromeDriverを自動管理します。\n従来のwebdriver-managerの代わりに使用できます。\nより安定した動作が期待できます。")
        
        # Chromeのバックグラウンドプロセスを停止
        if not hasattr(self.parent, 'selenium_stop_chrome_background'):
            self.parent.selenium_stop_chrome_background = tk.BooleanVar(value=False)
        stop_chrome_bg_check = ttk.Checkbutton(selenium_options_frame, text="Chromeのバックグラウンドプロセスを停止", 
                                               variable=self.parent.selenium_stop_chrome_background)
        stop_chrome_bg_check.grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ToolTip(stop_chrome_bg_check, "Selenium起動前にChromeのバックグラウンドプロセスを停止します。\nChromeの自動更新プロセスなどが起動している場合に有効です。\nバージョン取得エラーや起動エラーの回避に役立ちます。")
        
        # 一時ディレクトリクリーンアップ（カスタムパス指定の上に移動）
        if not hasattr(self.parent, 'selenium_cleanup_temp'):
            self.parent.selenium_cleanup_temp = tk.BooleanVar(value=False)
        cleanup_check = ttk.Checkbutton(selenium_options_frame, text="起動前に一時ディレクトリをクリーンアップ", 
                                        variable=self.parent.selenium_cleanup_temp)
        cleanup_check.grid(row=4, column=0, sticky="w", padx=5, pady=2)
        ToolTip(cleanup_check, "Seleniumが作成した一時ディレクトリを起動前に削除します。\n壊れたプロファイルの影響を避けるために使用します。\n通常のダウンロードでも有効です。")
        
        # レジストリからバージョンを取得
        if not hasattr(self.parent, 'selenium_use_registry_version'):
            self.parent.selenium_use_registry_version = tk.BooleanVar(value=True)
        registry_version_check = ttk.Checkbutton(selenium_options_frame, text="レジストリからChromeバージョンを取得", 
                                                 variable=self.parent.selenium_use_registry_version)
        registry_version_check.grid(row=5, column=0, sticky="w", padx=5, pady=2)
        ToolTip(registry_version_check, "Chromeのバージョンをレジストリから取得します。\n既存のChromeプロセスが多い場合、--versionの実行がタイムアウトするのを回避します。\n推奨: ONのまま")
        
        # カスタムパス機能のON/OFF
        if not hasattr(self.parent, 'selenium_custom_paths_enabled'):
            self.parent.selenium_custom_paths_enabled = tk.BooleanVar(value=False)
        custom_paths_onoff_frame = ttk.Frame(selenium_options_frame)
        custom_paths_onoff_frame.grid(row=6, column=0, sticky="ew", padx=5, pady=2)
        # カスタムパスON/OFFフレームへの参照を保持
        self.custom_paths_onoff_frame = custom_paths_onoff_frame
        ttk.Label(custom_paths_onoff_frame, text="カスタムパス指定:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Radiobutton(custom_paths_onoff_frame, text="OFF", value=False,
                       variable=self.parent.selenium_custom_paths_enabled,
                       command=self._update_selenium_paths_options).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(custom_paths_onoff_frame, text="ON", value=True,
                       variable=self.parent.selenium_custom_paths_enabled,
                       command=self._update_selenium_paths_options).grid(row=0, column=2, sticky="w", padx=2, pady=2)
        ToolTip(custom_paths_onoff_frame, "ChromeDriverとChromeのパスを手動で指定できます。\nOFFの場合は自動検出を使用します。")
        
        # ChromeDriverパス指定
        driver_path_frame = ttk.Frame(selenium_options_frame)
        driver_path_frame.grid(row=7, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(driver_path_frame, text="ChromeDriverパス:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'selenium_driver_path'):
            self.parent.selenium_driver_path = tk.StringVar(value="")
        self.selenium_driver_path_entry = ttk.Entry(driver_path_frame, textvariable=self.parent.selenium_driver_path, width=12)
        self.selenium_driver_path_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        driver_path_frame.columnconfigure(1, weight=1)
        
        driver_path_buttons_frame = ttk.Frame(driver_path_frame)
        driver_path_buttons_frame.grid(row=0, column=2, sticky="e", padx=2, pady=2)
        driver_browse_btn = ttk.Button(driver_path_buttons_frame, text="参照", width=8,
                                       command=self._browse_driver_path)
        driver_browse_btn.grid(row=0, column=0, padx=2, pady=2)
        driver_open_btn = ttk.Button(driver_path_buttons_frame, text="開く", width=8,
                                    command=self._open_driver_directory)
        driver_open_btn.grid(row=0, column=1, padx=2, pady=2)
        ToolTip(self.selenium_driver_path_entry, "ChromeDriverのパスを指定します。\n空欄の場合は自動検出を使用します。")
        
        # Chromeパス指定
        chrome_path_frame = ttk.Frame(selenium_options_frame)
        chrome_path_frame.grid(row=8, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(chrome_path_frame, text="Chromeパス:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'selenium_chrome_path'):
            self.parent.selenium_chrome_path = tk.StringVar(value="")
        self.selenium_chrome_path_entry = ttk.Entry(chrome_path_frame, textvariable=self.parent.selenium_chrome_path, width=12)
        self.selenium_chrome_path_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        chrome_path_frame.columnconfigure(1, weight=1)
        
        chrome_path_buttons_frame = ttk.Frame(chrome_path_frame)
        chrome_path_buttons_frame.grid(row=0, column=2, sticky="e", padx=2, pady=2)
        chrome_browse_btn = ttk.Button(chrome_path_buttons_frame, text="参照", width=8,
                                       command=self._browse_chrome_path)
        chrome_browse_btn.grid(row=0, column=0, padx=2, pady=2)
        chrome_open_btn = ttk.Button(chrome_path_buttons_frame, text="開く", width=8,
                                    command=self._open_chrome_directory)
        chrome_open_btn.grid(row=0, column=1, padx=2, pady=2)
        ToolTip(self.selenium_chrome_path_entry, "Chromeブラウザのパスを指定します。\n空欄の場合は自動検出を使用します。")
        
        # 自動入力ボタン
        auto_detect_frame = ttk.Frame(selenium_options_frame)
        auto_detect_frame.grid(row=9, column=0, sticky="ew", padx=5, pady=2)
        auto_detect_btn = ttk.Button(auto_detect_frame, text="自動検出", width=15,
                                    command=self.parent._auto_detect_selenium_paths)
        auto_detect_btn.grid(row=0, column=0, padx=5, pady=2)
        ToolTip(auto_detect_btn, "ChromeDriverとChromeのパスを自動検出して入力します。")
        
        # 初期状態でグレーアウト（OFFがデフォルト）
        self._update_selenium_options_state()
        
        # Seleniumテストモード（Seleniumオプションの下に配置）
        selenium_test_frame = ttk.LabelFrame(parent, text="Seleniumテストモード")
        selenium_test_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=5)
        
        # テストモード説明文
        test_desc = ttk.Label(selenium_test_frame, text="Selenium起動時の問題を診断するためのテストモードです。", 
                             foreground="blue", font=("Tahoma", 8))
        test_desc.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        # テストモードオプション
        test_options_frame = ttk.Frame(selenium_test_frame)
        test_options_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        
        # 最小限オプションで起動
        if not hasattr(self.parent, 'selenium_test_minimal_options'):
            self.parent.selenium_test_minimal_options = tk.BooleanVar(value=False)
        minimal_check = ttk.Checkbutton(test_options_frame, text="最小限のオプションで起動（問題診断用）", 
                                       variable=self.parent.selenium_test_minimal_options)
        minimal_check.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ToolTip(minimal_check, "最小限のChromeオプションで起動します。\nオプションの衝突を避けるために使用します。")
        
        # ヘッドレスモード無効化
        if not hasattr(self.parent, 'selenium_test_no_headless'):
            self.parent.selenium_test_no_headless = tk.BooleanVar(value=False)
        no_headless_check = ttk.Checkbutton(test_options_frame, text="ヘッドレスモードを無効化（ウィンドウ表示）", 
                                            variable=self.parent.selenium_test_no_headless)
        no_headless_check.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ToolTip(no_headless_check, "Chromeウィンドウを表示します。\n起動確認に使用します。")
        
        # テスト実行ボタン
        test_button_frame = ttk.Frame(selenium_test_frame)
        test_button_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        
        test_run_btn = ttk.Button(test_button_frame, text="テスト実行", 
                                 command=self.parent._test_selenium_launch, width=15)
        test_run_btn.grid(row=0, column=0, padx=2, pady=2)
        ToolTip(test_run_btn, "Seleniumを起動して最小限の操作をテストします。\n起動確認と動作確認に使用します。")
    
    def _update_selenium_options_state(self):
        """Seleniumオプション全体の有効/無効を更新"""
        try:
            # Seleniumオプション全体のON/OFF状態を取得
            options_enabled = self.parent.selenium_options_enabled.get() if hasattr(self.parent, 'selenium_options_enabled') else False
            
            # カスタムパス機能のON/OFF状態を取得
            custom_paths_enabled = self.parent.selenium_custom_paths_enabled.get() if hasattr(self.parent, 'selenium_custom_paths_enabled') else False
            
            # 実際の有効/無効状態（両方がONの場合のみ有効）
            enabled = options_enabled and custom_paths_enabled
            
            # パス入力フィールドとボタンの状態を更新
            if hasattr(self, 'selenium_driver_path_entry'):
                self.selenium_driver_path_entry.config(state='normal' if enabled else 'disabled')
            if hasattr(self, 'selenium_chrome_path_entry'):
                self.selenium_chrome_path_entry.config(state='normal' if enabled else 'disabled')
            
            # Seleniumオプションフレーム内のすべての要素を更新
            try:
                if hasattr(self, 'selenium_options_frame'):
                    # フレーム内のすべての要素を更新
                    for option_widget in self.selenium_options_frame.winfo_children():
                        if isinstance(option_widget, ttk.Frame):
                            # ON/OFFフレームは除外（常に有効）
                            if option_widget == getattr(self, 'selenium_options_onoff_frame', None):
                                continue
                            # カスタムパスON/OFFフレームも更新（SeleniumオプションがOFFの場合はグレーアウト）
                            if option_widget == getattr(self, 'custom_paths_onoff_frame', None):
                                # カスタムパスON/OFFフレーム内のラジオボタンを更新
                                # ⭐修正: winfo_children()を呼び出す前にhasattrでチェック⭐
                                if hasattr(option_widget, 'winfo_children'):
                                    for child in option_widget.winfo_children():
                                        if isinstance(child, ttk.Radiobutton):
                                            child.config(state='normal' if options_enabled else 'disabled')
                                continue
                            # フレーム内のウィジェットを再帰的に更新（stateはoptions_enabledを使用）
                            self._update_widget_state_recursive(option_widget, 'normal' if options_enabled else 'disabled')
                        # チェックボタンやその他のウィジェットを直接更新
                        elif isinstance(option_widget, ttk.Checkbutton):
                            option_widget.config(state='normal' if options_enabled else 'disabled')
            except Exception as e:
                self.parent.log(f"SeleniumオプションGUI更新エラー: {e}", "debug")
        except Exception as e:
            self.parent.log(f"Seleniumオプション状態更新エラー: {e}", "error")
    
    def _update_widget_state_recursive(self, widget, state):
        """ウィジェットの状態を再帰的に更新（統一シグネチャ）"""
        try:
            # 自身の状態を更新（ラベルとフレーム以外）
            if not isinstance(widget, (ttk.Label, ttk.Frame, ttk.LabelFrame)) and hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except tk.TclError:
                    pass  # 一部のウィジェットはstate設定不可
            
            # 子要素を再帰的に更新
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    self._update_widget_state_recursive(child, state)
        except Exception as e:
            self.parent.log(f"ウィジェット状態更新エラー: {e}", "debug")
    
    def _update_selenium_paths_options(self):
        """Seleniumパス指定オプションの有効/無効を更新"""
        try:
            enabled = self.parent.selenium_custom_paths_enabled.get() if hasattr(self.parent, 'selenium_custom_paths_enabled') else False
            
            # パス入力フィールドとボタンの状態を更新
            if hasattr(self, 'selenium_driver_path_entry'):
                self.selenium_driver_path_entry.config(state='normal' if enabled else 'disabled')
            if hasattr(self, 'selenium_chrome_path_entry'):
                self.selenium_chrome_path_entry.config(state='normal' if enabled else 'disabled')
            
            # 参照・開くボタンの状態を更新（親フレームから取得）
            try:
                # Seleniumオプションフレームを検索
                # ⭐修正: winfo_children()を呼び出す前にhasattrでチェック⭐
                if hasattr(self.parent, 'winfo_children'):
                    for widget in self.parent.winfo_children():
                        if isinstance(widget, ttk.Frame):
                            for child in widget.winfo_children():
                                if isinstance(child, ttk.LabelFrame) and child.cget('text') == 'Seleniumオプション':
                                    for option_widget in child.winfo_children():
                                        if isinstance(option_widget, ttk.Frame):
                                            for frame_child in option_widget.winfo_children():
                                                # ボタンフレーム内のボタンを検索
                                                if isinstance(frame_child, ttk.Frame):
                                                    for btn in frame_child.winfo_children():
                                                        if isinstance(btn, ttk.Button):
                                                            btn.config(state='normal' if enabled else 'disabled')
                                                # チェックボタンを検索
                                                elif isinstance(frame_child, ttk.Checkbutton):
                                                    check_text = frame_child.cget('text')
                                                    if '一時ディレクトリをクリーンアップ' in check_text:
                                                        frame_child.config(state='normal' if enabled else 'disabled')
            except Exception as e:
                self.parent.log(f"SeleniumオプションGUI更新エラー: {e}", "debug")
        except Exception as e:
            self.parent.log(f"Seleniumパスオプション更新エラー: {e}", "error")
    
    def _browse_driver_path(self):
        """ChromeDriverパスの参照ダイアログ"""
        try:
            from tkinter import filedialog
            initial_dir = ""
            if hasattr(self.parent, 'selenium_driver_path') and self.parent.selenium_driver_path.get():
                initial_dir = os.path.dirname(self.parent.selenium_driver_path.get())
            
            file_path = filedialog.askopenfilename(
                title="ChromeDriverを選択",
                filetypes=[("実行ファイル", "*.exe"), ("すべてのファイル", "*.*")],
                initialdir=initial_dir
            )
            
            if file_path:
                self.parent.selenium_driver_path.set(file_path)
        except Exception as e:
            self.parent.log(f"ChromeDriverパス参照エラー: {e}", "error")
    
    def _browse_chrome_path(self):
        """Chromeパスの参照ダイアログ"""
        try:
            from tkinter import filedialog
            initial_dir = ""
            if hasattr(self.parent, 'selenium_chrome_path') and self.parent.selenium_chrome_path.get():
                initial_dir = os.path.dirname(self.parent.selenium_chrome_path.get())
            
            file_path = filedialog.askopenfilename(
                title="Chromeブラウザを選択",
                filetypes=[("実行ファイル", "*.exe"), ("すべてのファイル", "*.*")],
                initialdir=initial_dir
            )
            
            if file_path:
                self.parent.selenium_chrome_path.set(file_path)
        except Exception as e:
            self.parent.log(f"Chromeパス参照エラー: {e}", "error")
    
    def _open_driver_directory(self):
        """ChromeDriverディレクトリをエクスプローラーで開く"""
        try:
            import subprocess
            import os
            
            driver_path = self.parent.selenium_driver_path.get() if hasattr(self.parent, 'selenium_driver_path') else ""
            
            if driver_path and os.path.exists(driver_path):
                directory = os.path.dirname(driver_path)
                subprocess.Popen(f'explorer "{directory}"')
            elif driver_path:
                self.parent.log(f"ChromeDriverパスが見つかりません: {driver_path}", "warning")
            else:
                # 自動検出して開く
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    driver_path = ChromeDriverManager().install()
                    directory = os.path.dirname(driver_path)
                    subprocess.Popen(f'explorer "{directory}"')
                except Exception as e:
                    self.parent.log(f"ChromeDriverディレクトリを開けませんでした: {e}", "error")
        except Exception as e:
            self.parent.log(f"ChromeDriverディレクトリを開くエラー: {e}", "error")
    
    def _open_chrome_directory(self):
        """Chromeディレクトリをエクスプローラーで開く"""
        try:
            import subprocess
            import os
            
            chrome_path = self.parent.selenium_chrome_path.get() if hasattr(self.parent, 'selenium_chrome_path') else ""
            
            if chrome_path and os.path.exists(chrome_path):
                directory = os.path.dirname(chrome_path)
                subprocess.Popen(f'explorer "{directory}"')
            elif chrome_path:
                self.parent.log(f"Chromeパスが見つかりません: {chrome_path}", "warning")
            else:
                # 自動検出して開く
                chrome_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                ]
                
                for path in chrome_paths:
                    if os.path.exists(path):
                        directory = os.path.dirname(path)
                        subprocess.Popen(f'explorer "{directory}"')
                        return
                
                self.parent.log("Chromeディレクトリが見つかりませんでした", "warning")
        except Exception as e:
            self.parent.log(f"Chromeディレクトリを開くエラー: {e}", "error")
    
    # カスタムディレクトリ機能を削除したため、関連メソッドも削除
    
    def _create_other_right_column(self, parent):
        """その他タブの右カラムを作成"""
        right_row = 0
        
        # DLリストのサムネイル表示オプション（右カラム最上部に移動）
        thumbnail_frame = ttk.LabelFrame(parent, text="DLリストのサムネイル表示")
        thumbnail_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        
        # OFF/ON選択
        thumbnail_onoff_frame = ttk.Frame(thumbnail_frame)
        thumbnail_onoff_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        if not hasattr(self.parent, 'thumbnail_display_enabled'):
            self.parent.thumbnail_display_enabled = tk.StringVar(value="off")
        ttk.Radiobutton(thumbnail_onoff_frame, text="OFF", value="off", variable=self.parent.thumbnail_display_enabled, width=6).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(thumbnail_onoff_frame, text="ON", value="on", variable=self.parent.thumbnail_display_enabled, width=6).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # 初期値を明示的に設定
        self.parent.thumbnail_display_enabled.set("off")
        
        # ツールチップ
        ToolTip(thumbnail_frame, "DLリストのURLにマウスホバーすることで、ギャラリーの最初のサムネイル画像を表示します。")
        
        # プログレスバーの表示制限オプション（右カラムに移動）
        progress_display_frame = ttk.LabelFrame(parent, text="プログレスバーの表示制限")
        progress_display_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        
        # OFF/ON選択
        display_onoff_frame = ttk.Frame(progress_display_frame)
        display_onoff_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        if not hasattr(self.parent, 'progress_display_limit_enabled'):
            self.parent.progress_display_limit_enabled = tk.BooleanVar(value=True)
        ttk.Radiobutton(display_onoff_frame, text="OFF", value=False,
                       variable=self.parent.progress_display_limit_enabled,
                       command=self._update_progress_display_options).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(display_onoff_frame, text="ON", value=True,
                       variable=self.parent.progress_display_limit_enabled,
                       command=self._update_progress_display_options).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # 表示数設定（グレーアウト制御）
        display_count_frame = ttk.Frame(progress_display_frame)
        display_count_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(display_count_frame, text="表示数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'progress_retention_count'):
            self.parent.progress_retention_count = tk.StringVar(value="100")
        self.progress_retention_entry = ttk.Entry(display_count_frame, textvariable=self.parent.progress_retention_count, width=10)
        self.progress_retention_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(display_count_frame, text="件").grid(row=0, column=2, sticky="w", padx=2, pady=2)
        
        # ツールチップ
        ToolTip(progress_display_frame, "指定した件数を超える古いプログレスバーは表示されません。\nOFFにすると表示制限を無効にします。")
        
        # ダウンロード情報の保存オプション
        dl_log_frame = ttk.LabelFrame(parent, text="ダウンロード情報の保存")
        dl_log_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        
        # OFF/ON選択
        dl_log_onoff_frame = ttk.Frame(dl_log_frame)
        dl_log_onoff_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        if not hasattr(self.parent, 'dl_log_enabled'):
            self.parent.dl_log_enabled = tk.BooleanVar(value=False)
        ttk.Radiobutton(dl_log_onoff_frame, text="OFF", value=False,
                       variable=self.parent.dl_log_enabled,
                       command=self._update_dl_log_options).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(dl_log_onoff_frame, text="ON", value=True,
                       variable=self.parent.dl_log_enabled,
                       command=self._update_dl_log_options).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # ダウンロード情報保存方法選択（グレーアウト制御）
        self.dl_log_method_frame = ttk.Frame(dl_log_frame)
        self.dl_log_method_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        if not hasattr(self.parent, 'dl_log_individual_save'):
            self.parent.dl_log_individual_save = tk.BooleanVar(value=False)
        if not hasattr(self.parent, 'dl_log_batch_save'):
            self.parent.dl_log_batch_save = tk.BooleanVar(value=False)
        individual_save_label = ttk.Label(self.dl_log_method_frame, text="個別データを個別フォルダに保存")
        individual_save_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        individual_save_checkbox = ttk.Checkbutton(self.dl_log_method_frame, variable=self.parent.dl_log_individual_save)
        individual_save_checkbox.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        batch_save_label = ttk.Label(self.dl_log_method_frame, text="全てのデータを保存フォルダに保存")
        batch_save_label.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        batch_save_checkbox = ttk.Checkbutton(self.dl_log_method_frame, variable=self.parent.dl_log_batch_save)
        batch_save_checkbox.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        # バックアップファイル形式選択
        dl_log_format_frame = ttk.Frame(dl_log_frame)
        dl_log_format_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        
        format_label = ttk.Label(dl_log_format_frame, text="保存形式:")
        format_label.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        if not hasattr(self.parent, 'dl_log_file_format'):
            self.parent.dl_log_file_format = tk.StringVar(value="HTML")
        
        dl_log_format_combo = ttk.Combobox(dl_log_format_frame, textvariable=self.parent.dl_log_file_format, 
                                          values=["HTML", "JSON", "CSV", "TXT"], 
                                          state="readonly", width=15)
        dl_log_format_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        # ツールチップ
        ToolTip(dl_log_format_combo, "ダウンロード情報の保存形式を選択\n• HTML: ブラウザで表示可能\n• JSON: データ解析・復元に最適\n• CSV: Excel等で開ける表形式\n• TXT: シンプルなテキスト形式")
        
        # ツールチップ
        ToolTip(dl_log_frame, "ダウンロード時の詳細ログを保存します。\n個別データを個別フォルダに保存: 各ギャラリー完了時に個別フォルダにファイルを作成\n全てのデータを保存フォルダに保存: 全ギャラリー完了時またはクリア時に一括保存")
        
        # DLログ保存のグレーアウト管理
        self.register_option_frame('dl_log_enabled', dl_log_frame)
        detail_items = [self.dl_log_method_frame, dl_log_format_frame]
        self.register_option_detail_items('dl_log_enabled', detail_items)
        
        # ⭐削除: プログレスバー永続化オプションを削除（問題1,2対応）⭐
        # プログレスバー情報は外部ファイルに保存しないため、これらのオプションは不要
        pass
    
    def _create_basic_settings_content(self):
        """基本設定タブの内容を作成（指示通りの構成）"""
        # 左右のフレームを水平に配置（幅を450pxに固定）
        columns_frame = ttk.Frame(self.basic_frame_inner)
        columns_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # 各カラムを450pxの固定幅に設定
        columns_frame.grid_columnconfigure(0, weight=0, minsize=450)
        columns_frame.grid_columnconfigure(1, weight=0, minsize=450)
        
        # 左右のカラムを作成（450px固定幅）
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        
        # === 左列オプション（指示通り） ===
        left_row = 0

        # 0. 保存ディレクトリ
        save_frame = ttk.LabelFrame(left_column, text="保存ディレクトリ")
        save_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5)
        left_row += 1
        
        save_inner_frame = ttk.Frame(save_frame)
        save_inner_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        save_inner_frame.grid_columnconfigure(0, weight=1)
        
        folder_entry = ttk.Entry(save_inner_frame, textvariable=self.parent.folder_var, width=30)
        folder_entry.grid(row=0, column=0, sticky="ew", padx=(0,2))
        
        browse_btn = ttk.Button(save_inner_frame, text="参照", command=self.parent.browse_folder, width=6)
        browse_btn.grid(row=0, column=1, padx=2)
        ToolTip(browse_btn, "ダウンロード先フォルダを選択します")
        
        open_btn = ttk.Button(save_inner_frame, text="開く", command=self.parent.open_download_folder, width=6)
        open_btn.grid(row=0, column=2, padx=2)
        ToolTip(open_btn, "現在設定されているダウンロードフォルダを開きます")

        # 1. 保存フォルダ名
        folder_name_frame = ttk.LabelFrame(left_column, text="保存フォルダ名")
        folder_name_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5)
        left_row += 1
        folder_name_frame.grid_columnconfigure(0, weight=1)
        
        # 1行目：h1優先とtitle優先を横並び
        folder_priority_frame = ttk.Frame(folder_name_frame)
        folder_priority_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        folder_priority_frame.grid_columnconfigure(1, weight=1)
        
        h1_rb = ttk.Radiobutton(folder_priority_frame, text="優先的に<h1>から取得（推奨）", value="h1_priority", 
                       variable=self.parent.folder_name_mode, command=self.state_manager._update_folder_name_state)
        h1_rb.grid(row=0, column=0, sticky="w", padx=(0,20))
        ToolTip(h1_rb, "日本語タイトル（H1タグ）を優先してフォルダ名に使用します")
        
        title_rb = ttk.Radiobutton(folder_priority_frame, text="<title>から取得", value="title_priority",
                       variable=self.parent.folder_name_mode, command=self.state_manager._update_folder_name_state)
        title_rb.grid(row=0, column=1, sticky="w")
        ToolTip(title_rb, "英語タイトル（Titleタグ）を優先してフォルダ名に使用します")
        
        # 2行目：カスタム（エントリとヒントボタンの幅調整）
        folder_custom_frame = ttk.Frame(folder_name_frame)
        folder_custom_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        folder_custom_frame.grid_columnconfigure(1, weight=1)
        
        folder_custom_rb = ttk.Radiobutton(folder_custom_frame, text="カスタム:", value="custom",
                                         variable=self.parent.folder_name_mode, command=self.state_manager._update_folder_name_state)
        folder_custom_rb.grid(row=0, column=0, sticky="w")
        ToolTip(folder_custom_rb, "カスタムテンプレートを使用してフォルダ名を指定します")
        
        self.custom_folder_name_entry = ttk.Entry(folder_custom_frame, textvariable=self.parent.custom_folder_name, width=20)
        self.custom_folder_name_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(self.custom_folder_name_entry, TOOLTIP_TEXTS.get('custom_folder_name', 'カスタムテンプレート'))
        
        self.custom_folder_hint_btn = ttk.Button(folder_custom_frame, text="?",
                                               command=self.parent.show_custom_folder_name_hint, width=3)
        self.custom_folder_hint_btn.grid(row=0, column=2)
        ToolTip(self.custom_folder_hint_btn, "使用可能な変数の説明を表示します")

        # 2. 保存ファイル名
        name_frame = ttk.LabelFrame(left_column, text="保存ファイル名")
        name_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5)
        left_row += 1
        name_frame.grid_columnconfigure(0, weight=1)

        name_options_frame = ttk.Frame(name_frame)
        name_options_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        name_options_frame.grid_columnconfigure(0, weight=1)
        
        original_rb = ttk.Radiobutton(name_options_frame, text="Original", value="Original", variable=self.parent.save_name, command=self.state_manager._update_custom_name_entry_state)
        original_rb.grid(row=0, column=0, sticky="w", padx=5)
        ToolTip(original_rb, "元のファイル名をそのまま使用します")
        
        simple_rb = ttk.Radiobutton(name_options_frame, text="連番 (0から)", value="simple_number", variable=self.parent.save_name, command=self.state_manager._update_custom_name_entry_state)
        simple_rb.grid(row=0, column=1, sticky="w", padx=5)
        ToolTip(simple_rb, "0, 1, 2... と連番で命名します")
        
        padded_rb = ttk.Radiobutton(name_options_frame, text="連番 (000から)", value="padded_number", variable=self.parent.save_name, command=self.state_manager._update_custom_name_entry_state)
        padded_rb.grid(row=0, column=2, sticky="w", padx=5)
        ToolTip(padded_rb, "000, 001, 002... とゼロ埋めで連番命名します")
        
        custom_name_frame = ttk.Frame(name_frame)
        custom_name_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        custom_name_frame.grid_columnconfigure(1, weight=1)
        
        custom_name_rb = ttk.Radiobutton(custom_name_frame, text="カスタム:", value="custom_name", variable=self.parent.save_name, command=self.state_manager._update_custom_name_entry_state)
        custom_name_rb.grid(row=0, column=0, sticky="w")
        ToolTip(custom_name_rb, "カスタムテンプレートを使用してファイル名を指定します")
        
        self.custom_name_entry = ttk.Entry(custom_name_frame, textvariable=self.parent.custom_name, width=20)
        self.custom_name_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(self.custom_name_entry, TOOLTIP_TEXTS.get('custom_name', 'カスタムテンプレート'))

        self.custom_name_hint_btn = ttk.Button(custom_name_frame, text="?", command=self.parent.show_custom_name_hint, width=3)
        self.custom_name_hint_btn.grid(row=0, column=2, padx=(2,5))
        ToolTip(self.custom_name_hint_btn, "使用可能な変数の説明を表示します")

        # 1ページ目だけ命名を変更
        first_page_frame = ttk.Frame(name_frame)
        first_page_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        first_page_frame.grid_columnconfigure(1, weight=1)
        
        first_page_cb = ttk.Checkbutton(first_page_frame, text="1ページ目だけ命名を変更", variable=self.parent.first_page_naming_enabled, command=self.state_manager._update_first_page_naming_state)
        first_page_cb.grid(row=0, column=0, sticky="w")
        ToolTip(first_page_cb, TOOLTIP_TEXTS.get('first_page_naming', '1ページ目のみ異なる名前を付けます'))
        
        self.first_page_naming_entry = ttk.Entry(first_page_frame, textvariable=self.parent.first_page_naming_format, width=15)
        self.first_page_naming_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(self.first_page_naming_entry, "1ページ目に付ける名前（例: cover, title）")
        
        # 初期状態で1ページ目命名入力を無効化と初期値設定
        if not self.parent.first_page_naming_enabled.get():
            self.first_page_naming_entry.config(state='disabled')
        self.parent.first_page_naming_format.set("title")  # 文字列として設定

        # 3. 同名フォルダが存在する場合の処理
        dup_folder_frame = ttk.LabelFrame(left_column, text="同名フォルダが存在する場合の処理")
        dup_folder_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5)
        left_row += 1
        dup_folder_frame.grid_columnconfigure(0, weight=1)
        ToolTip(dup_folder_frame, TOOLTIP_TEXTS['duplicate_folder_mode'])

        dup_folder_content = ttk.Frame(dup_folder_frame)
        dup_folder_content.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        dup_folder_content.grid_columnconfigure(1, weight=1)
        
        ttk.Label(dup_folder_content, text="処理方法:").grid(row=0, column=0, sticky="w")
        dup_folder_options = ["同名フォルダに上書き保存", "新しいフォルダ名で保存 (例: Folder(1))", "そのギャラリーからのDLをスキップ"]
        dup_folder_values = ["overwrite", "rename", "skip"]
        self.duplicate_folder_cb = ttk.Combobox(dup_folder_content, values=dup_folder_options, state="readonly", width=15)
        self.duplicate_folder_cb.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(self.duplicate_folder_cb, TOOLTIP_TEXTS['duplicate_folder_mode'])
        
        # 選択変更時の処理
        def _on_dup_folder_change(event):
            try:
                selection = self.duplicate_folder_cb.current()
                if selection >= 0:
                    new_value = dup_folder_values[selection]
                    # 内部値とGUI状態を同期
                    self.parent.duplicate_folder_mode.set(new_value)
            except Exception as e:
                self.parent.log(f"同名フォルダ処理変更エラー: {e}", "error")
        
        self.duplicate_folder_cb.bind('<<ComboboxSelected>>', _on_dup_folder_change)
        
        # 初期値設定の修正（設定読み込み後に実行）
        def _set_initial_dup_folder_value():
            try:
                current_mode = self.parent.duplicate_folder_mode.get()
                # 英語値から日本語値に変換してからインデックスを取得
                japanese_mode = self.parent._convert_duplicate_mode_to_japanese(current_mode)
                if japanese_mode in dup_folder_options:
                    index = dup_folder_options.index(japanese_mode)
                    self.duplicate_folder_cb.current(index)
                else:
                    self.duplicate_folder_cb.current(1)  # デフォルトは"rename"
            except Exception as e:
                self.parent.log(f"同名フォルダ初期値設定エラー: {e}", "error")
        
        # 設定読み込み後に初期値を設定
        self.parent.root.after(100, _set_initial_dup_folder_value)

        # 4. 同名ファイルが存在する場合の処理
        same_file_frame = ttk.LabelFrame(left_column, text="同名ファイルが存在する場合の処理")
        same_file_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5)
        left_row += 1
        same_file_frame.grid_columnconfigure(0, weight=1)
        ToolTip(same_file_frame, TOOLTIP_TEXTS['duplicate_file_mode'])
        
        # 処理方法の選択（コンボボックス化）
        same_file_content = ttk.Frame(same_file_frame)
        same_file_content.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        same_file_content.grid_columnconfigure(1, weight=1)
        
        ttk.Label(same_file_content, text="処理方法:").grid(row=0, column=0, sticky="w")
        # E-Hentai用に制限：リネームのみ有効
        same_file_options = ["新しいファイル名で保存 (例: file(1).jpg)"]
        same_file_values = ["rename"]
        self.duplicate_file_cb = ttk.Combobox(same_file_content, values=same_file_options, state="readonly", width=15)
        self.duplicate_file_cb.grid(row=0, column=1, sticky="ew", padx=5)
        ToolTip(self.duplicate_file_cb, "E-Hentai Galleriesには同名ファイルが同じギャラリーに含まれる可能性があるので変更不可")
        
        # コンボボックスの初期値設定（E-Hentai用にリネーム固定）
        self.duplicate_file_cb.current(0)  # リネームのみ
        
        # 選択変更時の処理
        def _on_dup_file_change(event):
            selection = self.duplicate_file_cb.current()
            if selection >= 0:
                self.parent.duplicate_file_mode.set(same_file_values[selection])
                self.state_manager._update_skip_count_state()
        self.duplicate_file_cb.bind('<<ComboboxSelected>>', _on_dup_file_change)
        
        # 初期値を設定（E-Hentai用にリネーム固定）
        self.parent.duplicate_file_mode.set("rename")
        
        # X回連続スキップ後にそのギャラリーのDLを完了（単独ボタン）
        # 将来的に使うかもしれないので機能的には残すが、GUI上からは非表示
        skip_after_frame = ttk.Frame(same_file_frame)
        # skip_after_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)  # コメントアウトで非表示
        skip_after_frame.grid_columnconfigure(0, weight=1)
        
        self.skip_after_count_cb = ttk.Checkbutton(skip_after_frame, text="X回連続スキップ後にそのギャラリーのDLをスキップ", variable=self.parent.skip_after_count_enabled, command=self.state_manager._update_skip_count_state)
        # self.skip_after_count_cb.grid(row=0, column=0, sticky="ew", padx=5, pady=2)  # コメントアウトで非表示
        
        # X回連続スキップのツールチップ
        ToolTip(self.skip_after_count_cb, "指定回数連続でスキップが発生した場合、そのギャラリー全体をスキップして次のURLに進みます。")
        
        # スキップ回数設定
        skip_count_frame = ttk.Frame(skip_after_frame)
        # skip_count_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=2)  # コメントアウトで非表示
        skip_count_frame.grid_columnconfigure(3, weight=1)  # 余白を右に寄せる
        
        ttk.Label(skip_count_frame, text="スキップ回数:").grid(row=0, column=0, sticky="w", padx=5)
        self.skip_count_entry = ttk.Entry(skip_count_frame, textvariable=self.parent.skip_count, width=8)
        self.skip_count_entry.grid(row=0, column=1, padx=5)
        ttk.Label(skip_count_frame, text="回").grid(row=0, column=2, sticky="w", padx=2)
        
        # 初期状態でスキップ回数入力を無効化
        if not self.parent.skip_after_count_enabled.get():
            self.skip_count_entry.config(state='disabled')
        
        # === 右列オプション（指示通り） ===
        right_row = 0
        
        # 1. 保存形式
        format_frame = ttk.LabelFrame(right_column, text="保存形式")
        format_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        format_frame.grid_columnconfigure(0, weight=1)

        formats_frame = ttk.Frame(format_frame)
        formats_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        formats = ["Original", "JPG", "PNG", "WEBP"]
        for i, f_text in enumerate(formats):
            ttk.Radiobutton(formats_frame, text=f_text, value=f_text, variable=self.parent.save_format).grid(row=0, column=i, padx=5)

        # JPG品質設定
        self.jpg_quality_frame = ttk.Frame(format_frame)
        self.jpg_quality_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(self.jpg_quality_frame, text="JPG品質:").grid(row=0, column=0, padx=5, sticky="w")
        self.jpg_quality_scale = ttk.Scale(self.jpg_quality_frame, from_=0, to=100, orient="horizontal", variable=self.parent.jpg_quality)
        self.jpg_quality_scale.grid(row=0, column=1, padx=5, sticky="ew")
        self.jpg_quality_entry = ttk.Entry(self.jpg_quality_frame, textvariable=self.parent.jpg_quality, width=4)
        self.jpg_quality_entry.grid(row=0, column=2, padx=2)
        ttk.Label(self.jpg_quality_frame, text="%").grid(row=0, column=3, padx=2, sticky="w")
        self.jpg_quality_frame.grid_columnconfigure(1, weight=1)
        
        # JPG品質の値を制限する関数
        def _validate_jpg_quality(*args):
            try:
                value = float(self.parent.jpg_quality.get())
                value = int(value)  # 小数点以下を切り捨て
                if value < 0:
                    self.parent.jpg_quality.set(0)
                elif value > 100:
                    self.parent.jpg_quality.set(100)
                else:
                    self.parent.jpg_quality.set(value)  # 整数値を設定
            except ValueError:
                self.parent.jpg_quality.set(85)  # デフォルト値
        
        # JPG品質の変更を監視
        self.parent.jpg_quality.trace_add("write", _validate_jpg_quality)

        # JPG品質設定の表示/非表示を制御する関数
        def _update_jpg_quality_visibility(*args):
            if self.parent.save_format.get() == "JPG":
                self.jpg_quality_frame.grid()
            else:
                self.jpg_quality_frame.grid_remove()
        
        # 保存形式変更時にJPG品質設定の表示/非表示を更新
        self.parent.save_format.trace_add("write", _update_jpg_quality_visibility)
        # 初期状態を設定
        _update_jpg_quality_visibility()

        # アニメーション保持オプション
        ttk.Checkbutton(format_frame, text="アニメーション画像は元形式を保持", variable=self.parent.preserve_animation).grid(row=2, column=0, sticky="ew", padx=5, pady=2)

        # 2. フォルダの圧縮
        compression_frame = ttk.LabelFrame(right_column, text="フォルダの圧縮 (ZIP)")
        compression_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        compression_frame.grid_columnconfigure(1, weight=1)
        
        # フォルダの圧縮のツールチップ
        ToolTip(compression_frame, "ダウンロード完了後にフォルダをZIP形式で圧縮します。同名ファイルが存在する場合は連番で両方保持されます。")
        
        # OFF/ONボタン（最小限の幅）
        compression_onoff_frame = ttk.Frame(compression_frame)
        compression_onoff_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=3)
        ttk.Radiobutton(compression_onoff_frame, text="OFF", value="off", variable=self.parent.compression_enabled, command=self.state_manager._update_compression_options_state, width=6).grid(row=0, column=0, sticky="w", padx=2, pady=3)
        ttk.Radiobutton(compression_onoff_frame, text="ON", value="on", variable=self.parent.compression_enabled, command=self.state_manager._update_compression_options_state, width=6).grid(row=0, column=1, sticky="w", padx=2, pady=3)
        
        self.compression_delete_original_cb = ttk.Checkbutton(compression_frame, text="圧縮後にオリジナルファイルを削除", variable=self.parent.compression_delete_original)
        self.compression_delete_original_cb.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        
        # ⭐追加: 圧縮後にフォルダごと削除オプション⭐
        if not hasattr(self.parent, 'compression_delete_folder'):
            self.parent.compression_delete_folder = tk.BooleanVar(value=False)
        self.compression_delete_folder_cb = ttk.Checkbutton(compression_frame, text="圧縮後にフォルダごと削除", variable=self.parent.compression_delete_folder)
        self.compression_delete_folder_cb.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        
        # TIPS表示
        compression_tips = ("💡 圧縮後にフォルダごと削除:\n"
                           "• ON: 圧縮後に元フォルダ全体を削除\n"
                           "• OFF: フォルダとZIP両方を保持\n"
                           "• オリジナルファイル削除と両方ONの場合、このオプションを優先\n"
                           "• 保存フォルダにサブディレクトリが存在する場合は削除しません")
        ToolTip(self.compression_delete_folder_cb, compression_tips)
        
        # 圧縮オプションのグレーアウト機能を統合ヘルパーで実装
        detail_widgets = [self.compression_delete_original_cb]
        if hasattr(self, 'compression_delete_folder_cb'):
            detail_widgets.append(self.compression_delete_folder_cb)
        self.state_manager._register_grayout_option('compression_enabled', detail_widgets, value_map={'on': True, 'off': False})

        # 3. 待機時間
        wait_sleep_frame = ttk.LabelFrame(right_column, text="待機時間 (秒)")
        wait_sleep_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5)
        right_row += 1
        wait_sleep_frame.grid_columnconfigure(0, weight=1)

        wait_frame = ttk.Frame(wait_sleep_frame)
        wait_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        wait_frame.grid_columnconfigure(3, weight=1)  # 最後の列に余白を寄せる
        
        ttk.Label(wait_frame, text="ページ間隔:").grid(row=0, column=0)
        ttk.Entry(wait_frame, textvariable=self.parent.wait_time, width=5).grid(row=0, column=1, padx=5)
        ttk.Label(wait_frame, text="画像毎:").grid(row=0, column=2)
        ttk.Entry(wait_frame, textvariable=self.parent.sleep_value, width=5).grid(row=0, column=3, padx=5, sticky="w")
        
        # 待機時間の初期値を設定（正規表現取得時間短縮のため）
        self.parent.wait_time.set("0.5")  # ページ間隔を0.5秒に短縮
        self.parent.sleep_value.set("0.5")  # 画像毎も0.5秒に短縮
        
        # ダウンロード範囲オプション（待機時間の下部）
        download_range_frame = ttk.LabelFrame(right_column, text="ダウンロード範囲")
        download_range_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5); right_row += 1
        
        # ON/OFFボタン
        download_range_onoff_frame = ttk.Frame(download_range_frame)
        download_range_onoff_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        ttk.Radiobutton(download_range_onoff_frame, text="OFF", value=False, variable=self.parent.download_range_enabled, width=6).grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(download_range_onoff_frame, text="ON", value=True, variable=self.parent.download_range_enabled, width=6).grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # セレクトボックス
        download_range_mode_frame = ttk.Frame(download_range_frame)
        download_range_mode_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(download_range_mode_frame, text="範囲:").grid(row=0, column=0, sticky="w", padx=(0,5))
        download_range_mode_combo = ttk.Combobox(download_range_mode_frame, textvariable=self.parent.download_range_mode, values=["1行目のURLのみ", "全てのURL"], state="readonly", width=15)
        download_range_mode_combo.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # 始点・終点入力フォーム
        download_range_input_frame = ttk.Frame(download_range_frame)
        download_range_input_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        download_range_input_frame.grid_columnconfigure(1, weight=1)
        download_range_input_frame.grid_columnconfigure(3, weight=1)
        
        ttk.Label(download_range_input_frame, text="始点:").grid(row=0, column=0, sticky="w", padx=(0,5))
        download_range_start_entry = ttk.Entry(download_range_input_frame, textvariable=self.parent.download_range_start, width=10)
        download_range_start_entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        
        ttk.Label(download_range_input_frame, text="終点:").grid(row=0, column=2, sticky="w", padx=(0,5))
        download_range_end_entry = ttk.Entry(download_range_input_frame, textvariable=self.parent.download_range_end, width=10)
        download_range_end_entry.grid(row=0, column=3, sticky="ew", padx=2, pady=2)
        
        # ⭐重要: エントリーウィジェットへの参照を保存（プレースホルダー更新用）⭐
        self.download_range_start_entry = download_range_start_entry
        self.download_range_end_entry = download_range_end_entry
        
        # プレースホルダー機能を実装
        self._setup_placeholder(download_range_start_entry, "空欄は0")
        self._setup_placeholder(download_range_end_entry, "空欄は∞")
        
        # ToolTipを追加
        ToolTip(download_range_frame, "ダウンロードするページの範囲を指定します。\n・1行目のURLのみ: DLリストの最初のURLのみをダウンロード\n・全てのURL: DLリストの全てのURLをダウンロード\n・始点: ダウンロード開始ページ（0から開始）\n・終点: ダウンロード終了ページ（空欄は最後まで）\n・入力値の検証: 始点は0以上、終点は始点以上である必要があります")
        
        # 視覚的フィードバック用のフレーム参照を保存
        self.download_range_frame = download_range_frame
        
        # 自動グレーアウト管理システムに登録
        self.register_option_frame('download_range_enabled', download_range_frame)
        
        # 詳細項目のグレーアウト管理
        detail_items = [download_range_mode_combo, download_range_start_entry, download_range_end_entry]
        self.register_option_detail_items('download_range_enabled', detail_items)
        self.state_manager._register_grayout_option('download_range_enabled', detail_items, extra_check=self.state_manager._check_download_range_state)
        
        # DL未完了フォルダのリネーム（基本設定タブの右カラムの最下部）
        incomplete_frame = ttk.LabelFrame(right_column, text="DL未完了フォルダのリネーム")
        incomplete_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5); right_row += 1
        incomplete_frame.grid_columnconfigure(1, weight=1)
        
        # DL未完了フォルダのリネームのツールチップ
        ToolTip(incomplete_frame, "ダウンロードが中断・エラー・スキップされたフォルダに接頭辞を付けます。")
        
        # OFF/ONラジオボタン（最小限の幅）
        incomplete_onoff_frame = ttk.Frame(incomplete_frame)
        incomplete_onoff_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        incomplete_off_radio = ttk.Radiobutton(incomplete_onoff_frame, text="OFF", value=False, variable=self.parent.rename_incomplete_folder, command=self.state_manager._update_incomplete_folder_options_state, width=6)
        incomplete_off_radio.grid(row=0, column=0, sticky="w", padx=2, pady=2)
        incomplete_on_radio = ttk.Radiobutton(incomplete_onoff_frame, text="ON", value=True, variable=self.parent.rename_incomplete_folder, command=self.state_manager._update_incomplete_folder_options_state, width=6)
        incomplete_on_radio.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # ToolTipを追加
        ToolTip(incomplete_off_radio, "未完了フォルダに接頭辞を付けません。フォルダ名は変更されません。")
        ToolTip(incomplete_on_radio, "ダウンロードが中断・エラー・スキップされたフォルダに接頭辞を付けます。")
        
        ttk.Label(incomplete_frame, text="接頭辞:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.incomplete_folder_prefix_entry = ttk.Entry(incomplete_frame, textvariable=self.parent.incomplete_folder_prefix, width=20)
        self.incomplete_folder_prefix_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        # 視覚的フィードバック用のフレーム参照を保存
        self.incomplete_frame = incomplete_frame
        self.incomplete_off_radio = incomplete_off_radio
        self.incomplete_on_radio = incomplete_on_radio
        
        # 自動グレーアウト管理システムに登録
        self.register_option_frame('rename_incomplete_folder', incomplete_frame)
        
        # 詳細項目のグレーアウト管理
        detail_items = [self.incomplete_folder_prefix_entry]
        self.register_option_detail_items('rename_incomplete_folder', detail_items)
        self.state_manager._register_grayout_option('rename_incomplete_folder', detail_items)
    
    def _create_image_editing_content(self):
        """特殊設定タブの内容を作成（元の仕様を完全保持）"""
        # 左右のフレームを水平に配置（幅を450pxに固定）
        columns_frame = ttk.Frame(self.image_frame_inner)
        columns_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # 各カラムを450pxの固定幅に設定
        columns_frame.grid_columnconfigure(0, weight=0, minsize=450)
        columns_frame.grid_columnconfigure(1, weight=0, minsize=450)
        
        # 左右のカラムを作成（450px固定幅）
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        
        # === 左列オプション（リサイズ設定） ===
        left_row = 0
        
        # リサイズ設定（幅を450px近くに拡大）
        resize_main_frame = ttk.LabelFrame(left_column, text="リサイズ設定")
        resize_main_frame.grid(row=left_row, column=0, sticky="ew", padx=5, pady=5); left_row += 1
        resize_main_frame.grid_columnconfigure(1, weight=1)
        # リサイズ設定フレームの最小幅を設定
        resize_main_frame.grid_columnconfigure(0, minsize=450)
        
        # リサイズON/OFF設定
        resize_onoff_frame = ttk.Frame(resize_main_frame)
        resize_onoff_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        resize_off_btn = ttk.Radiobutton(resize_onoff_frame, text="OFF", value="off", variable=self.parent.resize_enabled, command=self.state_manager._update_resize_options_state, width=6)
        resize_off_btn.grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ToolTip(resize_off_btn, "リサイズ機能を無効にします")
        
        resize_on_btn = ttk.Radiobutton(resize_onoff_frame, text="ON", value="on", variable=self.parent.resize_enabled, command=self.state_manager._update_resize_options_state, width=6)
        resize_on_btn.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        ToolTip(resize_on_btn, "リサイズ機能を有効にします。画像を指定したサイズに縮小します")
        
        # リサイズ詳細オプション用のフレーム（常に表示、オリジナルと同じ詳細表示）
        self.resize_details_frame = ttk.Frame(resize_main_frame)
        self.resize_details_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        
        # リサイズ設定のグレーアウト機能を直接実装（フレーム作成後に登録）
        self.state_manager._register_grayout_option('resize_enabled', [self.resize_details_frame], value_map={'on': True, 'off': False}, recursive=True)
        
        # モード設定（詳細フレーム内に配置）
        self.resize_mode_frame = ttk.Frame(self.resize_details_frame)
        self.resize_mode_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        resize_mode_label = ttk.Label(self.resize_mode_frame, text="モード:")
        resize_mode_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ToolTip(resize_mode_label, "リサイズの基準となるモードを選択します")
        
        resize_modes = ["縦幅上限", "横幅上限", "長辺上限", "長辺下限", "短辺上限", "短辺下限", "比率"]
        self.resize_mode_cb = ttk.Combobox(self.resize_mode_frame, textvariable=self.parent.resize_mode, values=resize_modes, state="readonly", width=18)
        self.resize_mode_cb.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        self.resize_mode_cb.set("縦幅上限")
        ToolTip(self.resize_mode_cb, """リサイズモードの詳細説明：

• 縦幅上限: 縦の長さを指定値以下に制限（横は自動調整）
• 横幅上限: 横の長さを指定値以下に制限（縦は自動調整）
• 長辺上限: 長い方の辺を指定値以下に制限
• 長辺下限: 長い方の辺を指定値以上に拡大
• 短辺上限: 短い方の辺を指定値以下に制限
• 短辺下限: 短い方の辺を指定値以上に拡大
• 比率: 元画像の指定パーセントに縮小（例: 80% = 元の80%のサイズ）

【リサイズ実行タイミング】
• ダウンロード完了後、保存前に実行
• 元画像のアスペクト比は保持されます
• リサイズ不要な画像はスキップされます""")
        
        # サイズ設定（詳細フレーム内に配置）
        self.resize_size_frame = ttk.Frame(self.resize_details_frame)
        self.resize_size_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        resize_size_label = ttk.Label(self.resize_size_frame, text="サイズ:")
        resize_size_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ToolTip(resize_size_label, "リサイズの基準となるサイズ値を入力します")

        # 数値のみを許可する検証関数
        def validate_number(text):
            if text == "":
                return True
            try:
                int(text)
                return True
            except ValueError:
                return False
        
        # 比率用の検証関数（小数点を許可）
        def validate_percentage(text):
            if text == "":
                return True
            try:
                value = float(text)
                return 0 <= value <= 1000  # 0-1000%の範囲を許可
            except ValueError:
                return False
        
        # リサイズ値の入力制限を設定
        vcmd = (self.parent.root.register(validate_number), '%P')
        vcmd_percentage = (self.parent.root.register(validate_percentage), '%P')
        # 初期値はデフォルトモード（縦幅上限）に対応する変数を設定
        self.resize_size_entry = ttk.Entry(self.resize_size_frame, textvariable=self.parent.resize_values["height"], width=12, validate="key", validatecommand=vcmd)
        self.resize_size_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ToolTip(self.resize_size_entry, """リサイズの基準となるサイズ値を入力します：

【入力形式】
• 数値のみ: 1920, 1080, 80
• 単位付き: 1920px, 80%

【注意事項】
• 比率モード以外: px単位で入力
• 比率モード: %単位で入力（1-100の範囲）
• 無効な値は自動的に修正されます""")
        
        self.resize_size_label = ttk.Label(self.resize_size_frame, text="px")
        self.resize_size_label.grid(row=0, column=2, padx=2, pady=2, sticky="w")
        ToolTip(self.resize_size_label, """サイズの単位：
• px: ピクセル単位（例: 1920）
• %: パーセント単位（例: 80 = 80%）

【入力例】
• 縦幅上限: 1080px → 縦1080px以下に縮小
• 比率: 80% → 元画像の80%サイズに縮小
• 長辺上限: 1920px → 長い辺が1920px以下に縮小""")
        
        # リサイズモード変更時の処理（オリジナル準拠）
        def _on_resize_mode_change(*args):
            """リサイズモード変更時の処理"""
            try:
                mode = self.parent.resize_mode.get()
                
                # resize_valuesが存在しない場合は初期化
                if not hasattr(self.parent, 'resize_values'):
                    self.parent.log("resize_values属性が存在しません。初期化をスキップします。", "warning")
                    return
                
                if not self.parent.resize_values:
                    self.parent.log("resize_valuesが空です。初期化をスキップします。", "debug")
                    return
                
                # 必要なキーが存在するか確認
                required_keys = ['height', 'width', 'short', 'long', 'percentage', 'unified']
                for key in required_keys:
                    if key not in self.parent.resize_values:
                        self.parent.log(f"resize_valuesに{key}キーが存在しません。初期化をスキップします。", "warning")
                        return
                
                if mode == "比率":
                    # 比率モードの場合は入力欄を%に変更
                    self.resize_size_label.config(text="%")
                    # 入力値をpercentageに変更し、検証関数も変更
                    self.resize_size_entry.config(textvariable=self.parent.resize_values["percentage"], validatecommand=vcmd_percentage)
                else:
                    # その他のモードの場合は入力欄をpxに変更
                    self.resize_size_label.config(text="px")
                    # 入力値を対応するモードの値に変更し、検証関数も変更
                    if mode == "縦幅上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["height"], validatecommand=vcmd)
                    elif mode == "横幅上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["width"], validatecommand=vcmd)
                    elif mode == "長辺上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["long"], validatecommand=vcmd)
                    elif mode == "長辺下限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["long"], validatecommand=vcmd)
                    elif mode == "短辺上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["short"], validatecommand=vcmd)
                    elif mode == "短辺下限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["short"], validatecommand=vcmd)
                    else:
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["unified"], validatecommand=vcmd)
            except Exception as e:
                self.parent.log(f"リサイズモード変更エラー: {e}", "error")
        
        # リサイズモード変更のイベントをバインド（エラーハンドリング付き）
        try:
            self.parent.resize_mode.trace_add('write', _on_resize_mode_change)
        except Exception as e:
            self.parent.log(f"リサイズモード変更イベントバインドエラー: {e}", "error")
        
        # リサイズモード変更時の処理（初期化時も実行）
        def _on_resize_mode_change_initial(*args):
            """リサイズモード変更時の処理（初期化時も実行）"""
            try:
                mode = self.parent.resize_mode.get()
                
                # 比率モードの場合は入力欄を%に変更
                if mode == "比率":
                    self.resize_size_label.config(text="%")
                    # 入力値をpercentageに変更し、検証関数も変更
                    self.resize_size_entry.config(textvariable=self.parent.resize_values["percentage"], validatecommand=vcmd_percentage)
                else:
                    # その他のモードの場合は入力欄をpxに変更
                    self.resize_size_label.config(text="px")
                    # 入力値を対応するモードの値に変更し、検証関数も変更
                    if mode == "縦幅上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["height"], validatecommand=vcmd)
                    elif mode == "横幅上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["width"], validatecommand=vcmd)
                    elif mode == "長辺上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["long"], validatecommand=vcmd)
                    elif mode == "長辺下限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["long"], validatecommand=vcmd)
                    elif mode == "短辺上限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["short"], validatecommand=vcmd)
                    elif mode == "短辺下限":
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["short"], validatecommand=vcmd)
                    else:
                        self.resize_size_entry.config(textvariable=self.parent.resize_values["unified"], validatecommand=vcmd)
            except Exception as e:
                self.parent.log(f"リサイズモード変更エラー: {e}", "error")
        
        # 初期化時にリサイズモード変更処理を実行（遅延実行で設定読み込み後に実行）
        self.parent.root.after(100, _on_resize_mode_change_initial)
        
        # 初期化は他のオプションと同じように辞書から読み込まれるため、特別な処理は不要
        
        # 品質設定（オリジナルと同じ）
        self.resize_quality_frame = ttk.Frame(self.resize_details_frame)
        self.resize_quality_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        resize_quality_label = ttk.Label(self.resize_quality_frame, text="品質:")
        resize_quality_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ToolTip(resize_quality_label, "リサイズ後の画像品質を設定します（1-100、デフォルト: 95）")
        
        self.resize_quality_entry = ttk.Entry(self.resize_quality_frame, textvariable=self.parent.resize_quality, width=12)
        self.resize_quality_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ToolTip(self.resize_quality_entry, "画像品質（1-100）。高い値ほど高品質ですがファイルサイズが大きくなります")
        
        # シャープネス設定（オリジナルと同じ）
        self.resize_sharpness_frame = ttk.Frame(self.resize_details_frame)
        self.resize_sharpness_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        resize_sharpness_label = ttk.Label(self.resize_sharpness_frame, text="シャープネス:")
        resize_sharpness_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ToolTip(resize_sharpness_label, "リサイズ後の画像のシャープネスを設定します（0.0-2.0、デフォルト: 1.0）")
        self.resize_sharpness_entry = ttk.Entry(self.resize_sharpness_frame, textvariable=self.parent.sharpness_value, width=12)
        self.resize_sharpness_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ToolTip(self.resize_sharpness_entry, "シャープネス値（0.0-2.0）。高い値ほど画像がシャープになります")
        
        # 補完モード設定（統合版）
        self.interpolation_frame = ttk.Frame(self.resize_details_frame)
        self.interpolation_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        interpolation_label = ttk.Label(self.interpolation_frame, text="補完モード:")
        interpolation_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ToolTip(interpolation_label, "リサイズに使用する補完方法を選択します")
        
        # interpolation_mode変数が存在しない場合は作成
        if not hasattr(self.parent, 'interpolation_mode'):
            self.parent.interpolation_mode = tk.StringVar(value="三次補完（画質優先）")
        
        interpolation_modes = ["三次補完（画質優先）", "線形補間（バランス）", "単純補完（速度優先）"]
        self.interpolation_cb = ttk.Combobox(self.interpolation_frame, textvariable=self.parent.interpolation_mode, values=interpolation_modes, state="readonly", width=20)
        ToolTip(self.interpolation_cb, """補間モードの詳細説明：

• 三次補完（画質優先）: 最高画質だが処理が遅い
  - 高品質なリサイズ結果
  - 処理時間が長い
  - 推奨: 高画質を重視する場合

• 線形補間（バランス）: 画質と速度のバランス
  - 適度な画質と処理速度
  - 一般的な用途に最適
  - 推奨: 通常の使用

• 単純補完（速度優先）: 高速だが画質が劣る
  - 最も高速な処理
  - 画質は劣る
  - 推奨: 大量処理で速度を重視する場合""")
        self.interpolation_cb.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        self.interpolation_cb.set("三次補完（画質優先）")
        
        # リサイズファイル名のリネーム
        self.resize_filename_enabled_cb = ttk.Checkbutton(self.resize_details_frame, text="リサイズファイル名のリネーム", variable=self.parent.resize_filename_enabled)
        ToolTip(self.resize_filename_enabled_cb, "リサイズしたファイルに特別なファイル名を付与します（例: image_resized.jpg）")
        self.resize_filename_enabled_cb.grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        
        # リサイズファイル名詳細
        self.resize_filename_frame = ttk.LabelFrame(self.resize_details_frame, text="リサイズファイル名")
        self.resize_filename_frame.grid(row=7, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        ttk.Label(self.resize_filename_frame, text="接頭辞:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        ttk.Entry(self.resize_filename_frame, textvariable=self.parent.resized_prefix, width=15).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ttk.Label(self.resize_filename_frame, text="接尾辞:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        ttk.Entry(self.resize_filename_frame, textvariable=self.parent.resized_suffix, width=15).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        # オリジナル保持設定
        ttk.Checkbutton(self.resize_details_frame, text="リサイズ時にオリジナル画像を保持", variable=self.parent.keep_original).grid(row=8, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        
        # リサイズされなくても別フォルダに保持
        ttk.Checkbutton(self.resize_details_frame, text="リサイズされなくても別フォルダに保持", variable=self.parent.keep_unresized).grid(row=9, column=0, columnspan=2, sticky="w", padx=25, pady=2)
        
        # リサイズ画像保存場所
        self.resize_location_frame = ttk.LabelFrame(self.resize_details_frame, text="リサイズ画像の保存場所")
        self.resize_location_frame.grid(row=10, column=0, columnspan=2, sticky="ew", padx=0, pady=2)
        ttk.Radiobutton(self.resize_location_frame, text="同一フォルダ", value="same", variable=self.parent.resize_save_location).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Radiobutton(self.resize_location_frame, text="子ディレクトリ", value="child", variable=self.parent.resize_save_location).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(self.resize_location_frame, text="サブディレクトリ名:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        ttk.Entry(self.resize_location_frame, textvariable=self.parent.resized_subdir_name, width=20).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        # === 右列オプション（文字列変換） ===
        right_row = 0
        
        # 文字列変換オプション（元の仕様通り）
        conversion_frame = ttk.LabelFrame(right_column, text="文字列の置換")
        conversion_frame.grid(row=right_row, column=0, sticky="ew", padx=5, pady=5); right_row += 1
        conversion_frame.grid_columnconfigure(0, weight=1)

        # OFF/ONボタン
        conversion_onoff_frame = ttk.Frame(conversion_frame)
        conversion_onoff_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        
        conversion_off_btn = ttk.Radiobutton(conversion_onoff_frame, text="OFF", value=False, variable=self.parent.string_conversion_enabled, command=self.state_manager._update_string_conversion_state, width=6)
        conversion_off_btn.grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ToolTip(conversion_off_btn, "文字列置換機能を無効にします")
        
        conversion_on_btn = ttk.Radiobutton(conversion_onoff_frame, text="ON", value=True, variable=self.parent.string_conversion_enabled, command=self.state_manager._update_string_conversion_state, width=6)
        conversion_on_btn.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        ToolTip(conversion_on_btn, "文字列置換機能を有効にします。ファイル名やフォルダ名の特定文字列を置換できます")
        # 初期状態をOFFに設定
        self.parent.string_conversion_enabled.set(False)

        # 変換ルールフレーム（常に表示）
        self.conversion_rules_frame = ttk.Frame(conversion_frame)
        self.conversion_rules_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        self.conversion_rules_frame.grid_columnconfigure(0, weight=1)

        # デフォルトルールフレーム
        self.default_rule_frame = ttk.Frame(self.conversion_rules_frame)
        self.default_rule_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
        self.default_rule_frame.grid_columnconfigure(1, weight=1)
        self.default_rule_frame.grid_columnconfigure(3, weight=1)

        # デフォルトルールの作成
        self.default_enabled_var = tk.BooleanVar(value=True)
        self.default_find_var = tk.StringVar(value="♥")
        self.default_replace_var = tk.StringVar(value="（はぁと）")

        check = ttk.Checkbutton(self.default_rule_frame, variable=self.default_enabled_var, 
                              command=lambda: self._update_rule_state(self.default_enabled_var, 
                                                                    self.default_find_entry, 
                                                                    self.default_replace_entry))
        check.grid(row=0, column=0, padx=(0, 5))
        ToolTip(check, "この置換ルールを有効/無効にします")

        self.default_find_entry = ttk.Entry(self.default_rule_frame, textvariable=self.default_find_var, width=15)
        self.default_find_entry.grid(row=0, column=1, sticky="ew", padx=2)
        ToolTip(self.default_find_entry, "置換対象の文字列を入力します（例: ♥, [NG], 特殊文字など）")

        label1 = ttk.Label(self.default_rule_frame, text=" を ")
        label1.grid(row=0, column=2, padx=2)
        ToolTip(label1, "置換の区切り文字")

        self.default_replace_entry = ttk.Entry(self.default_rule_frame, textvariable=self.default_replace_var, width=15)
        self.default_replace_entry.grid(row=0, column=3, sticky="ew", padx=2)
        ToolTip(self.default_replace_entry, "置換後の文字列を入力します（例: （はぁと）, 空白, 削除の場合は空欄）")

        label2 = ttk.Label(self.default_rule_frame, text=" に置換")
        label2.grid(row=0, column=4, padx=2)
        ToolTip(label2, "置換処理の説明")

        # 追加ルール用のコンテナ（幅を固定して横幅拡大を防ぐ）
        self.conversion_rules_container = ttk.Frame(self.conversion_rules_frame)
        self.conversion_rules_container.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        self.conversion_rules_container.grid_columnconfigure(0, weight=1)
        # コンテナの幅を固定（横幅拡大を防ぐ）
        self.conversion_rules_container.configure(width=450)

        # ボタンフレーム
        rule_buttons_frame = ttk.Frame(self.conversion_rules_frame)
        rule_buttons_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        rule_buttons_frame.grid_columnconfigure(2, weight=1)  # 余白を右に寄せる
        
        self.add_rule_button = ttk.Button(rule_buttons_frame, text="＋", command=self._add_conversion_rule, width=4)
        self.add_rule_button.grid(row=0, column=0)

        self.remove_rule_button = ttk.Button(rule_buttons_frame, text="－", command=self._remove_conversion_rule, width=4)
        self.remove_rule_button.grid(row=0, column=1, padx=5)
        
        # 視覚的フィードバック用のフレーム参照を保存
        self.conversion_frame = conversion_frame
        
        # 自動グレーアウト管理システムに登録
        self.register_option_frame('string_conversion_enabled', conversion_frame)
        
        # 詳細項目のグレーアウト管理
        detail_items = [self.conversion_rules_frame]
        self.register_option_detail_items('string_conversion_enabled', detail_items)
        self.state_manager._register_grayout_option('string_conversion_enabled', detail_items, recursive=True)
    
    
    def _create_resume_content(self):
        """統合エラーレジューム管理タブの内容を作成"""
        # 左右のフレームを水平に配置（左カラムは元の幅、右カラムはエラー統計と同じ幅）
        columns_frame = ttk.Frame(self.resume_frame_inner)
        columns_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        # 各カラムの幅を調整（左は300px、右はエラー統計と同じ幅に）
        columns_frame.grid_columnconfigure(0, weight=0, minsize=300)
        columns_frame.grid_columnconfigure(1, weight=0, minsize=450)
        
        # 左右のカラムを作成（450px固定幅）
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        
        # === 左列オプション（統合エラーレジューム管理） ===
        left_row = 0
        
        # 統合エラーレジューム管理
        self._create_enhanced_error_resume_section(left_column, left_row)
        left_row += 1
        
        # 右列オプション（常時エラー対策、エラー統計とレジューム管理）
        self._create_error_prevention_section(right_column, 0)
        self._create_enhanced_error_statistics_section(right_column, 1)
    
    def _create_error_prevention_section(self, parent, row):
        """常時エラー対策セクションを作成"""
        # 常時エラー対策フレーム
        error_prevention_frame = ttk.LabelFrame(parent, text="常時エラー対策")
        error_prevention_frame.grid(row=row, column=0, sticky="ew", padx=5, pady=5)
        
        # User-Agent偽装（左側）
        user_agent_frame = ttk.Frame(error_prevention_frame)
        user_agent_frame.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(user_agent_frame, text="User-Agent 偽装:").grid(row=0, column=0, sticky="w", padx=(0,5))
        user_agent_checkbox = ttk.Checkbutton(user_agent_frame, text="", variable=self.parent.user_agent_spoofing_enabled)
        user_agent_checkbox.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # User-Agentのツールチップ
        ToolTip(user_agent_frame, "ブラウザになりすましてアクセスします。簡単なブロック回避に効果的です。")
        
        # httpx使用（中央）
        httpx_frame = ttk.Frame(error_prevention_frame)
        httpx_frame.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(httpx_frame, text="httpx (HTTP/2) 使用:").grid(row=0, column=0, sticky="w", padx=(0,5))
        httpx_checkbox = ttk.Checkbutton(httpx_frame, text="", variable=self.parent.httpx_enabled)
        httpx_checkbox.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # httpxのツールチップ
        ToolTip(httpx_frame, "よりブラウザに近い通信(HTTP/2)を行います。TLSエラー対策にもなります。")
        
        # 「？」ボタンを右端に配置（User-Agent偽装と同じ行）
        help_btn_error = ttk.Button(error_prevention_frame, text="?", width=3, command=self._show_error_prevention_dialog)
        help_btn_error.grid(row=0, column=2, sticky="e", padx=5, pady=2)
        error_prevention_frame.grid_columnconfigure(2, weight=1)  # 右寄せのため
        
        # SSL設定
        ssl_frame = ttk.Frame(error_prevention_frame)
        ssl_frame.grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=2)
        ttk.Label(ssl_frame, text="SSLのセキュリティレベルを1に下げる:").grid(row=0, column=0, sticky="w", padx=(0,5))
        ssl_checkbox = ttk.Checkbutton(ssl_frame, text="", variable=self.parent.always_ssl_security_level)
        ssl_checkbox.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # SSL設定のツールチップ
        ToolTip(ssl_frame, """SSLのセキュリティレベルを1に下げる:

効果:
• SSL/TLSエラーの回避（DH_KEY_TOO_SMALL等）
• 古い暗号化方式への対応
• 互換性の向上

注意:
• セキュリティレベルが下がります
• 必要に応じてのみ使用してください""")
        
        # ⭐修正: 常時Selenium（全ページでSelenium使用）⭐
        selenium_frame = ttk.Frame(error_prevention_frame)
        selenium_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=2)
        ttk.Label(selenium_frame, text="常時Selenium使用(非常に時間が掛かる):").grid(row=0, column=0, sticky="w", padx=(0,5))
        
        # ⭐修正: selenium_always_enabled変数を初期化（常時Selenium専用）⭐
        if not hasattr(self.parent, 'selenium_always_enabled'):
            self.parent.selenium_always_enabled = tk.BooleanVar(value=False)
        
        selenium_checkbox = ttk.Checkbutton(selenium_frame, text="", variable=self.parent.selenium_always_enabled, 
                                           command=self._on_selenium_always_enabled_changed)
        selenium_checkbox.grid(row=0, column=1, sticky="w", padx=2, pady=2)
        
        # 常時Seleniumのツールチップ
        ToolTip(selenium_frame, """常時Selenium使用:

【重要】これはエラー処理の「Selenium自動適用」とは異なります

効果:
• 全てのページでSeleniumを使用
• より確実なページアクセス
• JavaScript対応
• ブラウザレベルの動作

注意:
• 非常に時間がかかる（通常の10倍以上）
• リソース使用量が大幅に増加
• 最後の手段として使用すべき

エラー時のみSeleniumを使いたい場合:
→ これをOFFにして、Context-Awareタブの
  「Selenium自動適用」をONにしてください""")
        
        # ⭐追加: ページ情報取得にもSeleniumを使う⭐
        page_info_selenium_frame = ttk.Frame(error_prevention_frame)
        page_info_selenium_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=5, pady=2)
        ttk.Label(page_info_selenium_frame, text="  ページ情報取得にもSeleniumを使う:").grid(row=0, column=0, sticky="w", padx=(0,5))
        
        # ⭐追加: selenium_use_for_page_info変数を初期化⭐
        if not hasattr(self.parent, 'selenium_use_for_page_info'):
            self.parent.selenium_use_for_page_info = tk.BooleanVar(value=False)
        
        # ON/OFFラジオボタン
        page_info_on = ttk.Radiobutton(page_info_selenium_frame, text="ON", 
                                      variable=self.parent.selenium_use_for_page_info, value=True)
        page_info_on.grid(row=0, column=1, sticky="w", padx=2)
        
        page_info_off = ttk.Radiobutton(page_info_selenium_frame, text="OFF", 
                                       variable=self.parent.selenium_use_for_page_info, value=False)
        page_info_off.grid(row=0, column=2, sticky="w", padx=2)
        
        # フレームを保存（グレーアウト制御用）
        self.page_info_selenium_frame = page_info_selenium_frame
        
        # ツールチップ
        ToolTip(page_info_selenium_frame, """ページ情報取得にもSeleniumを使う:

効果:
• ギャラリー情報取得時にもSeleniumを使用
• より確実なページ情報取得
• アクセス制限の回避

注意:
• 常時Selenium使用がONの場合のみ有効
• 処理時間がさらに長くなります""")
        
        # 初期状態を設定（常時SeleniumがOFFの場合はグレーアウト）
        self._update_page_info_selenium_state()
    
    def _create_enhanced_error_resume_section(self, parent, row):
        """Context-Aware自動エラーハンドリングセクションを作成（分離したUIを使用）"""
        from gui.components.resume_section import ResumeSectionUI
        
        if not hasattr(self, 'resume_section_ui'):
            self.resume_section_ui = ResumeSectionUI(self)
        
        return self.resume_section_ui.create_enhanced_error_resume_section(parent, row)
    
    def _create_enhanced_error_statistics_section(self, parent, row):
        """エラー統計セクションを作成（右カラム用）"""
        from gui.components.resume_section import ResumeSectionUI
        
        if not hasattr(self, 'resume_section_ui'):
            self.resume_section_ui = ResumeSectionUI(self)
        
        return self.resume_section_ui.create_error_statistics_section(parent, row)
    
    def _show_error_flow_dialog(self):
        """エラーレジューム処理フローダイアログを表示"""
        try:
            from gui.dialogs.error_flow_dialog import ErrorFlowDialog, PYQT5_AVAILABLE
            if PYQT5_AVAILABLE:
                from PyQt5.QtWidgets import QApplication
                app = QApplication.instance()
                if app is None:
                    app = QApplication([])
                
                dialog = ErrorFlowDialog(None)
                dialog.exec_()
            else:
                # PyQt5が利用できない場合は従来の方法を使用
                from tkinter import messagebox
                messagebox.showinfo("エラーレジューム処理フロー", 
                                  "PyQt5が必要です。\nエラーレジューム処理フローの詳細については、\n「？」ボタンをクリックしてください。")
        except Exception as e:
            self.parent.log(f"エラーフローダイアログ表示エラー: {e}", "error")
            from tkinter import messagebox
            messagebox.showerror("エラー", f"エラーフローダイアログの表示に失敗しました:\n{e}")
    
    def _show_error_prevention_dialog(self):
        """常時エラー対策の説明ダイアログを表示"""
        try:
            from gui.dialogs.error_flow_dialog import ErrorPreventionDialog, PYQT5_AVAILABLE
            if PYQT5_AVAILABLE:
                from PyQt5.QtWidgets import QApplication
                app = QApplication.instance()
                if app is None:
                    app = QApplication([])
                
                dialog = ErrorPreventionDialog(None)
                dialog.exec_()
            else:
                # PyQt5が利用できない場合は従来の方法を使用
                from tkinter import messagebox
                messagebox.showinfo("常時エラー対策", 
                                  "PyQt5が必要です。\n常時エラー対策の詳細については、\n「？」ボタンをクリックしてください。")
        except Exception as e:
            self.parent.log(f"常時エラー対策ダイアログ表示エラー: {e}", "error")
            from tkinter import messagebox
            messagebox.showerror("エラー", f"常時エラー対策ダイアログの表示に失敗しました:\n{e}")
    
    def _update_enhanced_error_options(self):
        """強化されたエラーオプションの状態を更新"""
        try:
            enabled = self.parent.enhanced_error_handling_enabled.get()
            state = 'normal' if enabled else 'disabled'
            
            # 保存されたウィジェットの状態を更新
            if hasattr(self, 'enhanced_error_widgets'):
                for widget in self.enhanced_error_widgets:
                    try:
                        if hasattr(widget, 'configure'):
                            widget.configure(state=state)
                        elif hasattr(widget, 'config'):
                            widget.config(state=state)
                    except Exception:
                        pass
            
            # リトライ上限達成時のラジオボタンの初期値を確実に設定
            if hasattr(self.parent, 'retry_limit_action'):
                current_value = self.parent.retry_limit_action.get()
                if not current_value or current_value == "":
                    self.parent.retry_limit_action.set("pause")
                # ラジオボタンの状態を更新
                if hasattr(self, 'retry_limit_frame'):
                    for widget in self.retry_limit_frame.winfo_children():
                        if isinstance(widget, ttk.Radiobutton):
                            widget_value = widget.cget('value')
                            if widget_value == self.parent.retry_limit_action.get():
                                # 変数の値と一致するラジオボタンを選択状態にする
                                widget.invoke()
                                break
            
            # Selenium安全弁のタイムアウト設定は、Selenium安全弁が有効な場合のみ有効化
            selenium_enabled = self.parent.selenium_fallback_enabled.get() if hasattr(self.parent, 'selenium_fallback_enabled') else False
            if hasattr(self, 'selenium_frame'):
                for child in self.selenium_frame.winfo_children():
                    if isinstance(child, ttk.Entry):
                        child.configure(state="normal" if (enabled and selenium_enabled) else "disabled")
                            
        except Exception as e:
            self.parent.log(f"強化されたエラーオプション更新エラー: {e}", "error")
    
    def _update_error_statistics(self):
        """エラー統計を更新（非同期版）"""
        def update_stats():
            try:
                # ⭐修正: enhanced_error_handlerから統計を取得（非同期実行）⭐
                if hasattr(self.parent, 'enhanced_error_handler') and self.parent.enhanced_error_handler:
                    stats = self.parent.enhanced_error_handler.get_error_statistics()
                    
                    # GUI更新はメインスレッドで実行
                    self.parent.root.after(0, lambda s=stats: self._update_stats_text(s))
                else:
                    self.parent.root.after(0, lambda: self._update_stats_text(None))
            except Exception as e:
                self.parent.log(f"エラー統計取得エラー: {e}", "error")
                self.parent.root.after(0, lambda: self._update_stats_text(None))

        # バックグラウンドスレッドで統計を取得
        import threading
        threading.Thread(target=update_stats, daemon=True).start()
    
    def _update_stats_text(self, stats):
        """統計テキストを更新（メインスレッドで実行）"""
        try:
            # ⭐追加: stats_textが初期化されているか確認⭐
            if not hasattr(self, 'stats_text') or not self.stats_text:
                return
            
            self.stats_text.config(state="normal")
            self.stats_text.delete(1.0, tk.END)

            if stats:
                # ⭐追加: スキップ統計を取得⭐
                skipped_url_count = 0
                skipped_image_count = 0
                if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
                    state_manager = self.parent.downloader_core.state_manager
                    # URLスキップ数を取得（StateManager経由で安全に取得）
                    try:
                        with state_manager._state_lock:
                            url_statuses = state_manager.download_state.url_status
                            skipped_url_count = sum(1 for status in url_statuses.values() if status == 'skipped')
                    except:
                        pass
                    # 画像スキップ数を取得
                    if hasattr(self.parent.downloader_core, 'skipped_image_urls'):
                        skipped_image_count = len(self.parent.downloader_core.skipped_image_urls)

                # 統計情報を表示
                stats_text = f"""エラー統計情報
    ================

    総エラー数: {stats.get('total_errors', 0)}
    リトライ試行: {stats.get('retry_attempts', 0)}
    成功リトライ: {stats.get('successful_retries', 0)} (リトライ後にダウンロードが成功した回数)
    リカバリ試行: {stats.get('recovery_attempts', 0)} (自動復旧処理を試行した回数)
    成功リカバリ: {stats.get('successful_recoveries', 0)} (自動復旧処理が成功した回数)
    レジューム試行: {stats.get('resume_attempts', 0)}
    成功レジューム: {stats.get('successful_resumes', 0)}

    スキップ統計:
    URLスキップ数: {skipped_url_count}
    画像スキップ数: {skipped_image_count}

    エラーカテゴリ別:
    """
                for category, count in stats.get('error_counts_by_category', {}).items():
                    stats_text += f"  {category}: {count}\n"

                stats_text += "\nエラー深刻度別:\n"
                for severity, count in stats.get('error_counts_by_severity', {}).items():
                    stats_text += f"  {severity}: {count}\n"

                self.stats_text.insert(1.0, stats_text)
            else:
                self.stats_text.insert(1.0, """エラーハンドラーが初期化されていません

    解決方法:
    1. アプリケーションを再起動してください
    2. 設定を確認してください
    3. エラーログを確認してください""")

            self.stats_text.config(state="disabled")
        except Exception as e:
            self.parent.log(f"統計テキスト更新エラー: {e}", "error")
    
    def _reset_error_statistics(self):
        """エラー統計をリセット"""
        try:
            # ⭐追加: 確認ダイアログを表示⭐
            from tkinter import messagebox
            result = messagebox.askyesno(
                "確認",
                "エラー統計をリセットしますか？\nこの操作は取り消せません。",
                icon="warning"
            )
            
            if not result:
                return
            
            # ⭐修正: enhanced_error_handlerから統計をリセット⭐
            if hasattr(self.parent, 'enhanced_error_handler') and self.parent.enhanced_error_handler:
                self.parent.enhanced_error_handler.reset_error_statistics()
                self._update_error_statistics()
                self.parent.log("エラー統計をリセットしました", "info")
        except Exception as e:
            self.parent.log(f"エラー統計リセットエラー: {e}", "error")
    
    def _cleanup_resume_points(self):
        """レジュームポイントをクリーンアップ"""
        try:
            if hasattr(self.parent, 'unified_error_resume_manager'):
                cleaned_count = self.parent.unified_error_resume_manager.cleanup_old_resume_points()
                self._update_resume_list()
                self.parent.log(f"レジュームポイントをクリーンアップしました: {cleaned_count}件", "info")
        except Exception as e:
            self.parent.log(f"レジュームポイントクリーンアップエラー: {e}", "error")
    
    def _on_progress_window_option_changed(self):
        """プログレスバー別ウィンドウ表示オプション変更時の処理"""
        try:
            # 背景色変更機能は削除されました
            
            # プログレスバーの表示モードを切り替え
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel.switch_progress_display_mode()
                
        except Exception as e:
            self.parent.log(f"プログレスバー表示オプション変更エラー: {e}", "error")
    
    def _on_thumbnail_option_changed(self):
        """サムネイル表示オプション変更時の処理"""
        try:
            # ⭐重要: 即座に反映されるように強制的に更新⭐
            current_value = self.parent.thumbnail_display_enabled.get()
            self.parent.log(f"サムネイル表示オプション変更: {current_value}", "info")
            
            # サムネイル表示の即時反映
            if hasattr(self.parent, 'url_panel'):
                # URLパネルのサムネイル表示状態を更新
                self.parent.url_panel._update_thumbnail_display_state()
                
                # 強制再描画を削除（自然な更新に任せる）
                # self.parent.root.update_idletasks()  # 削除
                
        except Exception as e:
            self.parent.log(f"サムネイル表示オプション変更エラー: {e}", "error")
    
    def _on_progress_window_option_changed(self):
        """プログレスバー別ウィンドウ表示オプション変更時の処理"""
        try:
            # 背景色変更機能は削除されました
            
            # プログレスバーの表示モードを切り替え
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel.switch_progress_display_mode()
                
        except Exception as e:
            self.log(f"プログレスバー表示オプション変更エラー: {e}", "error")
    
    def _on_thumbnail_option_changed(self):
        """サムネイル表示オプション変更時の処理"""
        try:
            # ⭐重要: 即座に反映されるように強制的に更新⭐
            current_value = self.parent.thumbnail_display_enabled.get()
            self.parent.log(f"サムネイル表示オプション変更: {current_value}", "info")
            
            # サムネイル表示の即時反映
            if hasattr(self.parent, 'url_panel'):
                # URLパネルのサムネイル表示状態を更新
                self.parent.url_panel._update_thumbnail_display_state()
                
                # 強制再描画を削除（自然な更新に任せる）
                # self.parent.root.update_idletasks()  # 削除
                
        except Exception as e:
            self.parent.log(f"サムネイル表示オプション変更エラー: {e}", "error")
    
    def _update_progress_display_options(self):
        """プログレスバー表示制限オプションの更新"""
        try:
            is_enabled = self.parent.progress_display_limit_enabled.get()
            state = 'normal' if is_enabled else 'disabled'
            
            # 表示数設定をグレーアウト
            if hasattr(self, 'progress_retention_entry'):
                self.progress_retention_entry.config(state=state)
            
            # 詳細項目をグレーアウト
            if hasattr(self, 'display_count_frame'):
                for child in self.display_count_frame.winfo_children():
                    self._set_widget_state_recursive(child, state)
                
        except Exception as e:
            self.parent.log(f"プログレスバー表示制限オプション更新エラー: {e}", "error")
    
    def _update_progress_backup_options(self):
        """プログレスバーログ保存オプションの更新"""
        try:
            is_enabled = self.parent.progress_backup_enabled.get()
            state = 'normal' if is_enabled else 'disabled'
            
            # 詳細項目をグレーアウト
            if hasattr(self, 'progress_backup_details_frame'):
                for child in self.progress_backup_details_frame.winfo_children():
                    self._set_widget_state_recursive(child, state)
                
        except Exception as e:
            self.parent.log(f"プログレスバーログ保存オプション更新エラー: {e}", "error")
    
    def _update_dl_log_options(self):
        """DLログ保存オプションの更新"""
        try:
            is_enabled = self.parent.dl_log_enabled.get()
            state = 'normal' if is_enabled else 'disabled'
            
            # 詳細項目をグレーアウト
            if hasattr(self, 'dl_log_method_frame'):
                for child in self.dl_log_method_frame.winfo_children():
                    self._update_widget_state_recursive(child, state)
                
        except Exception as e:
            self.parent.log(f"DLログ保存オプション更新エラー: {e}", "error")
    
    def _update_integrated_error_options(self):
        """統合エラー処理オプションの更新"""
        try:
            enabled = self.parent.integrated_error_handling_enabled.get()
            state = "normal" if enabled else "disabled"
            
            # 子ウィジェットの状態を更新
            if hasattr(self, 'integrated_error_details_frame'):
                for child in self.integrated_error_details_frame.winfo_children():
                    self._set_widget_state_recursive(child, state)
                
        except Exception as e:
            self.parent.log(f"統合エラー処理オプション更新エラー: {e}", "error")
    
    def _set_widget_state_recursive(self, widget, target_state):
        """ウィジェットの状態を再帰的に設定"""
        try:
            if hasattr(widget, 'config'):
                widget.config(state=target_state)
        except tk.TclError:
            pass
        
        # 子要素も処理
        if hasattr(widget, 'winfo_children'):
            for child in widget.winfo_children():
                self._set_widget_state_recursive(child, target_state)
    
    def _select_custom_backup_path(self):
        """カスタムバックアップパスを選択"""
        try:
            directory = filedialog.askdirectory(parent=self.parent.root)
            if directory:
                self.parent.custom_backup_path.set(directory)
        except Exception as e:
            self.parent.log(f"カスタムバックアップパス選択エラー: {e}", "error")
    
    def _create_manual_backup(self):
        """手動バックアップを作成（プログレスバーログのみ保存）"""
        try:
            # ⭐修正: backup_managerを使用してプログレスバーログをバックアップ⭐
            # ⭐重要: この操作はプログレスバーのログのみを保存し、設定ファイルやバックアップは保存しない⭐
            if hasattr(self.parent, 'backup_manager'):
                # ⭐修正: backup_enabledを確認⭐
                if not self.parent.backup_manager.backup_enabled:
                    messagebox.showwarning("警告", "バックアップ機能が無効になっています。\nオプションでバックアップ機能を有効にしてください。")
                    return
                
                # ⭐修正: 保存ディレクトリを事前に確認⭐
                save_dir = None
                if hasattr(self.parent.backup_manager, '_get_save_directory'):
                    try:
                        save_dir = self.parent.backup_manager._get_save_directory()
                        if not save_dir or not isinstance(save_dir, str):
                            self.parent.log(f"手動バックアップに失敗しました: 保存ディレクトリが無効です", "error")
                            messagebox.showerror("エラー", "バックアップの作成に失敗しました。\n\n保存ディレクトリが無効です。\nオプションで保存場所を確認してください。")
                            return
                    except Exception as e:
                        self.parent.log(f"保存ディレクトリ取得エラー: {e}", "error")
                        messagebox.showerror("エラー", f"バックアップの作成に失敗しました。\n\n保存ディレクトリの取得中にエラーが発生しました:\n{e}")
                        return
                
                backup_file = self.parent.backup_manager.create_backup()
                if backup_file and isinstance(backup_file, str):
                    file_name = os.path.basename(backup_file)
                    self.parent.log(f"プログレスバーログを手動バックアップしました: {backup_file}", "info")
                    messagebox.showinfo("完了", f"プログレスバーログを保存しました:\n\nファイル名: {file_name}\n保存場所: {backup_file}")
                else:
                    # ⭐修正: 詳細なエラー情報を表示⭐
                    self.parent.log(f"手動バックアップに失敗しました (保存場所: {save_dir if save_dir else '不明'})", "error")
                    messagebox.showerror("エラー", f"バックアップの作成に失敗しました。\n\n保存場所: {save_dir if save_dir else '不明'}\n\nバックアップ機能が有効になっているか確認してください。")
            elif hasattr(self.parent, 'settings_backup_manager'):
                # フォールバック: settings_backup_managerを使用
                backup_file = self.parent.settings_backup_manager.create_backup()
                if backup_file:
                    file_name = os.path.basename(backup_file) if backup_file else "不明"
                    self.parent.log(f"ログを手動バックアップしました: {backup_file}", "info")
                    messagebox.showinfo("完了", f"バックアップを作成しました:\n\nファイル名: {file_name}\n保存場所: {backup_file}")
                else:
                    self.parent.log("手動バックアップに失敗しました", "error")
                    messagebox.showerror("エラー", "バックアップの作成に失敗しました")
            else:
                self.parent.log("バックアップマネージャーが初期化されていません", "error")
                messagebox.showerror("エラー", "バックアップマネージャーが初期化されていません")
        except Exception as e:
            self.parent.log(f"手動バックアップエラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップ作成中にエラーが発生しました:\n{e}")
    
    def _show_backup_history(self):
        """バックアップ履歴を表示"""
        try:
            # バックアップ履歴ウィンドウを作成
            history_window = tk.Toplevel(self.parent.root)
            history_window.title("バックアップ履歴")
            history_window.geometry("600x400")
            
            # 履歴リスト
            history_frame = ttk.Frame(history_window)
            history_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            ttk.Label(history_frame, text="バックアップ履歴:").pack(anchor="w")
            
            # リストボックス
            history_listbox = tk.Listbox(history_frame)
            history_listbox.pack(fill="both", expand=True, pady=5)
            
            # バックアップファイルを検索
            backup_dir = self._get_backup_directory()
            self.parent.log(f"[DEBUG] バックアップディレクトリ: {backup_dir}", "debug")
            if backup_dir and os.path.exists(backup_dir):
                backup_files = []
                for filename in sorted(os.listdir(backup_dir), reverse=True):
                    if filename.startswith("download_history_") and filename.endswith((".html", ".md", ".json", ".csv")):
                        filepath = os.path.join(backup_dir, filename)
                        try:
                            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                            backup_files.append((file_time, filename, filepath))
                        except Exception as e:
                            self.parent.log(f"バックアップファイル情報取得エラー: {e}", "warning")
                            continue
                
                # 日時でソートして表示
                for file_time, filename, filepath in sorted(backup_files, key=lambda x: x[0], reverse=True):
                    history_listbox.insert(tk.END, f"{file_time.strftime('%Y-%m-%d %H:%M:%S')} - {filename}")
                
                if not backup_files:
                    history_listbox.insert(tk.END, "バックアップファイルが見つかりません")
            else:
                history_listbox.insert(tk.END, f"バックアップディレクトリが見つかりません: {backup_dir}")
            
            # 開くボタン
            def open_selected_backup():
                selection = history_listbox.curselection()
                if selection:
                    filename = history_listbox.get(selection[0]).split(" - ")[1]
                    filepath = os.path.join(backup_dir, filename)
                    if os.path.exists(filepath):
                        import webbrowser
                        webbrowser.open(f"file:///{filepath}")
            
            ttk.Button(history_frame, text="選択したバックアップを開く", 
                      command=open_selected_backup).pack(pady=5)
            
        except Exception as e:
            self.parent.log(f"バックアップ履歴表示エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップ履歴の表示中にエラーが発生しました:\n{e}")
    
    def _get_backup_directory(self):
        """バックアップディレクトリを取得"""
        try:
            if self.parent.backup_save_location.get() == "save_folder":
                return self.parent.folder_var.get()
            elif self.parent.backup_save_location.get() == "dedicated_folder":
                base_dir = self.parent.folder_var.get()
                return os.path.join(base_dir, "download_history")
            elif self.parent.backup_save_location.get() == "custom":
                return self.parent.custom_backup_path.get()
            else:
                return self.parent.folder_var.get()
        except Exception:
            return self.parent.folder_var.get()
    
    def _update_selenium_retry_mode(self):
        """Seleniumリトライモードの更新"""
        try:
            mode = self.parent.selenium_mode.get()
            
            # 全てのSeleniumオプションをFalseにリセット
            self.parent.selenium_page_retry_enabled.set(False)
            self.parent.selenium_session_retry_enabled.set(False)
            self.parent.selenium_persistent_enabled.set(False)
            
            # 選択されたモードに応じて対応するオプションをTrueに設定
            if mode == "page":
                self.parent.selenium_page_retry_enabled.set(True)
            elif mode == "session":
                self.parent.selenium_session_retry_enabled.set(True)
            elif mode == "persistent":
                self.parent.selenium_persistent_enabled.set(True)
                
        except Exception as e:
            self.log(f"Seleniumリトライモード更新エラー: {e}", "error")
        
    
    def register_option_frame(self, option_var_name, frame):
        """オプション変数とフレームを登録して自動グレーアウト管理を有効化"""
        try:
            self.option_frames[option_var_name] = frame
            
            # 変数変更時のコールバックを設定
            option_var = getattr(self.parent, option_var_name, None)
            if option_var:
                option_var.trace('w', lambda *args: self._on_option_changed(option_var_name))
                # オプションフレーム登録完了
            else:
                self.parent.log(f"オプション変数{option_var_name}が見つかりません", "warning")
                
        except Exception as e:
            self.parent.log(f"オプションフレーム登録エラー: {e}", "error")
    
    def _on_option_changed(self, option_var_name):
        """オプション変更時の自動処理"""
        try:
            if option_var_name in self.option_frames:
                option_var = getattr(self.parent, option_var_name, None)
                if option_var:
                    is_on = option_var.get()
                    # オプション変更
                else:
                    self.parent.log(f"オプション変数{option_var_name}が見つかりません", "warning")
            else:
                self.parent.log(f"オプションフレーム{option_var_name}が登録されていません", "warning")
                    
            # 古いグレーアウト機能は削除されました
                    
        except Exception as e:
            self.parent.log(f"オプション変更処理エラー: {e}", "error")
    
    def register_option_detail_items(self, option_var_name, detail_items):
        """オプションの詳細項目を登録して自動グレーアウト管理を有効化"""
        try:
            self.option_detail_items[option_var_name] = detail_items
            
            # オプション変数の変更を監視してグレーアウト状態を更新
            if hasattr(self.parent, option_var_name):
                option_var = getattr(self.parent, option_var_name)
                option_var.trace_add('write', lambda *args, name=option_var_name: self._update_option_detail_state(name))
                
                # 起動時に初期状態を設定
                self.parent.root.after(100, lambda: self._update_option_detail_state(option_var_name))
                
        except Exception as e:
            self.parent.log(f"オプション詳細項目登録エラー: {e}", "error")
    
    def _update_option_detail_state(self, option_var_name):
        """オプションの詳細項目のグレーアウト状態を更新"""
        try:
            if option_var_name not in self.option_detail_items:
                return
                
            # オプション変数の値を取得
            if hasattr(self.parent, option_var_name):
                option_var = getattr(self.parent, option_var_name)
                is_enabled = option_var.get()
                
                # 詳細項目の状態を更新
                detail_items = self.option_detail_items[option_var_name]
                for item in detail_items:
                    if item and hasattr(item, 'winfo_exists') and item.winfo_exists():
                        # 子ウィジェットの状態を更新
                        self._update_widget_state(item, is_enabled)
                        
        except Exception as e:
            self.parent.log(f"オプション詳細状態更新エラー: {e}", "error")
    
    def _update_widget_state(self, widget, is_enabled):
        """ウィジェットとその子ウィジェットの状態を更新"""
        try:
            if not widget or not hasattr(widget, 'winfo_exists') or not widget.winfo_exists():
                return
                
            # ウィジェットの状態を更新
            if hasattr(widget, 'config'):
                try:
                    widget.config(state='normal' if is_enabled else 'disabled')
                except:
                    pass
            
            # 子ウィジェットも再帰的に更新
            try:
                for child in widget.winfo_children():
                    self._update_widget_state(child, is_enabled)
            except:
                pass
                
        except Exception as e:
            pass  # エラーは無視
    
    # 古いグレーアウト機能は削除されました
    
    # 背景色変更機能は削除されました
    
    # エラーフレーム背景色変更機能は削除されました
    
    # Seleniumリトライフレーム背景色変更機能は削除されました

    def _add_conversion_rule(self, enabled=True, find_str="", replace_str=""):
        """文字列変換ルールを追加する"""
        try:
            # 新しいフレームを作成（幅を固定して横幅拡大を防ぐ）
            rule_frame = ttk.Frame(self.conversion_rules_container)
            rule_frame.grid(row=len(self.string_conversion_rules), column=0, sticky="ew", pady=2)
            rule_frame.grid_columnconfigure(2, weight=1)  # find_entryのカラムを伸縮可能に
            rule_frame.grid_columnconfigure(4, weight=1)  # replace_entryのカラムを伸縮可能に
            # ルールフレームの幅を固定
            rule_frame.configure(width=450)
            
            # 有効/無効のチェックボックス
            enabled_var = tk.BooleanVar(value=enabled)
            enabled_cb = ttk.Checkbutton(rule_frame, variable=enabled_var)
            enabled_cb.grid(row=0, column=0, padx=2)
            
            # 検索文字列の入力フィールド
            find_var = tk.StringVar(value=find_str)
            find_entry = ttk.Entry(rule_frame, textvariable=find_var, width=15)
            find_entry.grid(row=0, column=1, sticky="ew", padx=2)
            
            # 「を」ラベル
            ttk.Label(rule_frame, text="を").grid(row=0, column=2, padx=2)
            
            # 置換文字列の入力フィールド
            replace_var = tk.StringVar(value=replace_str)
            replace_entry = ttk.Entry(rule_frame, textvariable=replace_var, width=15)
            replace_entry.grid(row=0, column=3, sticky="ew", padx=2)
            
            # 「に置換」ラベル
            ttk.Label(rule_frame, text="に置換").grid(row=0, column=4, padx=2)
            
            # ルールをリストに追加
            rule = {
                'frame': rule_frame,
                'enabled': enabled_var,
                'find': find_var,
                'replace': replace_var
            }
            self.string_conversion_rules.append(rule)
            
            # 状態更新のバインド
            enabled_cb.config(command=lambda: self._update_rule_state(enabled_var, find_entry, replace_entry))
            self._update_rule_state(enabled_var, find_entry, replace_entry)
            
            # ボタンの状態を更新
            self._update_conversion_rule_buttons()
            
        except Exception as e:
            print(f"変換ルール追加エラー: {e}")

    def _remove_conversion_rule(self):
        """最後に追加された文字列変換ルールを削除する"""
        try:
            if self.string_conversion_rules:
                rule = self.string_conversion_rules.pop()
                rule['frame'].destroy()
                self._update_conversion_rule_buttons()
        except Exception as e:
            print(f"変換ルール削除エラー: {e}")

    def _update_conversion_rule_buttons(self):
        """変換ルールボタンの状態を更新"""
        try:
            if hasattr(self, 'remove_rule_button'):
                self.remove_rule_button.config(state='normal' if self.string_conversion_rules else 'disabled')
        except Exception as e:
            print(f"ボタン状態更新エラー: {e}")
    
    def _update_rule_state(self, enabled_var, find_entry, replace_entry):
        """ルールの有効/無効状態を更新"""
        try:
            state = 'normal' if enabled_var.get() else 'disabled'
            find_entry.config(state=state)
            replace_entry.config(state=state)
        except Exception as e:
            print(f"ルール状態更新エラー: {e}")

    # 古いグレーアウト機能は削除されました

    def _set_widget_state(self, widget, state):
        """ウィジェットとその子要素の状態を設定"""
        try:
            if hasattr(widget, 'config'):
                # stateオプションを持つウィジェットのみ設定
                widget_type = widget.winfo_class()
                
                # stateオプションをサポートするウィジェットタイプ
                state_supported_types = [
                    'TButton', 'TEntry', 'TCombobox', 'TCheckbutton', 
                    'TRadiobutton', 'TText', 'TScale', 'TSpinbox',
                    'Button', 'Entry', 'Text', 'Scale', 'Spinbox'
                ]
                
                if widget_type in state_supported_types:
                    try:
                        # stateオプションが存在するかテスト
                        current_state = widget.cget('state')
                        # 存在する場合は設定
                        widget.config(state=state)
                        self.parent.log(f"ウィジェット状態設定成功: {widget_type} -> {state}", "debug")
                    except tk.TclError as e:
                        # stateオプションが存在しない場合はスキップ
                        if "unknown option" not in str(e).lower():
                            # その他のエラーの場合はログ出力
                            self.parent.log(f"ウィジェット状態設定エラー: {widget_type} - {e}", "debug")
                        pass
                else:
                    # stateオプションをサポートしないウィジェットはスキップ
                    self.parent.log(f"stateオプション非対応ウィジェット: {widget_type}", "debug")
            
            # 子要素も再帰的に設定
            for child in widget.winfo_children():
                self._set_widget_state(child, state)
        except Exception as e:
            # 予期しないエラーの場合はログ出力
            self.parent.log(f"ウィジェット状態設定予期外エラー: {e}", "debug")
            pass
    
    def _setup_placeholder(self, entry_widget, placeholder_text):
        """エントリーフィールドにプレースホルダー機能を設定"""
        try:
            # プレースホルダーの色（薄い灰色）
            placeholder_color = "#999999"
            normal_color = "#000000"
            
            # textvariableを取得
            text_var = entry_widget.cget('textvariable')
            if text_var:
                # textvariableの文字列から直接取得
                var_name = str(text_var)
                if hasattr(self.parent, var_name):
                    var = getattr(self.parent, var_name)
                else:
                    var = None
            else:
                var = None
            
            # ⭐修正: プレースホルダー表示ロジックを改善⭐
            # textvariableの値を取得
            var_value = var.get() if var else ""
            entry_value = entry_widget.get()
            
            # プレースホルダーを表示する条件:
            # 1. textvariableが空文字列またはNone
            # 2. entry_widgetが空
            # 3. 現在の値がプレースホルダーテキストと一致しない
            should_show_placeholder = False
            if var:
                # textvariableが空文字列、またはプレースホルダーテキストと一致する場合
                if not var_value or var_value == "" or var_value == placeholder_text:
                    should_show_placeholder = True
            else:
                # textvariableがない場合、entry_widgetが空の場合
                if not entry_value or entry_value == "":
                    should_show_placeholder = True
            
            # プレースホルダーを表示
            if should_show_placeholder:
                # 既存の内容をクリア
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, placeholder_text)
                # ⭐修正: グレー表示機能を削除（常に黒色で表示）⭐
                entry_widget.config(foreground=normal_color)
                # ⭐重要: プレースホルダー表示時はtextvariableを空文字列に設定⭐
                if var:
                    var.set("")
            
            # フォーカスイベント
            def on_focus_in(event):
                current_text = entry_widget.get()
                # ⭐修正: プレースホルダーテキストと一致する場合、またはtextvariableが空の場合にクリア⭐
                if current_text == placeholder_text or (var and (not var.get() or var.get() == placeholder_text)):
                    entry_widget.delete(0, tk.END)
                    entry_widget.config(foreground=normal_color)
                    # textvariableもクリア
                    if var:
                        var.set("")
            
            def on_focus_out(event):
                current_text = entry_widget.get()
                # ⭐修正: 空文字列またはプレースホルダーテキストの場合のみプレースホルダーを表示⭐
                if not current_text or current_text.strip() == "":
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, placeholder_text)
                    # ⭐修正: グレー表示機能を削除（常に黒色で表示）⭐
                    entry_widget.config(foreground=normal_color)
                    # ⭐プレースホルダー表示時はtextvariableを空文字列に設定⭐
                    if var:
                        var.set("")
                else:
                    # ⭐重要: 入力値がある場合は常に黒色で表示⭐
                    entry_widget.config(foreground=normal_color)
                    # textvariableに値を設定（プレースホルダーテキストでない場合のみ）
                    if var and current_text != placeholder_text:
                        var.set(current_text)
            
            # キー入力時の色設定
            def on_key_press(event):
                current_text = entry_widget.get()
                # ⭐修正: プレースホルダーテキストが表示されている場合は削除⭐
                if current_text == placeholder_text:
                    entry_widget.delete(0, tk.END)
                    if var:
                        var.set("")
                # キー入力時は常に黒色で表示
                entry_widget.config(foreground=normal_color)
            
            # イベントをバインド
            entry_widget.bind('<FocusIn>', on_focus_in)
            entry_widget.bind('<FocusOut>', on_focus_out)
            entry_widget.bind('<KeyPress>', on_key_press)
            
        except Exception as e:
            if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                self.parent.log(f"プレースホルダー設定エラー: {e}", "error")
    
    def _select_ssl_config_file(self):
        """SSL設定ファイルを選択"""
        try:
            import tkinter.filedialog as fd
            
            # ファイル選択ダイアログを表示
            file_path = fd.askopenfilename(
                title="SSL設定ファイルを選択",
                filetypes=[
                    ("JSON files", "*.json"),
                    ("Text files", "*.txt"),
                    ("All files", "*.*")
                ],
                initialdir="."
            )
            
            if file_path:
                # 選択されたファイルパスを設定
                if hasattr(self.parent, 'custom_ssl_config_file'):
                    self.parent.custom_ssl_config_file.set(file_path)
                    self.parent.log(f"SSL設定ファイルを選択しました: {file_path}", "info")
                else:
                    self.parent.log("SSL設定ファイル変数が見つかりません", "error")
                    
        except Exception as e:
            self.parent.log(f"SSL設定ファイル選択エラー: {e}", "error")
    
    def _setup_placeholder(self, entry_widget, placeholder_text):
        """エントリーウィジェットにプレースホルダー機能を追加
        
        Args:
            entry_widget: ttk.Entryウィジェット
            placeholder_text: プレースホルダーとして表示するテキスト
        """
        try:
            # プレースホルダーの状態を管理する属性を追加
            entry_widget._placeholder_text = placeholder_text
            entry_widget._is_placeholder = True
            
            # 初期状態でプレースホルダーを表示
            if not entry_widget.get():
                entry_widget.insert(0, placeholder_text)
                entry_widget.config(foreground='gray')
                entry_widget._is_placeholder = True
            else:
                # 既に値がある場合は黒で表示
                entry_widget.config(foreground='black')
                entry_widget._is_placeholder = False
            
            def on_focus_in(event):
                """フォーカスイン時の処理"""
                if entry_widget._is_placeholder:
                    entry_widget.delete(0, tk.END)
                    entry_widget.config(foreground='black')
                    entry_widget._is_placeholder = False
            
            def on_focus_out(event):
                """フォーカスアウト時の処理"""
                if not entry_widget.get():
                    entry_widget.insert(0, placeholder_text)
                    entry_widget.config(foreground='gray')
                    entry_widget._is_placeholder = True
                else:
                    # 値がある場合は黒で表示
                    entry_widget.config(foreground='black')
                    entry_widget._is_placeholder = False
            
            # イベントをバインド
            entry_widget.bind('<FocusIn>', on_focus_in)
            entry_widget.bind('<FocusOut>', on_focus_out)
            
        except Exception as e:
            if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                self.parent.log(f"プレースホルダー設定エラー: {e}", "error")
    
    def _on_selenium_always_enabled_changed(self):
        """常時Selenium使用オプションが変更されたときの処理"""
        try:
            self._update_page_info_selenium_state()
            # デバッグログ
            if hasattr(self.parent, 'selenium_always_enabled'):
                is_enabled = self.parent.selenium_always_enabled.get()
                if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                    self.parent.log(f"常時Selenium: {'ON' if is_enabled else 'OFF'}", "debug")
        except Exception as e:
            if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                self.parent.log(f"Selenium状態更新エラー: {e}", "error")
    
    def _update_page_info_selenium_state(self):
        """ページ情報取得Seleniumオプションの状態を更新"""
        try:
            # ⭐修正: 常時Selenium(selenium_always_enabled)に連動⭐
            if hasattr(self, 'page_info_selenium_frame') and hasattr(self.parent, 'selenium_always_enabled'):
                # 常時SeleniumがONの場合のみ有効
                # BooleanVarの場合とboolの場合の両方に対応
                if isinstance(self.parent.selenium_always_enabled, tk.BooleanVar):
                    enabled = self.parent.selenium_always_enabled.get()
                else:
                    enabled = bool(self.parent.selenium_always_enabled)
                
                state = 'normal' if enabled else 'disabled'
                
                # フレーム内の全ウィジェットの状態を再帰的に更新
                if hasattr(self.page_info_selenium_frame, 'winfo_children'):
                    self._update_widget_state_recursive(self.page_info_selenium_frame, state)
        except Exception as e:
            if hasattr(self, 'parent') and hasattr(self.parent, 'log'):
                self.parent.log(f"ページ情報Selenium状態更新エラー: {e}", "error")
                import traceback
                self.parent.log(f"詳細: {traceback.format_exc()}", "debug")
    
    def _update_widget_state_recursive(self, widget, state):
        """ウィジェットとその子要素を再帰的に状態更新（ラベル以外）"""
        try:
            # 自身の状態を更新（ラベルとフレーム以外）
            if not isinstance(widget, (ttk.Label, ttk.Frame, ttk.LabelFrame)) and hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except tk.TclError:
                    pass  # 一部のウィジェットはstate設定不可
            
            # 子要素を再帰的に更新
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    self._update_widget_state_recursive(child, state)
        except Exception:
            pass  # エラーは無視して続行