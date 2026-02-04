# -*- coding: utf-8 -*-
"""
ダウンロードコンテキスト管理 - 型安全なAPI
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class DownloadStage(Enum):
    """ダウンロードステージ"""
    INITIAL = "initial"
    FETCHING_GALLERY = "fetching_gallery"
    DOWNLOADING_IMAGES = "downloading_images"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class DownloadRange:
    """ダウンロード範囲情報"""
    enabled: bool = False
    start: Optional[int] = None
    end: Optional[int] = None
    relative_page: Optional[int] = None  # 相対ページ番号（範囲内での位置）
    relative_total: Optional[int] = None  # 相対総ページ数
    range_changed: bool = False  # 範囲が変更されたかどうか
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（後方互換性）"""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadRange':
        """辞書から生成"""
        if not data:
            return cls()
        return cls(
            enabled=data.get('enabled', False),
            start=data.get('start'),
            end=data.get('end'),
            relative_page=data.get('relative_page'),
            relative_total=data.get('relative_total'),
            range_changed=data.get('range_changed', False)
        )
    
    def is_in_range(self, page: int) -> bool:
        """ページ番号が範囲内かチェック（絶対ページ番号）"""
        if not self.enabled or not self.start:
            return True
        if page < self.start:
            return False
        if self.end and page > self.end:
            return False
        return True
    
    def __repr__(self) -> str:
        if self.enabled:
            return f"DownloadRange({self.start}-{self.end or '∞'})"
        return "DownloadRange(disabled)"


