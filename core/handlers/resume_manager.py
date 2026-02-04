# -*- coding: utf-8 -*-
"""
Resume Manager - 中断・再開処理の専門コンポーネント

責任範囲:
- 中断要求の検出と処理
- 再開ポイントの管理
- pause/resume状態の制御
"""

from typing import Dict, Any, Optional


class ResumeManager:
    """中断・再開処理を担当するマネージャー
    
    StateManagerとUnifiedErrorResumeManagerに分散していた
    中断・再開ロジックを統合し、責任を明確化。
    """
    
    def __init__(self, parent):
        """初期化
        
        Args:
            parent: EHDownloaderCoreインスタンス（依存性注入）
        """
        self.parent = parent
        self.state_manager = parent.state_manager
        self.session_manager = parent.session_manager
        self.unified_manager = parent.parent.unified_error_resume_manager
    
    def check_interrupt_request(self, normalized_url: str, url: Optional[str] = None) -> Optional[str]:
        """統一的な中断要求チェック
        
        優先順位: skip > restart > pause > stop
        
        Args:
            normalized_url: 正規化されたURL
            url: 元のURL (オプション)
            
        Returns:
            str: 中断タイプ ('skip', 'restart', 'pause', 'stop') または None
        """
        # 優先順位1: スキップ要求
        skip_requested_url = self.state_manager.get_skip_requested_url()
        if skip_requested_url and (skip_requested_url == normalized_url or (url and skip_requested_url == url)):
            return 'skip'
        
        # 優先順位2: リスタート要求
        restart_requested_url = self.state_manager.get_restart_requested_url()
        if restart_requested_url == normalized_url:
            return 'restart'
        
        # 優先順位3: 中断要求
        if self.state_manager.is_pause_requested():
            return 'pause'
        
        # 優先順位4: 停止要求
        if self.state_manager.get_stop_flag().is_set():
            return 'stop'
        
        return None
    
    def handle_interrupt_request(self, interrupt_type: str, normalized_url: str, current_page: int,
                                 save_folder: str, download_range_info: Optional[Dict] = None,
                                 absolute_page: Optional[int] = None, url: Optional[str] = None,
                                 actual_total_pages: Optional[int] = None, reason_suffix: str = ""):
        """統一的な中断要求処理
        
        Args:
            interrupt_type: 中断タイプ ('skip', 'restart', 'pause', 'stop')
            normalized_url: 正規化されたURL
            current_page: 現在のページ番号（相対）
            save_folder: 保存フォルダ
            download_range_info: ダウンロード範囲情報
            absolute_page: 絶対ページ番号
            url: 元のURL
            actual_total_pages: 実際の総ページ数
            reason_suffix: ログメッセージの追加情報
        """
        # URL単位のダウンロード範囲を取得
        url_download_range = self.state_manager.get_url_download_range(normalized_url) if hasattr(self.state_manager, 'get_url_download_range') else {'enabled': False}
        
        # 保存用ページ番号を決定
        if url_download_range.get('enabled') and absolute_page is not None:
            save_page = absolute_page
        else:
            save_page = current_page
        
        if interrupt_type == 'skip':
            self._handle_skip(normalized_url, current_page, save_folder, reason_suffix)
        elif interrupt_type == 'restart':
            self._handle_restart(normalized_url, save_page, save_folder, current_page, reason_suffix)
        elif interrupt_type == 'pause':
            self._handle_pause(normalized_url, save_page, save_folder, current_page, reason_suffix)
        elif interrupt_type == 'stop':
            self._handle_stop(normalized_url, save_page, save_folder, current_page, reason_suffix)
    
    def _handle_skip(self, normalized_url: str, current_page: int, save_folder: str, reason_suffix: str):
        """スキップ処理"""
        self.session_manager.ui_bridge.post_log(f"画像 {current_page}: スキップ要求により中断{reason_suffix}")
        
        # URL状態を設定
        self.state_manager.set_url_status(normalized_url, 'skipped')
        
        # 未完了フォルダを記録
        if save_folder and self.parent.parent.rename_incomplete_folder.get():
            if not hasattr(self.parent, 'incomplete_folders'):
                self.parent.incomplete_folders = set()
            self.parent.incomplete_folders.add(save_folder)
        
        # current_url_indexをインクリメント
        current_index = self.state_manager.get_current_url_index()
        if current_index is not None:
            self.state_manager.set_current_url_index(current_index + 1)
        
        # 復帰ポイントをクリア
        self.state_manager.clear_resume_point(normalized_url)
        
        # 完了チェックをスキップするフラグを設定
        self.parent.skip_completion_check = True
    
    def _handle_restart(self, normalized_url: str, save_page: int, save_folder: str,
                       current_page: int, reason_suffix: str):
        """リスタート処理"""
        self.session_manager.ui_bridge.post_log(f"画像 {current_page}: リスタート要求により中断{reason_suffix}")
        self._save_resume_point(normalized_url, save_page, save_folder, 
                               stage='image_info', sub_stage='after', reason="restart")
    
    def _handle_pause(self, normalized_url: str, save_page: int, save_folder: str,
                     current_page: int, reason_suffix: str):
        """一時停止処理"""
        self.session_manager.ui_bridge.post_log(f"画像 {current_page}: 中断要求により一時停止{reason_suffix}")
        self._save_resume_point(normalized_url, save_page, save_folder, 
                               stage='image_info', sub_stage='after', reason="pause")
    
    def _handle_stop(self, normalized_url: str, save_page: int, save_folder: str,
                    current_page: int, reason_suffix: str):
        """停止処理"""
        self.session_manager.ui_bridge.post_log(f"画像 {current_page}: 停止要求により中断{reason_suffix}")
        self._save_resume_point(normalized_url, save_page, save_folder, 
                               stage='image_info', sub_stage='after', reason="stop")
    
    def _save_resume_point(self, url: str, current_page: int, save_folder: str,
                          stage: str = 'image_info', sub_stage: str = 'after',
                          reason: str = "interrupt"):
        """再開ポイントを保存
        
        Args:
            url: URL
            current_page: 現在のページ
            save_folder: 保存フォルダ
            stage: 処理段階
            sub_stage: サブ段階
            reason: 保存理由
        """
        # UnifiedErrorResumeManagerに委譲
        self.unified_manager.save_resume_point(
            url=url,
            page=current_page,
            folder=save_folder,
            stage=stage,
            sub_stage=sub_stage,
            reason=reason
        )
    
    def get_resume_point(self, url: str) -> Optional[Dict[str, Any]]:
        """再開ポイントを取得
        
        Args:
            url: URL
            
        Returns:
            Dict: 再開ポイント情報 または None
        """
        return self.state_manager.get_resume_point(url)
    
    def clear_resume_point(self, url: str):
        """再開ポイントをクリア
        
        Args:
            url: URL
        """
        self.state_manager.clear_resume_point(url)
