# -*- coding: utf-8 -*-
"""
Options Manager - プロフェッショナルなオプション管理システム

【設計思想】
1. Single Source of Truth: GUI変数が唯一の真実のソース
2. Observer Pattern: 変更を自動検知・同期
3. Registry Pattern: オプションを集中管理
4. Declarative Configuration: メタデータベースの定義

【機能】
- GUIとの自動同期（双方向バインディング）
- 設定ファイルへの保存/読み込み
- バリデーション
- 拡張可能な設計（新オプション追加が容易）
"""

import os
import json
import traceback
from typing import Any, Dict, Optional, Callable
from config.option_definitions import (
    OPTION_DEFINITIONS,
    OptionDefinition,
    OptionType,
    OptionScope,
    get_option_definition,
    get_persistent_options
)


class OptionsManager:
    """プロフェッショナルなオプション管理クラス
    
    すべてのオプションを一元管理し、GUIとの自動同期を実現します。
    新しいオプションを追加する場合は、option_definitions.py に
    定義を追加するだけで、このクラスが自動的に処理します。
    """
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderインスタンス（GUIへのアクセス用）
        """
        self.parent = parent
        self._option_definitions = {opt.name: opt for opt in OPTION_DEFINITIONS}
        self._trace_callbacks = {}  # トレースコールバックのID保存用
        self._sync_in_progress = False  # 循環同期防止フラグ
        self._log_enabled = True  # ログ出力制御
        self._auto_sync_initialized = False  # 自動同期初期化済みフラグ
    
    # ========================================
    # 🔄 GUI同期（自動バインディング）
    # ========================================
    
    def setup_auto_sync(self):
        """GUI変数に自動同期を設定（Observer Pattern）
        
        すべてのGUI変数にトレースコールバックを設定し、
        値が変更されたときに自動的に同期処理を実行します。
        """
        # 重複呼び出し防止
        if self._auto_sync_initialized:
            self._log("自動同期は既に初期化済みです（スキップ）", "debug")
            return
        
        try:
            for opt_def in OPTION_DEFINITIONS:
                if opt_def.gui_var_name:
                    self._setup_trace_for_option(opt_def)
            
            self._auto_sync_initialized = True
            self._log("オプション自動同期を設定しました", "info")
        except Exception as e:
            self._log(f"自動同期設定エラー: {e}", "error")
    
    def _setup_trace_for_option(self, opt_def: OptionDefinition):
        """個別オプションのトレース設定"""
        try:
            # GUI変数を取得
            if not hasattr(self.parent, opt_def.gui_var_name):
                return
            
            gui_var = getattr(self.parent, opt_def.gui_var_name)
            
            # StringVar, IntVar等のTkinter変数の場合
            if hasattr(gui_var, 'trace_add'):
                # コールバック関数を作成
                def on_change(*args):
                    self._on_option_changed(opt_def.name)
                
                # トレースを追加
                trace_id = gui_var.trace_add('write', on_change)
                self._trace_callbacks[opt_def.name] = trace_id
                
        except Exception as e:
            self._log(f"トレース設定エラー ({opt_def.name}): {e}", "debug")
    
    def _on_option_changed(self, option_name: str):
        """オプション変更時のコールバック（Observer）
        
        GUI変数が変更されたときに自動的に呼び出され、
        内部状態を同期します。
        """
        # 循環同期防止
        if self._sync_in_progress:
            return
        
        try:
            self._sync_in_progress = True
            opt_def = self._option_definitions.get(option_name)
            if not opt_def:
                return
            
            # GUI→内部値への同期
            self._sync_gui_to_internal(opt_def)
            
        except Exception as e:
            self._log(f"オプション同期エラー ({option_name}): {e}", "debug")
        finally:
            self._sync_in_progress = False
    
    def _sync_gui_to_internal(self, opt_def: OptionDefinition):
        """GUI→内部値への同期"""
        try:
            if not hasattr(self.parent, opt_def.gui_var_name):
                return
            
            gui_var = getattr(self.parent, opt_def.gui_var_name)
            
            # GUI値を取得
            if hasattr(gui_var, 'get'):
                gui_value = gui_var.get()
            else:
                gui_value = gui_var
            
            # 変換関数を適用
            if opt_def.to_internal:
                internal_value = opt_def.to_internal(gui_value)
            else:
                internal_value = gui_value
            
            # バリデーション
            if not opt_def.validate(internal_value):
                self._log(f"バリデーションエラー ({opt_def.name}): {internal_value}", "warning")
                return
            
            # 内部変数に設定（folder_path等）
            # ⭐修正: folder_varの場合、内部変数名はfolder_path⭐
            internal_var_name = opt_def.name
            if opt_def.gui_var_name == "folder_var":
                internal_var_name = "folder_path"  # folder_var → folder_path
                self._log(f"[folder_var同期] GUI値='{gui_value}' → 内部変数='{internal_var_name}'", "debug")
            
            # ⭐重要: GUI変数と同名の場合はsetattr禁止（StringVar等を上書きしないため）⭐
            if hasattr(self.parent, internal_var_name) and internal_var_name != opt_def.gui_var_name:
                setattr(self.parent, internal_var_name, internal_value)
                self._log(f"[同期完了] {opt_def.gui_var_name}({gui_value}) → {internal_var_name}({internal_value})", "debug")
            elif internal_var_name == opt_def.gui_var_name:
                # GUI変数自体なので同期不要（既に更新済み）
                self._log(f"[同期完了] {opt_def.gui_var_name}({gui_value}) → {internal_var_name}({internal_value})", "debug")
            else:
                self._log(f"[警告] 内部変数が存在しません: {internal_var_name}", "warning")

            
        except Exception as e:
            self._log(f"GUI→内部同期エラー ({opt_def.name}): {e}", "debug")
    
    def sync_internal_to_gui(self, option_name: str, value: Any):
        """内部値→GUIへの同期（プログラムから値を設定する場合）"""
        # 循環同期防止
        if self._sync_in_progress:
            return
        
        try:
            self._sync_in_progress = True
            opt_def = self._option_definitions.get(option_name)
            if not opt_def or not opt_def.gui_var_name:
                return
            
            if not hasattr(self.parent, opt_def.gui_var_name):
                return
            
            gui_var = getattr(self.parent, opt_def.gui_var_name)
            
            # 変換関数を適用
            if opt_def.to_gui:
                gui_value = opt_def.to_gui(value)
            else:
                gui_value = value
            
            # GUI変数に設定
            if hasattr(gui_var, 'set'):
                gui_var.set(gui_value)
            
        except Exception as e:
            self._log(f"内部→GUI同期エラー ({option_name}): {e}", "debug")
        finally:
            self._sync_in_progress = False
    
    # ========================================
    # 💾 永続化（設定ファイル保存/読み込み）
    # ========================================
    
    def load_from_file(self, file_path: str) -> bool:
        """設定ファイルから読み込み
        
        Args:
            file_path: 設定ファイルのパス
            
        Returns:
            bool: 成功時True
        """
        try:
            if not os.path.exists(file_path):
                self._log(f"設定ファイルが存在しません: {file_path}", "warning")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # 永続化対象のオプションのみ読み込み
            persistent_opts = get_persistent_options()
            loaded_count = 0
            
            for opt_def in persistent_opts:
                if opt_def.name in settings:
                    value = settings[opt_def.name]
                    
                    # バリデーション
                    if not opt_def.validate(value):
                        self._log(f"無効な値をスキップ ({opt_def.name}): {value}", "warning")
                        continue
                    
                    # GUIに設定
                    self.sync_internal_to_gui(opt_def.name, value)
                    loaded_count += 1
            
            self._log(f"設定を読み込みました ({loaded_count}個のオプション)", "info")
            return True
            
        except Exception as e:
            self._log(f"設定読み込みエラー: {e}", "error")
            return False
    
    def save_to_file(self, file_path: str) -> bool:
        """設定ファイルへ保存
        
        Args:
            file_path: 設定ファイルのパス
            
        Returns:
            bool: 成功時True
        """
        try:
            settings = {}
            
            # 永続化対象のオプションのみ保存
            persistent_opts = get_persistent_options()
            
            for opt_def in persistent_opts:
                value = self.get_option_value(opt_def.name)
                if value is not None:
                    settings[opt_def.name] = value
            
            # ファイルに書き込み
            os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            self._log(f"設定を保存しました ({len(settings)}個のオプション)", "info")
            return True
            
        except Exception as e:
            self._log(f"設定保存エラー: {e}", "error")
            return False
    
    # ========================================
    # 🔍 オプション値の取得/設定
    # ========================================
    
    def get_option_value(self, option_name: str) -> Any:
        """オプション値を取得（GUI変数から）
        
        Args:
            option_name: オプション名
            
        Returns:
            オプション値（存在しない場合はNone）
        """
        try:
            opt_def = self._option_definitions.get(option_name)
            if not opt_def:
                return None
            
            if not opt_def.gui_var_name or not hasattr(self.parent, opt_def.gui_var_name):
                # GUIがない場合は内部変数から取得
                if hasattr(self.parent, option_name):
                    return getattr(self.parent, option_name)
                return opt_def.default_value
            
            gui_var = getattr(self.parent, opt_def.gui_var_name)
            
            if hasattr(gui_var, 'get'):
                return gui_var.get()
            return gui_var
            
        except Exception as e:
            self._log(f"オプション取得エラー ({option_name}): {e}", "debug")
            return None
    
    def set_option_value(self, option_name: str, value: Any) -> bool:
        """オプション値を設定（GUIと内部の両方）
        
        Args:
            option_name: オプション名
            value: 設定する値
            
        Returns:
            bool: 成功時True
        """
        try:
            opt_def = self._option_definitions.get(option_name)
            if not opt_def:
                return False
            
            # バリデーション
            if not opt_def.validate(value):
                self._log(f"無効な値 ({option_name}): {value}", "warning")
                return False
            
            # GUIに設定（トレースで自動的に内部も同期される）
            self.sync_internal_to_gui(option_name, value)
            return True
            
        except Exception as e:
            self._log(f"オプション設定エラー ({option_name}): {e}", "error")
            return False
    
    def get_all_options(self) -> Dict[str, Any]:
        """すべてのオプション値を辞書で取得"""
        options = {}
        for opt_name in self._option_definitions.keys():
            value = self.get_option_value(opt_name)
            if value is not None:
                options[opt_name] = value
        return options
    
    # ========================================
    # 🔧 ユーティリティ
    # ========================================
    
    def reset_to_defaults(self):
        """すべてのオプションをデフォルト値にリセット"""
        try:
            for opt_def in OPTION_DEFINITIONS:
                self.set_option_value(opt_def.name, opt_def.default_value)
            
            self._log("オプションをデフォルト値にリセットしました", "info")
        except Exception as e:
            self._log(f"リセットエラー: {e}", "error")
    
    def validate_all(self) -> tuple[bool, list[str]]:
        """すべてのオプションをバリデーション
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        for opt_def in OPTION_DEFINITIONS:
            value = self.get_option_value(opt_def.name)
            if value is not None and not opt_def.validate(value):
                errors.append(f"{opt_def.display_name} ({opt_def.name}): 無効な値 {value}")
        
        return len(errors) == 0, errors
    
    def get_option_info(self, option_name: str) -> Optional[Dict[str, Any]]:
        """オプションの情報を取得（デバッグ用）"""
        opt_def = self._option_definitions.get(option_name)
        if not opt_def:
            return None
        
        return {
            'name': opt_def.name,
            'display_name': opt_def.display_name,
            'type': opt_def.option_type.value,
            'default': opt_def.default_value,
            'current': self.get_option_value(option_name),
            'scope': opt_def.scope.value,
            'category': opt_def.category,
            'description': opt_def.description
        }
    
    def _log(self, message: str, level: str = "info"):
        """ログ出力（親クラスのlogメソッドを使用）"""
        if not self._log_enabled:
            return
        
        try:
            if hasattr(self.parent, 'log'):
                # レベル変換
                level_map = {
                    "debug": "debug",
                    "info": "info",
                    "warning": "warning",
                    "error": "error"
                }
                self.parent.log(f"[OptionsManager] {message}", level_map.get(level, "info"))
        except Exception:
            pass  # ログ出力エラーは無視
    
    def cleanup(self):
        """クリーンアップ（トレースコールバック削除）"""
        try:
            for opt_name, trace_id in self._trace_callbacks.items():
                opt_def = self._option_definitions.get(opt_name)
                if opt_def and opt_def.gui_var_name and hasattr(self.parent, opt_def.gui_var_name):
                    gui_var = getattr(self.parent, opt_def.gui_var_name)
                    if hasattr(gui_var, 'trace_remove'):
                        try:
                            gui_var.trace_remove('write', trace_id)
                        except Exception:
                            pass
            
            self._trace_callbacks.clear()
        except Exception as e:
            self._log(f"クリーンアップエラー: {e}", "debug")
