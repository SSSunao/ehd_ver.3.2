# -*- coding: utf-8 -*-
"""
Download List Presentation Layer (三相設計: プレゼンテーション層)

このモジュールはTreeviewを使用したUI表示を担当します。
ビジネスロジック層と連携し、ユーザーインタラクションを処理します。
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
import webbrowser
from gui.components.download_list_model import DownloadItem, DownloadStatus
from gui.components.download_list_controller import DownloadListController
from core.communication.ui_bridge import ThreadSafeUIBridge


class DownloadListTreeview(ttk.Frame):
    """
    ダウンロードリストのTreeviewウィジェット
    
    責務:
    - Treeviewの描画・更新
    - ユーザーイベント処理（クリック、右クリックメニュー等）
    - サムネイル表示
    
    設計原則:
    - ビジネスロジックを含まない（Controllerに委譲）
    - イベント駆動（Controllerからの通知を受け取る）
    """
    
    def __init__(self, parent, controller: DownloadListController, **kwargs):
        """
        Args:
            parent: 親ウィジェット
            controller: ビジネスロジック層
            **kwargs: ttk.Frameのオプション
        """
        super().__init__(parent, **kwargs)
        
        self.controller = controller
        
        # ⭐Phase 1: ThreadSafeUIBridge初期化（段階的改善）⭐
        self.ui_bridge = None  # 後でルートウィンドウから設定
        
        # コールバック（外部から設定）
        self.on_url_open: Optional[Callable[[str], None]] = None
        self.on_item_edit: Optional[Callable[[DownloadItem], None]] = None
        self.on_item_delete: Optional[Callable[[DownloadItem], None]] = None
        
        # サムネイル表示用
        self.thumbnail_window: Optional[tk.Toplevel] = None
        self.thumbnail_label: Optional[tk.Label] = None
        
        # UI構築
        print(f"[DEBUG] DownloadListTreeview.__init__: self.ui_bridge={self.ui_bridge}")
        print(f"[DEBUG] DownloadListTreeview.__init__: self.parent={parent}")
        try:
            print(f"[DEBUG] DownloadListTreeview.__init__: self.parent.root={getattr(parent, 'root', None)}")
        except Exception as e:
            print(f"[DEBUG] DownloadListTreeview.__init__: self.parent.root取得エラー: {e}")
        self._create_widgets()
        self._setup_bindings()
        
        # Controllerのイベントリスナーに登録
        self.controller.add_listener(self._on_controller_event)
    
    def _create_widgets(self):
        """ウィジェット作成"""
        # ラベルフレーム
        self.label_frame = ttk.LabelFrame(self, text="DLリスト")
        self.label_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # ⭐「検索結果からDLリスト作成」ボタン（最上段左上）⭐
        parser_button_frame = ttk.Frame(self.label_frame)
        parser_button_frame.pack(fill="x", padx=5, pady=(5, 0))
        
        # ⭐修正: parentを外部から渡すように⭐
        self.parent_window = None  # 後で設定
        
        self.parser_button = ttk.Button(
            parser_button_frame,
            text="検索結果からDLリストの作成",
            command=self._launch_parser
        )
        self.parser_button.pack(side="left", padx=2)
        
        # Treeviewフレーム
        tree_frame = ttk.Frame(self.label_frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Treeview
        columns = ("status", "url", "title", "info")  # ⭐進捗列を削除⭐
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=15,
            selectmode="browse"  # ⭐修正: 1つだけ選択可能（排他的選択）⭐
        )
        
        # ⭐行高さ5px増加⭐
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)  # デフォルト20 → 25
        
        # ⭐縦線追加（薄い灰色）⭐
        style.layout("Treeview", [
            ('Treeview.treearea', {'sticky': 'nswe'})
        ])
        style.configure("Treeview",
                       background="white",
                       fieldbackground="white",
                       borderwidth=1,
                       relief="solid")
        
        # 列設定
        self.tree.heading("status", text="状態")
        self.tree.heading("url", text="URL")
        self.tree.heading("title", text="タイトル")
        self.tree.heading("info", text="情報")  # ⭐マーカー/エラー統合⭐
        
        self.tree.column("status", width=80, anchor="center", stretch=False)
        self.tree.column("url", width=350)
        self.tree.column("title", width=300)
        self.tree.column("info", width=350)  # ⭐幅広めに調整⭐
        
        # スクロールバー
        scrollbar_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # 配置
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # タグ設定（背景色）
        for status in DownloadStatus:
            self.tree.tag_configure(status.value, background=status.color)
        
        # ⭐修正: 選択時の色設定を濃い青に変更⭐
        style.map("Treeview",
                 background=[('selected', '#0056B3')],  # 濃い青（Bootstrap primary-dark相当）
                 foreground=[('selected', 'white')])
        
        # ⭐ボタンフレーム（「検索結果からDLリスト作成」の下）⭐
        button_frame = ttk.Frame(self.label_frame)
        button_frame.pack(fill="x", padx=5, pady=(5, 5))
        
        # ボタン配置
        ttk.Button(button_frame, text="📋 クリップボードから貼り付け",
                   command=self._paste_from_clipboard).pack(side="left", padx=2)
        ttk.Button(button_frame, text="📄 全URLコピー",
                   command=self._copy_all_urls).pack(side="left", padx=2)
        ttk.Button(button_frame, text="➖ 最下段削除",
                   command=self._delete_last).pack(side="left", padx=2)
        ttk.Button(button_frame, text="🗑 全削除",
                   command=self._delete_all).pack(side="left", padx=2)
        
        # 統計情報ラベル
        self.stats_label = ttk.Label(button_frame, text="総計: 0 | 完了: 0 | 待機: 0")
        self.stats_label.pack(side="right", padx=5)
        
        # ⭐フェーズ3: URL検索ボックス追加⭐
        search_frame = ttk.Frame(self.label_frame)
        search_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(search_frame, text="🔍 検索:").pack(side="left", padx=2)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side="left", padx=2)
        self.search_var.trace('w', lambda *args: self._on_search_changed())
        
        ttk.Button(search_frame, text="クリア", command=self._clear_search).pack(side="left", padx=2)
        
        self.search_result_label = ttk.Label(search_frame, text="")
        self.search_result_label.pack(side="left", padx=5)
    
    def _setup_bindings(self):
        """イベントバインディング"""
        # ⭐修正: シングルクリック: 選択/解除の排他制御⭐
        self.tree.bind("<Button-1>", self._on_single_click)
        
        # ダブルクリック: URLを開く
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # 右クリック: コンテキストメニュー
        self.tree.bind("<Button-3>", self._on_right_click)
        
        # マウスホバー: サムネイル表示
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._on_leave)
        
        # Deleteキー: 削除
        self.tree.bind("<Delete>", self._on_delete_key)
        
        # ⭐フェーズ3: ドラッグ&ドロップ機能追加⭐
        try:
            import tkinterdnd2
            if hasattr(tkinterdnd2, 'DND_FILES') and hasattr(self.tree, 'drop_target_register'):
                self.tree.drop_target_register(tkinterdnd2.DND_FILES, tkinterdnd2.DND_TEXT)
                self.tree.dnd_bind('<<Drop>>', self._on_drop)
        except Exception as e:
            # D&D機能が利用できない場合は静かに無視
            pass
    
    # ==================== コントローラーイベント処理 ====================
    
    def _on_controller_event(self, event_type: str, *args):
        """コントローラーからのイベントを処理（★スレッドセーフ対応）"""
        # ⭐修正: after()を使用してメインスレッドでGUI更新を実行⭐
        def update_gui():
            print(f"[DEBUG] update_gui: start event_type={event_type}")
            try:
                # ⭐デバッグログ追加: イベント受信確認⭐
                print(f"[DEBUG] View: received event '{event_type}' with {len(args)} args")
                if event_type == 'item_added':
                    item = args[0]
                    self._add_tree_item(item)
                elif event_type == 'items_added_batch':
                    items = args[0]
                    for item in items:
                        self._add_tree_item(item)
                elif event_type == 'item_updated':
                    old_item, new_item = args
                    print(f"[DEBUG] View: updating tree item - status: {new_item.status.value}, title: {new_item.title[:30]}")
                    self._update_tree_item(new_item)
                elif event_type == 'item_deleted':
                    item = args[0]
                    self._delete_tree_item(item)
                elif event_type == 'cleared':
                    self._clear_tree()
                elif event_type == 'items_imported':
                    count = args[0]
                    self._reload_all_items()
                # 統計情報を更新
                self._update_statistics()
                print(f"[DEBUG] update_gui: end event_type={event_type}")
            except Exception as e:
                print(f"[ERROR] View GUI更新エラー: {e}")
                import traceback
                traceback.print_exc()
        
        # ⭐Phase 1: ui_bridge経由でメインスレッド実行（スレッドセーフ）⭐
        if self.ui_bridge:
            self.ui_bridge.schedule_update(update_gui)
        else:
            # フォールバック: ui_bridgeがない場合は直接after()
            try:
                self.after(0, update_gui)
            except Exception as e:
                print(f"[ERROR] after()失敗: {e}")
    
    # ==================== Treeview操作 ====================
    
    def _add_tree_item(self, item: DownloadItem):
        """Treeviewにアイテムを追加"""
        values = self._item_to_values(item)
        iid = self.tree.insert('', 'end', values=values, tags=(item.status.value,))
        
        # ControllerにiidをHint
        self.controller.set_iid(item.url, iid)
    
    def _update_tree_item(self, item: DownloadItem):
        """Treeviewのアイテムを更新"""
        print(f"[DEBUG] _update_tree_item: start url={item.url[:50]}, iid={item.iid}")
        if not item.iid:
            print(f"[WARNING] View: item has no iid, searching by URL - URL: {item.url[:50]}")
            # ⭐修正: iidがない場合、TreeViewから検索して設定⭐
            found = False
            for child in self.tree.get_children():
                child_values = self.tree.item(child)['values']
                if child_values and len(child_values) > 0:
                    # URL列（最後の列）で比較
                    if child_values[-1] == item.url:
                        # 見つかったiidをControllerに設定
                        self.controller.set_iid(item.url, child)
                        item = self.controller.get_item(item.url)  # 更新されたitemを取得
                        found = True
                        print(f"[DEBUG] View: found iid by URL search: {child}")
                        break
            if not found:
                print(f"[WARNING] View: item not found in tree, skipping update")
                return
        try:
            values = self._item_to_values(item)
            self.tree.item(item.iid, values=values, tags=(item.status.value,))
            print(f"[DEBUG] View: tree item updated successfully - iid: {item.iid}, title: {item.title[:30] if item.title else 'N/A'}")
        except tk.TclError as e:
            print(f"[WARNING] View: TclError updating tree item - {e}")
            # iidが存在しない場合は再追加
            self._add_tree_item(item)
        print(f"[DEBUG] _update_tree_item: end url={item.url[:50]}, iid={item.iid}")
    
    def _delete_tree_item(self, item: DownloadItem):
        """Treeviewからアイテムを削除"""
        if item.iid:
            try:
                self.tree.delete(item.iid)
            except tk.TclError:
                pass
    
    def _clear_tree(self):
        """Treeviewをクリア"""
        for child in self.tree.get_children():
            self.tree.delete(child)
    
    def _reload_all_items(self):
        """全アイテムを再読み込み"""
        self._clear_tree()
        for item in self.controller.get_all_items():
            self._add_tree_item(item)
    
    def _item_to_values(self, item: DownloadItem) -> tuple:
        """DownloadItemをTreeview用の値に変換"""
        # ⭐情報列: マーカーとエラーを統合⭐
        info_parts = []
        
        # マーカー（圧縮・リサイズ）
        if item.markers_text:
            info_parts.append(item.markers_text)
        
        # エラーメッセージ
        if item.error_message:
            error_text = item.error_message[:50] + "..." if len(item.error_message) > 50 else item.error_message
            info_parts.append(f"❌ {error_text}")
        
        info_text = " | ".join(info_parts) if info_parts else ""
        
        return (
            item.status.icon,
            item.url[:80] + "..." if len(item.url) > 80 else item.url,
            item.title,
            info_text  # ⭐進捗列を削除⭐
        )
    
    # ==================== ユーザーインタラクション ====================
    
    def _on_single_click(self, event):
        """シングルクリック処理（選択/解除の排他制御）"""
        iid = self.tree.identify_row(event.y)
        
        # 空欄をクリックした場合は選択を解除
        if not iid:
            self.tree.selection_remove(self.tree.selection())
            return
        
        # 現在の選択を取得
        current_selection = self.tree.selection()
        
        # 同じアイテムをクリックした場合は選択を解除
        if current_selection and iid in current_selection:
            self.tree.selection_remove(iid)
            return "break"  # デフォルトの選択動作を抑制
        
        # 別のアイテムをクリックした場合は選択を切り替え
        # （selectmode="browse"なので自動的に排他的選択になる）
    
    def _on_double_click(self, event):
        """ダブルクリック処理"""
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        
        column = self.tree.identify_column(event.x)
        
        # URL列（#2）の場合はURLを開く
        if column == "#2":
            item = self.controller.get_item_by_iid(iid)
            if item and self.on_url_open:
                self.on_url_open(item.url)
            elif item:
                webbrowser.open(item.url)
    
    def _on_right_click(self, event):
        """右クリックメニュー"""
        iid = self.tree.identify_row(event.y)
        
        # ⭐修正: 既に選択されているアイテムがある場合はそれを優先⭐
        current_selection = self.tree.selection()
        if current_selection and not iid:
            # 選択されたアイテムがあるが、空欄で右クリックした場合
            # 選択されたアイテムに対してメニューを表示
            iid = current_selection[0]
        elif not iid and not current_selection:
            # 空欄で右クリックした場合のメニュー
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="📋 クリップボードから貼り付け", command=self._paste_from_clipboard)
            menu.add_command(label="📄 全URLコピー", command=self._copy_all_urls)
            menu.add_command(label="➖ 最下段を削除", command=self._delete_last)
            menu.add_command(label="🗑 全削除", command=self._delete_all)
            menu.tk_popup(event.x_root, event.y_root)
            return
        elif iid and iid not in current_selection:
            # 選択されていないアイテムを右クリックした場合は選択
            self.tree.selection_set(iid)
        
        # アイテム取得
        item = self.controller.get_item_by_iid(iid)
        if not item:
            return
        
        # メニュー作成
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="URLを開く", command=lambda: self._open_url(item))
        menu.add_command(label="URLをコピー", command=lambda: self._copy_url(item))
        menu.add_separator()
        
        if item.is_editable:
            menu.add_command(label="編集", command=lambda: self._edit_item(item))
        
        if item.is_deletable:
            menu.add_command(label="削除", command=lambda: self._delete_item(item))
        else:
            menu.add_command(label="削除（不可）", state="disabled")
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _on_motion(self, event):
        """マウスホバー処理（サムネイル表示）"""
        try:
            # ⭐修正: parent_windowを直接使用（初期化時に設定済み）⭐
            if not hasattr(self, 'parent_window') or not self.parent_window:
                return
            
            if not hasattr(self.parent_window, 'thumbnail_display_enabled'):
                return
            
            if self.parent_window.thumbnail_display_enabled.get() != "on":
                return
            
            # ホバーしている行を取得
            iid = self.tree.identify_row(event.y)
            if not iid:
                self._hide_thumbnail()
                return
            
            # アイテム取得
            item = self.controller.get_item_by_iid(iid)
            if not item or not item.url:
                self._hide_thumbnail()
                return
            
            # 既に同じURLのサムネイルを表示中の場合はスキップ
            if (hasattr(self, 'thumbnail_window') and self.thumbnail_window and 
                hasattr(self.thumbnail_window, "current_url") and 
                self.thumbnail_window.current_url == item.url):
                return
            
            # サムネイルを表示
            self._show_thumbnail(item.url, event.x_root, event.y_root)
            
        except Exception as e:
            pass  # エラーを無視（無限ループ防止）
    
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
                gallery_url = url
            
            if not gallery_url:
                return
            
            # サムネイルウィンドウを作成
            self.thumbnail_window = tk.Toplevel(self.master)
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
            pass  # エラーは無視
    
    def _on_leave(self, event):
        """マウスリーブ処理"""
        self._hide_thumbnail()
    
    def _launch_parser(self):
        """検索結果パーサーを起動"""
        if self.parent_window and hasattr(self.parent_window, 'launch_parser'):
            self.parent_window.launch_parser()
        else:
            messagebox.showwarning("警告", "パーサー機能が利用できません")
    
    def _on_delete_key(self, event):
        """Deleteキー処理"""
        selection = self.tree.selection()
        if not selection:
            return
        
        for iid in selection:
            item = self.controller.get_item_by_iid(iid)
            if item:
                self._delete_item(item)
    
    def _on_drop(self, event):
        """
        ドラッグ&ドロップ処理
        
        ⭐フェーズ3: URLファイル、テキストのドロップをサポート⭐
        """
        try:
            import re
            dropped_data = event.data
            
            # URL抽出パターン
            pattern = r'https?://(?:www\.)?e[-x]hentai\.org/g/\d+/[a-f0-9]+/?'
            urls = re.findall(pattern, dropped_data, re.IGNORECASE)
            
            if not urls:
                messagebox.showwarning("警告", "有効なURLが見つかりませんでした")
                return
            
            # 重複除去
            unique_urls = list(dict.fromkeys(urls))
            
            # 追加
            added_items = self.controller.add_urls_batch(unique_urls)
            
            messagebox.showinfo("完了", f"{len(added_items)}件のURLを追加しました")
            
        except Exception as e:
            messagebox.showerror("エラー", f"ドロップ処理エラー: {e}")
    
    # ==================== ボタンアクション ====================
    
    def _paste_from_clipboard(self):
        """クリップボードから貼り付け"""
        # ⭐重複防止ガード: 短時間での連続呼び出しを防ぐ⭐
        import time
        current_time = time.time()
        if hasattr(self, '_last_paste_time') and (current_time - self._last_paste_time) < 0.5:
            print(f"[DEBUG] 貼り付け処理がスキップされました（連続呼び出し防止）")
            return
        self._last_paste_time = current_time
        
        try:
            clipboard_text = self.clipboard_get()
            
            print(f"[DEBUG] クリップボード内容: {repr(clipboard_text[:200])}")  # デバッグ
            
            # ⭐空白や改行を削除⭐
            clipboard_text = clipboard_text.strip()
            if not clipboard_text:
                messagebox.showwarning("警告", "クリップボードが空です")
                return
            
            # URL抽出（簡易実装）
            import re
            pattern = r'https?://(?:www\.)?e[-x]hentai\.org/g/\d+/[a-f0-9]+/?'
            urls = re.findall(pattern, clipboard_text, re.IGNORECASE)
            
            print(f"[DEBUG] 抽出されたURL: {urls}")  # デバッグ
            
            if not urls:
                messagebox.showwarning("警告", "有効なURLが見つかりませんでした")
                return
            
            # ⭐重複除去（OrderedDictで順序保持）⭐
            from collections import OrderedDict
            unique_urls = list(OrderedDict.fromkeys(urls))
            
            print(f"[DEBUG] 重複除去後: {unique_urls}")  # デバッグ
            
            # ⭐既に存在するURLをスキップ⭐
            new_urls = [url for url in unique_urls if not self.controller.contains_url(url)]
            
            print(f"[DEBUG] 新規URL: {new_urls}")  # デバッグ
            
            if not new_urls:
                messagebox.showinfo("情報", "全てのURLが既に追加されています")
                return
            
            # 追加
            added_items = self.controller.add_urls_batch(new_urls)
            
            print(f"[DEBUG] 追加されたアイテム数: {len(added_items)}")  # デバッグ
            print(f"[DEBUG] 現在のTreeview総数: {self.controller.get_total_count()}")  # デバッグ
            
            messagebox.showinfo("完了", f"{len(added_items)}件のURLを追加しました")
            
        except tk.TclError:
            messagebox.showerror("エラー", "クリップボードが空です")
    
    def _copy_all_urls(self):
        """全URLをコピー"""
        urls_text = self.controller.export_urls_as_text()
        
        if not urls_text:
            messagebox.showwarning("警告", "URLがありません")
            return
        
        self.clipboard_clear()
        self.clipboard_append(urls_text)
        
        messagebox.showinfo("完了", f"{self.controller.get_total_count()}件のURLをコピーしました")
    
    def _delete_last(self):
        """最下段を削除"""
        items = self.controller.get_all_items()
        if not items:
            messagebox.showwarning("警告", "URLがありません")
            return
        
        last_item = items[-1]
        
        if not last_item.is_deletable:
            messagebox.showwarning("警告", "このアイテムは削除できません")
            return
        
        self.controller.delete_item(last_item.url)
    
    def _delete_all(self):
        """全削除（確認ダイアログ）"""
        if not self.controller.get_total_count():
            messagebox.showwarning("警告", "URLがありません")
            return
        
        result = messagebox.askyesno(
            "確認",
            f"{self.controller.get_total_count()}件のURLを全て削除しますか？\n\n"
            "※DL中・完了のアイテムは削除されません"
        )
        
        if result:
            print(f"[DEBUG] 全削除前のアイテム数: {self.controller.get_total_count()}")  # デバッグ
            deleted_count = self.controller.delete_all(force=False)
            print(f"[DEBUG] 削除されたアイテム数: {deleted_count}")  # デバッグ
            print(f"[DEBUG] 全削除後のアイテム数: {self.controller.get_total_count()}")  # デバッグ
            messagebox.showinfo("完了", f"{deleted_count}件のURLを削除しました")
    
    # ==================== ヘルパーメソッド ====================
    
    def _open_url(self, item: DownloadItem):
        """URLを開く"""
        if self.on_url_open:
            self.on_url_open(item.url)
        else:
            webbrowser.open(item.url)
    
    def _copy_url(self, item: DownloadItem):
        """URLをコピー"""
        self.clipboard_clear()
        self.clipboard_append(item.url)
        messagebox.showinfo("完了", "URLをコピーしました")
    
    def _edit_item(self, item: DownloadItem):
        """アイテムを編集"""
        if self.on_item_edit:
            self.on_item_edit(item)
        else:
            # デフォルト: 簡易編集ダイアログ
            from tkinter import simpledialog
            new_url = simpledialog.askstring("URL編集", "新しいURLを入力:", initialvalue=item.url)
            
            if new_url and new_url != item.url:
                # 削除して再追加
                self.controller.delete_item(item.url)
                self.controller.add_url(new_url, title=item.title)
    
    def _delete_item(self, item: DownloadItem):
        """アイテムを削除"""
        if self.on_item_delete:
            self.on_item_delete(item)
        else:
            try:
                self.controller.delete_item(item.url)
            except PermissionError as e:
                messagebox.showwarning("警告", str(e))
    
    def _hide_thumbnail(self):
        """サムネイルを非表示"""
        try:
            if hasattr(self, 'thumbnail_window') and self.thumbnail_window:
                self.thumbnail_window.destroy()
                self.thumbnail_window = None
        except Exception as e:
            pass  # エラーは無視
    
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
            return None
    
    def _fetch_and_display_thumbnail_async(self, gallery_url, loading_label, popup_frame):
        """非同期でサムネイルを取得・表示"""
        try:
            # サムネイルURLを取得
            thumbnail_url = self._get_thumbnail_url(gallery_url)
            if not thumbnail_url:
                self.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, error="サムネイルURLが取得できませんでした"))
                return
            
            # サムネイル画像を取得
            import requests
            from PIL import Image, ImageTk
            from io import BytesIO
            
            response = requests.get(thumbnail_url, timeout=10)
            response.raise_for_status()
            
            # 画像を読み込み
            image = Image.open(BytesIO(response.content))
            
            # リサイズ（最大300x400）
            max_width = 300
            max_height = 400
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # Tkinter用に変換
            photo = ImageTk.PhotoImage(image)
            
            # UIスレッドで表示を更新
            self.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, photo=photo))
            
        except Exception as e:
            self.after(0, lambda: self._update_thumbnail_content(loading_label, popup_frame, error=f"エラー: {str(e)}"))
    
    def _update_thumbnail_content(self, loading_label, popup_frame, photo=None, error=None):
        """サムネイル表示内容を更新（UIスレッドで実行）"""
        try:
            loading_label.destroy()
            
            if photo:
                # 画像を表示
                img_label = tk.Label(popup_frame, image=photo)
                img_label.image = photo  # 参照を保持
                img_label.pack(expand=True)
            elif error:
                # エラーメッセージを表示
                error_label = tk.Label(popup_frame, text=error, font=("Arial", 10), fg="red")
                error_label.pack(expand=True)
        except Exception as e:
            pass  # エラーは無視
    
    def _update_statistics(self):
        """統計情報を更新"""
        stats = self.controller.get_statistics()
        text = (
            f"総計: {stats['total']} | "
            f"完了: {stats['completed']} | "
            f"待機: {stats['pending']} | "
            f"DL中: {stats['downloading']} | "
            f"エラー: {stats['error']}"
        )
        self.stats_label.config(text=text)
    
    # ==================== 公開API ====================
    
    def get_selected_items(self) -> list:
        """選択されたアイテムを取得"""
        selection = self.tree.selection()
        items = []
        for iid in selection:
            item = self.controller.get_item_by_iid(iid)
            if item:
                items.append(item)
        return items
    
    def scroll_to_item(self, url: str):
        """指定URLにスクロール"""
        item = self.controller.get_item(url)
        if item and item.iid:
            self.tree.see(item.iid)
            self.tree.selection_set(item.iid)
    
    # ⭐フェーズ3: URL検索機能⭐
    
    def _on_search_changed(self):
        """検索テキスト変更時の処理"""
        if not hasattr(self, 'search_var'):
            return
            
        keyword = self.search_var.get().strip()
        
        if not keyword:
            # 検索クリア: 全アイテムを再表示
            self._reload_all_items()
            if hasattr(self, 'search_result_label'):
                self.search_result_label.config(text="")
            return
        
        # 検索実行
        results = self.controller.search_by_title(keyword)
        
        # Treeviewを更新
        self._clear_tree()
        for item in results:
            self._add_tree_item(item)
        
        # 結果表示
        if hasattr(self, 'search_result_label'):
            self.search_result_label.config(text=f"{len(results)}件")
    
    def _clear_search(self):
        """検索をクリア"""
        if hasattr(self, 'search_var'):
            self.search_var.set("")
        self._reload_all_items()
        if hasattr(self, 'search_result_label'):
            self.search_result_label.config(text="")


# エクスポート
__all__ = ['DownloadListTreeview']
