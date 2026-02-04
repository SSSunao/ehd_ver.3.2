# -*- coding: utf-8 -*-
"""
カスタム命名変数ヘルパーダイアログ（PyQt版・再設計版）
"""

try:
    from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                                 QLabel, QLineEdit, QComboBox, QSpinBox, QTextEdit,
                                 QGroupBox, QScrollArea, QWidget, QGridLayout,
                                 QTabWidget, QMessageBox, QListWidget, QListWidgetItem,
                                 QSplitter, QCheckBox)
    from PyQt5.QtCore import Qt, pyqtSignal, QEvent
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

class CustomNameDialog(QDialog):
    """カスタム命名変数ヘルパーダイアログ"""
    
    variable_inserted = pyqtSignal(str)  # 変数が挿入されたときに発火
    template_output = pyqtSignal(str)  # テンプレートを出力するときに発火
    
    def __init__(self, parent=None, dialog_type="file", current_template="", 
                 tag_delimiter=" ", tag_max_length=0, use_space_in_delimiter=True):
        """
        Args:
            parent: 親ウィンドウ
            dialog_type: "file" または "folder"
            current_template: 現在のテンプレート
            tag_delimiter: タグ区切り文字
            tag_max_length: タグ最大文字数
            use_space_in_delimiter: 区切り文字に半角スペースを含めるか
        """
        if not PYQT5_AVAILABLE:
            raise ImportError("PyQt5 is required for CustomNameDialog")
        
        super().__init__(parent)
        self.dialog_type = dialog_type
        self.current_template = current_template
        self.setWindowTitle("カスタム命名変数ヘルパー")
        self.setMinimumSize(900, 700)
        
        # タイトルバーに？ボタンを追加（右上の？ボタンは削除）
        # WindowContextHelpButtonHintを使用してタイトルバーに？ボタンを追加
        flags = self.windowFlags()
        self.setWindowFlags(flags | Qt.WindowContextHelpButtonHint)
        
        # タグ変数設定（デフォルト値: 半角スペース、チェックON）
        self.tag_delimiter = tag_delimiter if tag_delimiter else " "
        self.tag_max_length = tag_max_length
        self.use_space_in_delimiter = use_space_in_delimiter if tag_delimiter else True
        
        self._init_ui()
        self.set_current_template(current_template)
        
    def _init_ui(self):
        """UIの初期化"""
        main_layout = QVBoxLayout()
        
        # タブウィジェット
        tabs = QTabWidget()
        
        # 基本情報タブ
        basic_tab = self._create_basic_variables_tab()
        tabs.addTab(basic_tab, "基本情報")
        
        # メタデータタブ（タグ変数も含む）
        metadata_tab = self._create_metadata_variables_tab()
        tabs.addTab(metadata_tab, "メタデータ")
        
        # 使い方タブ
        usage_tab = self._create_usage_tab()
        tabs.addTab(usage_tab, "使い方")
        
        main_layout.addWidget(tabs)
        
        # タグ変数設定セクション
        tag_settings_group = QGroupBox("タグ変数設定")
        tag_settings_layout = QHBoxLayout()
        
        tag_settings_layout.addWidget(QLabel("区切り文字:"))
        self.delimiter_entry = QLineEdit()
        # デフォルト値の設定
        if self.use_space_in_delimiter:
            self.delimiter_entry.setText("")
            self.delimiter_entry.setEnabled(False)  # グレーアウト
            self.tag_delimiter = " "
        else:
            self.delimiter_entry.setText(self.tag_delimiter)
            self.tag_delimiter = self.tag_delimiter
        self.delimiter_entry.textChanged.connect(self._on_delimiter_changed)
        tag_settings_layout.addWidget(self.delimiter_entry)
        
        # 半角スペースチェックボタン
        self.space_checkbox = QCheckBox("半角スペース")
        self.space_checkbox.setChecked(self.use_space_in_delimiter)
        self.space_checkbox.stateChanged.connect(self._on_space_checkbox_changed)
        tag_settings_layout.addWidget(self.space_checkbox)
        
        tag_settings_layout.addWidget(QLabel("最大文字数(0=無制限):"))
        self.max_length_spin = QSpinBox()
        self.max_length_spin.setRange(0, 1000)
        self.max_length_spin.setValue(self.tag_max_length)
        self.max_length_spin.setSpecialValueText("無制限")
        self.max_length_spin.valueChanged.connect(self._on_max_length_changed)
        tag_settings_layout.addWidget(self.max_length_spin)
        
        tag_settings_layout.addStretch()
        tag_settings_group.setLayout(tag_settings_layout)
        main_layout.addWidget(tag_settings_group)
        
        # テンプレート入力セクション
        template_group = QGroupBox("カスタム名")
        template_layout = QHBoxLayout()
        
        self.template_entry = QLineEdit()
        self.template_entry.setText(self.current_template)
        self.template_entry.textChanged.connect(self._on_template_changed)
        template_layout.addWidget(self.template_entry)
        
        # 出力ボタン
        output_btn = QPushButton("出力")
        output_btn.clicked.connect(self._output_template)
        template_layout.addWidget(output_btn)
        
        template_group.setLayout(template_layout)
        main_layout.addWidget(template_group)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.reject)  # ⭐修正: 出力せずに閉じる（reject）⭐
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def _create_usage_tab(self):
        """使い方タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        
        # タグ変数の使い方
        usage_text = QLabel("""【タグ変数の使い方】

