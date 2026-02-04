"""
プロフェッショナルな進捗管理システム - Phase 1 Implementation

設計原則:
1. Immutable Progress State: スナップショットは不変
2. Thread-Safe: 複数スレッドから安全にアクセス可能
3. Observer Pattern: GUIは進捗変更を監視するだけ
4. Single Responsibility: 進捗管理のみに特化
"""

import threading
import time
from dataclasses import dataclass, field, replace
from typing import Dict, List, Callable, Optional, Any
from enum import Enum


class DownloadPhase(Enum):
    """ダウンロードフェーズ"""
    IDLE = "idle"
    URL_FETCHING = "url_fetching"         # 個別ページURL取得中
    IMAGE_DOWNLOADING = "image_downloading"  # 画像ダウンロード中
    IMAGE_PROCESSING = "image_processing"    # 画像処理中
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


@dataclass(frozen=True)
class ProgressSnapshot:
    """不変な進捗スナップショット
    
    Immutableにすることで:
    - スレッド間でのコピー不要
    - 意図しない変更を防止
    - 履歴管理が容易
    """
    url_index: int
    phase: DownloadPhase
    current: int
    total: int
    status: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def with_update(self, **kwargs) -> 'ProgressSnapshot':
        """新しいスナップショットを返す（イミュータブル更新）
        
        Example:
            new_snapshot = old_snapshot.with_update(current=10, status="処理中")
        """
        return replace(self, timestamp=time.time(), **kwargs)
    
    @property
    def progress_percent(self) -> float:
        """進捗率（0.0 ~ 100.0）"""
        if self.total == 0:
            return 0.0
        return min(100.0, (self.current / self.total) * 100.0)
    
    @property
    def is_active(self) -> bool:
        """アクティブな進捗か（完了/エラーではない）"""
        return self.phase not in [DownloadPhase.COMPLETED, DownloadPhase.ERROR]


