# -*- coding: utf-8 -*-
"""
ダウンロードセッション管理 - スレッド維持型レジューム処理
プロフェッショナルな状態機械パターンによる実装
"""

import threading
import time
import json
import os
from enum import Enum
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, asdict

class SessionState(Enum):
    """セッション状態"""
    IDLE = "idle"                   # アイドル状態
    INITIALIZING = "initializing"   # 初期化中
    DOWNLOADING = "downloading"     # ダウンロード中
    PAUSED = "paused"              # 一時停止
    ERROR = "error"                # エラー発生
    RETRYING = "retrying"          # リトライ中
    COMPLETED = "completed"        # 完了
    ABORTED = "aborted"            # 中止

class SessionAction(Enum):
    """セッションアクション"""
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    ERROR = "error"
    RETRY = "retry"
    SKIP = "skip"
    COMPLETE = "complete"
    ABORT = "abort"

@dataclass
class SessionContext:
    """セッションコンテキスト - 現在の実行状態"""
    url: str = ""
    normalized_url: str = ""
    current_page: int = 0
    total_pages: int = 0
    save_folder: str = ""
    stage: str = ""
    sub_stage: str = ""
    retry_count: int = 0
    error_message: str = ""
    last_successful_page: int = 0
    timestamp: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionContext':
        """辞書から復元"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

class DownloadSession:
    """
    ダウンロードセッション管理クラス
    スレッドを維持したまま状態遷移によるレジューム処理を実現
    """
    
    # 状態遷移表
    STATE_TRANSITIONS = {
        SessionState.IDLE: {
            SessionAction.START: SessionState.INITIALIZING,
        },
        SessionState.INITIALIZING: {
            SessionAction.START: SessionState.DOWNLOADING,
            SessionAction.ERROR: SessionState.ERROR,
            SessionAction.ABORT: SessionState.ABORTED,
        },
        SessionState.DOWNLOADING: {
            SessionAction.PAUSE: SessionState.PAUSED,
            SessionAction.ERROR: SessionState.ERROR,
            SessionAction.COMPLETE: SessionState.COMPLETED,
            SessionAction.ABORT: SessionState.ABORTED,
        },
        SessionState.PAUSED: {
            SessionAction.RESUME: SessionState.DOWNLOADING,
            SessionAction.ABORT: SessionState.ABORTED,
        },
        SessionState.ERROR: {
            SessionAction.RETRY: SessionState.RETRYING,
            SessionAction.SKIP: SessionState.DOWNLOADING,
            SessionAction.ABORT: SessionState.ABORTED,
            SessionAction.RESUME: SessionState.DOWNLOADING,
        },
        SessionState.RETRYING: {
            SessionAction.START: SessionState.DOWNLOADING,
            SessionAction.ERROR: SessionState.ERROR,
            SessionAction.ABORT: SessionState.ABORTED,
        },
        SessionState.COMPLETED: {
            SessionAction.START: SessionState.INITIALIZING,
        },
        SessionState.ABORTED: {
            SessionAction.START: SessionState.INITIALIZING,
        },
    }
    
    def __init__(self, session_id: str, parent=None, state_manager=None):
        """
        Args:
            session_id: セッションの一意識別子
            parent: 親オブジェクト（ログ出力用）
            state_manager: 状態管理マネージャー
        """
        self.session_id = session_id
        self.parent = parent
        self.state_manager = state_manager
        
        # 状態管理
        self.current_state = SessionState.IDLE
        self.previous_state = None
        self._state_lock = threading.RLock()
        
        # セッションコンテキスト
        self.context = SessionContext()
        self._context_lock = threading.RLock()
        
        # アクションキュー（スレッドセーフ）
        self._action_queue = []
        self._action_lock = threading.Lock()
        self._action_event = threading.Event()
        
        # 状態変更コールバック
        self._state_callbacks = []
        
        # 永続化設定
        self.persistence_file = f"session_{session_id}.json"
        
        # セッション実行フラグ
        self._running = False
        self._worker_thread = None
        
        # リトライポリシー
        self.max_retries = 3
        self.retry_delay = 5.0
        
        self.log(f"セッション初期化完了: {session_id}")
    
    def log(self, message: str, level: str = "info"):
        """ログ出力"""
        if self.parent and hasattr(self.parent, 'log'):
            self.parent.log(f"[Session:{self.session_id}] {message}", level)
    
    def start_session(self, context: SessionContext) -> bool:
        """
        セッションを開始
        
        Args:
            context: 初期コンテキスト
            
        Returns:
            成功した場合True
        """
        try:
            with self._state_lock:
                if self.current_state != SessionState.IDLE:
                    self.log(f"セッション開始失敗: 現在の状態={self.current_state}", "warning")
                    return False
                
                # コンテキストを設定
                with self._context_lock:
                    self.context = context
                    self.context.timestamp = time.time()
                
                # 状態遷移
                self._transition_state(SessionAction.START)
                
                # ワーカースレッドを開始
                self._running = True
                self._worker_thread = threading.Thread(
                    target=self._session_worker,
                    name=f"SessionWorker-{self.session_id}",
                    daemon=True
                )
                self._worker_thread.start()
                
                self.log("セッション開始")
                return True
                
        except Exception as e:
            self.log(f"セッション開始エラー: {e}", "error")
            return False
    
    def _session_worker(self):
        """セッションワーカースレッド - メインループ"""
        self.log("セッションワーカー開始")
        
        try:
            while self._running:
                # アクションキューを処理
                action = self._get_next_action()
                
                if action:
                    self._process_action(action)
                else:
                    # アクションがない場合は待機
                    self._action_event.wait(timeout=0.1)
                    self._action_event.clear()
                
                # 状態に応じた処理
                current_state = self.get_state()
                
                if current_state == SessionState.DOWNLOADING:
                    # ダウンロード処理は外部から制御される
                    # ここでは状態の監視のみ
                    time.sleep(0.1)
                    
                elif current_state == SessionState.PAUSED:
                    # 一時停止中は待機
                    self.log("一時停止中...", "debug")
                    time.sleep(0.5)
                    
                elif current_state == SessionState.ERROR:
                    # エラー状態での待機
                    self.log("エラー状態で待機中...", "debug")
                    time.sleep(0.5)
                    
                elif current_state == SessionState.RETRYING:
                    # リトライ待機
                    self.log(f"リトライ待機中... ({self.retry_delay}秒)", "debug")
                    time.sleep(self.retry_delay)
                    
                elif current_state in [SessionState.COMPLETED, SessionState.ABORTED]:
                    # 終了状態
                    self.log(f"セッション終了: {current_state.value}")
                    break
                    
        except Exception as e:
            self.log(f"セッションワーカーエラー: {e}", "error")
            with self._state_lock:
                self.current_state = SessionState.ERROR
                self.context.error_message = str(e)
        
        finally:
            self._running = False
            self.log("セッションワーカー終了")
    
    def pause(self) -> bool:
        """セッションを一時停止"""
        return self._enqueue_action(SessionAction.PAUSE)
    
    def resume(self) -> bool:
        """セッションを再開"""
        return self._enqueue_action(SessionAction.RESUME)
    
    def report_error(self, error_message: str) -> bool:
        """エラーを報告"""
        with self._context_lock:
            self.context.error_message = error_message
        return self._enqueue_action(SessionAction.ERROR)
    
    def retry(self) -> bool:
        """リトライを実行"""
        with self._context_lock:
            self.context.retry_count += 1
        return self._enqueue_action(SessionAction.RETRY)
    
    def skip_current(self) -> bool:
        """現在の項目をスキップ"""
        return self._enqueue_action(SessionAction.SKIP)
    
    def complete(self) -> bool:
        """セッションを完了"""
        return self._enqueue_action(SessionAction.COMPLETE)
    
    def abort(self) -> bool:
        """セッションを中止"""
        return self._enqueue_action(SessionAction.ABORT)
    
    def _enqueue_action(self, action: SessionAction) -> bool:
        """アクションをキューに追加"""
        try:
            with self._action_lock:
                self._action_queue.append(action)
            self._action_event.set()
            self.log(f"アクションをキューに追加: {action.value}", "debug")
            return True
        except Exception as e:
            self.log(f"アクションキュー追加エラー: {e}", "error")
            return False
    
    def _get_next_action(self) -> Optional[SessionAction]:
        """次のアクションを取得"""
        with self._action_lock:
            if self._action_queue:
                return self._action_queue.pop(0)
        return None
    
    def _process_action(self, action: SessionAction):
        """アクションを処理"""
        try:
            self.log(f"アクション処理: {action.value}")
            
            # 状態遷移
            if self._transition_state(action):
                # 状態変更コールバックを呼び出し
                self._notify_state_change()
                
                # 永続化
                self.save_state()
            else:
                self.log(f"無効な状態遷移: {action.value} from {self.current_state.value}", "warning")
                
        except Exception as e:
            self.log(f"アクション処理エラー: {e}", "error")
    
    def _transition_state(self, action: SessionAction) -> bool:
        """
        状態遷移を実行
        
        Args:
            action: 実行するアクション
            
        Returns:
            遷移が成功した場合True
        """
        with self._state_lock:
            current = self.current_state
            
            # 遷移表から次の状態を取得
            if current not in self.STATE_TRANSITIONS:
                return False
            
            transitions = self.STATE_TRANSITIONS[current]
            if action not in transitions:
                return False
            
            next_state = transitions[action]
            
            # 状態を更新
            self.previous_state = current
            self.current_state = next_state
            
            self.log(f"状態遷移: {current.value} -> {next_state.value} (action: {action.value})")
            return True
    
    def get_state(self) -> SessionState:
        """現在の状態を取得"""
        with self._state_lock:
            return self.current_state
    
    def get_context(self) -> SessionContext:
        """コンテキストのコピーを取得"""
        with self._context_lock:
            # dataclassのコピーを返す
            return SessionContext(**asdict(self.context))
    
    def update_context(self, **kwargs):
        """コンテキストを更新"""
        with self._context_lock:
            for key, value in kwargs.items():
                if hasattr(self.context, key):
                    setattr(self.context, key, value)
            self.context.timestamp = time.time()
    
    def register_state_callback(self, callback: Callable[[SessionState, SessionState], None]):
        """状態変更コールバックを登録"""
        self._state_callbacks.append(callback)
    
    def _notify_state_change(self):
        """状態変更を通知"""
        for callback in self._state_callbacks:
            try:
                callback(self.previous_state, self.current_state)
            except Exception as e:
                self.log(f"状態変更コールバックエラー: {e}", "error")
    
    def save_state(self) -> bool:
        """セッション状態を永続化"""
        try:
            state_data = {
                'session_id': self.session_id,
                'current_state': self.current_state.value,
                'previous_state': self.previous_state.value if self.previous_state else None,
                'context': self.context.to_dict(),
                'timestamp': time.time()
            }
            
            with open(self.persistence_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            
            self.log("セッション状態を保存", "debug")
            return True
            
        except Exception as e:
            self.log(f"状態保存エラー: {e}", "error")
            return False
    
    def load_state(self) -> bool:
        """セッション状態を復元"""
        try:
            if not os.path.exists(self.persistence_file):
                self.log("永続化ファイルが存在しません", "debug")
                return False
            
            with open(self.persistence_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # 状態を復元
            with self._state_lock:
                self.current_state = SessionState(state_data['current_state'])
                if state_data['previous_state']:
                    self.previous_state = SessionState(state_data['previous_state'])
            
            # コンテキストを復元
            with self._context_lock:
                self.context = SessionContext.from_dict(state_data['context'])
            
            self.log(f"セッション状態を復元: {self.current_state.value}")
            return True
            
        except Exception as e:
            self.log(f"状態復元エラー: {e}", "error")
            return False
    
    def can_resume(self) -> bool:
        """レジューム可能かチェック"""
        state = self.get_state()
        return state in [SessionState.PAUSED, SessionState.ERROR]
    
    def get_resume_info(self) -> Dict[str, Any]:
        """レジューム情報を取得"""
        context = self.get_context()
        return {
            'url': context.url,
            'page': context.current_page,
            'total_pages': context.total_pages,
            'save_folder': context.save_folder,
            'retry_count': context.retry_count,
            'last_successful_page': context.last_successful_page,
            'state': self.get_state().value,
        }
    
    def cleanup(self):
        """セッションのクリーンアップ"""
        try:
            self._running = False
            
            # ワーカースレッドの終了を待機
            if self._worker_thread and self._worker_thread.is_alive():
                self._action_event.set()  # スレッドを起こす
                self._worker_thread.join(timeout=2.0)
            
            # 永続化ファイルを削除
            if os.path.exists(self.persistence_file):
                os.remove(self.persistence_file)
                
            self.log("セッションクリーンアップ完了")
            
        except Exception as e:
            self.log(f"クリーンアップエラー: {e}", "error")
