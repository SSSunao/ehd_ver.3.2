# -*- coding: utf-8 -*-
"""
UI状態管理クラス - UI状態の管理を担当
"""

import tkinter as tk
from typing import Dict, Any, Optional, List, Callable, Union
from gui.components.download_list_model import DownloadStatus
from core.interfaces import IStateManager, ILogger

class UIStateManager:
    """UI状態の管理を担当するクラス"""
    
    def __init__(self, 
                 state_manager: IStateManager,
                 logger: ILogger):
        self.state_manager = state_manager
        self.logger = logger
        
        # UI状態
        self.ui_state = {
            'url_backgrounds': {},  # {url: color}
            'progress_info': {},    # {url: progress_info}
            'button_states': {},    # {button_name: enabled}
            'window_state': 'normal'  # normal, maximized, minimized
        }
        
        # 状態変更リスナー
        self.state_listeners = {}
        
        # 状態変更の通知を設定
        self._setup_state_listeners()
    
    def _setup_state_listeners(self):
        """状態変更リスナーの設定"""
        try:
            # ダウンロード状態の変更を監視
            self.state_manager.add_state_listener(
                'download_running', 
                self._on_download_state_changed
            )
            
            # URL状態の変更を監視
            self.state_manager.add_state_listener(
                'url_status', 
                self._on_url_status_changed
            )
            
            # 進捗の変更を監視
            self.state_manager.add_state_listener(
                'progress', 
                self._on_progress_changed
            )
            
        except Exception as e:
            self.logger.log(f"状態リスナー設定エラー: {e}", "error")
    
    def _on_download_state_changed(self, is_running: bool, old_value: bool = None):
        """ダウンロード状態変更時の処理"""
        try:
            # ボタン状態の更新
            self._update_button_states(is_running)
            
            # リスナーに通知
            self._notify_ui_state_change('download_state', {
                'is_running': is_running,
                'old_value': old_value
            })
            
        except Exception as e:
            self.logger.log(f"ダウンロード状態変更処理エラー: {e}", "error")
    
    def _on_url_status_changed(self, url_status: Dict[str, Union[str, DownloadStatus]]):
        """URL状態変更時の処理"""
        try:
            for url, status in url_status.items():
                # Enum変換
                if not isinstance(status, DownloadStatus):
                    try:
                        status = DownloadStatus(status)
                    except Exception:
                        status = DownloadStatus.PENDING
                color = self._get_status_color(status)
                self.ui_state['url_backgrounds'][url] = color
                self._notify_ui_state_change('url_background', {
                    'url': url,
                    'status': status,
                    'color': color
                })
        except Exception as e:
            self.logger.log(f"URL状態変更処理エラー: {e}", "error")
    
    def _on_progress_changed(self, progress: Dict[str, Any]):
        """進捗変更時の処理"""
        try:
            current = progress.get('current', 0)
            total = progress.get('total', 0)
            
            # 進捗情報の更新
            self.ui_state['progress_info'] = {
                'current': current,
                'total': total,
                'percentage': (current / total * 100) if total > 0 else 0
            }
            
            # リスナーに通知
            self._notify_ui_state_change('progress', self.ui_state['progress_info'])
            
        except Exception as e:
            self.logger.log(f"進捗変更処理エラー: {e}", "error")
    
    def _update_button_states(self, is_running: bool):
        """ボタン状態の更新"""
        try:
            if is_running:
                # ダウンロード中
                self.ui_state['button_states'] = {
                    'start': False,
                    'pause': True,
                    'resume': False,
                    'stop': True
                }
            else:
                # アイドル状態
                self.ui_state['button_states'] = {
                    'start': True,
                    'pause': False,
                    'resume': False,
                    'stop': False
                }
                
        except Exception as e:
            self.logger.log(f"ボタン状態更新エラー: {e}", "error")
    
    def _get_status_color(self, status: Union[str, DownloadStatus]) -> str:
        """状態に応じた色を取得（Enum対応）"""
        if not isinstance(status, DownloadStatus):
            try:
                status = DownloadStatus(status)
            except Exception:
                status = DownloadStatus.PENDING
        color_mapping = {
            DownloadStatus.PENDING: 'white',
            DownloadStatus.DOWNLOADING: '#FFFACD',
            DownloadStatus.COMPLETED: '#E0F6FF',
            DownloadStatus.ERROR: '#FFE4E1',
            DownloadStatus.PAUSED: '#FFE4E1',
            DownloadStatus.SKIPPED: '#F0F0F0',
            DownloadStatus.INCOMPLETE: '#F0F0F0',
        }
        return color_mapping.get(status, 'white')
    
    def _notify_ui_state_change(self, state_type: str, data: Dict[str, Any]):
        """UI状態変更の通知"""
        try:
            if state_type in self.state_listeners:
                for callback in self.state_listeners[state_type]:
                    try:
                        callback(data)
                    except Exception as e:
                        self.logger.log(f"UI状態変更通知エラー: {e}", "error")
        except Exception as e:
            self.logger.log(f"UI状態変更通知処理エラー: {e}", "error")
    
    def add_ui_state_listener(self, state_type: str, callback: Callable):
        """UI状態変更リスナーの追加"""
        if state_type not in self.state_listeners:
            self.state_listeners[state_type] = []
        self.state_listeners[state_type].append(callback)
    
    def remove_ui_state_listener(self, state_type: str, callback: Callable):
        """UI状態変更リスナーの削除"""
        if state_type in self.state_listeners:
            try:
                self.state_listeners[state_type].remove(callback)
            except ValueError:
                pass
    
    def get_url_background_color(self, url: str) -> str:
        """URLの背景色を取得"""
        return self.ui_state['url_backgrounds'].get(url, 'white')
    
    def get_progress_info(self) -> Dict[str, Any]:
        """進捗情報を取得"""
        return self.ui_state['progress_info'].copy()
    
    def get_button_state(self, button_name: str) -> bool:
        """ボタンの状態を取得"""
        return self.ui_state['button_states'].get(button_name, False)
    
    def set_window_state(self, state: str):
        """ウィンドウ状態の設定"""
        self.ui_state['window_state'] = state
    
    def get_window_state(self) -> str:
        """ウィンドウ状態の取得"""
        return self.ui_state['window_state']
    
    def update_url_status(self, url: str, status: Union[str, DownloadStatus]):
        """URL状態の更新（Enum対応）"""
        try:
            if not isinstance(status, DownloadStatus):
                try:
                    status = DownloadStatus(status)
                except Exception:
                    status = DownloadStatus.PENDING
            self.state_manager.set_url_status(url, status)
            color = self._get_status_color(status)
            self.ui_state['url_backgrounds'][url] = color
            self._notify_ui_state_change('url_background', {
                'url': url,
                'status': status,
                'color': color
            })
        except Exception as e:
            self.logger.log(f"URL状態更新エラー: {e}", "error")
    
    def update_progress(self, current: int, total: int):
        """進捗の更新"""
        try:
            # 状態管理に通知
            self.state_manager.set_progress(current, total)
            
            # 進捗情報の更新
            self.ui_state['progress_info'] = {
                'current': current,
                'total': total,
                'percentage': (current / total * 100) if total > 0 else 0
            }
            
            # リスナーに通知
            self._notify_ui_state_change('progress', self.ui_state['progress_info'])
            
        except Exception as e:
            self.logger.log(f"進捗更新エラー: {e}", "error")
    
    def reset_ui_state(self):
        """UI状態のリセット"""
        try:
            self.ui_state = {
                'url_backgrounds': {},
                'progress_info': {},
                'button_states': {
                    'start': True,
                    'pause': False,
                    'resume': False,
                    'stop': False
                },
                'window_state': 'normal'
            }
            
            # リスナーに通知
            self._notify_ui_state_change('reset', {})
            
        except Exception as e:
            self.logger.log(f"UI状態リセットエラー: {e}", "error")









