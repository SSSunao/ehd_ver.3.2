# -*- coding: utf-8 -*-
"""
DownloadSession - 統合ダウンロードセッション情報

GalleryInfo、ProgressBar、States を統合した単一の真実の源（Single Source of Truth）
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from enum import Enum
import time
import json
import os


class DownloadStatus(Enum):
    """ダウンロードステータス"""
    WAITING = "待機中"
    DOWNLOADING = "ダウンロード中"
    PAUSED = "中断"
    COMPLETED = "完了"
    SKIPPED = "スキップ"
    ERROR = "エラー"


@dataclass
class DownloadRangeInfo:
    """ダウンロード範囲情報"""
    enabled: bool = False
    start: int = 1
    end: Optional[int] = None
    
    def calculate_relative_total(self, absolute_total: int) -> int:
        """相対総ページ数を計算
        
        Args:
            absolute_total: 絶対総ページ数
            
        Returns:
            相対総ページ数（範囲が無効の場合は絶対総ページ数）
        """
        if not self.enabled:
            return absolute_total
        
        actual_end = self.end if self.end is not None else absolute_total
        # 範囲開始が1より大きい場合、開始ページから終了ページまでのページ数
        return max(0, actual_end - self.start + 1)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'start': self.start,
            'end': self.end
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'DownloadRangeInfo':
        if not data:
            return DownloadRangeInfo()
        return DownloadRangeInfo(
            enabled=data.get('enabled', False),
            start=data.get('start', 1),
            end=data.get('end')
        )


@dataclass
class DownloadSession:
    """
    統合ダウンロードセッション情報
    
    責任:
    - ダウンロード番号、タイトル、URL、保存先の管理
    - 絶対・相対ページ数の管理
    - 経過時間・残り時間の計算
    - ダウンロード範囲の管理
    - ステータス・完了フラグの管理
    - 未完了/完了フォルダフラグの管理
    - JSON永続化
    """
    
    # 基本情報
    url_index: int
    url: str
    title: str = "準備中..."
    save_folder: str = ""
    
    # 絶対ページ数（実際のギャラリーの総ページ数）
    absolute_total: int = 0
    absolute_current: int = 0
    
    # 相対ページ数（ダウンロード範囲が有効な場合に使用）
    relative_total: int = 0
    relative_current: int = 0
    
    # ダウンロード範囲
    download_range: DownloadRangeInfo = field(default_factory=DownloadRangeInfo)
    
    # 時間情報
    start_time: Optional[float] = None
    elapsed_time: float = 0.0
    estimated_remaining: Optional[float] = None
    paused_duration: float = 0.0
    pause_start_time: Optional[float] = None
    
    # ステータス
    status: DownloadStatus = DownloadStatus.WAITING
    completed: bool = False  # ダウンロード完了フラグ
    
    # フォルダフラグ（⭐プロフェッショナルな判断: 含めるべき⭐）
    # 理由: ダウンロードセッションの完全な状態を表すため必要
    is_incomplete_folder: bool = False  # 未完了フォルダフラグ
    is_completed_folder: bool = False   # 完了フォルダフラグ（圧縮済み等）
    
    # エラー情報
    error_message: Optional[str] = None
    
    @property
    def current_elapsed_time(self) -> float:
        """現在の経過時間を計算（一時停止時間を除く）"""
        if self.start_time is None:
            return self.elapsed_time
        
        current_time = time.time()
        elapsed = current_time - self.start_time - self.paused_duration
        
        # 現在一時停止中の場合は、pause_start_timeからの経過時間を除外
        if self.pause_start_time is not None:
            elapsed -= (current_time - self.pause_start_time)
        
        return max(0.0, elapsed)
    
    @property
    def current_estimated_remaining(self) -> Optional[float]:
        """残り予想時間を計算"""
        # 相対ページ数が有効な場合は相対で計算、そうでなければ絶対で計算
        current = self.relative_current if self.download_range.enabled else self.absolute_current
        total = self.relative_total if self.download_range.enabled else self.absolute_total
        
        if current > 0 and total > 0 and current < total:
            elapsed = self.current_elapsed_time
            if elapsed > 0:
                rate = elapsed / current  # 1ページあたりの時間
                remaining_pages = total - current
                return rate * remaining_pages
        return None
    
    def update_relative_pages(self, new_range: Optional[DownloadRangeInfo] = None):
        """相対ページ数を更新
        
        Args:
            new_range: 新しいダウンロード範囲（Noneの場合は現在の範囲を使用）
        """
        if new_range:
            self.download_range = new_range
        
        # 相対総ページ数を計算
        self.relative_total = self.download_range.calculate_relative_total(self.absolute_total)
        
        # 相対現在ページ数を再計算
        # ダウンロード範囲が変更された場合、相対現在ページは1にリセット
        if self.download_range.enabled:
            # 絶対現在ページが範囲内にある場合、相対位置を計算
            if self.absolute_current >= self.download_range.start:
                self.relative_current = self.absolute_current - self.download_range.start + 1
            else:
                # 範囲外の場合は1からスタート
                self.relative_current = 1
        else:
            self.relative_current = self.absolute_current
    
    def update_progress(self, absolute_current: int, absolute_total: Optional[int] = None):
        """進捗を更新
        
        Args:
            absolute_current: 絶対現在ページ数
            absolute_total: 絶対総ページ数（Noneの場合は既存値を使用）
        """
        self.absolute_current = absolute_current
        if absolute_total is not None:
            self.absolute_total = absolute_total
        
        # 相対ページ数を更新
        self.update_relative_pages()
        
        # 経過時間を更新
        self.elapsed_time = self.current_elapsed_time
        
        # 残り時間を更新
        self.estimated_remaining = self.current_estimated_remaining
    
    def start(self):
        """ダウンロード開始"""
        self.start_time = time.time()
        self.status = DownloadStatus.DOWNLOADING
    
    def pause(self):
        """ダウンロード一時停止"""
        self.pause_start_time = time.time()
        self.status = DownloadStatus.PAUSED
    
    def resume(self):
        """ダウンロード再開"""
        if self.pause_start_time is not None:
            self.paused_duration += time.time() - self.pause_start_time
            self.pause_start_time = None
        self.status = DownloadStatus.DOWNLOADING
    
    def complete(self):
        """ダウンロード完了"""
        self.status = DownloadStatus.COMPLETED
        self.completed = True
        self.is_completed_folder = True
        self.is_incomplete_folder = False
        # 経過時間を最終更新
        self.elapsed_time = self.current_elapsed_time
    
    def mark_error(self, error_message: str):
        """エラーマーク"""
        self.status = DownloadStatus.ERROR
        self.error_message = error_message
        self.is_incomplete_folder = True
    
    def skip(self):
        """スキップ"""
        self.status = DownloadStatus.SKIPPED
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（JSON永続化用）"""
        return {
            'url_index': self.url_index,
            'url': self.url,
            'title': self.title,
            'save_folder': self.save_folder,
            'absolute_total': self.absolute_total,
            'absolute_current': self.absolute_current,
            'relative_total': self.relative_total,
            'relative_current': self.relative_current,
            'download_range': self.download_range.to_dict(),
            'start_time': self.start_time,
            'elapsed_time': self.elapsed_time,
            'estimated_remaining': self.estimated_remaining,
            'paused_duration': self.paused_duration,
            'pause_start_time': self.pause_start_time,
            'status': self.status.value,
            'completed': self.completed,
            'is_incomplete_folder': self.is_incomplete_folder,
            'is_completed_folder': self.is_completed_folder,
            'error_message': self.error_message
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'DownloadSession':
        """辞書から復元（JSON読み込み用）"""
        # ステータスをEnumに変換
        status_str = data.get('status', 'WAITING')
        status = DownloadStatus.WAITING
        for s in DownloadStatus:
            if s.value == status_str or s.name == status_str:
                status = s
                break
        
        # ダウンロード範囲を復元
        download_range = DownloadRangeInfo.from_dict(data.get('download_range', {}))
        
        session = DownloadSession(
            url_index=data.get('url_index', 0),
            url=data.get('url', ''),
            title=data.get('title', '準備中...'),
            save_folder=data.get('save_folder', ''),
            absolute_total=data.get('absolute_total', 0),
            absolute_current=data.get('absolute_current', 0),
            relative_total=data.get('relative_total', 0),
            relative_current=data.get('relative_current', 0),
            download_range=download_range,
            start_time=data.get('start_time'),
            elapsed_time=data.get('elapsed_time', 0.0),
            estimated_remaining=data.get('estimated_remaining'),
            paused_duration=data.get('paused_duration', 0.0),
            pause_start_time=data.get('pause_start_time'),
            status=status,
            completed=data.get('completed', False),
            is_incomplete_folder=data.get('is_incomplete_folder', False),
            is_completed_folder=data.get('is_completed_folder', False),
            error_message=data.get('error_message')
        )
        
        return session


class DownloadSessionRepository:
    """DownloadSession の永続化管理（⭐修正: 永続化を無効化⭐）"""
    
    def __init__(self, file_path: str = "download_sessions.json"):
        self.file_path = file_path
        self.sessions: Dict[int, DownloadSession] = {}
        # ⭐修正: 起動時の読み込みを無効化⭐
        # self.load()
    
    def load(self):
        """JSONファイルから読み込み（⭐修正: 無効化⭐）"""
        # ⭐修正: 永続化を無効化したため、何もしない⭐
        pass
    
    def save(self):
        """JSONファイルに保存（⭐修正: 無効化⭐）"""
        # ⭐修正: 永続化を無効化したため、何もしない⭐
        pass
    
    def get(self, url_index: int) -> Optional[DownloadSession]:
        """セッションを取得"""
        return self.sessions.get(url_index)
    
    def set(self, session: DownloadSession):
        """セッションを設定"""
        self.sessions[session.url_index] = session
        self.save()  # 即座に保存
    
    def get_all(self) -> Dict[int, DownloadSession]:
        """全セッションを取得"""
        return self.sessions.copy()
    
    def clear(self):
        """全セッションをクリア"""
        self.sessions.clear()
        self.save()


