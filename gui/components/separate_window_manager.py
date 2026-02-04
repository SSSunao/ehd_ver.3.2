# -*- coding: utf-8 -*-
"""
Separate Window Manager for EH Downloader
ダウンロードマネージャー（別ウィンドウ）の管理を担当
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any


class SeparateWindowManager:
    def __init__(self, parent, progress_panel):
        self.parent = parent
        self.progress_panel = progress_panel
        self.separate_window = None
        self.separate_window_progress_bars = []
        self.separate_window_canvas = None
        self.separate_window_scrollable_frame = None
        self.separate_window_pause_btn = None
        self.separate_window_resume_btn = None
        self.separate_window_skip_btn = None
        self.separate_window_restart_btn = None
        self.separate_window_refresh_btn = None
        self.separate_window_autoscroll_btn = None
    
    def create_window(self):
        """別ウィンドウを作成"""
        try:
            if self.separate_window and self.separate_window.winfo_exists():
                return
            
            if self.separate_window:
                try:
                    self.separate_window.destroy()
                except:
                    pass
                self.separate_window = None
                self.separate_window_progress_bars = []
                if hasattr(self.parent, 'options_panel') and hasattr(self.parent.options_panel, '_update_download_manager_button_state'):
                    self.parent.options_panel._update_download_manager_button_state()
            
            self.separate_window = tk.Toplevel(self.parent.root)
            self.separate_window.title("ダウンロードマネージャー")
            
            saved_geometry = self._load_settings()
            self.separate_window.geometry(saved_geometry)
            self.separate_window.protocol("WM_DELETE_WINDOW", self._on_close)
            
            self._create_header()
            self._create_main_area()
            
            self._update_button_states()
            
            if hasattr(self.parent, 'options_panel'):
                self.parent.options_panel._update_download_manager_button_state()
            
            self.progress_panel._rebuild_all_progress_bars_in_separate_window()
            self.progress_panel._refresh_all_progress_bars_status_in_separate_window()
            self.progress_panel.hide_current_progress_bar()
                
        except Exception as e:
            self.progress_panel.log(f"別ウィンドウ作成エラー: {e}", "error")
    
    def _create_header(self):
        """ヘッダーエリアを作成"""
        header_frame = ttk.Frame(self.separate_window)
        header_frame.pack(fill="x", padx=5, pady=5)
        
        left_controls = ttk.Frame(header_frame)
        left_controls.pack(side="left", anchor="w")
        
        self.separate_window_pause_btn = ttk.Button(left_controls, text="中断", 
                                                  command=self.progress_panel._pause_download, width=8)
        self.separate_window_pause_btn.pack(side="left", padx=(0, 5))
        
        self.separate_window_resume_btn = ttk.Button(left_controls, text="再開", 
                                                   command=self.progress_panel._resume_download, width=8)
        self.separate_window_resume_btn.pack(side="left", padx=(0, 5))
        
        self.separate_window_refresh_btn = ttk.Button(left_controls, text="GUI更新", 
                                                   command=self.progress_panel._refresh_gui_state, width=8)
        self.separate_window_refresh_btn.pack(side="left", padx=(0, 5))
        
        right_controls = ttk.Frame(header_frame)
        right_controls.pack(side="right", anchor="e")
        
        self.separate_window_restart_btn = ttk.Button(right_controls, text="リスタート", 
                                                    command=self.progress_panel._restart_current_download, width=8)
        self.separate_window_restart_btn.pack(side="left", padx=(0, 5))
        
        self.separate_window_skip_btn = ttk.Button(right_controls, text="スキップ", 
                                                 command=self.progress_panel._skip_current_download, width=8)
        self.separate_window_skip_btn.pack(side="left", padx=(0, 5))
        
        self.separate_window_autoscroll_btn = tk.Button(right_controls, text="オートスクロール", 
                                                       command=self.progress_panel._toggle_autoscroll, width=12,
                                                       relief="raised", bg="SystemButtonFace")
        self.separate_window_autoscroll_btn.pack(side="left", padx=(0, 5))
    
    def _create_main_area(self):
        """メインエリア（スクロール可能）を作成"""
        main_frame = ttk.Frame(self.separate_window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="n")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def configure_scroll_region(event):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas_width = canvas.winfo_width()
                if canvas_width > 1:
                    for item in canvas.find_all():
                        if canvas.type(item) == "window":
                            canvas.itemconfig(item, width=canvas_width)
            except Exception:
                pass
                
        canvas.bind('<Configure>', configure_scroll_region)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.separate_window_canvas = canvas
        self.separate_window_scrollable_frame = scrollable_frame
    
    def _update_button_states(self):
        """ボタンの状態を更新"""
        if not self.separate_window or not self.separate_window.winfo_exists():
            return
        
        try:
            state_mgr = self.progress_panel._get_state_manager()
            if not state_mgr:
                return
            
            is_running = state_mgr.is_download_running()
            is_paused = state_mgr.is_paused()
            
            if is_running and not is_paused:
                if self.separate_window_pause_btn:
                    self.separate_window_pause_btn.config(state="normal")
                if self.separate_window_resume_btn:
                    self.separate_window_resume_btn.config(state="disabled")
                if self.separate_window_skip_btn:
                    self.separate_window_skip_btn.config(state="normal")
                if self.separate_window_restart_btn:
                    self.separate_window_restart_btn.config(state="normal")
            elif is_running and is_paused:
                if self.separate_window_pause_btn:
                    self.separate_window_pause_btn.config(state="disabled")
                if self.separate_window_resume_btn:
                    self.separate_window_resume_btn.config(state="normal")
                if self.separate_window_skip_btn:
                    self.separate_window_skip_btn.config(state="normal")
                if self.separate_window_restart_btn:
                    self.separate_window_restart_btn.config(state="normal")
            else:
                if self.separate_window_pause_btn:
                    self.separate_window_pause_btn.config(state="disabled")
                if self.separate_window_resume_btn:
                    self.separate_window_resume_btn.config(state="disabled")
                if self.separate_window_skip_btn:
                    self.separate_window_skip_btn.config(state="disabled")
                if self.separate_window_restart_btn:
                    self.separate_window_restart_btn.config(state="disabled")
        except Exception as e:
            self.progress_panel.log(f"ボタン状態更新エラー: {e}", "error")
    
    def _on_close(self):
        """ウィンドウを閉じる際の処理"""
        try:
            self._save_settings()
            
            if hasattr(self.parent, 'progress_separate_window_enabled'):
                self.parent.progress_separate_window_enabled.set(False)
            
            if self.separate_window:
                self.separate_window.destroy()
                self.separate_window = None
                self.separate_window_progress_bars = []
            
            if hasattr(self.parent, 'options_panel'):
                self.parent.options_panel._update_download_manager_button_state()
            
            self.progress_panel._show_latest_progress_in_main_window()
        except Exception as e:
            self.progress_panel.log(f"ウィンドウクローズエラー: {e}", "error")
    
    def _save_settings(self):
        """ウィンドウ設定を保存"""
        if not self.separate_window or not self.separate_window.winfo_exists():
            return
        
        try:
            geometry = self.separate_window.geometry()
            if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'settings_manager'):
                self.parent.downloader_core.settings_manager.set("separate_window_geometry", geometry)
        except Exception as e:
            self.progress_panel.log(f"設定保存エラー: {e}", "error")
    
    def _load_settings(self):
        """ウィンドウ設定を読み込み"""
        try:
            if hasattr(self.parent, 'downloader_core') and hasattr(self.parent.downloader_core, 'settings_manager'):
                geometry = self.parent.downloader_core.settings_manager.get("separate_window_geometry", "800x600")
                return geometry
        except Exception:
            pass
        return "800x600"
    
    def destroy(self):
        """ウィンドウを破棄"""
        if self.separate_window:
            try:
                self.separate_window.destroy()
            except:
                pass
            self.separate_window = None
            self.separate_window_progress_bars = []
