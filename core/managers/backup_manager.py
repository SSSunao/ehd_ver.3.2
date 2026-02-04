# -*- coding: utf-8 -*-
"""
Download backup manager for EH Downloader
"""

import os
import json
import csv
import io
from datetime import datetime
from typing import Dict, List, Optional

class DownloadBackupManager:
    """ダウンロード履歴バックアップマネージャー"""
    
    def __init__(self, parent):
        self.parent = parent
        self.backup_enabled = True
        self.retention_count = 100
        self.file_format = "HTML"
        self.save_location = "save_folder"
        self.custom_path = ""
        self.auto_backup = True
        self.gallery_history = []
        self.progress_history = []
    
    def update_settings(self, settings):
        """設定を更新"""
        self.backup_enabled = settings.get('backup_enabled', True)
        self.retention_count = int(settings.get('progress_retention_count', 100))
        self.file_format = settings.get('backup_file_format', 'HTML')
        self.save_location = settings.get('backup_save_location', 'save_folder')
        self.custom_path = settings.get('custom_backup_path', '')
        self.auto_backup = settings.get('auto_backup', True)
    
    def add_gallery_info(self, gallery_data):
        """ギャラリー情報を追加"""
        self.gallery_history.append({
            'url': gallery_data['url'],
            'title': gallery_data['title'],
            'artist': gallery_data.get('artist', ''),
            'parody': gallery_data.get('parody', ''),
            'character': gallery_data.get('character', ''),
            'tags': gallery_data.get('tags', []),
            'pages': gallery_data.get('pages', 0),
            'file_size': gallery_data.get('file_size', 0),
            'save_folder': gallery_data.get('save_folder', ''),
            'download_time': gallery_data.get('download_time', ''),
            'status': gallery_data.get('status', 'unknown')
        })
    
    def add_progress_info(self, progress_data):
        """プログレス情報を追加"""
        self.progress_history.append({
            'url': progress_data['url'],
            'title': progress_data['title'],
            'current': progress_data['current'],
            'total': progress_data['total'],
            'status': progress_data['status'],
            'timestamp': progress_data['timestamp'],
            'elapsed_time': progress_data.get('elapsed_time', 0)
        })
    
    def should_backup(self):
        """バックアップが必要かチェック"""
        return (len(self.progress_history) >= self.retention_count or 
                self._is_download_complete() or
                self._is_clear_requested())
    
    def create_backup(self):
        """バックアップを作成"""
        if not self.backup_enabled:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"download_history_{timestamp}"
        
        # 保存場所を決定
        save_dir = self._get_save_directory()
        if not save_dir:
            return None
        
        # ファイル形式に応じてバックアップを作成
        if self.file_format == "HTML":
            return self._create_html_backup(save_dir, base_filename)
        elif self.file_format == "Markdown":
            return self._create_markdown_backup(save_dir, base_filename)
        elif self.file_format == "JSON":
            return self._create_json_backup(save_dir, base_filename)
        elif self.file_format == "CSV":
            return self._create_csv_backup(save_dir, base_filename)
        elif self.file_format == "HTML+JSON":
            return self._create_html_json_backup(save_dir, base_filename)
        elif self.file_format == "Markdown+JSON":
            return self._create_markdown_json_backup(save_dir, base_filename)
        
        return None
    
    def save_batch_data(self):
        """一括保存処理（完了時・クリア時・ウィンドウ終了時）"""
        try:
            if not self.backup_enabled:
                return
            
            # 現在のデータをバックアップとして保存
            backup_file = self.create_backup()
            if backup_file:
                self.parent.log(f"📝 一括保存完了: {os.path.basename(backup_file)}")
            
            # ⭐修正: 履歴をクリアしない（保持する）⭐
            # self.gallery_history.clear()  # コメントアウト
            # self.progress_history.clear()  # コメントアウト
            
        except Exception as e:
            self.parent.log(f"一括保存エラー: {e}", "error")
    
    def _get_save_directory(self):
        """保存ディレクトリを取得"""
        try:
            if self.save_location == "save_folder":
                folder_path = self.parent.folder_var.get()
                if not folder_path or not isinstance(folder_path, str):
                    return None
                return folder_path
            elif self.save_location == "dedicated_folder":
                base_dir = self.parent.folder_var.get()
                if not base_dir or not isinstance(base_dir, str):
                    return None
                backup_dir = os.path.join(base_dir, "download_history")
                os.makedirs(backup_dir, exist_ok=True)
                return backup_dir
            elif self.save_location == "custom":
                if self.custom_path and isinstance(self.custom_path, str):
                    os.makedirs(self.custom_path, exist_ok=True)
                    return self.custom_path
                else:
                    folder_path = self.parent.folder_var.get()
                    if not folder_path or not isinstance(folder_path, str):
                        return None
                    return folder_path
            else:
                folder_path = self.parent.folder_var.get()
                if not folder_path or not isinstance(folder_path, str):
                    return None
                return folder_path
        except Exception:
            return None
    
    def _create_html_backup(self, save_dir, base_filename):
        """HTMLバックアップを作成"""
        try:
            html_content = self._generate_html_content()
            filepath = os.path.join(save_dir, f"{base_filename}.html")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return filepath
        except Exception as e:
            print(f"HTML backup creation error: {e}")
            return None
    
    def _create_markdown_backup(self, save_dir, base_filename):
        """Markdownバックアップを作成"""
        try:
            markdown_content = self._generate_markdown_content()
            filepath = os.path.join(save_dir, f"{base_filename}.md")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            return filepath
        except Exception as e:
            print(f"Markdown backup creation error: {e}")
            return None
    
    def _create_json_backup(self, save_dir, base_filename):
        """JSONバックアップを作成"""
        try:
            json_data = self._generate_json_data()
            filepath = os.path.join(save_dir, f"{base_filename}.json")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            return filepath
        except Exception as e:
            print(f"JSON backup creation error: {e}")
            return None
    
    def _create_csv_backup(self, save_dir, base_filename):
        """CSVバックアップを作成"""
        try:
            csv_content = self._generate_csv_content()
            filepath = os.path.join(save_dir, f"{base_filename}.csv")
            
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(csv_content)
            
            return filepath
        except Exception as e:
            print(f"CSV backup creation error: {e}")
            return None
    
    def _create_html_json_backup(self, save_dir, base_filename):
        """HTML + JSONバックアップを作成"""
        html_file = self._create_html_backup(save_dir, base_filename)
        json_file = self._create_json_backup(save_dir, base_filename)
        return html_file, json_file
    
    def _create_markdown_json_backup(self, save_dir, base_filename):
        """Markdown + JSONバックアップを作成"""
        markdown_file = self._create_markdown_backup(save_dir, base_filename)
        json_file = self._create_json_backup(save_dir, base_filename)
        return markdown_file, json_file
    
    def _generate_html_content(self):
        """HTMLコンテンツを生成"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>ダウンロード履歴 - {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .progress-bar {{ background: #f0f0f0; border: 1px solid #ccc; height: 20px; margin: 5px 0; border-radius: 4px; overflow: hidden; }}
        .progress-fill {{ background: linear-gradient(90deg, #4CAF50, #45a049); height: 100%; transition: width 0.3s; }}
        .gallery-item {{ border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 6px; background-color: #fafafa; }}
        .gallery-item h3 {{ margin-top: 0; color: #333; }}
        .gallery-item a {{ color: #0066cc; text-decoration: none; }}
        .gallery-item a:hover {{ text-decoration: underline; }}
        .status-completed {{ color: #4CAF50; font-weight: bold; }}
        .status-error {{ color: #f44336; font-weight: bold; }}
        .status-skipped {{ color: #ff9800; font-weight: bold; }}
        .status-downloading {{ color: #2196F3; font-weight: bold; }}
        .progress-info {{ background: #e3f2fd; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        .gallery-info {{ background: #f3e5f5; padding: 10px; border-radius: 4px; margin: 10px 0; }}
        .tag {{ background: #e1f5fe; color: #0277bd; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; margin: 2px; display: inline-block; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📥 ダウンロード履歴</h1>
        <p><strong>生成日時:</strong> {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
        <p><strong>総プログレス数:</strong> {len(self.progress_history)}件</p>
        
        <h2>📊 プログレス履歴</h2>
        {self._generate_progress_html()}
        
        <!-- ⭐削除: ギャラリー情報セクションを削除 ⭐ -->
    </div>
</body>
</html>"""
        return html
    
    def _generate_progress_html(self):
        """プログレス部分のHTMLを生成"""
        if not self.progress_history:
            return "<p>プログレス履歴がありません。</p>"
        
        html = ""
        for progress in self.progress_history:
            percentage = (progress['current'] / progress['total'] * 100) if progress['total'] > 0 else 0
            progress_bars = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
            
            status_class = f"status-{progress['status']}"
            
            html += f"""
            <div class="gallery-item">
                <div class="progress-info">
                    <h3><a href="{progress['url']}" target="_blank">{progress['title']}</a></h3>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {percentage:.1f}%"></div>
                    </div>
                    <p><strong>進捗:</strong> {progress_bars} ({progress['current']}/{progress['total']} - {percentage:.1f}%)</p>
                    <p><strong>状態:</strong> <span class="{status_class}">{progress['status']}</span></p>
                    <p><strong>経過時間:</strong> {progress['elapsed_time']}秒</p>
                </div>
            </div>
            """
        return html
    
    def _generate_gallery_html(self):
        """ギャラリー部分のHTMLを生成"""
        if not self.gallery_history:
            return "<p>ギャラリー情報がありません。</p>"
        
        html = ""
        for gallery in self.gallery_history:
            status_class = f"status-{gallery['status']}"
            tags_html = "".join([f'<span class="tag">{tag}</span>' for tag in gallery['tags']])
            
            html += f"""
            <div class="gallery-item">
                <div class="gallery-info">
                    <h3><a href="{gallery['url']}" target="_blank">{gallery['title']}</a></h3>
                    <p><strong>アーティスト:</strong> {gallery['artist']}</p>
                    <p><strong>パロディ:</strong> {gallery['parody']}</p>
                    <p><strong>キャラクター:</strong> {gallery['character']}</p>
                    <p><strong>ページ数:</strong> {gallery['pages']}</p>
                    <p><strong>ファイルサイズ:</strong> {self._format_file_size(gallery['file_size'])}</p>
                    <p><strong>保存場所:</strong> <a href="file:///{gallery['save_folder']}">{gallery['save_folder']}</a></p>
                    <p><strong>タグ:</strong> {tags_html}</p>
                    <p><strong>ダウンロード時刻:</strong> {gallery['download_time']}</p>
                    <p><strong>状態:</strong> <span class="{status_class}">{gallery['status']}</span></p>
                </div>
            </div>
            """
        return html
    
    def _generate_markdown_content(self):
        """Markdownコンテンツを生成"""
        md = f"""# 📥 ダウンロード履歴

**生成日時:** {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
**総ギャラリー数:** {len(self.gallery_history)}件
**総プログレス数:** {len(self.progress_history)}件

## 📊 プログレス履歴

"""
        
        for progress in self.progress_history:
            percentage = (progress['current'] / progress['total'] * 100) if progress['total'] > 0 else 0
            progress_bars = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
            
            md += f"""### {progress['title']}

- **URL:** {progress['url']}
- **進捗:** {progress_bars} ({progress['current']}/{progress['total']} - {percentage:.1f}%)
- **状態:** {progress['status']}
- **経過時間:** {progress['elapsed_time']}秒

"""
        
        md += """## 🖼️ ギャラリー情報

"""
        
        for gallery in self.gallery_history:
            md += f"""### {gallery['title']}

- **URL:** {gallery['url']}
- **アーティスト:** {gallery['artist']}
- **パロディ:** {gallery['parody']}
- **キャラクター:** {gallery['character']}
- **ページ数:** {gallery['pages']}
- **ファイルサイズ:** {self._format_file_size(gallery['file_size'])}
- **保存場所:** {gallery['save_folder']}
- **タグ:** {', '.join(gallery['tags'])}
- **ダウンロード時刻:** {gallery['download_time']}
- **状態:** {gallery['status']}

"""
        
        return md
    
    def _generate_csv_content(self):
        """CSVコンテンツを生成"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # ヘッダー
        writer.writerow([
            'タイトル', 'URL', 'アーティスト', 'パロディ', 'キャラクター', 
            'ページ数', 'ファイルサイズ', '保存場所', 'タグ', 'ダウンロード時刻', '状態'
        ])
        
        # データ
        for gallery in self.gallery_history:
            writer.writerow([
                gallery['title'],
                gallery['url'],
                gallery['artist'],
                gallery['parody'],
                gallery['character'],
                gallery['pages'],
                self._format_file_size(gallery['file_size']),
                gallery['save_folder'],
                ', '.join(gallery['tags']),
                gallery['download_time'],
                gallery['status']
            ])
        
        return output.getvalue()
    
    def _generate_json_data(self):
        """JSONデータを生成"""
        return {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_galleries': len(self.gallery_history),
                'total_progress_entries': len(self.progress_history),
                'backup_format': self.file_format
            },
            'gallery_history': self.gallery_history,
            'progress_history': self.progress_history
        }
    
    def _format_file_size(self, size_bytes):
        """ファイルサイズをフォーマット"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _is_download_complete(self):
        """ダウンロードが完了したかチェック"""
        # 実装は必要に応じて追加
        return False
    
    def _is_clear_requested(self):
        """クリア操作が要求されたかチェック"""
        # 実装は必要に応じて追加
        return False
