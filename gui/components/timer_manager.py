# -*- coding: utf-8 -*-
"""
Timer Manager for EH Downloader
経過時間タイマーの管理を担当
"""

import time


class TimerManager:
    def __init__(self, parent, progress_panel):
        self.parent = parent
        self.progress_panel = progress_panel
        self.elapsed_time_timer_id = None
        self.total_elapsed_seconds = 0
        self.last_elapsed_update_time = None
    
    def _get_state_manager(self):
        """StateManagerインスタンスを取得"""
        if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'state_manager'):
            return self.parent.downloader_core.state_manager
        return None
    
    def start_timer(self):
        """経過時間タイマーを開始"""
        state_mgr = self._get_state_manager()
        start_time = state_mgr.get_elapsed_time_start() if state_mgr else None
        if not start_time:
            start_time = time.time()
        self._start_timer_internal(start_time)
    
    def _start_timer_internal(self, start_time: float):
        """経過時間タイマーを開始（内部実装）"""
        try:
            if self.elapsed_time_timer_id:
                self.parent.root.after_cancel(self.elapsed_time_timer_id)
            
            if self.last_elapsed_update_time is None:
                self.last_elapsed_update_time = start_time if start_time else time.time()
            
            state_mgr = self._get_state_manager()
            self.total_elapsed_seconds = state_mgr.get_total_elapsed_seconds() if state_mgr else 0
            
            def update_elapsed_time():
                try:
                    state_mgr = self._get_state_manager()
                    is_running = state_mgr.is_download_running() if state_mgr else False
                    is_paused = state_mgr.is_paused() if state_mgr else False
                    
                    if is_running:
                        current_time = time.time()
                        if self.last_elapsed_update_time is None:
                            self.last_elapsed_update_time = current_time
                        
                        if not is_paused:
                            time_diff = current_time - self.last_elapsed_update_time
                            self.total_elapsed_seconds += time_diff
                            if state_mgr:
                                state_mgr.add_elapsed_time(time_diff)
                        
                        self.last_elapsed_update_time = current_time
                        self.progress_panel.update_elapsed_time(self.total_elapsed_seconds)
                        self.elapsed_time_timer_id = self.parent.root.after(1000, update_elapsed_time)
                except Exception as e:
                    self.progress_panel.log(f"経過時間更新エラー: {e}", "error")
            
            update_elapsed_time()
        except Exception as e:
            self.progress_panel.log(f"経過時間タイマー開始エラー: {e}", "error")
    
    def stop_timer(self):
        """経過時間タイマーを停止"""
        try:
            if self.elapsed_time_timer_id:
                self.parent.root.after_cancel(self.elapsed_time_timer_id)
                self.elapsed_time_timer_id = None
        except Exception as e:
            self.progress_panel.log(f"タイマー停止エラー: {e}", "error")
