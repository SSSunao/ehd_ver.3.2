# -*- coding: utf-8 -*-
"""
プリセットコントローラー
設定のプリセット保存・読み込み機能を管理
"""

import os
import json
from tkinter import filedialog, messagebox


class PresetController:
    """設定プリセットの保存・読み込みを担当するコントローラー"""
    
    def __init__(self, parent):
        """
        Args:
            parent: EHDownloaderインスタンス（ILogger, IGUIOperationsを実装）
        """
        self.parent = parent
    
    def save_current_options(self):
        """現在のオプション設定をプリセットとして保存"""
        try:
            # 現在の設定を取得
            settings = self._collect_current_settings()
            
            # 保存先ファイルを選択
            filepath = filedialog.asksaveasfilename(
                title="設定プリセットを保存",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~"),
                initialfile="user_preset.json"
            )
            
            if not filepath:
                return
            
            # ファイルに保存
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            messagebox.showinfo("設定保存", f"現在の設定をプリセットとして保存しました:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("エラー", f"設定保存に失敗しました: {e}")
    
    def load_saved_options(self):
        """保存された設定プリセットをロード"""
        try:
            # 読み込むファイルを選択
            filepath = filedialog.askopenfilename(
                title="設定プリセットを読み込む",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~")
            )
            
            if not filepath or not os.path.exists(filepath):
                if filepath:
                    messagebox.showwarning("設定ロード", "指定された設定ファイルが見つかりません。")
                return
            
            # ファイルから読み込み
            with open(filepath, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # 設定を適用
            self._apply_settings(settings)
            
            messagebox.showinfo("設定ロード", f"設定プリセットを読み込みました:\n{filepath}")
            
        except Exception as e:
            messagebox.showerror("エラー", f"設定ロード中にエラーが発生しました: {e}")
    
    def _collect_current_settings(self):
        """現在の設定を収集"""
        # 安全な値取得のヘルパー関数
        def safe_get(var, default=None):
            try:
                if hasattr(var, 'get'):
                    return var.get()
                else:
                    return var if var is not None else default
            except Exception:
                return default
        
        settings = {
            # ウィンドウ設定
            'window_geometry': self.parent.root.geometry() if hasattr(self.parent, 'root') else "",
            
            # 基本設定
            'folder_path': safe_get(self.parent.folder_var),
            'wait_time': safe_get(self.parent.wait_time),
            'sleep_value': safe_get(self.parent.sleep_value),
            'save_format': safe_get(self.parent.save_format),
            'save_name': safe_get(self.parent.save_name),
            'custom_name': safe_get(self.parent.custom_name),
            
            # リサイズ設定
            'resize_mode': safe_get(self.parent.resize_mode),
            'resize_enabled': safe_get(self.parent.resize_enabled),
            'resize_values': {k: safe_get(v) for k, v in self.parent.resize_values.items()},
            'interpolation_mode': safe_get(self.parent.interpolation_mode, "三次補完（画質優先）"),
            'sharpness_value': safe_get(self.parent.sharpness_value, "1.5"),
            'resize_filename_enabled': safe_get(self.parent.resize_filename_enabled, False),
            'resized_prefix': safe_get(self.parent.resized_prefix, ""),
            'resized_suffix': safe_get(self.parent.resized_suffix, "_resized"),
            'keep_original': safe_get(self.parent.keep_original, True),
            'resize_save_location': safe_get(self.parent.resize_save_location, "child"),
            'resized_subdir_name': safe_get(self.parent.resized_subdir_name, "resized"),
            
            # フォルダ・ファイル管理
            'duplicate_folder_mode': self.parent._convert_duplicate_mode_to_english(
                safe_get(self.parent.duplicate_folder_mode, "rename")),
            'rename_incomplete_folder': safe_get(self.parent.rename_incomplete_folder, False),
            'incomplete_folder_prefix': safe_get(self.parent.incomplete_folder_prefix, "[INCOMPLETE]_"),
            'folder_name_mode': safe_get(self.parent.folder_name_mode, "h1_priority"),
            'custom_folder_name': safe_get(self.parent.custom_folder_name, "{artist}_{title}"),
            'duplicate_file_mode': self.parent._convert_duplicate_mode_to_english(
                safe_get(self.parent.duplicate_file_mode, "overwrite")),
            
            # 圧縮設定
            'compression_enabled': safe_get(self.parent.compression_enabled, "off"),
            'compression_format': safe_get(self.parent.compression_format, "ZIP"),
            'compression_delete_original': safe_get(self.parent.compression_delete_original, False),
            
            # エラー処理・再開設定
            'error_handling_enabled': safe_get(self.parent.error_handling_enabled, True),
            'error_handling_mode': safe_get(self.parent.error_handling_mode, "auto_resume"),
            'auto_resume_delay': safe_get(self.parent.auto_resume_delay, "5"),
            'retry_delay_increment': safe_get(self.parent.retry_delay_increment, "10"),
            'max_retry_delay': safe_get(self.parent.max_retry_delay, "60"),
            'max_retry_count': safe_get(self.parent.max_retry_count, "3"),
            'retry_limit_action': safe_get(self.parent.retry_limit_action, 
                                          self.parent.DEFAULT_VALUES['retry_limit_action']),
            
            # ページ・ファイル命名設定
            'first_page_use_title': safe_get(self.parent.first_page_use_title, False),
            'first_page_naming_enabled': safe_get(self.parent.first_page_naming_enabled, False),
            'first_page_naming_format': safe_get(self.parent.first_page_naming_format, "title"),
            'skip_count': safe_get(self.parent.skip_count, "10"),
            'skip_after_count_enabled': safe_get(self.parent.skip_after_count_enabled, False),
            
            # マルチスレッド設定
            'multithread_enabled': safe_get(self.parent.multithread_enabled, "off"),
            'multithread_count': safe_get(self.parent.multithread_count, 3),
            'preserve_animation': safe_get(self.parent.preserve_animation, True),
            
            # 高度なオプション
            'advanced_options_enabled': safe_get(self.parent.advanced_options_enabled, False),
            'user_agent_spoofing_enabled': safe_get(self.parent.user_agent_spoofing_enabled, False),
            'httpx_enabled': safe_get(self.parent.httpx_enabled, False),
            
            # Selenium設定
            'selenium_enabled': safe_get(self.parent.selenium_enabled, False),
            'selenium_session_retry_enabled': safe_get(self.parent.selenium_session_retry_enabled, False),
            'selenium_persistent_enabled': safe_get(self.parent.selenium_persistent_enabled, False),
            'selenium_page_retry_enabled': safe_get(self.parent.selenium_page_retry_enabled, False),
            'selenium_mode': self.parent.selenium_mode.get(),
            
            # ダウンロード範囲設定
            'download_range_enabled': safe_get(self.parent.download_range_enabled, False),
            'download_range_mode': safe_get(self.parent.download_range_mode, "1行目のURLのみ"),
            'download_range_start': safe_get(self.parent.download_range_start, ""),
            'download_range_end': safe_get(self.parent.download_range_end, ""),
            
            # 画質設定
            'jpg_quality': safe_get(self.parent.jpg_quality, 85)
        }
        
        return settings
    
    def _apply_settings(self, settings):
        """設定を適用"""
        # 安全な値設定のヘルパー関数
        def safe_set(var, value, default=None):
            try:
                if hasattr(var, 'set'):
                    var.set(value)
            except Exception:
                if hasattr(var, 'set') and default is not None:
                    try:
                        var.set(default)
                    except Exception:
                        pass
        
        # ウィンドウ設定
        if 'window_geometry' in settings and settings['window_geometry']:
            try:
                self.parent.root.geometry(settings['window_geometry'])
            except Exception:
                pass
        
        # 基本設定
        safe_set(self.parent.folder_var, settings.get('folder_path', ''))
        safe_set(self.parent.wait_time, settings.get('wait_time', '1'))
        safe_set(self.parent.sleep_value, settings.get('sleep_value', '3'))
        safe_set(self.parent.save_format, settings.get('save_format', 'Original'))
        safe_set(self.parent.save_name, settings.get('save_name', 'Original'))
        safe_set(self.parent.custom_name, settings.get('custom_name', '{artist}_{title}_{page}'))
        
        # リサイズ設定
        safe_set(self.parent.resize_mode, settings.get('resize_mode', '縦幅上限'))
        safe_set(self.parent.resize_enabled, settings.get('resize_enabled', 'off'))
        
        # resize_valuesの特別な処理
        resize_vals = settings.get('resize_values', {})
        for key in self.parent.resize_values:
            default_value = self.parent.DEFAULT_VALUES['resize_values'].get(key, "")
            safe_set(self.parent.resize_values[key], resize_vals.get(key, default_value))
        
        safe_set(self.parent.interpolation_mode, settings.get('interpolation_mode', '三次補完（画質優先）'))
        safe_set(self.parent.sharpness_value, settings.get('sharpness_value', '1.5'))
        safe_set(self.parent.resize_filename_enabled, settings.get('resize_filename_enabled', False))
        safe_set(self.parent.resized_prefix, settings.get('resized_prefix', ""))
        safe_set(self.parent.resized_suffix, settings.get('resized_suffix', "_resized"))
        safe_set(self.parent.keep_original, settings.get('keep_original', True))
        safe_set(self.parent.resize_save_location, settings.get('resize_save_location', "child"))
        safe_set(self.parent.resized_subdir_name, settings.get('resized_subdir_name', "resized"))
        
        # フォルダ・ファイル管理
        safe_set(self.parent.duplicate_folder_mode, 
                self.parent._convert_duplicate_mode_to_japanese(settings.get('duplicate_folder_mode', "rename")))
        safe_set(self.parent.rename_incomplete_folder, settings.get('rename_incomplete_folder', False))
        safe_set(self.parent.incomplete_folder_prefix, settings.get('incomplete_folder_prefix', "[INCOMPLETE]_"))
        safe_set(self.parent.folder_name_mode, settings.get('folder_name_mode', "h1_priority"))
        safe_set(self.parent.custom_folder_name, settings.get('custom_folder_name', "{artist}_{title}"))
        # E-Hentai用：同名ファイル処理はリネーム固定
        safe_set(self.parent.duplicate_file_mode, 'rename')
        
        # 圧縮設定
        safe_set(self.parent.compression_enabled, settings.get('compression_enabled', "off"))
        safe_set(self.parent.compression_format, settings.get('compression_format', "ZIP"))
        safe_set(self.parent.compression_delete_original, settings.get('compression_delete_original', False))
        
        # エラー処理・再開設定
        safe_set(self.parent.error_handling_enabled, settings.get('error_handling_enabled', True))
        error_mode = settings.get('error_handling_mode', "auto_resume")
        safe_set(self.parent.error_handling_mode, error_mode)
        safe_set(self.parent.auto_resume_delay, settings.get('auto_resume_delay', "5"))
        safe_set(self.parent.retry_delay_increment, settings.get('retry_delay_increment', "10"))
        safe_set(self.parent.max_retry_delay, settings.get('max_retry_delay', "60"))
        safe_set(self.parent.max_retry_count, settings.get('max_retry_count', "3"))
        safe_set(self.parent.retry_limit_action, 
                settings.get('retry_limit_action', self.parent.DEFAULT_VALUES['retry_limit_action']))
        
        # ページ・ファイル命名設定
        safe_set(self.parent.first_page_use_title, settings.get('first_page_use_title', False))
        safe_set(self.parent.first_page_naming_enabled, settings.get('first_page_naming_enabled', False))
        safe_set(self.parent.first_page_naming_format, settings.get('first_page_naming_format', "title"))
        safe_set(self.parent.skip_count, settings.get('skip_count', "10"))
        safe_set(self.parent.skip_after_count_enabled, settings.get('skip_after_count_enabled', False))
        
        # マルチスレッド設定
        safe_set(self.parent.multithread_enabled, settings.get('multithread_enabled', "off"))
        safe_set(self.parent.multithread_count, settings.get('multithread_count', 3))
        safe_set(self.parent.preserve_animation, settings.get('preserve_animation', True))
        
        # 高度なオプション
        safe_set(self.parent.advanced_options_enabled, settings.get('advanced_options_enabled', False))
        safe_set(self.parent.user_agent_spoofing_enabled, settings.get('user_agent_spoofing_enabled', False))
        safe_set(self.parent.httpx_enabled, settings.get('httpx_enabled', False))
        
        # Selenium設定
        safe_set(self.parent.selenium_enabled, settings.get('selenium_enabled', False))
        safe_set(self.parent.selenium_session_retry_enabled, settings.get('selenium_session_retry_enabled', False))
        safe_set(self.parent.selenium_persistent_enabled, settings.get('selenium_persistent_enabled', False))
        safe_set(self.parent.selenium_page_retry_enabled, settings.get('selenium_page_retry_enabled', False))
        self.parent.selenium_mode.set(settings.get('selenium_mode', 'session'))
        
        # ダウンロード範囲設定
        safe_set(self.parent.download_range_enabled, settings.get('download_range_enabled', False))
        safe_set(self.parent.download_range_mode, settings.get('download_range_mode', "1行目のURLのみ"))
        safe_set(self.parent.download_range_start, settings.get('download_range_start', ""))
        safe_set(self.parent.download_range_end, settings.get('download_range_end', ""))
        
        # 画質設定
        safe_set(self.parent.jpg_quality, settings.get('jpg_quality', 85))
