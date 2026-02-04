# -*- coding: utf-8 -*-
"""
Compression Manager - 圧縮処理の専門コンポーネント

責任範囲:
- フォルダ圧縮処理
- 圧縮タスクの並行実行管理
- 圧縮後のファイル削除処理
- 未完了フォルダの接頭辞管理
"""

import os
import threading
from typing import Optional


class CompressionManager:
    """圧縮処理を担当するマネージャー
    
    downloader.pyから圧縮処理ロジックを分離し、
    単一責任の原則に従った設計を実現。
    """
    
    def __init__(self, parent):
        """初期化
        
        Args:
            parent: EHDownloaderCoreインスタンス（依存性注入）
        """
        self.parent = parent
        self.session_manager = parent.session_manager
        
        # 圧縮タスク管理
        self.compression_tasks = {}
        self.compression_in_progress = False
        self.compression_target_folder = None
        self.compression_target_url = None
    
    def start_compression_task(self, folder_path: str, url: Optional[str] = None):
        """圧縮タスクを並行して開始
        
        Args:
            folder_path: 圧縮対象フォルダパス
            url: 関連するURL（オプション）
        """
        try:
            # 圧縮が有効かチェック
            if not hasattr(self.parent.parent, 'compression_enabled'):
                return
            
            compression_enabled = self.parent.parent.compression_enabled.get() \
                if hasattr(self.parent.parent.compression_enabled, 'get') else "off"
            if compression_enabled != "on":
                return
            
            if not os.path.exists(folder_path):
                self.session_manager.ui_bridge.post_log(
                    f"圧縮対象フォルダが存在しません: {folder_path}", "warning"
                )
                return
            
            def compress_thread():
                try:
                    # 圧縮状態を実行中に設定
                    self.compression_in_progress = True
                    self.compression_target_folder = folder_path
                    self.compression_target_url = url
                    
                    if url:
                        self.compression_tasks[url] = 'running'
                        self.session_manager.ui_bridge.post_log(
                            f"🗜️  圧縮開始: {os.path.basename(folder_path)}"
                        )
                    else:
                        self.session_manager.ui_bridge.post_log(
                            f"🗜️  圧縮開始: {os.path.basename(folder_path)}"
                        )
                    
                    # 圧縮実行
                    self.compress_folder(folder_path)
                    
                    # ⭐修正: 圧縮完了処理（ログはcompress_folder内で出力済み）⭐
                    self.compression_in_progress = False
                    self.compression_target_folder = None
                    self.compression_target_url = None
                    
                    if url:
                        self.compression_tasks[url] = 'completed'
                        
                        # UIスレッドで圧縮完了マーカーを追加
                        self.parent.parent.async_executor.execute_gui_async(
                            lambda: self._add_compression_complete_marker(url)
                        )
                    
                except Exception as e:
                    if url:
                        self.compression_tasks[url] = 'error'
                        self.session_manager.ui_bridge.post_log(
                            f"圧縮エラー: {folder_path} (URL: {url}) - {e}", "error"
                        )
                    else:
                        self.session_manager.ui_bridge.post_log(
                            f"圧縮エラー: {folder_path} - {e}", "error"
                        )
            
            # 圧縮を別スレッドで実行
            compression_thread = threading.Thread(target=compress_thread, daemon=True)
            compression_thread.start()
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"圧縮タスク開始エラー: {e}", "error"
            )
    
    def compress_folder(self, folder_path: str):
        """フォルダの圧縮処理
        
        Args:
            folder_path: 圧縮対象フォルダパス
        """
        try:
            if not hasattr(self.parent.parent, 'compression_enabled') or \
               self.parent.parent.compression_enabled.get() != "on":
                return
            
            # フォルダ名から接頭辞を削除（圧縮前に実行）
            if hasattr(self.parent.parent, 'rename_incomplete_folder') and \
               self.parent.parent.rename_incomplete_folder.get():
                new_folder_path = self.remove_incomplete_prefix(folder_path)
                if new_folder_path and new_folder_path != folder_path:
                    folder_path = new_folder_path
            
            format_type = self.parent.parent.compression_format.get() \
                if hasattr(self.parent.parent, 'compression_format') else "ZIP"
            base_name = os.path.basename(folder_path)
            parent_dir = os.path.dirname(folder_path)
            
            if format_type == "ZIP":
                archive_path = os.path.join(parent_dir, f"{base_name}.zip")
                
                # リサイズ設定に応じた圧縮対象の決定
                resize_enabled = hasattr(self.parent.parent, 'resize_enabled') and \
                                self.parent.parent.resize_enabled.get() == "on"
                keep_original = hasattr(self.parent.parent, 'keep_original') and \
                               self.parent.parent.keep_original.get()
                
                import zipfile
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_name = os.path.relpath(file_path, folder_path)
                            
                            # リサイズ設定に応じた圧縮対象の判定
                            is_resized = "resized" in os.path.dirname(file_path)
                            
                            # 圧縮対象の判定
                            should_compress = False
                            if resize_enabled:
                                if keep_original:
                                    # オリジナル保持ON: オリジナルのみ圧縮
                                    should_compress = not is_resized
                                else:
                                    # オリジナル保持OFF: リサイズファイルのみ圧縮
                                    should_compress = is_resized
                            else:
                                # リサイズ無効: すべてのファイルを圧縮
                                should_compress = True
                            
                            if should_compress:
                                zipf.write(file_path, arc_name)
                
                self.session_manager.ui_bridge.post_log(
                    f"✅ ZIP圧縮完了: {os.path.basename(archive_path)}"
                )
                
                # 圧縮後フォルダごと削除（優先）
                if hasattr(self.parent.parent, 'compression_delete_folder') and \
                   self.parent.parent.compression_delete_folder.get():
                    self._delete_folder_after_compression(folder_path)
                # ⭐修正: 圧縮後オリジナル削除（ログはsafe_delete_compressed_files内で出力済み）⭐
                elif hasattr(self.parent.parent, 'compression_delete_original') and \
                     self.parent.parent.compression_delete_original.get():
                    self.safe_delete_compressed_files(
                        folder_path, resize_enabled, keep_original
                    )
            
            elif format_type == "7Z":
                # 7Z圧縮（py7zrライブラリが必要）
                try:
                    import py7zr
                    archive_path = os.path.join(parent_dir, f"{base_name}.7z")
                    with py7zr.SevenZipFile(archive_path, 'w') as archive:
                        archive.writeall(folder_path, base_name)
                    self.session_manager.ui_bridge.post_log(
                        f"✅ 7Z圧縮完了: {os.path.basename(archive_path)}"
                    )
                except ImportError:
                    self.session_manager.ui_bridge.post_log(
                        "7Z圧縮にはpy7zrライブラリが必要です", "error"
                    )
                    return
            
            elif format_type == "TAR":
                # TAR圧縮
                import tarfile
                archive_path = os.path.join(parent_dir, f"{base_name}.tar.gz")
                with tarfile.open(archive_path, 'w:gz') as tar:
                    tar.add(folder_path, arcname=base_name)
                self.session_manager.ui_bridge.post_log(
                    f"✅ TAR圧縮完了: {os.path.basename(archive_path)}"
                )
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"圧縮処理エラー: {e}", "error"
            )
            raise
    
    def _delete_folder_after_compression(self, folder_path: str):
        """圧縮後にフォルダごと削除
        
        Args:
            folder_path: 削除対象フォルダパス
        """
        # サブディレクトリが存在するかチェック
        has_subdirs = False
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    has_subdirs = True
                    break
        except Exception:
            pass
        
        if not has_subdirs:
            try:
                import shutil
                shutil.rmtree(folder_path)
                self.session_manager.ui_bridge.post_log(
                    f"✅ 圧縮後にフォルダごと削除: {os.path.basename(folder_path)}"
                )
            except Exception as e:
                self.session_manager.ui_bridge.post_log(
                    f"フォルダ削除エラー: {e}", "error"
                )
        else:
            self.session_manager.ui_bridge.post_log(
                f"サブディレクトリが存在するため、フォルダ削除をスキップ: {os.path.basename(folder_path)}"
            )
    
    def safe_delete_compressed_files(self, folder_path: str, resize_enabled: bool, 
                                     keep_original: bool):
        """圧縮済みファイルを安全に削除（DLした画像のみ）
        
        Args:
            folder_path: フォルダパス
            resize_enabled: リサイズ機能が有効か
            keep_original: オリジナルを保持するか
        """
        try:
            deleted_count = 0
            skipped_count = 0
            
            # 保存フォルダ直下のファイルとフォルダを走査
            for root, dirs, files in os.walk(folder_path, topdown=False):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # リサイズ設定に応じた削除対象の判定
                    is_resized = "resized" in os.path.dirname(file_path)
                    
                    # 削除対象の判定（圧縮対象と同じロジック）
                    should_delete = False
                    if resize_enabled:
                        if keep_original:
                            # オリジナル保持ON: オリジナルのみ削除
                            should_delete = not is_resized
                        else:
                            # オリジナル保持OFF: リサイズファイルのみ削除
                            should_delete = is_resized
                    else:
                        # リサイズ無効: 画像ファイルのみ削除
                        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', 
                                          '.webp', '.tiff', '.tif']
                        file_ext = os.path.splitext(file)[1].lower()
                        should_delete = file_ext in image_extensions
                    
                    if should_delete:
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except Exception:
                            skipped_count += 1
                    else:
                        skipped_count += 1
                
                # 空のディレクトリを削除（resizedフォルダなど）
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        # ディレクトリが空の場合のみ削除
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                    except Exception:
                        pass
            
            # ⭐修正: 削除完了ログを追加⭐
            if deleted_count > 0:
                self.session_manager.ui_bridge.post_log(
                    f"圧縮済みファイルを削除: {folder_path} ({deleted_count}ファイル)"
                )
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"圧縮済みファイル削除エラー: {e}", "error"
            )
    
    def remove_incomplete_prefix(self, folder_path: str) -> str:
        """未完了フォルダの接頭辞を削除
        
        Args:
            folder_path: フォルダパス
            
        Returns:
            str: 変更後のフォルダパス（変更なしの場合は元のパス）
        """
        try:
            if not hasattr(self.parent.parent, 'incomplete_folder_prefix'):
                return folder_path
            
            prefix = self.parent.parent.incomplete_folder_prefix.get()
            if not prefix or not folder_path:
                return folder_path
            
            folder_name = os.path.basename(folder_path)
            if folder_name.startswith(prefix):
                new_folder_name = folder_name[len(prefix):]
                new_folder_path = os.path.join(
                    os.path.dirname(folder_path), new_folder_name
                )
                
                # フォルダ名を変更
                os.rename(folder_path, new_folder_path)
                self.session_manager.ui_bridge.post_log(
                    f"フォルダ名を変更: {folder_name} -> {new_folder_name}"
                )
                return new_folder_path
            
            return folder_path
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"フォルダ名変更エラー: {e}", "error"
            )
            return folder_path

    def rename_incomplete_folders_on_exit(self, incomplete_folders: set, 
                                         renamed_folders: set):
        """アプリ終了時に未完了フォルダに接頭辞を追加
        
        Args:
            incomplete_folders: 未完了フォルダのセット
            renamed_folders: リネーム済みフォルダのセット
        """
        try:
            if not hasattr(self.parent.parent, 'rename_incomplete_folder') or \
               not self.parent.parent.rename_incomplete_folder.get():
                return
            
            if not incomplete_folders:
                return
            
            prefix = self.parent.parent.incomplete_folder_prefix.get()
            if not prefix:
                return
            
            for folder_path in incomplete_folders:
                try:
                    # フォルダが存在するかチェック
                    if not os.path.exists(folder_path):
                        continue
                    
                    # 既にリネーム済みかチェック
                    if folder_path in renamed_folders:
                        continue
                    
                    # 既に接頭辞が付いているかチェック
                    folder_name = os.path.basename(folder_path)
                    if folder_name.startswith(prefix):
                        continue
                    
                    # 新しいフォルダ名を作成
                    new_folder_name = prefix + folder_name
                    new_folder_path = os.path.join(
                        os.path.dirname(folder_path), new_folder_name
                    )
                    
                    # 同名フォルダが存在する場合は連番を付ける
                    counter = 1
                    original_new_folder_path = new_folder_path
                    while os.path.exists(new_folder_path):
                        folder_name_with_counter = f"{prefix}{folder_name}({counter})"
                        new_folder_path = os.path.join(
                            os.path.dirname(folder_path), folder_name_with_counter
                        )
                        counter += 1
                    
                    # フォルダ名を変更
                    os.rename(folder_path, new_folder_path)
                    self.session_manager.ui_bridge.post_log(
                        f"未完了フォルダに接頭辞を追加: {folder_path} -> {new_folder_path}"
                    )
                    
                    # リネーム済みフォルダとして記録
                    renamed_folders.add(folder_path)
                    
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(
                        f"未完了フォルダリネームエラー: {folder_path} - {e}", "error"
                    )
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"未完了フォルダリネーム処理エラー: {e}", "error"
            )
    
    def _add_compression_complete_marker(self, url_key: str):
        """URLの右側に（圧縮完了）マーカーを追加（Treeview統合版）
        
        Args:
            url_key: URL識別キー
        """
        try:
            # ⭐フェーズ3: Treeviewのis_compressedフラグを更新⭐
            if hasattr(self.parent.parent, 'download_list_widget'):
                # URLキーで検索してTreeviewを更新
                if self.parent.parent._is_valid_eh_url(url_key):
                    # ⭐修正: mark_compressedメソッドを使用⭐
                    self.parent.parent.download_list_widget.mark_compressed(url_key)
                    self.session_manager.ui_bridge.post_log(
                        f"✅ Treeview圧縮完了マーカー追加: {url_key[:50]}...", "info"
                    )
            
            # ⭐既存のTextウィジェット処理も維持（並行動作）⭐
            import tkinter as tk
            if not hasattr(self.parent.parent, 'url_text'):
                return
            
            content = self.parent.parent.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            
            for i, line_text in enumerate(lines):
                line_stripped = line_text.strip()
                # マーカーや他のテキストを除いた純粋なURL部分で比較
                raw_url_part = line_stripped.split("（")[0].strip()
                
                # キーがURLの場合とフォルダパスの場合で比較対象を切り替え
                current_line_key = self.parent.parent.normalize_url(raw_url_part) \
                    if self.parent.parent._is_valid_eh_url(raw_url_part) \
                    else raw_url_part
                
                if current_line_key == url_key:
                    if "（圧縮完了）" not in line_text:  # マーカーがまだない場合
                        line_start_index = f"{i+1}.0"
                        # 元のテキスト（URL部分）の実際の終了位置を正確に把握
                        original_text_end_index = f"{i+1}.{len(raw_url_part)}"
                        
                        # マーカーを追加（ゼロ幅スペースを使用）
                        self.parent.parent.url_text.insert(
                            original_text_end_index, "\u200B（圧縮完了）"
                        )
                        
                        # マーカー部分のタグ付け
                        marker_text = "（圧縮完了）"
                        marker_start_display_index = f"{i+1}.{len(raw_url_part) + 1}"
                        marker_end_display_index = f"{i+1}.{len(raw_url_part) + 1 + len(marker_text)}"
                        
                        # マーカーに色を付ける
                        self.parent.parent.url_text.tag_add(
                            "compression_marker", 
                            marker_start_display_index, 
                            marker_end_display_index
                        )
                        self.parent.parent.url_text.tag_config(
                            "compression_marker", 
                            foreground="green", 
                            background="#E0F6FF",
                            selectforeground="green",
                            selectbackground="#E0F6FF",
                            font=("Arial", 9)
                        )
                        
                        break
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"圧縮完了マーカー追加エラー: {e}", "error"
            )
