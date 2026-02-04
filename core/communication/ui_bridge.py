# -*- coding: utf-8 -*-
"""
UIBridge - GUI操作の非同期通知
コア層からGUI層への直接操作を排除
"""

import threading
import queue
import time
from typing import Any, Dict, Callable, Optional
from enum import Enum
from dataclasses import dataclass, field


class UIEventType(Enum):
    """UIイベントタイプ"""
    LOG = "log"
    PROGRESS_UPDATE = "progress_update"
    PROGRESS_BAR_SHOW = "progress_bar_show"  # プログレスバー表示イベント
    URL_PROGRESS_UPDATE = "url_progress_update"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    COMPLETE = "complete"
    BUTTON_STATE = "button_state"
    TITLE_UPDATE = "title_update"


@dataclass
class UIEvent:
    """UIイベント"""
    event_type: UIEventType
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def log(cls, message: str, level: str = "info") -> 'UIEvent':
        """ログイベントを作成"""
        import time
        return cls(
            event_type=UIEventType.LOG,
            data={'message': message, 'level': level},
            timestamp=time.time()
        )
    
    @classmethod
    def progress(cls, current: int, total: int, status: str = "") -> 'UIEvent':
        """進捗イベントを作成"""
        import time
        return cls(
            event_type=UIEventType.PROGRESS_UPDATE,
            data={'current': current, 'total': total, 'status': status},
            timestamp=time.time()
        )
    
    @classmethod
    def error(cls, message: str, error_type: str = "") -> 'UIEvent':
        """エラーイベントを作成"""
        import time
        return cls(
            event_type=UIEventType.ERROR,
            data={'message': message, 'error_type': error_type},
            timestamp=time.time()
        )


