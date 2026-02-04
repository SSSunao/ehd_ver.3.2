# -*- coding: utf-8 -*-
"""
ダウンロードタスク - 状態管理の統合
散らばっている状態変数を一つのオブジェクトに統合
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class DownloadTask:
    """
    ダウンロードタスクの状態を管理するクラス
    従来のself変数を全て統合
    """
    
    # URL情報
    url: str = ""
    normalized_url: str = ""
    current_url_index: int = 0
    
    # ページ情報
    current_page: int = 0
    total_pages: int = 0
    last_successful_page: int = 0
    
    # フォルダ情報
    save_folder: str = ""
    base_folder: str = ""
    
    # ギャラリー情報
    gallery_title: str = ""
    gallery_id: str = ""
    artist: str = ""
    parody: str = ""
    character: str = ""
    group: str = ""
    
    # ダウンロード範囲
    download_range_enabled: bool = False
    download_range_start: int = 1
    download_range_end: Optional[int] = None
    
    # リトライ情報
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: float = 5.0
    consecutive_errors: int = 0
    
    # Selenium状態
    is_selenium_mode: bool = False
    selenium_enabled_for_retry: bool = False
    selenium_scope: str = "page"
    selenium_enabled_url: Optional[str] = None
    
    # ステージ情報
    current_stage: str = ""
    sub_stage: str = ""
    stage_data: Dict[str, Any] = field(default_factory=dict)
    
    # フラグ
    is_paused: bool = False
    is_error: bool = False
    is_completed: bool = False
    is_skipped: bool = False
    skip_requested: bool = False
    
    # エラー情報
    error_message: str = ""
    error_type: str = ""
    last_error_page: int = 0
    
    # タイムスタンプ
    start_time: float = 0.0
    last_update_time: float = 0.0
    pause_time: float = 0.0
    
    # 圧縮情報
    compression_in_progress: bool = False
    compression_enabled: bool = False
    resize_enabled: bool = False
    
    # その他
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初期化後の処理"""
        if not self.start_time:
            self.start_time = datetime.now().timestamp()
        self.last_update_time = self.start_time
    
    def update_timestamp(self):
        """タイムスタンプを更新"""
        self.last_update_time = datetime.now().timestamp()
    
    def reset_retry_count(self):
        """リトライカウントをリセット"""
        self.retry_count = 0
        self.consecutive_errors = 0
    
    def increment_retry(self):
        """リトライカウントを増加"""
        self.retry_count += 1
        self.consecutive_errors += 1
        self.update_timestamp()
    
    def can_retry(self) -> bool:
        """リトライ可能かチェック"""
        return self.retry_count < self.max_retries
    
    def mark_success(self):
        """成功をマーク"""
        self.last_successful_page = self.current_page
        self.consecutive_errors = 0
        self.is_error = False
        self.error_message = ""
        self.update_timestamp()
    
    def mark_error(self, error_message: str, error_type: str = ""):
        """エラーをマーク"""
        self.is_error = True
        self.error_message = error_message
        self.error_type = error_type
        self.last_error_page = self.current_page
        self.update_timestamp()
    
    def mark_completed(self):
        """完了をマーク"""
        self.is_completed = True
        self.update_timestamp()
    
    def mark_skipped(self):
        """スキップをマーク"""
        self.is_skipped = True
        self.update_timestamp()
    
    def get_progress_info(self) -> Dict[str, Any]:
        """進捗情報を取得"""
        return {
            'url': self.url,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'progress_percent': (self.current_page / self.total_pages * 100) if self.total_pages > 0 else 0,
            'retry_count': self.retry_count,
            'is_error': self.is_error,
            'is_paused': self.is_paused,
            'is_completed': self.is_completed,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'url': self.url,
            'normalized_url': self.normalized_url,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'save_folder': self.save_folder,
            'gallery_title': self.gallery_title,
            'retry_count': self.retry_count,
            'is_error': self.is_error,
            'error_message': self.error_message,
            'current_stage': self.current_stage,
            'is_completed': self.is_completed,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadTask':
        """辞書から復元"""
        # dataclassのフィールドのみを抽出
        valid_fields = {k: v for k, v in data.items() if k in cls.__annotations__}
        return cls(**valid_fields)
    
    def clone(self) -> 'DownloadTask':
        """タスクのコピーを作成"""
        return DownloadTask(**self.to_dict())
