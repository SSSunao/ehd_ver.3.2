# -*- coding: utf-8 -*-
"""
イベントバス - スレッド間通信の統一インターフェース

責任:
1. イベントの発行と購読
2. スレッドセーフなイベント配信
3. イベントキューの管理

設計原則:
- 単一責任: イベント配信のみ
- スレッドセーフ: queueベースの実装
- 疎結合: 発行者と購読者が直接依存しない
"""

import queue
import threading
from typing import Callable, Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    """イベントタイプの定義"""
    # ダウンロード関連
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_ERROR = "download_error"
    DOWNLOAD_PAUSED = "download_paused"
    DOWNLOAD_RESUMED = "download_resumed"
    
    # URL関連
    URL_STARTED = "url_started"
    URL_COMPLETED = "url_completed"
    URL_SKIPPED = "url_skipped"
    
    # プログレスバー関連
    PROGRESS_BAR_CREATED = "progress_bar_created"
    PROGRESS_BAR_UPDATED = "progress_bar_updated"
    PROGRESS_BAR_REMOVED = "progress_bar_removed"
    
    # GUI関連
    GUI_UPDATE_REQUIRED = "gui_update_required"
    STATUS_CHANGED = "status_changed"


@dataclass
class Event:
    """イベントデータ"""
    type: EventType
    data: Dict[str, Any]
    source: str = "unknown"
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            import time
            self.timestamp = time.time()


class EventBus:
    """
    イベントバス - スレッド間通信の統一インターフェース
    
    使用例:
        # 購読
        event_bus.subscribe(EventType.DOWNLOAD_PROGRESS, on_progress)
        
        # 発行
        event_bus.publish(Event(
            type=EventType.DOWNLOAD_PROGRESS,
            data={'url_index': 0, 'current': 10, 'total': 100}
        ))
    """
    
    def __init__(self, logger: Callable[[str, str], None] = None):
        """
        Args:
            logger: ログ出力関数（省略可）
        """
        self.logger = logger
        
        # 購読者管理
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._subscribers_lock = threading.Lock()
        
        # イベントキュー
        self._event_queue = queue.Queue()
        
        # 処理スレッド
        self._running = False
        self._worker_thread: threading.Thread = None
    
    def start(self):
        """イベント処理スレッドを開始"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._process_events,
            daemon=True,
            name="EventBus-Worker"
        )
        self._worker_thread.start()
        
        if self.logger:
            self.logger("[EventBus] イベント処理スレッドを開始しました", "debug")
    
    def stop(self):
        """イベント処理スレッドを停止"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        
        if self.logger:
            self.logger("[EventBus] イベント処理スレッドを停止しました", "debug")
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        イベントを購読
        
        Args:
            event_type: イベントタイプ
            callback: コールバック関数（Event型を受け取る）
        """
        with self._subscribers_lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                
                if self.logger:
                    self.logger(
                        f"[EventBus] 購読追加: {event_type.value} -> {callback.__name__}",
                        "debug"
                    )
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        イベントの購読を解除
        
        Args:
            event_type: イベントタイプ
            callback: コールバック関数
        """
        with self._subscribers_lock:
            if event_type in self._subscribers:
                if callback in self._subscribers[event_type]:
                    self._subscribers[event_type].remove(callback)
                    
                    if self.logger:
                        self.logger(
                            f"[EventBus] 購読解除: {event_type.value} -> {callback.__name__}",
                            "debug"
                        )
    
    def publish(self, event: Event):
        """
        イベントを発行
        
        Args:
            event: イベントデータ
        """
        self._event_queue.put(event)
        
        if self.logger:
            self.logger(
                f"[EventBus] イベント発行: {event.type.value} (source={event.source})",
                "debug"
            )
    
    def publish_sync(self, event: Event):
        """
        イベントを同期的に発行（即座に購読者に通知）
        
        Args:
            event: イベントデータ
        """
        self._dispatch_event(event)
    
    def _process_events(self):
        """イベント処理ループ（ワーカースレッド）"""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
                self._dispatch_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                if self.logger:
                    self.logger(f"[EventBus] イベント処理エラー: {e}", "error")
                    import traceback
                    self.logger(f"詳細: {traceback.format_exc()}", "error")
    
    def _dispatch_event(self, event: Event):
        """イベントを購読者に配信"""
        with self._subscribers_lock:
            subscribers = self._subscribers.get(event.type, []).copy()
        
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                if self.logger:
                    self.logger(
                        f"[EventBus] コールバックエラー: {callback.__name__} - {e}",
                        "error"
                    )
                    import traceback
                    self.logger(f"詳細: {traceback.format_exc()}", "error")

