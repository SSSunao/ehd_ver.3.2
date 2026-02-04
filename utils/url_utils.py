
# -*- coding: utf-8 -*-
"""
URL utilities for EH Downloader
"""

import tkinter as tk
import re
import threading
import time
from config.settings import *
from config.constants import *

class EHDownloaderUrlUtils:
    def __init__(self, parent):
        self.parent = parent
        # 親から必要な属性を取得
        self.url_text = getattr(parent, 'url_text', None)
        self.log = getattr(parent, 'log', None)
        
    def normalize_url(self, url):
        """URLを正規化"""
        return self._normalize_gallery_url(url)

    def update_url_background(self, url):
        """URLの背景色を状態に応じて更新（リアルタイム対応）"""
        if not url:
            return
        
        try:
            # 正規化されたURLを取得
            normalized_url = self.normalize_url(url)
            if not normalized_url:
                return

            # URLテキスト全体を取得（安全なアクセス）
            if not self.url_text:
                return
            content = self.url_text.get("1.0", tk.END)
            lines = content.split('\n')
            
            # URLを含む行を検索（正規化URLでも検索）
            target_line = -1
            
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                raw_url_part = line_stripped.split("(")[0].strip()  # マーカーを除いたURL部分
                current_url = self.normalize_url(raw_url_part)
                
                if current_url == normalized_url:
                    target_line = i + 1  # tkinterは1ベース
                    break
            
            if target_line == -1:
                return
            
            # 現在の状態を取得
            status = getattr(self.parent, 'url_status', {}).get(normalized_url, "pending")
            
            # 状態に応じた背景色を設定
            if status == "downloading":
                bg_color = "#FFFACD"  # 薄い黄色（DL中）
                tag_name = "downloading"
            elif status in ["paused", "error"]:
                bg_color = "#FFE4E1"  # 薄い赤色（中断・エラー）
                tag_name = "paused_error"
            elif status == "completed":
                bg_color = "#E0F6FF"  # 薄い青色（完了）
                tag_name = "completed"
            elif status == "skipped":
                bg_color = "#F0F0F0"  # 薄いグレー（スキップ済み）
                tag_name = "skipped"
            else:
                # デフォルト（未処理）
                bg_color = "white"
                tag_name = "default"
            
            # タグを設定
            line_start = f"{target_line}.0"
            line_end = f"{target_line}.end"
            
            # 既存のタグを削除
            for tag in ["downloading", "paused_error", "completed", "skipped", "default"]:
                self.url_text.tag_remove(tag, line_start, line_end)
            
            # 新しいタグを適用
            self.url_text.tag_add(tag_name, line_start, line_end)
            self.url_text.tag_config(tag_name, background=bg_color)
            
            # 画面を強制更新
            self.url_text.update_idletasks()
            
        except Exception as e:
            if self.log:
                self.log(f"URL背景色更新エラー: {e}", "warning")

    def update_progress_display(self, url, current, total, title_override=None, status_text_override=None):
        """プログレス表示を更新（％表示と予想時間付き）"""
        try:
            # タイトルを更新
            if title_override:
                self.update_progress_title(url, title_override)
            
            # プログレス表示を更新（％表示と予想時間付き）
            if status_text_override:
                self.update_current_progress(current, total, status_text_override)
            else:
                # デフォルトのステータステキストに％と時間を含める
                if current > 0 and total > 0:
                    # 開始時間がない場合は現在時刻を設定
                    if not hasattr(self, 'current_download_start_time') or self.current_download_start_time is None:
                        self.current_download_start_time = time.time()
                    
                    elapsed_time = time.time() - self.current_download_start_time
                    progress_percent = (current / total) * 100
                    
                    if current > 0:
                        estimated_total_time = elapsed_time * (total / current)
                        remaining_time = max(0, estimated_total_time - elapsed_time)
                        
                        elapsed_str = f"{int(elapsed_time//60):02d}:{int(elapsed_time%60):02d}"
                        remaining_str = f"{int(remaining_time//60):02d}:{int(remaining_time%60):02d}"
                        
                        status_text = f"ページ {current}/{total} {progress_percent:.1f}% | 経過: {elapsed_str} | 残り予想: {remaining_str}"
                    else:
                        status_text = f"ページ {current}/{total} {progress_percent:.1f}%"
                else:
                    status_text = f"ページ {current}/{total}"
                
                self.update_current_progress(current, total, status_text)
            
        except Exception as e:
            self.log(f"プログレス表示更新エラー: {e}", "error")

    def set_url_status(self, url, status):
        """URL状態を設定（背景色も即座に更新）"""
        self.url_status[url] = status
        # 背景色を即座に更新
        self.root.after_idle(lambda: self.update_url_background(url))

    def reset_after_completion(self, error_occurred=False):
        """完了後のリセット（プログレスバーと背景色は保持）"""
        with self.lock:
            if not error_occurred:
                # エラーが発生していない場合のみ状態をリセット
                self.is_running = False
                self.paused = False
                self._is_restart = False
                self.restart_requested_url = None
                self.skip_requested_url = None
                self.current_gallery_url = None
                self.current_image_page_url = None
                self.current_save_folder = None
                self.current_progress = 0
                self.current_total = 0
                
                # GUIを更新
                self._update_gui_for_idle()
                
                # タイマー停止
                if hasattr(self, 'elapsed_time_timer_id') and self.elapsed_time_timer_id:
                    self.root.after_cancel(self.elapsed_time_timer_id)
                    self.elapsed_time_timer_id = None
            else:
                # エラー発生時は次のダウンロードを試みる
                self._safe_start_next_download()

    def _parse_urls_from_text(self, text):
        """テキストからURLを解析"""
        # 改行、カンマ、タブ、スペース、セミコロン、パイプで分割
        separators = ['\n', '\r\n', '\r', ',', '\t', ' ', ';', '|', '　']  # 全角スペースも追加
        lines = [text]
        
        for sep in separators:
            new_lines = []
            for line in lines:
                new_lines.extend(line.split(sep))
            lines = new_lines
        
        # URLを抽出・検証・正規化
        urls = []
        seen_urls = set()  # 重複除去用
        
        for line in lines:
            line = line.strip()
            if not line:  # 空行をスキップ
                continue
                
            # プレースホルダーテキストをスキップ（削除）
            # if line == self.URL_PLACEHOLDER_TEXT or self.URL_PLACEHOLDER_TEXT in line:
            #     continue
            
            # URLパターンを直接検索（より柔軟に）
            url_patterns = [
                r'https?://(?:e-hentai|exhentai)\.org/g/\d+/[a-f0-9]+/?[^\s]*',
                r'https?://(?:e-hentai|exhentai)\.org/s/[a-f0-9]+/\d+-\d+/?[^\s]*'
            ]
            
            found_urls = []
            for pattern in url_patterns:
                matches = re.findall(pattern, line)
                found_urls.extend(matches)
            
            # 見つからない場合は行全体をURLとして検証
            if not found_urls and self._is_valid_eh_url(line):
                found_urls = [line]
            
            # 各URLを正規化して追加
            for url in found_urls:
                if self._is_valid_eh_url(url):
                    normalized = self._normalize_gallery_url(url)
                    if normalized and normalized not in seen_urls:
                        urls.append(normalized)
                        seen_urls.add(normalized)
                        
        return urls

    def _is_valid_eh_url(self, url):
        """有効なE-Hentai/ExHentaiのURLかチェック（改善版）"""
        if not url or not isinstance(url, str):
            return False
            
        url = url.strip()
        
        # @で始まるURLの処理
        if url.startswith('@'):
            url = url[1:]
        
        # 基本的なURL形式チェック
        if not url.startswith(('http://', 'https://')):
            return False
        
        # URLの末尾に/がない場合は追加
        if not url.endswith('/'):
            url += '/'
        
        # E-Hentai/ExHentaiドメインチェック
        patterns = [
            r'https?://e-hentai\.org/g/\d+/[a-f0-9]+/?.*',
            r'https?://exhentai\.org/g/\d+/[a-f0-9]+/?.*',
            r'https?://e-hentai\.org/s/[a-f0-9]+/\d+-\d+/?.*',
            r'https?://exhentai\.org/s/[a-f0-9]+/\d+-\d+/?.*'
        ]
        
        return any(re.match(pattern, url, re.IGNORECASE) for pattern in patterns)

    def _normalize_gallery_url(self, url):
        """ギャラリーURLを正規化"""
        url = url.strip()
        
        # 画像ページURLをギャラリーURLに変換
        image_page_match = re.match(r'https?://(e-hentai|exhentai)\.org/s/([a-f0-9]+)/(\d+)-(\d+)', url)
        if image_page_match:
            domain, token, gid, page = image_page_match.groups()
            # 個別画像ページURLの場合は、正しいギャラリーURLを取得する必要がある
            # ここでは一時的に間違ったトークンを使用するが、実際の処理はcore/downloader.pyで行う
            return f"https://{domain}.org/g/{gid}/{token}/"
        
        # ギャラリーURL
        gallery_match = re.match(r'https?://(e-hentai|exhentai)\.org/g/(\d+)/([a-f0-9]+)', url)
        if gallery_match:
            domain, gid, token = gallery_match.groups()
            return f"https://{domain}.org/g/{gid}/{token}/"
        
        return None

