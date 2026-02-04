# -*- coding: utf-8 -*-
"""
状態管理クラス - アプリケーション全体の状態を一元管理
"""

import threading
import time
import queue
from typing import Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field

from enum import Enum
from core.models.progress_bar import ProgressBar, ProgressBarSnapshot

# ====== 追加: AppState Enum定義 ======
class AppState(Enum):
    IDLE = 'idle'
    RUNNING = 'running'
    PAUSED = 'paused'
    ERROR = 'error'

# ====== 追加: DownloadState dataclass定義 ======
@dataclass
class DownloadState:
    url_status: Dict[str, str] = field(default_factory=dict)
    progress_bars: Dict[int, ProgressBar] = field(default_factory=dict)
    is_running: bool = False
    paused: bool = False
    pause_requested: bool = False
    current_url_index: int = 0
    total_urls: int = 0
    current_progress: int = 0
    current_total: int = 0
    url_incomplete_flags: Dict[str, bool] = field(default_factory=dict)
    elapsed_time_timer_id: Optional[int] = None
    elapsed_time_start: Optional[float] = None
    elapsed_time_paused_start: Optional[float] = None
    total_elapsed_seconds: float = 0.0
    total_paused_time: float = 0.0
    resume_points: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    current_resume_point_url: Optional[str] = None
    skip_requested_url: Optional[str] = None
    restart_requested_url: Optional[str] = None
    current_gallery_url: Optional[str] = None

class StateManager:
    """アプリケーション全体の状態を管理するクラス（Observerパターン実装）"""

    def __init__(self):
        # 状態の初期化
        self.app_state = AppState.IDLE
        self.download_state = DownloadState()
        self.thread_state = ThreadState()
        self.network_state = NetworkState()

        # ⭐ ロックを削除、メッセージキューに変更 ⭐
        self._message_queue = queue.Queue()
        self._state_lock = threading.Lock()  # 高速読み取り用（最小限）

        # 状態変更の通知用
        # self.state_listeners: Dict[str, list] = {}
        self.state_listeners = {}

        # ⭐Phase 2: Observerパターン実装⭐
        # self._observers: list = []  # GUIオブザーバーのリスト
        self._observers = []
        self._observer_lock = threading.Lock()  # オブザーバー登録用ロック

        # ⭐追加: DownloadListControllerへの参照（DLリスト背景色更新用）⭐
        self.download_list_controller = None  # main.pyで設定される

        # ⭐Phase 2: DownloadSessionRepository統合⭐
        from core.models.download_session import DownloadSessionRepository
        self.session_repository = DownloadSessionRepository()

        # イベント処理スレッドを開始
    elapsed_time_timer_id: Optional[int] = None
    elapsed_time_start: Optional[float] = None
    elapsed_time_paused_start: Optional[float] = None
    total_elapsed_seconds: float = 0.0
    total_paused_time: float = 0.0
    # ⭐追加: 再開ポイント管理を一元化⭐
    resume_points: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # {url: resume_data}
    current_resume_point_url: Optional[str] = None
    # ⭐追加: スキップ・リスタート要求を一元管理⭐
    skip_requested_url: Optional[str] = None
    restart_requested_url: Optional[str] = None

@dataclass
class ThreadState:
    """スレッド関連の状態"""
    current_thread_id: Optional[int] = None
    download_thread: Optional[threading.Thread] = None
    stop_flag: threading.Event = field(default_factory=threading.Event)
    skip_flag: threading.Event = field(default_factory=threading.Event)  # ⭐追加: スキップ専用フラグ⭐

@dataclass
class NetworkState:
    """ネットワーク関連の状態"""
    session: Optional[Any] = None
    ssl_settings_applied: bool = False
    network_retry_count: int = 0

from gui.components.download_list_model import DownloadStatus

