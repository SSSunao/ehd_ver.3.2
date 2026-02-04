# -*- coding: utf-8 -*-
"""
オプション定義メタデータ
すべてのオプションを宣言的に定義し、拡張可能な設計を実現
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, List
from enum import Enum


class OptionType(Enum):
    """オプションのデータ型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DICT = "dict"
    LIST = "list"


class OptionScope(Enum):
    """オプションのスコープ（保存先）"""
    PERSISTENT = "persistent"  # 設定ファイルに保存
    SESSION = "session"        # セッション中のみ有効
    RUNTIME = "runtime"        # 実行時のみ（保存しない）


@dataclass
class OptionDefinition:
    """オプション定義のメタデータ
    
    このクラスで1つのオプションのすべての特性を定義します。
    新しいオプションを追加する場合は、OPTION_DEFINITIONS に追加するだけです。
    """
    # 基本属性
    name: str                           # オプション名（一意のキー）
    display_name: str                   # 表示名
    option_type: OptionType             # データ型
    default_value: Any                  # デフォルト値
    
    # スコープと保存
    scope: OptionScope = OptionScope.PERSISTENT
    
    # GUI関連
    gui_var_name: Optional[str] = None  # GUI変数名（例: "folder_var"）
    gui_widget_type: Optional[str] = None  # ウィジェット型（"Entry", "Checkbutton"等）
    
    # バリデーション
    validator: Optional[Callable[[Any], bool]] = None  # バリデーション関数
    min_value: Optional[Any] = None     # 最小値（数値型の場合）
    max_value: Optional[Any] = None     # 最大値（数値型の場合）
    allowed_values: Optional[List[Any]] = None  # 許可される値のリスト
    
    # 変換関数
    to_internal: Optional[Callable[[Any], Any]] = None  # GUI→内部値への変換
    to_gui: Optional[Callable[[Any], Any]] = None       # 内部値→GUI表示への変換
    
    # メタデータ
    description: str = ""               # 説明
    category: str = "general"           # カテゴリ（グルーピング用）
    deprecated: bool = False            # 廃止予定フラグ
    
    def validate(self, value: Any) -> bool:
        """値のバリデーション"""
        # カスタムバリデータ
        if self.validator and not self.validator(value):
            return False
        
        # 型チェック
        if self.option_type == OptionType.INTEGER:
            if not isinstance(value, int):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
        
        elif self.option_type == OptionType.FLOAT:
            if not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
        
        elif self.option_type == OptionType.BOOLEAN:
            if not isinstance(value, bool):
                return False
        
        # 許可値チェック
        if self.allowed_values and value not in self.allowed_values:
            return False
        
        return True


# ========================================
# 🔧 すべてのオプション定義（拡張可能）
# ========================================

