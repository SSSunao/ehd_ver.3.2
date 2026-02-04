# -*- coding: utf-8 -*-
"""
ダウンロードオーケストレーター - ダウンロード全体の調整役

⚠️ 注意: このクラスは将来の拡張用に実装されていますが、現在は使用されていません。
現在のダウンロード処理は EHDownloaderCore._download_url_thread と
CompletionCoordinator._proceed_to_next_url_async で行われています。

将来的な完全移行時に使用予定:
1. ダウンロードシーケンスの開始と停止
2. URL間の遷移管理
3. エラーハンドリングと再試行
4. 完了処理の調整

設計原則:
- 単一責任: ダウンロードの調整のみ
- GUI非依存: EventBus経由で通信
- スレッドセーフ: StateManagerに委譲
"""

from typing import Dict, Any, Optional, List, TYPE_CHECKING
import threading
from dataclasses import dataclass

from core.coordination.event_bus import EventBus, Event, EventType
from core.coordination.completion_coordinator import CompletionCoordinator, CompletionContext
from core.managers.state_manager import StateManager
from core.communication.ui_bridge import UIBridge

if TYPE_CHECKING:
    from core.downloader import EHDownloaderCore


@dataclass
class DownloadRequest:
    """ダウンロードリクエスト"""
    url: str
    url_index: int
    options: Dict[str, Any]