class UIBridge:
    """
    UIブリッジ - コア層とUI層の橋渡し
    GUI操作を直接行わず、イベント駆動で通知
    """
    
    def __init__(self, parent=None):
        """
        Args:
            parent: 親オブジェクト（GUIオブジェクト）
        """
        self.parent = parent
        
        # イベントキュー
        self._event_queue = queue.Queue()
        
        # イベントハンドラー
        self._event_handlers: Dict[UIEventType, list] = {}
        
        # ワーカースレッド
        self._running = False
        self._worker_thread = None
        
        # イベント統計
        self.stats = {
            'total_events': 0,
            'processed_events': 0,
            'dropped_events': 0,
        }
    
    def start(self):
        """UIブリッジを開始"""
        if not self._running:
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._event_worker,
                name="UIBridge-Worker",
                daemon=True
            )
            self._worker_thread.start()
    
    def stop(self):
        """UIブリッジを停止"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=1.0)
    
    def post_event(self, event: UIEvent):
        """イベントを投稿"""
        try:
            self._event_queue.put_nowait(event)
            self.stats['total_events'] += 1
        except queue.Full:
            self.stats['dropped_events'] += 1
    
    def post_log(self, message: str, level: str = "info"):
        """ログイベントを投稿"""
        self.post_event(UIEvent.log(message, level))
    
    def post_progress(self, current: int, total: int, status: str = ""):
        """進捗イベントを投稿"""
        self.post_event(UIEvent.progress(current, total, status))
    
    def post_error(self, message: str, error_type: str = ""):
        """エラーイベントを投稿"""
        self.post_event(UIEvent.error(message, error_type))
    
    def schedule_update(self, callback, *args, **kwargs):
        """
        UI更新をメインスレッドにスケジュール（ThreadSafeUIBridgeとの互換性のため）
        
        Args:
            callback: 実行する関数
            *args: 関数の引数
            **kwargs: 関数のキーワード引数
        
        Returns:
            after()のID（キャンセル用）、またはNone
        """
        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"[UIBridge] UI更新エラー: {e}")
        
        try:
            if self.parent and hasattr(self.parent, 'root'):
                return self.parent.root.after(0, wrapped)
            else:
                # parentがない場合は直接実行
                wrapped()
                return None
        except Exception as e:
            print(f"[UIBridge] after()失敗: {e}")
            return None
    
    def register_handler(self, event_type: UIEventType, handler: Callable[[UIEvent], None]):
        """イベントハンドラーを登録"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def _event_worker(self):
        """イベント処理ワーカー"""
        while self._running:
            try:
                # イベントを取得（タイムアウト付き）
                event = self._event_queue.get(timeout=0.1)
                
                # イベントを処理
                self._process_event(event)
                
                self.stats['processed_events'] += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                # エラーは無視して継続
                if self.parent and hasattr(self.parent, 'log'):
                    self.parent.log(f"[UIBridge] イベント処理エラー: {e}", "error")
    
    def _process_event(self, event: UIEvent):
        """イベントを処理"""
        try:
            # 登録されたハンドラーを呼び出し
            if event.event_type in self._event_handlers:
                for handler in self._event_handlers[event.event_type]:
                    try:
                        handler(event)
                    except Exception as e:
                        if self.parent and hasattr(self.parent, 'log'):
                            self.parent.log(
                                f"[UIBridge] ハンドラーエラー: {e}",
                                "error"
                            )
            
            # デフォルトハンドラー（後方互換性のため）
            self._default_handler(event)
            
        except Exception as e:
            if self.parent and hasattr(self.parent, 'log'):
                self.parent.log(f"[UIBridge] イベント処理エラー: {e}", "error")
    
    def _default_handler(self, event: UIEvent):
        """デフォルトイベントハンドラー"""
        if not self.parent:
            return
        
        try:
            if event.event_type == UIEventType.LOG:
                # ログ出力
                if hasattr(self.parent, 'log'):
                    self.parent.log(
                        event.data['message'],
                        event.data.get('level', 'info')
                    )
            
            elif event.event_type == UIEventType.PROGRESS_UPDATE:
                # 進捗更新
                if hasattr(self.parent, 'update_progress_display'):
                    self.parent.root.after(0, lambda: self.parent.update_progress_display(
                        url="",
                        current=event.data['current'],
                        total=event.data['total'],
                    ))
            
            elif event.event_type == UIEventType.ERROR:
                # エラー表示
                if hasattr(self.parent, 'log'):
                    self.parent.log(event.data['message'], 'error')
            
            elif event.event_type == UIEventType.BUTTON_STATE:
                # ボタン状態更新
                if hasattr(self.parent, '_update_button_states'):
                    self.parent.root.after(0, self.parent._update_button_states)
            
        except Exception as e:
            # エラーは無視
            pass
    
    def get_stats(self) -> Dict[str, int]:
        """統計情報を取得"""
        return self.stats.copy()
    
    # ============================================================
    # Phase 2: Parent Access Abstraction (親オブジェクトへのアクセス抽象化)
    # ============================================================
    
    def get_url_text(self) -> str:
        """URLテキストを取得"""
        if self.parent and hasattr(self.parent, 'url_text'):
            try:
                return self.parent.url_text.get("1.0", "end-1c").strip()
            except Exception:
                pass
        return ""
    
    def parse_urls_from_text(self, text: str) -> list:
        """テキストからURLを解析"""
        if self.parent and hasattr(self.parent, '_parse_urls_from_text'):
            try:
                return self.parent._parse_urls_from_text(text)
            except Exception:
                pass
        return []
    
    def normalize_url(self, url: str) -> str:
        """URLを正規化"""
        if self.parent and hasattr(self.parent, 'normalize_url'):
            try:
                return self.parent.normalize_url(url)
            except Exception:
                pass
        return url
    
    def get_option_value(self, option_name: str, default=None):
        """設定値を取得"""
        if self.parent and hasattr(self.parent, option_name):
            try:
                attr = getattr(self.parent, option_name)
                if hasattr(attr, 'get'):
                    return attr.get()
                return attr
            except Exception:
                pass
        return default
    
    def set_option_value(self, option_name: str, value):
        """設定値を設定"""
        if self.parent and hasattr(self.parent, option_name):
            try:
                attr = getattr(self.parent, option_name)
                if hasattr(attr, 'set'):
                    attr.set(value)
                    return True
            except Exception:
                pass
        return False
    
    def get_download_list_widget(self):
        """ダウンロードリストウィジェットを取得"""
        if self.parent and hasattr(self.parent, 'download_list_widget'):
            return self.parent.download_list_widget
        return None
    
    def get_unified_error_resume_manager(self):
        """統合エラー再開マネージャーを取得"""
        if self.parent and hasattr(self.parent, 'unified_error_resume_manager'):
            return self.parent.unified_error_resume_manager
        return None
    
    def execute_gui_async(self, callback):
        """非同期でGUI操作を実行"""
        if self.parent and hasattr(self.parent, 'async_executor'):
            try:
                self.parent.async_executor.execute_gui_async(callback)
                return True
            except Exception:
                pass
        return False
    
    def publish_state_change(self, key: str, new_value, old_value=None):
        """状態変更を通知"""
        if self.parent and hasattr(self.parent, '_publish_state_change'):
            try:
                self.parent._publish_state_change(key, new_value, old_value)
                return True
            except Exception:
                pass
        return False
    
    def get_manga_title(self, soup):
        """マンガタイトルを取得"""
        if self.parent and hasattr(self.parent, 'get_manga_title'):
            try:
                return self.parent.get_manga_title(soup)
            except Exception:
                pass
        return None
    
    def create_new_folder_name(self):
        """新しいフォルダ名を作成"""
        if self.parent and hasattr(self.parent, 'create_new_folder_name'):
            try:
                return self.parent.create_new_folder_name()
            except Exception:
                pass
        return None
    
    def is_valid_eh_url(self, url: str) -> bool:
        """有効なE-H URLかチェック"""
        if self.parent and hasattr(self.parent, '_is_valid_eh_url'):
            try:
                return self.parent._is_valid_eh_url(url)
            except Exception:
                pass
        return False
    
    def update_gui_for_running(self):
        """実行中のGUI状態に更新"""
        if self.parent and hasattr(self.parent, '_update_gui_for_running'):
            try:
                self.parent._update_gui_for_running()
                return True
            except Exception:
                pass
        return False
    
    def get_async_executor(self):
        """非同期実行エグゼキュータを取得"""
        if self.parent and hasattr(self.parent, 'async_executor'):
            return self.parent.async_executor
        return None
    
    def get_url_panel(self):
        """URLパネルを取得"""
        if self.parent and hasattr(self.parent, 'url_panel'):
            return self.parent.url_panel
        return None
    
    def set_current_image_page_url(self, url: str):
        """現在の画像ページURLを設定"""
        if self.parent and hasattr(self.parent, 'current_image_page_url'):
            try:
                self.parent.current_image_page_url = url
                return True
            except Exception:
                pass
        return False


