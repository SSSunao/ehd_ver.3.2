# -*- coding: utf-8 -*-
"""
Gallery downloader module - ギャラリーダウンロード処理の分離
_download_gallery_pagesメソッドを機能別に分割
"""

import os
import time
import threading
from typing import Optional, Dict, Any

from config.settings import SkipUrlException, DownloadErrorException, FolderMissingException
from core.utils.validation import require_not_none, safe_str, validate_url, validate_index
from core.utils.contracts import require
from core.errors.error_context import ErrorContext
from core.errors.enhanced_error_handler import FinalAction


class GalleryDownloader:
    """ギャラリーダウンロード処理を担当するクラス"""
    
    def __init__(self, core_downloader):
        """
        Args:
            core_downloader: EHDownloaderCoreインスタンス（親クラス）
        """
        self.core = core_downloader
        self.parent = core_downloader.parent
        self.state_manager = core_downloader.state_manager
        self.session_manager = core_downloader.session_manager
        # ⭐Phase1.1: ProgressTracker参照を追加⭐
        self.progress_tracker = core_downloader.progress_tracker
    
    def download_gallery_pages(
        self,
        save_folder: str,
        start_page: int,
        total_pages: int,
        url: str,
        wait_time_value: float,
        sleep_value_sec: float,
        save_format_option: str,
        save_name_option: str,
        custom_name_format: str,
        resize_mode: str,
        resize_values: dict,
        manga_title: str,
        options: dict,
        parent=None,
        gallery_info: Optional[Dict[str, Any]] = None,
    ):
        """
        ギャラリーダウンロードのメインエントリ。
        Args:
            save_folder: 保存先フォルダ
            start_page: 開始ページ
            total_pages: 総ページ数
            url: ギャラリーURL
            wait_time_value: 待機時間
            sleep_value_sec: スリープ時間
            save_format_option: 保存形式
            save_name_option: ファイル名オプション
            options: ダウンロードオプション
            parent: 親オブジェクト
        Returns:
            bool: 成功時True、失敗時False、スキップ時None
        Raises:
            ValueError: 引数が不正な場合
            SkipUrlException: URLをスキップする場合
            FolderMissingException: フォルダが見つからない場合
        """
        # ...本来のロジック・UIBridgeへのpost_log・エラーハンドリングのみ...
        import threading
        thread_id = threading.current_thread().ident
        # urlがNoneなら即return（全体完了時の誤呼び出し対策）
        if url is None:
            self.session_manager.ui_bridge.post_log("[DEBUG] url is Noneのためdownload_gallery_pagesを即return", "debug")
            return
        thread_name = threading.current_thread().name
        self.session_manager.ui_bridge.post_log(f"[DEBUG] download_gallery_pages()開始: thread_id={thread_id}, thread_name={thread_name}, url={url[:80]}")
        
        # フラグリセット（StateManager経由に統一）
        self.state_manager.download_state.skip_completion_check = False
        self.state_manager.download_state.error_occurred = False
        
        # オプション取得
        if options is None:
            options = self.core._get_current_options()
        
        normalized_gallery_url = self.parent.normalize_url(url)
        
        # ギャラリー情報取得・検証
        gallery_info = self._fetch_and_validate_gallery_info(
            url, normalized_gallery_url, save_folder, options, gallery_info
        )
        if gallery_info is None:
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] gallery_infoがNoneのためreturn: url={url}, normalized_gallery_url={normalized_gallery_url}",
                "debug"
            )
            return  # 取得失敗・スキップ
        
        # コンテキスト初期化
        from core.communication.download_context import DownloadContext
        context: DownloadContext = self._initialize_gallery_context(
            gallery_info, normalized_gallery_url, save_folder, 
            start_page, options
        )
        if context is None:
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] contextがNoneのためreturn: url={url}, normalized_gallery_url={normalized_gallery_url}, gallery_info={gallery_info}",
                "debug"
            )
            return  # 範囲エラー・スキップ

        # タイトルをStateManager経由で保存
        url_index = self.state_manager.get_current_url_index()
        if url_index is not None:
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] ProgressBar初期化直前: url_index={url_index}, context.total_pages={context.total_pages}, len(context.download_image_urls)={len(context.download_image_urls)}",
                "debug"
            )
            self.state_manager.set_progress_bar_title(url_index, gallery_info.get('title', 'Unknown'))

        # ⭐Phase1.1: ProgressTracker経由でプログレス初期化⭐
        self._initialize_progress_with_tracker(
            context.start_page,
            context.total_pages,
            context.applied_range,
            normalized_gallery_url,
            gallery_info.get('title', 'Unknown')
        )
        
        # 追加デバッグ: ループ条件の内容を出力
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] download_gallery_pages直後: download_image_urls={context.download_image_urls[:3]}... (len={len(context.download_image_urls)}), start_page={context.start_page}, total_pages={context.total_pages}",
            "debug"
        )
        # ループ突入前のデバッグ
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] 画像DLループ呼び出し直前: context={context}, url={url}, normalized_gallery_url={normalized_gallery_url}, save_folder={save_folder}, start_page={start_page}, total_pages={total_pages}",
            "debug"
        )
        # ループ条件のデバッグ
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] ループ条件: len(context.download_image_urls)={len(context.download_image_urls)}, context.start_page={context.start_page}, context.total_pages={context.total_pages}",
            "debug"
        )
        # 画像ダウンロードループ実行
        try:
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _execute_image_download_loop呼び出し", "debug"
            )
            self._execute_image_download_loop(
                context, url, normalized_gallery_url, save_folder,
                wait_time_value, sleep_value_sec, save_format_option,
                save_name_option, custom_name_format, resize_mode,
                resize_values, manga_title, options, gallery_info
            )
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _execute_image_download_loop終了", "debug"
            )
        except (SkipUrlException, FolderMissingException) as e:
            # URLスキップ・フォルダエラーは上位で処理
            raise
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"画像ダウンロードループでエラー: {e}", "error"
            )
            import traceback
            self.session_manager.ui_bridge.post_log(
                f"詳細: {traceback.format_exc()}", "error"
            )
            raise
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] download_gallery_pages末尾: 画像DLループ後まで到達", "debug"
        )
        # 完了処理チェーンのデバッグ
        try:
            self.session_manager.ui_bridge.post_log("[DEBUG] 完了処理開始: _finalize_download呼び出し直前", "debug")
            self.core._finalize_download(url, save_folder, options)
            self.session_manager.ui_bridge.post_log("[DEBUG] 完了処理終了: _finalize_download呼び出し直後", "debug")
        except Exception as e:
            import traceback
            self.session_manager.ui_bridge.post_log(f"[ERROR] 完了処理で例外: {e}", "error")
            self.session_manager.ui_bridge.post_log(f"[ERROR] 完了処理トレース: {traceback.format_exc()}", "error")
        try:
            self.session_manager.ui_bridge.post_log("[DEBUG] 次URL遷移開始: _schedule_next_download呼び出し直前", "debug")
            self.core._schedule_next_download("完了処理後")
            self.session_manager.ui_bridge.post_log("[DEBUG] 次URL遷移終了: _schedule_next_download呼び出し直後", "debug")
        except Exception as e:
            import traceback
            self.session_manager.ui_bridge.post_log(f"[ERROR] 次URL遷移で例外: {e}", "error")
            self.session_manager.ui_bridge.post_log(f"[ERROR] 次URL遷移トレース: {traceback.format_exc()}", "error")
        
        # ダウンロード完了処理
        try:
            # ⭐修正: スキップ時は完了処理をスキップして次のURLへ⭐
            if self.state_manager.download_state.skip_completion_check:
                self.session_manager.ui_bridge.post_log(f"スキップされたURLのため完了処理をスキップして次のURLへ: {normalized_gallery_url}")
                # ⭐修正: download_threadをクリアして次のURLダウンロードを許可⭐
                self.state_manager.set_download_thread(None)
                # フラグをリセット
                self.state_manager.reset_stop_flag()
                self.state_manager.download_state.skip_completion_check = False
                # 次のURLをスケジュール
                self.core._schedule_next_download("スキップ完了")
                return  # ⭐早期リターンで完了処理をスキップ⭐
            
            # ⭐修正: 画像スキップ時の未完了処理⭐
            has_skipped_images = getattr(context, 'has_skipped_images', False)
            if has_skipped_images:
                self.session_manager.ui_bridge.post_log(
                    f"画像スキップが発生したため、未完了としてマークします: {normalized_gallery_url}",
                    "warning"
                )
                # DLリストを未完了としてマーク
                if hasattr(self.parent, 'download_list_widget'):
                    actual_total_pages = getattr(context, 'actual_total_pages', 0)
                    if actual_total_pages > 0:
                        self.parent.download_list_widget.update_progress(normalized_gallery_url, actual_total_pages, actual_total_pages)
                    # ステータスを'incomplete'に設定（画像スキップ発生）
                    self.parent.download_list_widget.update_status(normalized_gallery_url, 'pending')
                
                # 未完了フォルダとして記録
                if save_folder and self.parent.rename_incomplete_folder.get():
                    if not hasattr(self.core, 'incomplete_folders'):
                        self.core.incomplete_folders = set()
                    self.core.incomplete_folders.add(save_folder)
                
                # プログレスバーのis_completedをFalseに設定
                current_url_index = self.state_manager.get_current_url_index()
                if current_url_index is not None:
                    progress_info = self.state_manager.get_progress_bar(current_url_index)
                    if progress_info:
                        progress_info.is_completed = False
            
            # ⭐修正: ダウンロード情報を保存⭐
            if hasattr(self.core, 'gallery_info_manager'):
                self.core.gallery_info_manager.save_gallery_completion_info(
                    url, save_folder, gallery_info
                )
            
            # ⭐Phase10: CompletionCoordinatorに完了処理を委譲（同期的に実行）⭐
            from core.coordination.completion_coordinator import CompletionContext
            
            completion_context = CompletionContext(
                url=url,
                save_folder=save_folder,
                options=options,
                actual_total_pages=getattr(context, 'actual_total_pages', 0),
                has_errors=getattr(context, 'has_skipped_images', False)
            )
            
            # ⭐修正: 完了処理を非同期で実行（GUIスレッドのブロッキングを防ぐ）⭐
            def _handle_completion_async():
                import threading
                print(f"[DEBUG] gallery_downloader: _handle_completion_async開始 (thread_id={{}} thread_name={{}})".format(
                    threading.current_thread().ident, threading.current_thread().name))
                try:
                    print("[DEBUG] gallery_downloader: CompletionCoordinator.handle_completion呼び出し直前")
                    self.core.completion_coordinator.handle_completion(completion_context)
                    print("[DEBUG] gallery_downloader: CompletionCoordinator.handle_completion呼び出し直後")
                except Exception as e:
                    self.session_manager.ui_bridge.post_log(
                        f"完了処理エラー: {e}",
                        "error"
                    )
                    import traceback
                    self.session_manager.ui_bridge.post_log(
                        f"詳細: {traceback.format_exc()}",
                        "error"
                    )
                print("[DEBUG] gallery_downloader: _handle_completion_async終了")
            # 非同期で実行
            if hasattr(self.parent, 'async_executor'):
                print("[DEBUG] gallery_downloader: async_executor経由で_completion_asyncをスレッド実行")
                self.parent.async_executor.execute_in_thread(_handle_completion_async)
            else:
                import threading
                print("[DEBUG] gallery_downloader: threading.Threadで_completion_asyncをスレッド実行")
                threading.Thread(target=_handle_completion_async, daemon=True).start()
            print("[DEBUG] download_gallery_pages: return True直前")
            
            # 次のURLへ進む
            print("[DEBUG] download_gallery_pages: return True直前")
            return True  # ⭐修正: 成功を返す⭐
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"完了処理エラー: {e}", "error"
            )
            return False  # ⭐修正: 失敗を返す⭐
    
    def _fetch_and_validate_gallery_info(
        self, 
        url: str, 
        normalized_url: str, 
        save_folder: str, 
        options: Optional[Dict[str, Any]], 
        gallery_info: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        ギャラリー情報を取得して検証
        
        Args:
            url: ギャラリーURL
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            options: ダウンロードオプション
            gallery_info: 既存のギャラリー情報
            
        Returns:
            有効なgallery_info、またはNone（スキップ時）
        """
        # 既に取得済みで、かつimage_page_urlsが含まれている場合のみ使用
        if gallery_info is not None and gallery_info.get('image_page_urls'):
            return gallery_info
        
        try:
            self.session_manager.ui_bridge.post_log("【新仕様】全画像ページURLを取得中...")
            gallery_info = self.core._get_gallery_pages(url, options)
            
            if not gallery_info or not gallery_info.get('image_page_urls'):
                self.session_manager.ui_bridge.post_log(
                    "[WARNING] ギャラリー情報が取得できないか、ダウンロード範囲が無効です", 
                    "warning"
                )
                self._handle_invalid_gallery_info(normalized_url, save_folder)
                return None
            
            self.session_manager.ui_bridge.post_log(
                f"【新仕様】取得完了: 総画像数={len(gallery_info['image_page_urls'])}, "
                f"開始ページ={gallery_info.get('start_page', 1)}"
            )
            return gallery_info
            
        except Exception as e:
            # ⭐エラー統計を更新⭐
            if hasattr(self, 'core') and hasattr(self.core, 'parent') and hasattr(self.core.parent, 'enhanced_error_handler'):
                try:
                    from core.errors.error_types import ErrorContext
                    context = ErrorContext.create_for_gallery_info(normalized_url if 'normalized_url' in locals() else "")
                    self.core.parent.enhanced_error_handler.handle_error(e, context)
                except:
                    pass  # エラーハンドラーの呼び出し失敗は無視
            
            self.session_manager.ui_bridge.post_log(
                f"【新仕様】画像ページURL取得エラー: {e}", "error"
            )
            self._schedule_next_download_and_increment("画像ページURL取得エラー")
            return None
    
    def _handle_invalid_gallery_info(self, normalized_url: str, save_folder: str) -> None:
        """
        ギャラリー情報が無効な場合の処理
        
        Args:
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
        """
        # 未完了フォルダとして記録
        if save_folder and self.parent.rename_incomplete_folder.get():
            if not hasattr(self.core, 'incomplete_folders'):
                self.core.incomplete_folders = set()
            self.core.incomplete_folders.add(save_folder)
            self.core.incomplete_urls.add(normalized_url)
            self.session_manager.ui_bridge.post_log(
                f"[INFO] 未完了フォルダとして記録: {save_folder}"
            )
        
        # URLステータスをincompleteに設定
        self.state_manager.set_url_status(normalized_url, 'incomplete')
        self._schedule_next_download_and_increment("ギャラリー情報なし/範囲無効")
    
    def _schedule_next_download_and_increment(self, reason: str) -> None:
        """
        次のダウンロードをスケジュールしてインデックスを進める
        
        Args:
            reason: スケジュール理由
        """
        reason = require_not_none(reason, "reason", default="不明な理由")
        current_index = self.state_manager.get_current_url_index()
        next_index = current_index + 1
        self.state_manager.set_current_url_index(next_index)
        self.core._schedule_next_download(reason)
    
    def _initialize_gallery_context(
        self, 
        gallery_info: Dict[str, Any], 
        normalized_url: str, 
        save_folder: str, 
        start_page: int, 
        options: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        ギャラリーダウンロードのコンテキストを初期化
        
        Args:
            gallery_info: ギャラリー情報
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            start_page: 開始ページ
            options: ダウンロードオプション
            
        Returns:
            コンテキスト情報、またはNone（エラー時）
        """
        from core.communication.download_context import DownloadContext
        all_image_urls = gallery_info.get('image_page_urls', [])
        # 空の配列チェック
        if not all_image_urls:
            return self._handle_empty_image_list(
                gallery_info, normalized_url, save_folder, options
            )

        # ページ数計算
        original_total_pages = gallery_info.get('original_total_images', len(all_image_urls))
        start_page_from_info = gallery_info.get('start_page', 1)
        actual_start_page = max(1, start_page)
        # ダウンロード範囲適用
        download_image_urls = self._apply_download_range(
            all_image_urls, actual_start_page, start_page_from_info,
            normalized_url, save_folder, gallery_info
        )
        if download_image_urls is None:
            return None  # 範囲エラー
        # ダウンロード範囲情報計算
        download_range_info = self._calculate_download_range_info(
            gallery_info, options, all_image_urls, 
            download_image_urls, original_total_pages
        )
        # 総ページ数計算
        actual_total_pages = self._calculate_actual_total_pages(
            download_range_info, original_total_pages, 
            download_image_urls, normalized_url
        )
        # 状態管理初期化
        self.core.current_save_folder = save_folder
        self.core.current_gallery_url = normalized_url
        self.core.current_page = actual_start_page
        # DownloadContextで返却
        return DownloadContext(
            url=normalized_url,
            save_folder=save_folder,
            start_page=actual_start_page,
            current_page=actual_start_page,
            total_pages=actual_total_pages,
            download_range=download_range_info.get('download_range') if isinstance(download_range_info, dict) else None,
            applied_range=download_range_info,
            gallery_title=gallery_info.get('title', ''),
            gallery_metadata=gallery_info,
            image_page_urls=all_image_urls,
            download_image_urls=download_image_urls,
            downloaded_pages=0,
            failed_pages=[],
            skipped_pages=[],
            stage="initial",
            options=options,
            sub_stage="",
            stage_data=None,
            is_resume=False,
            resume_info=None,
            absolute_page=None,
            error_occurred=False,
            error_message="",
            error_page=None,
            retry_count=0,
            url_index=None,
            current_image_page_url=""
        )
    
    def _handle_empty_image_list(
        self, 
        gallery_info: Dict[str, Any], 
        normalized_url: str, 
        save_folder: str, 
        options: Optional[Dict[str, Any]]
    ) -> None:
        """
        空の画像リストの処理
        
        Args:
            gallery_info: ギャラリー情報
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            options: ダウンロードオプション
        """
        download_range_info = gallery_info.get('download_range_info')
        
        if (download_range_info is None and 
            options and options.get('download_range_enabled', False)):
            # ダウンロード範囲が無効
            self.session_manager.ui_bridge.post_log(
                "[WARNING] ダウンロード範囲が無効です。", "warning"
            )
            self.session_manager.ui_bridge.post_log(
                "[INFO] 正しいページ範囲を入力するか、ページ範囲オプションをOFFにしてリスタートしてください。", 
                "info"
            )
            
            # 中断状態に設定
            self.state_manager.set_url_status(normalized_url, 'paused')
            self.state_manager.set_paused(True)
            self.core.current_gallery_url = normalized_url
            
            # 復帰ポイント保存
            self.core._save_resume_point(
                normalized_url, 1, 
                save_folder if save_folder else "", 
                reason="range_invalid"
            )
            
            # GUI更新
            if hasattr(self.parent, '_update_gui_for_paused'):
                self.parent._update_gui_for_paused()
            
            return None
        else:
            # ギャラリー情報なし
            self._handle_invalid_gallery_info(normalized_url, save_folder)
            return None
    
    def _apply_download_range(
        self, 
        all_image_urls: list, 
        actual_start_page: int, 
        start_page_from_info: int, 
        normalized_url: str, 
        save_folder: str, 
        gallery_info: Dict[str, Any]
    ) -> Optional[list]:
        """
        ダウンロード範囲を適用
        
        Args:
            all_image_urls: 全画像URLリスト
            actual_start_page: 実際の開始ページ
            start_page_from_info: 情報から取得した開始ページ
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            gallery_info: ギャラリー情報
            
        Returns:
            範囲適用後の画像URLリスト、またはNone（エラー時）
        """
        download_image_urls = all_image_urls
        
        if actual_start_page > 1:
            # 復帰ポイントチェック
            download_image_urls = self._handle_resume_from_page(
                all_image_urls, actual_start_page, 
                normalized_url, save_folder, gallery_info
            )
            if download_image_urls is None:
                return None  # 範囲外エラー
                
        elif start_page_from_info > 1:
            # 開始ページ指定
            if start_page_from_info <= len(all_image_urls):
                download_image_urls = all_image_urls[start_page_from_info-1:]
                self.session_manager.ui_bridge.post_log(
                    f"【新仕様】開始ページ {start_page_from_info} からダウンロード開始"
                )
            else:
                # 範囲外
                self.session_manager.ui_bridge.post_log(
                    f"[ERROR] 開始ページ({start_page_from_info})が配列範囲({len(all_image_urls)})を超えています。",
                    "error"
                )
                self._handle_invalid_gallery_info(normalized_url, save_folder)
                return None
        
        return download_image_urls
    
    def _handle_resume_from_page(
        self, 
        all_image_urls: list, 
        actual_start_page: int,
        normalized_url: str, 
        save_folder: str, 
        gallery_info: Dict[str, Any]
    ) -> Optional[list]:
        """
        復帰ポイントからの再開処理
        
        Args:
            all_image_urls: 全画像URLリスト
            actual_start_page: 実際の開始ページ
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            gallery_info: ギャラリー情報
            
        Returns:
            範囲適用後の画像URLリスト、またはNone（エラー時）
        """
        # resume_infoから sub_stage を取得
        resume_info = self.state_manager.get_resume_point(normalized_url)
        resume_sub_stage = resume_info.get('sub_stage') if resume_info else None
        
        if not resume_sub_stage and gallery_info and 'resume_info' in gallery_info:
            resume_sub_stage = gallery_info['resume_info'].get('sub_stage')
        
        # 'after' ステージの処理
        if resume_sub_stage == 'after':
            stage_data = resume_info.get('stage_data', {}) if resume_info else {}
            save_path = stage_data.get('save_path')
            
            if save_path and os.path.exists(save_path):
                # 画像保存済み：次のページから開始
                actual_start_page = actual_start_page + 1
                self.session_manager.ui_bridge.post_log(
                    f"【中断再開】sub_stage='after'のため、次のページ({actual_start_page})から開始"
                )
            else:
                # 画像未保存：同じページから再開
                self.session_manager.ui_bridge.post_log(
                    f"【中断再開】画像未保存のため、同じページ({actual_start_page})から再開"
                )
        
        # 範囲チェック
        if actual_start_page <= len(all_image_urls):
            download_image_urls = all_image_urls[actual_start_page-1:]
            self.session_manager.ui_bridge.post_log(
                f"【復帰ポイント再開】開始ページ {actual_start_page} からダウンロード開始"
            )
            return download_image_urls
        else:
            # 範囲外エラー
            self.session_manager.ui_bridge.post_log(
                f"[ERROR] 復帰ページ({actual_start_page})が配列範囲({len(all_image_urls)})を超えています。",
                "error"
            )
            self._handle_invalid_gallery_info(normalized_url, save_folder)
            return None
    
    def _calculate_download_range_info(
        self, 
        gallery_info: Dict[str, Any], 
        options: Optional[Dict[str, Any]], 
        all_image_urls: list, 
        download_image_urls: list, 
        original_total_pages: int
    ) -> Optional[Dict[str, Any]]:
        """
        ダウンロード範囲情報を計算
        
        Args:
            gallery_info: ギャラリー情報
            options: ダウンロードオプション
            all_image_urls: 全画像URLリスト
            download_image_urls: ダウンロード対象URLリスト
            original_total_pages: 元の総ページ数
            
        Returns:
            ダウンロード範囲情報、またはNone
        """
        download_range_info = gallery_info.get('download_range_info')
        
        if not download_range_info:
            download_range_info = getattr(self.core, 'current_download_range_info', None)
        
        if (download_range_info and download_range_info.get('enabled') and 
            len(download_image_urls) > 0):
            download_range_info['relative_total'] = len(download_image_urls)
        elif not download_range_info and options.get('download_range_enabled', False):
            # ダウンロード範囲計算（直接計算）
            try:
                start = int(options.get('download_range_start', 0) or 0)
                end_value = options.get('download_range_end', '')
                end = int(end_value) if end_value and str(end_value).strip() else original_total_pages
                
                # start=0は「最初から」の意味で有効
                if end >= start:
                    # ⭐修正: relative_totalの計算から+1を削除（0-indexedリストに対応）⭐
                    download_range_info = {
                        'enabled': True,
                        'start': start,
                        'end': min(end, original_total_pages),
                        'relative_total': min(end, original_total_pages) - start,
                        'absolute_total': original_total_pages,
                        'range_changed': True
                    }
            except (ValueError, TypeError) as e:
                self.session_manager.ui_bridge.post_log(
                    f"[WARNING] ダウンロード範囲解析エラー: {e}", "warning"
                )
                download_range_info = None
        
        return download_range_info
    
    def _calculate_actual_total_pages(
        self, 
        download_range_info: Optional[Dict[str, Any]], 
        original_total_pages: int, 
        download_image_urls: list, 
        normalized_url: str
    ) -> int:
        """
        実際の総ページ数を計算
        
        Args:
            download_range_info: ダウンロード範囲情報
            original_total_pages: 元の総ページ数
            download_image_urls: ダウンロード対象URLリスト
            normalized_url: 正規化されたURL
            
        Returns:
            実際の総ページ数
        """
        if download_range_info and download_range_info.get('enabled'):
            relative_total = download_range_info.get('relative_total', 0)
            
            if relative_total <= 0:
                relative_total = len(download_image_urls)
                if relative_total > 0:
                    download_range_info['relative_total'] = relative_total
            
            # 既存プログレスバーから取得を試みる
            url_index = self.state_manager.get_current_url_index()
            if url_index is None:
                url_index = self.state_manager.get_url_index_by_url(normalized_url)
            
            if url_index is not None:
                existing_progress = self.state_manager.get_progress_bar(url_index)
                if existing_progress:
                    # ⭐修正: フラットな辞書から直接取得⭐
                    existing_total = existing_progress.get('total', 0)
                    if existing_total > 0:
                        return existing_total
            
            return relative_total if relative_total > 0 else len(download_image_urls)
        else:
            return original_total_pages
    
    def _initialize_progress(self, actual_start_page, actual_total_pages,
                            download_range_info, normalized_url):
        """プログレス表示を初期化"""
        # タイトル取得（StateManager経由）
        url_index = self.state_manager.get_current_url_index()
        title = None
        if url_index is not None:
            progress = self.state_manager.get_progress_bar(url_index)
            if progress:
                title = progress.get('title')
        
        if actual_start_page > 1:
            # 再開時
            self._initialize_resume_progress(
                actual_start_page, actual_total_pages,
                download_range_info, normalized_url, title
            )
        else:
            # 新規ダウンロード
            self.core.current_progress = 0
            current_url_index = self.state_manager.get_current_url_index()
            if current_url_index is None:
                current_url_index = self.state_manager.get_url_index_by_url(normalized_url)
            
            # ⭐Phase 1: url_indexのバリデーションとエラーコンテキスト⭐
            if current_url_index is None:
                context = ErrorContext.for_progress_update(
                    url_index=current_url_index,
                    url=normalized_url
                )
                context.add_info("current_url_index_from_state", self.state_manager.get_current_url_index())
                context.add_info("available_progress_bars", list(self.state_manager.get_all_progress_bars().keys()))
                
                self.session_manager.ui_bridge.post_log(
                    f"[CRITICAL] url_indexが取得できません\n{context.to_json()}",
                    "error"
                )
                # スキップして次へ
                self._schedule_next_download_and_increment("url_index取得失敗")
                return
            
            # ⭐修正: 2行目以降のURLではdownload_range_infoを表示しない⭐
            display_range_info = download_range_info
            if download_range_info and download_range_info.get('enabled'):
                # 範囲モード確認
                options = self.core._get_current_options()
                range_mode = options.get('download_range_mode', "全てのURL")
                if range_mode == "1行目のURLのみ" and current_url_index > 0:
                    display_range_info = None
            
            self.core.update_current_progress(
                0, actual_total_pages, "状態: ダウンロード準備中",
                url=normalized_url,
                download_range_info=display_range_info,
                url_index=current_url_index
            )
            
            # ⭐修正: タイトルとDLリストを更新⭐
            if title:
                # プログレスバーのタイトル更新
                if hasattr(self.core, 'update_progress_title'):
                    self.core.update_progress_title(normalized_url, title)
                
                # DLリストのタイトル更新
                if hasattr(self.parent, 'download_list_widget'):
                    self.parent.download_list_widget.update_title(normalized_url, title)
    
    def _initialize_progress_with_tracker(
        self, 
        actual_start_page: int, 
        actual_total_pages: int,
        download_range_info: Optional[dict], 
        normalized_url: str, 
        title: Optional[str]
    ) -> None:
        """
        ⭐Phase 1: ProgressTracker経由でプログレス初期化（型アノテーション追加）⭐
        
        Args:
            actual_start_page: 実際の開始ページ (>= 1)
            actual_total_pages: 実際の総ページ数 (> 0)
            download_range_info: ダウンロード範囲情報（オプション）
            normalized_url: 正規化されたURL
            title: ギャラリータイトル（Noneの場合は"準備中..."を使用）
        """
        from core.progress_tracker import DownloadPhase
        
        # ⭐Phase 1: 契約設計による前提条件チェック⭐
        require(actual_start_page >= 1, f"actual_start_page must be >= 1, got: {actual_start_page}")
        require(actual_total_pages > 0, f"actual_total_pages must be positive, got: {actual_total_pages}")
        
        current_url_index = self.state_manager.get_current_url_index()
        if current_url_index is None:
            current_url_index = self.state_manager.get_url_index_by_url(normalized_url)
        
        # ⭐Phase 1: url_indexのバリデーションとエラーコンテキスト⭐
        if current_url_index is None:
            context = ErrorContext.for_progress_update(
                url_index=current_url_index,
                url=normalized_url
            )
            context.add_info("operation_stage", "initialize_progress_with_tracker")
            context.add_info("available_progress_bars", list(self.state_manager.get_all_progress_bars().keys()))
            
            self.session_manager.ui_bridge.post_log(
                f"[CRITICAL] url_indexが取得できません\n{context.to_json()}",
                "error"
            )
            # スキップして次へ
            self._schedule_next_download_and_increment("url_index取得失敗")
            return
        
        # ⭐修正: プログレスバーが存在しない場合は作成し、完全な情報を設定⭐
        progress_bar = self.state_manager.get_progress_bar(current_url_index)
        if progress_bar is None:
            # プログレスバーを新規作成
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] プログレスバー新規作成: url_index={current_url_index}, url={normalized_url[:80]}",
                "debug"
            )
            progress_bar = self.state_manager.ensure_progress_bar(normalized_url, current_url_index)
        
        # ⭐修正: start_timeをupdate_progress_bar_state()経由で設定（スレッドセーフ）⭐
        current_start_time = None
        if isinstance(progress_bar, dict):
            current_start_time = progress_bar.get('start_time')
        elif hasattr(progress_bar, 'start_time'):
            current_start_time = progress_bar.start_time
        
        # start_timeが未設定の場合は現在時刻を設定
        if current_start_time is None:
            current_start_time = time.time()
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] start_timeを新規設定: {current_start_time}",
                "debug"
            )
        
        # ⭐Phase 1: Noneセーフな文字列処理⭐
        safe_title = require_not_none(title, "title", default="準備中...")
        safe_url = safe_str(normalized_url, maxlen=80)
        
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] update_progress_bar_state()呼び出し: url_index={current_url_index}, title='{safe_str(safe_title, maxlen=30)}', status='ダウンロード準備中'",
            "debug"
        )
        self.state_manager.update_progress_bar_state(
            url_index=current_url_index,
            current=0,
            total=actual_total_pages,
            title=safe_title,  # タイトルを明示的に設定（Noneチェック済み）
            status="ダウンロード準備中",
            download_range_info=download_range_info,
            start_time=current_start_time  # ⭐追加: start_timeを明示的に設定⭐
        )
        
        # ProgressTracker経由で画像ダウンロードフェーズ開始
        if current_url_index is not None:
            # ⭐修正: titleがNoneの場合のエラーを防ぐ⭐
            safe_title_tracker = require_not_none(title, "title", default="準備中...")
            self.progress_tracker.create(
                url_index=current_url_index,
                phase=DownloadPhase.IMAGE_DOWNLOADING,
                total=actual_total_pages,
                status=f"画像ダウンロード準備中: {safe_str(safe_title_tracker, maxlen=50)}",
                metadata={
                    'url': normalized_url,
                    'title': title,
                    'range_info': download_range_info,
                    'start_page': actual_start_page
                }
            )
        
        # 既存のStateManager経由も一時的に併用（互換性維持）
        self.core.current_progress = 0
        self.core.update_current_progress(
            actual_start_page - 1 if actual_start_page > 1 else 0,
            actual_total_pages,
            "状態: ダウンロード準備中",
            url=normalized_url,
            download_range_info=download_range_info,
            url_index=current_url_index
        )
        
        # ⭐修正: StateManager経由でプログレスバーの初期状態を設定（タイトル含む）⭐
        if current_url_index is not None:
            safe_title = title or "準備中..."  # ⭐Noneチェック⭐
            self.state_manager.update_progress_bar_state(
                url_index=current_url_index,
                current=0,
                total=actual_total_pages,
                title=safe_title,  # ⭐タイトルを明示的に設定（Noneチェック済み）⭐
                status="ダウンロード準備中",
                download_range_info=download_range_info
            )
        
        # DLリストのタイトル更新
        if title and hasattr(self.parent, 'download_list_widget'):
            self.parent.download_list_widget.update_title(normalized_url, title)
    
    def _initialize_resume_progress(
        self, 
        actual_start_page: int, 
        actual_total_pages: int,
        download_range_info: Optional[Dict[str, Any]], 
        normalized_url: str
    ) -> None:
        """
        再開時のプログレス初期化
        
        Args:
            actual_start_page: 実際の開始ページ
            actual_total_pages: 実際の総ページ数
            download_range_info: ダウンロード範囲情報
            normalized_url: 正規化されたURL
        """
        current_url_index = self.state_manager.get_current_url_index()
        
        existing_current = 0
        range_changed = True
        
        if current_url_index is not None:
            existing_progress = self.state_manager.get_progress_bar(current_url_index)
            if existing_progress:
                # ⭐修正: フラットな辞書から直接取得⭐
                existing_current = existing_progress.get('current', 0)
                
                if download_range_info and download_range_info.get('range_changed') is not None:
                    range_changed = download_range_info['range_changed']
        
        # currentの設定
        if not range_changed and existing_current > 0:
            self.core.current_progress = existing_current
        else:
            if existing_current == 0:
                if download_range_info and download_range_info.get('enabled'):
                    range_start = download_range_info.get('start', 1)
                    resume_current = max(0, actual_start_page - range_start)
                else:
                    resume_current = actual_start_page - 1
                self.core.current_progress = resume_current
            else:
                self.core.current_progress = existing_current
        
        # プログレス更新
        if current_url_index is not None:
            self.core.update_current_progress(
                self.core.current_progress, actual_total_pages,
                "状態: ダウンロード中",
                url=normalized_url,
                download_range_info=download_range_info,
                url_index=current_url_index
            )
    
    def _execute_image_download_loop(
        self, 
        context,  # DownloadContext型
        url: str, 
        normalized_url: str, 
        save_folder: str,
        wait_time_value: float, 
        sleep_value_sec: float,
        save_format_option: str, 
        save_name_option: str, 
        custom_name_format: str,
        resize_mode: str, 
        resize_values: dict, 
        manga_title: str,
        options: Optional[Dict[str, Any]], 
        gallery_info: Optional[Dict[str, Any]]
    ) -> bool:
        """
        画像ダウンロードループを実行
        
        Args:
            context: ダウンロードコンテキスト
            url: 元のURL
            normalized_url: 正規化されたURL
            save_folder: 保存先フォルダ
            wait_time_value: 待機時間
            sleep_value_sec: スリープ時間
            save_format_option: 保存フォーマット
            save_name_option: ファイル名オプション
            custom_name_format: カスタム名フォーマット
            resize_mode: リサイズモード
            resize_values: リサイズ値
            manga_title: マンガタイトル
            options: ダウンロードオプション
            gallery_info: ギャラリー情報
            
        Returns:
            成功時True
        """
        import time
        
        download_image_urls = context.download_image_urls
        actual_start_page = context.start_page
        actual_total_pages = context.total_pages
        # 追加デバッグ: ループ条件の内容を出力
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] 画像ダウンロードループ直前: download_image_urls={download_image_urls[:3]}... (len={len(download_image_urls)}), actual_start_page={actual_start_page}, actual_total_pages={actual_total_pages}",
            "debug"
        )
        
        # ⭐DEBUG: 画像ダウンロードループ開始⭐
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] 画像ダウンロードループ開始: 画像URL数={len(download_image_urls)}, start={actual_start_page}, total={actual_total_pages}",
            "debug"
        )
        
        # 各画像ページをダウンロード
        for index, image_page_url in enumerate(download_image_urls, start=actual_start_page):
            # ⭐DEBUG: 各画像処理開始⭐
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] 画像{index}処理開始: URL={image_page_url[:80] if image_page_url else 'None'}",
                "debug"
            )
            try:
                # ⭐統一された停止チェック（skip_completion_checkで区別）⭐
                if self.core._should_stop():
                    # ログメッセージを区別（スキップ vs 停止）
                    if self.state_manager.download_state.skip_completion_check:
                        self.session_manager.ui_bridge.post_log("スキップ要求を検出", "info")
                    else:
                        self.session_manager.ui_bridge.post_log("ダウンロード停止要求を検出", "info")
                    # 停止時に未完了フォルダとして記録
                    self._mark_as_incomplete_on_stop(save_folder, normalized_url)
                    break
                
                # 一時停止処理
                while self.state_manager.is_paused():
                    time.sleep(0.1)
                    # 一時停止中も停止チェック
                    if self.core._should_stop():
                        if self.state_manager.download_state.skip_completion_check:
                            self.session_manager.ui_bridge.post_log("スキップ要求を検出（一時停止中）", "info")
                        else:
                            self.session_manager.ui_bridge.post_log("ダウンロード停止要求を検出（一時停止中）", "info")
                        self._mark_as_incomplete_on_stop(save_folder, normalized_url)
                        break
                
                # 停止チェック（一時停止から復帰後）
                if self.core._should_stop():
                    if self.state_manager.download_state.skip_completion_check:
                        self.session_manager.ui_bridge.post_log("スキップ要求を検出（一時停止復帰後）", "info")
                    else:
                        self.session_manager.ui_bridge.post_log("ダウンロード停止要求を検出（一時停止復帰後）", "info")
                    self._mark_as_incomplete_on_stop(save_folder, normalized_url)
                    break
                
                # ⭐Phase1.1: ProgressTracker経由で進捗更新⭐
                self.core.current_page = index
                current_url_index = self.state_manager.get_current_url_index()
                if current_url_index is not None:
                    self.progress_tracker.update(
                        url_index=current_url_index,
                        current=index,
                        status=f"画像 {index}/{actual_total_pages} ダウンロード中"
                    )
                    
                    # ⭐修正: StateManager経由でプログレスバーGUIを更新⭐
                    self.state_manager.update_progress_bar_state(
                        url_index=current_url_index,
                        current=index,
                        total=actual_total_pages,
                        status=f"ダウンロード中",
                        download_range_info=context.applied_range
                    )
                
                # ログ出力（10枚ごとに間引き）
                if index % 10 == 0 or index == actual_total_pages:
                    self.session_manager.ui_bridge.post_log(
                        f"[{index}/{actual_total_pages}] 画像ダウンロード中...", 
                        "info"
                    )
                
                # 実際の画像ダウンロード処理
                self._process_single_image_page(
                    image_page_url, index, actual_total_pages,
                    save_folder, save_format_option, save_name_option,
                    custom_name_format, resize_mode, resize_values,
                    manga_title, options
                )
                
                # 待機時間
                if wait_time_value > 0:
                    time.sleep(wait_time_value)
                
            except Exception as e:
                self.session_manager.ui_bridge.post_log(
                    f"[{index}/{actual_total_pages}] エラー: {e}", 
                    "error"
                )
                import traceback
                self.session_manager.ui_bridge.post_log(
                    f"詳細: {traceback.format_exc()}", 
                    "debug"
                )
                # エラーが連続する場合は停止
                # 継続してスキップ
                continue
        
        # ⭐Phase1.1: ダウンロードループ完了を通知⭐
        current_url_index = self.state_manager.get_current_url_index()
        if current_url_index is not None:
            self.progress_tracker.complete(
                url_index=current_url_index,
                status=f"✅ {actual_total_pages}枚のダウンロード完了"
            )
        
        self.session_manager.ui_bridge.post_log("ダウンロードループ完了", "info")
    
    def _process_single_image_page(
        self, 
        image_page_url: str, 
        page_num: int, 
        total_pages: int,
        save_folder: str, 
        save_format_option: str, 
        save_name_option: str,
        custom_name_format: str, 
        resize_mode: str, 
        resize_values: dict,
        manga_title: str, 
        options: Optional[Dict[str, Any]]
    ) -> None:
        """
        単一画像ページの処理
        
        Args:
            image_page_url: 画像ページのURL
            page_num: ページ番号
            total_pages: 総ページ数
            save_folder: 保存フォルダ
            save_format_option: 保存形式
            save_name_option: ファイル名オプション
            custom_name_format: カスタムファイル名フォーマット
            resize_mode: リサイズモード
            resize_values: リサイズ値
            manga_title: マンガタイトル
            options: ダウンロードオプション
        """
        # ⭐DEBUG: 画像ページ処理開始⭐
        self.session_manager.ui_bridge.post_log(
            f"[DEBUG] _process_single_image_page()開始: page={page_num}, URL={image_page_url[:80] if image_page_url else 'None'}",
            "debug"
        )
        try:
            # 1. 画像ページから実画像URLと情報を取得
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _get_image_info_from_page()呼び出し直前",
                "debug"
            )
            image_info = self.core._get_image_info_from_page(image_page_url)
            self.session_manager.ui_bridge.post_log(
                f"[DEBUG] _get_image_info_from_page()完了: image_info={image_info is not None}",
                "debug"
            )
            if not image_info or 'image_url' not in image_info:
                raise Exception("画像情報の取得に失敗しました")
            
            image_url = image_info['image_url']
            original_filename = image_info.get('original_filename', '')
            
            # 2. 保存パスを生成
            # ギャラリー情報からメタデータを取得
            artist = getattr(self.core, 'artist', None)
            parody = getattr(self.core, 'parody', None)
            character = getattr(self.core, 'character', None)
            group = getattr(self.core, 'group', None)
            
            save_path = self.core.get_save_path(
                save_folder, page_num, image_url,
                save_name_option, custom_name_format,
                manga_title, artist, parody, character, group,
                save_format_option
            )
            
            # 3. Context-Aware Error Handling統合: 画像ダウンロードをリトライラッピング
            def download_with_context():
                """Context-Aware Error Handlingでラップされたダウンロード処理"""
                # 4. 実際のダウンロード処理
                return self._download_and_save_image(
                    image_url, save_path, page_num, total_pages,
                    duplicate_mode=options.get('duplicate_file_mode', 'overwrite')
                )
            
            # Enhanced Error Handlerが利用可能な場合はContext-Aware Retryを使用
            if (hasattr(self.core.parent, 'enhanced_error_handler') and 
                self.core.parent.enhanced_error_handler and
                hasattr(self.core.parent.enhanced_error_handler, 'handle_error_with_retry')):
                
                # ⭐Phase 1改善: Factory PatternとDTO使用⭐
                from core.errors.error_types import DownloadContext, ErrorContextFactory, RetryResult
                
                # DTOを使用してレイヤー間でデータを転送
                download_ctx = DownloadContext(
                    url=image_url,
                    page_num=page_num,
                    total_pages=total_pages,
                    image_url=image_url
                )
                
                # Factoryパターンでコンテキスト生成
                context = ErrorContextFactory.create_for_image_download(download_ctx)
                
                # Context-Aware Retryでラップして実行
                result = self.core.parent.enhanced_error_handler.handle_error_with_retry(
                    download_with_context,
                    context,
                    max_retries=None  # Noneでエラー種別により自動決定
                )
                
                # ⭐Phase 1改善: Result型の統一的な処理⭐
                if isinstance(result, RetryResult):
                    if not result.success:
                        # ⭐修正: 画像スキップ時の未完了フラグ設定⭐
                        if result.action == FinalAction.SKIP_IMAGE:
                            self.session_manager.ui_bridge.post_log(
                                f"[{page_num}/{total_pages}] 画像スキップ: プレースホルダーファイルを作成",
                                "warning"
                            )
                            # 未完了フラグを設定（コンテキストに保存）
                            if 'context' in locals():
                                context['has_skipped_images'] = True
                            
                            # ⭐プレースホルダーファイルを作成⭐
                            try:
                                # ファイル名を決定（save_pathが既に設定されている場合はそれを使用）
                                if not save_path or not os.path.exists(os.path.dirname(save_path)):
                                    # save_pathが無効な場合は、絶対ページ数を使用
                                    placeholder_name = f"{page_num}.txt"
                                    save_path = os.path.join(save_folder, placeholder_name)
                                else:
                                    # save_pathの拡張子を.txtに変更
                                    base_name = os.path.splitext(save_path)[0]
                                    save_path = f"{base_name}.txt"
                                
                                # プレースホルダーファイルの内容
                                placeholder_content = f"画像ダウンロード失敗\nURL: {image_page_url}\nページ: {page_num}/{total_pages}\n"
                                
                                # ファイルを作成
                                with open(save_path, 'w', encoding='utf-8') as f:
                                    f.write(placeholder_content)
                                
                                self.session_manager.ui_bridge.post_log(
                                    f"[{page_num}/{total_pages}] プレースホルダーファイル作成: {os.path.basename(save_path)}",
                                    "info"
                                )
                            except Exception as placeholder_error:
                                self.session_manager.ui_bridge.post_log(
                                    f"[{page_num}/{total_pages}] プレースホルダーファイル作成エラー: {placeholder_error}",
                                    "error"
                                )
                            
                            # 画像スキップ時は例外を発生させずに継続
                            return
                        # ⭐修正: Selenium処理への移行チェック⭐
                        elif result.action == FinalAction.CONTINUE:
                            # Selenium処理を試行
                            self.session_manager.ui_bridge.post_log(
                                f"[{page_num}/{total_pages}] Selenium処理を試行します...",
                                "info"
                            )
                            # Selenium処理を実行
                            selenium_result = self._try_selenium_download(
                                image_page_url, save_path, page_num, total_pages, options
                            )
                            if not selenium_result:
                                raise Exception(f"Selenium処理も失敗: {result.error}")
                        else:
                            raise Exception(f"画像ダウンロード失敗: {result.error}")
                elif isinstance(result, dict):
                    # 後方互換性: 辞書形式もサポート
                    if result.get('status') != 'success' and not result.get('success'):
                        # ⭐修正: Selenium処理への移行チェック⭐
                        from core.errors.enhanced_error_handler import FinalAction
                        if result.get('action') == FinalAction.CONTINUE or result.get('reason') in ['selenium_fallback_needed', 'selenium_fallback_early', 'selenium_immediate_mode']:
                            # Selenium処理を試行
                            self.session_manager.ui_bridge.post_log(
                                f"[{page_num}/{total_pages}] Selenium処理を試行します...",
                                "info"
                            )
                            # Selenium処理を実行
                            selenium_result = self._try_selenium_download(
                                image_page_url, save_path, page_num, total_pages, options
                            )
                            if not selenium_result:
                                error_msg = str(result.get('error', '不明なエラー'))
                                raise Exception(f"Selenium処理も失敗: {error_msg}")
                        else:
                            error_msg = str(result.get('error', '不明なエラー'))
                            raise Exception(f"画像ダウンロード失敗: {error_msg}")
            else:
                # フォールバック: 通常のダウンロード処理
                download_with_context()
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"[{page_num}/{total_pages}] 画像処理エラー: {e}",
                "error"
            )
            raise
    
    def _try_selenium_download(
        self,
        image_page_url: str,
        save_path: str,
        page_num: int,
        total_pages: int,
        options: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Selenium処理を試行して画像をダウンロード
        
        Args:
            image_page_url: 画像ページURL
            save_path: 保存パス
            page_num: ページ番号
            total_pages: 総ページ数
            options: ダウンロードオプション
            
        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            # Seleniumが有効かチェック
            if not hasattr(self.core.parent, 'selenium_enabled') or not self.core.parent.selenium_enabled.get():
                self.session_manager.ui_bridge.post_log(
                    "Seleniumが無効のため、Selenium処理をスキップします",
                    "warning"
                )
                return False
            
            # Seleniumで画像情報を取得
            image_info = self.core._fetch_image_info_with_selenium(image_page_url)
            if not image_info or 'image_url' not in image_info:
                self.session_manager.ui_bridge.post_log(
                    f"[{page_num}/{total_pages}] Seleniumでの画像情報取得に失敗",
                    "error"
                )
                return False
            
            image_url = image_info['image_url']
            
            # 画像をダウンロード
            result = self._download_and_save_image(
                image_url, save_path, page_num, total_pages,
                duplicate_mode=options.get('duplicate_file_mode', 'overwrite')
            )
            
            if result.get('status') == 'success':
                self.session_manager.ui_bridge.post_log(
                    f"[{page_num}/{total_pages}] Selenium処理成功",
                    "info"
                )
                return True
            else:
                return False
                
        except Exception as e:
            self.session_manager.ui_bridge.post_log(
                f"[{page_num}/{total_pages}] Selenium処理エラー: {e}",
                "error"
            )
            return False
    
    def _download_and_save_image(
        self, 
        image_url: str, 
        save_path: str, 
        page_num: int, 
        total_pages: int, 
        duplicate_mode: str = 'overwrite'
    ) -> dict:
        """
        画像をダウンロードして保存する実装部分
        
        Args:
            image_url: 画像URL
            save_path: 保存パス
            page_num: ページ番号
            total_pages: 総ページ数
            duplicate_mode: 重複ファイル処理モード
        
        Returns:
            {'status': 'success'} または {'status': 'skipped'}
        """
        # ファイルが既に存在するかチェック
        if os.path.exists(save_path):
            if duplicate_mode == 'skip':
                self.session_manager.ui_bridge.post_log(
                    f"[{page_num}/{total_pages}] スキップ（既存）: {os.path.basename(save_path)}",
                    "info"
                )
                return {'status': 'skipped'}
            elif duplicate_mode == 'rename':
                # ファイル名を変更
                base, ext = os.path.splitext(save_path)
                counter = 1
                while os.path.exists(save_path):
                    save_path = f"{base}_{counter}{ext}"
                    counter += 1
        
        # 画像をダウンロードして保存
        success = self.core.download_and_save_image(
            image_url, save_path, None, {}  # save_format_option, optionsはコア側で処理
        )
        
        if success:
            self.session_manager.ui_bridge.post_log(
                f"[{page_num}/{total_pages}] 保存完了: {os.path.basename(save_path)}",
                "info"
            )
            return {'status': 'success'}
        else:
            raise Exception(f"ダウンロード失敗: {image_url}")
    
    def _mark_as_incomplete_on_stop(self, save_folder: str, url: str = None):
        """停止時に未完了フォルダとして記録
        
        Args:
            save_folder: 保存フォルダパス
            url: ギャラリーURL（オプション）
        """
        if save_folder and self.parent.rename_incomplete_folder.get():
            if not hasattr(self.core, 'incomplete_folders'):
                self.core.incomplete_folders = set()
            self.core.incomplete_folders.add(save_folder)
            self.session_manager.ui_bridge.post_log(
                f"停止: 未完了フォルダとして記録: {os.path.basename(save_folder)}", 
                "info"
            )
        
        # ⭐修正: "incomplete"ステータスを設定（有効なDownloadStatus）⭐
        if url:
            normalized_url = self.parent.normalize_url(url)
            self.state_manager.set_url_status(normalized_url, "incomplete")