class DownloadOrchestrator:
    """
    ダウンロードオーケストレーター
    
    責任:
    - ダウンロードシーケンスの開始
    - URL間の遷移
    - 完了処理の調整
    """
    # =============================
    # デバッグ用監視・記録ユーティリティ
    # =============================
    def _debug_thread_and_state_watch(self, note=""):
        import threading
        try:
            main_thread = threading.main_thread()
            current_threads = threading.enumerate()
            thread_names = [t.name for t in current_threads]
            log_msg = (
                f"[WATCH] {note} | MainThread alive={main_thread.is_alive()} | "
                f"CurrentThreads={thread_names} | "
                f"_current_request={getattr(self, '_current_request', None)} | "
                f"_proceeding={getattr(self, '_proceeding', None)} | "
                f"_start_next_download_running={getattr(self.core, '_start_next_download_running', None)} | "
                f"_sequence_complete_executed={getattr(self.core, '_sequence_complete_executed', None)}"
            )
            self.ui_bridge.post_log(log_msg, "debug")
        except Exception as e:
            self.ui_bridge.post_log(f"[WATCH] 監視エラー: {e}", "error")
    
    def __init__(
        self,
        core: "EHDownloaderCore",
        state_manager: StateManager,
        ui_bridge: UIBridge,
        event_bus: EventBus,
        completion_coordinator: CompletionCoordinator
    ):
        self.core = core
        self.state_manager = state_manager
        self.ui_bridge = ui_bridge
        self.event_bus = event_bus
        self.completion_coordinator = completion_coordinator
        
        # 現在のダウンロード
        self._current_request: Optional[DownloadRequest] = None
        self._current_thread: Optional[threading.Thread] = None
        
        # ロック
        self._orchestrator_lock = threading.Lock()
        
        # イベント購読
        self._subscribe_events()
    
    def _subscribe_events(self):
        """イベントを購読"""
        self.event_bus.subscribe(EventType.URL_COMPLETED, self._on_url_completed)
        self.event_bus.subscribe(EventType.URL_SKIPPED, self._on_url_skipped)
        self.event_bus.subscribe(EventType.DOWNLOAD_ERROR, self._on_download_error)
    
    def start_sequence(self, urls: List[str], options: Dict[str, Any]) -> bool:
        """
        ダウンロードシーケンスを開始
        
        Args:
            urls: ダウンロード対象URLリスト
            options: ダウンロードオプション
            
        Returns:
            開始成功時True
        """
        with self._orchestrator_lock:
            if self._current_request is not None:
                self.ui_bridge.post_log(
                    "[DownloadOrchestrator] 既にダウンロード中です",
                    "warning"
                )
                return False
            
            if not urls:
                self.ui_bridge.post_log(
                    "[DownloadOrchestrator] URLリストが空です",
                    "error"
                )
                return False
            
            # 最初のURLを開始
            self._start_url(urls[0], 0, options)
            
            # イベント発行
            self.event_bus.publish(Event(
                type=EventType.DOWNLOAD_STARTED,
                data={'urls': urls, 'total': len(urls)},
                source="DownloadOrchestrator"
            ))
            
            return True
    
    def _start_url(self, url: str, url_index: int, options: Dict[str, Any]):
        """
        URLのダウンロードを開始
        
        Args:
            url: ダウンロード対象URL
            url_index: URLインデックス
            options: ダウンロードオプション
        """
        self.ui_bridge.post_log(
            f"[DownloadOrchestrator] URL開始: index={url_index}, url={url[:50]}...",
            "info"
        )
        
        # リクエスト作成
        request = DownloadRequest(
            url=url,
            url_index=url_index,
            options=options
        )
        self._current_request = request
        
        # 状態更新
        self.state_manager.set_current_url_index(url_index)
        self.state_manager.set_url_status(url, 'downloading')
        
        # イベント発行
        self.event_bus.publish(Event(
            type=EventType.URL_STARTED,
            data={'url': url, 'url_index': url_index},
            source="DownloadOrchestrator"
        ))
        
        # ダウンロード実行（別スレッド）
        self._current_thread = threading.Thread(
            target=self._execute_download,
            args=(request,),
            daemon=True,
            name=f"Download-{url_index}"
        )
        self._current_thread.start()
    
    def _execute_download(self, request: DownloadRequest):
        """
        ダウンロードを実行（ワーカースレッド）
        
        Args:
            request: ダウンロードリクエスト
        """
        try:
            # EHDownloaderCoreのダウンロードメソッドを呼び出す
            # TODO: これは後でGalleryProcessorに置き換える
            self.core._download_url_thread(request.url, request.options)
            
        except Exception as e:
            self.ui_bridge.post_log(
                f"[DownloadOrchestrator] ダウンロードエラー: {e}",
                "error"
            )
            import traceback
            self.ui_bridge.post_log(
                f"詳細: {traceback.format_exc()}",
                "error"
            )
            
            # エラーイベント発行
            self.event_bus.publish(Event(
                type=EventType.DOWNLOAD_ERROR,
                data={'url': request.url, 'error': str(e)},
                source="DownloadOrchestrator"
            ))
    
    def _on_url_completed(self, event: Event):
        """URL完了イベントハンドラ"""
        self._debug_thread_and_state_watch("_on_url_completed: start")
        url = event.data.get('url')
        self.ui_bridge.post_log(
            f"[DownloadOrchestrator] URL完了: {url[:50]}...",
            "info"
        )
        
        # 次のURLに進む
        self._proceed_to_next_url()
    
    def _on_url_skipped(self, event: Event):
        """URLスキップイベントハンドラ"""
        self._debug_thread_and_state_watch("_on_url_skipped: start")
        url = event.data.get('url')
        self.ui_bridge.post_log(
            f"[DownloadOrchestrator] URLスキップ: {url[:50]}...",
            "info"
        )
        
        # 次のURLに進む
        self._proceed_to_next_url()
    
    def _on_download_error(self, event: Event):
        """ダウンロードエラーイベントハンドラ"""
        self._debug_thread_and_state_watch("_on_download_error: start")
        url = event.data.get('url')
        error = event.data.get('error')
        self.ui_bridge.post_log(
            f"[DownloadOrchestrator] ダウンロードエラー: {url[:50]}... - {error}",
            "error"
        )
        
        # エラー処理（リトライ or スキップ）
        # TODO: エラーハンドリングロジックを実装
    
    def _proceed_to_next_url(self):
        """次のURLに進む（多重呼出防止・例外安全化）"""
        self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: 呼び出し開始", "debug")
        if getattr(self, "_proceeding", False):
            self.ui_bridge.post_log("[WARNING] 多重に_next_urlが呼ばれたためスキップ", "warning")
            return
        self._proceeding = True
        try:
            self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: ロック取得前", "debug")
            with self._orchestrator_lock:
                self.ui_bridge.post_log(f"[DEBUG] _proceed_to_next_url: ロック取得済み, _current_request={self._current_request}", "debug")
                if self._current_request is None:
                    self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: _current_request is None、return", "debug")
                    self._proceeding = False
                    return
                current_index = self._current_request.url_index
                next_index = current_index + 1
                urls = self._get_all_urls()
                total_urls = len(urls)
                self.ui_bridge.post_log(
                    f"[DownloadOrchestrator] 次のURL判定: current={current_index}, total={total_urls}",
                    "debug"
                )
                if next_index >= total_urls:
                    self.ui_bridge.post_log(
                        "[DownloadOrchestrator] 全てのURLが完了しました",
                        "info"
                    )
                    self._on_sequence_complete()
                    self._proceeding = False
                    self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: シーケンス完了return", "debug")
                    return
                next_url = urls[next_index]
                options = self._current_request.options
                self.ui_bridge.post_log(f"[DEBUG] _proceed_to_next_url: 次のURL開始 next_index={next_index}, next_url={next_url}", "debug")
                self._current_request = None
                try:
                    self._start_url(next_url, next_index, options)
                    self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: _start_url呼び出し完了", "debug")
                except Exception as e:
                    self.ui_bridge.post_log(f"[ERROR] 次のURL開始時に例外: {e}", "error")
                    import traceback
                    self.ui_bridge.post_log(traceback.format_exc(), "error")
                    self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: 例外発生return", "debug")
                    return
        finally:
            self.ui_bridge.post_log("[DEBUG] _proceed_to_next_url: finally _proceeding=False", "debug")
            self._proceeding = False
    
    def _get_all_urls(self) -> List[str]:
        """全URLを取得"""
        # 方法1: download_list_widgetから取得
        if hasattr(self.core.parent, 'download_list_widget'):
            urls = self.core.parent.download_list_widget.get_all_urls()
            if urls:
                return urls
        
        # 方法2: UIBridge経由
        text_content = self.ui_bridge.get_url_text()
        urls = self.ui_bridge.parse_urls_from_text(text_content)
        return urls
    
    def _on_sequence_complete(self):
        self._debug_thread_and_state_watch("_on_sequence_complete: start")
        """シーケンス完了処理"""
        self.ui_bridge.post_log(
            "[DownloadOrchestrator] ダウンロードシーケンス完了",
            "info"
        )
        
        # 状態クリア
        self._current_request = None
        self._current_thread = None
        
        # イベント発行
        self.event_bus.publish(Event(
            type=EventType.DOWNLOAD_COMPLETED,
            data={},
            source="DownloadOrchestrator"
        ))
        
        # EHDownloaderCoreの完了処理を呼び出す
        if hasattr(self.core, '_on_sequence_complete'):
            self.core._on_sequence_complete()

