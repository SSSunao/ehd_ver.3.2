# -*- coding: utf-8 -*-
"""
Settings, constants, and exceptions for EH Downloader
"""

import tkinter as tk
import threading
from PIL import Image

# --- Custom Exceptions ---
class InitialInfoException(Exception):
    """Indicates a non-recoverable error during initial gallery info fetching."""
    pass

class SkipUrlException(Exception):
    """Indicates that the current URL should be skipped."""
    pass

class DownloadErrorException(Exception):
    """Indicates a recoverable download error that can be retried or skipped."""
    def __init__(self, message, url="", page=0, total_pages=0, save_folder=""):
        super().__init__(message)
        self.url = url
        self.page = page
        self.total_pages = total_pages
        self.save_folder = save_folder

class FolderMissingException(Exception):
    """Indicates that the download folder was deleted during download."""
    def __init__(self, message, original_folder="", url=""):
        super().__init__(message)
        self.original_folder = original_folder
        self.url = url

class ToolTip:
    """汎用ツールチップクラス"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.show)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def show(self, event=None):
        if self.tooltip_window:
            return
        
        # ウィジェットの位置を取得（より汎用的な方法）
        try:
            x = self.widget.winfo_rootx() + 25
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        except:
            return  # ウィジェットがまだ表示されていない場合

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip_window, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"), wraplength=400)
        label.pack(ipadx=3, ipady=2)

    def hide(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

# Settings and Constants
SETTINGS_FILENAME = "ehd_settings.json"

# Default values
DEFAULT_VALUES = {
    'wait_time': "0.5",
    'sleep_value': "0.5",
    'save_format': "Original",
    'save_name': "Original",
    'custom_name': "{artist}_{title}_{page}",
    'resize_enabled': "off",
    'resize_mode': "縦幅上限",
    # 個別のリサイズ変数は削除（resize_values辞書を使用）
    'interpolation_mode': "三次補完（画質優先）",
    'sharpness_value': "50",
    'keep_original': True,
    'resize_filename_enabled': False,
    'resized_subdir_name': "resized",
    'resized_prefix': "",
    'resized_suffix': "_resized",
    'resize_save_location': "child",
    'duplicate_folder_mode': "rename",
    'rename_incomplete_folder': False,
    'incomplete_folder_prefix': "[INCOMPLETE]_",
    'compression_enabled': "off",
    'compression_format': "ZIP",
    'compression_delete_original': False,
    'error_handling_mode': "manual",
    'auto_resume_delay': "5",
    'retry_delay_increment': "10",
    'max_retry_delay': "60",
    'max_retry_count': "3",
    'retry_limit_action': "skip_image",  # デフォルト: 画像スキップ（後で再挑戦可能）
    'base_retry_count': 5,  # Context-Aware: 基準リトライ回数
    'base_wait_time': 3,  # Context-Aware: 基準待機時間（秒）
    'circuit_breaker_threshold': 5,  # Circuit Breaker閾値
    'selenium_enabled': True,  # Selenium自動適用
    'first_page_use_title': False,
    'multithread_enabled': "off",
    'multithread_count': 3,
    'preserve_animation': True,
    'folder_name_mode': "h1_priority",
    'custom_folder_name': "{artist}_{title}",
    'first_page_naming_enabled': False,
    'first_page_naming_format': "title",
    'duplicate_file_mode': "overwrite",
    'skip_count': "10",
    'skip_after_count_enabled': False,
    'jpg_quality': 85,
    'string_conversion_enabled': False,
    'advanced_options_enabled': False,
    'user_agent_spoofing_enabled': False,
    'httpx_enabled': False,
    'selenium_enabled': False,
    'selenium_session_retry_enabled': False,
    'selenium_persistent_enabled': False,
    'selenium_page_retry_enabled': False
}

# Interpolation mapping
INTERPOLATION_MAPPING = {
    "三次補完（画質優先）": Image.LANCZOS,
    "線形補間（バランス）": Image.BILINEAR,
    "単純補完（速度優先）": Image.NEAREST
}

# System resource monitoring constants
MEMORY_WARNING_THRESHOLD_MB = 500
DISK_SPACE_WARNING_MB = 100
MAX_PATH_LENGTH = 240

STATE_KEYS = [
    'window_geometry', 'sash_pos_v', 'sash_pos_h', 'folder_path', 'wait_time', 'sleep_value',
    'save_format', 'save_name', 'custom_name', 'cookies_var',
    'resize_mode', 'resize_values', 'keep_original', 'keep_unresized', 'save_resized_subdir',
    'resized_subdir_name', 'resized_prefix', 'resized_suffix',
    'resize_filename_enabled', 'resize_save_location',
    'duplicate_folder_mode', 'initial_error_mode',
    'rename_incomplete_folder', 'incomplete_folder_prefix',
    'compression_enabled', 'compression_format', 'compression_delete_original',
    'auto_resume_enabled', 'auto_resume_delay', 'retry_delay_increment',
    'max_retry_delay', 'max_retry_mode', 'max_retry_count', 'retry_limit_action',
    'url_list_content', 'current_url_index', 'url_status',
    'log_content', 'total_elapsed_seconds',
    'folder_name_mode', 'custom_folder_name', 'first_page_naming_enabled', 
    'first_page_naming_format', 'duplicate_file_mode', 'skip_count',
    'skip_after_count_enabled',
    'string_conversion_enabled', 'string_conversion_rules',
    'jpg_quality', 'resize_quality', 'sharpness_value',
    'advanced_options_enabled', 'user_agent_spoofing_enabled', 'httpx_enabled', 
    'selenium_enabled', 'selenium_session_retry_enabled', 'selenium_persistent_enabled', 'selenium_page_retry_enabled'
]

MIN_PANE_HEIGHT = 200