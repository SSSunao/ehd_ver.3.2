"""
プログレスバー管理パッケージ

シンプルで保守しやすいアーキテクチャ:
- progress_manager.py: 統一インターフェース（Facade）
- progress_data.py: 型安全なデータクラス
- progress_widget.py: 再利用可能なWidget
- main_window_view.py: メインウィンドウの表示
- separate_window_view.py: ダウンロードマネージャーの表示
"""

from .progress_manager import ProgressManager

__all__ = ['ProgressManager']


