"""
GalleryInfoManager - ギャラリー情報の専門管理

責任範囲:
- ギャラリーメタデータの抽出と管理
- ギャラリー完了情報の保存（HTML/CSV/TXT形式）
- 一括ダウンロード情報の生成と保存
- タグ情報の整形と表示

Phase8: downloader.pyから約550行を分離
"""

import os
import time
import csv
import io
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup


class GalleryInfoManager:
    """ギャラリー情報の専門管理クラス"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderCore インスタンス（委譲元）
        """
        self.parent = parent
        self.session_manager = parent.session_manager
    
    # ========================================
    # 基本メタデータ抽出
    # ========================================
    
    def get_manga_title(self, soup: BeautifulSoup) -> str:
        """漫画タイトルを取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            str: タイトル（取得失敗時は"Unknown Title"）
        """
        try:
            # 親クラスのメソッドに委譲
            if hasattr(self.parent.parent, 'get_manga_title'):
                return self.parent.parent.get_manga_title(soup)
            return "Unknown Title"
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"タイトル取得エラー: {e}", "error")
            return "Unknown Title"
    
    def get_artist_and_parody(self, soup: BeautifulSoup) -> tuple:
        """アーティストとパロディ情報を取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            tuple: (artist, parody, character, group)
        """
        try:
            # 親クラスのメソッドに委譲
            if hasattr(self.parent.parent, 'get_artist_and_parody'):
                return self.parent.parent.get_artist_and_parody(soup)
            return "", "", "", ""
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"アーティスト情報取得エラー: {e}", "error")
            return "", "", "", ""
    
    def get_length(self, soup: BeautifulSoup) -> int:
        """ページ数の取得
        
        Args:
            soup: BeautifulSoupオブジェクト
            
        Returns:
            int: ページ数（取得失敗時は0）
        """
        try:
            # gddテーブルから情報を取得
            gdd_table = soup.find('div', {'id': 'gdd'})
            if gdd_table:
                gdt_rows = gdd_table.find_all('tr')
                for row in gdt_rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].text.strip().replace(':', '')
                        value = cells[1].text.strip()
                        
                        if label == 'Length':
                            # "23 pages" のような形式からページ数を抽出
                            import re
                            match = re.search(r'(\d+)', value)
                            if match:
                                return int(match.group(1))
            return 0
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ページ数取得エラー: {e}", "error")
            return 0
    
    # ========================================
    # ギャラリー完了情報の保存
    # ========================================
    
    def save_gallery_completion_info(self, url: str, save_folder: str, gallery_info: Any):
        """ギャラリー完了時のダウンロード情報を保存
        
        Args:
            url: ギャラリーURL
            save_folder: 保存先フォルダ
            gallery_info: ギャラリー情報（辞書またはGalleryInfoオブジェクト）
        """
        try:
            # ⭐修正: 個別保存オプションの判定を簡潔化⭐
            # dl_log_individual_saveがONの場合のみ実行
            if not hasattr(self.parent.parent, 'dl_log_individual_save'):
                return
            if not self.parent.parent.dl_log_individual_save.get():
                return
            
            # ギャラリー情報を準備（取得済みのメタデータを確実に利用）
            original_pages = 0
            if gallery_info:
                if isinstance(gallery_info, dict):
                    original_pages = gallery_info.get('original_total_pages', 0)
                elif hasattr(gallery_info, 'total_pages'):
                    original_pages = gallery_info.total_pages
            
            gallery_data = {
                # 基本情報
                'url': url,
                'title': getattr(self.parent, 'current_gallery_title', '') or getattr(self.parent, 'manga_title', ''),
                'pages': original_pages,
                'file_size': self._calculate_folder_size(save_folder),
                'save_folder': save_folder,
                'download_time': time.strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'completed',
                
                # DLリスト情報
                'dl_index': getattr(self.parent.parent, 'current_url_index', 1),
                'dl_count': len(getattr(self.parent.parent, 'url_list', [])) if hasattr(self.parent.parent, 'url_list') else 1,
                
                # 取得済みのメタデータを直接利用（空でない場合のみ）
                'artist': getattr(self.parent, 'artist', '') if getattr(self.parent, 'artist', '') else None,
                'parody': getattr(self.parent, 'parody', '') if getattr(self.parent, 'parody', '') else None,
                'character': getattr(self.parent, 'character', '') if getattr(self.parent, 'character', '') else None,
                'group': getattr(self.parent, 'group', '') if getattr(self.parent, 'group', '') else None,
                'language': getattr(self.parent, 'language', '') if getattr(self.parent, 'language', '') else None,
                'category': getattr(self.parent, 'category', '') if getattr(self.parent, 'category', '') else None,
                'uploader': getattr(self.parent, 'uploader', '') if getattr(self.parent, 'uploader', '') else None,
                'gid': getattr(self.parent, 'gid', '') if getattr(self.parent, 'gid', '') else None,
                'token': getattr(self.parent, 'token', '') if getattr(self.parent, 'token', '') else None,
                'date': getattr(self.parent, 'date', '') if getattr(self.parent, 'date', '') else None,
                'rating': getattr(self.parent, 'rating', '') if getattr(self.parent, 'rating', '') else None,
                'tags': getattr(self.parent, 'all_extracted_tags', {}) if getattr(self.parent, 'all_extracted_tags', {}) else None,
            }
            
            # 空でないデータのみを追加
            gallery_data = self._filter_empty_data(gallery_data)
            
            # 個別ディレクトリに保存
            self._save_individual_gallery_info(gallery_data, save_folder)
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ギャラリー完了情報保存エラー: {e}", "error")
    
    def _calculate_folder_size(self, folder_path: str) -> int:
        """フォルダサイズを計算
        
        Args:
            folder_path: フォルダパス
            
        Returns:
            int: フォルダサイズ（バイト）
        """
        try:
            if not os.path.exists(folder_path):
                return 0
            
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
            return total_size
        except Exception:
            return 0
    
    def _filter_empty_data(self, gallery_data: Dict[str, Any]) -> Dict[str, Any]:
        """空のデータをフィルタリング
        
        Args:
            gallery_data: ギャラリーデータ辞書
            
        Returns:
            Dict: フィルタリング後のデータ
        """
        return {k: v for k, v in gallery_data.items() if v is not None and str(v).strip()}
    
    def _save_individual_gallery_info(self, gallery_data: Dict[str, Any], save_folder: str):
        """個別ギャラリー情報を個別ディレクトリに保存
        
        Args:
            gallery_data: ギャラリーデータ
            save_folder: 保存先フォルダ
        """
        try:
            # ⭐修正: 保存形式をStringVarから正しく取得⭐
            save_format = 'HTML'  # デフォルト
            if hasattr(self.parent.parent, 'dl_log_file_format'):
                format_var = self.parent.parent.dl_log_file_format
                if hasattr(format_var, 'get'):
                    save_format = format_var.get()
                else:
                    save_format = format_var  # StringVarではない場合は直接使用
            
            # 個別ディレクトリへの保存
            if save_format == 'HTML':
                content = self._generate_gallery_info_html(gallery_data)
                ext = '.html'
            elif save_format == 'CSV':
                content = self._generate_gallery_info_csv(gallery_data)
                ext = '.csv'
            else:  # TEXT
                content = self._generate_gallery_info_txt(gallery_data)
                ext = '.txt'
            
            # ファイル名を生成
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"gallery_info_{timestamp}{ext}"
            filepath = os.path.join(save_folder, filename)
            
            # ファイルに保存
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.session_manager.ui_bridge.post_log(f"📝 ギャラリー情報を保存しました: {os.path.basename(filepath)}")
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"個別ギャラリー情報保存エラー: {e}", "error")
    
    # ========================================
    # HTML生成
    # ========================================
    
    def _generate_gallery_info_html(self, gallery_data: Dict[str, Any]) -> str:
        """HTML形式でギャラリー情報を生成
        
        Args:
            gallery_data: ギャラリーデータ
            
        Returns:
            str: HTML文字列
        """
        html = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ギャラリー情報 - {gallery_data.get('title', 'Unknown')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; }}
        .info {{ margin: 20px 0; }}
        .url {{ word-break: break-all; }}
        .metadata {{ background-color: #f8f8f8; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        .tag-category {{ margin: 10px 0; }}
        .tag-category h4 {{ margin: 5px 0; color: #333; }}
        .tag-row {{ display: flex; align-items: center; margin: 5px 0; }}
        .tag-category-label {{ min-width: 100px; font-weight: bold; }}
        .tag-list {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ギャラリー情報</h1>
        <p>保存日時: {gallery_data.get('download_time', 'Unknown')}</p>
    </div>
    
    <div class="info">
        <h2>基本情報</h2>
        <p><strong>タイトル:</strong> {gallery_data.get('title', 'Unknown')}</p>
        <p><strong>ページ数:</strong> {gallery_data.get('pages', 0)}</p>
        <p><strong>ファイルサイズ:</strong> {self._format_file_size(gallery_data.get('file_size', 0))}</p>
        <p><strong>ステータス:</strong> {gallery_data.get('status', 'Unknown')}</p>
        <p><strong>DL順序:</strong> {gallery_data.get('dl_index', 1)}/{gallery_data.get('dl_count', 1)}</p>
    </div>
    
    <div class="metadata">
        <h2>メタデータ</h2>
"""
        
        # メタデータを条件付きで表示（空でない場合のみ）
        metadata_items = [
            ('アーティスト', gallery_data.get('artist')),
            ('パロディ', gallery_data.get('parody')),
            ('キャラクター', gallery_data.get('character')),
            ('サークル', gallery_data.get('group')),
            ('言語', gallery_data.get('language')),
            ('カテゴリ', gallery_data.get('category')),
            ('アップローダー', gallery_data.get('uploader')),
            ('投稿日', gallery_data.get('date')),
            ('評価', gallery_data.get('rating')),
            ('ギャラリーID', gallery_data.get('gid')),
            ('トークン', gallery_data.get('token')),
        ]
        
        for label, value in metadata_items:
            if value and str(value).strip() and str(value).strip() != 'Unknown':
                if label == 'アップローダー':
                    # アップローダーにハイパーリンクを追加
                    uploader_url = f"https://e-hentai.org/uploader/{value}"
                    html += f"        <p><strong>{label}:</strong> <a href=\"{uploader_url}\" target=\"_blank\">{value}</a></p>\n"
                else:
                    html += f"        <p><strong>{label}:</strong> {value}</p>\n"
        
        # URLを正しく表示
        gallery_url = gallery_data.get('url', '')
        html += f"""    </div>
    
    <div class="info">
        <h2>URL</h2>
        <p class="url"><a href="{gallery_url}" target="_blank">{gallery_url}</a></p>
    </div>
    
    <div class="info">
        <h2>タグ</h2>
"""
        
        # タグをカテゴリ別にグループ化して表示（実際の表示形式に合わせる）
        tags = gallery_data.get('tags', {})
        if tags:
            for category, tag_list in tags.items():
                if isinstance(tag_list, list) and tag_list:
                    html += f"        <div class=\"tag-row\">\n"
                    html += f"            <div class=\"tag-category-label\">{category}:</div>\n"
                    html += f"            <div class=\"tag-list\">\n"
                    
                    for i, tag in enumerate(tag_list):
                        if isinstance(tag, dict):
                            tag_name = tag.get('name', str(tag))
                        else:
                            tag_name = str(tag)
                        
                        # タグURLを生成（スペースを+に変換）
                        tag_url = f"https://e-hentai.org/tag/{category}:{tag_name.replace(' ', '+')}"
                        html += f"                <span class=\"tag\"><a href=\"{tag_url}\" target=\"_blank\">{tag_name}</a></span>\n"
                    
                    html += f"            </div>\n"
                    html += f"        </div>\n"
        else:
            html += '        <p>タグ情報なし</p>\n'
        
        html += """
    </div>
</body>
</html>
"""
        return html
    
    def _format_file_size(self, size_bytes: int) -> str:
        """ファイルサイズをフォーマット
        
        Args:
            size_bytes: サイズ（バイト）
            
        Returns:
            str: フォーマット済みサイズ文字列
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    # ========================================
    # CSV生成
    # ========================================
    
    def _generate_gallery_info_csv(self, gallery_data: Dict[str, Any]) -> str:
        """CSV形式でギャラリー情報を生成
        
        Args:
            gallery_data: ギャラリーデータ
            
        Returns:
            str: CSV文字列
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # ヘッダー
        writer.writerow([
            '項目', '値'
        ])
        
        # データ
        for key, value in gallery_data.items():
            if key == 'tags' and isinstance(value, dict):
                # タグを文字列に変換
                tag_strings = []
                for category, tags in value.items():
                    for tag in tags:
                        if isinstance(tag, dict):
                            tag_strings.append(f"{category}:{tag.get('name', tag)}")
                        else:
                            tag_strings.append(f"{category}:{tag}")
                value = ', '.join(tag_strings)
            elif isinstance(value, (list, dict)):
                value = str(value)
            
            writer.writerow([key, value])
        
        return output.getvalue()
    
    # ========================================
    # TXT生成
    # ========================================
    
    def _generate_gallery_info_txt(self, gallery_data: Dict[str, Any]) -> str:
        """テキスト形式でギャラリー情報を生成
        
        Args:
            gallery_data: ギャラリーデータ
            
        Returns:
            str: テキスト文字列
        """
        lines = []
        lines.append("=== ギャラリー情報 ===")
        lines.append(f"保存日時: {gallery_data.get('download_time', 'Unknown')}")
        lines.append("")
        
        # 基本情報
        lines.append("【基本情報】")
        lines.append(f"タイトル: {gallery_data.get('title', 'Unknown')}")
        lines.append(f"URL: {gallery_data.get('url', 'Unknown')}")
        lines.append(f"ページ数: {gallery_data.get('pages', 0)}")
        lines.append(f"ファイルサイズ: {self._format_file_size(gallery_data.get('file_size', 0))}")
        lines.append(f"保存フォルダ: {gallery_data.get('save_folder', 'Unknown')}")
        lines.append(f"状態: {gallery_data.get('status', 'Unknown')}")
        lines.append(f"DL順序: {gallery_data.get('dl_index', 1)}/{gallery_data.get('dl_count', 1)}")
        lines.append("")
        
        # メタデータ
        lines.append("【メタデータ】")
        lines.append(f"アーティスト: {gallery_data.get('artist', 'Unknown')}")
        lines.append(f"パロディ: {gallery_data.get('parody', 'Unknown')}")
        lines.append(f"キャラクター: {gallery_data.get('character', 'Unknown')}")
        lines.append(f"サークル: {gallery_data.get('group', 'Unknown')}")
        lines.append(f"言語: {gallery_data.get('language', 'Unknown')}")
        lines.append(f"カテゴリ: {gallery_data.get('category', 'Unknown')}")
        lines.append(f"アップローダー: {gallery_data.get('uploader', 'Unknown')}")
        lines.append(f"投稿日: {gallery_data.get('date', 'Unknown')}")
        lines.append(f"評価: {gallery_data.get('rating', 'Unknown')}")
        lines.append(f"ギャラリーID: {gallery_data.get('gid', 'Unknown')}")
        lines.append(f"トークン: {gallery_data.get('token', 'Unknown')}")
        lines.append("")
        
        # タグ情報
        lines.append("【タグ情報】")
        tags = gallery_data.get('tags', {})
        if tags:
            for category, tag_list in tags.items():
                lines.append(f"{category}:")
                for tag in tag_list:
                    if isinstance(tag, dict):
                        lines.append(f"  - {tag.get('name', tag)}")
                    else:
                        lines.append(f"  - {tag}")
        else:
            lines.append("タグ情報なし")
        
        return '\n'.join(lines)
    
    # ========================================
    # 一括ダウンロード情報
    # ========================================
    
    def save_batch_download_info(self):
        """全URL完了時の一括保存処理"""
        try:
            # 一括保存が有効な場合のみ実行
            if not hasattr(self.parent.parent, 'dl_log_enabled') or not self.parent.parent.dl_log_enabled.get():
                return
            # dl_log_enabledがOFFでもdl_log_batch_saveがONなら実行可能
            if not hasattr(self.parent.parent, 'dl_log_batch_save') or not self.parent.parent.dl_log_batch_save.get():
                return
            
            # 親ディレクトリ（保存フォルダ）に一括保存を実行
            self._save_batch_to_parent_directory()
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"一括保存エラー: {e}", "error")
    
    def _save_batch_to_parent_directory(self):
        """親ディレクトリ（保存フォルダ）に一括保存"""
        try:
            # 親ディレクトリ（保存フォルダ）を取得
            parent_dir = self.parent.parent.folder_var.get()
            if not parent_dir or not os.path.exists(parent_dir):
                self.session_manager.ui_bridge.post_log("保存フォルダが設定されていません", "warning")
                return
            
            # 一括保存ファイル名を生成
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"download_summary_{timestamp}.html"
            filepath = os.path.join(parent_dir, filename)
            
            # 全ギャラリー情報を収集
            all_gallery_data = self._collect_all_gallery_data()
            
            # HTMLコンテンツを生成
            html_content = self._generate_batch_summary_html(all_gallery_data)
            
            # ファイルに保存
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            self.session_manager.ui_bridge.post_log(f"📝 一括ダウンロード情報を保存しました: {os.path.basename(filepath)}")
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"一括保存エラー: {e}", "error")
    
    def _collect_all_gallery_data(self) -> List[Dict[str, Any]]:
        """全ギャラリーのデータを収集
        
        Returns:
            List[Dict]: 全ギャラリーデータのリスト
        """
        try:
            all_data = []
            
            # 管理されているフォルダから情報を収集
            if hasattr(self.parent, 'managed_folders'):
                for url, folder_path in self.parent.managed_folders.items():
                    if os.path.exists(folder_path):
                        # フォルダ内の個別情報ファイルを検索
                        for filename in os.listdir(folder_path):
                            if filename.startswith('gallery_info_') and filename.endswith('.html'):
                                # 個別情報ファイルからデータを抽出
                                gallery_data = self._extract_gallery_data_from_html(os.path.join(folder_path, filename))
                                if gallery_data:
                                    all_data.append(gallery_data)
            
            return all_data
            
        except Exception as e:
            self.session_manager.ui_bridge.post_log(f"ギャラリーデータ収集エラー: {e}", "error")
            return []
    
    def _extract_gallery_data_from_html(self, html_file_path: str) -> Optional[Dict[str, Any]]:
        """HTMLファイルからギャラリー情報を抽出
        
        Args:
            html_file_path: HTMLファイルパス
            
        Returns:
            Optional[Dict]: 抽出されたギャラリーデータ（失敗時はNone）
        """
        try:
            with open(html_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 簡単な情報抽出（実際の実装ではより詳細な解析が必要）
            import re
            
            title_match = re.search(r'<title>ギャラリー情報 - ([^<]+)</title>', content)
            url_match = re.search(r'<a href="([^"]+)"', content)
            
            return {
                'title': title_match.group(1) if title_match else 'Unknown',
                'url': url_match.group(1) if url_match else '',
                'html_file': html_file_path
            }
            
        except Exception as e:
            return None
    
    def _generate_batch_summary_html(self, all_gallery_data: List[Dict[str, Any]]) -> str:
        """一括サマリーのHTMLを生成
        
        Args:
            all_gallery_data: 全ギャラリーデータのリスト
            
        Returns:
            str: HTML文字列
        """
        html = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ダウンロード一括サマリー</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .gallery-item {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }}
        .gallery-item h3 {{ margin-top: 0; }}
        .url {{ word-break: break-all; }}
        .stats {{ background-color: #e8f4f8; padding: 10px; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ダウンロード一括サマリー</h1>
        <p>生成日時: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>総ギャラリー数: {len(all_gallery_data)}</p>
    </div>
    
    <div class="stats">
        <h2>統計情報</h2>
        <p>完了したギャラリー数: {len(all_gallery_data)}</p>
        <p>保存場所: {self.parent.parent.folder_var.get()}</p>
    </div>
    
    <div class="summary">
        <h2>ギャラリー一覧</h2>
"""
        
        # 各ギャラリーの情報を追加
        for i, gallery_data in enumerate(all_gallery_data, 1):
            html += f"""
        <div class="gallery-item">
            <h3>{i}. {gallery_data.get('title', 'Unknown')}</h3>
            <p class="url"><a href="{gallery_data.get('url', '')}" target="_blank">{gallery_data.get('url', 'Unknown')}</a></p>
            <p><a href="file:///{gallery_data.get('html_file', '')}" target="_blank">詳細情報を表示</a></p>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html
