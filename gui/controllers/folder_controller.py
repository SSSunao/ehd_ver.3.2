# -*- coding: utf-8 -*-
"""
フォルダコントローラー
フォルダ選択・開く・管理機能を担当
"""

import os
import subprocess
import platform
from tkinter import filedialog


class FolderController:
    """フォルダ管理を担当するコントローラー"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderインスタンス（ILogger, IGUIOperationsを実装）
        """
        self.parent = parent
    
    def browse_folder(self):
        """フォルダを選択"""
        # 現在のフォーム値を取得
        current_folder = self.parent.folder_var.get().strip()
        initial_dir = current_folder if current_folder and os.path.exists(current_folder) else os.path.expanduser("~")
        
        folder = filedialog.askdirectory(initialdir=initial_dir)
        if folder:
            # ⭐Single Source of Truth: folder_varのみを更新（folder_pathは自動同期）⭐
            self.parent.folder_var.set(folder)
    
    def open_download_folder(self):
        """ダウンロードフォルダを開く"""
        try:
            # GUI変数からディレクトリを取得
            directory = self.parent.folder_var.get().strip()
            
            # 空の場合はエラー
            if not directory:
                self.parent.log("ダウンロードフォルダが設定されていません", "error")
                return
            
            # パス区切り文字を正規化（Windowsの場合）
            directory = directory.replace('/', '\\') if os.name == 'nt' else directory
            
            # 相対パスの場合は絶対パスに変換
            if not os.path.isabs(directory):
                directory = os.path.abspath(directory)
                self.parent.log(f"相対パスを絶対パスに変換: {directory}", "debug")
            
            # 存在確認
            if os.path.exists(directory):
                self.parent.log(f"フォルダを開きます: {directory}", "info")
                self._open_folder_os_specific(directory)
            else:
                self.parent.log(f"ダウンロードフォルダが見つかりません: {directory}", "error")
                self.parent.log(f"folder_var の値: '{self.parent.folder_var.get()}'", "debug")
        except Exception as e:
            self.parent.log(f"フォルダを開くエラー: {e}", "error")
            import traceback
            self.parent.log(f"詳細: {traceback.format_exc()}", "debug")
    
    def open_current_download_folder(self):
        """現在のダウンロードフォルダを開く"""
        try:
            # progress_panel._open_current_folder を直接呼び出す
            if (hasattr(self.parent, 'progress_panel') 
                and hasattr(self.parent.progress_panel, '_open_current_folder')):
                self.parent.progress_panel._open_current_folder()
                return
            
            # フォールバック処理
            current_folder = self._get_current_download_folder()
            
            if current_folder and os.path.exists(current_folder):
                self._open_folder_os_specific(current_folder)
                self.parent.log(f"フォルダを開きました: {current_folder}")
            else:
                self.parent.log("現在のダウンロードフォルダが設定されていません", "warning")
                
        except Exception as e:
            self.parent.log(f"ダウンロードフォルダを開くエラー: {e}", "error")
            import traceback
            traceback.print_exc()
    
    def open_folder(self, folder_path):
        """指定されたフォルダを開く"""
        try:
            # 相対パスの場合は絶対パスに変換
            if folder_path and not os.path.isabs(folder_path):
                folder_path = os.path.abspath(folder_path)
            
            if folder_path and os.path.exists(folder_path):
                self._open_folder_os_specific(folder_path)
            else:
                self.parent.log(f"フォルダが見つかりません: {folder_path}", "warning")
        except Exception as e:
            self.parent.log(f"フォルダを開くエラー: {e}", "error")
    
    def _get_current_download_folder(self):
        """現在のダウンロードフォルダを取得"""
        current_folder = None
        
        # progress_bars 配列から現在URLの保存フォルダを検索
        if (hasattr(self.parent, 'progress_panel') 
            and hasattr(self.parent.progress_panel, 'progress_bars')):
            if (hasattr(self.parent, 'downloader_core') 
                and hasattr(self.parent.downloader_core, 'current_gallery_url')):
                current_url = self.parent.downloader_core.current_gallery_url
                if current_url:
                    for progress in self.parent.progress_panel.progress_bars:
                        if progress.get('url') == current_url:
                            save_folder = progress.get('save_folder', '')
                            if save_folder and os.path.exists(save_folder):
                                current_folder = save_folder
                                break
            
            # 見つからない場合は最新のプログレスバーから取得
            if not current_folder and self.parent.progress_panel.progress_bars:
                latest_progress = self.parent.progress_panel.progress_bars[-1]
                save_folder = latest_progress.get('save_folder', '')
                if save_folder and os.path.exists(save_folder):
                    current_folder = save_folder
        
        return current_folder
    
    def _open_folder_os_specific(self, folder_path):
        """OSに応じたフォルダを開く処理"""
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(
                    ['explorer', folder_path],
                    shell=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
            elif system == "Darwin":
                subprocess.Popen(['open', folder_path], shell=False)
            else:
                subprocess.Popen(['xdg-open', folder_path], shell=False)
        except Exception as e:
            # Windows のフォールバック os.startfile
            try:
                os.startfile(folder_path)
            except Exception as startfile_error:
                self.parent.log(f"フォルダを開くのに失敗しました: {startfile_error}", "error")
                raise
