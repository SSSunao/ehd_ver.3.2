# プログレスバーシステム移行ガイド

## 📊 概要

**旧システム**: `progress_panel.py` (5300行の単一ファイル)  
**新システム**: `progress/` パッケージ (6ファイル、約1500行)

## 🎯 改善点

### 1. **コード量70%削減**
- 5300行 → 1500行

### 2. **型安全性の向上**
- `dataclass` + `Optional` 型で静的解析可能
- `ProgressStatus` Enumで状態管理

### 3. **責任の明確化**
| ファイル | 責任 | 行数 |
|---------|------|------|
| `progress_data.py` | データ定義 | ~200 |
| `progress_widget.py` | 単一Widget | ~200 |
| `main_window_view.py` | メインウィンドウView | ~150 |
| `separate_window_view.py` | ダウンロードマネージャーView | ~350 |
| `progress_manager.py` | Facadeコントローラー | ~400 |

### 4. **保守性の向上**
- 各クラスが単一責任
- テストしやすい構造
- ドキュメント完備

## 🔄 API変更

### 旧API（複雑）
```python
# 3つの異なるメソッドが存在
progress_panel.update_current_progress(current, total, status, url, ...)
progress_panel.update_progress_display(url, current, total, ...)
progress_panel.update_progress_status(status_type, details, ...)

# メインウィンドウと別ウィンドウの管理が複雑
progress_panel._show_latest_progress_in_main_window()
progress_panel._update_separate_window_progress_bar(...)
```

### 新API（シンプル）
```python
# 統一インターフェース
progress_manager.update_progress(url_index)

# ダウンロードマネージャーの表示/非表示
progress_manager.show_separate_window()
progress_manager.hide_separate_window()

# 表示制限の設定（即座に反映）
progress_manager.set_max_display_count(10)
```

## 📝 統合手順

### Step 1: インポートを変更

```python
# 旧
from gui.components.progress_panel import EHDownloaderProgressPanel

# 新
from gui.components.progress import ProgressManager
```

### Step 2: 初期化を変更

```python
# 旧
self.progress_panel = EHDownloaderProgressPanel(self)

# 新
self.progress_manager = ProgressManager(
    parent_window=self.root,
    main_v_pane=self.main_v_pane,
    bottom_pane=self.bottom_pane,
    state_manager=self.downloader_core.state_manager,
    managed_folders_getter=lambda: self.downloader_core.managed_folders,
    log_callback=self.log
)
```

### Step 3: メソッド呼び出しを変更

```python
# プログレス更新（旧）
self.progress_panel.update_current_progress(
    current, total, status, url, download_range_info, url_index
)

# プログレス更新（新）
# StateManagerが自動的に通知するため、手動呼び出しは不要！
# ただし、強制更新が必要な場合:
self.progress_manager.update_progress(url_index)
```

```python
# ダウンロードマネージャー表示（旧）
self.progress_panel.switch_progress_display_mode()

# ダウンロードマネージャー表示（新）
if self.progress_manager.is_separate_window_open():
    self.progress_manager.hide_separate_window()
else:
    self.progress_manager.show_separate_window()
```

## ⚙️ 設定連携

### 表示制限数の反映

```python
# オプション変更時
def on_max_display_changed(new_value):
    self.progress_manager.set_max_display_count(new_value)
```

## 🔌 StateManager統合

新システムは **StateManagerのイベントリスナー** で自動更新されます：

```python
# StateManagerが progress_bar_updated イベントを発行
# ↓
# ProgressManagerが自動的にGUIを更新
# ↓
# 手動での update_progress() 呼び出しは不要
```

**メリット**:
- GUIとCore層の疎結合
- 更新漏れの防止
- スレッドセーフ

## 🧪 テスト方法

### 1. 基本動作テスト
```python
# プログレスバー表示
progress_manager.update_progress(0)

# ダウンロードマネージャー表示
progress_manager.show_separate_window()

# 表示制限変更
progress_manager.set_max_display_count(5)
```

### 2. エッジケースのテスト
```python
# Noneセーフティ
progress_info = ProgressInfo.from_dict(0, {})  # 空辞書でもOK
print(progress_info.display_title)  # "準備中..."

# 無効な状態でも安全
progress_manager.update_progress(999)  # ログに警告が出るだけ
```

## 📦 必要な依存関係

```python
# 既存の依存関係のみ（追加なし）
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
```

## 🐛 既知の問題と対処法

### 問題1: StateManagerのsubscribeメソッドがない

**対処法**:
```python
# progress_manager.py の _setup_listeners() で条件チェック済み
if hasattr(self.state_manager, 'subscribe'):
    self.state_manager.subscribe('progress_bar_updated', self._on_progress_updated)
```

### 問題2: managed_foldersが辞書でない

**対処法**:
```python
# Callableで渡すことで、常に最新の値を取得
managed_folders_getter=lambda: self.downloader_core.managed_folders
```

## ✅ 移行チェックリスト

- [ ] 新しいprogressパッケージを`gui/components/`に配置
- [ ] `main_window.py`でインポートを変更
- [ ] ProgressManagerの初期化コードを追加
- [ ] 旧API呼び出しを新APIに置き換え
- [ ] オプション変更時に`set_max_display_count()`を呼び出す
- [ ] 動作テスト（基本機能）
- [ ] 動作テスト（エッジケース）
- [ ] 旧`progress_panel.py`をバックアップ
- [ ] 旧`progress_panel.py`を削除

## 🎉 完了後の効果

1. ✅ **コードの可読性向上** - 各ファイルが単一責任
2. ✅ **バグ修正が容易** - 影響範囲が明確
3. ✅ **型安全性** - mypy等で静的解析可能
4. ✅ **テストしやすい** - モックが簡単
5. ✅ **拡張性** - 新機能追加が容易

---

**質問がある場合**: `progress_manager.py`のdocstringを参照