OPTION_DEFINITIONS = [
    # === フォルダ・パス関連 ===
    OptionDefinition(
        name="folder_path",
        display_name="保存ディレクトリ",
        option_type=OptionType.STRING,
        default_value="",
        gui_var_name="folder_var",
        gui_widget_type="Entry",
        description="ダウンロード先のディレクトリパス",
        category="path"
    ),
    
    # === 保存形式関連 ===
    OptionDefinition(
        name="save_format",
        display_name="保存形式",
        option_type=OptionType.STRING,
        default_value="Original",
        allowed_values=["Original", "JPG", "PNG", "WEBP"],  # GUI実際の値に合わせる
        gui_var_name="save_format",
        description="画像の保存形式",
        category="format"
    ),
    
    OptionDefinition(
        name="save_name",
        display_name="ファイル名形式",
        option_type=OptionType.STRING,
        default_value="Original",
        allowed_values=["Original", "Custom", "custom_name", "simple_number", "padded_number"],  # ⭐padded_numberを追加⭐
        gui_var_name="save_name",
        description="ファイル名の形式",
        category="format"
    ),
    
    # === リサイズ関連 ===
    OptionDefinition(
        name="resize_enabled",
        display_name="リサイズ有効",
        option_type=OptionType.STRING,
        default_value="off",
        allowed_values=["on", "off"],
        gui_var_name="resize_enabled",
        description="リサイズ機能の有効/無効",
        category="resize"
    ),
    
    OptionDefinition(
        name="resize_mode",
        display_name="リサイズモード",
        option_type=OptionType.STRING,
        default_value="縦幅上限",
        allowed_values=["縦幅上限", "横幅上限", "長辺上限", "長辺下限", "短辺上限", "短辺下限", "比率"],
        gui_var_name="resize_mode",
        description="リサイズのモード",
        category="resize"
    ),
    
    OptionDefinition(
        name="resize_values",
        display_name="リサイズ値",
        option_type=OptionType.DICT,
        default_value={
            'height': 1024,
            'width': 1024,
            'short': 1024,
            'long': 1024,
            'percentage': 80,
            'unified': 1600
        },
        gui_var_name="resize_values",
        description="リサイズの各種パラメータ",
        category="resize"
    ),
    
    # === ダウンロード範囲関連 ===
    OptionDefinition(
        name="download_range_enabled",
        display_name="ダウンロード範囲指定",
        option_type=OptionType.BOOLEAN,
        default_value=False,
        gui_var_name="download_range_enabled",
        description="ダウンロード範囲の指定を有効化",
        category="download"
    ),
    
    OptionDefinition(
        name="download_range_mode",
        display_name="範囲モード",
        option_type=OptionType.STRING,
        default_value="all",
        allowed_values=["all", "range", "multiple"],
        gui_var_name="download_range_mode",
        description="ダウンロード範囲のモード",
        category="download"
    ),
    
    # === 圧縮関連 ===
    OptionDefinition(
        name="compression_enabled",
        display_name="圧縮有効",
        option_type=OptionType.STRING,
        default_value="off",
        allowed_values=["on", "off"],
        gui_var_name="compression_enabled",
        description="ダウンロード後の圧縮を有効化",
        category="compression"
    ),
    
    OptionDefinition(
        name="compression_format",
        display_name="圧縮形式",
        option_type=OptionType.STRING,
        default_value="ZIP",
        allowed_values=["ZIP", "7Z", "TAR"],
        gui_var_name="compression_format",
        description="圧縮ファイルの形式",
        category="compression"
    ),
    
    # === Selenium関連 ===
    OptionDefinition(
        name="selenium_enabled",
        display_name="Selenium有効",
        option_type=OptionType.BOOLEAN,
        default_value=False,
        gui_var_name="selenium_enabled",
        description="Seleniumを使用した高度なダウンロード",
        category="selenium"
    ),
    
    # === 未完了フォルダ関連 ===
    OptionDefinition(
        name="rename_incomplete_folder",
        display_name="未完了フォルダリネーム",
        option_type=OptionType.BOOLEAN,
        default_value=False,
        gui_var_name="rename_incomplete_folder",
        description="未完了フォルダに接頭辞を付ける",
        category="folder"
    ),
    
    OptionDefinition(
        name="incomplete_folder_prefix",
        display_name="未完了フォルダ接頭辞",
        option_type=OptionType.STRING,
        default_value="[未完了]",
        gui_var_name="incomplete_folder_prefix",
        description="未完了フォルダに付ける接頭辞",
        category="folder"
    ),
    
    # === タイミング関連 ===
    OptionDefinition(
        name="wait_time",
        display_name="待機時間",
        option_type=OptionType.INTEGER,
        default_value=1,
        min_value=0,
        max_value=60,
        gui_var_name="wait_time",
        description="リクエスト間の待機時間（秒）",
        category="timing"
    ),
    
    OptionDefinition(
        name="sleep_value",
        display_name="スリープ時間",
        option_type=OptionType.INTEGER,
        default_value=3,
        min_value=0,
        max_value=300,
        gui_var_name="sleep_value",
        description="エラー後のスリープ時間（秒）",
        category="timing"
    ),
]


# ========================================
# 🔍 ユーティリティ関数
# ========================================

def get_option_definition(name: str) -> Optional[OptionDefinition]:
    """オプション定義を名前で取得"""
    for opt_def in OPTION_DEFINITIONS:
        if opt_def.name == name:
            return opt_def
    return None


def get_options_by_category(category: str) -> List[OptionDefinition]:
    """カテゴリでオプション定義をフィルタ"""
    return [opt for opt in OPTION_DEFINITIONS if opt.category == category]


def get_persistent_options() -> List[OptionDefinition]:
    """永続化対象のオプション定義を取得"""
    return [opt for opt in OPTION_DEFINITIONS if opt.scope == OptionScope.PERSISTENT]


def get_all_option_names() -> List[str]:
    """すべてのオプション名を取得"""
    return [opt.name for opt in OPTION_DEFINITIONS]