@dataclass
class DownloadContext:
    """
    ダウンロードコンテキスト - 型安全なAPI
    
    単一URLのダウンロード処理に必要な全情報を管理。
    複数の引数を1つのオブジェクトに統合し、可読性と保守性を向上。
    """
    
    # === 基本情報 ===
    url: str  # 正規化されたURL
    save_folder: str  # 保存先フォルダ
    
    # === ページ情報 ===
    current_page: int = 1  # 現在のページ（絶対ページ番号）
    start_page: int = 1  # 開始ページ
    total_pages: int = 0  # 総ページ数
    
    # === ダウンロード範囲 ===
    download_range: DownloadRange = field(default_factory=DownloadRange)
    applied_range: Optional[Dict[str, Any]] = None  # 適用された範囲情報（後方互換性）
    
    # === ギャラリー情報 ===
    gallery_title: str = ""
    gallery_metadata: Dict[str, Any] = field(default_factory=dict)
    image_page_urls: List[str] = field(default_factory=list)
    # ダウンロード対象画像URLリスト
    download_image_urls: List[str] = field(default_factory=list)
    
    # === 進捗情報 ===
    downloaded_pages: int = 0
    failed_pages: List[int] = field(default_factory=list)
    skipped_pages: List[int] = field(default_factory=list)
    
    # === ステージ管理 ===
    stage: str = "initial"  # DownloadStage
    
    # === オプション（Phase B追加） ===
    options: Optional[Any] = None  # DownloadOptionsオブジェクトまたは辞書
    sub_stage: str = ""
    stage_data: Optional[Dict[str, Any]] = None
    
    # === レジューム情報 ===
    is_resume: bool = False  # レジュームからの再開かどうか
    resume_info: Optional[Dict[str, Any]] = None
    absolute_page: Optional[int] = None  # 絶対ページ番号（レジューム用）
    
    # === エラー情報 ===
    error_occurred: bool = False
    error_message: str = ""
    error_page: Optional[int] = None
    retry_count: int = 0
    
    # === URL管理 ===
    url_index: Optional[int] = None  # URLリスト内のインデックス
    current_image_page_url: str = ""  # 現在処理中の画像ページURL
    
    # === タイムスタンプ ===
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def update_progress(self, page: int):
        """進捗を更新"""
        self.current_page = page
        if page > self.downloaded_pages:
            self.downloaded_pages = page
        self.updated_at = datetime.now().isoformat()
    
    def mark_error(self, error_msg: str, page: Optional[int] = None):
        """エラーをマーク"""
        self.error_occurred = True
        self.error_message = error_msg
        self.error_page = page or self.current_page
        self.stage = "error"
        self.updated_at = datetime.now().isoformat()
    
    def add_failed_page(self, page: int):
        """失敗ページを追加"""
        if page not in self.failed_pages:
            self.failed_pages.append(page)
        self.updated_at = datetime.now().isoformat()
    
    def add_skipped_page(self, page: int):
        """スキップページを追加"""
        if page not in self.skipped_pages:
            self.skipped_pages.append(page)
        self.updated_at = datetime.now().isoformat()
    
    def set_stage(self, stage: str, sub_stage: str = "", stage_data: Optional[Dict] = None):
        """ステージを設定"""
        self.stage = stage
        self.sub_stage = sub_stage
        self.stage_data = stage_data
        self.updated_at = datetime.now().isoformat()
    
    @property
    def progress_percentage(self) -> float:
        """進捗率（0-100）"""
        if self.total_pages == 0:
            return 0.0
        return (self.downloaded_pages / self.total_pages) * 100
    
    @property
    def is_complete(self) -> bool:
        """ダウンロード完了判定"""
        if self.total_pages == 0:
            return False
        return self.downloaded_pages >= self.total_pages
    
    @property
    def has_range(self) -> bool:
        """ダウンロード範囲が有効かどうか"""
        return self.download_range.enabled
    
    def get_relative_page(self) -> Optional[int]:
        """相対ページ番号を取得（範囲内での位置）"""
        if not self.has_range or not self.download_range.start:
            return self.current_page
        return self.current_page - self.download_range.start + 1
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（後方互換性のため）"""
        result = asdict(self)
        # DownloadRangeを辞書に変換
        if isinstance(self.download_range, DownloadRange):
            result['download_range'] = self.download_range.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadContext':
        """辞書から生成"""
        # DownloadRangeを個別に処理
        download_range = data.get('download_range')
        if isinstance(download_range, dict):
            download_range = DownloadRange.from_dict(download_range)
        elif not isinstance(download_range, DownloadRange):
            download_range = DownloadRange()
        
        # 辞書から直接展開（存在しないキーは無視される）
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        filtered_data['download_range'] = download_range
        
        return cls(**filtered_data)
    
    @classmethod
    def from_legacy(cls, url: str, save_folder: str, start_page: int = 1, 
                    total_pages: int = 0, resume_info: Optional[Dict] = None,
                    download_range_info: Optional[Dict] = None) -> 'DownloadContext':
        """
        レガシー引数形式から生成（後方互換性）
        
        Args:
            url: 正規化されたURL
            save_folder: 保存先フォルダ
            start_page: 開始ページ
            total_pages: 総ページ数
            resume_info: レジューム情報
            download_range_info: ダウンロード範囲情報
        """
        # ダウンロード範囲を変換
        download_range = DownloadRange.from_dict(download_range_info or {})
        
        # レジューム情報から復元
        is_resume = resume_info is not None
        gallery_metadata = {}
        if resume_info:
            gallery_metadata = resume_info.get('gallery_metadata', {})
        
        return cls(
            url=url,
            save_folder=save_folder,
            start_page=start_page,
            current_page=start_page,
            total_pages=total_pages,
            download_range=download_range,
            is_resume=is_resume,
            resume_info=resume_info,
            gallery_metadata=gallery_metadata
        )
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        レガシー辞書形式に変換（後方互換性）
        
        既存コードが期待する形式:
        {
            'url': str,
            'applied_range': {...},
            'current_page': int,
            ...
        }
        """
        return {
            'url': self.url,
            'save_folder': self.save_folder,
            'current_page': self.current_page,
            'start_page': self.start_page,
            'total_pages': self.total_pages,
            'applied_range': self.download_range.to_dict() if self.has_range else None,
            'gallery_title': self.gallery_title,
            'downloaded_pages': self.downloaded_pages,
            'stage': self.stage,
            'sub_stage': self.sub_stage,
            'is_resume': self.is_resume
        }
    
    def __repr__(self) -> str:
        """デバッグ用文字列表現"""
        return (
            f"DownloadContext("
            f"url='{self.url[:50]}...', "
            f"page={self.current_page}/{self.total_pages}, "
            f"progress={self.progress_percentage:.1f}%, "
            f"stage={self.stage})"
        )


# ヘルパー関数
def create_download_context(url: str, save_folder: str, start_page: int = 1, 
                            total_pages: int = 0) -> DownloadContext:
    """簡易的なDownloadContext生成"""
    return DownloadContext(
        url=url,
        save_folder=save_folder,
        start_page=start_page,
        current_page=start_page,
        total_pages=total_pages
    )
