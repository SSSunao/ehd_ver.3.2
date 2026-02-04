"""
ValidationManager - 検証処理の専門管理

責任範囲:
- URL形式の検証
- ダウンロードオプションの検証
- ダウンロード範囲の検証
- ファイル名のサニタイズ
- SSL設定の構成

Phase9: downloader.pyから約250行を分離
"""

import os
import re
import ssl
import tkinter as tk
import urllib3
from typing import Dict, Tuple, Optional, Any
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context


class ValidationManager:
    """検証処理の専門管理クラス"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderCore インスタンス（委譲元）
        """
        self.parent = parent
        self.session_manager = parent.session_manager
    
    # ========================================
    # URL検証
    # ========================================
    
    def is_valid_eh_url(self, url: str) -> bool:
        """E-Hentai URLの形式検証
        
        Args:
            url: 検証対象URL
            
        Returns:
            bool: 有効なE-Hentai URLならTrue
        """
        try:
            if not url or not isinstance(url, str):
                return False
            
            url = url.strip()
            if not url:
                return False
            
            # E-HentaiのURLパターンをチェック
            eh_patterns = [
                r'https?://e-hentai\.org/g/\d+/[a-f0-9]+/',
                r'https?://exhentai\.org/g/\d+/[a-f0-9]+/',
                r'https?://e-hentai\.org/s/[a-f0-9]+/\d+-\d+',
                r'https?://exhentai\.org/s/[a-f0-9]+/\d+-\d+'
            ]
            
            for pattern in eh_patterns:
                if re.match(pattern, url):
                    return True
            
            return False
            
        except Exception:
            return False
    
    # ========================================
    # ダウンロードオプション検証
    # ========================================
    
    def validate_download_options(self) -> Dict[str, Any]:
        """ダウンロード実行前のオプション検証
        
        Returns:
            Dict: {'valid': bool, 'message': str} 検証結果
        """
        try:
            # 保存ディレクトリ（親フォルダ）の検証
            save_directory = getattr(self.parent.parent, 'folder_path', None)
            if not save_directory or not save_directory.strip():
                return {'valid': False, 'message': '保存ディレクトリが設定されていません'}
            
            # 保存ディレクトリの存在確認
            if not os.path.exists(save_directory):
                try:
                    os.makedirs(save_directory, exist_ok=True)
                except Exception as e:
                    return {'valid': False, 'message': f'保存ディレクトリの作成に失敗しました: {e}'}
            
            # 保存ディレクトリの書き込み権限確認
            if not os.access(save_directory, os.W_OK):
                return {'valid': False, 'message': '保存ディレクトリに書き込み権限がありません'}
            
            # ⭐修正: TreeviewからURLを取得⭐
            urls = []
            if hasattr(self.parent.parent, 'download_list_widget'):
                urls = self.parent.parent.download_list_widget.get_pending_urls()
            
            # Treeviewが空の場合、url_textから取得
            if not urls and hasattr(self.parent.parent, 'url_text') and self.parent.parent.url_text:
                urls_text = self.parent.parent.url_text.get("1.0", tk.END).strip()
                if urls_text:
                    urls = [url.strip() for url in urls_text.splitlines() if url.strip()]
            
            if not urls:
                return {'valid': False, 'message': 'URLが入力されていません'}
            
            # 各URLの形式検証
            for url in urls:
                if not self.is_valid_eh_url(url):
                    return {'valid': False, 'message': f'無効なURL形式です: {url}'}
            
            # 途中ページURLの解析結果をダウンロード範囲に反映
            first_url = urls[0]
            try:
                normalized_url, start_page = self.parent._normalize_gallery_url_with_start_page(first_url)
                if start_page > 1:
                    # 途中ページから開始する場合、ダウンロード範囲の始点を設定
                    if hasattr(self.parent.parent, 'download_range_start'):
                        self.parent.parent.download_range_start.set(str(start_page))
                        # 途中ページURL検出: 始点を設定
            except Exception as e:
                # 途中ページURL解析エラー
                pass
            
            # リサイズオプションの検証
            if hasattr(self.parent.parent, 'resize_enabled'):
                resize_enabled = self.parent.parent.resize_enabled.get()
                if resize_enabled == "on":
                    # リサイズモードの検証
                    resize_mode = getattr(self.parent.parent, 'resize_mode', None)
                    if not resize_mode:
                        return {'valid': False, 'message': 'リサイズモードが設定されていません'}
                    
                    mode_value = resize_mode.get()
                    # 日本語の表示値でチェック
                    valid_modes = ['縦幅上限', '横幅上限', '長辺上限', '長辺下限', '短辺上限', '短辺下限', '比率', 'off']
                    if mode_value not in valid_modes:
                        return {'valid': False, 'message': f'無効なリサイズモード: {mode_value}'}
            
            # 保存形式の検証
            if hasattr(self.parent.parent, 'save_format'):
                save_format = self.parent.parent.save_format.get()
                valid_formats = ['original', 'jpeg', 'png', 'webp', 'avif']
                # 大文字小文字を区別しない比較
                if save_format.lower() not in valid_formats:
                    return {'valid': False, 'message': f'無効な保存形式: {save_format}'}
            
            # 全ての検証を通過
            return {'valid': True, 'message': '検証成功'}
            
        except Exception as e:
            return {'valid': False, 'message': f'オプション検証エラー: {e}'}
    
    def validate_download_range_options(self, options: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[float]]:
        """ダウンロード範囲オプションの妥当性を検証
        
        Args:
            options: ダウンロードオプション辞書
            
        Returns:
            Tuple[bool, Optional[int], Optional[float]]: 
                (検証成功, 始点ページ, 終点ページ)
                検証失敗の場合は (False, エラーメッセージ, None)
        """
        try:
            if not options.get('download_range_enabled', False):
                return True, None, None
            
            start_str = options.get('download_range_start', "")
            end_str = options.get('download_range_end', "")
            
            # 始点の処理（空欄の場合は0）
            if start_str and start_str.strip() and start_str != "空欄は0":
                try:
                    start_page = int(start_str)
                    if start_page < 0:
                        return False, "始点は0以上である必要があります", None
                except ValueError:
                    return False, "始点の値が無効です", None
            else:
                start_page = 0  # 空欄の場合は0
            
            # 終点の処理（空欄の場合は∞）
            if end_str and end_str.strip() and end_str != "空欄は∞":
                try:
                    end_page = int(end_str)
                    if end_page < 0:
                        return False, "終点は0以上である必要があります", None
                    if end_page < start_page:
                        return False, "終点は始点以上である必要があります", None
                except ValueError:
                    return False, "終点の値が無効です", None
            else:
                end_page = float('inf')  # 空欄の場合は∞
            
            return True, start_page, end_page
            
        except Exception as e:
            return False, f"範囲検証エラー: {e}", None
    
    # ========================================
    # ファイル名サニタイズ
    # ========================================
    
    def sanitize_filename(self, filename: str) -> str:
        """ファイル名の無効文字を置換（文字列変換対応）
        
        Args:
            filename: サニタイズ対象のファイル名
            
        Returns:
            str: サニタイズ済みファイル名
        """
        try:
            if not filename:
                return "untitled"
            
            # 文字列変換ルールを適用
            if hasattr(self.parent.parent, 'string_conversion_enabled') and self.parent.parent.string_conversion_enabled.get():
                filename = self._apply_string_conversion(filename)
            
            # 既存の無効文字置換処理
            invalid_chars = r'[\\/:*?"<>|]'
            filename = re.sub(invalid_chars, '_', filename)
            
            # 連続するアンダースコアを単一に
            filename = re.sub(r'_+', '_', filename)
            
            # 先頭・末尾のドットやスペースを削除
            filename = filename.strip(' .')
            
            return filename or "untitled"
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ファイル名変換エラー: {e}", "error")
            return "untitled"
    
    def _apply_string_conversion(self, filename: str) -> str:
        """文字列変換ルールを適用
        
        Args:
            filename: 変換対象のファイル名
            
        Returns:
            str: 変換後のファイル名
        """
        try:
            if not hasattr(self.parent.parent, 'string_conversion_rules') or not self.parent.parent.string_conversion_rules:
                return filename
            
            # ⭐型チェック: リストでない場合はスキップ⭐
            if not isinstance(self.parent.parent.string_conversion_rules, list):
                return filename
            
            for rule in self.parent.parent.string_conversion_rules:
                if rule.get('enabled', False):
                    find_text = rule.get('find', '')
                    replace_text = rule.get('replace', '')
                    if find_text:
                        old_filename = filename
                        filename = filename.replace(find_text, replace_text)
                        # 文字列置換実行時にログ出力
                        if old_filename != filename:
                            self.session_manager.ui_bridge.post_log(
                                f"文字列置換実行: '{find_text}' → '{replace_text}' (結果: {filename})", 
                                "info"
                            )
            
            return filename
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"文字列変換エラー: {e}", "error")
            return filename
    
    # ========================================
    # SSL設定
    # ========================================
    
    def configure_ssl_settings(self):
        """SSL/TLS問題を回避するための設定（DH key too smallエラー対策）"""
        try:
            # SSL設定開始
            
            # 既に設定済みの場合はスキップ
            if hasattr(self.parent.parent, '_ssl_settings_applied') and self.parent.parent._ssl_settings_applied:
                # SSL設定は既に適用済み
                return
            
            # SSL関連モジュールインポート中
            self.session_manager.ui_bridge.post_log("【SSL設定】DH key too smallエラー対策のためSSL設定を適用中...", "info")
            
            # カスタムSSLコンテキストを作成
            class CustomHTTPAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    context = create_urllib3_context()
                    # セキュリティレベルを下げてDH key too smallエラーを回避
                    context.set_ciphers('DEFAULT@SECLEVEL=1')
                    kwargs['ssl_context'] = context
                    return super().init_poolmanager(*args, **kwargs)
            
            # セッションにカスタムアダプターを設定（同期的に実行）
            if hasattr(self.parent.parent, 'session') and self.parent.parent.session:
                # セッションにアダプター設定中
                self.parent.parent.session.mount('https://', CustomHTTPAdapter())
                self.parent.parent.session.mount('http://', CustomHTTPAdapter())
                self.parent.parent._ssl_settings_applied = True
                self.session_manager.ui_bridge.post_log("【SSL設定】設定完了", "info")
            else:
                self.session_manager.ui_bridge.post_log("【SSL設定】セッションが初期化されていません", "warning")
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"SSL設定エラー: {e}", "error")
            import traceback
            self.session_manager.ui_bridge.post_log(f"SSL設定エラー詳細: {traceback.format_exc()}", "error")
