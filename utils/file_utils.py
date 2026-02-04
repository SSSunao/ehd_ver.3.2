# -*- coding: utf-8 -*-
"""
File utilities for EH Downloader
"""


import tkinter as tk
import os
import shutil
import zipfile
import threading
import time
import requests
import json
from PIL import Image
from bs4 import BeautifulSoup
from config.settings import *
from config.constants import *
# DownloadStatus Enumをインポート
from gui.components.download_list_model import DownloadStatus
    def _to_enum_status(self, status):
        """status文字列またはEnumをDownloadStatus Enumに変換"""
        if isinstance(status, DownloadStatus):
            return status
        try:
            return DownloadStatus(status)
        except Exception:
            return None

class EHDownloaderFileUtils:
    def __init__(self, parent):
        self.parent = parent
    
    def log(self, message, level="info"):
        """ログ出力メソッド"""
        if hasattr(self.parent, 'log'):
            self.parent.log(message, level)
        else:
            print(f"[{level.upper()}] {message}")
    
    # 補完モードのマッピング
    INTERPOLATION_MAPPING = {
        "三次補完（画質優先）": Image.LANCZOS,
        "LANCZOS": Image.LANCZOS,
        "BILINEAR": Image.BILINEAR,
        "NEAREST": Image.NEAREST,
        "二次補完（速度優先）": Image.BILINEAR,
        "最近傍補完": Image.NEAREST
    }
        
    def _determine_image_filename(self, gallery_info, page_num, image_info):
        """画像ファイル名を決定"""
        save_name_mode = self.save_name.get()
        
        # 1ページ目の特別命名をチェック
        if page_num == 1 and self.first_page_naming_enabled.get():
            template = self.first_page_naming_format.get()
            if template == "title":
                # "title"の場合は実際のタイトルを使用
                base_name = gallery_info.get('title', 'Unknown')
            else:
                base_name = template
        else:
            # 通常の命名規則
            if save_name_mode == "Original":
                base_name = image_info['original_filename']
            elif save_name_mode == "simple_number":
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = f"{page_num - 1}{ext}"  # 0から開始
            elif save_name_mode == "padded_number":
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = f"{page_num - 1:03d}{ext}"  # 000から開始
            elif save_name_mode == "custom_name":
                template = self.custom_name.get()
                ext = os.path.splitext(image_info['original_filename'])[1]
                base_name = self._format_filename_template(
                    template, gallery_info, page_num, 
                    image_info['original_filename'], ext
                ) + ext
            else:
                base_name = image_info['original_filename']
        
        # ファイル名を安全にする
        safe_filename = re.sub(r'[\\/:*?"<>|]', '_', base_name)
        return safe_filename

    def _handle_duplicate_file(self, file_path, page_num):
        """同名ファイルの処理"""
        if not os.path.exists(file_path):
            return file_path
        
        mode = self.duplicate_file_mode.get()
        self.log(f"同名ファイル処理モード: {mode}")
        
        if mode == "skip":
            self.log(f"ページ {page_num}: 同名ファイルが存在するためスキップします: {os.path.basename(file_path)}")
            return None
        elif mode == "overwrite":
            # 圧縮時は連番で両方保持するように変更
            base, ext = os.path.splitext(file_path)
            counter = 1
            new_path = file_path
            
            while os.path.exists(new_path):
                new_path = f"{base}({counter}){ext}"
                counter += 1
            
            self.log(f"ページ {page_num}: 圧縮時のため連番で保存します: {os.path.basename(file_path)} → {os.path.basename(new_path)}")
            return new_path
        else:  # rename
            base, ext = os.path.splitext(file_path)
            counter = 1
            new_path = file_path
            
            while os.path.exists(new_path):
                new_path = f"{base}({counter}){ext}"
                counter += 1
            
            self.log(f"ページ {page_num}: ファイル名を変更します: {os.path.basename(file_path)} → {os.path.basename(new_path)}")
            return new_path

    def _download_single_image(self, image_url, file_path, page_num):
        """単一画像のダウンロード"""
        try:
            response = self.session.get(image_url)
            if not self.is_running:  # 中断チェック
                raise requests.exceptions.RequestException("ダウンロードが中断されました")
            response.raise_for_status()
            
            # 画像データを取得
            image_data = response.content
            self.log(f"画像データ取得完了: {len(image_data)} bytes")
            
            # 標準の保存処理を使用
            result = self._save_image_data(image_data, file_path, "Original", image_url)
            if result is True:  # スキップされた場合
                self.log(f"既存ファイルのためスキップ: {os.path.basename(file_path)}")
            elif result:  # 保存パスが返された場合
                self.log(f"画像保存完了: {os.path.basename(result)}")
                
                # ページ完了時のSelenium無効化処理
                self._deactivate_selenium_if_needed(page_completed=True)
                
            return result
            
        except Exception as e:
            # エラーを上位に伝播
            raise requests.exceptions.RequestException(f"ページ {page_num}: 画像のダウンロードに失敗しました。") from e


    def _process_image_resize(self, file_path, gallery_info, page_num, image_info):
        """画像リサイズ処理"""
        try:
            # リサイズが無効の場合は何もせずに終了（ログ出力なし）
            if self.resize_enabled.get() != "on" or self.resize_mode.get() == "none":
                return
            
            from PIL import Image
            
            # 元画像を開く
            with Image.open(file_path) as img:
                # アニメーション保持チェック
                if (self.preserve_animation.get() and 
                    img.format in ['GIF', 'WEBP'] and 
                    getattr(img, 'is_animated', False)):
                    self.log(f"ページ {page_num}: アニメーション画像のためリサイズをスキップ")
                    return
                
                try:
                    # リサイズ後の保存パスを決定
                    resized_file_path = self._get_resized_save_path(file_path)
                    
                    # ディレクトリ作成
                    os.makedirs(os.path.dirname(resized_file_path), exist_ok=True)
                    
                    # リサイズ実行（保存先パスを指定）
                    resize_mode = self.resize_mode.get()
                    resize_values = self.resize_values
                    
                    def resize_thread():
                        try:
                            resized = self.resize_image(file_path, resize_mode, resize_values, save_path=resized_file_path)
                            
                            if resized:
                                # オリジナルを保持しない場合は削除
                                if not self.keep_original.get():
                                    if os.path.exists(file_path):
                                        os.remove(file_path)
                                    else:
                                        self.log(f"警告: 削除対象の元ファイルが見つかりません: {file_path}", "warning")
                                
                                # リサイズ完了をチェック
                                if hasattr(self, 'current_gallery_url'):
                                    # 全ての画像のリサイズが完了したかチェック
                                    try:
                                        save_folder = os.path.dirname(os.path.dirname(resized_file_path))
                                        resized_folder = os.path.dirname(resized_file_path)
                                        
                                        # 元画像フォルダ内の画像ファイル数を取得
                                        original_files = [f for f in os.listdir(save_folder) 
                                                        if os.path.isfile(os.path.join(save_folder, f)) and 
                                                        f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
                                        
                                        # リサイズ済みフォルダ内の画像ファイル数を取得
                                        resized_files = [f for f in os.listdir(resized_folder) 
                                                       if os.path.isfile(os.path.join(resized_folder, f)) and 
                                                       f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]
                                        
                                        # 全ての画像がリサイズされた場合のみマーカーを追加
                                        if len(original_files) == len(resized_files) and len(resized_files) == gallery_info.get('total_pages', 0):
                                            self.root.after(0, lambda: self._add_resize_complete_marker(self.current_gallery_url))
                                    except Exception as e:
                                        self.log(f"リサイズ完了チェックエラー: {e}", "warning")
                            else:
                                # リサイズされなかった場合でも、keep_unresizedがONの場合はコピー
                                if self.keep_unresized.get():
                                    import shutil
                                    shutil.copy2(file_path, resized_file_path)
                                    self.log(f"ページ {page_num}: リサイズ不要のため、別フォルダにコピー")
                                    # オリジナルを保持しない場合は削除
                                    if not self.keep_original.get():
                                        if os.path.exists(file_path):
                                            os.remove(file_path)
                                        else:
                                            self.log(f"警告: 削除対象の元ファイルが見つかりません: {file_path}", "warning")
                        except Exception as e:
                            self.log(f"リサイズスレッドエラー: {e}", "error")
                    
                    # 新しいスレッドを作成して開始
                    thread = threading.Thread(target=resize_thread, daemon=True)
                    thread.start()
                        
                except FileNotFoundError as e:
                    self.log(f"リサイズエラー: {e}", "error")
                    raise  # 上位でハンドリングするためにエラーを伝播
                    
        except Exception as e:
            self.log(f"ページ {page_num} リサイズエラー: {e}", "error")
            raise  # 上位でハンドリングするためにエラーを伝播

    def _calculate_resize_dimensions(self, original_size):
        """リサイズ寸法を計算（安全策付き）"""
        try:
            width, height = original_size
            resize_mode = self.resize_mode.get()
            
            # リサイズ値の安全な取得
            target_size = self._get_safe_resize_value(resize_mode)
            if target_size is None:
                return None
            
            # 極端に大きな値に対する安全策
            MAX_SAFE_SIZE = 10000  # 最大安全サイズ
            MIN_SAFE_SIZE = 10     # 最小安全サイズ
            
            if target_size > MAX_SAFE_SIZE:
                self.log(f"リサイズ値が大きすぎます（{target_size}）。最大値{MAX_SAFE_SIZE}に制限します。", "warning")
                target_size = MAX_SAFE_SIZE
            elif target_size < MIN_SAFE_SIZE:
                self.log(f"リサイズ値が小さすぎます（{target_size}）。最小値{MIN_SAFE_SIZE}に制限します。", "warning")
                target_size = MIN_SAFE_SIZE
            
            if resize_mode == "縦幅上限":
                if height <= target_size:
                    return original_size
                scale = target_size / height
                new_width = int(width * scale)
                # 幅の安全チェック
                if new_width > MAX_SAFE_SIZE:
                    self.log(f"計算された幅が大きすぎます（{new_width}）。リサイズをスキップします。", "warning")
                    return original_size
                return (new_width, target_size)
                
            elif resize_mode == "横幅上限":
                if width <= target_size:
                    return original_size
                scale = target_size / width
                new_height = int(height * scale)
                # 高さの安全チェック
                if new_height > MAX_SAFE_SIZE:
                    self.log(f"計算された高さが大きすぎます（{new_height}）。リサイズをスキップします。", "warning")
                    return original_size
                return (target_size, new_height)
                
            elif resize_mode == "長辺上限":
                max_side = max(width, height)
                if max_side <= target_size:
                    return original_size
                scale = target_size / max_side
                new_width = int(width * scale)
                new_height = int(height * scale)
                # 両方のサイズをチェック
                if new_width > MAX_SAFE_SIZE or new_height > MAX_SAFE_SIZE:
                    self.log(f"計算されたサイズが大きすぎます（{new_width}x{new_height}）。リサイズをスキップします。", "warning")
                    return original_size
                return (new_width, new_height)
                
            elif resize_mode == "短辺下限":
                min_side = min(width, height)
                if min_side >= target_size:
                    return original_size
                scale = target_size / min_side
                new_width = int(width * scale)
                new_height = int(height * scale)
                # 両方のサイズをチェック
                if new_width > MAX_SAFE_SIZE or new_height > MAX_SAFE_SIZE:
                    self.log(f"計算されたサイズが大きすぎます（{new_width}x{new_height}）。リサイズをスキップします。", "warning")
                    return original_size
                return (new_width, new_height)
                
            elif resize_mode == "長辺下限":
                max_side = max(width, height)
                if max_side >= target_size:
                    return original_size
                scale = target_size / max_side
                new_width = int(width * scale)
                new_height = int(height * scale)
                # 両方のサイズをチェック
                if new_width > MAX_SAFE_SIZE or new_height > MAX_SAFE_SIZE:
                    self.log(f"計算されたサイズが大きすぎます（{new_width}x{new_height}）。リサイズをスキップします。", "warning")
                    return original_size
                return (new_width, new_height)
                
            elif resize_mode == "短辺上限":
                min_side = min(width, height)
                if min_side <= target_size:
                    return original_size
                scale = target_size / min_side
                new_width = int(width * scale)
                new_height = int(height * scale)
                # 両方のサイズをチェック
                if new_width > MAX_SAFE_SIZE or new_height > MAX_SAFE_SIZE:
                    self.log(f"計算されたサイズが大きすぎます（{new_width}x{new_height}）。リサイズをスキップします。", "warning")
                    return original_size
                return (new_width, new_height)
            
            return original_size
            
        except Exception as e:
            self.log(f"リサイズ寸法計算エラー: {e}", "error")
            return None
    
    def _get_safe_resize_value(self, resize_mode):
        """リサイズ値を安全に取得"""
        try:
            # モードに応じた値を取得
            if resize_mode == "縦幅上限":
                size_value = self.resize_values["height"].get()
            elif resize_mode == "横幅上限":
                size_value = self.resize_values["width"].get()
            elif resize_mode == "長辺上限":
                size_value = self.resize_values["long"].get()
            elif resize_mode == "短辺下限":
                size_value = self.resize_values["short"].get()
            elif resize_mode == "長辺下限":
                size_value = self.resize_values["long"].get()
            elif resize_mode == "短辺上限":
                size_value = self.resize_values["short"].get()
            elif resize_mode == "比率":
                size_value = self.resize_values["percentage"].get()
            else:
                size_value = self.resize_values["unified"].get()
            
            if not size_value:
                return None
            
            # 数値変換
            if resize_mode == "比率":
                try:
                    target_size = float(size_value)
                    # 比率の範囲チェック（0.1% ～ 1000%）
                    if target_size < 0.1 or target_size > 1000:
                        self.log(f"比率値が範囲外です（{target_size}%）。0.1%～1000%の範囲に制限します。", "warning")
                        target_size = max(0.1, min(1000, target_size))
                    return target_size
                except ValueError:
                    self.log(f"無効な比率値: {size_value}", "error")
                    return None
            else:
                try:
                    target_size = int(size_value)
                    return target_size
                except ValueError:
                    self.log(f"無効なサイズ値: {size_value}", "error")
                    return None
                    
        except Exception as e:
            self.log(f"リサイズ値取得エラー: {e}", "error")
            return None

    def _compress_folder(self, folder_path, gallery_info):
        """フォルダの圧縮処理"""
        try:
            if self.compression_enabled.get() != "on":
                return
            
            # フォルダ名から接頭辞を削除（圧縮前に実行）
            if self.rename_incomplete_folder.get():
                new_folder_path = self._remove_incomplete_prefix(folder_path)
                if new_folder_path and new_folder_path != folder_path:
                    folder_path = new_folder_path
            
            format_type = self.compression_format.get()
            base_name = os.path.basename(folder_path)
            parent_dir = os.path.dirname(folder_path)
            
            if format_type == "ZIP":
                archive_path = os.path.join(parent_dir, f"{base_name}.zip")
                
                # リサイズ設定に応じた圧縮対象の決定
                resize_enabled = hasattr(self, 'resize_enabled') and self.resize_enabled.get() == "on"
                keep_original = hasattr(self, 'keep_original') and self.keep_original.get()
                
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
                
                self.log(f"ZIP圧縮完了: {archive_path}")
                
                # オリジナルフォルダを削除（条件付き）
                if self.compression_delete_original.get():
                    for root, dirs, files in os.walk(folder_path, topdown=False):
                        for file in files:
                            file_path = os.path.join(root, file)
                            is_resized = "resized" in os.path.dirname(file_path)
                            
                            # 削除対象の判定
                            should_delete = False
                            if resize_enabled:
                                if keep_original:
                                    # オリジナル保持ON: オリジナルのみ削除
                                    should_delete = not is_resized
                                else:
                                    # オリジナル保持OFF: リサイズファイルのみ削除
                                    should_delete = is_resized
                            else:
                                # リサイズ無効: すべてのファイルを削除
                                should_delete = True
                            
                            if should_delete:
                                try:
                                    os.remove(file_path)
                                except Exception as e:
                                    self.log(f"ファイル削除エラー ({file_path}): {e}", "error")
                    
                    # 空のフォルダを削除
                    try:
                        if not os.listdir(folder_path):
                            shutil.rmtree(folder_path)
                            self.log(f"空のフォルダを削除: {folder_path}")
                    except Exception as e:
                        self.log(f"フォルダ削除エラー ({folder_path}): {e}", "error")
                    
            elif format_type in ["RAR", "7z"]:
                # 外部ツールが必要
                self.log(f"{format_type}圧縮は外部ツールが必要です", "warning")
                return
                
        except Exception as e:
            self.log(f"圧縮エラー: {e}", "error")

    def _format_filename_template(self, template, metadata, page_num=1, original_filename="", ext=""):
        """ファイル名テンプレートをフォーマット"""
        try:
            # DLリスト進行状況を含む変数辞書
            format_dict = {
                'title': str(metadata.get('title', '')),
                'page': int(page_num),
                'artist': str(metadata.get('artist', '')),
                'parody': str(metadata.get('parody', '')),
                'character': str(metadata.get('character', '')),
                'group': str(metadata.get('group', '')),
                'language': str(metadata.get('language', '')),
                'category': str(metadata.get('category', '')),
                'uploader': str(metadata.get('uploader', '')),
                'gid': str(metadata.get('gid', '')),
                'token': str(metadata.get('token', '')),
                'date': str(metadata.get('date', '')),
                'rating': str(metadata.get('rating', '')),
                'pages': str(metadata.get('pages', '')),
                'filesize': str(metadata.get('filesize', '')),
                'tags': str(metadata.get('tags', '')),
                'ext': str(ext),
                'original_filename': str(original_filename),
                'dl_index': int(getattr(self, 'dl_list_index', 1)),  # DLリスト進行番号（1ベース）
                'dl_count': int(getattr(self, 'dl_list_count', 1))   # DLリスト総数
            }
            
            formatted = template.format(**format_dict)
            
            # 無効な文字を置換
            invalid_chars = r'[\\/:*?"<>|]'
            formatted = re.sub(invalid_chars, '_', formatted)
            
            return formatted
            
        except Exception as e:
            self.log(f"ファイル名フォーマットエラー: {e}", "error")
            return f"file_{page_num}"

    def _check_and_rename_incomplete_folders(self):
        """安全な未完了フォルダのチェックとリネーム処理"""
        try:
            if not self.rename_incomplete_folder.get():
                return

            # 保存先フォルダのパスを取得
            root_folder = self.folder_var.get()
            if not root_folder or not os.path.exists(root_folder):
                return

            self.log("未完了フォルダのチェックを開始します", "info")
            
            # 管理対象フォルダのみを処理（安全性確保）
            prefix = self.incomplete_folder_prefix.get() or "[INCOMPLETE]_"
            processed_folders = 0
            
            for normalized_url, folder_path in self.managed_folders.items():
                # フォルダが存在するかチェック
                if not os.path.exists(folder_path):
                    self.log(f"管理対象フォルダが見つかりません: {folder_path}", "warning")
                    continue
                
                # URLの状態を取得
                url_status = self.url_status.get(normalized_url, "")
                folder_name = os.path.basename(folder_path)
                
                # フォルダ内のファイル数を確認
                try:
                    files = [f for f in os.listdir(folder_path) 
                            if os.path.isfile(os.path.join(folder_path, f))]
                    file_count = len(files)
                    
                    # 画像ファイルのみをカウント（より正確な判定）
                    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                    image_count = sum(1 for f in files 
                                    if os.path.splitext(f.lower())[1] in image_extensions)
                    
                except Exception as e:
                    self.log(f"フォルダ確認エラー ({folder_path}): {e}", "warning")
                    continue

                # 安全な状態判定（個別URL単位）
                should_have_prefix = self._should_folder_have_incomplete_prefix(
                    url_status, file_count, image_count, normalized_url
                )
                
                current_has_prefix = folder_name.startswith(prefix)
                
                # 状態に応じてリネーム処理
                if should_have_prefix and not current_has_prefix:
                    # 接頭辞を付与
                    self._add_incomplete_prefix_safe(folder_path, prefix, normalized_url)
                    processed_folders += 1
                elif not should_have_prefix and current_has_prefix:
                    # 接頭辞を削除
                    self._remove_incomplete_prefix_safe(folder_path, prefix, normalized_url)
                    processed_folders += 1
            
            if processed_folders > 0:
                self.log(f"未完了フォルダチェック完了: {processed_folders}個のフォルダを処理", "info")
            else:
                self.log("未完了フォルダチェック完了: 処理対象なし", "info")

        except Exception as e:
            self.log(f"未完了フォルダチェックエラー: {e}", "error")
    
    def _should_folder_have_incomplete_prefix(self, url_status, file_count, image_count, url):
        """フォルダが未完了接頭辞を持つべきかを判定"""
        # ダウンロード中は変更しない（フォルダ名変更を防ぐ）
        if url_status == "downloading":
            return False
        
        # 完了状態なら接頭辞は不要
        if url_status == "completed":
            return False
        
        # ファイルが存在しない空フォルダなら接頭辞は不要
        if file_count == 0:
            return False
        
        # スキップ済み、エラー状態、または未完了状態で画像ファイルがある場合は接頭辞が必要
        if url_status in ["skipped", "error", "paused", ""] and image_count > 0:
            return True
        
        return False
    
    def _add_incomplete_prefix_safe(self, folder_path, prefix, url):
        """安全な接頭辞付与"""
        try:
            folder_name = os.path.basename(folder_path)
            parent_dir = os.path.dirname(folder_path)
            
            # 新しいフォルダ名を生成
            new_folder_name = prefix + folder_name
            new_folder_path = os.path.join(parent_dir, new_folder_name)
            
            # 同名フォルダが存在する場合は連番
            counter = 1
            while os.path.exists(new_folder_path):
                new_folder_name = f"{prefix}{folder_name}({counter})"
                new_folder_path = os.path.join(parent_dir, new_folder_name)
                counter += 1
            
            # リネーム実行
            os.rename(folder_path, new_folder_path)
            
            # 管理対象フォルダの記録を更新
            self.managed_folders[url] = new_folder_path
            
            self.log(f"未完了接頭辞を付与: {folder_name} → {new_folder_name}")
            
        except Exception as e:
            self.log(f"接頭辞付与エラー ({folder_path}): {e}", "error")
    
    def _remove_incomplete_prefix_safe(self, folder_path, prefix, url):
        """安全な接頭辞削除"""
        try:
            folder_name = os.path.basename(folder_path)
            parent_dir = os.path.dirname(folder_path)
            
            # 接頭辞を削除した新しい名前
            if folder_name.startswith(prefix):
                new_folder_name = folder_name[len(prefix):]
                new_folder_path = os.path.join(parent_dir, new_folder_name)
                
                # 同名フォルダが存在する場合は連番
                counter = 1
                while os.path.exists(new_folder_path):
                    name_parts = os.path.splitext(new_folder_name)
                    if name_parts[1]:  # 拡張子がある場合
                        new_folder_name = f"{name_parts[0]}({counter}){name_parts[1]}"
                    else:
                        new_folder_name = f"{new_folder_name}({counter})"
                    new_folder_path = os.path.join(parent_dir, new_folder_name)
                    counter += 1
                
                # リネーム実行
                os.rename(folder_path, new_folder_path)
                
                # 管理対象フォルダの記録を更新
                self.managed_folders[url] = new_folder_path
                
                self.log(f"未完了接頭辞を削除: {folder_name} → {new_folder_name}")
                
        except Exception as e:
            self.log(f"接頭辞削除エラー ({folder_path}): {e}", "error")

    def _update_open_buttons_state(self):
        """ページを開く/フォルダを開くボタンの状態を更新（強化版）"""
        def update_buttons():
            try:
                # ページを開くボタン
                page_state = 'normal' if self.current_image_page_url else 'disabled'
                if hasattr(self, 'open_page_btn'):
                    self.open_page_btn.config(state=page_state)
                
                # フォルダを開くボタン - より確実な判定
                folder_state = 'disabled'
                
                # 1. 現在のダウンロードフォルダを最優先でチェック
                if self.current_save_folder and os.path.exists(self.current_save_folder):
                    folder_state = 'normal'
                # 2. managed_foldersから現在のURLのフォルダを取得
                elif hasattr(self, 'managed_folders') and self.current_gallery_url:
                    managed_folder = self.managed_folders.get(self.current_gallery_url, "")
                    if managed_folder and os.path.exists(managed_folder):
                        folder_state = 'normal'
                        # current_save_folderを更新
                        self.current_save_folder = managed_folder
                # 3. 設定されたフォルダパスをチェック
                elif self.folder_var.get() and os.path.exists(self.folder_var.get()):
                    folder_state = 'normal'
                    
                if hasattr(self, 'open_folder_btn'):
                    self.open_folder_btn.config(state=folder_state)
                    
            except Exception as e:
                self.log(f"ボタン状態更新エラー: {e}", "error")
        
        # GUI スレッドで確実に実行
        if self.root:
            self.root.after(0, update_buttons)

    def update_progress_title(self, url, title):
        """プログレスタイトルを更新（スレッドセーフ）"""
        if not title:  # タイトルが無効な場合は更新しない
            return
            
        self.current_gallery_title = title  # タイトルを保存
        
        def update_title():
            try:
                with self.progress_update_lock:
                    # プログレスバーが存在しない場合は新規作成
                    if not self.progress_bars or not self.current_progress_bar:
                        self.show_current_progress_bar()
                    
                    # 全てのプログレスバーのタイトルを更新
                    for progress_info in self.progress_bars:
                        try:
                            if progress_info['title'] and progress_info['title'].winfo_exists():
                                progress_info['title'].config(text=f"タイトル: {title}")
                                
                                # フレームのタイトルは更新しない
                                if progress_info['frame'] and progress_info['frame'].winfo_exists():
                                    progress_info['frame'].config(text="現在のダウンロード進捗")
                        except tk.TclError:
                            pass
            except Exception as e:
                self.log(f"プログレスタイトル更新エラー: {e}", "error")
        
        # GUIスレッドで安全に実行
        if self.root:
            self.root.after(0, update_title)

    @property
    def resize_mode_map(self):
        """リサイズモードのマッピング"""
        return {
            "Original": "Original",
            "縦幅上限": "height",
            "横幅上限": "width", 
            "長辺上限": "max_side",
            "短辺下限": "min_side"
        }

    @property
    def resize_value_entries(self):
        """リサイズ値エントリのマッピング"""
        entries = {}
        if hasattr(self, 'resize_size_entry'):
            entries["unified"] = self.resize_size_entry
        return entries


    def _update_download_status(self, url, status):
        """ダウンロード状態更新"""
        try:
            self.url_status[url] = status
            
            # URLテキストの色分け更新
            self._update_url_text_colors()
            
        except Exception as e:
            self.log(f"状態更新エラー: {e}", "error")

    def _update_all_url_backgrounds(self):
        """全てのURLの背景色を一括で更新"""
        try:
            content = self.url_text.get("1.0", tk.END)
            urls = self._parse_urls_from_text(content)
            for url in urls:
                self.update_url_background(url)
        except Exception as e:
            self.log(f"全URL背景色更新エラー: {e}", "warning")

    def _update_url_text_colors(self):
        """URLテキストの色分け更新"""
        try:
            if not hasattr(self, 'url_text'):
                return
            
            # すべてのタグをクリア
            for tag in ['completed', 'error', 'current', 'pending', 'incomplete']:
                self.url_text.tag_delete(tag)
                
                # 背景色のみ定義（文字色は黒のまま）
                self.url_text.tag_config('completed', background='#E0F6FF')  # 薄い青色
                self.url_text.tag_config('error', background='#FFE4E1')      # 薄い赤色
                self.url_text.tag_config('current', background='#FFFACD')    # 薄い黄色
                self.url_text.tag_config('pending', background='white')      # 白
                self.url_text.tag_config('incomplete', background='#D3D3D3')  # グレー（未完了）
                
                # URLリストを取得
                content = self.url_text.get("1.0", tk.END)
                urls = self._parse_urls_from_text(content)
                
                # 各URLの状態に応じて色付け
                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    line = line.strip()
                    if line and self._is_valid_eh_url(line.strip()):
                        normalized_url = self._normalize_gallery_url(line.strip())
                        
                        # 未完了フラグをチェック
                        is_incomplete = normalized_url in getattr(self, 'incomplete_urls', set())
                        
                        if normalized_url in self.url_status:
                            status = self.url_status[normalized_url]
                            if is_incomplete:
                                tag = 'incomplete'  # 未完了の場合は灰色
                            elif status == 'completed':
                                tag = 'completed'
                            elif status in ['error', 'paused']:
                                tag = 'error'
                            elif status == 'downloading':
                                tag = 'current'
                            else:
                                tag = 'pending'
                        elif normalized_url == self.current_gallery_url:
                            tag = 'current'
                        else:
                            tag = 'pending'
                        
                        start_pos = f"{line_num}.0"
                        end_pos = f"{line_num}.end"
                        self.url_text.tag_add(tag, start_pos, end_pos)
                    
        except Exception as e:
            self.log(f"URL色分け更新エラー: {e}", "error")

    def _set_url_incomplete_style(self, url):
        """指定URLを未完了スタイル（グレー）に設定"""
        try:
            self._update_url_text_colors()
        except Exception as e:
            self.log(f"未完了スタイル設定エラー: {e}", "error")

    def _save_progress_state(self):
        """進行状況を保存（エラー情報は除外）"""
        try:
            progress_data = {
                'current_url_index': self.current_url_index,
                'current_gallery_url': self.current_gallery_url,
                'current_progress': self.current_progress,
                'current_total': self.current_total,
                'url_status': self.url_status,
                'total_elapsed_seconds': self.total_elapsed_seconds
            }
            
            progress_file = os.path.splitext(self._get_settings_path())[0] + "_progress.json"
            
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.log(f"進行状況保存エラー: {e}", "error")

    def _load_progress_state(self):
        """進行状況を読み込み（エラー情報は除外）"""
        try:
            progress_file = os.path.splitext(self._get_settings_path())[0] + "_progress.json"
            
            if not os.path.exists(progress_file):
                return False
                
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            
            self.current_url_index = progress_data.get('current_url_index', 0)
            self.current_gallery_url = progress_data.get('current_gallery_url', '')
            self.current_progress = progress_data.get('current_progress', 0)
            self.current_total = progress_data.get('current_total', 0)
            self.url_status = progress_data.get('url_status', {})
            self.total_elapsed_seconds = progress_data.get('total_elapsed_seconds', 0.0)
            
            return True
            
        except Exception as e:
            self.log(f"進行状況読み込みエラー: {e}", "error")
            return False

    def _clear_progress_state(self):
        """進行状況をクリア"""
        try:
            progress_file = os.path.splitext(self._get_settings_path())[0] + "_progress.json"
            
            if os.path.exists(progress_file):
                os.remove(progress_file)
                
        except Exception as e:
            self.log(f"進行状況クリアエラー: {e}", "error")

    def _export_download_log(self):
        """ダウンロードログをエクスポート"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"download_log_{timestamp}.txt"
            
            log_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfilename=log_filename
            )
            
            if log_path:
                log_content = self.log_text.get("1.0", tk.END)
                
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f"E-Hentai ダウンローダー ログエクスポート\n")
                    f.write(f"エクスポート日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(log_content)
                
                self.log(f"ログをエクスポート: {log_path}")
                messagebox.showinfo("エクスポート完了", f"ログを保存しました:\n{log_path}")
                
        except Exception as e:
            self.log(f"ログエクスポートエラー: {e}", "error")
            messagebox.showerror("エラー", f"ログのエクスポートに失敗しました:\n{e}")

    def _validate_settings(self):
        """設定値を検証"""
        try:
            errors = []
            
            # 待機時間の検証
            try:
                wait_time = float(self.wait_time.get())
                if wait_time < 0:
                    errors.append("待機時間(Wait)は0以上を指定してください")
            except ValueError:
                errors.append("待機時間(Wait)は数値を入力してください")
            
            try:
                sleep_time = float(self.sleep_value.get())
                if sleep_time < 0:
                    errors.append("待機時間(Sleep)は0以上を指定してください")
            except ValueError:
                errors.append("待機時間(Sleep)は数値を入力してください")
            
            # リサイズ設定の検証
            if self.resize_enabled.get() == "on":
                resize_value = self.resize_values["unified"].get()
                if resize_value:
                    try:
                        size = int(resize_value)
                        if size <= 0:
                            errors.append("リサイズサイズは1以上を指定してください")
                    except ValueError:
                        errors.append("リサイズサイズは整数を入力してください")
            
            # 自動再開設定の検証
            if self.error_handling_mode.get() == "auto_retry":
                try:
                    delay = int(self.auto_resume_delay.get())
                    if delay < 0:
                        errors.append("自動再開遅延は0以上を指定してください")
                except ValueError:
                    errors.append("自動再開遅延は整数を入力してください")
            
            if errors:
                error_message = "設定エラー:\n" + "\n".join(f"• {error}" for error in errors)
                messagebox.showerror("設定エラー", error_message)
                return False
                
            return True
            
        except Exception as e:
            self.log(f"設定検証エラー: {e}", "error")
            return False

    def _get_system_info(self):
        """システム情報を取得"""
        try:
            import platform
            import sys
            
            info = {
                'platform': platform.platform(),
                'python_version': sys.version,
                'tkinter_version': tk.Tcl().eval('info patchlevel'),
                'requests_version': getattr(requests, '__version__', 'Unknown'),
                'pil_version': getattr(Image, '__version__', 'Unknown') if 'Image' in globals() else 'Not installed'
            }
            
            return info
            
        except Exception as e:
            self.log(f"システム情報取得エラー: {e}", "error")
            return {}

    def _show_about_dialog(self):
        """アバウトダイアログを表示"""
        try:
            if PYQT5_AVAILABLE:
                # PyQt5を使用したカスタムダイアログ（リンククリック機能付き）
                class AboutDialog(QDialog):
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setWindowTitle("E-Hentai ダウンローダーについて")
                        self.setModal(True)
                        self.setFixedSize(500, 400)
                        
                        # レイアウト設定
                        layout = QVBoxLayout()
                        
                        # タイトル
                        from app_info import APP_NAME, VERSION_STRING
                        title_label = QLabel(f"<h3>{APP_NAME} {VERSION_STRING}</h3>")
                        title_label.setAlignment(Qt.AlignCenter)
                        layout.addWidget(title_label)
                        
                        # 説明文
                        desc_label = QLabel("""<p>E-hentai.orgの高機能画像ダウンローダーです。<br>
常識の範囲内でお使いください。<br>
過度なアクセスを行うとIP禁止になる恐れがあるのでご注意ください。</p>""")
                        desc_label.setWordWrap(True)
                        layout.addWidget(desc_label)
                        
                        # 制作者情報
                        creator_label = QLabel("""<p>AIに下駄履かせてもらって色々作ります。<br>
制作：ひびかん🐸 (hibikan_frog)</p>""")
                        creator_label.setWordWrap(True)
                        layout.addWidget(creator_label)
                        
                        # Noteリンク
                        note_layout = QHBoxLayout()
                        note_label = QLabel("Note:")
                        note_link = QLabel('<a href="https://note.com/hibikan_frog">https://note.com/hibikan_frog</a>')
                        note_link.setOpenExternalLinks(True)
                        note_link.linkActivated.connect(self._open_link)
                        note_layout.addWidget(note_label)
                        note_layout.addWidget(note_link)
                        note_layout.addStretch()
                        layout.addLayout(note_layout)
                        
                        # コーヒー情報
                        coffee_label = QLabel("""<p>業スー愛好家。<br>
コーヒー代をいただけると元気が出ます☕</p>""")
                        coffee_label.setWordWrap(True)
                        layout.addWidget(coffee_label)
                        
                        # Buy Me a Coffeeリンク
                        coffee_layout = QHBoxLayout()
                        coffee_text_label = QLabel("Buy Me a Coffee:")
                        coffee_link = QLabel('<a href="https://buymeacoffee.com/hibikan_frog">https://buymeacoffee.com/hibikan_frog</a>')
                        coffee_link.setOpenExternalLinks(True)
                        coffee_link.linkActivated.connect(self._open_link)
                        coffee_layout.addWidget(coffee_text_label)
                        coffee_layout.addWidget(coffee_link)
                        coffee_layout.addStretch()
                        layout.addLayout(coffee_layout)
                        
                        # 著作権
                        copyright_label = QLabel("<p>© 2025 E-Hentai Downloader Project</p>")
                        copyright_label.setAlignment(Qt.AlignCenter)
                        layout.addWidget(copyright_label)
                        
                        # スペーサー
                        layout.addStretch()
                        
                        # OKボタン
                        button_layout = QHBoxLayout()
                        button_layout.addStretch()
                        ok_button = QPushButton("OK")
                        ok_button.clicked.connect(self.accept)
                        button_layout.addWidget(ok_button)
                        button_layout.addStretch()
                        layout.addLayout(button_layout)
                        
                        self.setLayout(layout)
                    
                    def _open_link(self, url):
                        """リンクを開く（確認ダイアログ付き）"""
                        try:
                            confirm_box = QMessageBox()
                            confirm_box.setWindowTitle("外部リンクの確認")
                            confirm_box.setText(f"以下のURLを外部ブラウザで開きますか？\n\n{url}")
                            confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                            confirm_box.setDefaultButton(QMessageBox.No)
                            
                            if confirm_box.exec_() == QMessageBox.Yes:
                                QDesktopServices.openUrl(QUrl(url))
                        except Exception as e:
                            # 確認ダイアログでエラーが発生した場合は直接開く
                            try:
                                QDesktopServices.openUrl(QUrl(url))
                            except Exception:
                                pass
                
                # QApplicationインスタンスを作成（存在しない場合）
                app = QApplication.instance()
                if app is None:
                    app = QApplication([])
                
                # カスタムダイアログを表示
                dialog = AboutDialog()
                dialog.exec_()
                
            else:
                # PyQt5が利用できない場合は通常のmessageboxを使用
                about_text = f"""E-Hentai Downloader Ver3.12

E-hentai.orgの高機能画像ダウンローダーです。
常識の範囲内でお使いください。
過度なアクセスを行うとIP禁止になる恐れがあるのでご注意ください。

AIに下駄履かせてもらって色々作ります。
制作：ひびかん🐸 (hibikan_frog) https://note.com/hibikan_frog

業スー愛好家。
コーヒー代をいただけると元気が出ます☕ https://buymeacoffee.com/hibikan_frog

© 2025 E-Hentai Downloader Project"""
                
                messagebox.showinfo("E-Hentai ダウンローダーについて", about_text)
            
        except Exception as e:
            self.log(f"アバウトダイアログエラー: {e}", "error")
            # エラーが発生した場合はフォールバック
            try:
                about_text = f"""E-Hentai Downloader Ver3.12

E-hentai.orgの高機能画像ダウンローダーです。
常識の範囲内でお使いください。
過度なアクセスを行うとIP禁止になる恐れがあるのでご注意ください。

AIに下駄履かせてもらって色々作ります。
制作：ひびかん🐸 (hibikan_frog) https://note.com/hibikan_frog

業スー愛好家。
コーヒー代をいただけると元気が出ます☕ https://buymeacoffee.com/hibikan_frog

© 2025 E-Hentai Downloader Project"""
                
                messagebox.showinfo("E-Hentai ダウンローダーについて", about_text)
            except Exception as fallback_error:
                self.log(f"フォールバックダイアログエラー: {fallback_error}", "error")

    def _create_backup(self):
        """設定とログのバックアップを作成"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f"backup_{timestamp}"
            
            backup_path = filedialog.askdirectory(title="バックアップ保存先を選択")
            if not backup_path:
                return

            full_backup_path = os.path.join(backup_path, backup_dir)
            try:
                os.makedirs(full_backup_path, exist_ok=True)
            except OSError as e:
                raise FileOperationError(f"バックアップフォルダの作成に失敗: {e}", "create", full_backup_path)
            
            # 設定ファイルをバックアップ
            settings_path = self._get_settings_path()
            if os.path.exists(settings_path):
                try:
                    shutil.copy2(settings_path, os.path.join(full_backup_path, "settings.json"))
                except OSError as e:
                    raise FileOperationError(f"設定ファイルのコピーに失敗: {e}", "copy", settings_path)
            
            # 現在のログをバックアップ
            log_content = self.log_text.get("1.0", tk.END)
            log_file_path = os.path.join(full_backup_path, "current_log.txt")
            try:
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
            except OSError as e:
                raise FileOperationError(f"ログファイルの保存に失敗: {e}", "write", log_file_path)
            
            # DLリストの全URLをバックアップ
            url_content = self.url_text.get("1.0", tk.END).strip()
            if url_content:
                url_list_path = os.path.join(full_backup_path, "url_list.txt")
                try:
                    with open(url_list_path, 'w', encoding='utf-8') as f:
                        f.write(url_content)
                except OSError as e:
                    raise FileOperationError(f"URLリストの保存に失敗: {e}", "write", url_list_path)
            
            # 未完了URLのみをバックアップ
            incomplete_urls = []
            if url_content:
                urls = self._parse_urls_from_text(url_content)
                for url in urls:
                    status = self._to_enum_status(self.url_status.get(url, ""))
                    if status not in [DownloadStatus.COMPLETED, DownloadStatus.SKIPPED]:
                        incomplete_urls.append(url)
            
            if incomplete_urls:
                incomplete_urls_path = os.path.join(full_backup_path, "incomplete_urls.txt")
                try:
                    with open(incomplete_urls_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(incomplete_urls))
                except OSError as e:
                    raise FileOperationError(f"未完了URLリストの保存に失敗: {e}", "write", incomplete_urls_path)
            
            self.log(f"バックアップ作成完了: {full_backup_path}")
            messagebox.showinfo("バックアップ完了", f"バックアップを作成しました:\n{full_backup_path}")
            
        except FileOperationError as e:
            self.log(f"バックアップ作成エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの作成に失敗しました:\n{e}")
        except Exception as e:
            self.log(f"予期しないバックアップエラー: {e}", "error")
            messagebox.showerror("エラー", f"予期しないエラーが発生しました:\n{e}")

    def _restore_from_backup(self):
        """バックアップから復元"""
        try:
            backup_path = filedialog.askdirectory(title="バックアップフォルダを選択")
            if not backup_path:
                return

            settings_backup = os.path.join(backup_path, "settings.json")
            url_list_backup = os.path.join(backup_path, "url_list.txt")
            current_log_backup = os.path.join(backup_path, "current_log.txt")
            
            restored_files = []
            
            # 設定ファイルを復元
            if os.path.exists(settings_backup):
                try:
                    # 設定ファイルを直接読み込んでGUIに反映
                    self._load_settings_from_file(settings_backup)
                    restored_files.append("設定ファイル")
                except Exception as e:
                    self.log(f"設定ファイルの復元に失敗: {e}", "warning")
            
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
                    
                    self.url_text.delete("1.0", tk.END)
                    if urls:
                        self.url_text.insert("1.0", "\n".join(urls) + "\n")
                    
                    restored_files.append("URLリスト")
                except Exception as e:
                    self.log(f"URLリストの復元に失敗: {e}", "warning")
            
            # ログファイルを復元
            if os.path.exists(current_log_backup):
                try:
                    with open(current_log_backup, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    self.log_text.delete("1.0", tk.END)
                    self.log_text.insert("1.0", log_content)
                    restored_files.append("ログファイル")
                except Exception as e:
                    self.log(f"ログファイルの復元に失敗: {e}", "warning")
            
            if restored_files:
                self.log(f"バックアップから復元: {', '.join(restored_files)}")
                messagebox.showinfo("復元完了", f"以下のファイルを復元しました:\n{chr(10).join(restored_files)}")
            else:
                messagebox.showwarning("復元失敗", "バックアップファイルが見つかりませんでした。")
            
        except Exception as e:
            self.log(f"バックアップ復元エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの復元に失敗しました:\n{e}")

    def _backup_incomplete_urls(self):
        """未完了URLのバックアップを作成"""
        try:
            # 未完了URLを収集
            incomplete_urls = []
            content = self.url_text.get("1.0", tk.END)
            urls = self._parse_urls_from_text(content)
            for url in urls:
                status = self._to_enum_status(self.url_status.get(url, ""))
                if status not in [DownloadStatus.COMPLETED, DownloadStatus.SKIPPED]:
                    incomplete_urls.append(url)
            
            if not incomplete_urls:
                messagebox.showinfo("情報", "未完了のURLはありません。")
                return
            
            # 保存先を選択
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"incomplete_urls_{timestamp}.txt"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("テキストファイル", "*.txt")],
                initialfile=default_filename
            )
            
            if not file_path:
                return
                
            # ファイルに保存
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(incomplete_urls))
            except OSError as e:
                raise FileOperationError(f"未完了URLの保存に失敗: {e}", "write", file_path)
            
            self.log(f"未完了URLをバックアップしました: {file_path}")
            messagebox.showinfo("完了", f"未完了URLを保存しました:\n{file_path}")
            
        except FileOperationError as e:
            self.log(f"未完了URLのバックアップ作成エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの作成に失敗しました:\n{e}")
        except Exception as e:
            self.log(f"予期しない未完了URLバックアップエラー: {e}", "error")
            messagebox.showerror("エラー", f"予期しないエラーが発生しました:\n{e}")

    def _create_menu_bar(self):
        """メニューバーを作成"""
        try:
            menubar = tk.Menu(self.root)
            self.root.config(menu=menubar)
            
            # ファイルメニュー
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="ファイル", menu=file_menu)
            file_menu.add_command(label="バックアップ作成", command=self._create_backup)
            file_menu.add_command(label="バックアップから復元", command=self._restore_from_backup)
            file_menu.add_separator()
            file_menu.add_command(label="未完了URLのみバックアップ", command=self._backup_incomplete_urls)
            file_menu.add_separator()
            file_menu.add_command(label="終了", command=self.on_closing)
            
            # ヘルプメニュー
            help_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label="ヘルプ", menu=help_menu)
            help_menu.add_command(label="システム情報", command=lambda: messagebox.showinfo("システム情報", "\n".join([f"{k}: {v}" for k, v in self._get_system_info().items()])))
            help_menu.add_command(label="アバウト", command=self._show_about_dialog)
            
            # デバッグメニューは非表示
            if False:  # デバッグメニューを無効化
                debug_menu = tk.Menu(menubar, tearoff=0)
                menubar.add_cascade(label="デバッグ", menu=debug_menu)
                debug_menu.add_command(label="ネットワークエラーを発生", command=self._trigger_network_error)
                debug_menu.add_command(label="フォルダ削除エラーを発生", command=self._trigger_folder_error)
                debug_menu.add_command(label="画像ダウンロードエラーを発生", command=self._trigger_download_error)
                debug_menu.add_command(label="デッドロックテスト", command=self._trigger_deadlock_test)
                debug_menu.add_separator()
                debug_menu.add_command(label="エラー状態を表示", command=self._show_error_state)
                debug_menu.add_command(label="再開ポイントを表示", command=self._show_resume_point)
            
        except Exception as e:
            self.log(f"メニューバー作成エラー: {e}", "error")
    
    def _trigger_network_error(self):
        """ネットワークエラーを意図的に発生"""
        if self.is_running:
            self.log("デバッグ: ネットワークエラーを発生させます", "warning")
            error = requests.exceptions.ConnectionError("Debug: Simulated network error")
            self.root.after(0, lambda: self._handle_download_error(self.current_gallery_url, error))
        else:
            self.log("ダウンロード中でないため、エラーを発生できません", "warning")
    
    def _trigger_folder_error(self):
        """フォルダ削除エラーを意図的に発生"""
        if self.is_running and hasattr(self, 'current_save_folder'):
            self.log("デバッグ: フォルダ削除エラーを発生させます", "warning")
            error = FolderMissingException("Debug: Simulated folder deletion", self.current_save_folder, self.current_gallery_url)
            self.root.after(0, lambda: self._handle_download_error(self.current_gallery_url, error))
        else:
            self.log("ダウンロード中でないため、エラーを発生できません", "warning")
    
    def _trigger_download_error(self):
        """画像ダウンロードエラーを意図的に発生"""
        if self.is_running:
            self.log("デバッグ: 画像ダウンロードエラーを発生させます", "warning")
            error = DownloadErrorException("Debug: Simulated image download error", self.current_gallery_url, getattr(self, 'current_page', 0), getattr(self, 'total_pages', 0), getattr(self, 'current_save_folder', ''))
            self.root.after(0, lambda: self._handle_download_error(self.current_gallery_url, error))
        else:
            # テスト用に、ダウンロード中でなくてもエラー処理を呼び出す
            self.log("デバッグ: テスト用エラーを発生させます（ダウンロード中でない場合）", "warning")
            test_url = "https://e-hentai.org/g/test/test"
            error = DownloadErrorException("Debug: Test error (not downloading)", test_url, 1, 10, "test_folder")
            self.root.after(0, lambda: self._handle_download_error(test_url, error))
    
    def _trigger_deadlock_test(self):
        """デッドロックテストを実行"""
        if self.is_running:
            self.log("デバッグ: デッドロックテストを開始します", "warning")
            
            def deadlock_test():
                try:
                    # 複数のスレッドからロックを取得してみる
                    import threading
                    import time
                    
                    def thread1():
                        with self.lock:
                            self.log("Thread1: ロック取得", "debug")
                            time.sleep(0.1)
                            # GUI操作を試行
                            self.root.after(0, lambda: self._update_gui_for_error())
                    
                    def thread2():
                        time.sleep(0.05)
                        with self.lock:
                            self.log("Thread2: ロック取得", "debug")
                            self.paused = not self.paused
                    
                    t1 = threading.Thread(target=thread1)
                    t2 = threading.Thread(target=thread2)
                    
                    t1.start()
                    t2.start()
                    
                    t1.join(timeout=2)
                    t2.join(timeout=2)
                    
                    if t1.is_alive() or t2.is_alive():
                        self.log("デッドロックが検出されました！", "error")
                    else:
                        self.log("デッドロックテスト完了", "info")
                        
                except Exception as e:
                    self.log(f"デッドロックテストエラー: {e}", "error")
            
            threading.Thread(target=deadlock_test, daemon=True).start()
        else:
            self.log("ダウンロード中でないため、デッドロックテストを実行できません", "warning")
    
    def _show_error_state(self):
        """現在のエラー状態を表示"""
        import tkinter.messagebox as msgbox
        
        error_text = f"""エラー状態情報:
        
has_error: {self.error_info['has_error']}
url: {self.error_info['url']}
page: {self.error_info['page']}
type: {self.error_info['type']}
message: {self.error_info['message']}
save_folder: {self.error_info['save_folder']}
gallery_url: {self.error_info['gallery_url']}
image_page_url: {self.error_info['image_page_url']}
total_pages: {self.error_info['total_pages']}
timestamp: {self.error_info['timestamp']}

実行状態:
is_running: {self.is_running}
paused: {self.paused}
stop_flag: {self.stop_flag.is_set()}"""
        
        msgbox.showinfo("エラー状態", error_text)
    
    def _show_resume_point(self):
        """再開ポイント情報を表示"""
        import tkinter.messagebox as msgbox
        
        resume_text = f"""再開ポイント情報:
        
url: {self.resume_point.get('url', '')}
page: {self.resume_point.get('page', 0)}
folder: {self.resume_point.get('folder', '')}
current_url_index: {self.resume_point.get('current_url_index', 0)}
timestamp: {self.resume_point.get('timestamp', 0)}

ギャラリーメタデータ:
title: {self.resume_point.get('gallery_metadata', {}).get('title', '')}
artist: {self.resume_point.get('gallery_metadata', {}).get('artist', '')}
total_pages: {self.resume_point.get('gallery_metadata', {}).get('total_pages', 0)}"""
        
        msgbox.showinfo("再開ポイント", resume_text)


    def _find_main_image_url(self, soup):
        """メイン画像URLを検索"""
        try:
            # 画像要素を検索（優先順位順）
            
            # 1. id="img"の画像を探す
            img_elem = soup.find('img', {'id': 'img'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 2. class="main_image"の画像を探す
            img_elem = soup.find('img', {'class': 'main_image'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 3. id="image"の画像を探す
            img_elem = soup.find('img', {'id': 'image'})
            if img_elem and img_elem.get('src'):
                return img_elem['src']
            
            # 4. 画像を含むdivを探す
            div_elem = soup.find('div', {'id': 'i3'})
            if div_elem:
                img_elem = div_elem.find('img')
                if img_elem and img_elem.get('src'):
                    return img_elem['src']
            
            # 5. すべての画像から適切なものを探す
            img_elems = soup.find_all('img')
            for img in img_elems:
                src = img.get('src', '')
                if any(domain in src.lower() for domain in ['ehgt.org', 'exhentai.org', 'e-hentai.org']):
                    if any(ext in src.lower() for ext in ['.jpg', '.png', '.gif', '.jpeg', '.webp']):
                        return src
            
            # 6. nl要素内の画像を探す
            nl_elem = soup.find('a', {'id': 'loadfail'})
            if nl_elem and nl_elem.get('href'):
                return nl_elem['href']
            
            self.log("画像URLが見つかりませんでした", "warning")
            return None
            
        except Exception as e:
            self.log(f"画像URL検索エラー: {e}", "error")
            return None

    def get_save_path(self, save_folder, page, image_url, save_name_option, custom_name_format, manga_title, artist, parody, character, group, save_format_option):
        """保存パス決定（１ページ目命名修正版）"""
        try:
            # 拡張子決定
            if save_format_option == "Original":
                ext = os.path.splitext(image_url)[1] or ".jpg"
            else:
                ext = f".{save_format_option.lower()}"
            
            # １ページ目の特別命名処理
            if page == 1 and self.first_page_naming_enabled.get():
                first_page_format = self.first_page_naming_format.get().strip()
                
                if first_page_format:
                    # {}で囲まれた部分のみを変数として扱う
                    if '{' in first_page_format and '}' in first_page_format:
                        # テンプレート変数として処理
                        filename = self._format_filename_template(
                            first_page_format,
                            {
                                'title': manga_title,
                                'artist': artist,
                                'parody': parody,
                                'character': character,
                                'group': group,
                                'page': page
                            },
                            page,
                            os.path.basename(image_url),
                            ext.lstrip('.')
                        )
                    else:
                        # {}がない場合は文字列をそのまま使用
                        filename = first_page_format
                    
                    # 無効文字のサニタイズ
                    filename = self.sanitize_filename(filename)
                    return os.path.join(save_folder, filename + ext)
            
            # 通常の命名処理
            if save_name_option == "Original":
                filename = os.path.splitext(os.path.basename(image_url))[0]
            elif save_name_option == "simple_number":
                # 1から始まる連番: 1, 2, 3...
                filename = str(page)  # 1ベースのまま使用
            elif save_name_option == "padded_number":
                # 001から始まる連番: 001, 002, 003...
                filename = f"{page:03d}"  # 1ベースのまま使用
            elif save_name_option == "custom_name" and custom_name_format:
                # カスタム命名でも{}の有無をチェック
                if '{' in custom_name_format and '}' in custom_name_format:
                    filename = self._format_filename_template(
                        custom_name_format,
                        {
                            'title': manga_title,
                            'artist': artist,
                            'parody': parody,
                            'character': character,
                            'group': group,
                            'page': page
                        },
                        page,
                        os.path.basename(image_url),
                        ext.lstrip('.')
                    )
                else:
                    # {}がない場合は文字列をそのまま使用
                    filename = custom_name_format
            else:
                filename = f"page_{page:03d}"
            
            # サニタイズ
            filename = self.sanitize_filename(filename)
            return os.path.join(save_folder, filename + ext)

        except Exception as e:
            self.log(f"保存パス決定エラー: {e}", "error")
            fallback_filename = f"image_{page:03d}{ext}"
            return os.path.join(save_folder, fallback_filename)

    def _save_image_data(self, image_data, save_path, save_format_option, original_url=None):
        """画像データを保存する共通処理"""
        temp_path = save_path + '.tmp'
        
        try:
            # 保存先フォルダの存在確認と作成
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            
            # 既存ファイルチェック
            if os.path.exists(save_path):
                new_path = self._handle_duplicate_file(save_path, 0)
                if not new_path:
                    return True
                save_path = new_path
                temp_path = save_path + '.tmp'
            
            # JPG形式で保存する場合の処理
            if save_format_option == "JPG":
                try:
                    from PIL import Image
                    from io import BytesIO
                    
                    with Image.open(BytesIO(image_data)) as img:
                        # RGBモードに変換
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            bg = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                if save_format_option == "JPEG":
                            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                            img = bg
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        quality = self.jpg_quality.get() if hasattr(self, 'jpg_quality') else 85
                        with open(temp_path, 'wb') as f:
                            img.save(f, 'JPEG', quality=quality)
                        self.log(f"JPG形式で保存（品質: {quality}%）: {os.path.basename(save_path)}")
                        
                except Exception as jpg_error:
                    self.log(f"JPG変換エラー: {jpg_error}, 通常の方法で保存します。")
                    with open(temp_path, 'wb') as f:
                        f.write(image_data)
            else:
                print(f"[DEBUG] _save_image_data: open({temp_path}, 'wb')直前")
                self.log(f"[DEBUG] _save_image_data: open({temp_path}, 'wb')直前")
                with open(temp_path, 'wb') as f:
                    f.write(image_data)
                print(f"[DEBUG] _save_image_data: open({temp_path}, 'wb')直後")
                self.log(f"[DEBUG] _save_image_data: open({temp_path}, 'wb')直後")
            
                            # 一時ファイルを本来のファイル名に移動
            if os.path.exists(temp_path):
                if os.path.exists(save_path):
                    os.remove(save_path)
                os.rename(temp_path, save_path)
            else:
                raise DownloadErrorException(f"一時ファイルが見つかりません: {temp_path}")
            
            # アニメーション画像の処理
            if (save_format_option != "Original" and 
                hasattr(self, 'preserve_animation') and 
                self.preserve_animation.get() and
                original_url):
                
                if self._check_if_animated(save_path):
                    original_ext = os.path.splitext(original_url.split('?')[0])[1]
                    if original_ext:
                        base_path = os.path.splitext(save_path)[0]
                        new_save_path = base_path + original_ext
                        if save_path != new_save_path:
                            if os.path.exists(new_save_path):
                                os.remove(new_save_path)
                            os.rename(save_path, new_save_path)
                            self.log(f"アニメーション画像の形式を保持: {os.path.basename(new_save_path)}")
                            save_path = new_save_path
            
            return save_path
        except Exception as e:
            print(f"[DEBUG] _save_image_data: Exception発生: {e}")
            self.log(f"[DEBUG] _save_image_data: Exception発生: {e}")
            self._cleanup_temp_file(temp_path)
            raise DownloadErrorException(f"画像保存エラー: {e}")
        except BaseException as e:
            print(f"[DEBUG] _save_image_data: BaseException発生: {e}")
            self.log(f"[DEBUG] _save_image_data: BaseException発生: {e}")
            self._cleanup_temp_file(temp_path)
            raise
        
    def _cleanup_temp_file(self, temp_path):
        """一時ファイルの安全な削除"""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            self.log(f"一時ファイルの削除に失敗: {e}", "error")

    def download_and_save_image(self, image_url, save_path, save_format_option, options=None):
        """画像をダウンロードして保存（高度なオプション対応版）"""
        # オプションの取得
        if options is None:
            options = self._get_current_options()
        
        # 高度なオプションが有効な場合の処理
        if options.get('advanced_options_enabled', False):
            return self._download_with_advanced_options(image_url, save_path, save_format_option, options)
        else:
            return self._download_standard(image_url, save_path, save_format_option)
    
    def _download_with_advanced_options(self, image_url, save_path, save_format_option, options):
        """高度なオプション対応のダウンロード方式"""
        try:
            # Seleniumが有効な場合は優先的に使用
            if options.get('selenium_enabled', False):
                self.log("【Selenium】優先的にSeleniumを使用してダウンロード")
                return self._download_with_selenium(image_url, save_path, save_format_option, options)
            
            # httpxが有効な場合
            elif options.get('httpx_enabled', False):
                self.log("【httpx】httpxを使用してダウンロード")
                return self._download_with_httpx(image_url, save_path, save_format_option, options)
            
            # User-Agent偽装が有効な場合
            elif options.get('user_agent_spoofing_enabled', False):
                self.log("【User-Agent】User-Agent偽装を使用してダウンロード")
                return self._download_with_user_agent_spoofing(image_url, save_path, save_format_option, options)
            
            # デフォルトは標準ダウンロード
            else:
                return self._download_standard(image_url, save_path, save_format_option)
                
        except Exception as e:
            self.log(f"高度なオプション対応ダウンロードエラー: {e}", "error")
            # エラー時は標準ダウンロードにフォールバック
            return self._download_standard(image_url, save_path, save_format_option)
    
    def _download_with_selenium(self, image_url, save_path, save_format_option, options):
        """Seleniumを使用したダウンロード"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            import base64
            
            # Chromeドライバーの設定
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # ドライバーの取得
            driver_path = ChromeDriverManager().install()
            service = Service(driver_path)
            
            # ブラウザの起動
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            try:
                # 画像URLにアクセス
                driver.get(image_url)
                
                # 画像のbase64データを取得
                script = """
                var img = document.querySelector('img');
                if (img) {
                    var canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').split(',')[1];
                }
                return null;
                """
                image_data_b64 = driver.execute_script(script)
                
                if image_data_b64:
                    # base64データをデコード
                    image_data = base64.b64decode(image_data_b64)
                    
                    # 保存処理
                    result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                    if result is True:
                        self.log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                    elif result:
                        self.log(f"Selenium画像保存完了: {os.path.basename(result)}")
                    return result
                else:
                    raise Exception("画像データの取得に失敗しました")
                    
            finally:
                driver.quit()
                
        except Exception as e:
            self.log(f"Seleniumダウンロードエラー: {e}", "error")
            raise DownloadErrorException(f"Seleniumダウンロードエラー: {e}")
    
    def _download_with_httpx(self, image_url, save_path, save_format_option, options):
        """httpxを使用したダウンロード"""
        try:
            import httpx
            
            # httpxクライアントの設定
            client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                http2=True
            )
            
            try:
                # 画像をダウンロード
                response = client.get(image_url)
                response.raise_for_status()
                image_data = response.content
                
                # 保存処理
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:
                    self.log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                elif result:
                    self.log(f"httpx画像保存完了: {os.path.basename(result)}")
                return result
                
            finally:
                client.close()
                
        except Exception as e:
            self.log(f"httpxダウンロードエラー: {e}", "error")
            raise DownloadErrorException(f"httpxダウンロードエラー: {e}")
    
    def _download_with_user_agent_spoofing(self, image_url, save_path, save_format_option, options):
        """User-Agent偽装を使用したダウンロード"""
        try:
            # カスタムUser-Agentを設定
            custom_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # カスタムセッションでダウンロード
            with self.session.get(image_url, headers=custom_headers, timeout=30, stream=True) as response:
                response.raise_for_status()
                image_data = response.content
                
                # 保存処理
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:
                    self.log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                elif result:
                    self.log(f"User-Agent偽装画像保存完了: {os.path.basename(result)}")
                return result
                
        except Exception as e:
            self.log(f"User-Agent偽装ダウンロードエラー: {e}", "error")
            raise DownloadErrorException(f"User-Agent偽装ダウンロードエラー: {e}")
    
    def _download_standard(self, image_url, save_path, save_format_option):
        """標準ダウンロード方式（既存の実装）"""
        # パス長チェックと修正
        try:
            if os.name == 'nt':  # Windowsの場合
                # 実際のパス長をチェック
                real_length = len(os.path.abspath(save_path))
                if real_length > self.MAX_PATH_LENGTH:
                    base, ext = os.path.splitext(save_path)
                    max_base_length = self.MAX_PATH_LENGTH - len(ext) - 1
                    save_path = base[:max_base_length] + ext
                    self.log(f"警告: パス名が長すぎるため短縮されました: {os.path.basename(save_path)}", "warning")
        except:
            pass  # パス処理でエラーが発生した場合は元のパスを使用

        # ディスク容量チェック
        try:
            import psutil
            free_space = psutil.disk_usage(os.path.dirname(save_path)).free / (1024 * 1024)
            if free_space < self.DISK_SPACE_WARNING_MB:
                error_msg = f"ディスク容量が不足しています（必要: {self.DISK_SPACE_WARNING_MB}MB, 残り: {free_space:.1f}MB）"
                self.log(error_msg, "error")
                # 既存のエラー処理を利用し、強制的に手動再開モードで中断
                error = DownloadErrorException(error_msg)
                self._handle_permanent_error_new(self.current_gallery_url, error, error_msg)
                self.log("ディスク容量不足のため、手動再開モードに強制変更されました", "warning")
                raise error
        except ImportError:
            pass  # psutilが利用できない場合は容量チェックをスキップ
        except Exception as e:
            if not isinstance(e, DownloadErrorException):
                self.log(f"ディスク容量チェック中にエラーが発生: {str(e)}", "warning")

        # メモリ使用量チェック
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > self.MEMORY_WARNING_THRESHOLD_MB:
                self.log(f"警告: メモリ使用量が高くなっています ({memory_mb:.1f}MB)", "warning")
        except:
            pass  # psutilが利用できない場合は静かに失敗

        temp_path = save_path + '.tmp'
        response = None
        img = None
        
        try:
            # 保存先フォルダの存在確認と作成
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    self.log(f"削除された保存先フォルダを再作成: {save_dir}")
                except Exception as folder_error:
                    raise FolderMissingException(
                        f"保存先フォルダの再作成に失敗: {folder_error}", 
                        save_dir, 
                        getattr(self, 'current_gallery_url', '')
                    )

            # 既存ファイルチェック
            if os.path.exists(save_path):
                new_path = self._handle_duplicate_file(save_path, 0)
                if not new_path:
                    self.log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                    return True
                save_path = new_path
                temp_path = save_path + '.tmp'

            # 画像ダウンロード - with文でリソース管理
            with self.session.get(image_url, timeout=30, stream=True) as response:
                response.raise_for_status()
                image_data = response.content
                self.log(f"画像データ取得完了: {len(image_data)} bytes")

                # 標準の保存処理を使用
                result = self._save_image_data(image_data, save_path, save_format_option, image_url)
                if result is True:  # スキップされた場合
                    self.log(f"既存ファイルのためスキップ: {os.path.basename(save_path)}")
                elif result:  # 保存パスが返された場合
                    self.log(f"画像保存完了: {os.path.basename(result)}")
                return result

        except requests.exceptions.RequestException as req_err:
            # ⭐簡易ネットワークエラーの場合は回復まで待機⭐
            if self._is_simple_network_error(req_err):
                self._cleanup_temp_file(temp_path)
                self._wait_for_network_recovery_simple(image_url, save_path, save_format_option)
                return save_path
            else:
                error_msg = f"画像ダウンロードエラー: {req_err}"
                self.log(error_msg, "error")
                self._cleanup_temp_file(temp_path)
                raise DownloadErrorException(error_msg)

        except Exception as e:
            error_msg = f"画像保存エラー: {e}"
            self.log(error_msg, "error")
            self._cleanup_temp_file(temp_path)
            raise DownloadErrorException(error_msg)
        

    def resize_image(self, image_path, resize_mode, resize_values, save_path=None):
        """画像をリサイズ（拡張子変更後に実行）
        Args:
            image_path: 元画像のパス
            resize_mode: リサイズモード
            resize_values: リサイズ値
            save_path: 保存先パス（Noneの場合は上書き）
        Returns:
            bool: リサイズが実行された場合はTrue、不要だった場合はFalse
        """
        try:
            # PILライブラリが利用可能かチェック
            try:
                from PIL import Image, ImageEnhance
            except ImportError:
                self.log("PIL (Pillow) が利用できません。リサイズをスキップします。")
                return False

            # リサイズサイズを取得
            if not resize_values:
                self.log("リサイズ値が設定されていません。リサイズをスキップします。リサイズ設定を確認してください。")
                return False
            
            # モードに応じた値を取得
            size_value = None
            if resize_mode == "縦幅上限":
                size_value = resize_values.get("height", "0")
            elif resize_mode == "横幅上限":
                size_value = resize_values.get("width", "0")
            elif resize_mode == "長辺上限":
                size_value = resize_values.get("long", "0")
            elif resize_mode == "短辺上限":
                size_value = resize_values.get("short", "0")
            elif resize_mode == "長辺下限":
                size_value = resize_values.get("long", "0")
            elif resize_mode == "短辺下限":
                size_value = resize_values.get("short", "0")
            elif resize_mode == "比率":
                size_value = resize_values.get("percentage", "100")
            else:
                size_value = resize_values.get("unified", "0")
            
            # StringVarからの値取得と検証
            try:
                if hasattr(size_value, "get"):
                    size_value = size_value.get().strip()
                if not size_value:
                    self.log("リサイズ値が設定されていません。リサイズをスキップします。リサイズ設定を確認してください。")
                    return False
                
                target_size = float(size_value)
                if target_size <= 0:
                    self.log("リサイズ値が無効です（0以下）。リサイズをスキップします。正の数値を指定してください。")
                    return False
            except (ValueError, AttributeError) as e:
                self.log(f"リサイズ値が無効です（{str(e)}）。リサイズをスキップします。正の数値を指定してください。")
                return False
            
            self.log(f"リサイズ設定: モード={resize_mode}, 目標サイズ={target_size}")
            
            # 画像の元のサイズを取得してログ出力
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                self.log(f"元の画像サイズ: {original_width}x{original_height}")
                should_resize = False
                new_width, new_height = original_width, original_height
                
                if resize_mode == "縦幅上限":
                    # 縦幅が上限を超える場合のみリサイズ
                    if original_height > target_size:
                        ratio = target_size / original_height
                        new_width = int(original_width * ratio)
                        new_height = int(target_size)
                        should_resize = True
                        self.log(f"縦幅が上限({target_size})を超えているためリサイズします")
                        
                elif resize_mode == "横幅上限":
                    # 横幅が上限を超える場合のみリサイズ
                    if original_width > target_size:
                        ratio = target_size / original_width
                        new_width = int(target_size)
                        new_height = int(original_height * ratio)
                        should_resize = True
                        self.log(f"横幅が上限({target_size})を超えているためリサイズします")
                        
                elif resize_mode == "長辺上限":
                    # 長辺が上限を超える場合のみリサイズ
                    longer_side = max(original_width, original_height)
                    if longer_side > target_size:
                        ratio = target_size / longer_side
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)
                        should_resize = True
                        self.log(f"長辺({longer_side})が上限({target_size})を超えているためリサイズします")
                
                elif resize_mode == "短辺上限":
                    # 短辺が上限を超える場合のみリサイズ
                    shorter_side = min(original_width, original_height)
                    if shorter_side > target_size:
                        ratio = target_size / shorter_side
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)
                        should_resize = True
                        self.log(f"短辺({shorter_side})が上限({target_size})を超えているためリサイズします")
                
                elif resize_mode == "長辺下限":
                    # 長辺が下限未満の場合のみリサイズ
                    longer_side = max(original_width, original_height)
                    if longer_side < target_size:
                        ratio = target_size / longer_side
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)
                        should_resize = True
                        self.log(f"長辺({longer_side})が下限({target_size})未満のためリサイズします")
                
                elif resize_mode == "短辺下限":
                    # 短辺が下限未満の場合のみリサイズ
                    shorter_side = min(original_width, original_height)
                    if shorter_side < target_size:
                        ratio = target_size / shorter_side
                        new_width = int(original_width * ratio)
                        new_height = int(original_height * ratio)
                        should_resize = True
                        self.log(f"短辺({shorter_side})が下限({target_size})未満のためリサイズします")
                
                elif resize_mode == "比率":
                    # 比率によるリサイズ（常に実行、100%以上でも拡大可能）
                    ratio = target_size / 100.0
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                    
                    # 極端に大きな値に対する安全策
                    MAX_SAFE_SIZE = 10000
                    if new_width > MAX_SAFE_SIZE or new_height > MAX_SAFE_SIZE:
                        self.log(f"計算されたサイズが大きすぎます（{new_width}x{new_height}）。リサイズをスキップします。", "warning")
                        return False
                    
                    should_resize = True
                    self.log(f"比率({target_size}%)でリサイズします")
                
                # リサイズが必要な場合のみ実行
                if should_resize:
                    self.log(f"リサイズを実行します: {original_width}x{original_height} → {new_width}x{new_height}")
                    
                    # 補完モードを取得
                    interpolation_mode = "三次補完（画質優先）"
                    if hasattr(self.parent, 'interpolation_mode'):
                        interpolation_mode = self.parent.interpolation_mode.get()
                    interpolation_method = self.INTERPOLATION_MAPPING.get(interpolation_mode, Image.LANCZOS)
                    
                    # リサイズ実行
                    resized_img = img.resize((new_width, new_height), interpolation_method)
                    
                    # シャープネス適用
                    try:
                        sharpness_value = float(self.sharpness_value.get()) if hasattr(self, 'sharpness_value') else 50.0
                        if sharpness_value != 50.0:  # デフォルト値でない場合のみ適用
                            sharpness_factor = sharpness_value / 50.0
                            enhancer = ImageEnhance.Sharpness(resized_img)
                            resized_img = enhancer.enhance(sharpness_factor)
                            self.log(f"シャープネス適用: {sharpness_value}")
                    except Exception as e:
                        self.log(f"シャープネス適用エラー: {e}", "warning")
                    
                    # 保存先パスが指定されている場合はそこに保存
                    target_path = save_path if save_path else image_path
                    # JPG形式の場合は品質設定を適用
                    if target_path.lower().endswith('.jpg') or target_path.lower().endswith('.jpeg'):
                        quality = self.jpg_quality.get() if hasattr(self, 'jpg_quality') else 85
                        resized_img.save(target_path, quality=quality)
                        self.log(f"リサイズ画像をJPG形式で保存（品質: {quality}%）: {os.path.basename(target_path)}")
                    else:
                        resized_img.save(target_path)
                        self.log(f"リサイズが完了しました: {os.path.basename(target_path)}")
                    return True
                else:
                    self.log(f"リサイズは不要です（条件を満たしていません）: {os.path.basename(image_path)}")
                    return False

        except Exception as e:
            self.log(f"リサイズエラー: {e}", "error")
            return False
        
    def navigate_to_next_page(self, soup, wait_time_value):
        """次のページへナビゲート（ネットワークエラー処理強化版）"""
        try:
            # "Next"リンクを検索
            next_link = soup.find('a', id='next')
            if not next_link or not next_link.get('href'):
                self.log("次のページリンクが見つかりませんでした")
                return None

            next_url = next_link['href']
            
            # 次のページにアクセス
            time.sleep(float(wait_time_value))
            
            try:
                response = self.session.get(next_url, timeout=20)
                response.raise_for_status()
                
                if "Your IP address has been temporarily banned" in response.text:
                    raise Exception("IP address banned")
                
                # 現在のページURLを更新
                with self.lock:
                    self.current_image_page_url = next_url
                
                return BeautifulSoup(response.text, 'html.parser')
                
            except requests.exceptions.RequestException as req_err:
                # ネットワークエラー（回線切断等）を明確に区別
                if isinstance(req_err, (requests.exceptions.ConnectionError, 
                                      requests.exceptions.Timeout, 
                                      requests.exceptions.ConnectTimeout,
                                      requests.exceptions.ReadTimeout)):
                    error_msg = f"ネットワーク接続エラー（回線切断の可能性）: {req_err}"
                    self.log(error_msg, "error")
                    raise DownloadErrorException(error_msg)
                else:
                    error_msg = f"HTTPリクエストエラー: {req_err}"
                    self.log(error_msg, "error")
                    raise DownloadErrorException(error_msg)
            
        except DownloadErrorException:
            # DownloadErrorExceptionはそのまま再投げ
            raise
        except Exception as e:
            error_msg = f"次のページへのナビゲーションに失敗: {e}"
            self.log(error_msg, "error")
            raise DownloadErrorException(error_msg)

    def _get_resized_save_path(self, original_path):
        """リサイズ画像の保存パスを取得"""
        try:
            if not os.path.exists(original_path):
                raise FileNotFoundError(f"元画像が存在しません: {original_path}")
                
            original_dir = os.path.dirname(original_path)
            original_name = os.path.basename(original_path)
            name_without_ext, ext = os.path.splitext(original_name)
            
            # リサイズファイル名の設定（修正版）
            try:
                if hasattr(self.resize_filename_enabled, "get") and self.resize_filename_enabled.get():
                    # リネームが有効な場合のみカスタムプレフィックス・サフィックスを適用
                    prefix = self.resized_prefix.get().strip() if hasattr(self.resized_prefix, "get") else ""
                    suffix = self.resized_suffix.get().strip() if hasattr(self.resized_suffix, "get") else "_resized"
                    new_name = f"{prefix}{name_without_ext}{suffix}{ext}"
                else:
                    # リネームが無効な場合
                    if hasattr(self.keep_original, "get") and self.keep_original.get():
                        # オリジナル保持ONでリネーム無効の場合、保存場所が同じディレクトリなら_resizedを付与
                        save_location = self.resize_save_location.get() if hasattr(self.resize_save_location, "get") else "child"
                        if save_location == "same":
                            new_name = f"{name_without_ext}_resized{ext}"
                        else:
                            new_name = original_name  # 元のファイル名をそのまま使用
                    else:
                        new_name = original_name  # 元のファイル名をそのまま使用
            except (AttributeError, Exception) as e:
                self.log(f"ファイル名設定エラー: {e}", "warning")
                new_name = original_name  # デフォルトは元のファイル名
            
            # 保存場所に応じてパス決定
            try:
                save_location = self.resize_save_location.get() if hasattr(self.resize_save_location, "get") else "child"
            except Exception as e:
                self.log(f"保存場所設定エラー: {e}", "warning")
                save_location = "child"  # デフォルト値を使用
                
            # 保存先ディレクトリの決定
            if save_location == "child":
                # 子ディレクトリ
                try:
                    subdir_name = self.resized_subdir_name.get().strip() if hasattr(self.resized_subdir_name, "get") else "resized"
                    if not subdir_name:
                        subdir_name = "resized"  # デフォルト値
                except Exception as e:
                    self.log(f"サブディレクトリ名設定エラー: {e}", "warning")
                    subdir_name = "resized"  # デフォルト値を使用
                    
                save_dir = os.path.join(original_dir, subdir_name)
                
                # 親ディレクトリの存在チェック
                if not os.path.exists(original_dir):
                    raise FileNotFoundError(f"親ディレクトリが存在しません: {original_dir}")
                    
            elif save_location == "parent":
                # 親ディレクトリ
                parent_dir = os.path.dirname(original_dir)
                if not os.path.exists(parent_dir):
                    raise FileNotFoundError(f"親ディレクトリが存在しません: {parent_dir}")
                    
                resized_base_dir = os.path.join(parent_dir, "resized")
                gallery_name = os.path.basename(original_dir)
                save_dir = os.path.join(resized_base_dir, gallery_name)
                
            else:
                # 同じディレクトリ
                if not os.path.exists(original_dir):
                    raise FileNotFoundError(f"保存先ディレクトリが存在しません: {original_dir}")
                save_dir = original_dir

            # 保存先ディレクトリが存在しない場合は作成
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)

            # 同名ファイルが存在する場合の処理
            final_path = os.path.join(save_dir, new_name)
            if os.path.exists(final_path):
                # duplicate_file_modeに従って処理
                duplicate_mode = self.duplicate_file_mode.get() if hasattr(self, 'duplicate_file_mode') else "rename"
                if duplicate_mode == "skip":
                    self.log(f"リサイズファイルが既に存在するためスキップ: {new_name}")
                    return None
                elif duplicate_mode == "overwrite":
                    self.log(f"既存のリサイズファイルを上書き: {new_name}")
                    return final_path
                else:  # rename
                    counter = 1
                    name_without_ext, ext = os.path.splitext(new_name)
                    while os.path.exists(final_path):
                        final_path = os.path.join(save_dir, f"{name_without_ext}({counter}){ext}")
                        counter += 1
                    self.log(f"リサイズファイル名を変更: {os.path.basename(final_path)}")
            
            return final_path
                    
        except Exception as e:
            self.log(f"リサイズパス決定エラー: {e}", "error")
            raise  # エラーを上位に伝播させる

    def _check_if_animated(self, image_path):
        """アニメーション画像かチェック"""
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return hasattr(img, 'is_animated') and img.is_animated
        except:
            return False

    def _start_compression_task(self, folder_path, url=None):
        """圧縮タスクを並行して開始（実行確認強化版）"""
        
        # 圧縮が有効かチェック
        try:
            if not hasattr(self.compression_enabled, "get") or self.compression_enabled.get() != "on":
                return  # ログメッセージを出力しない
        except Exception as e:
            self.log(f"圧縮設定の取得に失敗: {e}", "error")
            return

        if not os.path.exists(folder_path):
            self.log(f"圧縮対象フォルダが存在しません: {folder_path}", "warning")
            return
        
        def compress_thread():
            try:
                # 圧縮状態を実行中に設定
                if url:
                    with self.lock:
                        self.compression_tasks[url] = 'running'
                    self.log(f"圧縮開始: {folder_path} (URL: {url})")
                else:
                    self.log(f"圧縮開始: {folder_path}")
                
                # 圧縮実行
                self._compress_folder(folder_path, None)
                
                # 圧縮完了処理
                if url:
                    with self.lock:
                        self.compression_tasks[url] = 'completed'
                    
                    # UIスレッドで圧縮完了マーカーを追加
                    self.root.after(0, lambda: self._add_compression_complete_marker(url))
                    self.log(f"圧縮完了: {folder_path} (URL: {url})")
                else:
                    self.log(f"圧縮完了: {folder_path}")
                
            except Exception as e:
                if url:
                    with self.lock:
                        self.compression_tasks[url] = 'error'
                    self.log(f"圧縮エラー: {folder_path} (URL: {url}) - {e}", "error")
                else:
                    self.log(f"圧縮エラー: {folder_path} - {e}", "error")
            finally:
                # スレッドリストから削除
                try:
                    if hasattr(self, 'compression_threads'):
                        self.compression_threads.remove(thread)
                except (ValueError, AttributeError):
                    pass
        
        # compression_threadsリストの初期化確認
        if not hasattr(self, 'compression_threads'):
            self.compression_threads = []
        
        # 新しいスレッドを作成して開始
        thread = threading.Thread(target=compress_thread, daemon=True)
        self.compression_threads.append(thread)
        thread.start()
        
        self.log(f"圧縮タスクを開始しました: {folder_path}")

    def _check_all_compressions_complete(self):
        """すべての圧縮が完了しているかチェック"""
        with self.lock:
            for status in self.compression_tasks.values():
                if status == 'running':
                    return False
        return True

    def _get_pending_compression_count(self):
        """実行中の圧縮タスク数を取得"""
        with self.lock:
            return sum(1 for status in self.compression_tasks.values() if status == 'running')

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
            self.root.after_cancel(self._hyperlink_update_timer)
        self._hyperlink_update_timer = self.root.after(500, self._setup_hyperlinks)

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
                    if self._is_valid_eh_url(raw_url_part):
                        self.url_text.tag_add("hyperlink", line_start_index, original_text_end_index)
                        self.url_text.tag_config("hyperlink", foreground="blue", underline=True)
                    
                    # 背景色を更新
                    self.update_url_background(url_key)
                    break
            
            # 全てのURLの背景色を更新
            self._update_all_url_backgrounds()
            
        except Exception as e:
            self.log(f"リサイズ完了マーカー追加エラー: {e}", "error")

    def _add_compression_complete_marker(self, url_key):
        """URLの右側に（圧縮完了）マーカーを追加（ハイパーリンク除外・キーベース）"""
        try:
            content = self.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            # url_key は normalize_url されたものか、フォルダパスの場合がある
            
            for i, line_text in enumerate(lines):
                line_stripped = line_text.strip()
                # マーカーや他のテキストを除いた純粋なURL部分で比較
                raw_url_part = line_stripped.split("（")[0].strip() 
                
                # キーがURLの場合とフォルダパスの場合で比較対象を切り替え
                current_line_key = self.normalize_url(raw_url_part) if self._is_valid_eh_url(raw_url_part) else raw_url_part

                if current_line_key == url_key:
                    if "（圧縮完了）" not in line_text: # マーカーがまだない場合
                        line_start_index = f"{i+1}.0"
                        # 元のテキスト（URL部分）の実際の終了位置を正確に把握
                        original_text_end_index = f"{i+1}.{len(raw_url_part)}"
                        
                        # マーカーを追加（ゼロ幅スペースを使用）
                        self.url_text.insert(original_text_end_index, "\u200B（圧縮完了）")
                        
                        # マーカー部分のタグ付け
                        marker_text = "（圧縮完了）"
                        # マーカーの開始位置は元のテキストの直後（+1はゼロ幅スペース分）
                        marker_start_display_index = f"{i+1}.{len(raw_url_part) + 1}" 
                        marker_end_display_index = f"{i+1}.{len(raw_url_part) + 1 + len(marker_text)}"
                        
                        self.url_text.tag_add("compression_marker", marker_start_display_index, marker_end_display_index)
                        self.url_text.tag_config("compression_marker", 
                                                foreground="green", 
                                                selectforeground="green", # 選択時の文字色
                                                selectbackground=self.url_text.cget("background")) # 選択時の背景を通常に
                        
                        # 元のURL部分にハイパーリンクを再確認・設定 (マーカー部分は含めない)
                        # 既存のハイパーリンクがあれば一度削除し、URL部分にのみ再設定
                        self.url_text.tag_remove("hyperlink", line_start_index, f"{i+1}.end") # 行全体のハイパーリンクを一旦クリア
                        if self._is_valid_eh_url(raw_url_part): # 有効なURLならハイパーリンク設定
                            self.url_text.tag_add("hyperlink", line_start_index, original_text_end_index)
                            self.url_text.tag_config("hyperlink", foreground="blue", underline=True)
                        
                        self.log(f"圧縮完了マーカーを追加: {url_key}")
                        break 
                        
        except Exception as e:
            self.log(f"圧縮完了マーカー追加エラー ({url_key}): {e}", "error")

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
            self.log(f"ファイル名変換エラー: {e}", "error")
            return "untitled"
