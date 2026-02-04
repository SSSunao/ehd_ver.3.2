# -*- coding: utf-8 -*-
"""
Completion Handler - ダウンロード完了処理の専門コンポーネント

責任範囲:
- ダウンロード完了時の状態管理
- GUI更新の調整
- プログレス履歴管理
- セッションクリーンアップ
"""

import time
import os
from typing import Dict, Any, Optional


class CompletionHandler:
    """ダウンロード完了処理を担当するハンドラー
    
    EHDownloaderCoreから完了処理ロジックを分離し、
    単一責任の原則に従ったクリーンな設計を実現。
    """
    
    def __init__(self, parent):
        """初期化
        
        Args:
            parent: EHDownloaderCoreインスタンス（依存性注入）
        """
        self.parent = parent
        self.state_manager = parent.state_manager
        self.session_manager = parent.session_manager
    
    def handle_url_skipped(self, normalized_url: str) -> bool:
        """スキップされたURLの処理
        
        Args:
            normalized_url: 正規化されたURL
            
        Returns:
            bool: 次のダウンロードを自動開始するか
        """
        self.session_manager.ui_bridge.post_log(f"ダウンロードがスキップされました: {normalized_url}")
        self.state_manager.set_url_status(normalized_url, "skipped")
        self.state_manager.set_skip_requested_url(None)
        
        # DLリスト通知
        if hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'download_list_widget'):
            self.parent.parent.download_list_widget.update_status(normalized_url, 'skipped')
        
        return True
    
    def handle_url_restarted(self, normalized_url: str, save_folder: str, options: Dict[str, Any]) -> bool:
        """リスタートされたURLの処理
        
        Args:
            normalized_url: 正規化されたURL
            save_folder: 保存フォルダパス
            options: ダウンロードオプション
            
        Returns:
            bool: 次のダウンロードを自動開始するか
        """
        self.session_manager.ui_bridge.post_log(f"リスタートによるダウンロードが完了しました: {normalized_url}")
        self.state_manager.set_url_status(normalized_url, "completed")
        self.parent.url_status[normalized_url] = "completed"
        self.state_manager.set_restart_requested_url(None)
        
        # DLリスト通知
        if hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'download_list_widget'):
            self.parent.parent.download_list_widget.update_status(normalized_url, 'completed')
        
        # 圧縮処理の開始
        if options.get('compression_enabled', False):
            self.parent._start_compression_task(save_folder, normalized_url)
        
        return True
    
    def _get_url_index_for_update(self, normalized_url: str) -> Optional[int]:
        """URL更新用のインデックスを取得
        
        Args:
            normalized_url: 正規化されたURL
            
        Returns:
            Optional[int]: URLインデックス、見つからない場合None
        """
        url_index = None
        
        # 1. 現在のurl_indexを取得
        if hasattr(self.parent, 'current_url_index'):
            url_index = self.parent.current_url_index
        elif hasattr(self, 'state_manager'):
            url_index = self.state_manager.get_current_url_index()
        
        # 2. URLから検索
        if url_index is None or url_index < 0:
            all_progress_bars = self.state_manager.get_all_progress_bars()
            for idx, progress in all_progress_bars.items():
                if progress.get('url') == normalized_url:
                    url_index = idx
                    break
        
        return url_index
    
    def _update_progress_status(self, url_index: int, status_label: str):
        """プログレスバーのステータスを更新
        
        Args:
            url_index: URLインデックス
            status_label: ステータスラベル（"完了"、"エラー"等）
        """
        try:
            progress_info = self.state_manager.get_progress_bar(url_index)
            if progress_info:
                # ⭐修正: progress_infoがProgressInfoオブジェクトか辞書かをチェック⭐
                if hasattr(progress_info, 'current'):
                    # ProgressInfoオブジェクトの場合
                    current = progress_info.current
                    total = progress_info.total
                    start_time = getattr(progress_info, 'start_time', None)
                else:
                    # 辞書の場合（後方互換性）
                    current = progress_info.get('state', {}).get('current', 0) if isinstance(progress_info.get('state'), dict) else 0
                    total = progress_info.get('state', {}).get('total', 0) if isinstance(progress_info.get('state'), dict) else 0
                    start_time = progress_info.get('start_time')
                
                elapsed_str = ""
                if start_time:
                    elapsed_time = time.time() - start_time
                    elapsed_str = f"{int(elapsed_time//60):02d}:{int(elapsed_time%60):02d}"
                
                # ステータステキスト生成
                if current > 0 and total > 0 and elapsed_str:
                    status_text = f"ページ {current}/{total} | 経過: {elapsed_str} | 状態: {status_label}"
                elif current > 0 and total > 0:
                    status_text = f"ページ {current}/{total} | 状態: {status_label}"
                else:
                    status_text = f"状態: {status_label}"
                
                self.state_manager.update_progress_bar_state(url_index, status=status_text)
            else:
                self.state_manager.update_progress_bar_state(url_index, status=f"状態: {status_label}")
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ステータス更新エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"詳細: {traceback.format_exc()}", "debug")
    
    def handle_url_completed_successfully(self, normalized_url: str, save_folder: str, options: Dict[str, Any]) -> bool:
        """正常完了時のURL処理
        
        Args:
            normalized_url: 正規化されたURL
            save_folder: 保存フォルダパス
            options: ダウンロードオプション
            
        Returns:
            bool: 次のダウンロードを自動開始するか
        """
        # スキップまたは停止確認
        current_status = self.state_manager.get_url_status(normalized_url)
        if current_status in ['skipped', 'user_stopped']:
            reason = "スキップ" if current_status == 'skipped' else "停止"
            self.session_manager.ui_bridge.post_log(f"{reason}されたURLのため完了処理をスキップ: {normalized_url}")
            return True
        
        self.session_manager.ui_bridge.post_log(f"ダウンロードが完了しました: {normalized_url}")
        
        # ステータス更新
        if current_status != 'skipped':
            self.state_manager.set_url_status(normalized_url, "completed")
            self.state_manager.clear_resume_point(normalized_url)
        
        # DLリスト通知
        if hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'download_list_widget'):
            self.parent.parent.download_list_widget.update_status(normalized_url, 'completed')
        
        # GUI更新
        url_index = self._get_url_index_for_update(normalized_url)
        if url_index is not None and url_index >= 0:
            self._update_progress_status(url_index, "完了")
        
        # リトライカウンターとエラー状態をクリア
        if hasattr(self.parent, 'auto_retry_count') and normalized_url in self.parent.auto_retry_count:
            del self.parent.auto_retry_count[normalized_url]
        
        if hasattr(self.parent, 'error_info') and self.parent.error_info.get('has_error', False):
            self.parent.error_info['has_error'] = False
        
        # 未完了チェックと圧縮処理
        url_status = self.state_manager.get_url_status(normalized_url)
        if url_status in ["error", "incomplete"]:
            self._handle_incomplete_folder(normalized_url, save_folder)
            return True
        
        # ⭐修正: 圧縮処理はCompletionCoordinatorに移行⭐
        
        # 最新フォルダ更新
        if save_folder and os.path.exists(save_folder) and url_status != "skipped":
            self.parent.last_download_folder = save_folder
            self.parent.managed_folders[normalized_url] = save_folder
        
        # プログレス履歴追加
        self._add_progress_history(normalized_url)
        
        # クリーンアップ
        self._cleanup_download_session()
        
        # ⭐修正: インデックスのインクリメントは_handle_download_completion内で行う⭐
        # （次のURL判定と同時に行うため）
        
        return True
    
    def _handle_incomplete_folder(self, normalized_url: str, save_folder: str):
        """未完了フォルダの処理
        
        Args:
            normalized_url: 正規化されたURL
            save_folder: 保存フォルダパス
        """
        url_status = self.state_manager.get_url_status(normalized_url)
        self.session_manager.ui_bridge.post_log(
            f"【完了処理】未完了状態のため、圧縮処理をスキップ: {normalized_url} (status: {url_status})"
        )
        
        if self.parent.rename_incomplete_folder.get() and save_folder:
            try:
                if not hasattr(self.parent, 'incomplete_folders'):
                    self.parent.incomplete_folders = set()
                self.parent.incomplete_folders.add(save_folder)
                self.session_manager.ui_bridge.post_log(f"[DEBUG] 未完了フォルダを記録: {save_folder}")
            except Exception as rename_error:
                self.session_manager.ui_bridge.post_log(f"未完了フォルダ記録エラー: {rename_error}", "warning")
    
    def _add_progress_history(self, normalized_url: str):
        """プログレス履歴に追加
        
        Args:
            normalized_url: 正規化されたURL
        """
        if not hasattr(self.parent, 'backup_manager'):
            return
        
        current_url_index = self.state_manager.get_current_url_index()
        all_progress_bars = self.state_manager.get_all_progress_bars()
        
        # 経過時間計算
        elapsed_time = 0
        start_time = self.state_manager.get_elapsed_time_start()
        if start_time:
            elapsed_time = time.time() - start_time
        else:
            elapsed_time = self.state_manager.get_total_elapsed_seconds()
        
        # プログレスバー情報から取得
        if current_url_index in all_progress_bars:
            progress_info = all_progress_bars[current_url_index]
            self.parent.backup_manager.add_progress_info({
                'url': normalized_url,
                'title': progress_info.get('title', getattr(self.parent, 'current_gallery_title', '')),
                'current': progress_info.get('current', 0),
                'total': progress_info.get('total', 0),
                'status': progress_info.get('status', self.state_manager.get_url_status(normalized_url)),
                'timestamp': time.time(),
                'elapsed_time': progress_info.get('elapsed_time', elapsed_time)
            })
        else:
            # フォールバック
            self.parent.backup_manager.add_progress_info({
                'url': normalized_url,
                'title': getattr(self.parent, 'current_gallery_title', ''),
                'current': getattr(self.parent, 'current_progress', 0),
                'total': getattr(self.parent, 'current_total', 0),
                'status': self.state_manager.get_url_status(normalized_url),
                'timestamp': time.time(),
                'elapsed_time': elapsed_time
            })
    
    def _cleanup_download_session(self):
        """ダウンロードセッションのクリーンアップ"""
        # スレッド状態をクリア
        self.state_manager.set_download_thread(None)
        self.parent.current_gallery_url = None
        self.parent.current_image_page_url = None
        
        # セッションをクリア
        if hasattr(self.parent, 'session'):
            try:
                self.parent.session.close()
            except:
                pass
            self.parent.session = None
        
        # プログレスバーのクリーンアップ
        if not hasattr(self.parent, 'error_occurred') or not self.parent.error_occurred:
            self.parent.progress_cleanup_needed = True
        
        # ダウンロードマネージャーOFF時の処理
        if not (hasattr(self.parent, 'progress_separate_window_enabled') and 
                self.parent.progress_separate_window_enabled.get()):
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel._show_latest_progress_in_main_window()
