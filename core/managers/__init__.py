# -*- coding: utf-8 -*-
"""
Core managers layer - 状態・データ管理層
状態管理、セッション管理、ギャラリー情報、検証、バックアップを担当
"""

from .state_manager import StateManager, DownloadState
from .session_manager import SessionManager
from .gallery_info_manager import GalleryInfoManager
from .validation_manager import ValidationManager
from .backup_manager import DownloadBackupManager
from .settings_backup_manager import SettingsBackupManager

__all__ = [
    'StateManager',
    'DownloadState',
    'SessionManager',
    'GalleryInfoManager',
    'ValidationManager',
    'DownloadBackupManager',
    'SettingsBackupManager',
]
