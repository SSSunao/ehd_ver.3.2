# -*- coding: utf-8 -*-
"""
完了処理の統合管理

責任:
1. 完了イベントの受信
2. 完了処理の調整（順序保証）
3. 次のダウンロード開始の調整

設計原則:
- 単一責任: 完了処理の調整のみ
- GUI非依存: EventBus経由で通信
- スレッドセーフ: 状態管理はStateManagerに委譲
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
import threading
from dataclasses import dataclass

if TYPE_CHECKING:
    from core.coordination.event_bus import EventBus


@dataclass
class CompletionContext:
    """完了処理のコンテキスト"""
    url: str
    save_folder: str
    options: Dict[str, Any]
    actual_total_pages: int = 0
    has_errors: bool = False


class CompletionCoordinator:
    """完了処理の統合管理（単一責任）"""
    
    def __init__(self, core):
        """
        Args:
            core: EHDownloaderCoreインスタンス
        """
        self.core = core
        self.state_manager = core.state_manager
        self.session_manager = core.session_manager
        self.compression_manager = core.compression_manager
        
        # EventBusは後で設定される（循環参照回避）
        self.event_bus: Optional["EventBus"] = None
        
        # 完了処理のロック（順序保証）
        self._completion_lock = threading.Lock()
    
    def handle_completion(self, context: CompletionContext) -> bool:
        import threading
        print(f"[DEBUG] CompletionCoordinator: handle_completion開始 (thread_id={{}} thread_name={{}})".format(
            threading.current_thread().ident, threading.current_thread().name))
        """
        完了処理のエントリーポイント（⭐同期的に実行、次のURLのみ非同期⭐）
        
        Args:
            context: 完了処理のコンテキスト
            
        Returns:
            成功時True
        """
        try:
            self.session_manager.ui_bridge.post_log(
                f"[CompletionCoordinator] 完了処理開始: {context.url[:50]}...",
                "debug"
            )
            print("[DEBUG] CompletionCoordinator: 状態更新前")
            self._update_state(context)
            print("[DEBUG] CompletionCoordinator: 状態更新後、GUI更新イベント送信前")
            self._send_gui_update_event(context)
            print("[DEBUG] CompletionCoordinator: GUI更新イベント送信後、圧縮処理前")
            if context.options.get('compression_enabled'):
                print("[DEBUG] CompletionCoordinator: 圧縮処理開始")
                self._start_compression(context)
                print("[DEBUG] CompletionCoordinator: 圧縮処理完了")
            print("[DEBUG] CompletionCoordinator: 完了後処理前")
            self._finalize_completion(context)
            print("[DEBUG] CompletionCoordinator: 完了後処理完了、次のURL判定前")
            self.session_manager.ui_bridge.post_log(
                f"[CompletionCoordinator] 完了処理完了（次のURL判定開始）",
                "debug"
            )
            if self.event_bus:
                from core.coordination.event_bus import Event, EventType
                self.event_bus.publish(Event(
                    type=EventType.URL_COMPLETED,
                    data={
                        'url': context.url,
                        'save_folder': context.save_folder,
                        'actual_total_pages': context.actual_total_pages
                    },
                    source="CompletionCoordinator"
                ))
            if self.state_manager.is_download_running():
                print("[DEBUG] CompletionCoordinator: _schedule_next_download呼び出し直前")
                self.core._schedule_next_download("CompletionCoordinator")
                print("[DEBUG] CompletionCoordinator: _schedule_next_download呼び出し直後")
            print("[DEBUG] CompletionCoordinator.handle_completion: return True直前")
            return True
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"[CompletionCoordinator] 完了処理エラー: {e}",
                "error"
            )
            import traceback
            self.session_manager.ui_bridge.post_log(
                f"詳細: {traceback.format_exc()}",
                "error"
            )
            print("[DEBUG] CompletionCoordinator: 例外発生")
            return False
    
    def _update_state(self, context: CompletionContext):
        """状態更新"""
        normalized_url = self.session_manager.ui_bridge.normalize_url(context.url)
        self.state_manager.set_url_status(normalized_url, 'completed')
    
    def _send_gui_update_event(self, context: CompletionContext):
        """GUI更新イベント送信"""
        def update_gui():
            try:
                normalized_url = self.session_manager.ui_bridge.normalize_url(context.url)
                
                # DLリスト更新
                if hasattr(self.core.parent, 'download_list_widget'):
                    if context.actual_total_pages > 0:
                        self.core.parent.download_list_widget.update_progress(
                            normalized_url,
                            context.actual_total_pages,
                            context.actual_total_pages
                        )
                    self.core.parent.download_list_widget.update_status(
                        normalized_url,
                        'completed'
                    )
                    
            except Exception as e:
                self.session_manager.ui_bridge.post_log(
                    f"[CompletionCoordinator] GUI更新エラー: {e}",
                    "error"
                )
        
        # GUIスレッドで実行
        self.session_manager.ui_bridge.schedule_update(update_gui)
    
    def _start_compression(self, context: CompletionContext):
        """圧縮処理開始（⭐同期的に開始、圧縮自体は別スレッド⭐）"""
        try:
            normalized_url = self.session_manager.ui_bridge.normalize_url(context.url)
            url_status = self.state_manager.get_url_status(normalized_url)
            
            if url_status not in ["skipped", "error"]:
                # _start_compression_task内で別スレッドが起動される
                self.core._start_compression_task(context.save_folder, normalized_url)
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"[CompletionCoordinator] 圧縮処理エラー: {e}",
                "error"
            )
    
    def _finalize_completion(self, context: CompletionContext):
        """完了後処理（履歴、クリーンアップ）"""
        try:
            # 最新フォルダ更新
            if context.save_folder:
                import os
                if os.path.exists(context.save_folder):
                    normalized_url = self.session_manager.ui_bridge.normalize_url(context.url)
                    self.core.last_download_folder = context.save_folder
                    self.core.managed_folders[normalized_url] = context.save_folder
            
            # エラーフラグクリア
            if hasattr(self.core, 'error_info'):
                self.core.error_info['has_error'] = False
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"[CompletionCoordinator] 完了後処理エラー: {e}",
                "error"
            )
    

