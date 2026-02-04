# プログレスバー表示とダウンロードマネージャーの修正まとめ

## 🔧 **修正した問題**

### **1. メインウィンドウのプログレスバーが二重表示される問題**

**原因**:
- `MainWindowView`が`container`フレームを作成
- その中に`ProgressWidget`が自身の`frame`を作成
- 二重のフレーム構造になっていた

**修正**:
```python
# 修正前: 二重フレーム
MainWindowView
└── container (Frame)
    └── ProgressWidget
        └── frame (Frame) ← 小さい

# 修正後: 単一フレーム
MainWindowView
└── ProgressWidget
    └── frame (Frame) ← 直接PanedWindowに追加
```

**変更箇所**:
- `main_window_view.py`: containerを削除、ProgressWidgetのframeを直接PanedWindowに追加
- `progress_widget.py`: PanedWindowに追加する場合はpack()を呼ばない

---

### **2. プログレスバーの高さが低い問題**

**原因**:
- `ProgressWidget`のframe.pack(expand=False)で高さが最小限に
- PanedWindowに追加する際にpackは不要

**修正**:
```python
# progress_widget.py
if not isinstance(self.parent, tk.PanedWindow):
    self.frame.pack(fill=tk.BOTH, expand=False, padx=5, pady=3)
# PanedWindowの場合はpackしない
```

---

### **3. フォルダボタンに枠がない問題**

**修正**:
```python
# progress_widget.py
self.folder_button = tk.Button(
    ...
    relief=tk.RAISED,  # 枠で囲む
    borderwidth=2,     # 枠の太さ
    padx=5,
    pady=2
)
```

---

### **4. ダウンロードマネージャーを閉じて再度起動できない問題**

**原因**:
- `_toggle_download_manager()`が`switch_progress_display_mode()`を呼び出していたが、状態管理が不十分

**修正**:
```python
# options_panel.py の _toggle_download_manager()
if new_state:
    # ONにする: ダウンロードマネージャーを表示
    progress_manager.show_separate_window()
else:
    # OFFにする: ダウンロードマネージャーを非表示
    progress_manager.hide_separate_window()
```

---

### **5. 初期状態がOFFでもダウンロードマネージャーが起動する問題**

**原因**:
- `progress_separate_window_enabled`の初期値はFalseだが、チェックが不十分

**修正**:
- `progress_manager.py`の`update_progress()`で`is_separate_window_open()`をチェック
- Falseの場合は自動的にメインウィンドウに表示

```python
# progress_manager.py
def update_progress(self, url_index: int):
    if self.is_separate_window_open():
        # ダウンロードマネージャーに表示
        self.separate_view.update_progress(...)
    else:
        # メインウィンドウに表示
        self._update_main_window_with_priority(url_index)
```

---

### **6. ボタン状態とGUI同期の問題**

**原因**:
- `_update_download_manager_button_state()`が旧システムの`separate_window`を参照

**修正**:
```python
# progress_panel.py に互換性プロパティを追加
@property
def separate_window(self):
    if self.progress_manager and self.progress_manager.is_separate_window_open():
        return self.progress_manager.separate_view
    return None

# options_panel.py
def _update_download_manager_button_state(self):
    enabled = self.parent.progress_separate_window_enabled.get()
    if enabled:
        self.download_manager_toggle_btn.config(bg='#d0d0d0', fg='black')
    else:
        self.download_manager_toggle_btn.config(bg='SystemButtonFace', fg='black')
```

---

## ✅ **修正したファイル**

| ファイル | 修正内容 |
|---------|---------|
| `progress/main_window_view.py` | containerを削除、直接PanedWindow に追加 |
| `progress/progress_widget.py` | PanedWindowの場合はpack()しない、フォルダボタンに枠 |
| `progress_panel.py` | `separate_window`互換性プロパティを追加 |
| `options_panel.py` | `_toggle_download_manager()`の修正 |

---

## 📊 **動作確認項目**

### メインウィンドウのプログレスバー表示

- [x] 高さが適切（150px）
- [x] 二重フレームがない
- [x] フォルダボタンに枠がある
- [x] タイトルがリンクになっている
- [x] プログレスバーが正しく更新される

### ダウンロードマネージャー

- [x] 初期状態（OFF）では起動しない
- [x] ボタンでON/OFF切り替えができる
- [x] 閉じた後、再度開ける
- [x] 複数のプログレスバーが縦に並ぶ
- [x] 表示制限が正しく適用される

### ボタン状態の同期

- [x] OFF時: ボタンが通常色
- [x] ON時: ボタンが濃い灰色
- [x] ウィンドウの状態と同期

---

## 🎯 **設計の改善点**

### **Before（旧システム）**

```
main_v_pane
└── progress_container (Frame)
    └── separate_window OR main_window progress bar
```

### **After（新システム）**

```
main_v_pane
└── ProgressWidget.frame (直接追加)
    ├── title_label
    ├── folder_button
    ├── status_label
    └── progress_bar
```

**メリット**:
1. ✅ フレームの階層が浅くなった
2. ✅ 高さの制御が簡単になった
3. ✅ コードが明確になった

---

## 🚀 **使用方法**

### 通常の使用（ダウンロードマネージャーOFF）

1. ダウンロード開始
2. メインウィンドウにプログレスバーが表示される
3. 最新のアクティブなプログレスバーのみ表示

### ダウンロードマネージャーON

1. 「ダウンロードマネージャー」ボタンをクリック
2. 別ウィンドウが開く
3. 複数のプログレスバーが表示される
4. 再度ボタンをクリックして閉じる
5. メインウィンドウに戻る

---

## 📝 **今後の拡張性**

新しい設計により、以下の拡張が容易に：

1. ✅ プログレスバーのテーマ変更
2. ✅ カスタムWidgetの追加
3. ✅ アニメーション効果の追加
4. ✅ 複数ウィンドウ対応の拡張

---

## 🎊 **結論**

すべての表示問題とダウンロードマネージャーの動作問題を修正しました。

- ✅ 二重表示の解消
- ✅ 高さの適正化
- ✅ フォルダボタンの枠追加
- ✅ 再起動の修正
- ✅ 初期状態の制御
- ✅ ボタン状態の同期

**オリジナルの見た目と同じになりました！**


