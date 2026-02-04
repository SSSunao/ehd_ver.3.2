# -*- coding: utf-8 -*-
"""
プログレスバーモデル - 型安全なプログレスバー実装
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from enum import Enum

class ProgressStatus(Enum):
    """プログレスバーの状態"""
    WAITING = "待機中"
    PREPARING = "準備中..."
    DOWNLOADING = "ダウンロード中"
    PAUSED = "一時停止"
    COMPLETED = "完了"
    ERROR = "エラー"
    SKIPPED = "スキップ"

@dataclass
class ProgressBar:
    """型安全なプログレスバークラス
    
    Attributes:
        url: ダウンロード対象のURL
        url_index: URL配列内のインデックス
        start_time: ダウンロード開始時刻（Unix timestamp）
        paused_duration: 一時停止の累計時間（秒）
        current: 現在の進捗（ページ番号など）
        total: 合計数（総ページ数など）
        title: ギャラリータイトル
        status: 現在の状態
        download_range_info: ダウンロード範囲情報
    """
    url: str
    url_index: int
    start_time: float = field(default_factory=time.time)
    paused_duration: float = 0.0
    current: int = 0
    total: int = 0
    title: str = "準備中..."
    status: str = ProgressStatus.WAITING.value
    download_range_info: Optional[Dict[str, Any]] = None
    
    # 一時停止関連の内部状態
    _pause_start_time: Optional[float] = field(default=None, repr=False)
    
    @property
    def elapsed_time(self) -> float:
        """経過時間を計算（一時停止時間を除く）"""
        # ⭐修正: start_timeがNoneの場合は0.0を返す⭐
        if self.start_time is None:
            return 0.0
        
        current_time = time.time()
        elapsed = current_time - self.start_time - self.paused_duration
        
        # 現在一時停止中の場合は、pause_start_timeからの経過時間を除外
        if self._pause_start_time is not None:
            elapsed -= (current_time - self._pause_start_time)
        
        return max(0.0, elapsed)
    
    @property
    def estimated_remaining(self) -> Optional[float]:
        """残り予想時間を計算（秒）"""
        if self.current > 0 and self.total > 0 and self.current < self.total:
            elapsed = self.elapsed_time
            if elapsed > 0:
                rate = elapsed / self.current  # 1ページあたりの時間
                remaining_pages = self.total - self.current
                return rate * remaining_pages
        return None
    
    @property
    def progress_percentage(self) -> float:
        """進捗率を計算（0.0～1.0）"""
        if self.total > 0:
            return min(1.0, max(0.0, self.current / self.total))
        return 0.0
    
    @property
    def is_completed(self) -> bool:
        """完了しているかどうか"""
        return self.status in [ProgressStatus.COMPLETED.value, ProgressStatus.SKIPPED.value]
    
    @property
    def is_active(self) -> bool:
        """アクティブ（ダウンロード中）かどうか"""
        return self.status == ProgressStatus.DOWNLOADING.value
    
    def update_progress(self, current: int, total: Optional[int] = None):
        """進捗を更新
        
        Args:
            current: 現在の進捗
            total: 合計数（指定された場合のみ更新）
        """
        self.current = current
        if total is not None and total > 0:
            self.total = total
    
    def set_title(self, title: str):
        """タイトルを設定"""
        self.title = title
    
    def set_status(self, status: str):
        """状態を設定"""
        self.status = status
    
    def pause(self):
        """一時停止を開始"""
        if self._pause_start_time is None:
            self._pause_start_time = time.time()
            self.status = ProgressStatus.PAUSED.value
    
    def resume(self):
        """一時停止から再開"""
        if self._pause_start_time is not None:
            pause_duration = time.time() - self._pause_start_time
            self.paused_duration += pause_duration
            self._pause_start_time = None
            self.status = ProgressStatus.DOWNLOADING.value
    
    def complete(self):
        """完了状態にする"""
        self.status = ProgressStatus.COMPLETED.value
        self.current = self.total
    
    def mark_error(self):
        """エラー状態にする"""
        self.status = ProgressStatus.ERROR.value
    
    def mark_skipped(self):
        """スキップ状態にする"""
        self.status = ProgressStatus.SKIPPED.value
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（JSON出力用）
        
        Returns:
            辞書形式のデータ（内部状態を除く）
        """
        data = asdict(self)
        # 内部状態を除外
        data.pop('_pause_start_time', None)
        # 計算プロパティを追加
        data['elapsed_time'] = self.elapsed_time
        data['estimated_remaining'] = self.estimated_remaining
        data['progress_percentage'] = self.progress_percentage
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProgressBar':
        """辞書からProgressBarを復元
        
        Args:
            data: 辞書形式のデータ
            
        Returns:
            ProgressBarインスタンス
        """
        # 計算プロパティを除外
        data = data.copy()
        data.pop('elapsed_time', None)
        data.pop('estimated_remaining', None)
        data.pop('progress_percentage', None)
        
        return cls(**data)
    
    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return (
            f"ProgressBar(url_index={self.url_index}, "
            f"current={self.current}/{self.total}, "
            f"status={self.status}, "
            f"elapsed={self.elapsed_time:.1f}s)"
        )


@dataclass
class ProgressBarSnapshot:
    """プログレスバーのスナップショット（バックアップ用）
    
    全てのProgressBarの状態を保存・復元するためのコンテナ
    """
    progress_bars: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def add_progress_bar(self, url_index: int, progress_bar: ProgressBar):
        """プログレスバーを追加"""
        self.progress_bars[url_index] = progress_bar.to_dict()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'progress_bars': self.progress_bars,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProgressBarSnapshot':
        """辞書から復元"""
        return cls(
            progress_bars=data.get('progress_bars', {}),
            timestamp=data.get('timestamp', time.time())
        )
    
    def restore_progress_bars(self) -> Dict[int, ProgressBar]:
        """全てのProgressBarを復元
        
        Returns:
            url_index -> ProgressBar のマッピング
        """
        restored = {}
        for url_index, data in self.progress_bars.items():
            try:
                restored[int(url_index)] = ProgressBar.from_dict(data)
            except Exception as e:
                print(f"Failed to restore progress bar {url_index}: {e}")
        return restored
