"""
新しいプログレスバーシステムの統合サンプルコード

このファイルは、main_window.py に統合する際の参考コードです。
"""

import tkinter as tk
from gui.components.progress import ProgressManager


class MainWindow:
    """メインウィンドウの統合例"""
    
    def __init__(self, root):
        self.root = root
        
        # ... 既存の初期化コード ...
        
        # ダウンローダーコアの初期化（既存）
        self.downloader_core = self._initialize_downloader_core()
        
        # プログレスマネージャーの初期化（新規）
        self._initialize_progress_manager()
    
    def _initialize_progress_manager(self):
        """プログレスマネージャーの初期化"""
        self.progress_manager = ProgressManager(
            parent_window=self.root,
            main_v_pane=self.main_v_pane,
            bottom_pane=self.bottom_pane,
            state_manager=self.downloader_core.state_manager,
            managed_folders_getter=lambda: self.downloader_core.managed_folders,
            log_callback=self.log
        )
        
        # オプションから最大表示数を設定
        max_display = self.options_manager.get_option('progress_bar_display_limit', 10)
        self.progress_manager.set_max_display_count(max_display)
    
    def log(self, message: str, level: str = "info"):
        """ログ出力（既存のメソッドをそのまま使用）"""
        # 既存のログ処理
        pass
    
    # ===============================================
    # ボタンハンドラーの例
    # ===============================================
    
    def on_download_manager_button_click(self):
        """ダウンロードマネージャーボタンのクリックハンドラー"""
        if self.progress_manager.is_separate_window_open():
            # 開いている場合は閉じる
            self.progress_manager.hide_separate_window()
            self.download_manager_button.config(text="ダウンロードマネージャーを開く")
        else:
            # 閉じている場合は開く
            self.progress_manager.show_separate_window()
            self.download_manager_button.config(text="ダウンロードマネージャーを閉じる")
    
    def on_option_changed(self, option_name: str, new_value):
        """オプション変更時のハンドラー"""
        if option_name == 'progress_bar_display_limit':
            # 表示制限が変更された場合
            self.progress_manager.set_max_display_count(new_value)
    
    # ===============================================
    # 手動更新の例（通常は不要、StateManagerが自動通知）
    # ===============================================
    
    def force_update_progress(self, url_index: int):
        """プログレスバーを強制更新（デバッグ用）"""
        self.progress_manager.update_progress(url_index)
    
    def force_refresh_separate_window(self):
        """ダウンロードマネージャーを強制更新（GUIボタン用）"""
        self.progress_manager.refresh_separate_window()


# ===============================================
# StateManagerとの連携例
# ===============================================

class DownloaderCore:
    """ダウンローダーコアの例"""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.managed_folders = {}
    
    def start_download(self, url: str, url_index: int):
        """ダウンロード開始"""
        # プログレスバーを初期化
        self.state_manager.set_progress_bar(url_index, {
            'url': url,
            'title': None,  # まだ取得していない
            'current': 0,
            'total': 0,
            'status': '待機中',
            'start_time': time.time(),
            'elapsed_time': 0.0,
            'estimated_remaining': None,
            'download_range_info': None
        })
        
        # StateManagerがイベントを発行
        # → ProgressManagerが自動的にGUIを更新
        # → 手動でupdate_progress()を呼ぶ必要なし！
    
    def update_download_progress(self, url_index: int, current: int, total: int):
        """ダウンロード進捗を更新"""
        # StateManagerを更新
        self.state_manager.update_progress_bar(url_index, {
            'current': current,
            'total': total,
            'status': 'ダウンロード中'
        })
        
        # StateManagerがイベントを発行
        # → ProgressManagerが自動的にGUIを更新
        # → 手動でupdate_progress()を呼ぶ必要なし！


# ===============================================
# オプションマネージャーとの連携例
# ===============================================

class OptionsManager:
    """オプションマネージャーの例"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.options = {
            'progress_bar_display_limit': 10
        }
    
    def set_option(self, option_name: str, value):
        """オプションを設定"""
        old_value = self.options.get(option_name)
        self.options[option_name] = value
        
        # 変更を通知
        self.main_window.on_option_changed(option_name, value)


# ===============================================
# 完全な統合例
# ===============================================

def main():
    """完全な統合例"""
    root = tk.Tk()
    root.title("E-Hentai Downloader")
    
    # メインウィンドウを作成
    main_window = MainWindow(root)
    
    # ダウンロードマネージャーボタン
    download_manager_button = tk.Button(
        root,
        text="ダウンロードマネージャーを開く",
        command=main_window.on_download_manager_button_click
    )
    download_manager_button.pack()
    
    # ダウンロード開始ボタン（例）
    def start_download():
        url = "https://e-hentai.org/g/1234567/abcdefghij/"
        url_index = 0
        main_window.downloader_core.start_download(url, url_index)
    
    start_button = tk.Button(
        root,
        text="ダウンロード開始",
        command=start_download
    )
    start_button.pack()
    
    root.mainloop()


if __name__ == "__main__":
    main()


# ===============================================
# 重要な注意事項
# ===============================================

"""
1. StateManagerのイベント発行が必須
   - set_progress_bar() 後に 'progress_bar_updated' イベントを発行
   - ProgressManagerが自動的にGUIを更新

2. managed_foldersは常に最新の辞書を返す
   - lambda: self.downloader_core.managed_folders
   - 動的に取得することで、常に最新のフォルダパスを使用

3. 手動でupdate_progress()を呼ぶ必要はない
   - StateManagerが自動通知
   - ただし、強制更新が必要な場合は呼び出し可能

4. エラーハンドリング
   - ProgressManagerは内部でtry-exceptを使用
   - エラーが発生してもアプリがクラッシュしない

5. スレッドセーフティ
   - ProgressInfoがImmutableなのでスレッドセーフ
   - StateManagerのロックも適切に使用
"""


