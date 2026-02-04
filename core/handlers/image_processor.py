# -*- coding: utf-8 -*-
"""
Image Processor - 画像処理の専門コンポーネント

責任範囲:
- 画像リサイズ処理
- リサイズパラメータ管理
- リサイズファイル保存場所制御
- 画像検証・変換
"""

import os
from typing import Dict, Any, Optional


class ImageProcessor:
    """画像処理を担当するプロセッサー
    
    downloader.pyから画像処理ロジックを分離し、
    単一責任の原則に従った設計を実現。
    """
    
    def __init__(self, parent):
        """初期化
        
        Args:
            parent: EHDownloaderCoreインスタンス（依存性注入）
        """
        self.parent = parent
        self.session_manager = parent.session_manager
    
    def process_image_resize(self, image_path: str, gallery_info: Any, page_num: int, 
                            image_info: Any, resize_values: Optional[Dict[str, Any]] = None) -> bool:
        """画像のリサイズ処理
        
        Args:
            image_path: 画像ファイルパス
            gallery_info: ギャラリー情報
            page_num: ページ番号
            image_info: 画像情報
            resize_values: リサイズパラメータ（Noneの場合は自動取得）
            
        Returns:
            bool: 成功したらTrue
        """
        try:
            # リサイズ機能が無効の場合はスキップ
            if not hasattr(self.parent.parent, 'resize_enabled') or \
               self.parent.parent.resize_enabled.get() != "on":
                return False
            
            # リサイズ値とモードを取得
            resize_mode = self.parent.parent.resize_mode.get()
            
            # resize_valuesが渡されていない場合は取得
            if resize_values is None:
                resize_values = self.get_resize_values_safely()
            
            if not resize_values:
                self.session_manager.ui_bridge.post_log("リサイズ値が取得できません", "warning")
                return False
            
            self.session_manager.ui_bridge.post_log(
                f"リサイズ処理開始: {image_path} (モード: {resize_mode})", "debug"
            )
            
            # リサイズ処理を実行
            from utils.file_utils import EHDownloaderFileUtils
            file_utils = EHDownloaderFileUtils(self.parent.parent)
            
            # リサイズ後の保存場所を決定
            resize_save_location = "child"  # デフォルト
            if hasattr(self.parent.parent, 'resize_save_location'):
                resize_save_location = self.parent.parent.resize_save_location.get()
            
            # リサイズ後のファイル名を生成
            resized_path = self._generate_resized_path(
                image_path, resize_save_location
            )
            
            # リサイズ実行（resize_valuesを辞書形式で渡す）
            resize_values_dict = {
                k: int(v) if isinstance(v, str) and v.isdigit() else v 
                for k, v in resize_values.items()
            }
            success = file_utils.resize_image(
                image_path, resize_mode, resize_values_dict, resized_path
            )
            
            if success:
                self.session_manager.ui_bridge.post_log(
                    f"リサイズ処理完了: {resized_path}", "debug"
                )
            else:
                self.session_manager.ui_bridge.post_log(
                    f"リサイズ処理失敗: {image_path}", "warning"
                )
            
            return success
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"リサイズ処理エラー: {e}", "error"
            )
            raise
    
    def _generate_resized_path(self, image_path: str, resize_save_location: str) -> str:
        """リサイズ後のファイルパスを生成
        
        Args:
            image_path: 元の画像パス
            resize_save_location: 保存場所 ('child' or 'same')
            
        Returns:
            str: リサイズ後の保存パス
        """
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        ext = os.path.splitext(image_path)[1]
        
        # ファイル名の接頭辞・接尾辞を取得
        resized_prefix = ""
        resized_suffix = "_resized"
        if hasattr(self.parent.parent, 'resized_prefix'):
            resized_prefix = self.parent.parent.resized_prefix.get()
        if hasattr(self.parent.parent, 'resized_suffix'):
            resized_suffix = self.parent.parent.resized_suffix.get()
        
        resized_filename = f"{resized_prefix}{base_name}{resized_suffix}{ext}"
        
        # 保存場所に基づいてパスを決定
        if resize_save_location == "child":
            # 子ディレクトリに保存
            subdir_name = "resized"  # デフォルト
            if hasattr(self.parent.parent, 'resized_subdir_name'):
                subdir_name = self.parent.parent.resized_subdir_name.get()
            
            original_dir = os.path.dirname(image_path)
            resized_dir = os.path.join(original_dir, subdir_name)
            
            # ディレクトリが存在しない場合は作成
            if not os.path.exists(resized_dir):
                os.makedirs(resized_dir)
            
            resized_path = os.path.join(resized_dir, resized_filename)
        else:
            # 同一フォルダに保存
            resized_path = os.path.join(
                os.path.dirname(image_path), resized_filename
            )
        
        return resized_path

    def get_resize_values_safely(self) -> Dict[str, int]:
        """resize_valuesを安全に取得
        
        Returns:
            Dict[str, int]: リサイズパラメータ辞書
        """
        try:
            # 安全な属性アクセス関数
            def safe_get_attr(obj, attr_name, default=None):
                try:
                    if hasattr(obj, attr_name):
                        attr = getattr(obj, attr_name)
                        if hasattr(attr, 'get'):
                            return attr.get()
                        else:
                            return attr
                    return default
                except Exception:
                    return default

            # 安全な数値変換関数
            def safe_int(value, default=0):
                try:
                    if hasattr(value, 'get'):
                        value = value.get()
                    return int(value) if value else default
                except (ValueError, TypeError):
                    return default

            # resize_valuesを直接取得
            if hasattr(self.parent.parent, 'resize_values'):
                resize_values = self.parent.parent.resize_values
            else:
                resize_values = {}
            
            if not isinstance(resize_values, dict):
                resize_values = {}

            result = {}
            for key in ['height', 'width', 'short', 'long', 'percentage', 'unified']:
                if key in resize_values:
                    value = resize_values[key]
                    if hasattr(value, 'get'):
                        # tk.StringVarの場合
                        str_value = value.get()
                        result[key] = safe_int(
                            str_value, 1024 if key != 'percentage' else 80
                        )
                    else:
                        # 文字列値の場合
                        result[key] = safe_int(
                            value, 1024 if key != 'percentage' else 80
                        )
                else:
                    # デフォルト値
                    result[key] = 1024 if key != 'percentage' else 80
            
            return result
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"resize_values取得エラー: {e}", "error"
            )
            import traceback
            self.session_manager.ui_bridge.post_log(
                f"resize_values取得エラー詳細: {traceback.format_exc()}", "error"
            )
            return {
                'height': 1024,
                'width': 1024,
                'short': 1024,
                'long': 1024,
                'percentage': 80,
                'unified': 1600
            }
    
    def validate_image(self, image_path: str) -> bool:
        """画像ファイルの検証
        
        Args:
            image_path: 画像ファイルパス
            
        Returns:
            bool: 有効な画像ならTrue
        """
        try:
            if not os.path.exists(image_path):
                return False
            
            # ファイルサイズチェック
            file_size = os.path.getsize(image_path)
            if file_size == 0:
                return False
            
            # 画像拡張子チェック
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif']
            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext not in image_extensions:
                return False
            
            # PIL で画像を開いて検証
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    img.verify()
                return True
            except Exception:
                return False
                
        except Exception:
            return False
    
    def get_image_format(self, image_path: str) -> Optional[str]:
        """画像フォーマットを取得
        
        Args:
            image_path: 画像ファイルパス
            
        Returns:
            Optional[str]: 画像フォーマット（'JPEG', 'PNG'等）、エラー時はNone
        """
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.format
        except Exception:
            return None
