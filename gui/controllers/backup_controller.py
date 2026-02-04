# -*- coding: utf-8 -*-
"""
バックアップコントローラー
バックアップの復元と管理機能を担当
"""

import os
import json
import tkinter as tk
from tkinter import messagebox


class BackupController:
    """バックアップの復元と管理を担当するコントローラー"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderインスタンス（IStateManager, ILogger, IGUIOperationsを実装）
        """
        self.parent = parent
    
    def is_backup_folder(self, folder_path):
        """指定されたフォルダがバックアップフォルダかチェック"""
        required_files = ['settings.json', 'url_list.txt', 'resume_points.json']
        return all(os.path.exists(os.path.join(folder_path, f)) for f in required_files)
    
    def restore_backup_from_path(self, backup_path):
        """指定されたパスからバックアップを復元（ドラッグ&ドロップ用）"""
        try:
            # ダウンロード実行中の場合は警告
            is_running = (self.parent.downloader_core.state_manager.is_download_running() 
                         if hasattr(self.parent, 'downloader_core') 
                         and hasattr(self.parent.downloader_core, 'state_manager') 
                         else False)
            
            if is_running:
                response = messagebox.askyesno(
                    "警告",
                    "ダウンロード実行中です。バックアップを復元するとダウンロードが中断されます。\n続行しますか？"
                )
                if not response:
                    return
                
                # ダウンロード停止
                if (hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'state_manager')):
                    self.parent.downloader_core.state_manager.set_download_running(False)
                    self.parent.downloader_core.state_manager.set_paused(True)
                if (hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'stop_flag')):
                    self.parent.downloader_core.stop_flag.set()
            
            # バックアップファイルのパス
            settings_backup = os.path.join(backup_path, "settings.json")
            url_list_backup = os.path.join(backup_path, "url_list.txt")
            current_log_backup = os.path.join(backup_path, "current_log.txt")
            resume_point_backup = os.path.join(backup_path, "resume_points.json")
            
            restored_files = []
            
            # 1. 設定ファイルを復元
            if os.path.exists(settings_backup):
                try:
                    self.parent._load_settings_from_file(settings_backup)
                    restored_files.append("設定ファイル")
                except Exception as e:
                    self.parent.log(f"設定ファイルの復元に失敗: {e}", "warning")
            
            # 2. URLリストを復元
            if os.path.exists(url_list_backup):
                try:
                    with open(url_list_backup, 'r', encoding='utf-8') as f:
                        url_content = f.read()
                    
                    self.parent.url_text.delete("1.0", tk.END)
                    if url_content.strip():
                        self.parent.url_text.insert("1.0", url_content)
                    
                    restored_files.append("URLリスト")
                except Exception as e:
                    self.parent.log(f"URLリストの復元に失敗: {e}", "warning")
            
            # 3. ログファイルを復元
            if os.path.exists(current_log_backup):
                try:
                    with open(current_log_backup, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    self.parent.log_text.config(state='normal')
                    self.parent.log_text.delete("1.0", tk.END)
                    self.parent.log_text.insert("1.0", log_content)
                    self.parent.log_text.config(state='disabled')
                    restored_files.append("ログファイル")
                except Exception as e:
                    self.parent.log(f"ログファイルの復元に失敗: {e}", "warning")
            
            # 4. 再開ポイントとURL状態を復元
            if os.path.exists(resume_point_backup):
                try:
                    with open(resume_point_backup, 'r', encoding='utf-8') as f:
                        state_data = json.load(f)
                    
                    self._restore_download_state(state_data)
                    self._restore_gui_from_state()
                    
                    restored_files.append("再開ポイント・ダウンロード状態")
                except Exception as e:
                    self.parent.log(f"再開ポイントの復元に失敗: {e}", "warning")
            
            # 復元結果を表示
            if restored_files:
                self.parent.log(f"バックアップから復元: {', '.join(restored_files)}")
                messagebox.showinfo("復元完了", 
                    f"ドラッグ&ドロップでバックアップを復元しました:\n{chr(10).join(restored_files)}\n\n"
                    f"ダウンロードは中断状態として復元されました。\n"
                    f"再開ボタンで続きからダウンロードできます。")
            else:
                messagebox.showwarning("復元失敗", "バックアップファイルが見つかりませんでした。")
            
        except Exception as e:
            self.parent.log(f"バックアップ復元エラー: {e}", "error")
            messagebox.showerror("エラー", f"バックアップの復元に失敗しました:\n{e}")
    
    def _restore_download_state(self, state_data):
        """ダウンロード状態を復元"""
        # ダウンロード状態を中断状態として復元
        download_state = state_data.get('download_state', {})
        was_running = download_state.get('is_running', False)
        was_paused = download_state.get('paused', False)
        
        # エラー状態または実行中だった場合は中断状態として復元
        if was_running or was_paused:
            if (hasattr(self.parent, 'downloader_core') 
                and hasattr(self.parent.downloader_core, 'state_manager')):
                self.parent.downloader_core.state_manager.set_download_running(False)
                self.parent.downloader_core.state_manager.set_paused(True)
            self.parent.log("バックアップ: ダウンロードが中断状態として復元されました", "info")
        
        # URL状態を復元
        self.parent.url_status = download_state.get('url_status', {})
        self.parent.current_url_index = download_state.get('current_url_index', 0)
        
        # ダウンローダーコアに再開ポイントを復元
        if hasattr(self.parent, 'downloader_core'):
            self._restore_downloader_core_state(state_data)
    
    def _restore_downloader_core_state(self, state_data):
        """ダウンローダーコアの状態を復元"""
        # 再開ポイント復元
        if 'resume_points' in state_data:
            resume_points = state_data['resume_points']
            if resume_points:
                # 最初の復帰ポイントを使用
                url, resume_data = next(iter(resume_points.items()))
                self.parent.downloader_core.resume_point = resume_data
            # parentにもresume_pointsを設定
            self.parent.resume_points = state_data['resume_points']
        
        # 管理フォルダと未完了URLを復元
        if 'managed_folders' in state_data:
            self.parent.downloader_core.managed_folders = state_data['managed_folders']
        if 'incomplete_urls' in state_data:
            self.parent.downloader_core.incomplete_urls = set(state_data['incomplete_urls'])
        
        # 完了状態の復元
        if 'completion_state' in state_data:
            completion_state = state_data['completion_state']
            self.parent.downloader_core._sequence_complete_executed = completion_state.get(
                'sequence_complete_executed', False)
            self.parent.downloader_core.current_gallery_url = completion_state.get('current_gallery_url', None)
            self.parent.downloader_core.current_image_page_url = completion_state.get('current_image_page_url', None)
            self.parent.downloader_core.current_save_folder = completion_state.get('current_save_folder', None)
            self.parent.downloader_core.current_page = completion_state.get('current_page', 0)
            self.parent.downloader_core.current_total = completion_state.get('current_total', 0)
            # 重要フラグを復元
            self.parent.downloader_core.error_occurred = completion_state.get('error_occurred', False)
            self.parent.downloader_core.gallery_completed = completion_state.get('gallery_completed', False)
            self.parent.downloader_core.skip_completion_check = completion_state.get('skip_completion_check', False)
            # バックアップ復元マーカーを設定
            self.parent.downloader_core._flags_restored_from_backup = True
        
        # Selenium状態の復元
        if 'selenium_state' in state_data:
            selenium_state = state_data['selenium_state']
            self.parent.downloader_core.selenium_enabled_for_retry = selenium_state.get('enabled_for_retry', False)
            self.parent.downloader_core.selenium_scope = selenium_state.get('scope', 'page')
            self.parent.downloader_core.selenium_enabled_url = selenium_state.get('enabled_url', None)
        
        # 圧縮状態の復元
        if 'compression_state' in state_data:
            compression_state = state_data['compression_state']
            self.parent.downloader_core._compression_in_progress = compression_state.get('in_progress', False)
            self.parent.downloader_core._compression_target_folder = compression_state.get('target_folder', None)
            self.parent.downloader_core._compression_target_url = compression_state.get('target_url', None)
        
        # StateManagerにも状態を反映
        if hasattr(self.parent.downloader_core, 'state_manager'):
            self.parent.downloader_core.state_manager.set_download_running(False)
            self.parent.downloader_core.state_manager.set_paused(True)
            self.parent.downloader_core.state_manager.set_current_url_index(self.parent.current_url_index)
        
        # 圧縮状態の特別処理
        if getattr(self.parent.downloader_core, '_compression_in_progress', False):
            self.parent.log("バックアップ復元: 圧縮処理が実行中でした。圧縮状態をリセットします。", "info")
            self.parent.downloader_core._compression_in_progress = False
            self.parent.downloader_core._compression_target_folder = None
            self.parent.downloader_core._compression_target_url = None
    
    def _restore_gui_from_state(self):
        """GUIを復元"""
        # URL背景色を更新
        if hasattr(self.parent, 'url_panel'):
            self.parent.root.after(100, self.parent.url_panel._update_all_url_backgrounds)
        
        # GUI状態を更新（再開ボタンを有効にするため）
        self.parent.root.after(200, self.parent._update_gui_state_from_thread)