class ProgressTracker:
    """スレッドセーフな進捗トラッカー
    
    責務:
    - 進捗状態の一元管理
    - オブザーバーへの通知
    - スレッドセーフなアクセス保証
    
    使用例:
        tracker = ProgressTracker()
        
        # オブザーバー登録
        tracker.subscribe(lambda snapshot: print(f"進捗: {snapshot.progress_percent}%"))
        
        # 進捗更新
        tracker.create(url_index=0, phase=DownloadPhase.URL_FETCHING, total=100)
        tracker.update(url_index=0, current=50)
        tracker.complete(url_index=0)
    """
    
    def __init__(self) -> None:
        self._snapshots: Dict[int, ProgressSnapshot] = {}
        self._lock = threading.RLock()  # 再入可能ロック
        self._observers: List[Callable[[ProgressSnapshot], None]] = []
        self._observer_lock = threading.Lock()
        
    def create(self, 
               url_index: int, 
               phase: DownloadPhase,
               total: int,
               status: str = "",
               metadata: Optional[Dict[str, Any]] = None) -> ProgressSnapshot:
        """新しい進捗を作成
        
        Args:
            url_index: URL識別子
            phase: ダウンロードフェーズ
            total: 総数
            status: ステータスメッセージ
            metadata: 追加メタデータ
            
        Returns:
            作成されたスナップショット
        """
        with self._lock:
            snapshot = ProgressSnapshot(
                url_index=url_index,
                phase=phase,
                current=0,
                total=total,
                status=status,
                metadata=metadata or {}
            )
            self._snapshots[url_index] = snapshot
            self._notify(snapshot)
            return snapshot
    
    def update(self, 
               url_index: int, 
               current: Optional[int] = None,
               status: Optional[str] = None,
               phase: Optional[DownloadPhase] = None,
               metadata: Optional[Dict[str, Any]] = None) -> Optional[ProgressSnapshot]:
        """進捗を更新
        
        Args:
            url_index: URL識別子
            current: 現在値（指定時のみ更新）
            status: ステータス（指定時のみ更新）
            phase: フェーズ（指定時のみ更新）
            metadata: メタデータ（マージされる）
            
        Returns:
            更新されたスナップショット（存在しない場合はNone）
        """
        with self._lock:
            if url_index not in self._snapshots:
                return None
            
            old_snapshot = self._snapshots[url_index]
            updates = {}
            
            if current is not None:
                updates['current'] = current
            if status is not None:
                updates['status'] = status
            if phase is not None:
                updates['phase'] = phase
            if metadata is not None:
                merged_metadata = {**old_snapshot.metadata, **metadata}
                updates['metadata'] = merged_metadata
            
            if not updates:
                return old_snapshot  # 変更なし
            
            new_snapshot = old_snapshot.with_update(**updates)
            self._snapshots[url_index] = new_snapshot
            self._notify(new_snapshot)
            return new_snapshot
    
    def increment(self, url_index: int, delta: int = 1) -> Optional[ProgressSnapshot]:
        """進捗をインクリメント
        
        Args:
            url_index: URL識別子
            delta: 増分（デフォルト1）
            
        Returns:
            更新されたスナップショット
        """
        with self._lock:
            if url_index not in self._snapshots:
                return None
            
            old_snapshot = self._snapshots[url_index]
            new_current = min(old_snapshot.current + delta, old_snapshot.total)
            return self.update(url_index, current=new_current)
    
    def complete(self, url_index: int, status: str = "完了") -> Optional[ProgressSnapshot]:
        """進捗を完了状態にする
        
        Args:
            url_index: URL識別子
            status: 完了メッセージ
            
        Returns:
            完了したスナップショット
        """
        with self._lock:
            if url_index not in self._snapshots:
                return None
            
            old_snapshot = self._snapshots[url_index]
            return self.update(
                url_index,
                phase=DownloadPhase.COMPLETED,
                current=old_snapshot.total,
                status=status
            )
    
    def error(self, url_index: int, error_message: str) -> Optional[ProgressSnapshot]:
        """進捗をエラー状態にする
        
        Args:
            url_index: URL識別子
            error_message: エラーメッセージ
            
        Returns:
            エラー状態のスナップショット
        """
        return self.update(
            url_index,
            phase=DownloadPhase.ERROR,
            status=error_message
        )
    
    def get(self, url_index: int) -> Optional[ProgressSnapshot]:
        """指定URLの進捗を取得
        
        Args:
            url_index: URL識別子
            
        Returns:
            スナップショット（存在しない場合はNone）
        """
        with self._lock:
            return self._snapshots.get(url_index)
    
    def get_all(self) -> Dict[int, ProgressSnapshot]:
        """全進捗を取得
        
        Returns:
            全スナップショットのコピー
        """
        with self._lock:
            return self._snapshots.copy()
    
    def get_active(self) -> List[ProgressSnapshot]:
        """アクティブな進捗を取得
        
        Returns:
            完了/エラーでないスナップショットのリスト
        """
        with self._lock:
            return [s for s in self._snapshots.values() if s.is_active]
    
    def remove(self, url_index: int) -> bool:
        """進捗を削除
        
        Args:
            url_index: URL識別子
            
        Returns:
            削除成功したか
        """
        with self._lock:
            if url_index in self._snapshots:
                del self._snapshots[url_index]
                return True
            return False
    
    def clear(self) -> None:
        """全進捗をクリア"""
        with self._lock:
            self._snapshots.clear()
    
    def subscribe(self, observer: Callable[[ProgressSnapshot], None]) -> None:
        """オブザーバーを登録
        
        Args:
            observer: コールバック関数（引数: ProgressSnapshot）
        """
        with self._observer_lock:
            if observer not in self._observers:
                self._observers.append(observer)
    
    def unsubscribe(self, observer: Callable[[ProgressSnapshot], None]) -> None:
        """オブザーバーを解除
        
        Args:
            observer: 登録済みのコールバック関数
        """
        with self._observer_lock:
            if observer in self._observers:
                self._observers.remove(observer)
    
    def _notify(self, snapshot: ProgressSnapshot) -> None:
        """オブザーバーに通知（内部メソッド）
        
        Args:
            snapshot: 通知するスナップショット
        """
        # ロックを持ったまま通知すると、オブザーバー内でデッドロックの可能性
        # → 一時的にコピーを作成して通知
        with self._observer_lock:
            observers = self._observers.copy()
        
        for observer in observers:
            try:
                observer(snapshot)
            except Exception as e:
                # オブザーバーのエラーは無視（トラッカーの動作を止めない）
                print(f"[ProgressTracker] Observer error: {e}")


class ThrottledProgressObserver:
    """間引き機能付きプログレスオブザーバー
    
    GUI更新頻度を制限し、パフォーマンスを向上させる
    
    使用例:
        throttled = ThrottledProgressObserver(
            callback=lambda s: update_gui(s),
            min_interval_ms=500  # 500msに1回だけ更新
        )
        tracker.subscribe(throttled)
    """
    
    def __init__(self, 
                 callback: Callable[[ProgressSnapshot], None],
                 min_interval_ms: int = 500):
        """
        Args:
            callback: 実際の更新処理
            min_interval_ms: 最小更新間隔（ミリ秒）
        """
        self.callback = callback
        self.min_interval = min_interval_ms / 1000.0  # 秒に変換
        self._last_update: Dict[int, float] = {}  # url_index -> timestamp
        self._lock = threading.Lock()
    
    def __call__(self, snapshot: ProgressSnapshot) -> None:
        """オブザーバーとして呼び出される
        
        Args:
            snapshot: 進捗スナップショット
        """
        with self._lock:
            now = time.time()
            url_index = snapshot.url_index
            last_time = self._last_update.get(url_index, 0)
            
            # 完了/エラーは必ず通知
            should_update = (
                not snapshot.is_active or
                (now - last_time) >= self.min_interval
            )
            
            if should_update:
                self._last_update[url_index] = now
                try:
                    self.callback(snapshot)
                except Exception as e:
                    print(f"[ThrottledObserver] Callback error: {e}")
