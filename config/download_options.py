# -*- coding: utf-8 -*-
"""
ダウンロードオプション管理 - 型安全なAPI
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, Literal
from enum import Enum


class SaveFormat(Enum):
    """保存形式"""
    ORIGINAL = "Original"
    JPG = "JPG"
    PNG = "PNG"
    WEBP = "WEBP"


class SaveNameFormat(Enum):
    """ファイル名形式"""
    ORIGINAL = "Original"
    CUSTOM = "Custom"
    PAGE_NUMBER = "PageNumber"


class ResizeMode(Enum):
    """リサイズモード"""
    HEIGHT_LIMIT = "縦幅上限"
    WIDTH_LIMIT = "横幅上限"
    SHORT_SIDE = "短辺基準"
    LONG_SIDE = "長辺基準"
    PERCENTAGE = "パーセント"
    UNIFIED = "統一"


class ErrorHandlingMode(Enum):
    """エラーハンドリングモード"""
    MANUAL = "manual"
    AUTO_RETRY = "auto_retry"
    AUTO_SKIP = "auto_skip"
    AUTO_RESUME = "auto_resume"


class FolderNameMode(Enum):
    """フォルダ名モード"""
    H1_PRIORITY = "h1_priority"
    TITLE_PRIORITY = "title_priority"
    CUSTOM = "custom"


class DuplicateMode(Enum):
    """重複処理モード"""
    RENAME = "rename"
    OVERWRITE = "overwrite"
    SKIP = "skip"


@dataclass
class ResizeValues:
    """リサイズ値"""
    height: int = 1024
    width: int = 1024
    short: int = 1024
    long: int = 1024
    percentage: int = 80
    unified: int = 1600
    
    def to_dict(self) -> Dict[str, int]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResizeValues':
        return cls(
            height=data.get('height', 1024),
            width=data.get('width', 1024),
            short=data.get('short', 1024),
            long=data.get('long', 1024),
            percentage=data.get('percentage', 80),
            unified=data.get('unified', 1600)
        )


@dataclass
class DownloadOptions:
    """
    ダウンロードオプション - 型安全なAPI
    
    全てのダウンロード設定を型安全に管理するデータクラス。
    GUI依存を排除し、バリデーションとデフォルト値を提供。
    """
    
    # === 基本設定 ===
    wait_time: int = 1  # ページ間の待機時間（秒）
    sleep_value: int = 3  # スリープ値（秒）
    
    # === 保存形式 ===
    save_format: str = "Original"  # SaveFormat
    save_name: str = "Original"  # SaveNameFormat
    custom_name: str = "{artist}_{title}_{page}"
    
    # === リサイズ設定 ===
    resize_enabled: str = "off"  # "on" | "off"
    resize_mode: str = "縦幅上限"  # ResizeMode
    resize_values: ResizeValues = field(default_factory=ResizeValues)
    keep_original: bool = True
    resize_filename_enabled: bool = False
    resized_subdir_name: str = "resized"
    resized_prefix: str = ""
    resized_suffix: str = "_resized"
    resize_save_location: str = "child"  # "child" | "parent"
    
    # === フォルダ管理 ===
    duplicate_folder_mode: str = "rename"  # DuplicateMode
    rename_incomplete_folder: bool = False
    incomplete_folder_prefix: str = "[INCOMPLETE]_"
    folder_name_mode: str = "h1_priority"  # FolderNameMode
    custom_folder_name: str = "{artist}_{title}"
    
    # === 圧縮設定 ===
    compression_enabled: str = "off"  # "on" | "off"
    compression_format: str = "ZIP"  # "ZIP" | "7Z" | "RAR"
    compression_delete_original: bool = False
    
    # === エラーハンドリング ===
    error_handling_mode: str = "manual"  # ErrorHandlingMode
    auto_resume_delay: int = 5
    retry_delay_increment: int = 10
    max_retry_delay: int = 60
    max_retry_count: int = 3
    retry_limit_action: str = "skip"  # "skip" | "abort"
    
    # === ページ名設定 ===
    first_page_use_title: bool = False
    first_page_naming_enabled: bool = False
    first_page_naming_format: str = "title"
    
    # === マルチスレッド ===
    multithread_enabled: str = "off"  # "on" | "off"
    multithread_count: int = 3
    
    # === 画像処理 ===
    preserve_animation: bool = True
    jpg_quality: int = 85
    
    # === ファイル処理 ===
    duplicate_file_mode: str = "overwrite"  # DuplicateMode
    skip_count: int = 10
    skip_after_count_enabled: bool = False
    
    # === 高度な設定 ===
    string_conversion_enabled: bool = False
    advanced_options_enabled: bool = False
    user_agent_spoofing_enabled: bool = False
    httpx_enabled: bool = False
    
    # === Selenium設定 ===
    selenium_enabled: bool = False
    selenium_session_retry_enabled: bool = False
    selenium_persistent_enabled: bool = False
    selenium_page_retry_enabled: bool = False
    
    # === ダウンロード範囲 ===
    download_range_enabled: bool = False
    download_range_mode: str = "全てのURL"
    download_range_start: Optional[str] = ""
    download_range_end: Optional[str] = ""
    
    # === 追加フィールド（内部使用） ===
    title: Optional[str] = None  # ギャラリータイトル（内部使用）
    folder_path: str = ""  # 保存フォルダパス（GUIから取得）
    
    def validate(self) -> tuple[bool, str]:
        """
        オプションのバリデーション
        
        Returns:
            (有効性, エラーメッセージ)
        """
        # 数値範囲チェック
        if self.wait_time < 0:
            return False, "wait_timeは0以上である必要があります"
        
        if self.sleep_value < 0:
            return False, "sleep_valueは0以上である必要があります"
        
        if not (1 <= self.max_retry_count <= 10):
            return False, "max_retry_countは1-10の範囲である必要があります"
        
        if not (1 <= self.jpg_quality <= 100):
            return False, "jpg_qualityは1-100の範囲である必要があります"
        
        if self.multithread_count < 1:
            return False, "multithread_countは1以上である必要があります"
        
        # ダウンロード範囲チェック（有効な場合のみ）
        if self.download_range_enabled:
            try:
                # 開始位置チェック（空文字列または0の場合はスキップ）
                if self.download_range_start and str(self.download_range_start).strip():
                    start_str = str(self.download_range_start).strip()
                    if start_str not in ["空欄は0", "空欄は∞", "0"]:
                        start = int(self.download_range_start)
                        if start < 1:
                            return False, "download_range_startは1以上である必要があります"
                
                # 終了位置チェック
                if self.download_range_end and str(self.download_range_end).strip():
                    end_str = str(self.download_range_end).strip()
                    if end_str not in ["空欄は0", "空欄は∞", "0"]:
                        end = int(self.download_range_end)
                        if end < 1:
                            return False, "download_range_endは1以上である必要があります"
                        
                        # 開始位置との比較
                        if self.download_range_start and str(self.download_range_start).strip():
                            start_str = str(self.download_range_start).strip()
                            if start_str not in ["空欄は0", "空欄は∞", "0"]:
                                start = int(self.download_range_start)
                        if end < start:
                            return False, "download_range_endはdownload_range_start以上である必要があります"
            except (ValueError, TypeError):
                return False, "download_range_start/endは数値である必要があります"
        
        return True, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（後方互換性のため）"""
        result = asdict(self)
        # ResizeValuesを辞書に変換
        if isinstance(self.resize_values, ResizeValues):
            result['resize_values'] = self.resize_values.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadOptions':
        """辞書から生成"""
        # ResizeValuesを個別に処理
        resize_values = data.get('resize_values')
        if isinstance(resize_values, dict):
            resize_values = ResizeValues.from_dict(resize_values)
        elif not isinstance(resize_values, ResizeValues):
            resize_values = ResizeValues()
        
        # 辞書から直接展開（存在しないキーは無視される）
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        filtered_data['resize_values'] = resize_values
        
        return cls(**filtered_data)
    
    @classmethod
    def from_gui(cls, parent: Any, force_reload: bool = False) -> 'DownloadOptions':
        """
        GUIオブジェクトから生成（安全な属性アクセス）
        
        Args:
            parent: GUIオブジェクト（tkinter.Tkなど）
            force_reload: Trueの場合、キャッシュを無視して再読み込み
            
        Returns:
            DownloadOptionsインスタンス
            
        Note:
            force_reload=Trueはリスタート/レジューム時に使用
        """
        def safe_get(attr_name: str, default: Any) -> Any:
            """安全な属性取得。StringVar/IntVarなどは.get()を呼び出して値を返す"""
            try:
                attr = getattr(parent, attr_name, default)
                if hasattr(attr, 'get'):
                    value = attr.get()
                    # デバッグ: 取得した値の型を確認
                    if not isinstance(value, (str, int, bool, type(None))):
                        print(f"[WARNING] {attr_name}の値が予期しない型: {type(value)}")
                    return value
                return attr
            except Exception as e:
                print(f"[ERROR] safe_get({attr_name}): {e}")
                return default
        
        def safe_int(value: Any, default: int) -> int:
            """安全な整数変換。値は既に.get()済みを前提"""
            try:
                # 既にsafe_getで.get()済みなので再度.get()しない
                if isinstance(value, str):
                    return int(value) if value else default
                return int(value)
            except:
                return default
        
        def safe_bool(value: Any, default: bool) -> bool:
            """安全なブール変換。値は既に.get()済みを前提"""
            try:
                # 既にsafe_getで.get()済み
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', 'yes', '1', 'on')
                return bool(value)
            except:
                return default
        
        # ResizeValuesを構築
        resize_values = ResizeValues(
            height=safe_int(safe_get('height_limit', 1024), 1024),
            width=safe_int(safe_get('width_limit', 1024), 1024),
            short=safe_int(safe_get('short_side_limit', 1024), 1024),
            long=safe_int(safe_get('long_side_limit', 1024), 1024),
            percentage=safe_int(safe_get('percentage_value', 80), 80),
            unified=safe_int(safe_get('unified_limit', 1600), 1600)
        )
        
        return cls(
            wait_time=safe_int(safe_get('wait_time', 1), 1),
            sleep_value=safe_int(safe_get('sleep_value', 3), 3),
            save_format=safe_get('save_format', "Original"),
            save_name=safe_get('save_name', "Original"),
            custom_name=safe_get('custom_name', "{artist}_{title}_{page}"),
            resize_enabled=safe_get('resize_enabled', "off"),
            resize_mode=safe_get('resize_mode', "縦幅上限"),
            resize_values=resize_values,
            keep_original=safe_bool(safe_get('keep_original', True), True),
            resize_filename_enabled=safe_bool(safe_get('resize_filename_enabled', False), False),
            resized_subdir_name=safe_get('resized_subdir_name', "resized"),
            resized_prefix=safe_get('resized_prefix', ""),
            resized_suffix=safe_get('resized_suffix', "_resized"),
            resize_save_location=safe_get('resize_save_location', "child"),
            duplicate_folder_mode=safe_get('duplicate_folder_mode', "rename"),
            rename_incomplete_folder=safe_bool(safe_get('rename_incomplete_folder', False), False),
            incomplete_folder_prefix=safe_get('incomplete_folder_prefix', "[INCOMPLETE]_"),
            folder_name_mode=safe_get('folder_name_mode', "h1_priority"),
            custom_folder_name=safe_get('custom_folder_name', "{artist}_{title}"),
            compression_enabled=safe_get('compression_enabled', "off"),
            compression_format=safe_get('compression_format', "ZIP"),
            compression_delete_original=safe_bool(safe_get('compression_delete_original', False), False),
            error_handling_mode=safe_get('error_handling_mode', "manual"),
            auto_resume_delay=safe_int(safe_get('auto_resume_delay', 5), 5),
            retry_delay_increment=safe_int(safe_get('retry_delay_increment', 10), 10),
            max_retry_delay=safe_int(safe_get('max_retry_delay', 60), 60),
            max_retry_count=safe_int(safe_get('max_retry_count', 3), 3),
            retry_limit_action=safe_get('retry_limit_action', "skip"),
            first_page_use_title=safe_bool(safe_get('first_page_use_title', False), False),
            first_page_naming_enabled=safe_bool(safe_get('first_page_naming_enabled', False), False),
            first_page_naming_format=safe_get('first_page_naming_format', "title"),
            multithread_enabled=safe_get('multithread_enabled', "off"),
            multithread_count=safe_int(safe_get('multithread_count', 3), 3),
            preserve_animation=safe_bool(safe_get('preserve_animation', True), True),
            jpg_quality=safe_int(safe_get('jpg_quality', 85), 85),
            duplicate_file_mode=safe_get('duplicate_file_mode', "overwrite"),
            skip_count=safe_int(safe_get('skip_count', 10), 10),
            skip_after_count_enabled=safe_bool(safe_get('skip_after_count_enabled', False), False),
            string_conversion_enabled=safe_bool(safe_get('string_conversion_enabled', False), False),
            advanced_options_enabled=safe_bool(safe_get('advanced_options_enabled', False), False),
            user_agent_spoofing_enabled=safe_bool(safe_get('user_agent_spoofing_enabled', False), False),
            httpx_enabled=safe_bool(safe_get('httpx_enabled', False), False),
            selenium_enabled=safe_bool(safe_get('selenium_enabled', False), False),
            selenium_session_retry_enabled=safe_bool(safe_get('selenium_session_retry_enabled', False), False),
            selenium_persistent_enabled=safe_bool(safe_get('selenium_persistent_enabled', False), False),
            selenium_page_retry_enabled=safe_bool(safe_get('selenium_page_retry_enabled', False), False),
            download_range_enabled=safe_bool(safe_get('download_range_enabled', False), False),
            download_range_mode=safe_get('download_range_mode', "全てのURL"),
            download_range_start=safe_get('download_range_start', ""),
            download_range_end=safe_get('download_range_end', "")
        )
    
    def __repr__(self) -> str:
        """デバッグ用文字列表現"""
        return (
            f"DownloadOptions("
            f"save_format={self.save_format}, "
            f"max_retry={self.max_retry_count}, "
            f"range={self.download_range_enabled})"
        )


# グローバルデフォルトインスタンス
DEFAULT_OPTIONS = DownloadOptions()
