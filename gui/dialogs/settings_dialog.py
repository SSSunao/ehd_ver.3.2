# -*- coding: utf-8 -*-
"""
Settings dialog for EH Downloader
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import webbrowser
from config.settings import *
from config.constants import *

class EHDownloaderSettingsDialog:
    def __init__(self, parent):
        self.parent = parent
        
    def show_custom_folder_name_hint(self):
        """保存フォルダ名カスタムのヒントを表示（保存ファイル名と同じ内容）"""
        messagebox.showinfo("カスタムフォルダ名命名について",
            "使用可能な変数（フォルダ名）:\n"
            "・{title}: ギャラリータイトル（<h1>から取得）\n"
            "・{page_title}: ページタイトル（<title>タグから取得）⭐追加⭐\n"
            "・{artist}: アーティスト名\n"
            "・{parody}: パロディ名\n"
            "・{character}: キャラクター名\n"
            "・{group}: グループ名\n"
            "・{language}: 言語\n"
            "・{category}: カテゴリ\n"
            "・{uploader}: アップローダー\n"
            "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
            "・{token}: トークン\n"
            "・{date}: 投稿日 (YYYY-MM-DD)\n"
            "・{rating}: 評価\n"
            "・{pages}: ページ数\n"
            "・{filesize}: ファイルサイズ\n"
            "・{tags}: タグ（スペース区切り）\n"
            "・{female}: femaleタグ（カンマ区切り）\n"
            "・{female_first}: 最初のfemaleタグ\n"
            "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
            "・{cosplayer_first}: 最初のcosplayerタグ\n"
            "・{other}: otherタグ（カンマ区切り）\n"
            "・{other_first}: 最初のotherタグ\n"
            "・{dl_index}: DLリスト進行番号（1ベース）\n"
            "・{dl_count}: DLリスト総数\n\n"
            "例:\n"
            "・{title}\n"
            "・{artist}_{title}\n"
            "・[{category}] {title}\n"
            "・{date}_{gid}_{title}\n"
            "・{artist} - {title} [{language}]\n"
            "・{dl_index:02d}_{title}\n\n"
            "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。")

    def show_custom_name_hint(self):
        """カスタムファイル名のヒントを表示"""
        messagebox.showinfo("カスタム命名について",
            "使用可能な変数（ファイル名）:\n"
            "・{title}: ギャラリータイトル（<h1>から取得）\n"
            "・{page_title}: ページタイトル（<title>タグから取得）⭐追加⭐\n"
            "・{page}: ページ番号\n"
            "・{page:02d}: ページ番号（2桁0埋め）\n"
            "・{page:03d}: ページ番号（3桁0埋め）\n"
            "・{artist}: アーティスト名\n"
            "・{parody}: パロディ名\n"
            "・{character}: キャラクター名\n"
            "・{group}: グループ名\n"
            "・{language}: 言語\n"
            "・{category}: カテゴリ\n"
            "・{uploader}: アップローダー\n"
            "・{gid}: ギャラリーID（URLから抽出、例: 1234567）\n"
            "・{token}: トークン\n"
            "・{date}: 投稿日 (YYYY-MM-DD)\n"
            "・{rating}: 評価\n"
            "・{pages}: ページ数\n"
            "・{filesize}: ファイルサイズ\n"
            "・{tags}: タグ（スペース区切り）\n"
            "・{female}: femaleタグ（カンマ区切り）\n"
            "・{female_first}: 最初のfemaleタグ\n"
            "・{cosplayer}: cosplayerタグ（カンマ区切り）\n"
            "・{cosplayer_first}: 最初のcosplayerタグ\n"
            "・{other}: otherタグ（カンマ区切り）\n"
            "・{other_first}: 最初のotherタグ\n"
            "・{ext}: 拡張子\n"
            "・{original_filename}: 元のファイル名（拡張子なし）\n"
            "・{dl_index}: DLリスト進行番号（1ベース）\n"
            "・{dl_count}: DLリスト総数\n\n"
            "例:\n"
            "・{title}_{page:03d}\n"
            "・{gid}_{page:02d}_{title}\n"
            "・[{artist}] {title} - {page:03d}\n"
            "・{date}_{category}_{page:03d}\n"
            "・{dl_index:02d}_{title}_{page:03d}\n\n"
            "注意: ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます。")

    def browse_folder(self):
        """フォルダ選択ダイアログ"""
        folder = filedialog.askdirectory(initialdir=self.folder_var.get())
        if folder:
            self.folder_var.set(folder)

    def open_download_folder(self):
        """ダウンロードフォルダを開く"""
        try:
            folder = self.folder_var.get()
            if folder and os.path.exists(folder):
                if sys.platform == 'win32':
                    os.startfile(folder)
                elif sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', folder])
                else:  # linux
                    subprocess.run(['xdg-open', folder])
            else:
                self.log("指定されたフォルダが存在しません。", "warning")
        except Exception as e:
            self.log(f"フォルダを開く際にエラーが発生しました: {e}", "error")

    def open_current_download_folder(self):
        """現在のダウンロードフォルダを開く"""
        try:
            folder_path = None
            
            # 最後に保存したフォルダを優先
            if hasattr(self, 'last_download_folder') and self.last_download_folder:
                base_folder = self.last_download_folder
                prefix = self.incomplete_folder_prefix.get() or "[INCOMPLETE]_"
                parent_dir = os.path.dirname(base_folder)
                base_name = os.path.basename(base_folder)
                
                # 接頭辞なしのパスを優先
                if os.path.exists(base_folder):
                    folder_path = base_folder
                # 次に接頭辞付きのパスを試す
                else:
                    incomplete_path = os.path.join(parent_dir, f"{prefix}{base_name}")
                    if os.path.exists(incomplete_path):
                        folder_path = incomplete_path
            
            # 現在のダウンロードフォルダを試す
            if not folder_path and hasattr(self, 'current_save_folder') and self.current_save_folder:
                base_folder = self.current_save_folder
                prefix = self.incomplete_folder_prefix.get() or "[INCOMPLETE]_"
                parent_dir = os.path.dirname(base_folder)
                base_name = os.path.basename(base_folder)
                
                # 接頭辞なしのパスを優先
                if os.path.exists(base_folder):
                    folder_path = base_folder
                # 次に接頭辞付きのパスを試す
                else:
                    incomplete_path = os.path.join(parent_dir, f"{prefix}{base_name}")
                    if os.path.exists(incomplete_path):
                        folder_path = incomplete_path
            
            # 保存先フォルダを試す
            if not folder_path:
                folder = self.folder_var.get()
                if folder and os.path.exists(folder):
                    folder_path = folder
            
            if not folder_path:
                self.log("開くフォルダが設定されていません。", "warning")
                return
            
            # フォルダを開く
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', folder_path])
            else:  # linux
                subprocess.run(['xdg-open', folder_path])
                
            self.log(f"フォルダを開きました: {folder_path}")
            
        except Exception as e:
            self.log(f"フォルダを開く際にエラーが発生しました: {e}", "error")

    def open_current_image_page(self):
        """現在の画像ページを開く"""
        if self.current_image_page_url:
            webbrowser.open(self.current_image_page_url)
