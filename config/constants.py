# -*- coding: utf-8 -*-
"""
Constants for EH Downloader
"""

from PIL import Image

# Settings filename
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
    'retry_limit_action': "skip",
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
    'jpg_quality',
    'advanced_options_enabled', 'user_agent_spoofing_enabled', 'httpx_enabled', 
    'selenium_enabled', 'selenium_session_retry_enabled', 'selenium_persistent_enabled', 'selenium_page_retry_enabled'
]

MIN_PANE_HEIGHT = 200