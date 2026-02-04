# -*- coding: utf-8 -*-
"""
ダウンロードコントローラー
ダウンロード開始・停止・一時停止・再開・スキップなどのビジネスロジックを管理
"""

import re
import tkinter as tk


class DownloadController:
    """ダウンロード制御を担当するコントローラー"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderインスタンス（IStateManager, ILogger, IGUIOperationsを実装）
        """
        self.parent = parent
        self._pause_processing = False
    
    def start_download_sequence(self):
        """ダウンロードシーケンスを開始"""
        try:
            # ユーザー操作を登録
            if hasattr(self.parent, 'enhanced_error_handler'):
                self.parent.enhanced_error_handler.register_user_operation("start")
            
            # オプションを読み込み
            self.parent._load_options_for_download()
            
            # 既に実行中の場合は警告
            is_running = (self.parent.downloader_core.state_manager.is_download_running() 
                         if hasattr(self.parent, 'downloader_core') 
                         and hasattr(self.parent.downloader_core, 'state_manager') 
                         else False)
            if is_running:
                self.parent.log("ダウンロードは既に実行中です", "warning")
                return
            
            # ⭐修正: TreeviewからURL配列を取得⭐
            urls = []
            total_urls = 0
            
            # まずTreeviewから取得を試みる
            if hasattr(self.parent, 'download_list_widget'):
                urls = self.parent.download_list_widget.get_pending_urls()
                total_urls = len(urls)
                print(f"[DEBUG] Treeviewから取得したURL数: {total_urls}")  # デバッグ
                if urls:
                    print(f"[DEBUG] 最初のURL: {urls[0][:50]}...")  # デバッグ
            
            # Treeviewが空の場合、TextウィジェットからURL同期を試みる
            if total_urls == 0 and hasattr(self.parent, 'url_text'):
                text_content = self.parent.url_text.get("1.0", tk.END)
                urls_to_sync = self._parse_urls_from_text(text_content)
                print(f"[DEBUG] Textから解析したURL数: {len(urls_to_sync)}")  # デバッグ
                
                if urls_to_sync and hasattr(self.parent, 'download_list_widget'):
                    # Treeviewに追加
                    for url in urls_to_sync:
                        self.parent.download_list_widget.add_url(url)
                    urls = urls_to_sync
                    total_urls = len(urls)
                    self.parent.log(f"📥 {total_urls}件のURLをTreeviewに同期しました", "info")
            
            if total_urls == 0:
                self.parent.log("ダウンロードするURLが指定されていません", "warning")
                return
            
            # ダウンロードマネージャーの表示モード制御
            self._handle_download_manager_display()
            
            # URL進捗を初期化
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel.update_url_progress(0, total_urls)
            
            # downloader_coreに処理を委譲
            if hasattr(self.parent, 'downloader_core') and self.parent.downloader_core is not None:
                self.parent.downloader_core.start_download_sequence()
                # ⭐追加: ボタン状態を更新⭐
                self.parent._update_button_states_unified('downloading')
                self.parent._update_gui_state_from_thread()
            else:
                self.parent.log("ダウンローダーコアが初期化されていません", "error")
                if (hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'state_manager')):
                    self.parent.downloader_core.state_manager.set_download_running(False)
                self.parent._update_gui_state_from_thread()

        except Exception as e:
            self.parent.log(f"ダウンロード開始エラー: {e}", "error")
            import traceback
            traceback.print_exc()
            if (hasattr(self.parent, 'downloader_core') 
                and hasattr(self.parent.downloader_core, 'state_manager')):
                self.parent.downloader_core.state_manager.set_download_running(False)
            self.parent._update_gui_state_from_thread()
    
    def _handle_download_manager_display(self):
        """ダウンロードマネージャーの表示モードを制御"""
        if (hasattr(self.parent, 'progress_separate_window_enabled') 
            and self.parent.progress_separate_window_enabled.get()):
            # ダウンロードマネージャーON: サブウィンドウを開く
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel.switch_progress_display_mode()
                if hasattr(self.parent, 'options_panel'):
                    self.parent.options_panel._update_download_manager_button_state()
        else:
            # ダウンロードマネージャーOFF: メインウィンドウ表示モード
            if hasattr(self.parent, 'progress_panel'):
                self.parent.progress_panel.switch_progress_display_mode()
                if hasattr(self.parent, 'options_panel'):
                    self.parent.options_panel._update_download_manager_button_state()
                # 既存のプログレスバーがあれば表示
                progress_bars = self.parent.progress_panel._get_progress_bars()
                if progress_bars:
                    self.parent.progress_panel._show_latest_progress_in_main_window()
    
    def _parse_urls_from_text(self, text):
        """テキストからURLをパースする"""
        urls = []
        
        for line in text.splitlines():
            line = line.strip()
            
            # @マークやマーカーを除去
            line = re.sub(r'^@', '', line)
            line = re.sub(r'\u200B?\(リサイズ完了\)', '', line)
            line = re.sub(r'\u200B?（圧縮完了）', '', line)
            
            if line and self._is_valid_eh_url(line):
                # 個別画像ページURLの場合は正規化せずにそのまま渡す
                if re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', line):
                    urls.append(line)
                else:
                    normalized = self.parent.normalize_url(line)
                    if normalized:
                        urls.append(normalized)
        
        return urls
    
    def _is_valid_eh_url(self, url):
        """有効なE-Hentai URLかチェック"""
        return bool(re.match(r'https?://(e-hentai|exhentai)\.org/', url))
    
    def pause_download(self):
        """ダウンロードを一時停止"""
        # 連打防止
        if self._pause_processing:
            self.parent.log("中断処理中です。しばらくお待ちください。", "warning")
            return
        
        self._pause_processing = True
        
        try:
            is_running = (self.parent.downloader_core.state_manager.is_download_running() 
                         if hasattr(self.parent, 'downloader_core') 
                         and hasattr(self.parent.downloader_core, 'state_manager') 
                         else False)
            is_paused = (self.parent.downloader_core.state_manager.is_paused() 
                        if hasattr(self.parent, 'downloader_core') 
                        and hasattr(self.parent.downloader_core, 'state_manager') 
                        else False)
            
            if is_running and not is_paused:
                # 中断要求フラグを設定
                if (hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'state_manager')):
                    self.parent.downloader_core.state_manager.set_pause_requested(True)
                    self.parent.downloader_core.state_manager.set_paused(True)
                
                # ⭐追加: 経過時間タイマーを停止⭐
                if hasattr(self.parent, 'progress_panel') and hasattr(self.parent.progress_panel, '_stop_elapsed_time_timer'):
                    self.parent.progress_panel._stop_elapsed_time_timer()
                
                self.parent.log("ダウンロードを一時停止します...", "info")
                self.parent._update_gui_state_from_thread()
        finally:
            self._pause_processing = False
    
    def resume_download(self):
        """ダウンロードを再開"""
        try:
            is_paused = (self.parent.downloader_core.state_manager.is_paused() 
                        if hasattr(self.parent, 'downloader_core') 
                        and hasattr(self.parent.downloader_core, 'state_manager') 
                        else False)
            
            if is_paused:
                # 中断解除フラグを設定
                if (hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'state_manager')):
                    self.parent.downloader_core.state_manager.set_paused(False)
                    self.parent.downloader_core.state_manager.set_pause_requested(False)
                
                self.parent.log("ダウンロードを再開します", "info")
                self.parent._update_gui_state_from_thread()
        except Exception as e:
            self.parent.log(f"ダウンロード再開エラー: {e}", "error")
            import traceback
            traceback.print_exc()
    
    def stop_download(self):
        """ダウンロードを停止"""
        is_running = (self.parent.downloader_core.state_manager.is_download_running() 
                     if hasattr(self.parent, 'downloader_core') 
                     and hasattr(self.parent.downloader_core, 'state_manager') 
                     else False)
        
        if is_running:
            # StateManagerで状態を管理
            if (hasattr(self.parent, 'downloader_core') 
                and hasattr(self.parent.downloader_core, 'state_manager')):
                self.parent.downloader_core.state_manager.set_download_running(False)
                self.parent.downloader_core.state_manager.set_paused(False)
            
            # GUIを更新
            self.parent._update_gui_state_from_thread()
            
            self.parent.log("ダウンロードを停止しました", "info")
    
    def restart_download(self):
        """現在のURLをリスタート（軽度エラーのタイムラグキャンセル対応）"""
        # ⭐追加: 連打防止⭐
        if hasattr(self, '_restart_in_progress') and self._restart_in_progress:
            self.parent.log("リスタート処理実行中です。しばらくお待ちください。", "warning")
            return
        
        # オプションを読み込み
        self.parent._load_options_for_download()
        
        # リスタート可能かチェック
        if (not hasattr(self.parent.downloader_core, 'current_gallery_url') 
            or not self.parent.downloader_core.current_gallery_url):
            self.parent.log("リスタート可能なダウンロードがありません", "warning")
            return
        
        restart_url = self.parent.downloader_core.current_gallery_url
        self.parent.log(f"ダウンロードを最初からやり直します: {restart_url}")
        
        # ⭐追加: 連打防止フラグを設定⭐
        self._restart_in_progress = True
        
        # リスタート要求を設定
        if hasattr(self.parent.downloader_core, 'restart_requested_url'):
            self.parent.downloader_core.restart_requested_url = restart_url
        
        # URL状態をdownloadingに戻す
        self.parent.state_manager.set_url_status(restart_url, "downloading")
        
        # URL背景色を更新
        if hasattr(self.parent, 'url_panel'):
            self.parent.url_panel.update_url_background(restart_url)
        
        # ⭐修正: ダウンローダーコアのリスタート処理を非同期で呼び出し⭐
        def restart_async():
            try:
                if hasattr(self.parent.downloader_core, 'restart_current_url'):
                    self.parent.downloader_core.restart_current_url()
                
                # リスタート後は実行中状態に更新
                if (hasattr(self.parent, 'options_panel') 
                    and hasattr(self.parent.options_panel, '_update_gui_for_running')):
                    self.parent.root.after(0, self.parent.options_panel._update_gui_for_running)
                
                self.parent.log("リスタート処理を開始しました", "info")
            finally:
                # ⭐追加: 連打防止フラグを解除⭐
                self._restart_in_progress = False
        
        # 非同期実行
        if hasattr(self.parent, 'async_executor'):
            self.parent.async_executor.execute_in_thread(restart_async)
        else:
            import threading
            threading.Thread(target=restart_async, daemon=True).start()
    
    def skip_current_download_manual(self):
        """手動スキップ専用の統一処理"""
        try:
            # 現在のURLを取得
            current_url = None
            if (hasattr(self.parent.downloader_core, 'current_gallery_url') 
                and self.parent.downloader_core.current_gallery_url):
                current_url = self.parent.downloader_core.current_gallery_url
            elif hasattr(self.parent.downloader_core, 'state_manager'):
                current_url = self.parent.downloader_core.state_manager.get_current_gallery_url()
            
            if not current_url:
                self.parent.log("スキップするURLが見つかりません", "warning")
                return False
            
            self.parent.log(f"手動スキップ処理開始: {current_url}")
            
            # 完了処理スキップフラグを設定（競合防止）
            if hasattr(self.parent.downloader_core, 'skip_completion_check'):
                self.parent.downloader_core.skip_completion_check = True
                self.parent.log("完了処理スキップフラグを設定（競合防止）")
            
            # ⭐修正: 停止フラグを設定（skip_completion_checkで完了処理を区別）⭐
            if hasattr(self.parent.downloader_core, 'state_manager'):
                self.parent.downloader_core.state_manager.set_stop_flag()
                self.parent.log("停止フラグを設定してダウンロードループ脱出を要求（スキップ）")
            
            # URL状態を「スキップ」に設定
            if hasattr(self.parent, 'state_manager'):
                self.parent.state_manager.set_url_status(current_url, "skipped")
                self.parent.log(f"URL状態を「スキップ」に設定: {current_url}")
            
            # URL背景色を更新
            if hasattr(self.parent, 'url_panel'):
                self.parent.url_panel.update_url_background(current_url)
            
            self.parent.log(f"手動スキップ完了: {current_url}", "info")
            return True
            
        except Exception as e:
            self.parent.log(f"手動スキップエラー: {e}", "error")
            import traceback
            traceback.print_exc()
            return False
    
    def toggle_pause_resume(self):
        """一時停止/再開をトグル"""
        is_paused = (self.parent.downloader_core.state_manager.is_paused() 
                    if hasattr(self.parent, 'downloader_core') 
                    and hasattr(self.parent.downloader_core, 'state_manager') 
                    else False)
        
        if is_paused:
            self.resume_download()
        else:
            self.pause_download()
