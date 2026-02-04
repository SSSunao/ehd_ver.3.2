# -*- coding: utf-8 -*-
"""
レジュームセクションのUI定義（options_panel.pyから分離）
"""
import tkinter as tk
from tkinter import ttk
from config.settings import ToolTip


class ResumeSectionUI:
    """レジュームタブのUI作成を担当するクラス"""
    
    def __init__(self, options_panel):
        """
        Args:
            options_panel: OptionsPanel インスタンス
        """
        self.options_panel = options_panel
        self.parent = options_panel.parent
        self.ui_bridge = None  # ⭐Phase 1.5: ThreadSafeUIBridge参照⭐
        self.enhanced_error_widgets = []
    
    def create_enhanced_error_resume_section(self, parent, row):
        """Context-Aware自動エラーハンドリングセクションを作成"""
        # メインフレーム
        error_frame = ttk.LabelFrame(parent, text="Context-Aware自動エラーハンドリング")
        error_frame.grid(row=row, column=0, sticky="ew", padx=5, pady=5)
        error_frame.grid_columnconfigure(0, weight=1)
        
        # エラー処理の有効/無効
        error_enabled_frame = ttk.Frame(error_frame)
        error_enabled_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        if not hasattr(self.parent, 'smart_error_handling'):
            self.parent.smart_error_handling = tk.BooleanVar(value=True)
        
        rb1 = ttk.Radiobutton(error_enabled_frame, text="OFF", value=False, 
                             variable=self.parent.smart_error_handling,
                             command=self._update_error_handling_state)
        rb1.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(rb1)
        
        rb2 = ttk.Radiobutton(error_enabled_frame, text="ON (推奨)", value=True, 
                             variable=self.parent.smart_error_handling,
                             command=self._update_error_handling_state)
        rb2.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(rb2)
        
        # 設定フレーム（子要素）
        self.settings_frame = ttk.Frame(error_frame)
        self.settings_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.settings_frame.grid_columnconfigure(0, weight=0)
        self.settings_frame.grid_columnconfigure(1, weight=1)
                # エラーフレーム全体にTooltipを追加
        ToolTip(error_frame, """Context-Aware自動エラーハンドリング

エラー種別を自動判断して最適な処理を実行:
• タイムアウト → 基準リトライ回数×1.0倍でリトライ
• 503過負荷 → 基準リトライ回数×1.6倍でリトライ（長い待機）
• 429制限 → 基準リトライ回数×2.0倍でリトライ（超長待機）
• 403禁止 → 1回リトライ後、即座にSeleniumを適用
• 404不存在 → 0回リトライ、即座にスキップ
• HTML解析失敗 → 1回失敗後にSeleniumを試行

OFFにするとエラー時にダウンロードを停止し、手動再開が必要です""")
        
        self._create_retry_settings(self.settings_frame)
        self._create_circuit_breaker_setting(self.settings_frame)
        self._create_selenium_setting(self.settings_frame)
        
        # 統計表示エリアは右カラムに移動するため削除
        
        # トレースコールバックを設定（変数変更時に自動更新）
        self.parent.smart_error_handling.trace('w', lambda *args: self._update_error_handling_state())
        
        # 初期状態を設定
        # ⭐Phase 1.5: ui_bridge経由でスケジュール（利用可能な場合）⭐
        if self.ui_bridge:
            self.ui_bridge.schedule_update_later(100, self._update_error_handling_state)
        else:
            self.parent.root.after(100, self._update_error_handling_state)
        
        return error_frame
    
    def _update_error_handling_state(self):
        """自動エラーハンドリングの状態に応じて子要素をグレーアウト"""
        try:
            enabled = self.parent.smart_error_handling.get()
            state = 'normal' if enabled else 'disabled'
            
            # settings_frame内の全ウィジェットを再帰的にグレーアウト
            if hasattr(self, 'settings_frame'):
                self._update_widget_state_recursive(self.settings_frame, state)
                
        except Exception as e:
            if hasattr(self.parent, 'log'):
                self.parent.log(f"エラーハンドリング状態更新エラー: {e}", "error")
    
    def _update_widget_state_recursive(self, widget, state):
        """ウィジェットとその子要素を再帰的に状態更新"""
        try:
            # 自身の状態を更新（ラベル以外）
            if not isinstance(widget, ttk.Label) and hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except tk.TclError:
                    pass  # 一部のウィジェットはstate設定不可
            
            # 子要素を再帰的に更新
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    self._update_widget_state_recursive(child, state)
        except Exception:
            pass  # エラーは無視して続行
    
    def _create_retry_settings(self, parent):
        """基準リトライ回数と基準待機時間の設定"""
        # 基準リトライ回数
        ttk.Label(parent, text="基準リトライ回数:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'base_retry_count'):
            self.parent.base_retry_count = tk.IntVar(value=5)
        retry_entry = ttk.Entry(parent, textvariable=self.parent.base_retry_count, width=8)
        retry_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(retry_entry)
        ttk.Label(parent, text="回", font=('', 8)).grid(row=0, column=2, sticky="w", pady=2)
        
        ToolTip(retry_entry, """基準リトライ回数

エラー種別により自動調整されます:
• タイムアウト: 基準値×1.0倍
• 503過負荷: 基準値×1.6倍
• 429制限: 基準値×2.0倍
• 403禁止: 1回→即Selenium
• 404不存在: 0回→即スキップ

【特殊設定: 基準0回 + Selenium ON】
基準リトライ回数を「0」に設定し、
Selenium自動適用をONにすると:
→ エラー発生時に即座にSeleniumを起動
→ そのページのみでSeleniumでリトライ
→ 次のページは通常HTTPに戻る
→ 通常のHTTPリトライは行わない

推奨値: 5回""")
        
        # 基準待機時間
        ttk.Label(parent, text="基準待機時間:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'base_wait_time'):
            self.parent.base_wait_time = tk.IntVar(value=3)
        wait_entry = ttk.Entry(parent, textvariable=self.parent.base_wait_time, width=8)
        wait_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(wait_entry)
        ttk.Label(parent, text="秒", font=('', 8)).grid(row=1, column=2, sticky="w", pady=2)
        
        ToolTip(wait_entry, """基準待機時間

リトライまでの待機時間の基準値です。
エラー回数に応じて段階的に加算されます:
• 1回目: 基準値
• 2回目: 基準値×1.5
• 3回目: 基準値×2.0
• 4回目以降: 基準値×2.5

例: 基準3秒の場合
→ 1回目: 3秒待機
→ 2回目: 4.5秒待機
→ 3回目: 6秒待機
→ 4回目以降: 7.5秒待機

推奨値: 3秒""")
        
        # リトライ上限達成時の処理（基準待機時間の子要素として配置）
        retry_limit_frame = ttk.LabelFrame(parent, text="リトライ上限達成時の処理")
        retry_limit_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=15, pady=(5,5))
        
        if not hasattr(self.parent, 'retry_limit_action'):
            self.parent.retry_limit_action = tk.StringVar(value="pause")
        
        rb_pause = ttk.Radiobutton(retry_limit_frame, text="中断（手動再開が必要）", value="pause", 
                                   variable=self.parent.retry_limit_action)
        rb_pause.grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(rb_pause)
        
        rb_skip_img = ttk.Radiobutton(retry_limit_frame, text="画像スキップ", value="skip_image", 
                                      variable=self.parent.retry_limit_action)
        rb_skip_img.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(rb_skip_img)
        
        rb_skip_url = ttk.Radiobutton(retry_limit_frame, text="URLスキップ", value="skip_url", 
                                      variable=self.parent.retry_limit_action)
        rb_skip_url.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(rb_skip_url)
        
        ToolTip(retry_limit_frame, """リトライ上限達成時の処理

全てのリトライを試行しても失敗した場合:

【中断】
• ダウンロードを停止
• 「再開」ボタンで手動続行が必要
• 安全だが手間がかかる

【画像スキップ】
• その画像をスキップして次へ進む
• DL失敗ページのURLをプレースホルダーとして保存
• ギャラリーを「未完了」扱いにする
  └ フォルダ名に「(未完了)」を追加
  └ URL背景色を未完了色に変更
  └ 圧縮・トレント作成等をスキップ
• 後で手動リトライ可能

【URLスキップ】
• そのギャラリー全体をスキップ
• 次のURLへ進む
• URL背景色をスキップ色に変更
• 完全に諦める場合に使用

推奨: 画像スキップ（後で再挑戦可能）""")
    
    def _create_circuit_breaker_setting(self, parent):
        """Circuit Breaker閾値の設定"""
        ttk.Label(parent, text="Circuit Breaker閾値:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        if not hasattr(self.parent, 'circuit_breaker_threshold'):
            self.parent.circuit_breaker_threshold = tk.IntVar(value=5)
        cb_entry = ttk.Entry(parent, textvariable=self.parent.circuit_breaker_threshold, width=8)
        cb_entry.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(cb_entry)
        ttk.Label(parent, text="回", font=('', 8)).grid(row=3, column=2, sticky="w", pady=2)
        
        ToolTip(cb_entry, """Circuit Breaker閾値

【動作説明】
同一URL/ギャラリーで連続してエラーが
この回数に達すると:

1. ダウンロードを自動停止
2. 「Circuit Breaker発動」とログ表示
3. 60秒間の冷却期間
4. 60秒後に自動復旧を試行
5. 復旧成功で再開、失敗で停止維持

【目的】
• 無限ループの防止
• サーバー負荷の軽減  
• 一時的な問題の自動回復

【推奨値】
• 通常: 5回
• 不安定なサーバー: 3回
• 安定したサーバー: 10回

例: 閾値5回の場合
→ タイムアウト×5回発生で発動
→ 5回連続で失敗=25回リトライ実行済み
→ これ以上は無駄と判断して停止""")
    
    def _create_selenium_setting(self, parent):
        """エラー時Selenium自動適用の設定（リトライ上限達成後に一度だけSeleniumで試行）"""
        ttk.Label(parent, text="Selenium自動適用:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        # ⭐修正: selenium_fallback_enabled変数を使用（エラー時のみ）⭐
        if not hasattr(self.parent, 'selenium_fallback_enabled'):
            self.parent.selenium_fallback_enabled = tk.BooleanVar(value=False)
        selenium_check = ttk.Checkbutton(parent, text="有効", variable=self.parent.selenium_fallback_enabled)
        selenium_check.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        self.enhanced_error_widgets.append(selenium_check)
        
        ToolTip(selenium_check, """エラー時Selenium自動適用

【重要】
これは「常時Selenium使用」とは異なります。
リトライ上限達成後に一度だけSeleniumで試行する
エラーハンドリング機能です。

【動作タイミング】
1. 通常のHTTPリトライを基準回数×倍率実施
2. 全て失敗した場合のみSeleniumを起動
3. Seleniumで1回だけ試行
4. 成功すればダウンロード続行
5. 失敗すれば「リトライ上限達成時の処理」へ

【Seleniumインストール確認】
Seleniumがインストールされていない場合:
→ ログに「Seleniumがインストールされていません」と表示
→ 通常のリトライ上限処理を実行

【常時Seleniumとの違い】
• 常時Selenium: 全ページで使用（非常に遅い）
• これ: エラー時のみ使用（最後の手段）

OFFにすると通常のHTTPリトライのみ実行""")
    
    def create_error_statistics_section(self, parent, row):
        """エラー統計セクションを作成（右カラム用）"""
        stats_frame = ttk.LabelFrame(parent, text="エラー処理統計")
        stats_frame.grid(row=row, column=0, sticky="nsew", padx=5, pady=5)
        stats_frame.grid_rowconfigure(0, weight=1)
        stats_frame.grid_columnconfigure(0, weight=1)
        
        # Textウィジェット
        self.options_panel.stats_text = tk.Text(stats_frame, height=8, width=40, 
                                                state="disabled", font=("Consolas", 9))
        self.options_panel.stats_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # スクロールバー
        stats_scrollbar = ttk.Scrollbar(stats_frame, orient="vertical", 
                                       command=self.options_panel.stats_text.yview)
        stats_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.options_panel.stats_text.configure(yscrollcommand=stats_scrollbar.set)
        
        # ボタンフレーム
        button_frame = ttk.Frame(stats_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        ttk.Button(button_frame, text="統計更新", 
                  command=self.options_panel._update_error_statistics).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="統計リセット", 
                  command=self.options_panel._reset_error_statistics).pack(side=tk.LEFT, padx=2)
        
        return stats_frame