# ============================================================
# Phase 1: 統一UIブリッジ（中期的改善）
# ============================================================

class ThreadSafeUIBridge:
    """
    スレッドセーフなUI更新ブリッジ（シンプル版）
    
    設計方針:
    - 最小限の機能（オーバーエンジニアリング回避）
    - after()を使ったメインスレッドキューイング
    - 既存コードとの共存可能
    - 段階的な移行をサポート
    
    使用例:
        ui_bridge = ThreadSafeUIBridge(root)
        
        # ワーカースレッドから安全にGUI更新
        ui_bridge.schedule_update(label.config, text="完了")
        
        # 遅延更新
        ui_bridge.schedule_update_later(1000, button.config, state='normal')
    """
    
    def __init__(self, root):
        """
        Args:
            root: Tkinterのルートウィンドウ
        """
        self.root = root
        self._update_count = 0
        self._error_count = 0
    
    def schedule_update(self, callback, *args, **kwargs):
        """
        UI更新をメインスレッドにスケジュール
        
        Args:
            callback: 実行する関数
            *args: 関数の引数
            **kwargs: 関数のキーワード引数
        
        Returns:
            after()のID（キャンセル用）
        """
        def wrapped():
            try:
                callback(*args, **kwargs)
                self._update_count += 1
            except Exception as e:
                self._error_count += 1
                # エラーログ（オプショナル）
                print(f"[ThreadSafeUIBridge] UI更新エラー: {e}")
        
        try:
            return self.root.after(0, wrapped)
        except Exception as e:
            # after()自体が失敗した場合（稀）
            print(f"[ThreadSafeUIBridge] after()失敗: {e}")
            return None
    
    def schedule_update_later(self, delay_ms, callback, *args, **kwargs):
        """
        遅延付きUI更新をスケジュール
        
        Args:
            delay_ms: 遅延時間（ミリ秒）
            callback: 実行する関数
            *args: 関数の引数
            **kwargs: 関数のキーワード引数
        
        Returns:
            after()のID（キャンセル用）
        """
        def wrapped():
            try:
                callback(*args, **kwargs)
                self._update_count += 1
            except Exception as e:
                self._error_count += 1
                print(f"[ThreadSafeUIBridge] UI更新エラー: {e}")
        
        try:
            return self.root.after(delay_ms, wrapped)
        except Exception as e:
            print(f"[ThreadSafeUIBridge] after()失敗: {e}")
            return None
    
    def cancel_update(self, after_id):
        """
        スケジュール済みの更新をキャンセル
        
        Args:
            after_id: schedule_update()やschedule_update_later()の戻り値
        """
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
    
    def get_stats(self):
        """統計情報を取得"""
        return {
            'update_count': self._update_count,
            'error_count': self._error_count
        }
