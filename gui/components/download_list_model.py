# -*- coding: utf-8 -*-
"""
Download List Data Model Layer (三相設計: データモデル層)

このモジュールは純粋なデータ構造を定義し、ビジネスロジックやUIに依存しません。
Immutableな操作を推奨し、データの整合性を保証します。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import time


class DownloadStatus(Enum):
    """ダウンロードステータス（状態遷移を明確化）"""
    PENDING = "pending"           # ⏳ 待機中
    DOWNLOADING = "downloading"   # ⬇ ダウンロード中
    PAUSED = "paused"            # ⏸ 中断
    COMPLETED = "completed"       # ✅ 完了
    ERROR = "error"              # ❌ エラー
    SKIPPED = "skipped"          # ⏭ スキップ
    INCOMPLETE = "incomplete"     # ⚠ 未完了（画像スキップあり）
    
    @property
    def icon(self) -> str:
        """ステータスアイコン"""
        icons = {
            self.PENDING: "⏳",
            self.DOWNLOADING: "⬇",
            self.PAUSED: "⏸",
            self.COMPLETED: "✅",
            self.ERROR: "❌",
            self.SKIPPED: "⏭",
            self.INCOMPLETE: "⚠"
        }
        return icons.get(self, "")
    
    @property
    def color(self) -> str:
        """ステータス背景色"""
        colors = {
            self.PENDING: "white",
            self.DOWNLOADING: "#FFFACD",  # 薄い黄色
            self.PAUSED: "#E0E0E0",       # 薄いグレー（中断）
            self.COMPLETED: "#E0F6FF",    # 薄い青色
            self.ERROR: "#FFE4E1",        # 薄い赤色
            self.SKIPPED: "#F0F0F0",      # 薄いグレー
            self.INCOMPLETE: "#FFF8DC"    # コーンシルク色
        }
        return colors.get(self, "white")
    
    @property
    def display_name(self) -> str:
        """表示名"""
        names = {
            self.PENDING: "待機中",
            self.DOWNLOADING: "DL中",
            self.COMPLETED: "完了",
            self.ERROR: "エラー",
            self.SKIPPED: "スキップ",
            self.INCOMPLETE: "未完了"
        }
        return names.get(self, "不明")
    
    def can_edit(self) -> bool:
        """編集可能か"""
        return self in {self.PENDING, self.ERROR, self.SKIPPED}
    
    def can_delete(self) -> bool:
        """削除可能か"""
        return self in {self.PENDING, self.ERROR, self.SKIPPED, self.INCOMPLETE}


@dataclass
class DownloadItem:
    """
    ダウンロードアイテムのデータモデル（Immutable推奨）
    
    設計原則:
    - 全てのフィールドはプリミティブ型または不変型
    - ビジネスロジックを含まない（純粋なデータ）
    - バリデーションは最小限（型チェックのみ）
    """
    
    # 必須フィールド
    url: str                                    # 元のURL
    normalized_url: str                         # 正規化URL（検索キー）
    
    # メタデータ
    title: str = "準備中..."                    # ギャラリータイトル
    status: DownloadStatus = DownloadStatus.PENDING
    
    # 進捗情報
    progress: int = 0                          # ダウンロード進捗（0-100%）
    current_page: int = 0                      # 現在のページ
    total_pages: int = 0                       # 総ページ数
    
    # ビジュアル情報
    thumbnail_url: str = ""                    # サムネイルURL
    thumbnail_data: Optional[bytes] = None     # キャッシュされたサムネイル画像
    
    # エラー情報
    error_message: str = ""                    # エラーメッセージ
    error_count: int = 0                       # エラー回数
    
    # 処理完了フラグ
    is_compressed: bool = False                # 圧縮完了
    is_resized: bool = False                   # リサイズ完了
    
    # 権限フラグ（キャッシュ用）
    _is_editable: Optional[bool] = field(default=None, repr=False)
    _is_deletable: Optional[bool] = field(default=None, repr=False)
    
    # Treeview関連
    iid: str = ""                              # TreeviewアイテムID（UI層で設定）
    
    # タイムスタンプ
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None         # ダウンロード開始時刻
    completed_at: Optional[float] = None       # 完了時刻
    
    def __post_init__(self):
        """バリデーション"""
        if not self.url:
            raise ValueError("URLは必須です")
        if not self.normalized_url:
            raise ValueError("正規化URLは必須です")
        if not isinstance(self.status, DownloadStatus):
            raise TypeError("statusはDownloadStatusである必要があります")
        if not 0 <= self.progress <= 100:
            raise ValueError("progressは0-100の範囲である必要があります")
    
    @property
    def is_editable(self) -> bool:
        """編集可能か（キャッシュ）"""
        if self._is_editable is None:
            self._is_editable = self.status.can_edit()
        return self._is_editable
    
    @property
    def is_deletable(self) -> bool:
        """削除可能か（キャッシュ）"""
        if self._is_deletable is None:
            self._is_deletable = self.status.can_delete()
        return self._is_deletable
    
    @property
    def progress_text(self) -> str:
        """進捗テキスト"""
        if self.total_pages > 0:
            return f"{self.current_page}/{self.total_pages} ({self.progress}%)"
        return f"{self.progress}%"
    
    @property
    def markers_text(self) -> str:
        """マーカーテキスト（デバッグログ追加）"""
        markers = []
        if self.is_compressed:
            markers.append("✓圧縮")
        if self.is_resized:
            markers.append("✓リサイズ")
        result = " ".join(markers)
        # デバッグログ（一時的）
        if result:
            print(f"[DEBUG] markers_text: {result} (is_compressed={self.is_compressed}, is_resized={self.is_resized})")
        return result
    
    @property
    def elapsed_time(self) -> Optional[float]:
        """経過時間（秒）"""
        if self.started_at is None:
            return None
        end_time = self.completed_at if self.completed_at else time.time()
        return end_time - self.started_at
    
    @property
    def elapsed_time_text(self) -> str:
        """経過時間テキスト（HH:MM:SS）"""
        elapsed = self.elapsed_time
        if elapsed is None:
            return ""
        
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（シリアライズ用）"""
        return {
            'url': self.url,
            'normalized_url': self.normalized_url,
            'title': self.title,
            'status': self.status.value,
            'progress': self.progress,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'thumbnail_url': self.thumbnail_url,
            'error_message': self.error_message,
            'error_count': self.error_count,
            'is_compressed': self.is_compressed,
            'is_resized': self.is_resized,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadItem':
        """辞書形式から復元（デシリアライズ用）"""
        # statusをEnumに変換
        if isinstance(data.get('status'), str):
            data['status'] = DownloadStatus(data['status'])
        
        # thumbnail_dataは保存しない（メモリ効率のため）
        data.pop('thumbnail_data', None)
        data.pop('_is_editable', None)
        data.pop('_is_deletable', None)
        
        return cls(**data)
    
    def clone(self, **changes) -> 'DownloadItem':
        """
        変更を加えたコピーを作成（Immutable操作）
        
        使用例:
            new_item = item.clone(status=DownloadStatus.DOWNLOADING, progress=50)
        """
        data = self.to_dict()
        data.update(changes)
        data['updated_at'] = time.time()
        
        # statusが文字列の場合はEnumに変換
        if isinstance(data.get('status'), str):
            data['status'] = DownloadStatus(data['status'])
        
        return DownloadItem.from_dict(data)


class DownloadItemFactory:
    """
    DownloadItemのファクトリークラス
    
    複雑な生成ロジックをカプセル化し、データモデル層の責務を明確化
    """
    
    @staticmethod
    def create_from_url(url: str, normalized_url: str, **kwargs) -> DownloadItem:
        """URLからDownloadItemを作成"""
        return DownloadItem(
            url=url,
            normalized_url=normalized_url,
            **kwargs
        )
    
    @staticmethod
    def create_from_backup(backup_data: Dict[str, Any]) -> DownloadItem:
        """バックアップデータから復元"""
        return DownloadItem.from_dict(backup_data)
    
    @staticmethod
    def create_batch_from_urls(urls: list, normalize_func) -> list:
        """複数URLから一括作成"""
        items = []
        for url in urls:
            normalized_url = normalize_func(url)
            item = DownloadItem(url=url, normalized_url=normalized_url)
            items.append(item)
        return items


# バリデーション関数（データモデル層の責務）

def validate_url(url: str) -> bool:
    """URL形式のバリデーション"""
    if not url:
        return False
    
    # 基本的なURL形式チェック
    import re
    pattern = r'^https?://(?:www\.)?e[-x]hentai\.org/g/\d+/[a-f0-9]+/?'
    return bool(re.match(pattern, url, re.IGNORECASE))


def validate_progress(progress: int) -> bool:
    """進捗値のバリデーション"""
    return 0 <= progress <= 100


def validate_status_transition(old_status: DownloadStatus, new_status: DownloadStatus) -> bool:
    """
    ステータス遷移のバリデーション
    
    許可される遷移:
    - PENDING -> DOWNLOADING, SKIPPED, ERROR, PAUSED
    - DOWNLOADING -> COMPLETED, ERROR, INCOMPLETE, PAUSED
    - PAUSED -> DOWNLOADING, SKIPPED
    - ERROR -> DOWNLOADING, SKIPPED
    - SKIPPED -> DOWNLOADING
    - COMPLETED -> (なし: 終了状態)
    - INCOMPLETE -> DOWNLOADING
    """
    valid_transitions = {
        DownloadStatus.PENDING: {
            DownloadStatus.DOWNLOADING,
            DownloadStatus.SKIPPED,
            DownloadStatus.ERROR,
            DownloadStatus.PAUSED  # ⭐追加⭐
        },
        DownloadStatus.DOWNLOADING: {
            DownloadStatus.COMPLETED,
            DownloadStatus.ERROR,
            DownloadStatus.INCOMPLETE,
            DownloadStatus.SKIPPED,  # 中断
            DownloadStatus.PAUSED   # ⭐追加: 一時停止⭐
        },
        DownloadStatus.PAUSED: {  # ⭐追加: 中断状態からの遷移⭐
            DownloadStatus.DOWNLOADING,
            DownloadStatus.SKIPPED
        },
        DownloadStatus.ERROR: {
            DownloadStatus.DOWNLOADING,
            DownloadStatus.SKIPPED
        },
        DownloadStatus.SKIPPED: {
            DownloadStatus.DOWNLOADING
        },
        DownloadStatus.INCOMPLETE: {
            DownloadStatus.DOWNLOADING
        },
        DownloadStatus.COMPLETED: set()  # 終了状態
    }
    
    allowed = valid_transitions.get(old_status, set())
    return new_status in allowed


# エクスポート
__all__ = [
    'DownloadStatus',
    'DownloadItem',
    'DownloadItemFactory',
    'validate_url',
    'validate_progress',
    'validate_status_transition'
]
