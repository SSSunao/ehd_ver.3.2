# -*- coding: utf-8 -*-
"""
Download List Business Logic Layer (三相設計: ビジネスロジック層)

このモジュールはダウンロードリストの操作ロジックを提供します。
UIに依存せず、純粋なビジネスロジックのみを実装します。
"""

from typing import Optional, List, Dict, Callable, Any
from collections import OrderedDict
import threading
from gui.components.download_list_model import (
    DownloadItem,
    DownloadStatus,
    DownloadItemFactory,
    validate_url,
    validate_status_transition
)


class DownloadListController:
    """
    ダウンロードリストのビジネスロジック層
    
    責務:
    - ダウンロードアイテムのCRUD操作
    - ステータス遷移の管理
    - 検索・フィルタリング
    - 統計情報の計算
    
    設計原則:
    - UIに依存しない（Treeviewを直接操作しない）
    - スレッドセーフ（ロック機構を実装）
    - イベント駆動（Observer パターン）
    """
    
    def __init__(self, normalize_url_func: Callable[[str], str]):
        """
        Args:
            normalize_url_func: URL正規化関数（依存性注入）
        """
        self.normalize_url = normalize_url_func
        
        # データストア（順序保持）
        self._items: OrderedDict[str, DownloadItem] = OrderedDict()
        
        # 高速検索用インデックス
        self._url_to_normalized: Dict[str, str] = {}
        self._iid_to_normalized: Dict[str, str] = {}
        
        # スレッドロック
        self._lock = threading.RLock()
        
        # イベントリスナー（Observer パターン）
        self._listeners: List[Callable] = []
    
    # ==================== CRUD操作 ====================
    
    def add_url(self, url: str, **kwargs) -> Optional[DownloadItem]:
        """
        URLを追加
        
        Args:
            url: 追加するURL
            **kwargs: DownloadItemの追加属性
        
        Returns:
            追加されたDownloadItem、または重複の場合はNone
        """
        with self._lock:
            # URL正規化
            normalized_url = self.normalize_url(url)
            
            # 重複チェック
            if normalized_url in self._items:
                return None
            
            # アイテム作成
            item = DownloadItemFactory.create_from_url(
                url=url,
                normalized_url=normalized_url,
                **kwargs
            )
            
            # 登録
            self._items[normalized_url] = item
            self._url_to_normalized[url] = normalized_url
            
            # イベント発火
            self._notify_listeners('item_added', item)
            
            return item
    
    def add_urls_batch(self, urls: List[str]) -> List[DownloadItem]:
        """
        複数URLを一括追加
        
        Args:
            urls: 追加するURLリスト
        
        Returns:
            追加されたDownloadItemリスト
        """
        added_items = []
        
        with self._lock:
            for url in urls:
                # ⭐修正: add_url()内部のロジックを直接実行（イベント重複防止）⭐
                normalized_url = self.normalize_url(url)
                
                # 重複チェック
                if normalized_url in self._items:
                    continue
                
                # アイテム作成
                item = DownloadItemFactory.create_from_url(
                    url=url,
                    normalized_url=normalized_url
                )
                
                # 登録
                self._items[normalized_url] = item
                self._url_to_normalized[url] = normalized_url
                added_items.append(item)
        
        # ⭐一括追加イベントのみ発火（個別イベントは発火しない）⭐
        if added_items:
            self._notify_listeners('items_added_batch', added_items)
        
        return added_items
    
    def get_item(self, url: str) -> Optional[DownloadItem]:
        """
        URLからアイテムを取得
        
        Args:
            url: 取得するURL（元のURLまたは正規化URL）
        
        Returns:
            DownloadItem、または存在しない場合はNone
        """
        with self._lock:
            # 正規化URLで検索
            normalized_url = self.normalize_url(url)
            return self._items.get(normalized_url)
    
    def get_item_by_iid(self, iid: str) -> Optional[DownloadItem]:
        """
        TreeviewアイテムIDからアイテムを取得
        
        Args:
            iid: TreeviewアイテムID
        
        Returns:
            DownloadItem、または存在しない場合はNone
        """
        with self._lock:
            normalized_url = self._iid_to_normalized.get(iid)
            if normalized_url:
                return self._items.get(normalized_url)
            return None
    
    def update_item(self, url: str, **changes) -> Optional[DownloadItem]:
        """
        アイテムを更新（Immutable操作）
        
        Args:
            url: 更新するURL
            **changes: 変更する属性
        
        Returns:
            更新後のDownloadItem、または存在しない場合はNone
        """
        with self._lock:
            normalized_url = self.normalize_url(url)
            old_item = self._items.get(normalized_url)
            
            if not old_item:
                return None
            
            # ステータス遷移のバリデーション
            if 'status' in changes:
                new_status = changes['status']
                if isinstance(new_status, str):
                    new_status = DownloadStatus(new_status)
                
                # ⭐修正: 同じステータスへの変更は早期リターン（エラーを出さない）⭐
                if old_item.status == new_status:
                    return old_item
                
                if not validate_status_transition(old_item.status, new_status):
                    raise ValueError(
                        f"不正なステータス遷移: {old_item.status.value} -> {new_status.value}"
                    )
            
            # ⭐修正: iidを明示的に保持（Immutableパターンでも継承）⭐
            if 'iid' not in changes and old_item.iid:
                changes['iid'] = old_item.iid
            
            # 新しいアイテム作成（Immutable）
            new_item = old_item.clone(**changes)
            self._items[normalized_url] = new_item
            
            # iidインデックスを更新
            if new_item.iid:
                self._iid_to_normalized[new_item.iid] = normalized_url
            
            # ⭐デバッグログ追加: イベント発火確認⭐
            print(f"[DEBUG] Controller: item_updated event fired - URL: {normalized_url[:50]}, status: {new_item.status.value}")
            
            # イベント発火
            self._notify_listeners('item_updated', old_item, new_item)
            
            return new_item
    
    def delete_item(self, url: str) -> bool:
        """
        アイテムを削除
        
        Args:
            url: 削除するURL
        
        Returns:
            削除成功した場合True
        """
        with self._lock:
            normalized_url = self.normalize_url(url)
            item = self._items.get(normalized_url)
            
            if not item:
                return False
            
            # 削除可能かチェック
            if not item.is_deletable:
                raise PermissionError(
                    f"このアイテムは削除できません（ステータス: {item.status.display_name}）"
                )
            
            # 削除
            del self._items[normalized_url]
            self._url_to_normalized.pop(item.url, None)
            if item.iid:
                self._iid_to_normalized.pop(item.iid, None)
            
            # イベント発火
            self._notify_listeners('item_deleted', item)
            
            return True
    
    def delete_all(self, force: bool = False) -> int:
        """
        全アイテムを削除
        
        Args:
            force: 強制削除（削除不可アイテムも削除）
        
        Returns:
            削除されたアイテム数
        """
        with self._lock:
            if not force:
                # 削除可能なアイテムのみ
                deletable_items = [
                    item for item in self._items.values()
                    if item.is_deletable
                ]
            else:
                deletable_items = list(self._items.values())
            
            # 削除
            for item in deletable_items:
                self.delete_item(item.url)
            
            return len(deletable_items)
    
    def set_iid(self, url: str, iid: str):
        """
        TreeviewアイテムIDを設定（UI層から呼び出される）
        
        Args:
            url: URL
            iid: TreeviewアイテムID
        """
        with self._lock:
            normalized_url = self.normalize_url(url)
            item = self._items.get(normalized_url)
            
            if item:
                # ⭐修正: Immutableパターンに従い、clone()で新しいインスタンスを作成⭐
                updated_item = item.clone(iid=iid)
                self._items[normalized_url] = updated_item
                self._iid_to_normalized[iid] = normalized_url
    
    # ==================== 検索・フィルタリング ====================
    
    def get_all_items(self) -> List[DownloadItem]:
        """全アイテムを取得（順序保持）"""
        with self._lock:
            return list(self._items.values())
    
    def get_items_by_status(self, status: DownloadStatus) -> List[DownloadItem]:
        """ステータスでフィルタリング"""
        with self._lock:
            return [
                item for item in self._items.values()
                if item.status == status
            ]
    
    def get_next_pending_item(self) -> Optional[DownloadItem]:
        """次の待機中アイテムを取得"""
        with self._lock:
            for item in self._items.values():
                if item.status == DownloadStatus.PENDING:
                    return item
            return None
    
    def search_by_title(self, keyword: str) -> List[DownloadItem]:
        """タイトルで検索"""
        with self._lock:
            keyword_lower = keyword.lower()
            return [
                item for item in self._items.values()
                if keyword_lower in item.title.lower()
            ]
    
    def contains_url(self, url: str) -> bool:
        """URLが存在するかチェック"""
        with self._lock:
            normalized_url = self.normalize_url(url)
            return normalized_url in self._items
    
    # ==================== 統計情報 ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        with self._lock:
            total = len(self._items)
            status_counts = {}
            
            for status in DownloadStatus:
                count = sum(1 for item in self._items.values() if item.status == status)
                status_counts[status.value] = count
            
            return {
                'total': total,
                'pending': status_counts.get('pending', 0),
                'downloading': status_counts.get('downloading', 0),
                'completed': status_counts.get('completed', 0),
                'error': status_counts.get('error', 0),
                'skipped': status_counts.get('skipped', 0),
                'incomplete': status_counts.get('incomplete', 0),
                'progress_percentage': self._calculate_progress_percentage()
            }
    
    def _calculate_progress_percentage(self) -> float:
        """全体の進捗率を計算"""
        if not self._items:
            return 0.0
        
        total_progress = sum(item.progress for item in self._items.values())
        return total_progress / len(self._items)
    
    def get_total_count(self) -> int:
        """総アイテム数"""
        with self._lock:
            return len(self._items)
    
    def get_completed_count(self) -> int:
        """完了アイテム数"""
        with self._lock:
            return sum(
                1 for item in self._items.values()
                if item.status == DownloadStatus.COMPLETED
            )
    
    def get_pending_count(self) -> int:
        """待機中アイテム数"""
        with self._lock:
            return sum(
                1 for item in self._items.values()
                if item.status == DownloadStatus.PENDING
            )
    
    def is_all_completed(self) -> bool:
        """全て完了したか"""
        with self._lock:
            if not self._items:
                return False
            
            return all(
                item.status in {DownloadStatus.COMPLETED, DownloadStatus.SKIPPED}
                for item in self._items.values()
            )
    
    # ==================== バックアップ・復元 ====================
    
    def export_to_dict(self) -> Dict[str, Any]:
        """
        辞書形式にエクスポート（バックアップ用）
        
        Returns:
            エクスポートデータ
        """
        with self._lock:
            return {
                'version': '3.14',
                'items': [item.to_dict() for item in self._items.values()]
            }
    
    def import_from_dict(self, data: Dict[str, Any]) -> int:
        """
        辞書形式からインポート（復元用）
        
        Args:
            data: インポートデータ
        
        Returns:
            インポートされたアイテム数
        """
        with self._lock:
            items_data = data.get('items', [])
            imported_count = 0
            
            for item_data in items_data:
                try:
                    item = DownloadItemFactory.create_from_backup(item_data)
                    
                    # 重複チェック
                    if item.normalized_url not in self._items:
                        self._items[item.normalized_url] = item
                        self._url_to_normalized[item.url] = item.normalized_url
                        imported_count += 1
                except Exception as e:
                    # ログ出力（UI層で処理）
                    print(f"インポートエラー: {e}")
                    continue
            
            # イベント発火
            if imported_count > 0:
                self._notify_listeners('items_imported', imported_count)
            
            return imported_count
    
    def export_urls_as_text(self) -> str:
        """
        URL一覧をテキスト形式でエクスポート
        
        Returns:
            1行1URLのテキスト
        """
        with self._lock:
            return '\n'.join(item.url for item in self._items.values())
    
    # ==================== イベントリスナー（Observer パターン） ====================
    
    def add_listener(self, callback: Callable):
        """
        イベントリスナーを追加
        
        Args:
            callback: イベントコールバック関数
                      シグネチャ: callback(event_type: str, *args)
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable):
        """イベントリスナーを削除"""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)
    
    def _notify_listeners(self, event_type: str, *args):
        """リスナーに通知"""
        # コピーを作成（イテレーション中の変更を防ぐ）
        listeners = list(self._listeners)
        
        for listener in listeners:
            try:
                listener(event_type, *args)
            except Exception as e:
                print(f"リスナーエラー: {e}")
    
    # ==================== ユーティリティ ====================
    
    def clear(self):
        """全データをクリア"""
        with self._lock:
            self._items.clear()
            self._url_to_normalized.clear()
            self._iid_to_normalized.clear()
            
            self._notify_listeners('cleared')
    
    def __len__(self) -> int:
        """len()サポート"""
        return len(self._items)
    
    def __contains__(self, url: str) -> bool:
        """in演算子サポート"""
        return self.contains_url(url)
    
    def __repr__(self) -> str:
        return f"<DownloadListController: {len(self._items)} items>"


# エクスポート
__all__ = ['DownloadListController']
