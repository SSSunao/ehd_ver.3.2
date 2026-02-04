# -*- coding: utf-8 -*-
"""
インターフェース定義 - 依存関係の一方向化のため
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Callable
import threading

class IStateManager(ABC):
    """状態管理インターフェース"""
    
    @abstractmethod
    def set_app_state(self, state: Any):
        pass
    
    @abstractmethod
    def get_app_state(self) -> Any:
        pass
    
    @abstractmethod
    def set_download_running(self, running: bool):
        pass
    
    @abstractmethod
    def is_download_running(self) -> bool:
        pass
    
    @abstractmethod
    def set_paused(self, paused: bool):
        pass
    
    @abstractmethod
    def is_paused(self) -> bool:
        pass
    
    @abstractmethod
    def set_current_url_index(self, index: int):
        pass
    
    @abstractmethod
    def get_current_url_index(self) -> int:
        pass
    
    @abstractmethod
    def set_url_status(self, url: str, status: str):
        pass
    
    @abstractmethod
    def get_url_status(self, url: str) -> str:
        pass
    
    @abstractmethod
    def set_current_gallery_url(self, url: str):
        pass
    
    @abstractmethod
    def get_current_gallery_url(self) -> str:
        pass
    
    @abstractmethod
    def set_progress(self, current: int, total: int):
        pass
    
    @abstractmethod
    def get_progress(self) -> tuple[int, int]:
        pass
    
    @abstractmethod
    def set_session(self, session):
        pass
    
    @abstractmethod
    def get_session(self):
        pass
    
    @abstractmethod
    def set_ssl_settings_applied(self, applied: bool):
        pass
    
    @abstractmethod
    def is_ssl_settings_applied(self) -> bool:
        pass
    
    @abstractmethod
    def set_download_thread(self, thread: threading.Thread):
        pass
    
    @abstractmethod
    def get_download_thread(self) -> Optional[threading.Thread]:
        pass
    
    @abstractmethod
    def get_stop_flag(self) -> threading.Event:
        pass
    
    @abstractmethod
    def reset_stop_flag(self):
        pass
    
    @abstractmethod
    def set_stop_flag(self):
        pass

class ILogger(ABC):
    """ログ出力インターフェース"""
    
    @abstractmethod
    def log(self, message: str, level: str = "info"):
        pass

class IGUIOperations(ABC):
    """GUI操作インターフェース"""
    
    @abstractmethod
    def update_url_background(self, url: str):
        pass
    
    @abstractmethod
    def update_progress_display(self, url: str, current: int, total: int, title_override: str = None, status_text_override: str = None):
        pass
    
    @abstractmethod
    def update_current_progress(self, current: int, total: int, status: str = ""):
        pass
    
    @abstractmethod
    def show_current_progress_bar(self):
        pass
    
    @abstractmethod
    def update_progress_title(self, url: str, title: str):
        pass
    
    @abstractmethod
    def update_gui_for_running(self):
        pass
    
    @abstractmethod
    def update_gui_for_idle(self):
        pass
    
    @abstractmethod
    def update_gui_for_error(self):
        pass

class INetworkOperations(ABC):
    """ネットワーク操作インターフェース"""
    
    @abstractmethod
    def normalize_url(self, url: str) -> str:
        pass
    
    @abstractmethod
    def get_manga_title(self, soup) -> str:
        pass
    
    @abstractmethod
    def get_artist_and_parody(self, soup) -> tuple[str, str, str, str]:
        pass
    
    @abstractmethod
    def create_new_folder_name(self) -> str:
        pass
    
    @abstractmethod
    def configure_ssl_settings(self):
        pass

class IFileOperations(ABC):
    """ファイル操作インターフェース"""
    
    @abstractmethod
    def parse_urls_from_text(self, text: str) -> List[str]:
        pass
    
    @abstractmethod
    def is_valid_eh_url(self, url: str) -> bool:
        pass

class IAsyncExecutor(ABC):
    """非同期実行インターフェース"""
    
    @abstractmethod
    def execute_async(self, func: Callable, *args, **kwargs):
        pass
    
    @abstractmethod
    def execute_after(self, delay_ms: int, func: Callable, *args, **kwargs):
        pass
    
    @abstractmethod
    def execute_gui_async(self, func: Callable, *args, **kwargs):
        pass
    
    @abstractmethod
    def execute_in_thread(self, func: Callable, *args, **kwargs):
        pass