• {female} で全てのfemaleタグ（設定した区切り文字で結合）
• {female_1} で1番目のfemaleタグ
• {female_2} で2番目のfemaleタグ
• {character_1} で1番目のcharacterタグ
• {group_2} で2番目のgroupタグ
• 全てのタグカテゴリに対して {カテゴリ名_数値} の形式で使用可能
• 例: {parody_1}, {language_2}, {artist_3} など
• 手入力で使用できます

【使用例】
• {title}_{page:03d}
• {artist}_{title}
• [{category}] {title}
• {date}_{gid}_{title}
• {artist} - {title} [{language_1}]
• {female_1}_{character_1}_{page:03d}

【注意】
• ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます
• タグ変数の区切り文字と最大文字数は「タグ変数設定」で変更できます
• タグのインデックス指定は手入力で使用できます""")
        
        usage_text.setWordWrap(True)
        usage_text.setStyleSheet("padding: 20px; font-size: 10pt;")
        scroll_layout.addWidget(usage_text)
        
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        widget.setLayout(layout)
        return widget
    
    def _show_help(self):
        """ヘルプ情報を表示"""
        help_text = """【カスタム命名変数ヘルパーについて】

【基本情報】
• {title}: タイトル（<h1>）
• {page_title}: タイトル（<title>）
• {page}: ページ番号
• {page:02d}: ページ番号（2桁0埋め）
• {page:03d}: ページ番号（3桁0埋め）
• {ext}: 拡張子
• {original_filename}: 元のファイル名（拡張子なし）
• {dl_index}: DLリスト進行番号（1ベース）
• {dl_count}: DLリスト総数

【メタデータ】
• {artist}: アーティスト名
• {category}: カテゴリ
• {uploader}: アップローダー
• {gid}: ギャラリーID（例: 1234567）
• {token}: トークン
• {date}: 投稿日 (YYYY-MM-DD)
• {rating}: 評価
• {pages}: ページ数
• {filesize}: ファイルサイズ
• {parody}: パロディ名
• {character}: キャラクター名
• {group}: グループ名
• {language}: 言語

【タグ変数】
• {female}: 全てのfemaleタグ（設定した区切り文字で結合）
• {cosplayer}: 全てのcosplayerタグ
• {character}: 全てのcharacterタグ
• {parody}: 全てのparodyタグ
• {group}: 全てのgroupタグ
• {language}: 全てのlanguageタグ
• その他のタグカテゴリも同様に使用可能

【タグのインデックス指定】
• {female_1}: 1番目のfemaleタグ
• {female_2}: 2番目のfemaleタグ
• {character_1}: 1番目のcharacterタグ
• {group_2}: 2番目のgroupタグ
• 全てのタグカテゴリに対して {カテゴリ名_数値} の形式で使用可能
• 例: {parody_1}, {language_2}, {artist_3} など

【使用例】
• {title}_{page:03d}
• {artist}_{title}
• [{category}] {title}
• {date}_{gid}_{title}
• {artist} - {title} [{language_1}]
• {female_1}_{character_1}_{page:03d}

