# -*- coding: utf-8 -*-
"""
Download List Integrated Widget (三相設計: 統合レイヤー)

このモジュールは三層（データモデル・ビジネスロジック・プレゼンテーション）を
統合し、外部から簡単に使用できる公開APIを提供します。

使用例:
    # 初期化
    widget = DownloadListWidget(parent, normalize_url_func)
    
    # URLを追加
    widget.add_url("https://e-hentai.org/g/12345/abcdef")
    
    # 状態を更新
    widget.update_status("https://e-hentai.org/g/12345/abcdef", "downloading", progress=50)
    
    # 次のURLを取得
    next_url = widget.get_next_url()
"""

from typing import Optional, Callable, Dict, Any, List
from gui.components.download_list_model import DownloadItem, DownloadStatus
from gui.components.download_list_controller import DownloadListController
from gui.components.download_list_view import DownloadListTreeview


class DownloadListWidget:
    """
    ダウンロードリストの統合ウィジェット
    
    三相設計の統合レイヤーとして、以下の責務を持ちます:
    - 三層の初期化と接続
    - 公開APIの提供（シンプルなインターフェース）
    - 既存コード（url_panel）との互換性維持
    
    設計原則:
    - Facade パターン: 複雑な内部構造を隠蔽
    - 既存のurl_panelと同じインターフェース
    - 段階的移行をサポート（Textウィジェットと並行動作可能）
    """
    
    def __init__(self, parent, normalize_url_func: Callable[[str], str]):
        """
        Args:
            parent: 親ウィジェット
            normalize_url_func: URL正規化関数（依存性注入）
        """
        # ビジネスロジック層
        self.controller = DownloadListController(normalize_url_func)
        
        # プレゼンテーション層
        self.view = DownloadListTreeview(parent, self.controller)
        
        # ⭐追加: frame属性（viewへのエイリアス、既存コード互換）⭐
        self.frame = self.view
        
        # 外部コールバック（後で設定可能）
        self.on_url_added: Optional[Callable] = None
        self.on_url_removed: Optional[Callable] = None
        self.on_status_changed: Optional[Callable] = None
    
    # ==================== 公開API: URL操作 ====================
    
    def add_url(self, url: str, **kwargs) -> bool:
        """
        URLを追加
        
        Args:
            url: 追加するURL
            **kwargs: 追加属性（title, thumbnail_url等）
        
        Returns:
            成功した場合True
        """
        item = self.controller.add_url(url, **kwargs)
        
        if item and self.on_url_added:
            self.on_url_added(url)
        
        return item is not None
    
    def add_urls(self, urls: List[str]) -> int:
        """
        複数URLを一括追加
        
        Args:
            urls: URLリスト
        
        Returns:
            追加された件数
        """
        items = self.controller.add_urls_batch(urls)
        return len(items)
    
    def remove_url(self, url: str) -> bool:
        """
        URLを削除
        
        Args:
            url: 削除するURL
        
        Returns:
            成功した場合True
        """
        try:
            success = self.controller.delete_item(url)
            
            if success and self.on_url_removed:
                self.on_url_removed(url)
            
            return success
        except PermissionError:
            return False
    
    def clear_all(self, force: bool = False) -> int:
        """
        全URLを削除
        
        Args:
            force: 強制削除（DL中・完了も含む）
        
        Returns:
            削除された件数
        """
        return self.controller.delete_all(force=force)
    
    def contains_url(self, url: str) -> bool:
        """
        URLが存在するかチェック
        
        Args:
            url: チェックするURL
        
        Returns:
            存在する場合True
        """
        return self.controller.contains_url(url)
    
    # ==================== 公開API: ステータス操作 ====================
    
    def update_status(self, url: str, status: 'DownloadStatus', **kwargs) -> bool:
        """
        ステータスを更新
        
        Args:
            url: 更新するURL
            status: 新しいステータス（pending, downloading, completed等）
            **kwargs: 追加の更新属性（progress, error_message等）
        
        Returns:
            成功した場合True
        """
        # ⭐修正: スキップ済みURLをdownloadingに戻すことを防止⭐
        item = self.controller.get_item(url)
        if item and item.status in (DownloadStatus.SKIPPED, DownloadStatus.COMPLETED):
            if not isinstance(status, DownloadStatus):
                try:
                    status_enum = DownloadStatus(status)
                except Exception:
                    status_enum = DownloadStatus.PENDING
            else:
                status_enum = status
            if status_enum == DownloadStatus.DOWNLOADING:
                print(f"[DEBUG] update_status: スキップ/完了済みURLのdownloading設定を防止 - URL: {url[:50]}")
                return False
        
        # ⭐デバッグログ追加⭐
        print(f"[DEBUG] update_status called: url={url[:50]}, status={status}, kwargs={kwargs}")
        
        # 文字列をEnumに変換
        if not isinstance(status, DownloadStatus):
            try:
                status = DownloadStatus(status)
            except Exception:
                status = DownloadStatus.PENDING
        
        try:
            item = self.controller.update_item(url, status=status, **kwargs)
            if item and self.on_status_changed:
                self.on_status_changed(url, status.value)
            return item is not None
        except (ValueError, KeyError):
            return False
    
    def update_progress(self, url: str, current: int, total: int, **kwargs):
        """
        進捗を更新
        
        Args:
            url: 更新するURL
            current: 現在のページ
            total: 総ページ数
            **kwargs: 追加の更新属性
        """
        # 進捗率を計算
        progress = int((current / total * 100)) if total > 0 else 0
        
        self.controller.update_item(
            url,
            current_page=current,
            total_pages=total,
            progress=progress,
            **kwargs
        )
    
    def update_title(self, url: str, title: str):
        """
        タイトルを更新
        
        Args:
            url: 更新するURL
            title: 新しいタイトル
        """
        self.controller.update_item(url, title=title)
    
    def set_error(self, url: str, error_message: str):
        """
        エラーを設定
        
        Args:
            url: エラーが発生したURL
            error_message: エラーメッセージ
        """
        item = self.controller.get_item(url)
        if item:
            error_count = item.error_count + 1
            self.controller.update_item(
                url,
                status=DownloadStatus.ERROR,
                error_message=error_message,
                error_count=error_count
            )
    
    def mark_compressed(self, url: str):
        """圧縮完了マーカーを設定"""
        self.controller.update_item(url, is_compressed=True)
    
    def mark_resized(self, url: str):
        """リサイズ完了マーカーを設定"""
        self.controller.update_item(url, is_resized=True)
    
    # ==================== 公開API: 検索・取得 ====================
    
    def get_next_url(self) -> Optional[str]:
        """
        次の待機中URLを取得
        
        Returns:
            次のURL、または存在しない場合はNone
        """
        item = self.controller.get_next_pending_item()
        return item.url if item else None
    
    def get_all_urls(self) -> List[str]:
        """
        全URLを取得
        
        Returns:
            URLリスト
        """
        items = self.controller.get_all_items()
        return [item.url for item in items]
    
    def get_pending_urls(self) -> List[str]:
        """
        待機中のURLを取得
        
        Returns:
            待機中URLリスト
        """
        items = self.controller.get_items_by_status(DownloadStatus.PENDING)
        return [item.url for item in items]
    
    def get_item_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        アイテム情報を取得
        
        Args:
            url: 取得するURL
        
        Returns:
            アイテム情報の辞書、または存在しない場合はNone
        """
        item = self.controller.get_item(url)
        return item.to_dict() if item else None
    
    # ==================== 公開API: 統計情報 ====================
    
    def get_total_count(self) -> int:
        """総URL数を取得"""
        return self.controller.get_total_count()
    
    def get_completed_count(self) -> int:
        """完了URL数を取得"""
        return self.controller.get_completed_count()
    
    def get_pending_count(self) -> int:
        """待機中URL数を取得"""
        return self.controller.get_pending_count()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        return self.controller.get_statistics()
    
    def is_all_completed(self) -> bool:
        """全て完了したかチェック"""
        return self.controller.is_all_completed()
    
    # ==================== 公開API: バックアップ・復元 ====================
    
    def export_to_dict(self) -> Dict[str, Any]:
        """
        バックアップ用にエクスポート
        
        Returns:
            エクスポートデータ
        """
        return self.controller.export_to_dict()
    
    def import_from_dict(self, data: Dict[str, Any]) -> int:
        """
        バックアップから復元
        
        Args:
            data: インポートデータ
        
        Returns:
            インポートされた件数
        """
        return self.controller.import_from_dict(data)
    
    def export_urls_as_text(self) -> str:
        """
        URLを1行1URLのテキスト形式でエクスポート
        
        Returns:
            テキスト形式のURL一覧
        """
        return self.controller.export_urls_as_text()
    
    def import_urls_from_text(self, text: str) -> int:
        """
        テキスト形式からURLをインポート
        
        Args:
            text: テキスト形式のURL一覧
        
        Returns:
            インポートされた件数
        """
        import re
        pattern = r'https?://(?:www\.)?e[-x]hentai\.org/g/\d+/[a-f0-9]+/?'
        urls = re.findall(pattern, text, re.IGNORECASE)
        
        if urls:
            return self.add_urls(urls)
        return 0
    
    # ==================== 公開API: UI操作 ====================
    
    def get_widget(self):
        """
        Tkinterウィジェットを取得
        
        Returns:
            DownloadListTreeviewウィジェット
        """
        return self.view
    
    def scroll_to_url(self, url: str):
        """
        指定URLにスクロール
        
        Args:
            url: スクロール先のURL
        """
        self.view.scroll_to_item(url)
    
    def set_url_open_callback(self, callback: Callable[[str], None]):
        """
        URL開封コールバックを設定
        
        Args:
            callback: コールバック関数
        """
        self.view.on_url_open = callback
    
    def set_item_edit_callback(self, callback: Callable[[DownloadItem], None]):
        """
        アイテム編集コールバックを設定
        
        Args:
            callback: コールバック関数
        """
        self.view.on_item_edit = callback
    
    def set_item_delete_callback(self, callback: Callable[[DownloadItem], None]):
        """
        アイテム削除コールバックを設定
        
        Args:
            callback: コールバック関数
        """
        self.view.on_item_delete = callback
    
    # ==================== url_panel互換API ====================
    
    def get_url_text_content(self) -> str:
        """
        url_panel互換: URLテキストの内容を取得
        
        Returns:
            1行1URLのテキスト
        """
        return self.export_urls_as_text()
    
    def set_url_text_content(self, text: str):
        """
        url_panel互換: URLテキストの内容を設定
        
        Args:
            text: 1行1URLのテキスト
        """
        # 既存をクリア
        self.controller.clear()
        
        # インポート
        self.import_urls_from_text(text)
    
    def update_url_background(self, url: str):
        """
        url_panel互換: URL背景色を更新
        
        Note: Treeviewではタグで管理されるため、自動更新されます
        
        Args:
            url: 更新するURL
        """
        # Treeviewでは自動更新されるため、何もしない
        pass
    
    # ==================== デバッグAPI ====================
    
    def __repr__(self) -> str:
        return f"<DownloadListWidget: {self.get_total_count()} items>"
    
    def __len__(self) -> int:
        return self.get_total_count()


# エクスポート
__all__ = ['DownloadListWidget']
