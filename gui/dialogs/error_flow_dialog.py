# -*- coding: utf-8 -*-
"""
エラーレジューム処理フローダイアログ（PyQt版）
"""

try:
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QTextEdit, QScrollArea, QWidget)
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

class ErrorFlowDialog(QDialog):
    """エラーレジューム処理フローダイアログ"""
    
    def __init__(self, parent=None):
        if not PYQT5_AVAILABLE:
            raise ImportError("PyQt5 is required for ErrorFlowDialog")
        
        super().__init__(parent)
        self.setWindowTitle("エラーレジューム処理フロー")
        self.setMinimumSize(700, 800)
        
        self._init_ui()
    
    def _init_ui(self):
        """UIの初期化"""
        main_layout = QVBoxLayout()
        
        # ヘッダー
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # フロー内容
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        flow_content = """【エラーレジューム処理フロー】

1. エラー発生
   ↓
2. エラー処理モードに応じて処理
   • 自動再開: リトライ戦略に従って再試行
   • URLスキップ: そのURLをスキップして次へ
   • 画像スキップ: その画像をスキップして次へ
   • 中断: ダウンロードを一時停止
   ↓
3. 自動再開の場合
   ↓
4. リトライ戦略に従って再試行
   • 指数バックオフ: 5秒→10秒→20秒...
   • 線形増加: 5秒→10秒→15秒...
   • 固定間隔: 5秒→5秒→5秒...
   • ランダム: ランダムな間隔
   ↓
5. 最大リトライ回数に達した場合
   ↓
6. リトライ上限達成時の処理
   • 中断: ダウンロードを一時停止
   • 画像スキップ: その画像をスキップ
   • URLスキップ: そのURLをスキップ
   ↓
7. Selenium安全弁が有効な場合
   ↓
8. Seleniumで再試行
   ↓
9. Seleniumでも失敗した場合
   ↓
10. リトライ上限達成時の処理を適用
    （中断/画像スキップ/URLスキップ）

【各設定の意味】

【エラー処理モード】
• 自動再開: エラー時に自動でリトライを試みる
• URLスキップ: エラー時にそのURL全体をスキップ
• 画像スキップ: エラー時にその画像のみをスキップ
• 中断: エラー時にダウンロードを一時停止

【リトライ戦略】
• 指数バックオフ: 待機時間が指数関数的に増加
  例: 5秒→10秒→20秒→40秒...
• 線形増加: 待機時間が一定量ずつ増加
  例: 5秒→10秒→15秒→20秒...
• 固定間隔: 常に同じ待機時間
  例: 5秒→5秒→5秒→5秒...
• ランダム: ランダムな待機時間

【リトライ上限達成時】
• 中断: ダウンロードを一時停止（手動で再開可能）
• 画像スキップ: その画像をスキップして次へ
• URLスキップ: そのURL全体をスキップして次へ

【Selenium安全弁】
• 通常のダウンロードが失敗した場合の代替手段
• ブラウザを自動操作してダウンロードを試みる
• ⚠️ 重要: Selenium使用時は処理時間が大幅に増加します（通常の数倍～数十倍）
• ⚠️ 重要: ブラウザ起動・操作に時間がかかるため、ダウンロード速度が遅くなります
• Seleniumでも失敗した場合:
  → リトライ上限達成時の処理を適用
  （中断/画像スキップ/URLスキップ）

【レジューム設定】
• 最大リトライ回数: リトライを試みる最大回数
• 基本遅延時間: リトライの最初の待機時間（秒）
• 最大遅延時間: リトライの最大待機時間（秒）
• レジューム有効期間: レジュームポイントの有効期間（時間）"""
        
        flow_text = QTextEdit()
        flow_text.setReadOnly(True)
        flow_text.setFont(QFont("Consolas", 10))
        flow_text.setPlainText(flow_content)
        scroll_layout.addWidget(flow_text)
        
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)
        
        # 閉じるボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)


class ErrorPreventionDialog(QDialog):
    """常時エラー対策の説明ダイアログ"""
    
    def __init__(self, parent=None):
        if not PYQT5_AVAILABLE:
            raise ImportError("PyQt5 is required for ErrorPreventionDialog")
        
        super().__init__(parent)
        self.setWindowTitle("常時エラー対策の説明")
        self.setMinimumSize(700, 600)
        
        self._init_ui()
    
    def _init_ui(self):
        """UIの初期化"""
        main_layout = QVBoxLayout()
        
        # ヘッダー
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        main_layout.addLayout(header_layout)
        
        # 説明内容
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        prevention_content = """【常時エラー対策の説明】

【User-Agent 偽装】
• ブラウザになりすましてアクセスします
• 簡単なブロック回避に効果的です
• リソース使用量: 低
• 処理速度への影響: ほぼなし

【httpx (HTTP/2) 使用】
• よりブラウザに近い通信(HTTP/2)を行います
• TLSエラー対策にもなります
• リソース使用量: 中
• 処理速度への影響: 軽微

【SSLのセキュリティレベルを1に下げる】
• SSL/TLSエラーの回避（DH_KEY_TOO_SMALL等）
• 古い暗号化方式への対応
• 互換性の向上
• 注意: セキュリティレベルが下がります
• リソース使用量: 低
• 処理速度への影響: ほぼなし

【常時Selenium使用】
• より確実なページアクセス
• JavaScript対応
• ブラウザレベルの動作
• ⚠️ 重要: リソース使用量が大幅に増加します
• ⚠️ 重要: 処理速度が大幅に遅くなります（通常の数倍～数十倍の時間がかかります）
• 使用推奨: 通常のダウンロードでエラーが頻発する場合のみ

【各オプションの使い分け】
1. まずは「User-Agent 偽装」を試してください（最も軽量）
2. それでもエラーが出る場合は「httpx (HTTP/2) 使用」を追加
3. SSL/TLSエラーが出る場合は「SSLのセキュリティレベルを1に下げる」を追加
4. それでも解決しない場合のみ「常時Selenium使用」を検討してください
   （Seleniumは時間がかかるため、最後の手段として使用）

【推奨設定】
• 通常時: User-Agent偽装のみ
• エラー頻発時: User-Agent偽装 + httpx使用
• 深刻なエラー時: 上記 + SSLセキュリティレベル下げる
• 最終手段: 常時Selenium使用（時間がかかることを理解した上で）"""
        
        prevention_text = QTextEdit()
        prevention_text.setReadOnly(True)
        prevention_text.setFont(QFont("Consolas", 10))
        prevention_text.setPlainText(prevention_content)
        scroll_layout.addWidget(prevention_text)
        
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)
        
        # 閉じるボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)