【注意】
• ファイル名に使用できない文字（\\/:*?\"<>|）は自動的に置換されます
• タグ変数の区切り文字と最大文字数は「タグ変数設定」で変更できます
• タグのインデックス指定は手入力で使用できます"""
        
        QMessageBox.information(self, "カスタム命名変数ヘルパー - ヘルプ", help_text)
    
    def _create_basic_variables_tab(self):
        """基本情報変数タブを作成（2カラムレイアウト）"""
        widget = QWidget()
        main_layout = QHBoxLayout()
        
        # 左カラム
        left_scroll = QScrollArea()
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        
        variables = [
            ("title", "ギャラリータイトル（<h1>から取得）"),
            ("page_title", "ページタイトル（<title>タグから取得）"),  # ⭐追加⭐
            ("page", "ページ番号"),
            ("page:02d", "ページ番号（2桁0埋め）"),
            ("page:03d", "ページ番号（3桁0埋め）"),
            ("absolute_page", "絶対ページ番号"),  # ⭐追加: 絶対ページ番号⭐
            ("ext", "拡張子"),
            ("original_filename", "元のファイル名（拡張子なし）"),
            ("dl_index", "DLリスト進行番号（1ベース）"),
            ("dl_count", "DLリスト総数"),
        ]
        
        for var_name, description in variables:
            row_widget = self._create_variable_row(var_name, description)
            left_layout.addWidget(row_widget)
        
        left_layout.addStretch()
        left_widget.setLayout(left_layout)
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        main_layout.addWidget(left_scroll)
        
        # 右カラム（初期値ボタン）
        right_scroll = QScrollArea()
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        
        # カスタムファイル名の初期値
        file_default_row = self._create_variable_row("{artist}_{title}_{page}", "カスタムファイル名の初期値")
        right_layout.addWidget(file_default_row)
        
        # カスタムフォルダ名の初期値
        folder_default_row = self._create_variable_row("{artist}_{title}", "カスタムフォルダ名の初期値")
        right_layout.addWidget(folder_default_row)
        
        right_layout.addStretch()
        right_widget.setLayout(right_layout)
        right_scroll.setWidget(right_widget)
        right_scroll.setWidgetResizable(True)
        main_layout.addWidget(right_scroll)
        
        widget.setLayout(main_layout)
        return widget
    
    def _create_metadata_variables_tab(self):
        """メタデータ変数タブを作成（2カラムレイアウト、タグ変数も含む）"""
        widget = QWidget()
        main_layout = QHBoxLayout()
        
        # 左カラム
        left_scroll = QScrollArea()
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        
        # メタデータ変数（tagsを削除、parody, character, group, languageを右カラムに移動）
        metadata_variables = [
            ("artist", "アーティスト名"),
            ("category", "カテゴリ"),
            ("uploader", "アップローダー"),
            ("gid", "ギャラリーID（例: 1234567）"),
            ("token", "トークン"),
            ("date", "投稿日 (YYYY-MM-DD)"),
            ("rating", "評価"),
            ("pages", "ページ数"),
            ("filesize", "ファイルサイズ"),
        ]
        
        for var_name, description in metadata_variables:
            row_widget = self._create_variable_row(var_name, description)
            left_layout.addWidget(row_widget)
        
        left_layout.addStretch()
        left_widget.setLayout(left_layout)
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        main_layout.addWidget(left_scroll)
        
        # 右カラム（タグ変数 + parody, character, group, language）
        right_scroll = QScrollArea()
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        
        # メタデータ変数（右カラムに移動）
        right_metadata_variables = [
            ("parody", "パロディ名"),
            ("character", "キャラクター名"),
            ("group", "グループ名"),
            ("language", "言語"),
        ]
        
        for var_name, description in right_metadata_variables:
            row_widget = self._create_variable_row(var_name, description)
            right_layout.addWidget(row_widget)
        
        # タグカテゴリ（主要なもののみ、「全ての」を削除）
        tag_categories = ["female", "cosplayer", "other", "male", "artist", "character", 
                         "parody", "group", "language", "category"]
        
        for category in tag_categories:
            # 「全ての」を削除
            row_widget = self._create_variable_row(f"{category}", f"{category}タグ")
            right_layout.addWidget(row_widget)
        
        right_layout.addStretch()
        right_widget.setLayout(right_layout)
        right_scroll.setWidget(right_widget)
        right_scroll.setWidgetResizable(True)
        main_layout.addWidget(right_scroll)
        
        widget.setLayout(main_layout)
        return widget
    
    def _create_variable_row(self, var_name, description):
        """変数行を作成（変数ボタン + 説明）"""
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(2, 1, 2, 1)  # 上下1pxのマージン
        
        # 変数ボタン（高さを増やす）
        btn = QPushButton(f"{{{var_name}}}")
        btn.setFixedHeight(btn.fontMetrics().height() + 10)  # 文字の高さ + 10px（高さを増やす）
        btn.setStyleSheet("font-weight: bold; text-align: left; padding: 5px;")
        btn.clicked.connect(lambda checked, v=var_name: self._insert_variable(v))
        row_layout.addWidget(btn)
        
        # 説明ラベル（高さを増やす）
        desc_label = QLabel(description)
        desc_label.setFixedHeight(desc_label.fontMetrics().height() + 10)  # 文字の高さ + 10px（高さを増やす）
        desc_label.setStyleSheet("color: #666; padding: 5px;")
        row_layout.addWidget(desc_label)
        
        row_layout.addStretch()
        row_widget.setLayout(row_layout)
        return row_widget
    
    def _insert_variable(self, variable_name):
        """変数を挿入"""
        variable_text = f"{{{variable_name}}}"
        # シグナルを発火（メインウィンドウのエントリに挿入）
        self.variable_inserted.emit(variable_text)
        # ダイアログ内のテンプレート入力も更新
        current_text = self.template_entry.text()
        cursor_pos = self.template_entry.cursorPosition()
        new_text = current_text[:cursor_pos] + variable_text + current_text[cursor_pos:]
        self.template_entry.setText(new_text)
        # カーソル位置を更新
        self.template_entry.setCursorPosition(cursor_pos + len(variable_text))
    
    def _output_template(self):
        """テンプレートを出力してウィンドウを閉じる"""
        template = self.template_entry.text()
        # シグナルを発火（メインウィンドウのエントリに出力）
        self.template_output.emit(template)
        # ⭐修正: 出力後にウィンドウを閉じる（accept）⭐
        self.accept()
    
    def closeEvent(self, event):
        """ウィンドウが閉じられるときの処理（タイトルバーの×ボタンなど）"""
        # ⭐修正: タイトルバーの閉じるボタンでも出力せずに閉じる⭐
        # 出力ボタンで閉じた場合は既にaccept()が呼ばれているため、ここでは何もしない
        event.accept()
    
    def event(self, event):
        """イベントハンドラ（タイトルバーの？ボタン用）"""
        if event.type() == QEvent.EnterWhatsThisMode:
            self._show_help()
            return True
        return super().event(event)
    
    def whatsThis(self):
        """What's This? イベントハンドラ"""
        self._show_help()
    
    def _on_delimiter_changed(self, text):
        """区切り文字が変更されたとき"""
        if not self.use_space_in_delimiter:
            self.tag_delimiter = text
    
    def _on_space_checkbox_changed(self, state):
        """半角スペースチェックボタンが変更されたとき"""
        self.use_space_in_delimiter = (state == Qt.Checked)
        if self.use_space_in_delimiter:
            # 半角スペースが優先される
            self.tag_delimiter = " "
            self.delimiter_entry.setEnabled(False)  # グレーアウト
        else:
            # 入力フォームの値を使用
            self.delimiter_entry.setEnabled(True)  # 有効化
            current_delimiter = self.delimiter_entry.text()
            self.tag_delimiter = current_delimiter if current_delimiter else ", "
    
    def _on_max_length_changed(self, value):
        """最大文字数が変更されたとき"""
        self.tag_max_length = value
    
    def _on_template_changed(self, text):
        """テンプレートが変更されたとき"""
        self.current_template = text
    
    def set_current_template(self, template):
        """現在のテンプレートを設定"""
        self.current_template = template
        self.template_entry.setText(template)
    
    def get_tag_delimiter(self):
        """タグ区切り文字を取得"""
        return self.tag_delimiter
    
    def get_tag_max_length(self):
        """タグ最大文字数を取得"""
        return self.tag_max_length
    
    def get_use_space_in_delimiter(self):
        """区切り文字に半角スペースを含めるか取得"""
        return self.use_space_in_delimiter
    
    def get_template(self):
        """現在のテンプレートを取得"""
        return self.template_entry.text()
