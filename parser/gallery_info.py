# -*- coding: utf-8 -*-
"""
ギャラリー情報管理 - 型安全なAPI
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class ImageInfo:
    """画像情報"""
    url: str  # 画像ページURL
    direct_url: Optional[str] = None  # 直接画像URL
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None  # バイト数
    format: Optional[str] = None  # "jpg", "png", "gif"など
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImageInfo':
        return cls(
            url=data.get('url', ''),
            direct_url=data.get('direct_url'),
            width=data.get('width'),
            height=data.get('height'),
            size=data.get('size'),
            format=data.get('format')
        )


@dataclass
class GalleryMetadata:
    """ギャラリーメタデータ"""
    title: str = ""
    title_japanese: Optional[str] = None
    artist: Optional[str] = None
    category: Optional[str] = None
    language: Optional[str] = None
    pages: int = 0
    rating: Optional[float] = None
    favorites: Optional[int] = None
    uploader: Optional[str] = None
    posted: Optional[str] = None  # ISO形式の日付文字列
    parent: Optional[str] = None  # 親ギャラリーURL
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != [] and v != ""}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GalleryMetadata':
        return cls(
            title=data.get('title', ''),
            title_japanese=data.get('title_japanese'),
            artist=data.get('artist'),
            category=data.get('category'),
            language=data.get('language'),
            pages=data.get('pages', 0),
            rating=data.get('rating'),
            favorites=data.get('favorites'),
            uploader=data.get('uploader'),
            posted=data.get('posted'),
            parent=data.get('parent'),
            tags=data.get('tags', [])
        )


@dataclass
class GalleryInfo:
    """
    ギャラリー情報 - 型安全なAPI
    
    ギャラリーの全情報を型安全に管理するデータクラス。
    画像URL、メタデータ、進捗情報を統合。
    
    データ構造:
    - url: ギャラリーURL
    - title: ギャラリータイトル（<h1 id="gn">優先、空の場合は<title>）
    - image_page_urls: 画像ページURLのリスト
    - image_infos: 画像情報（ImageInfo）のリスト
    - metadata: ギャラリーメタデータ（GalleryMetadata）
        - title: タイトル（メタデータ内）
        - title_japanese: 日本語タイトル
        - artist: アーティスト
        - category: カテゴリ
        - language: 言語
        - pages: ページ数
        - rating: 評価
        - favorites: お気に入り数
        - uploader: アップローダー
        - posted: 投稿日
        - parent: 親ギャラリーURL
        - tags: タグのリスト
    - total_pages: 総ページ数
    - downloaded_pages: ダウンロード済みページ数
    - download_range_enabled: ダウンロード範囲が有効か
    - download_range_start: ダウンロード範囲開始
    - download_range_end: ダウンロード範囲終了
    - fetched_at: 取得日時（ISO形式）
    """
    
    # 基本情報
    url: str
    title: str = ""
    
    # 画像情報
    image_page_urls: List[str] = field(default_factory=list)
    image_infos: List[ImageInfo] = field(default_factory=list)
    
    # メタデータ
    metadata: GalleryMetadata = field(default_factory=GalleryMetadata)
    
    # 進捗情報
    total_pages: int = 0
    downloaded_pages: int = 0
    
    # ダウンロード範囲情報
    download_range_enabled: bool = False
    download_range_start: Optional[int] = None
    download_range_end: Optional[int] = None
    
    # その他
    fetched_at: Optional[str] = None  # 取得日時（ISO形式）
    
    def __post_init__(self):
        """初期化後処理"""
        if self.total_pages == 0 and self.image_page_urls:
            self.total_pages = len(self.image_page_urls)
        
        if not self.fetched_at:
            self.fetched_at = datetime.now().isoformat()
    
    @property
    def is_complete(self) -> bool:
        """ダウンロード完了判定"""
        return self.downloaded_pages >= self.total_pages
    
    @property
    def progress_percentage(self) -> float:
        """進捗率（0-100）"""
        if self.total_pages == 0:
            return 0.0
        return (self.downloaded_pages / self.total_pages) * 100
    
    def get_image_url(self, page: int) -> Optional[str]:
        """ページ番号から画像URLを取得（1-indexed）"""
        if 1 <= page <= len(self.image_page_urls):
            return self.image_page_urls[page - 1]
        return None
    
    def get_image_info(self, page: int) -> Optional[ImageInfo]:
        """ページ番号から画像情報を取得（1-indexed）"""
        if 1 <= page <= len(self.image_infos):
            return self.image_infos[page - 1]
        return None
    
    def update_progress(self, downloaded: int):
        """進捗を更新"""
        self.downloaded_pages = min(downloaded, self.total_pages)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（後方互換性のため）"""
        return {
            'url': self.url,
            'title': self.title,
            'image_page_urls': self.image_page_urls,
            'image_infos': [img.to_dict() for img in self.image_infos],
            'metadata': self.metadata.to_dict(),
            'total_pages': self.total_pages,
            'downloaded_pages': self.downloaded_pages,
            'download_range_enabled': self.download_range_enabled,
            'download_range_start': self.download_range_start,
            'download_range_end': self.download_range_end,
            'fetched_at': self.fetched_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GalleryInfo':
        """辞書から生成"""
        # ImageInfoリストを復元
        image_infos = []
        if 'image_infos' in data:
            image_infos = [
                ImageInfo.from_dict(img) if isinstance(img, dict) else img
                for img in data['image_infos']
            ]
        
        # GalleryMetadataを復元
        metadata = data.get('metadata', {})
        if isinstance(metadata, dict):
            metadata = GalleryMetadata.from_dict(metadata)
        
        return cls(
            url=data.get('url', ''),
            title=data.get('title', ''),
            image_page_urls=data.get('image_page_urls', []),
            image_infos=image_infos,
            metadata=metadata,
            total_pages=data.get('total_pages', 0),
            downloaded_pages=data.get('downloaded_pages', 0),
            download_range_enabled=data.get('download_range_enabled', False),
            download_range_start=data.get('download_range_start'),
            download_range_end=data.get('download_range_end'),
            fetched_at=data.get('fetched_at')
        )
    
    @classmethod
    def from_legacy(cls, url: str, gallery_data: Dict[str, Any]) -> 'GalleryInfo':
        """
        レガシー辞書形式から生成（後方互換性）
        
        Args:
            url: ギャラリーURL
            gallery_data: 旧形式の辞書データ
                {
                    'gallery_info': {...},
                    'image_page_urls': [...],
                    'total_pages': 100
                }
        """
        gallery_info_dict = gallery_data.get('gallery_info', {})
        
        # メタデータを構築
        metadata = GalleryMetadata(
            title=gallery_info_dict.get('title', ''),
            title_japanese=gallery_info_dict.get('title_japanese'),
            artist=gallery_info_dict.get('artist'),
            category=gallery_info_dict.get('category'),
            language=gallery_info_dict.get('language'),
            pages=gallery_data.get('total_pages', 0),
            tags=gallery_info_dict.get('tags', [])
        )
        
        return cls(
            url=url,
            title=gallery_info_dict.get('title', ''),
            image_page_urls=gallery_data.get('image_page_urls', []),
            metadata=metadata,
            total_pages=gallery_data.get('total_pages', 0)
        )
    
    def __repr__(self) -> str:
        """デバッグ用文字列表現"""
        return (
            f"GalleryInfo("
            f"title='{self.title[:30]}...', "
            f"pages={self.total_pages}, "
            f"progress={self.progress_percentage:.1f}%)"
        )


# ヘルパー関数
def create_gallery_info(url: str, title: str = "", total_pages: int = 0) -> GalleryInfo:
    """簡易的なGalleryInfo生成"""
    return GalleryInfo(
        url=url,
        title=title,
        total_pages=total_pages
    )
