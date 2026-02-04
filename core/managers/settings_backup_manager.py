# -*- coding: utf-8 -*-
"""
設定バックアップ管理クラス - 設定の一元管理とバックアップ
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List
from core.interfaces import ILogger

class SettingsBackupManager:
    """設定のバックアップと同期を管理するクラス"""
    
    def __init__(self, logger: ILogger):
        self.logger = logger
        self.settings_file = "ehd_settings.json"
        self.backup_file = "ehd_settings_backup.json"
        self.temp_file = "ehd_settings_temp.json"
        
        # 設定ファイルの保存場所
        self.settings_directory = os.getcwd()  # デフォルトはアプリケーションディレクトリ
        
        # 統一（新）構造のデフォルト値
        self.default_settings = {
            'main_app': {
                'window_geometry': "1630x1380+100+100",
                'window_state': "normal",
                'sash_pos_v': 400,
                'sash_pos_h': 800,
                'folder_path': os.path.join(os.path.expanduser("~"), "Documents"),
                'wait_time': "0.5",
                'sleep_value': "0.5",
                'save_format': "Original",
                'save_name': "Original",
                'custom_name': "{artist}_{title}_{page}",
                'resize_enabled': "off",
                'resize_mode': "縦幅上限",
                'resize_values': {
                    'height': "1024",
                    'width': "1024",
                    'short': "1024",
                    'long': "1024",
                    'percentage': "80",
                    'unified': "1600"
                },
                'interpolation_mode': "三次補完（画質優先）",
                'sharpness_value': "1.5",
                'keep_original': True,
                'resize_filename_enabled': False,
                'resized_subdir_name': "resized",
                'resized_prefix': "",
                'resized_suffix': "_resized",
                'resize_save_location': "child",
                'duplicate_folder_mode': "rename",
                'duplicate_file_mode': "overwrite",
                'rename_incomplete_folder': False,
                'incomplete_folder_prefix': "[INCOMPLETE]_",
                'folder_name_mode': "h1_priority",
                'custom_folder_name': "{artist}_{title}",
                'compression_enabled': "off",
                'compression_format': "ZIP",
                'compression_delete_original': False,
                'error_handling_enabled': True,
                'error_handling_mode': "auto_resume",
                'auto_resume_delay': "5",
                'retry_delay_increment': "10",
                'max_retry_delay': "60",
                'max_retry_count': "3",
                'retry_limit_action': "SeleniumをONにしてリトライ",
                'selenium_scope': "1",
                'selenium_failure_action': "manual_resume",
                'first_page_use_title': False,
                'first_page_naming_enabled': False,
                'first_page_naming_format': "title",
                'skip_count': "10",
                'skip_after_count_enabled': False,
                'jpg_quality': 85,
                'preserve_animation': True,
                'string_conversion_enabled': False,
                'string_conversion_rules': [],
                'multithread_enabled': "off",
                'multithread_count': 3,
                'advanced_options_enabled': True,
                'user_agent_spoofing_enabled': False,
                'httpx_enabled': False,
                'selenium_enabled': False,
                'selenium_use_for_page_info': False,
                'selenium_session_retry_enabled': False,
                'selenium_persistent_enabled': False,
                'selenium_page_retry_enabled': False,
                'selenium_mode': 'session',
                'download_range_enabled': False,
                'download_range_mode': '1行目のURLのみ',
                'download_range_start': '',
                'download_range_end': '',
                'thumbnail_display_enabled': "off",
                'progress_separate_window_enabled': False,
                'url_list_content': "",
                'current_url_index': 0,
                'url_status': {},
                'log_content': "",
                'total_elapsed_seconds': 0,
                'last_saved': None,
                'version': "3.12",
                'backup_count': 0
            },
            'parser': {
                'window_geometry': "800x600+200+200",
                'window_state': "normal",
                'target_count': 25,
                'page_wait_time': 2.0,
                'auto_thumb': False,
                'thumb_wait_time': 0.3,
                'cache_size': 500,
                'disable_thumb': False,
                'parse_mode': "DBに追加"
            },
            'torrent_manager': {
                'window_geometry': "670x1100+100+100",
                'window_state': "normal",
                'save_directory': os.path.join(os.path.expanduser("~"), "Downloads", "Torrents"),
                'page_wait_time': 1.0,
                'error_handling': "pause",
                'torrent_selection': "bottom_order",
                'duplicate_file_mode': "rename",
                'filtering_enabled': False,
                'filtering_size': 600,
                'filtering_action': "max_only"
            },
            'download_manager': {
                'window_geometry': "800x600+300+300",
                'window_state': "normal",
                'auto_scroll_enabled': True
            }
        }
    
    def set_settings_directory(self, directory: str):
        """設定ファイルの保存ディレクトリを設定"""
        try:
            self.settings_directory = directory
            # ファイルパスを更新
            self.settings_file = os.path.join(directory, "ehd_settings.json")
            self.backup_file = os.path.join(directory, "ehd_settings_backup.json")
            self.temp_file = os.path.join(directory, "ehd_settings_temp.json")
            self.logger.log(f"設定ファイル保存ディレクトリを設定: {directory}", "info")
        except Exception as e:
            self.logger.log(f"設定ディレクトリ設定エラー: {e}", "error")
    
    def load_settings(self) -> Dict[str, Any]:
        """設定の読み込み（常に新構造で返す・旧構造は自動移行）"""
        try:
            loaded: Dict[str, Any]
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 重複ログを避けるため、最初の読み込み時のみログ出力（load_settings_and_stateで出力される）
                # self.logger.log(f"設定を読み込みました: {self.settings_file}", "info")
            elif os.path.exists(self.backup_file):
                with open(self.backup_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self.logger.log("バックアップ設定を読み込みました", "warning")
            else:
                # ⭐修正: 警告はload_settings_and_stateで出力されるため、ここでは出力しない⭐
                # self.logger.log("設定ファイルが見つかりません。デフォルト設定を使用します。", "warning")
                loaded = {}

            unified = self._ensure_unified_structure(loaded)
            return unified

        except Exception as e:
            self.logger.log(f"設定読み込みエラー: {e}", "error")
            return self._ensure_unified_structure({})
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """設定の保存（新構造で強制保存）"""
        try:
            self.logger.log(f"設定ファイルを保存中: {self.settings_file}", "debug")
            unified = self._ensure_unified_structure(settings)

            # メタデータの更新は main_app 配下に持つ
            unified['main_app']['last_saved'] = datetime.now().isoformat()
            unified['main_app']['version'] = "3.12"

            # ⭐修正: 自動バックアップを無効化（ehd_settings.jsonのみ使用）⭐
            # if os.path.exists(self.settings_file):
            #     self._create_backup()

            with open(self.temp_file, 'w', encoding='utf-8') as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)

            shutil.move(self.temp_file, self.settings_file)
            self.logger.log(f"設定を保存しました: {self.settings_file}", "info")
            return True

        except Exception as e:
            self.logger.log(f"設定保存エラー: {e}", "error")
            if os.path.exists(self.temp_file):
                os.remove(self.temp_file)
            return False
    
    def create_backup(self) -> bool:
        """設定のバックアップ作成"""
        try:
            if os.path.exists(self.settings_file):
                # バックアップファイルの作成
                shutil.copy2(self.settings_file, self.backup_file)
                
                # バックアップカウントの更新
                settings = self.load_settings()
                settings['backup_count'] = settings.get('backup_count', 0) + 1
                self.save_settings(settings)
                
                self.logger.log("設定のバックアップを作成しました", "info")
                return True
            else:
                self.logger.log("バックアップする設定ファイルがありません", "warning")
                return False
                
        except Exception as e:
            self.logger.log(f"バックアップ作成エラー: {e}", "error")
            return False
    
    def restore_from_backup(self) -> bool:
        """バックアップからの復元"""
        try:
            if os.path.exists(self.backup_file):
                # バックアップファイルをメインファイルにコピー
                shutil.copy2(self.backup_file, self.settings_file)
                self.logger.log("バックアップから設定を復元しました", "info")
                return True
            else:
                self.logger.log("復元するバックアップファイルがありません", "warning")
                return False
                
        except Exception as e:
            self.logger.log(f"バックアップ復元エラー: {e}", "error")
            return False
    
    def reset_to_defaults(self) -> bool:
        """デフォルト設定にリセット"""
        try:
            # デフォルト設定を保存
            default_settings = self.default_settings.copy()
            default_settings['last_saved'] = datetime.now().isoformat()
            default_settings['version'] = "3.12"
            default_settings['backup_count'] = 0
            
            return self.save_settings(default_settings)
            
        except Exception as e:
            self.logger.log(f"デフォルト設定リセットエラー: {e}", "error")
            return False
    
    def export_settings(self, file_path: str) -> bool:
        """設定のエクスポート"""
        try:
            settings = self.load_settings()
            
            # エクスポート用の設定を作成
            export_settings = settings.copy()
            export_settings['exported_at'] = datetime.now().isoformat()
            export_settings['export_version'] = "3.12"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_settings, f, ensure_ascii=False, indent=2)
            
            self.logger.log(f"設定をエクスポートしました: {file_path}", "info")
            return True
            
        except Exception as e:
            self.logger.log(f"設定エクスポートエラー: {e}", "error")
            return False
    
    def import_settings(self, file_path: str) -> bool:
        """設定のインポート"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_settings = json.load(f)
            
            # 設定の検証
            validated_settings = self._validate_settings(imported_settings)
            
            # インポート日時の追加
            validated_settings['imported_at'] = datetime.now().isoformat()
            
            # 設定の保存
            return self.save_settings(validated_settings)
            
        except Exception as e:
            self.logger.log(f"設定インポートエラー: {e}", "error")
            return False
    
    def get_settings_info(self) -> Dict[str, Any]:
        """設定情報の取得"""
        try:
            settings = self.load_settings()
            return {
                'file_path': self.settings_file,
                'backup_path': self.backup_file,
                'last_saved': settings.get('last_saved'),
                'version': settings.get('version'),
                'backup_count': settings.get('backup_count', 0),
                'file_exists': os.path.exists(self.settings_file),
                'backup_exists': os.path.exists(self.backup_file),
                'file_size': os.path.getsize(self.settings_file) if os.path.exists(self.settings_file) else 0
            }
        except Exception as e:
            self.logger.log(f"設定情報取得エラー: {e}", "error")
            return {}
    
    def _merge_with_defaults(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """（互換）新構造に正規化しつつデフォルトとマージ"""
        unified = self._ensure_unified_structure(settings)
        return unified

    def _ensure_unified_structure(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """常に統一構造 {main_app, parser, torrent_manager, download_manager} で返す。
        旧フラット構造は main_app に移行する。"""
        try:
            # 旧構造（flat）→ 新構造に移行
            if not isinstance(settings, dict) or 'main_app' not in settings:
                migrated = {
                    'main_app': settings if isinstance(settings, dict) else {},
                    'parser': {},
                    'torrent_manager': {},
                    'download_manager': {}
                }
            else:
                migrated = settings

            # main_app にデフォルトを適用（他セクションは現在は任意項目のためそのまま）
            main_app = {}
            main_defaults = self.default_settings.copy()
            if isinstance(migrated.get('main_app'), dict):
                main_app = {**main_defaults, **migrated['main_app']}
            else:
                main_app = main_defaults

            return {
                'main_app': main_app,
                'parser': migrated.get('parser', {}) if isinstance(migrated.get('parser'), dict) else {},
                'torrent_manager': migrated.get('torrent_manager', {}) if isinstance(migrated.get('torrent_manager'), dict) else {},
                'download_manager': migrated.get('download_manager', {}) if isinstance(migrated.get('download_manager'), dict) else {}
            }
        except Exception as e:
            self.logger.log(f"設定正規化エラー: {e}", "error")
            # 失敗時は新構造のデフォルトを返す
            return {
                'main_app': self.default_settings.copy(),
                'parser': {},
                'torrent_manager': {},
                'download_manager': {}
            }
    
    def _validate_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """（互換）新構造に正規化する。詳細型検証は省略。"""
        return self._ensure_unified_structure(settings)
    
    def _create_backup(self):
        """内部バックアップ作成"""
        try:
            if os.path.exists(self.settings_file):
                shutil.copy2(self.settings_file, self.backup_file)
        except Exception as e:
            self.logger.log(f"内部バックアップ作成エラー: {e}", "error")
