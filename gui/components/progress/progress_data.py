"""
プログレスバーのデータクラス（型安全・Immutable）

設計原則:
1. 型アノテーションで静的解析可能
2. Optionalで明示的なNoneチェック
3. dataclassでボイラープレートコード削減
4. frozen=Trueで不変性保証（スレッドセーフ）
5. DownloadSessionとの統合（Single Source of Truth）
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import sys
import os

# ⭐追加: DownloadSessionをインポート⭐
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from core.models.download_session import DownloadSession, DownloadStatus


class ProgressStatus(Enum):
    """プログレスバーの状態（型安全）"""
    WAITING = "待機中"
    DOWNLOADING = "ダウンロード中"
    PAUSED = "中断"
    COMPLETED = "完了"
    SKIPPED = "スキップ"
    ERROR = "エラー"


@dataclass(frozen=True)
class DownloadRange:
    """ダウンロード範囲情報（Immutable）"""
    enabled: bool = False
    start: int = 0
    end: Optional[int] = None
    
    def to_text(self) -> str:
        """表示用テキストを生成"""
        if not self.enabled:
            return ""
        if self.end is None:
            return f"ダウンロード範囲: {self.start}～∞"
        return f"ダウンロード範囲: {self.start}～{self.end}"


@dataclass(frozen=True)
class ProgressInfo:
    """
    プログレスバーの情報（Immutable・型安全）
    
    StateManagerから取得したデータをラップする
    全フィールドがOptionalまたはデフォルト値を持つことで、
    部分的なデータでも安全に扱える
    """
    url_index: int
    url: str
    title: Optional[str] = None
    current: int = 0
    total: int = 0
    status: ProgressStatus = ProgressStatus.WAITING
    start_time: Optional[float] = None
    elapsed_time: float = 0.0
    estimated_remaining: Optional[float] = None
    download_range: DownloadRange = field(default_factory=DownloadRange)
    
    @property
    def progress_percent(self) -> float:
        """進捗率（0-100）"""
        if self.total <= 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100)
    
    @property
    def display_title(self) -> str:
        """表示用タイトル（Noneセーフ）"""
        return self.title or "準備中..."
    
    @property
    def elapsed_text(self) -> str:
        """経過時間テキスト（MM:SS形式）"""
        if self.elapsed_time <= 0:
            return ""
        minutes = int(self.elapsed_time // 60)
        seconds = int(self.elapsed_time % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def remaining_text(self) -> str:
        """残り時間テキスト（MM:SS形式）"""
        if not self.estimated_remaining or self.estimated_remaining <= 0:
            return ""
        minutes = int(self.estimated_remaining // 60)
        seconds = int(self.estimated_remaining % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def build_status_text(self) -> str:
        """
        ステータステキストを構築
        
        Returns:
            "ページ 50/100 | 経過: 05:30 | 残り: 05:30 | 状態: ダウンロード中"
        """
        parts = []
        
        # 一時停止アイコン
        if self.status == ProgressStatus.PAUSED:
            parts.append("⏸")
        
        # ページ数
        if self.total > 0:
            parts.append(f"ページ {self.current}/{self.total}")
        
        # ⭐修正: 経過時間 - ダウンロード完了後も表示し続ける⭐
        if self.elapsed_text:
            parts.append(f"経過: {self.elapsed_text}")
        
        # ⭐修正: 残り時間 - 完了状態の場合は表示しない⭐
        if self.remaining_text and self.status not in [ProgressStatus.COMPLETED, ProgressStatus.SKIPPED, ProgressStatus.ERROR]:
            parts.append(f"残り: {self.remaining_text}")
        
        # ダウンロード範囲
        range_text = self.download_range.to_text()
        if range_text:
            parts.append(range_text)
        
        # 状態
        parts.append(f"状態: {self.status.value}")
        
        return " | ".join(parts) if parts else "状態: 待機中"
    
    @staticmethod
    def from_session(session: 'DownloadSession') -> 'ProgressInfo':
        """
        DownloadSessionからProgressInfoを生成（⭐新しい統合ポイント⭐）
        
        Args:
            session: DownloadSessionインスタンス
            
        Returns:
            ProgressInfo: 型安全なデータオブジェクト
        """
        # ステータスを変換
        status = ProgressStatus.WAITING
        if session.status == DownloadStatus.DOWNLOADING:
            status = ProgressStatus.DOWNLOADING
        elif session.status == DownloadStatus.PAUSED:
            status = ProgressStatus.PAUSED
        elif session.status == DownloadStatus.COMPLETED:
            status = ProgressStatus.COMPLETED
        elif session.status == DownloadStatus.SKIPPED:
            status = ProgressStatus.SKIPPED
        elif session.status == DownloadStatus.ERROR:
            status = ProgressStatus.ERROR
        
        # ダウンロード範囲
        download_range = DownloadRange(
            enabled=session.download_range.enabled,
            start=session.download_range.start,
            end=session.download_range.end
        )
        
        # ⭐相対ページ数を使用（範囲が有効な場合）⭐
        current = session.relative_current if session.download_range.enabled else session.absolute_current
        total = session.relative_total if session.download_range.enabled else session.absolute_total
        
        return ProgressInfo(
            url_index=session.url_index,
            url=session.url,
            title=session.title,
            current=current,
            total=total,
            status=status,
            start_time=session.start_time,
            elapsed_time=session.elapsed_time,
            estimated_remaining=session.estimated_remaining,
            download_range=download_range
        )
    
    @staticmethod
    def from_dict(url_index: int, data: Dict[str, Any]) -> 'ProgressInfo':
        """
        辞書からProgressInfoを生成（防御的プログラミング）
        
        Args:
            url_index: URLインデックス
            data: StateManagerから取得した辞書
            
        Returns:
            ProgressInfo: 型安全なデータオブジェクト
        """
        # ⭐防御的プログラミング: dataがNoneの場合のデフォルト値⭐
        if data is None:
            data = {}
        
        # 状態を変換
        status_str = data.get('status', '待機中')
        # ⭐Noneチェック追加⭐
        if status_str is None:
            status_str = '待機中'
        
        status = ProgressStatus.WAITING
        for s in ProgressStatus:
            if s.value == status_str or s.name.lower() == status_str.lower():
                status = s
                break
        
        # ダウンロード範囲
        range_data = data.get('download_range_info', {})
        # ⭐Noneチェック追加⭐
        if range_data is None:
            range_data = {}
        
        download_range = DownloadRange(
            enabled=range_data.get('enabled', False) if isinstance(range_data, dict) else False,
            start=range_data.get('start', 0) if isinstance(range_data, dict) else 0,
            end=range_data.get('end') if isinstance(range_data, dict) else None
        )
        
        # ⭐防御的プログラミング: 各フィールドのNoneチェックと型チェック⭐
        url = data.get('url', '')
        if url is None:
            url = ''
        
        title = data.get('title')
        # titleがNoneの場合はNoneのまま（Optional）
        
        current = data.get('current', 0)
        if current is None or not isinstance(current, (int, float)):
            current = 0
        
        total = data.get('total', 0)
        if total is None or not isinstance(total, (int, float)):
            total = 0
        
        start_time = data.get('start_time')
        # start_timeがNoneの場合はNoneのまま（Optional）
        
        elapsed_time = data.get('elapsed_time', 0.0)
        if elapsed_time is None or not isinstance(elapsed_time, (int, float)):
            elapsed_time = 0.0
        
        estimated_remaining = data.get('estimated_remaining')
        # estimated_remainingがNoneまたは数値でない場合はNone
        if estimated_remaining is not None and not isinstance(estimated_remaining, (int, float)):
            estimated_remaining = None
        
        return ProgressInfo(
            url_index=url_index,
            url=url,
            title=title,
            current=int(current),
            total=int(total),
            status=status,
            start_time=start_time,
            elapsed_time=float(elapsed_time),
            estimated_remaining=float(estimated_remaining) if estimated_remaining is not None else None,
            download_range=download_range
        )

