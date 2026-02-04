# -*- coding: utf-8 -*-
"""
スレッドモデルの定義

3層スレッドモデル:
1. GUIスレッド: GUI操作のみ
2. Coordinatorスレッド: 調整役（軽量）
3. Workerスレッド: 重い処理

通信:
- Command Queue: GUI → Coordinator
- Task Queue: Coordinator → Worker
- Event Queue: Worker → GUI
"""

import queue
import threading
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class CommandType(Enum):
    """コマンドタイプ"""
    START_DOWNLOAD = "start_download"
    PAUSE_DOWNLOAD = "pause_download"
    RESUME_DOWNLOAD = "resume_download"
    STOP_DOWNLOAD = "stop_download"
    SKIP_URL = "skip_url"


class TaskType(Enum):
    """タスクタイプ"""
    DOWNLOAD = "download"
    COMPRESS = "compress"


class EventType(Enum):
    """イベントタイプ"""
    PROGRESS_UPDATED = "progress_updated"
    DOWNLOAD_COMPLETED = "completed"
    DOWNLOAD_ERROR = "error"
    SEQUENCE_COMPLETED = "sequence_completed"


@dataclass
class Command:
    """GUIからのコマンド"""
    type: CommandType
    data: Dict[str, Any]


@dataclass
class Task:
    """Workerへのタスク"""
    type: TaskType
    data: Dict[str, Any]


@dataclass
class Event:
    """GUIへのイベント"""
    type: EventType
    data: Dict[str, Any]


class ThreadModel:
    """スレッドモデルの実装"""
    
    def __init__(self, logger):
        """
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger
        
        # キュー（スレッド間通信）
        self.command_queue = queue.Queue()  # GUI → Coordinator
        self.task_queue = queue.Queue()     # Coordinator → Worker
        self.event_queue = queue.Queue()    # Worker → GUI
        
        # スレッド
        self.coordinator_thread: Optional[threading.Thread] = None
        self.worker_threads: Dict[str, threading.Thread] = {}
        
        # 停止フラグ
        self._stop_flag = threading.Event()
        
        # コールバック
        self._event_handlers: Dict[EventType, Callable] = {}
    
    def start(self):
        """スレッドモデル開始"""
        self._stop_flag.clear()
        
        # Coordinatorスレッド開始
        self.coordinator_thread = threading.Thread(
            target=self._coordinator_loop,
            daemon=True,
            name="CoordinatorThread"
        )
        self.coordinator_thread.start()
        
        self.logger.log("[ThreadModel] Coordinatorスレッド開始", "info")
    
    def stop(self):
        """スレッドモデル停止"""
        self._stop_flag.set()
        
        # 全てのキューをクリア
        self._clear_queue(self.command_queue)
        self._clear_queue(self.task_queue)
        self._clear_queue(self.event_queue)
        
        self.logger.log("[ThreadModel] スレッドモデル停止", "info")
    
    def _clear_queue(self, q: queue.Queue):
        """キューをクリア"""
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
    
    def send_command(self, command: Command):
        """GUIからコマンドを送信"""
        self.command_queue.put(command)
    
    def send_task(self, task: Task):
        """Coordinatorからタスクを送信"""
        self.task_queue.put(task)
    
    def send_event(self, event: Event):
        """WorkerからGUIにイベントを送信"""
        self.event_queue.put(event)
    
    def register_event_handler(self, event_type: EventType, handler: Callable):
        """イベントハンドラを登録"""
        self._event_handlers[event_type] = handler
    
    def process_events_in_gui(self):
        """GUIスレッドでイベント処理（定期的に呼び出す）"""
        try:
            while True:
                event = self.event_queue.get_nowait()
                
                # イベントハンドラを呼び出す
                handler = self._event_handlers.get(event.type)
                if handler:
                    try:
                        handler(event)
                    except Exception as e:
                        self.logger.log(
                            f"[ThreadModel] イベントハンドラエラー: {e}",
                            "error"
                        )
                        
        except queue.Empty:
            pass
    
    def _coordinator_loop(self):
        """Coordinatorループ（調整役）"""
        self.logger.log("[ThreadModel] Coordinatorループ開始", "debug")
        
        while not self._stop_flag.is_set():
            try:
                # GUIからのコマンドを受信（タイムアウト付き）
                command = self.command_queue.get(timeout=0.1)
                
                self.logger.log(
                    f"[ThreadModel] コマンド受信: {command.type.value}",
                    "debug"
                )
                
                # コマンドをタスクに変換
                self._handle_command(command)
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.log(
                    f"[ThreadModel] Coordinatorエラー: {e}",
                    "error"
                )
        
        self.logger.log("[ThreadModel] Coordinatorループ終了", "debug")
    
    def _handle_command(self, command: Command):
        """コマンドをハンドリング"""
        if command.type == CommandType.START_DOWNLOAD:
            # ダウンロードタスクを送信
            task = Task(
                type=TaskType.DOWNLOAD,
                data=command.data
            )
            self.send_task(task)
            
        elif command.type == CommandType.PAUSE_DOWNLOAD:
            # 一時停止イベントを送信
            event = Event(
                type=EventType.PROGRESS_UPDATED,
                data={'status': 'paused'}
            )
            self.send_event(event)
            
        # 他のコマンドも同様に処理