class StateManager:
    def get_total_url_count(self) -> int:
        """DLリストWidgetの総URL数を返す（存在しない場合は従来のtotal_urls）"""
        try:
            # DownloadListWidgetがあればそちらを優先
            if hasattr(self, 'download_list_controller') and self.download_list_controller:
                # download_list_controllerはDownloadListControllerインスタンス
                return self.download_list_controller.get_total_count()
            # fallback: download_state.total_urls
            return self.get_total_urls()
        except Exception:
            return self.get_total_urls()

    def get_completed_url_count(self) -> int:
        """DLリストWidgetの完了URL数を返す（存在しない場合は従来のcompleted数）"""
        try:
            if hasattr(self, 'download_list_controller') and self.download_list_controller:
                return self.download_list_controller.get_completed_count()
            # fallback: download_state.url_status
            with self._state_lock:
                return sum(1 for status in self.download_state.url_status.values()
                            if str(status) in ("completed", "skipped"))
        except Exception:
            with self._state_lock:
                return sum(1 for status in self.download_state.url_status.values()
                            if str(status) in ("completed", "skipped"))
            
    """アプリケーション全体の状態を管理するクラス（Observerパターン実装）"""

    def __init__(self) -> None:
        # 状態の初期化
        self.app_state = AppState.IDLE
        self.download_state = DownloadState()
        self.thread_state = ThreadState()
        self.network_state = NetworkState()
        
        # ⭐ ロックを削除、メッセージキューに変更 ⭐
        self._message_queue = queue.Queue()
        self._state_lock = threading.Lock()  # 高速読み取り用（最小限）
        
        # 状態変更の通知用
        self.state_listeners: Dict[str, list] = {}
        
        # ⭐Phase 2: Observerパターン実装⭐
        self._observers: list = []  # GUIオブザーバーのリスト
        self._observer_lock = threading.Lock()  # オブザーバー登録用ロック
        
        # ⭐追加: DownloadListControllerへの参照（DLリスト背景色更新用）⭐
        self.download_list_controller = None  # main.pyで設定される
        
        # ⭐Phase 2: DownloadSessionRepository統合⭐
        from core.models.download_session import DownloadSessionRepository
        self.session_repository = DownloadSessionRepository()
    
        # イベント処理スレッドを開始
        self._event_thread = None
        self._stop_event = threading.Event()
        self._start_event_thread()
    
    def _start_event_thread(self) -> None:
        """イベント処理スレッドを開始（GUI非依存）"""
        def event_worker():
            """イベント処理ワーカー"""
            while not self._stop_event.is_set():
                try:
                    message = self._message_queue.get(timeout=0.1)
                    self._handle_message(message)
                    self._message_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"StateManager event error: {e}")
        
        self._event_thread = threading.Thread(
            target=event_worker,
            daemon=True,
            name="StateManagerEventThread"
        )
        self._event_thread.start()
    
    def post_message(self, msg_type: str, data: dict):
        """
        メッセージをキューに投稿（非同期処理）
        
        Args:
            msg_type: メッセージタイプ
            data: メッセージデータ
        """
        try:
            message = {
                'type': msg_type,
                'data': data,
                'timestamp': time.time()
            }
            self._message_queue.put(message)
        except Exception as e:
            print(f"StateManager post_message error: {e}")
    
    # ============================================
    # ⭐Phase 2: Observerパターン実装⭐
    # ============================================
    
    def attach_observer(self, observer: Any) -> None:
        """
        オブザーバーを登録（GUI層から呼び出される）
        
        Args:
            observer: on_progress_updated(url_index, data) メソッドを持つオブジェクト
        """
        with self._observer_lock:
            if observer not in self._observers:
                self._observers.append(observer)
    
    def detach_observer(self, observer: Any) -> None:
        """オブザーバーの登録解除"""
        with self._observer_lock:
            if observer in self._observers:
                self._observers.remove(observer)
    
    def _notify_observers(self, event_type: str, data: dict):
        """
        全オブザーバーに状態変更を通知
        
        Args:
            event_type: イベントタイプ（'progress_updated', 'status_changed'など）
            data: イベントデータ
        """
        with self._observer_lock:
            observers_copy = self._observers.copy()
        
        # ⭐DEBUG: Observer通知のログ（頻度制限）⭐
        if event_type == 'progress_updated':
            url_index = data.get('url_index', -1)
            if url_index % 10 == 0 or url_index <= 1:
                print(f"[DEBUG] Observer通知: event={event_type}, url_index={url_index}, observers={len(observers_copy)}, current={data.get('current')}/{data.get('total')}")
        
        for observer in observers_copy:
            try:
                # オブザーバーのメソッドを呼び出す
                if event_type == 'progress_updated' and hasattr(observer, 'on_progress_updated'):
                    observer.on_progress_updated(data.get('url_index'), data)
                elif event_type == 'status_changed' and hasattr(observer, 'on_status_changed'):
                    observer.on_status_changed(data)
            except Exception as e:
                print(f"Observer notification error: {e}")
    
    def post_message(self, msg_type: str, data: dict):
        """
        メッセージをキューに投稿（非同期処理）
        
        Args:
            msg_type: メッセージタイプ
            data: メッセージデータ
        """
        try:
            message = {
                'type': msg_type,
                'data': data,
                'timestamp': time.time()
            }
            self._message_queue.put(message)
        except Exception as e:
            print(f"StateManager post_message error: {e}")
    
    def remove_progress_bar(self, url_index: int):
        """
        指定されたURL番号のプログレスバーを削除
        
        Args:
            url_index: 削除するプログレスバーのURL番号
        """
        self.post_message('remove_progress_bar', {'url_index': url_index})
    
    def _handle_message(self, message: Dict[str, Any]) -> None:
        """メッセージを処理（専用スレッドで実行、ロック不要）"""
        msg_type = message.get('type')
        data = message.get('data', {})
        old_value = message.get('old_value')
        
        # ⭐ 状態を更新（専用スレッドでのみ実行、ロック不要）⭐
        if msg_type == 'set_app_state':
            old_state = self.app_state
            self.app_state = data['state']
            self._notify_state_change('app_state', data['state'], old_state)
        
        elif msg_type == 'remove_progress_bar':
            url_index = data['url_index']
            if url_index in self.download_state.progress_bars:
                del self.download_state.progress_bars[url_index]
                self._notify_state_change('progress_bar_removed', {'url_index': url_index})
        
        elif msg_type == 'set_url_status':
            url = data['url']
            status = data['status']
            # Enum変換
            if not isinstance(status, DownloadStatus):
                try:
                    status = DownloadStatus(status)
                except Exception:
                    raise ValueError(f"Invalid status: {status}")
            current_status = self.download_state.url_status.get(url)
            if current_status == status:
                return  # 重複処理を防止
            self.download_state.url_status[url] = status
            self._notify_state_change('url_status', {url: status})
            # DownloadListControllerに通知
            if self.download_list_controller:
                try:
                    print(f"[DEBUG] StateManager: DLリスト更新通知 - URL: {url[:80]}, status: {status}")
                    self.download_list_controller.update_item(url, status=status)
                except Exception as e:
                    print(f"[WARNING] StateManager: DownloadListController通知エラー（メッセージハンドラ）: {e}")
                    import traceback
                    traceback.print_exc()
        
        elif msg_type == 'set_download_running':
            running = data['running']
            self.download_state.is_running = running
            if running:
                self.app_state = AppState.RUNNING
            else:
                self.app_state = AppState.IDLE
            self._notify_state_change('download_running', running)
        
        elif msg_type == 'set_paused':
            paused = data['paused']
            timestamp = data.get('timestamp', time.time())
            
            # ⭐追加: 中断時間管理⭐
            if paused:
                # 中断開始: 現在時刻を記録
                self.download_state.elapsed_time_paused_start = timestamp
                print(f"[中断] 中断開始: {timestamp}")
                
                # ⭐追加: 各URLのstatusを「一時停止」に変更⭐
                for url_index, progress_bar in self.download_state.progress_bars.items():
                    if isinstance(progress_bar, dict):
                        if 'state' not in progress_bar:
                            progress_bar['state'] = {}
                        current_status = progress_bar['state'].get('status', '')
                        # 既に終了状態でない場合のみ更新
                        if '完了' not in current_status and 'エラー' not in current_status and 'スキップ' not in current_status:
                            progress_bar['state']['status'] = '一時停止'
                            print(f"[中断] url_index={url_index}: status='{current_status}'→'一時停止'")
                            # Observer通知
                            self._notify_observers('progress_updated', {
                                'url_index': url_index,
                                'status': '一時停止',
                                'current': progress_bar['state'].get('current', 0),
                                'total': progress_bar['state'].get('total', 0),
                                'title': progress_bar['state'].get('title', ''),
                                'url': progress_bar.get('url', '')
                            })
                    elif hasattr(progress_bar, 'status'):
                        current_status = progress_bar.status
                        if '完了' not in current_status and 'エラー' not in current_status and 'スキップ' not in current_status:
                            progress_bar.status = '一時停止'
            else:
                # 中断終了: 中断時間を累積
                if self.download_state.elapsed_time_paused_start:
                    paused_interval = timestamp - self.download_state.elapsed_time_paused_start
                    print(f"[中断] 中断終了: 中断時間={paused_interval:.2f}秒")
                    
                    # ⭐全てのprogress_barのpaused_durationを更新⭐
                    for url_index, progress_bar in self.download_state.progress_bars.items():
                        if isinstance(progress_bar, dict):
                            current_paused = progress_bar.get('paused_duration', 0.0)
                            if current_paused is None:
                                current_paused = 0.0
                            progress_bar['paused_duration'] = current_paused + paused_interval
                            print(f"[中断] url_index={url_index}: paused_duration更新 {current_paused:.2f}→{progress_bar['paused_duration']:.2f}秒")
                            
                            # ⭐追加: statusを「ダウンロード中」に戻す⭐
                            if 'state' in progress_bar and progress_bar['state'].get('status') == '一時停止':
                                progress_bar['state']['status'] = 'ダウンロード中'
                                print(f"[中断] url_index={url_index}: status='一時停止'→'ダウンロード中'")
                                # Observer通知
                                self._notify_observers('progress_updated', {
                                    'url_index': url_index,
                                    'status': 'ダウンロード中',
                                    'current': progress_bar['state'].get('current', 0),
                                    'total': progress_bar['state'].get('total', 0),
                                    'title': progress_bar['state'].get('title', ''),
                                    'url': progress_bar.get('url', '')
                                })
                        elif hasattr(progress_bar, 'paused_duration'):
                            progress_bar.paused_duration += paused_interval
                            if progress_bar.status == '一時停止':
                                progress_bar.status = 'ダウンロード中'
                    
                    # グローバルな中断時間も更新
                    self.download_state.total_paused_time += paused_interval
                    self.download_state.elapsed_time_paused_start = None
            
            self.download_state.paused = paused
            if paused and self.download_state.is_running:
                self.app_state = AppState.PAUSED
            elif self.download_state.is_running:
                self.app_state = AppState.RUNNING
            self._notify_state_change('paused', paused)
        
        elif msg_type == 'set_pause_requested':
            self.download_state.pause_requested = data['requested']
            self._notify_state_change('pause_requested', data['requested'])
        
        elif msg_type == 'set_current_url_index':
            self.download_state.current_url_index = data['index']
            self._notify_state_change('current_url_index', data['index'])
        
        elif msg_type == 'set_total_urls':
            self.download_state.total_urls = data['total']
            self._notify_state_change('total_urls', data['total'])
        
        elif msg_type == 'set_current_gallery_url':
            self.download_state.current_gallery_url = data['url']
            self._notify_state_change('current_gallery_url', data['url'])
        
        elif msg_type == 'set_progress':
            self.download_state.current_progress = data['current']
            self.download_state.current_total = data['total']
            self._notify_state_change('progress', {'current': data['current'], 'total': data['total']})
        
        elif msg_type == 'set_url_incomplete_flag':
            url = data['url']
            incomplete = data['incomplete']
            self.download_state.url_incomplete_flags[url] = incomplete
            self._notify_state_change('url_incomplete_flag', {url: incomplete})
        
        elif msg_type == 'set_session':
            self.network_state.session = data['session']
            self._notify_state_change('session', data['session'])
        
        elif msg_type == 'set_ssl_settings_applied':
            self.network_state.ssl_settings_applied = data['applied']
            self._notify_state_change('ssl_settings_applied', data['applied'])
        
        elif msg_type == 'set_progress_bar':
            # ⭐変更: ProgressBarオブジェクトとして保存⭐
            url_index = data['url_index']
            progress_bar = data['progress_bar']  # ProgressBarインスタンス
            is_new = url_index not in self.download_state.progress_bars
            self.download_state.progress_bars[url_index] = progress_bar
            if is_new:
                self._notify_state_change('progress_bar_created', {'url_index': url_index, 'progress_bar': progress_bar})
            else:
                self._notify_state_change('progress_bar_update', {'url_index': url_index})
        
        elif msg_type == 'update_progress_bar_state':
            # ⭐修正: ProgressBarオブジェクトと辞書の両方に対応⭐
            url_index = data['url_index']
            current = data.get('current')
            total = data.get('total')
            title = data.get('title')
            status = data.get('status')
            download_range_info = data.get('download_range_info')
            start_time = data.get('start_time')  # ⭐追加: 開始時刻⭐
            paused_duration = data.get('paused_duration')  # ⭐追加: 累積中断時間⭐
            
            # ⭐DEBUG: プログレスバー更新のログ⭐
            print(f"[DEBUG] StateManager._handle_message(update_progress_bar_state): url_index={url_index}, current={current}/{total}, status={status}, exists={url_index in self.download_state.progress_bars}")
            
            # ⭐Phase 2: DownloadSessionを更新⭐
            from core.models.download_session import DownloadSession, DownloadRangeInfo
            session = self.session_repository.get(url_index)
            if session:
                # 絶対ページ数を更新
                if current is not None:
                    session.update_progress(current, total)
                
                # タイトルを更新
                if title is not None:
                    session.title = title
                
                # ダウンロード範囲を更新
                if download_range_info is not None:
                    range_info = DownloadRangeInfo(
                        enabled=download_range_info.get('enabled', False),
                        start=download_range_info.get('start_page', 1),
                        end=download_range_info.get('end_page')
                    )
                    session.update_relative_pages(range_info)
                
                # リポジトリに保存
                self.session_repository.set(session)
            
            if url_index in self.download_state.progress_bars:
                progress_bar = self.download_state.progress_bars[url_index]
                
                # ⭐型チェック: ProgressBarオブジェクトか辞書か⭐
                if hasattr(progress_bar, 'update_progress'):
                    # ProgressBarオブジェクトの場合
                    if current is not None or total is not None:
                        progress_bar.update_progress(
                            current=current if current is not None else progress_bar.current,
                            total=total
                        )
                    if title is not None:
                        progress_bar.set_title(title)
                    if status is not None:
                        progress_bar.set_status(status)
                    if download_range_info is not None:
                        progress_bar.download_range_info = download_range_info
                    
                    # ⭐Phase 2: オブザーバーに通知⭐
                    self._notify_observers('progress_updated', {
                        'url_index': url_index,
                        'current': progress_bar.current,
                        'total': progress_bar.total,
                        'title': progress_bar.title,
                        'status': progress_bar.status,
                        'download_range_info': progress_bar.download_range_info,
                        'url': progress_bar.url
                    })
                elif isinstance(progress_bar, dict):
                    # 辞書の場合（後方互換性）
                    if 'state' not in progress_bar:
                        progress_bar['state'] = {}
                    if current is not None:
                        progress_bar['state']['current'] = current
                    if total is not None and total > 0:
                        progress_bar['state']['total'] = total
                    if title is not None:
                        progress_bar['state']['title'] = title
                    if status is not None:
                        progress_bar['state']['status'] = status
                    if download_range_info is not None:
                        progress_bar['download_range_info'] = download_range_info
                    # ⭐追加: start_timeとpaused_durationの更新⭐
                    if start_time is not None:
                        progress_bar['start_time'] = start_time
                        print(f"[DEBUG] start_time更新: url_index={url_index}, start_time={start_time}")
                    if paused_duration is not None:
                        progress_bar['paused_duration'] = paused_duration
                        print(f"[DEBUG] paused_duration更新: url_index={url_index}, paused_duration={paused_duration}秒")
                    
                    # ⭐追加: 辞書形式でもオブザーバーに通知⭐
                    self._notify_observers('progress_updated', {
                        'url_index': url_index,
                        'current': progress_bar['state'].get('current', 0),
                        'total': progress_bar['state'].get('total', 0),
                        'title': progress_bar['state'].get('title', ''),
                        'status': progress_bar['state'].get('status', ''),
                        'download_range_info': progress_bar.get('download_range_info'),
                        'url': progress_bar.get('url', '')
                    })
                else:
                    print(f"[ERROR] Unknown progress_bar type: {type(progress_bar)}")
                    return
                
                self._notify_state_change('progress_bar_update', {'url_index': url_index})
            else:
                # プログレスバーが存在しない場合もログ出力し、通知を試みる
                print(f"[WARNING] ProgressBar not found for url_index={url_index}")
                # ⭐追加: プログレスバーが存在しない場合も通知（初回生成トリガー用）⭐
                if current is not None and total is not None:
                    self._notify_observers('progress_updated', {
                        'url_index': url_index,
                        'current': current,
                        'total': total,
                        'title': title or '準備中...',
                        'status': status or '待機中',
                        'download_range_info': download_range_info,
                        'url': ''
                    })
        
        elif msg_type == 'set_elapsed_time_timer_id':
            self.download_state.elapsed_time_timer_id = data['timer_id']
            self._notify_state_change('elapsed_time_timer_id', data['timer_id'])
        
        elif msg_type == 'set_elapsed_time_start':
            self.download_state.elapsed_time_start = data['start_time']
            self._notify_state_change('elapsed_time_start', data['start_time'])
        
        elif msg_type == 'set_elapsed_time_paused_start':
            self.download_state.elapsed_time_paused_start = data['paused_start']
            self._notify_state_change('elapsed_time_paused_start', data['paused_start'])
        
        elif msg_type == 'add_elapsed_time':
            self.download_state.total_elapsed_seconds += data['seconds']
            self._notify_state_change('total_elapsed_seconds', self.download_state.total_elapsed_seconds)
        
        elif msg_type == 'add_paused_time':
            self.download_state.total_paused_time += data['seconds']
            self._notify_state_change('total_paused_time', self.download_state.total_paused_time)
        
        elif msg_type == 'reset_elapsed_time':
            self.download_state.elapsed_time_start = None
            self.download_state.elapsed_time_paused_start = None
            self.download_state.total_elapsed_seconds = 0.0
            self.download_state.total_paused_time = 0.0
            self._notify_state_change('elapsed_time_reset', None)
        
        elif msg_type == 'set_current_thread_id':
            self.thread_state.current_thread_id = data['thread_id']
            self._notify_state_change('current_thread_id', data['thread_id'])
        
        elif msg_type == 'set_resume_point':
            url = data['url']
            resume_data = data['resume_data']
            self.download_state.resume_points[url] = resume_data
            self.download_state.current_resume_point_url = url
            self._notify_state_change('resume_point', {url: resume_data})
        
        elif msg_type == 'clear_resume_point':
            url = data.get('url')
            if url:
                if url in self.download_state.resume_points:
                    del self.download_state.resume_points[url]
                if self.download_state.current_resume_point_url == url:
                    self.download_state.current_resume_point_url = None
            else:
                # urlが指定されていない場合は全てクリア
                self.download_state.resume_points.clear()
                self.download_state.current_resume_point_url = None
            self._notify_state_change('resume_point_cleared', url)
        
        elif msg_type == 'set_skip_requested_url':
            self.download_state.skip_requested_url = data.get('url')
            self._notify_state_change('skip_requested_url', data.get('url'))
        
        elif msg_type == 'set_restart_requested_url':
            self.download_state.restart_requested_url = data.get('url')
            self._notify_state_change('restart_requested_url', data.get('url'))
        
        elif msg_type == 'set_url_download_range':
            # URL単位のダウンロード範囲を設定
            if not hasattr(self.download_state, '_url_download_ranges'):
                self.download_state._url_download_ranges = {}
            
            url = data['url']
            start = data.get('start')
            end = data.get('end')
            
            if start is not None:
                self.download_state._url_download_ranges[url] = {
                    'start': start,
                    'end': end,
                    'enabled': True
                }
            else:
                self.download_state._url_download_ranges[url] = {
                    'enabled': False
                }
            self._notify_state_change('url_download_range', {url: self.download_state._url_download_ranges[url]})
        
        elif msg_type == 'clear_url_download_range':
            # URL単位のダウンロード範囲をクリア
            if hasattr(self.download_state, '_url_download_ranges'):
                url = data['url']
                if url in self.download_state._url_download_ranges:
                    del self.download_state._url_download_ranges[url]
                    self._notify_state_change('url_download_range_cleared', url)
        
        elif msg_type == 'clear_all_url_download_ranges':
            # 全URLのダウンロード範囲をクリア
            if hasattr(self.download_state, '_url_download_ranges'):
                self.download_state._url_download_ranges.clear()
                self._notify_state_change('all_url_download_ranges_cleared', None)
        
        elif msg_type == 'set_url_applied_range':
            # URL単位の適用されたダウンロード範囲を記録
            if not hasattr(self.download_state, '_url_applied_ranges'):
                self.download_state._url_applied_ranges = {}
            
            url = data['url']
            applied_range = data['applied_range']
            self.download_state._url_applied_ranges[url] = applied_range
            self._notify_state_change('url_applied_range', {url: applied_range})
        
        elif msg_type == 'clear_url_applied_range':
            # URL単位の適用されたダウンロード範囲をクリア
            if hasattr(self.download_state, '_url_applied_ranges'):
                url = data['url']
                if url in self.download_state._url_applied_ranges:
                    del self.download_state._url_applied_ranges[url]
                    self._notify_state_change('url_applied_range_cleared', url)
        
        elif msg_type == 'reset_all_states':
            self.app_state = AppState.IDLE
            self.download_state = DownloadState()
            self.thread_state = ThreadState()
            self.network_state = NetworkState()
            self._notify_state_change('reset_all', None)
    
    def set_app_state(self, state: AppState):
        """アプリケーション状態を設定（ロック不要）"""
        old_state = self.app_state
        self._message_queue.put({
            'type': 'set_app_state',
            'data': {'state': state},
            'old_value': old_state
        })
    
    def get_app_state(self) -> AppState:
        """アプリケーション状態を取得（高速読み取り用）"""
        with self._state_lock:
            return self.app_state
    
    def set_download_running(self, running: bool):
        """ダウンロード実行状態を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_download_running',
            'data': {'running': running}
        })
    
    def is_download_running(self) -> bool:
        """ダウンロード実行状態を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.is_running
    
    def is_download_running_unsafe(self) -> bool:
        """ダウンロード実行状態を取得（ロックなし、高速）"""
        return self.download_state.is_running
    
    def set_paused(self, paused: bool):
        """一時停止状態を設定（ロック不要）
        
        ⭐追加: 中断時間を自動管理⭐
        """
        self._message_queue.put({
            'type': 'set_paused',
            'data': {'paused': paused, 'timestamp': time.time()}  # ⭐追加: timestamp⭐
        })
    
    def is_paused(self) -> bool:
        """一時停止状態を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.paused
    
    def is_paused_unsafe(self) -> bool:
        """一時停止状態を取得（ロックなし、高速）"""
        return self.download_state.paused
    
    def set_pause_requested(self, requested: bool):
        """中断要求状態を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_pause_requested',
            'data': {'requested': requested}
        })
    
    def is_pause_requested(self) -> bool:
        """中断要求状態を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.pause_requested
    
    def is_pause_requested_unsafe(self) -> bool:
        """中断要求状態を取得（ロックなし、高速）"""
        return self.download_state.pause_requested
    
    def set_current_url_index(self, index: int):
        """現在のURLインデックスを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_current_url_index',
            'data': {'index': index}
        })
    
    def get_current_url_index(self) -> int:
        """現在のURLインデックスを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.current_url_index
    
    def get_current_url_index_unsafe(self) -> int:
        """現在のURLインデックスを取得（ロックなし、高速）"""
        return self.download_state.current_url_index
    
    def set_total_urls(self, total: int):
        """URL総数を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_total_urls',
            'data': {'total': total}
        })
    
    def get_total_urls(self) -> int:
        """URL総数を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.total_urls
    
    def set_url_status(self, url: str, status: Union[str, DownloadStatus]):
        """URLの状態を設定（DownloadStatus Enum基準、ロック不要）"""
        # Enum変換
        if not isinstance(status, DownloadStatus):
            try:
                status = DownloadStatus(status)
            except Exception:
                raise ValueError(f"Invalid status: {status}")
        current_status = self.download_state.url_status.get(url)
        if current_status == status:
            return  # 変更なしならスキップ
        self._message_queue.put({
            'type': 'set_url_status',
            'data': {'url': url, 'status': status}
        })
        # DownloadSessionの状態もEnumで更新
        url_index = self.get_url_index_by_url(url)
        if url_index is not None:
            session = self.session_repository.get(url_index)
            if session:
                if status == DownloadStatus.COMPLETED:
                    session.complete()
                elif status == DownloadStatus.ERROR:
                    session.mark_error("ダウンロードエラー")
                elif status == DownloadStatus.SKIPPED:
                    session.skip()
                elif status == DownloadStatus.DOWNLOADING:
                    if session.status != DownloadStatus.DOWNLOADING:
                        session.status = DownloadStatus.DOWNLOADING
                elif status == DownloadStatus.PAUSED:
                    session.pause()
                self.session_repository.set(session)
    
    def get_url_status(self, url: str) -> DownloadStatus:
        """URLの状態を取得（DownloadStatus Enum、なければPENDING）"""
        with self._state_lock:
            status = self.download_state.url_status.get(url, DownloadStatus.PENDING)
            if not isinstance(status, DownloadStatus):
                try:
                    status = DownloadStatus(status)
                except Exception:
                    status = DownloadStatus.PENDING
            return status
    
    def get_url_status_unsafe(self, url: str) -> DownloadStatus:
        """URLの状態を取得（ロックなし、高速、Enum）"""
        status = self.download_state.url_status.get(url, DownloadStatus.PENDING)
        if not isinstance(status, DownloadStatus):
            try:
                status = DownloadStatus(status)
            except Exception:
                status = DownloadStatus.PENDING
        return status
    
    def get_completed_url_count(self) -> int:
        """完了済みURLの数を取得（COMPLETED と SKIPPED を含む、高速読み取り用）"""
        with self._state_lock:
            return sum(1 for status in self.download_state.url_status.values() 
                      if status in [DownloadStatus.COMPLETED, DownloadStatus.SKIPPED])
    
    def get_error_url_count(self) -> int:
        """エラー状態のURLの数を取得（高速読み取り用）"""
        with self._state_lock:
            return sum(1 for status in self.download_state.url_status.values() 
                      if status == "error")
    
    def get_error_urls(self) -> list:
        """エラー状態のURLのリストを取得（高速読み取り用）"""
        with self._state_lock:
            return [url for url, status in self.download_state.url_status.items() 
                   if status == 'error']
    
    def get_completed_urls(self) -> list:
        """完了済みURLのリストを取得（高速読み取り用）"""
        with self._state_lock:
            return [url for url, status in self.download_state.url_status.items() 
                   if status == "completed"]
    
    def get_all_url_statuses(self) -> dict:
        """すべてのURLステータスを取得（コピーを返す、高速読み取り用）"""
        with self._state_lock:
            return self.download_state.url_status.copy()
    
    def set_url_incomplete_flag(self, url: str, incomplete: bool):
        """URLのincompleteフラグを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_url_incomplete_flag',
            'data': {'url': url, 'incomplete': incomplete}
        })
    
    def get_url_incomplete_flag(self, url: str) -> bool:
        """URLのincompleteフラグを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.url_incomplete_flags.get(url, False)
    
    def get_url_incomplete_flag_unsafe(self, url: str) -> bool:
        """URLのincompleteフラグを取得（ロックなし、高速）"""
        return self.download_state.url_incomplete_flags.get(url, False)
    
    def is_download_actually_completed(self, url: str) -> bool:
        """ダウンロードが実際に完了しているかチェック（高速読み取り用）"""
        with self._state_lock:
            status = self.download_state.url_status.get(url, 'pending')
            incomplete = self.download_state.url_incomplete_flags.get(url, False)
            # ステータスがcompletedで、incompleteフラグがFalseの場合のみ真の完了
            return status == 'completed' and not incomplete
    
    def set_current_gallery_url(self, url: str):
        """現在のギャラリーURLを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_current_gallery_url',
            'data': {'url': url}
        })
    
    def get_current_gallery_url(self) -> str:
        """現在のギャラリーURLを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.current_gallery_url
    
    def set_progress(self, current: int, total: int):
        """進捗を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_progress',
            'data': {'current': current, 'total': total}
        })
    
    def get_progress(self) -> tuple[int, int]:
        """進捗を取得（高速読み取り用）"""
        with self._state_lock:
            return (self.download_state.current_progress, self.download_state.current_total)
    
    def set_session(self, session: Any) -> None:
        """セッションを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_session',
            'data': {'session': session}
        })
    
    def get_session(self) -> Optional[Any]:
        """セッションを取得（高速読み取り用）"""
        with self._state_lock:
            return self.network_state.session
    
    def set_ssl_settings_applied(self, applied: bool):
        """SSL設定適用状態を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_ssl_settings_applied',
            'data': {'applied': applied}
        })
    
    def is_ssl_settings_applied(self) -> bool:
        """SSL設定適用状態を取得（高速読み取り用）"""
        with self._state_lock:
            return self.network_state.ssl_settings_applied
    
    def set_download_thread(self, thread: Optional[Any]) -> None:
        """ダウンロードスレッド/Futureを設定
        
        Args:
            thread: threading.Thread または concurrent.futures.Future オブジェクト
        """
        self.thread_state.download_thread = thread
        if thread:
            # Futureの場合はthread.identが存在しないため、チェック
            if hasattr(thread, 'ident'):
                self.thread_state.current_thread_id = thread.ident
            # Futureの場合はスレッドIDを設定しない（実行開始後にdownloader側で設定される）
        else:
            self.thread_state.current_thread_id = None
        self._notify_state_change('download_thread', thread)
    
    def get_download_thread(self) -> Optional[Any]:
        """ダウンロードスレッド/Futureを取得
        
        Returns:
            threading.Thread または concurrent.futures.Future または None
        """
        return self.thread_state.download_thread
    
    def get_current_thread_id(self) -> Optional[int]:
        """現在のスレッドIDを取得（高速読み取り用）"""
        with self._state_lock:
            return self.thread_state.current_thread_id
    
    def set_current_thread_id(self, thread_id: Optional[int]):
        """現在のスレッドIDを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_current_thread_id',
            'data': {'thread_id': thread_id}
        })
    
    def get_stop_flag(self) -> threading.Event:
        """停止フラグを取得"""
        return self.thread_state.stop_flag
    
    def reset_stop_flag(self) -> None:
        """停止フラグをリセット"""
        self.thread_state.stop_flag.clear()
    
    def set_stop_flag(self) -> None:
        """停止フラグを設定"""
        self.thread_state.stop_flag.set()
    
    # ⭐追加: スキップフラグ管理メソッド⭐
    def get_skip_flag(self) -> threading.Event:
        """スキップフラグを取得"""
        return self.thread_state.skip_flag
    
    def reset_skip_flag(self) -> None:
        """スキップフラグをリセット"""
        self.thread_state.skip_flag.clear()
    
    def set_skip_flag(self) -> None:
        """スキップフラグを設定（停止フラグとは独立）"""
        self.thread_state.skip_flag.set()
    
    def is_skip_requested(self) -> bool:
        """スキップ要求があるか（高速チェック用）"""
        return self.thread_state.skip_flag.is_set()
    
    # ⭐追加: 再開ポイント管理メソッド⭐
    def get_resume_point(self, url: str) -> Optional[Dict[str, Any]]:
        """再開ポイント情報を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.resume_points.get(url)
    
    def set_resume_point(self, url: str, resume_data: Dict[str, Any]):
        """再開ポイント情報を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_resume_point',
            'data': {'url': url, 'resume_data': resume_data}
        })
    
    def clear_resume_point(self, url: Optional[str] = None):
        """再開ポイント情報をクリア（ロック不要）"""
        self._message_queue.put({
            'type': 'clear_resume_point',
            'data': {'url': url}
        })
    
    def get_current_resume_point_url(self) -> Optional[str]:
        """現在の再開ポイントURLを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.current_resume_point_url
    
    def add_state_listener(self, state_name: str, callback: Callable):
        """状態変更のリスナーを追加"""
        if state_name not in self.state_listeners:
            self.state_listeners[state_name] = []
        self.state_listeners[state_name].append(callback)
    
    def remove_state_listener(self, state_name: str, callback: Callable):
        """状態変更のリスナーを削除"""
        if state_name in self.state_listeners:
            try:
                self.state_listeners[state_name].remove(callback)
            except ValueError:
                pass
    
    def _notify_state_change(self, state_name: str, new_value: Any, old_value: Any = None):
        """状態変更を通知（イベント駆動型GUI更新）"""
        if state_name in self.state_listeners:
            for callback in self.state_listeners[state_name]:
                try:
                    if callable(callback):
                        import inspect
                        sig = inspect.signature(callback)
                        param_count = len(sig.parameters)

                        if param_count == 0:
                            # 引数なしコールバック
                            callback()
                        elif param_count == 1:
                            # 新しい値のみを受け取るコールバック
                            callback(new_value)
                        elif param_count == 2:
                            # 新旧値を受け取るコールバック
                            callback(new_value, old_value)
                        else:
                            # 状態名と値を辞書で渡す
                            callback({
                                'state_name': state_name,
                                'new_value': new_value,
                                'old_value': old_value
                            })
                except Exception as e:
                    print(f"State listener error: {e}")

    def reset_all_states(self) -> None:
        """全ての状態をリセット（ロック不要）"""
        self._message_queue.put({
            'type': 'reset_all_states',
            'data': {}
        })
    
    # ⭐新規: プログレスバー管理の型安全なAPIメソッド⭐
    def create_progress_bar(self, url: str, url_index: int) -> ProgressBar:
        """プログレスバーを新規作成（冪等性保証）
        
        ⭐Phase 2: DownloadSessionとの統合⭐
        - ProgressBarとDownloadSessionを同時に作成
        - DownloadSessionをリポジトリに保存
        
        Args:
            url: ダウンロード対象URL
            url_index: URL配列内のインデックス
            
        Returns:
            作成されたProgressBarインスタンス
        """
        with self._state_lock:
            # 既存のProgressBarがあればそれを返す（冪等性）
            if url_index in self.download_state.progress_bars:
                return self.download_state.progress_bars[url_index]
        
        # ⭐追加: DownloadSessionを作成⭐
        from core.models.download_session import DownloadSession
        session = DownloadSession(
            url_index=url_index,
            url=url,
            title="準備中...",
            save_folder=""
        )
        session.start()  # 開始時刻を設定
        
        # リポジトリに保存
        self.session_repository.set(session)
        
        # 新規作成（既存互換性のため）
        progress_bar = ProgressBar(
            url=url,
            url_index=url_index
        )
        
        # メッセージキューに投稿（非同期）
        self._message_queue.put({
            'type': 'set_progress_bar',
            'data': {'url_index': url_index, 'progress_bar': progress_bar}
        })
        
        return progress_bar
    
    def ensure_progress_bar(self, url: str, url_index: int) -> ProgressBar:
        """プログレスバーの存在を保証（なければ作成）
        
        Args:
            url: ダウンロード対象URL
            url_index: URL配列内のインデックス
            
        Returns:
            ProgressBarインスタンス
        """
        return self.create_progress_bar(url, url_index)
    
    def get_progress_bar_typed(self, url_index: int) -> Optional[ProgressBar]:
        """型安全なプログレスバー取得
        
        Args:
            url_index: URL配列内のインデックス
            
        Returns:
            ProgressBarインスタンス（存在しない場合はNone）
        """
        with self._state_lock:
            return self.download_state.progress_bars.get(url_index)
    
    def update_progress_bar(self, url_index: int, current: int, total: Optional[int] = None) -> None:
        """プログレスバーの進捗を更新
        
        Args:
            url_index: URL配列内のインデックス
            current: 現在の進捗
            total: 合計数（指定された場合のみ更新）
        """
        self.update_progress_bar_state(
            url_index=url_index,
            current=current,
            total=total
        )
    
    def set_progress_bar_title(self, url_index: int, title: str) -> None:
        """プログレスバーのタイトルを設定
        
        Args:
            url_index: URL配列内のインデックス
            title: タイトル
        """
        self.update_progress_bar_state(
            url_index=url_index,
            title=title
        )
    
    def set_progress_bar_status(self, url_index: int, status: str) -> None:
        """プログレスバーの状態を設定
        
        Args:
            url_index: URL配列内のインデックス
            status: 状態
        """
        self.update_progress_bar_state(
            url_index=url_index,
            status=status
        )
    
    def pause_progress_bar(self, url_index: int) -> None:
        """プログレスバーを一時停止
        
        Args:
            url_index: URL配列内のインデックス
        """
        with self._state_lock:
            if url_index in self.download_state.progress_bars:
                self.download_state.progress_bars[url_index].pause()
                self._notify_state_change('progress_bar_paused', {'url_index': url_index})
    
    def resume_progress_bar(self, url_index: int) -> None:
        """プログレスバーを再開
        
        Args:
            url_index: URL配列内のインデックス
        """
        with self._state_lock:
            if url_index in self.download_state.progress_bars:
                self.download_state.progress_bars[url_index].resume()
                self._notify_state_change('progress_bar_resumed', {'url_index': url_index})
    
    def export_progress_bars_to_json(self) -> Dict[str, Any]:
        """全てのプログレスバーをJSON形式でエクスポート（バックアップ用）
        
        Returns:
            JSON形式のデータ
        """
        snapshot = ProgressBarSnapshot()
        
        with self._state_lock:
            for url_index, progress_bar in self.download_state.progress_bars.items():
                snapshot.add_progress_bar(url_index, progress_bar)
        
        return snapshot.to_dict()
    
    def import_progress_bars_from_json(self, data: Dict[str, Any]) -> None:
        """JSON形式からプログレスバーをインポート（復元用）
        
        Args:
            data: JSON形式のデータ
        """
        snapshot = ProgressBarSnapshot.from_dict(data)
        restored = snapshot.restore_progress_bars()
        
        for url_index, progress_bar in restored.items():
            self._message_queue.put({
                'type': 'set_progress_bar',
                'data': {'url_index': url_index, 'progress_bar': progress_bar}
            })
    
    # ⭐既存: 後方互換性のためのメソッド（旧API）⭐
    def get_progress_bar(self, url_index: int) -> Optional[Dict[str, Any]]:
        """プログレスバー情報を取得（後方互換性用・非推奨）
        
        Note:
            新規コードでは get_progress_bar_typed() を使用してください
        """
        with self._state_lock:
            progress_bar = self.download_state.progress_bars.get(url_index)
            if progress_bar:
                # ⭐ProgressBarオブジェクトか辞書かを判定⭐
                if hasattr(progress_bar, 'to_dict'):
                    result = progress_bar.to_dict()
                    print(f"[DEBUG] get_progress_bar({url_index}): ProgressBar -> dict, title='{result.get('title', '')[:30]}', status='{result.get('status', '')[:30]}', current={result.get('current')}/{result.get('total')}")
                    return result
                elif isinstance(progress_bar, dict):
                    # ⭐修正: stateネストを解除してフラットな辞書を返す⭐
                    if 'state' in progress_bar:
                        # stateネストされた辞書 -> フラット化
                        state = progress_bar.get('state', {})
                        # 経過時間と残り時間を計算
                        start_time = progress_bar.get('start_time')
                        paused_duration = progress_bar.get('paused_duration', 0.0)
                        current = state.get('current', 0)
                        total = state.get('total', 0)
                        
                        elapsed_time = 0.0
                        estimated_remaining = None
                        if start_time:
                            elapsed_time = max(0.0, time.time() - start_time - paused_duration)
                            if current > 0 and total > 0 and current < total and elapsed_time > 0:
                                rate = elapsed_time / current
                                remaining_pages = total - current
                                estimated_remaining = rate * remaining_pages
                            elif current >= total:
                                # ⭐修正: 完了時は残り時間を0に設定⭐
                                estimated_remaining = 0.0
                        
                        # ⭐修正: 経過時間と残り時間を常に最新の値で計算⭐
                        if start_time:
                            # 現在時刻から開始時刻を引いて、中断時間を差し引く
                            elapsed_time = max(0.0, time.time() - start_time - (paused_duration or 0.0))
                            
                            # 残り時間を計算（ダウンロード中のみ）
                            if current > 0 and total > 0 and current < total and elapsed_time > 0:
                                rate = elapsed_time / current  # 1ページあたりの時間
                                remaining_pages = total - current
                                estimated_remaining = rate * remaining_pages
                            elif current >= total:
                                # ⭐修正: 完了時は残り時間を0に設定⭐
                                estimated_remaining = 0.0
                            else:
                                estimated_remaining = None
                        else:
                            elapsed_time = 0.0
                            estimated_remaining = None
                        
                        result = {
                            'url': progress_bar.get('url', ''),
                            'url_index': url_index,
                            'start_time': start_time,
                            'paused_duration': paused_duration,
                            'current': current,
                            'total': total,
                            'title': state.get('title', '準備中...'),
                            'status': state.get('status', '待機中'),
                            'download_range_info': progress_bar.get('download_range_info'),
                            'elapsed_time': elapsed_time,
                            'estimated_remaining': estimated_remaining
                        }
                        # ⭐修正: Noneセーフなデバッグログ出力⭐
                        elapsed_str = f"{elapsed_time:.1f}s" if elapsed_time is not None else "None"
                        remaining_str = f"{estimated_remaining:.1f}s" if estimated_remaining is not None else "None"
                        print(f"[DEBUG] get_progress_bar({url_index}): Dict (nested) -> flat, title='{result.get('title', '')[:30]}', status='{result.get('status', '')[:30]}', current={result.get('current')}/{result.get('total')}, elapsed={elapsed_str}, remaining={remaining_str}")
                        return result
                    else:
                        # 既にフラットな辞書
                        print(f"[DEBUG] get_progress_bar({url_index}): Dict (flat), title='{progress_bar.get('title', '')[:30]}', status='{progress_bar.get('status', '')[:30]}'")
                        return progress_bar
                else:
                    print(f"[ERROR] Unknown progress_bar type: {type(progress_bar)}")
                    return None
            print(f"[DEBUG] get_progress_bar({url_index}): url_indexが存在しません（progress_bars={list(self.download_state.progress_bars.keys())}）")
            return None
    
    def set_progress_bar(self, url_index: int, progress_info: Dict[str, Any]) -> None:
        """プログレスバー情報を設定（後方互換性用・非推奨）
        
        Note:
            新規コードでは create_progress_bar() を使用してください
        """
        # 辞書からProgressBarを復元
        if isinstance(progress_info, dict):
            # ⭐修正: 辞書の構造を正しく解析⭐
            # state辞書が存在する場合とない場合の両方に対応
            if 'state' in progress_info:
                # 新形式の辞書
                state = progress_info.get('state', {})
                progress_bar = ProgressBar(
                    url=progress_info.get('url', ''),
                    url_index=url_index,
                    start_time=progress_info.get('start_time', time.time()),
                    paused_duration=progress_info.get('paused_duration', 0.0),
                    current=state.get('current', 0),
                    total=state.get('total', 0),
                    title=state.get('title', '準備中...'),
                    status=state.get('status', '待機中'),
                    download_range_info=progress_info.get('download_range_info')
                )
            else:
                # 古い形式または直接のフィールド
                progress_bar = ProgressBar(
                    url=progress_info.get('url', ''),
                    url_index=url_index,
                    start_time=progress_info.get('start_time', time.time()),
                    paused_duration=progress_info.get('paused_duration', 0.0),
                    current=progress_info.get('current', 0),
                    total=progress_info.get('total', 0),
                    title=progress_info.get('title', '準備中...'),
                    status=progress_info.get('status', '待機中'),
                    download_range_info=progress_info.get('download_range_info')
                )
        elif hasattr(progress_info, 'to_dict'):
            # 既にProgressBarオブジェクト
            progress_bar = progress_info
        else:
            print(f"[ERROR] Invalid progress_info type: {type(progress_info)}")
            return
        
        self._message_queue.put({
            'type': 'set_progress_bar',
            'data': {'url_index': url_index, 'progress_bar': progress_bar}
        })
    
    def update_progress_bar_state(self, url_index: int, current: Optional[int] = None, 
                                   total: Optional[int] = None, title: Optional[str] = None, 
                                   status: Optional[str] = None, download_range_info: Optional[dict] = None, 
                                   start_time: Optional[float] = None, paused_duration: Optional[float] = None) -> None:
        """プログレスバーの状態を更新（ロック不要）
        
        Args:
            start_time: ダウンロード開始時刻（Noneの場合は変更しない）
            paused_duration: 累積中断時間（秒）（Noneの場合は変更しない）
        """
        self._message_queue.put({
            'type': 'update_progress_bar_state',
            'data': {
                'url_index': url_index,
                'current': current,
                'total': total,
                'title': title,
                'status': status,
                'download_range_info': download_range_info,
                'start_time': start_time,
                'paused_duration': paused_duration
            }
        })
    
    def get_url_index_by_url(self, url: str) -> Optional[int]:
        """URLからurl_indexを取得（高速読み取り用）"""
        with self._state_lock:
            # progress_barsからURLで検索
            for url_index, progress_bar in self.download_state.progress_bars.items():
                # ⭐ProgressBarオブジェクトか辞書かを判定⭐
                if hasattr(progress_bar, 'url'):
                    # ProgressBarオブジェクト
                    if progress_bar.url == url:
                        return url_index
                elif isinstance(progress_bar, dict):
                    # 辞書
                    if progress_bar.get('url') == url:
                        return url_index
            return None
    
    def get_all_progress_bars(self) -> Dict[int, ProgressBar]:
        """全てのプログレスバー情報を取得（高速読み取り用）
        
        Returns:
            Dict[int, ProgressBar]: url_index -> ProgressBarオブジェクトのマッピング
            
        Note:
            辞書が混在している場合は自動的にProgressBarに変換します
        """
        with self._state_lock:
            result = {}
            for url_index, progress_bar in self.download_state.progress_bars.items():
                if hasattr(progress_bar, 'to_dict'):
                    # 既にProgressBarオブジェクト
                    result[url_index] = progress_bar
                elif isinstance(progress_bar, dict):
                    # 辞書の場合はProgressBarに変換
                    try:
                        if 'state' in progress_bar:
                            state = progress_bar.get('state', {})
                            pb = ProgressBar(
                                url=progress_bar.get('url', ''),
                                url_index=url_index,
                                start_time=progress_bar.get('start_time', time.time()),
                                paused_duration=progress_bar.get('paused_duration', 0.0),
                                current=state.get('current', 0),
                                total=state.get('total', 0),
                                title=state.get('title', '準備中...'),
                                status=state.get('status', '待機中'),
                                download_range_info=progress_bar.get('download_range_info')
                            )
                        else:
                            pb = ProgressBar(
                                url=progress_bar.get('url', ''),
                                url_index=url_index,
                                start_time=progress_bar.get('start_time', time.time()),
                                paused_duration=progress_bar.get('paused_duration', 0.0),
                                current=progress_bar.get('current', 0),
                                total=progress_bar.get('total', 0),
                                title=progress_bar.get('title', '準備中...'),
                                status=progress_bar.get('status', '待機中'),
                                download_range_info=progress_bar.get('download_range_info')
                            )
                        result[url_index] = pb
                    except Exception as e:
                        print(f"[ERROR] Failed to convert dict to ProgressBar for url_index={url_index}: {e}")
                        continue
                else:
                    print(f"[ERROR] Unknown progress_bar type for url_index={url_index}: {type(progress_bar)}")
                    continue
            return result
    
    # ⭐追加: タイマー管理メソッド⭐
    def set_elapsed_time_timer_id(self, timer_id: Optional[int]) -> None:
        """経過時間タイマーIDを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_elapsed_time_timer_id',
            'data': {'timer_id': timer_id}
        })
    
    def get_elapsed_time_timer_id(self) -> Optional[int]:
        """経過時間タイマーIDを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.elapsed_time_timer_id
    
    def set_elapsed_time_start(self, start_time: Optional[float]) -> None:
        """経過時間開始時刻を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_elapsed_time_start',
            'data': {'start_time': start_time}
        })
    
    def get_elapsed_time_start(self) -> Optional[float]:
        """経過時間開始時刻を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.elapsed_time_start
    
    def set_elapsed_time_paused_start(self, paused_start: Optional[float]) -> None:
        """中断開始時刻を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_elapsed_time_paused_start',
            'data': {'paused_start': paused_start}
        })
    
    def get_elapsed_time_paused_start(self) -> Optional[float]:
        """中断開始時刻を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.elapsed_time_paused_start
    
    def add_elapsed_time(self, seconds: float) -> None:
        """経過時間を追加（ロック不要）"""
        self._message_queue.put({
            'type': 'add_elapsed_time',
            'data': {'seconds': seconds}
        })
    
    def get_total_elapsed_seconds(self) -> float:
        """総経過時間を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.total_elapsed_seconds
    
    def add_paused_time(self, seconds: float) -> None:
        """中断時間を追加（ロック不要）"""
        self._message_queue.put({
            'type': 'add_paused_time',
            'data': {'seconds': seconds}
        })
    
    def get_total_paused_time(self) -> float:
        """総中断時間を取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.total_paused_time
    
    def reset_elapsed_time(self) -> None:
        """経過時間をリセット（ロック不要）"""
        self._message_queue.put({
            'type': 'reset_elapsed_time',
            'data': {}
        })
    
    # ⭐追加: スキップ・リスタート要求管理メソッド⭐
    def get_skip_requested_url(self) -> Optional[str]:
        """スキップ要求URLを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.skip_requested_url
    
    def set_skip_requested_url(self, url: Optional[str]) -> None:
        """スキップ要求URLを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_skip_requested_url',
            'data': {'url': url}
        })
    
    def get_restart_requested_url(self) -> Optional[str]:
        """リスタート要求URLを取得（高速読み取り用）"""
        with self._state_lock:
            return self.download_state.restart_requested_url
    
    def set_restart_requested_url(self, url: Optional[str]) -> None:
        """リスタート要求URLを設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_restart_requested_url',
            'data': {'url': url}
        })


    
    # ==================== URL単位のダウンロード範囲管理 ====================
    
    def set_url_download_range(self, url: str, start: Optional[int] = None, end: Optional[int] = None) -> None:
        """URLに対してダウンロード範囲を設定（ロック不要）"""
        self._message_queue.put({
            'type': 'set_url_download_range',
            'data': {
                'url': url,
                'start': start,
                'end': end
            }
        })
    
    def get_url_download_range(self, url: str) -> Dict[str, Any]:
        """URLのダウンロード範囲を取得（高速読み取り用）"""
        if not hasattr(self.download_state, '_url_download_ranges'):
            self.download_state._url_download_ranges = {}
        
        with self._state_lock:
            return self.download_state._url_download_ranges.get(url, {'enabled': False})
    
    def clear_url_download_range(self, url: str) -> None:
        """URLのダウンロード範囲をクリア（ロック不要）"""
        self._message_queue.put({
            'type': 'clear_url_download_range',
            'data': {'url': url}
        })
    
    def clear_all_url_download_ranges(self) -> None:
        """全URLのダウンロード範囲をクリア（ロック不要）"""
        self._message_queue.put({
            'type': 'clear_all_url_download_ranges',
            'data': {}
        })
    
    # ==================== URL単位の適用されたダウンロード範囲管理 ====================
    
    def set_url_applied_range(self, url: str, applied_range: Dict[str, Any]) -> None:
        """URLに適用されたダウンロード範囲を記録（ロック不要）"""
        self._message_queue.put({
            'type': 'set_url_applied_range',
            'data': {
                'url': url,
                'applied_range': applied_range
            }
        })
    
    def get_url_applied_range(self, url: str) -> Optional[Dict[str, Any]]:
        """URLに適用されたダウンロード範囲を取得（高速読み取り用）"""
        if not hasattr(self.download_state, '_url_applied_ranges'):
            self.download_state._url_applied_ranges = {}
        
        with self._state_lock:
            return self.download_state._url_applied_ranges.get(url)
    
    def clear_url_applied_range(self, url: str) -> None:
        """URLに適用されたダウンロード範囲をクリア（ロック不要）"""
        self._message_queue.put({
            'type': 'clear_url_applied_range',
            'data': {'url': url}
        })
