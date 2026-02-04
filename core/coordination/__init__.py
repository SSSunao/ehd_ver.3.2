# -*- coding: utf-8 -*-
"""
Coordination Layer - 調整層

責任:
- 複数のコンポーネント間の調整
- イベントの順序保証
- 非同期処理の調整

設計原則:
- GUI非依存
- 単一責任
- スレッドセーフ
"""

from .completion_coordinator import CompletionCoordinator, CompletionContext
from .event_bus import EventBus, Event, EventType
from .download_orchestrator import DownloadOrchestrator, DownloadRequest

__all__ = [
    'CompletionCoordinator',
    'CompletionContext',
    'EventBus',
    'Event',
    'EventType',
    'DownloadOrchestrator',
    'DownloadRequest'
]

