# -*- coding: utf-8 -*-
"""
統合エラーレジューム管理クラス - エラー処理とレジューム機能を統合
"""

import json
import os
import time
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from core.interfaces import IStateManager, ILogger, IGUIOperations, IFileOperations

class ErrorSeverity(Enum):
    """エラーの深刻度"""
    LOW = "low"           # 軽微なエラー（リトライ可能）
    MEDIUM = "medium"     # 中程度のエラー（スキップ可能）
    HIGH = "high"         # 深刻なエラー（URLスキップ）
    CRITICAL = "critical" # 致命的エラー（シーケンス中止）

class ErrorCategory(Enum):
    """エラーのカテゴリ"""
    NETWORK = "network"       # ネットワーク関連
    FILE = "file"            # ファイル関連
    PERMISSION = "permission" # 権限関連
    TIMEOUT = "timeout"      # タイムアウト関連
    PARSING = "parsing"      # パース関連
    VALIDATION = "validation" # 検証関連
    UNKNOWN = "unknown"      # 不明

class ResumePoint:
    """レジュームポイントのデータクラス"""
    
    def __init__(self, url: str, stage: str, data: Dict[str, Any]):
        self.url = url
        self.stage = stage
        self.data = data
        self.timestamp = datetime.now()
        self.success = False
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'url': self.url,
            'stage': self.stage,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'success': self.success
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResumePoint':
        """辞書から復元"""
        resume_point = cls(
            data['url'],
            data['stage'],
            data['data']
        )
        resume_point.timestamp = datetime.fromisoformat(data['timestamp'])
        resume_point.success = data.get('success', False)
        return resume_point

class UnifiedErrorResumeManager:
    """統合エラーレジューム管理クラス"""
    
    def __init__(self, 
                 state_manager: IStateManager,
                 logger: ILogger,
                 gui_operations: IGUIOperations,
                 file_operations: IFileOperations):
        self.state_manager = state_manager
        self.logger = logger
        self.gui_operations = gui_operations
        self.file_operations = file_operations
        
        # ファイルパス
        self.resume_file = "unified_resume_data.json"
        self.error_log_file = "unified_error_log.json"
        
        # レジュームポイントの管理
        self.resume_points: Dict[str, ResumePoint] = {}
        self.current_resume_point: Optional[ResumePoint] = None
        
        # エラー統計
        self.error_stats = {
            'total_errors': 0,
            'error_counts_by_category': {},
            'error_counts_by_severity': {},
            'url_error_counts': {},
            'recovery_attempts': 0,
            'successful_recoveries': 0,
            'resume_attempts': 0,
            'successful_resumes': 0
        }
        
        # エラー処理設定
        self.error_config = {
            'max_retry_attempts': 3,
            'retry_delay_base': 5.0,
            'retry_delay_max': 60.0,
            'retry_delay_multiplier': 2.0,
            'enable_auto_recovery': True,
            'enable_error_escalation': True,
            'max_resume_age_hours': 24,
            'max_resume_points': 100,
            'auto_cleanup': True
        }
        
        # ロック
        self.resume_lock = threading.Lock()
        self.error_lock = threading.Lock()
        
        # ⭐追加: 非同期更新用のキューとスレッド⭐
        self._resume_update_queue = queue.Queue(maxsize=500)  # 最大500件までキューに保持（100→500に増加）
        self._resume_update_thread = None
        self._resume_update_stop = threading.Event()
        self._start_resume_update_thread()
        
        # ⭐追加: エラー統計更新用の非同期キューとスレッド⭐
        self._error_update_queue = queue.Queue(maxsize=100)  # 最大100件までキューに保持
        self._error_update_thread = None
        self._error_update_stop = threading.Event()
        self._start_error_update_thread()
        
        # エラー処理戦略
        self.error_strategies = {
            ErrorCategory.NETWORK: self._handle_network_error,
            ErrorCategory.FILE: self._handle_file_error,
            ErrorCategory.PERMISSION: self._handle_permission_error,
            ErrorCategory.TIMEOUT: self._handle_timeout_error,
            ErrorCategory.PARSING: self._handle_parsing_error,
            ErrorCategory.VALIDATION: self._handle_validation_error,
            ErrorCategory.UNKNOWN: self._handle_unknown_error
        }
        
        # データの読み込み
        self._load_resume_data()
        self._load_error_log()
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> str:
        """エラーの処理（メインエントリーポイント）"""
        try:
            # ⭐修正: エラー統計の更新を着火式（非同期）に変更⭐
            # エラー発生をイベントとして発火（ブロッキングしない）
            self._fire_error_event(error, context)
            
            # エラーの分析（同期的に実行、処理に必要）
            error_analysis = self._analyze_error(error, context)
            
            # エラーログの出力（同期的に実行、即座に表示）
            self._log_error(error, error_analysis, context)
            
            # エラー処理戦略の実行（同期的に実行、処理に必要）
            result = self._execute_error_strategy(error, error_analysis, context)
            
            # ⭐修正: 結果の記録も着火式（非同期）に変更⭐
            self._fire_error_result_event(result, error_analysis)
            
            return result
                
        except Exception as e:
            self.logger.log(f"エラーハンドリング中にエラーが発生: {e}", "error")
            return "abort"
    
    def _start_resume_update_thread(self):
        """レジュームポイント更新用の非同期スレッドを開始"""
        if self._resume_update_thread is None or not self._resume_update_thread.is_alive():
            self._resume_update_stop.clear()
            self._resume_update_thread = threading.Thread(
                target=self._resume_update_worker,
                daemon=True,
                name="ResumeUpdateThread"
            )
            self._resume_update_thread.start()
    
    def _start_error_update_thread(self):
        """エラー統計更新用の非同期スレッドを開始"""
        if self._error_update_thread is None or not self._error_update_thread.is_alive():
            self._error_update_stop.clear()
            self._error_update_thread = threading.Thread(
                target=self._error_update_worker,
                daemon=True,
                name="ErrorUpdateThread"
            )
            self._error_update_thread.start()
    
    def _resume_update_worker(self):
        """レジュームポイント更新ワーカースレッド"""
        while not self._resume_update_stop.is_set():
            try:
                # キューから更新リクエストを取得（タイムアウト付き）
                try:
                    url, stage, data = self._resume_update_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # 同期版のupdate_resume_pointを呼び出し
                self._update_resume_point_sync(url, stage, data)
                
                # タスク完了をマーク
                self._resume_update_queue.task_done()
                
            except Exception as e:
                self.logger.log(f"レジュームポイント非同期更新エラー: {e}", "error")
    
    def _error_update_worker(self):
        """エラー統計更新ワーカースレッド"""
        while not self._error_update_stop.is_set():
            try:
                # キューから更新リクエストを取得（タイムアウト付き）
                try:
                    request_type, *args = self._error_update_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # リクエストタイプに応じて処理
                if request_type == 'error_stats':
                    error, context = args
                    with self.error_lock:
                        self._update_error_stats(error, context)
                elif request_type == 'error_result':
                    result, analysis = args
                    with self.error_lock:
                        self._record_error_result(result, analysis)
                
                # タスク完了をマーク
                self._error_update_queue.task_done()
                
            except Exception as e:
                self.logger.log(f"エラー統計非同期更新エラー: {e}", "error")
    
    def _fire_error_event(self, error: Exception, context: Dict[str, Any] = None):
        """エラーイベントを発火（非同期で統計を更新）"""
        try:
            # 非同期キューに追加（ブロッキングしない）
            try:
                self._error_update_queue.put_nowait(('error_stats', error, context))
            except queue.Full:
                self.logger.log("エラー統計更新キューが満杯です", "warning")
        except Exception as e:
            self.logger.log(f"エラーイベント発火エラー: {e}", "error")
    
    def _fire_error_result_event(self, result: str, analysis: Dict[str, Any]):
        """エラー結果イベントを発火（非同期で結果を記録）"""
        try:
            # 非同期キューに追加（ブロッキングしない）
            try:
                self._error_update_queue.put_nowait(('error_result', result, analysis))
            except queue.Full:
                self.logger.log("エラー結果記録キューが満杯です", "warning")
        except Exception as e:
            self.logger.log(f"エラー結果イベント発火エラー: {e}", "error")
    
    def _update_resume_point_sync(self, url: str, stage: str, data: Dict[str, Any]) -> bool:
        """レジュームポイントの同期更新（内部実装）"""
        try:
            with self.resume_lock:
                if url in self.resume_points:
                    self.resume_points[url].stage = stage
                    self.resume_points[url].data.update(data)
                    self.resume_points[url].timestamp = datetime.now()
                    
                    # ファイルに保存
                    self._save_resume_data()
                    
                    self.logger.log(f"レジュームポイント更新: {url} ({stage})", "info")
                    return True
                else:
                    # 新しいレジュームポイントを作成
                    return self._create_resume_point_sync(url, stage, data)
                    
        except Exception as e:
            self.logger.log(f"レジュームポイント更新エラー: {e}", "error")
            return False
    
    def _create_resume_point_sync(self, url: str, stage: str, data: Dict[str, Any]) -> bool:
        """レジュームポイントの同期作成（内部実装）"""
        try:
            with self.resume_lock:
                resume_point = ResumePoint(url, stage, data)
                self.resume_points[url] = resume_point
                
                # ファイルに保存
                self._save_resume_data()
                
                self.logger.log(f"レジュームポイント作成: {url} ({stage})", "info")
                return True
                
        except Exception as e:
            self.logger.log(f"レジュームポイント作成エラー: {e}", "error")
            return False
    
    def create_resume_point(self, url: str, stage: str, data: Dict[str, Any]) -> bool:
        """レジュームポイントの作成（非同期版）"""
        try:
            # ⭐修正: 非同期キューに追加（ブロッキングしない）⭐
            try:
                self._resume_update_queue.put_nowait((url, stage, data))
                return True  # キューへの追加が成功したことを返す
            except queue.Full:
                # キューが満杯の場合はログを出力してスキップ
                self.logger.log(f"レジュームポイント作成キューが満杯です: {url}", "warning")
                return False
        except Exception as e:
            self.logger.log(f"レジュームポイント作成エラー: {e}", "error")
            return False
    
    def update_resume_point(self, url: str, stage: str, data: Dict[str, Any]) -> bool:
        """レジュームポイントの更新（非同期版）"""
        try:
            # ⭐修正: 同じURLの古い更新をキューから削除して、最新の更新のみを保持⭐
            # レジュームポイントは最新のものだけ記録するので、同じURLの古い更新は不要
            try:
                # キュー内の同じURLの古い更新を削除
                temp_items = []
                while not self._resume_update_queue.empty():
                    try:
                        item = self._resume_update_queue.get_nowait()
                        item_url, item_stage, item_data = item
                        # 同じURLの更新はスキップ（最新の更新のみ保持）
                        if item_url != url:
                            temp_items.append(item)
                    except queue.Empty:
                        break
                
                # 古い更新をキューに戻す
                for item in temp_items:
                    try:
                        self._resume_update_queue.put_nowait(item)
                    except queue.Full:
                        # キューが満杯の場合は古い更新をスキップ
                        pass
                
                # 最新の更新をキューに追加
                self._resume_update_queue.put_nowait((url, stage, data))
                return True  # キューへの追加が成功したことを返す
            except queue.Full:
                # キューが満杯の場合は、同じURLの古い更新を削除して再試行
                # これでも満杯の場合は、最新の更新を優先して古い更新を削除
                temp_items = []
                same_url_found = False
                while not self._resume_update_queue.empty():
                    try:
                        item = self._resume_update_queue.get_nowait()
                        item_url, item_stage, item_data = item
                        if item_url == url:
                            # 同じURLの古い更新はスキップ
                            same_url_found = True
                            continue
                        temp_items.append(item)
                    except queue.Empty:
                        break
                
                # 古い更新をキューに戻す
                for item in temp_items:
                    try:
                        self._resume_update_queue.put_nowait(item)
                    except queue.Full:
                        # キューが満杯の場合は古い更新をスキップ
                        pass
                
                # 最新の更新をキューに追加
                try:
                    self._resume_update_queue.put_nowait((url, stage, data))
                    return True
                except queue.Full:
                    # それでも満杯の場合は、古い更新を1つ削除して再試行
                    try:
                        self._resume_update_queue.get_nowait()
                        self._resume_update_queue.put_nowait((url, stage, data))
                        return True
                    except (queue.Empty, queue.Full):
                        # それでも満杯の場合はログを出力してスキップ
                        self.logger.log(f"レジュームポイント更新キューが満杯です（最新の更新を優先）: {url}", "warning")
                        return False
        except Exception as e:
            self.logger.log(f"レジュームポイント更新エラー: {e}", "error")
            return False
    
    def mark_resume_point_success(self, url: str) -> bool:
        """レジュームポイントを成功としてマーク"""
        try:
            with self.resume_lock:
                if url in self.resume_points:
                    self.resume_points[url].success = True
                    self.resume_points[url].timestamp = datetime.now()
                    
                    # ファイルに保存
                    self._save_resume_data()
                    
                    self.logger.log(f"レジュームポイント成功マーク: {url}", "info")
                    return True
                return False
                
        except Exception as e:
            self.logger.log(f"レジュームポイント成功マークエラー: {e}", "error")
            return False
    
    def get_resume_point(self, url: str) -> Optional[ResumePoint]:
        """レジュームポイントの取得"""
        try:
            with self.resume_lock:
                return self.resume_points.get(url)
        except Exception as e:
            self.logger.log(f"レジュームポイント取得エラー: {e}", "error")
            return None
    
    def is_resume_available(self, url: str) -> bool:
        """レジューム可能かどうかの確認"""
        try:
            resume_point = self.get_resume_point(url)
            if not resume_point:
                return False
            
            # レジュームポイントの有効性をチェック
            return self._is_resume_point_valid(resume_point)
            
        except Exception as e:
            self.logger.log(f"レジューム可能性確認エラー: {e}", "error")
            return False
    
    def resume_from_point(self, url: str) -> bool:
        """レジュームポイントから再開"""
        try:
            resume_point = self.get_resume_point(url)
            if not resume_point:
                self.logger.log(f"レジュームポイントが見つかりません: {url}", "error")
                return False
            
            if not self._is_resume_point_valid(resume_point):
                self.logger.log(f"無効なレジュームポイント: {url}", "error")
                return False
            
            # 現在のレジュームポイントを設定
            self.current_resume_point = resume_point
            
            # エラー統計の更新
            with self.error_lock:
                self.error_stats['resume_attempts'] += 1
            
            # レジューム処理の実行
            self.logger.log(f"レジューム開始: {url} ({resume_point.stage})", "info")
            
            # 具体的なレジューム処理は各ダウンローダーで実装
            # ここでは基本的な状態復元のみ
            
            return True
            
        except Exception as e:
            self.logger.log(f"レジューム実行エラー: {e}", "error")
            return False
    
    def cleanup_old_resume_points(self) -> int:
        """古いレジュームポイントのクリーンアップ"""
        try:
            with self.resume_lock:
                current_time = datetime.now()
                max_age = timedelta(hours=self.error_config['max_resume_age_hours'])
                cleaned_count = 0
                
                # 古いレジュームポイントを削除
                urls_to_remove = []
                for url, resume_point in self.resume_points.items():
                    if current_time - resume_point.timestamp > max_age:
                        urls_to_remove.append(url)
                        cleaned_count += 1
                
                for url in urls_to_remove:
                    del self.resume_points[url]
                
                # 最大数を超える場合は古いものから削除
                if len(self.resume_points) > self.error_config['max_resume_points']:
                    sorted_points = sorted(
                        self.resume_points.items(),
                        key=lambda x: x[1].timestamp
                    )
                    
                    excess_count = len(self.resume_points) - self.error_config['max_resume_points']
                    for i in range(excess_count):
                        url, _ = sorted_points[i]
                        del self.resume_points[url]
                        cleaned_count += 1
                
                # ファイルに保存
                if cleaned_count > 0:
                    self._save_resume_data()
                    self.logger.log(f"古いレジュームポイントをクリーンアップ: {cleaned_count}件", "info")
                
                return cleaned_count
                
        except Exception as e:
            self.logger.log(f"レジュームポイントクリーンアップエラー: {e}", "error")
            return 0
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """エラー統計の取得"""
        try:
            with self.error_lock:
                # 統計項目を統一
                return {
                    'total_errors': self.error_stats.get('total_errors', 0),
                    'retry_attempts': self.error_stats.get('recovery_attempts', 0),
                    'successful_retries': self.error_stats.get('successful_recoveries', 0),
                    'recovery_attempts': self.error_stats.get('recovery_attempts', 0),
                    'successful_recoveries': self.error_stats.get('successful_recoveries', 0),
                    'resume_attempts': self.error_stats.get('resume_attempts', 0),
                    'successful_resumes': self.error_stats.get('successful_resumes', 0),
                    'error_counts_by_category': self.error_stats.get('error_counts_by_category', {}),
                    'error_counts_by_severity': self.error_stats.get('error_counts_by_severity', {}),
                    'url_error_counts': self.error_stats.get('url_error_counts', {})
                }
        except Exception as e:
            self.logger.log(f"エラー統計取得エラー: {e}", "error")
            return {}
    
    def reset_error_statistics(self):
        """エラー統計のリセット"""
        try:
            with self.error_lock:
                self.error_stats = {
                    'total_errors': 0,
                    'error_counts_by_category': {},
                    'error_counts_by_severity': {},
                    'url_error_counts': {},
                    'recovery_attempts': 0,
                    'successful_recoveries': 0,
                    'resume_attempts': 0,
                    'successful_resumes': 0
                }
                self.logger.log("エラー統計をリセットしました", "info")
        except Exception as e:
            self.logger.log(f"エラー統計リセットエラー: {e}", "error")
    
    def _analyze_error(self, error: Exception, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """エラーの分析"""
        try:
            error_type = type(error).__name__
            error_message = str(error)
            
            # エラーのカテゴリを判定
            category = self._classify_error_category(error)
            
            # エラーの深刻度を判定
            severity = self._classify_error_severity(error, context)
            
            # コンテキスト情報の取得
            url = context.get('url', '') if context else ''
            stage = context.get('stage', '') if context else ''
            
            return {
                'error_type': error_type,
                'error_message': error_message,
                'category': category,
                'severity': severity,
                'url': url,
                'stage': stage,
                'timestamp': datetime.now().isoformat(),
                'context': context or {}
            }
            
        except Exception as e:
            self.logger.log(f"エラー分析エラー: {e}", "error")
            return {
                'error_type': 'Unknown',
                'error_message': str(error),
                'category': ErrorCategory.UNKNOWN,
                'severity': ErrorSeverity.HIGH,
                'url': '',
                'stage': '',
                'timestamp': datetime.now().isoformat(),
                'context': context or {}
            }
    
    def _classify_error_category(self, error: Exception) -> ErrorCategory:
        """エラーのカテゴリを分類"""
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        if 'network' in error_message or 'connection' in error_message or 'timeout' in error_message:
            return ErrorCategory.NETWORK
        elif 'file' in error_message or 'permission' in error_message or 'access' in error_message:
            return ErrorCategory.FILE
        elif 'permission' in error_message or 'access denied' in error_message:
            return ErrorCategory.PERMISSION
        elif 'timeout' in error_message or 'timed out' in error_message:
            return ErrorCategory.TIMEOUT
        elif 'parse' in error_message or 'json' in error_message or 'xml' in error_message:
            return ErrorCategory.PARSING
        elif 'validation' in error_message or 'invalid' in error_message:
            return ErrorCategory.VALIDATION
        else:
            return ErrorCategory.UNKNOWN
    
    def _classify_error_severity(self, error: Exception, context: Dict[str, Any] = None) -> ErrorSeverity:
        """エラーの深刻度を分類"""
        error_type = type(error).__name__
        error_message = str(error).lower()
        
        # 致命的エラー
        if 'critical' in error_message or 'fatal' in error_message:
            return ErrorSeverity.CRITICAL
        
        # 深刻なエラー
        if 'connection refused' in error_message or 'not found' in error_message:
            return ErrorSeverity.HIGH
        
        # 中程度のエラー
        if 'timeout' in error_message or 'temporary' in error_message:
            return ErrorSeverity.MEDIUM
        
        # 軽微なエラー
        if 'warning' in error_message or 'minor' in error_message:
            return ErrorSeverity.LOW
        
        # デフォルトは中程度
        return ErrorSeverity.MEDIUM
    
    def _execute_error_strategy(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """エラー処理戦略の実行"""
        try:
            category = analysis['category']
            severity = analysis['severity']
            
            # エラー処理戦略を実行
            if category in self.error_strategies:
                return self.error_strategies[category](error, analysis, context)
            else:
                return self._handle_unknown_error(error, analysis, context)
                
        except Exception as e:
            self.logger.log(f"エラー処理戦略実行エラー: {e}", "error")
            return "abort"
    
    def _handle_network_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """ネットワークエラーの処理"""
        try:
            # リトライ可能なエラーの場合
            if analysis['severity'] in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]:
                self.logger.log(f"ネットワークエラー - リトライを試行: {analysis['error_message']}", "warning")
                return "retry"
            else:
                self.logger.log(f"ネットワークエラー - URLをスキップ: {analysis['error_message']}", "error")
                return "skip"
                
        except Exception as e:
            self.logger.log(f"ネットワークエラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_file_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """ファイルエラーの処理"""
        try:
            # 権限エラーの場合
            if 'permission' in str(error).lower():
                self.logger.log(f"ファイル権限エラー - 手動確認が必要: {analysis['error_message']}", "error")
                return "manual"
            else:
                self.logger.log(f"ファイルエラー - URLをスキップ: {analysis['error_message']}", "error")
                return "skip"
                
        except Exception as e:
            self.logger.log(f"ファイルエラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_permission_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """権限エラーの処理"""
        try:
            self.logger.log(f"権限エラー - 手動確認が必要: {analysis['error_message']}", "error")
            return "manual"
            
        except Exception as e:
            self.logger.log(f"権限エラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_timeout_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """タイムアウトエラーの処理"""
        try:
            # タイムアウトはリトライ可能
            self.logger.log(f"タイムアウトエラー - リトライを試行: {analysis['error_message']}", "warning")
            return "retry"
            
        except Exception as e:
            self.logger.log(f"タイムアウトエラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_parsing_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """パースエラーの処理"""
        try:
            # パースエラーは通常スキップ
            self.logger.log(f"パースエラー - URLをスキップ: {analysis['error_message']}", "error")
            return "skip"
            
        except Exception as e:
            self.logger.log(f"パースエラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_validation_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """検証エラーの処理"""
        try:
            # 検証エラーは通常スキップ
            self.logger.log(f"検証エラー - URLをスキップ: {analysis['error_message']}", "error")
            return "skip"
            
        except Exception as e:
            self.logger.log(f"検証エラー処理エラー: {e}", "error")
            return "abort"
    
    def _handle_unknown_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """不明エラーの処理"""
        try:
            # 不明エラーは深刻度に応じて処理
            if analysis['severity'] == ErrorSeverity.CRITICAL:
                self.logger.log(f"致命的な不明エラー - シーケンスを中止: {analysis['error_message']}", "error")
                return "abort"
            else:
                self.logger.log(f"不明エラー - URLをスキップ: {analysis['error_message']}", "error")
                return "skip"
                
        except Exception as e:
            self.logger.log(f"不明エラー処理エラー: {e}", "error")
            return "abort"
    
    def _update_error_stats(self, error: Exception, context: Dict[str, Any] = None):
        """エラー統計の更新"""
        try:
            self.error_stats['total_errors'] += 1
            
            # エラーカテゴリの統計
            category = self._classify_error_category(error)
            category_name = category.value
            self.error_stats['error_counts_by_category'][category_name] = \
                self.error_stats['error_counts_by_category'].get(category_name, 0) + 1
            
            # エラー深刻度の統計
            severity = self._classify_error_severity(error, context)
            severity_name = severity.value
            self.error_stats['error_counts_by_severity'][severity_name] = \
                self.error_stats['error_counts_by_severity'].get(severity_name, 0) + 1
            
            # URL別エラー統計
            if context and 'url' in context:
                url = context['url']
                self.error_stats['url_error_counts'][url] = \
                    self.error_stats['url_error_counts'].get(url, 0) + 1
                    
        except Exception as e:
            self.logger.log(f"エラー統計更新エラー: {e}", "error")
    
    def _log_error(self, error: Exception, analysis: Dict[str, Any], context: Dict[str, Any] = None):
        """エラーログの出力"""
        try:
            error_message = f"【{analysis['category'].value.upper()}】{analysis['error_message']}"
            if analysis['url']:
                error_message += f" (URL: {analysis['url']})"
            if analysis['stage']:
                error_message += f" (Stage: {analysis['stage']})"
            
            self.logger.log(error_message, "error")
            
        except Exception as e:
            self.logger.log(f"エラーログ出力エラー: {e}", "error")
    
    def _record_error_result(self, result: str, analysis: Dict[str, Any]):
        """エラー処理結果の記録"""
        try:
            if result == "retry":
                self.error_stats['recovery_attempts'] += 1
            elif result in ["continue", "success"]:
                self.error_stats['successful_recoveries'] += 1
            elif result == "resume":
                self.error_stats['resume_attempts'] += 1
                self.error_stats['successful_resumes'] += 1
                
        except Exception as e:
            self.logger.log(f"エラー結果記録エラー: {e}", "error")
    
    def _is_resume_point_valid(self, resume_point: ResumePoint) -> bool:
        """レジュームポイントの有効性をチェック"""
        try:
            # 時間の有効性をチェック
            current_time = datetime.now()
            max_age = timedelta(hours=self.error_config['max_resume_age_hours'])
            
            if current_time - resume_point.timestamp > max_age:
                return False
            
            # データの有効性をチェック
            if not resume_point.data or not isinstance(resume_point.data, dict):
                return False
            
            # 必須フィールドのチェック
            required_fields = ['url', 'stage']
            for field in required_fields:
                if field not in resume_point.data:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.log(f"レジュームポイント有効性チェックエラー: {e}", "error")
            return False
    
    def _save_resume_data(self):
        """レジュームデータの保存"""
        try:
            data = {
                'resume_points': {url: point.to_dict() for url, point in self.resume_points.items()},
                'current_resume_point': self.current_resume_point.to_dict() if self.current_resume_point else None,
                'error_config': self.error_config,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.resume_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.log(f"レジュームデータ保存エラー: {e}", "error")
    
    def _load_resume_data(self):
        """レジュームデータの読み込み"""
        try:
            if os.path.exists(self.resume_file):
                with open(self.resume_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # レジュームポイントの復元
                self.resume_points = {}
                for url, point_data in data.get('resume_points', {}).items():
                    self.resume_points[url] = ResumePoint.from_dict(point_data)
                
                # 現在のレジュームポイントの復元
                if data.get('current_resume_point'):
                    self.current_resume_point = ResumePoint.from_dict(data['current_resume_point'])
                
                # 設定の復元
                if 'error_config' in data:
                    self.error_config.update(data['error_config'])
                
                self.logger.log(f"レジュームデータを読み込みました: {len(self.resume_points)}件", "info")
                
        except Exception as e:
            self.logger.log(f"レジュームデータ読み込みエラー: {e}", "error")
    
    def _load_error_log(self):
        """エラーログの読み込み"""
        try:
            if os.path.exists(self.error_log_file):
                with open(self.error_log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # エラー統計の復元
                if 'error_stats' in data:
                    self.error_stats.update(data['error_stats'])
                
                self.logger.log("エラーログを読み込みました", "info")
                
        except Exception as e:
            self.logger.log(f"エラーログ読み込みエラー: {e}", "error")
    
    def _save_error_log(self):
        """エラーログの保存"""
        try:
            data = {
                'error_stats': self.error_stats,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.error_log_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.log(f"エラーログ保存エラー: {e}", "error")
    
    def save_resume_point_detailed(self, url: str, page: int, folder: str, 
                                    stage: str = "", sub_stage: str = "", 
                                    stage_data: Optional[Dict[str, Any]] = None, 
                                    reason: str = "", image_page_url: str = "", 
                                    current_url_index: Optional[int] = None, 
                                    absolute_page: Optional[int] = None, 
                                    explicit_download_range_info: Optional[Dict[str, Any]] = None,
                                    downloader_context: Optional[Any] = None) -> bool:
        """詳細な再開ポイントの保存（downloader.py _save_resume_pointから移行）
        
        Args:
            downloader_context: ダウンローダーのコンテキスト（self参照を渡す）
        """
        try:
            # downloader_contextから必要な情報を取得
            if downloader_context:
                parent = downloader_context.parent
                state_manager = downloader_context.state_manager
                session_manager = downloader_context.session_manager
                cached_gallery_info = getattr(downloader_context, 'cached_gallery_info', {})
                current_download_context = getattr(downloader_context, 'current_download_context', None)
                download_range_info_attr = getattr(downloader_context, 'download_range_info', None)
                
                # get_retry_countメソッド
                get_retry_count = getattr(downloader_context, 'get_retry_count', lambda x: 0)
            else:
                # フォールバック
                parent = self.gui_operations
                state_manager = self.state_manager
                session_manager = None
                cached_gallery_info = {}
                current_download_context = None
                download_range_info_attr = None
                get_retry_count = lambda x: 0
            
            # normalize_urlメソッドを取得
            normalize_url = getattr(parent, 'normalize_url', lambda x: x)
            
            # エラー発生時はスキップされたURLでも復帰ポイントを保存
            if url:
                normalized_url = normalize_url(url)
                url_status = state_manager.get_url_status(normalized_url)
                if url_status == 'skipped' and reason != 'error':
                    return True
            
            # 理由の自動判定
            if not reason:
                if stage == 'image_download' and sub_stage == 'after':
                    reason = 'error'
                elif stage == 'image_download' and sub_stage == 'before':
                    reason = 'pause'
                else:
                    reason = 'progress'
            
            # エラー時はリトライカウントも保存
            retry_count = 0
            if reason == 'error' and image_page_url:
                retry_count = get_retry_count(image_page_url)
                self.logger.log(f"[リトライ保存] {image_page_url}: {retry_count}回のリトライ回数を保存")
            
            # gallery_infoキャッシュの取得
            gallery_info_cache = None
            original_total_pages = 0
            if cached_gallery_info and url:
                normalized_url = normalize_url(url)
                gallery_info_cache = cached_gallery_info.get(normalized_url)
                if gallery_info_cache:
                    original_total_pages = gallery_info_cache.get('original_total_images', 0)
                    if original_total_pages <= 0:
                        image_urls = gallery_info_cache.get('image_page_urls', [])
                        if image_urls:
                            original_total_pages = len(image_urls)
            
            # 既存のプログレスバーからoriginal_totalを取得
            if original_total_pages <= 0:
                try:
                    url_index = state_manager.get_current_url_index()
                    if url_index is None and hasattr(parent, 'current_url_index'):
                        url_index = parent.current_url_index
                    
                    if url_index is not None:
                        existing_progress = state_manager.get_progress_bar(url_index)
                        if existing_progress:
                            original_total = existing_progress.get('original_total', 0)
                            if original_total > 0:
                                original_total_pages = original_total
                except Exception:
                    pass
            
            # 適用されたダウンロード範囲を取得
            applied_range = None
            if explicit_download_range_info:
                applied_range = explicit_download_range_info
            elif current_download_context and current_download_context.get('url') == url:
                applied_range = current_download_context.get('applied_range')
            else:
                applied_range = state_manager.get_url_applied_range(url)
            
            # 後方互換性: download_range_infoを更新
            if applied_range and applied_range.get('enabled'):
                if downloader_context:
                    downloader_context.download_range_info = applied_range
            else:
                if downloader_context:
                    downloader_context.download_range_info = None
            
            # 絶対ページ番号の計算
            absolute_page_number = None
            download_range_info = None
            
            if absolute_page is not None:
                absolute_page_number = absolute_page
            
            try:
                if applied_range and applied_range.get('enabled'):
                    start_page = applied_range.get('start')
                    end_page = applied_range.get('end')
                    
                    if start_page:
                        try:
                            range_start = int(start_page)
                            
                            if absolute_page_number is None:
                                relative_page_num = max(1, int(page or 1))
                                absolute_page_number = range_start + relative_page_num - 1
                            
                            relative_page = absolute_page_number - range_start + 1
                            if relative_page < 1:
                                relative_page = 1
                            
                            download_range_info = {
                                'enabled': True,
                                'start': range_start,
                                'end': int(end_page) if end_page else None,
                                'relative_page': relative_page,
                                'relative_total': None,
                                'absolute_page': absolute_page_number
                            }
                            
                            # 相対総ページ数を取得
                            try:
                                url_index = state_manager.get_current_url_index()
                                if url_index is None and hasattr(parent, 'current_url_index'):
                                    url_index = parent.current_url_index
                                
                                if url_index is not None:
                                    existing_progress = state_manager.get_progress_bar(url_index)
                                    if existing_progress:
                                        relative_total = existing_progress['state'].get('total', 0)
                                        if relative_total > 0:
                                            download_range_info['relative_total'] = relative_total
                            except Exception as e:
                                self.logger.log(f"相対総ページ数取得エラー: {e}", "error")
                            
                        except (ValueError, TypeError):
                            pass
                else:
                    if absolute_page_number is None:
                        absolute_page_number = max(1, int(page or 1))
            except Exception as e:
                self.logger.log(f"[WARNING] 絶対ページ番号計算エラー: {e}", "warning")
            
            # downloader_contextから追加情報を取得
            if downloader_context:
                current_stage = stage or getattr(downloader_context, 'current_stage', '')
                current_sub_stage = sub_stage or getattr(downloader_context, 'current_sub_stage', '')
                stage_data_copy = (stage_data or getattr(downloader_context, 'stage_data', {})).copy() if hasattr(stage_data or getattr(downloader_context, 'stage_data', {}), 'copy') else (stage_data or {})
                current_image_page_url = image_page_url or getattr(downloader_context, 'current_image_page_url', '')
                current_gallery_title = getattr(downloader_context, 'current_gallery_title', '')
                artist = getattr(downloader_context, 'artist', '')
                parody = getattr(downloader_context, 'parody', '')
                character = getattr(downloader_context, 'character', '')
                group = getattr(downloader_context, 'group', '')
                current_total = getattr(downloader_context, 'current_total', 0)
            else:
                current_stage = stage
                current_sub_stage = sub_stage
                stage_data_copy = (stage_data or {}).copy() if hasattr(stage_data or {}, 'copy') else {}
                current_image_page_url = image_page_url
                current_gallery_title = ''
                artist = ''
                parody = ''
                character = ''
                group = ''
                current_total = 0
            
            resume_data = {
                'url': url or '',
                'page': max(0, int(page or 0)),
                'absolute_page_number': absolute_page_number if absolute_page_number is not None else max(0, int(page or 0)),
                'download_range_info': download_range_info,
                'folder': folder or '',
                'stage': current_stage,
                'sub_stage': current_sub_stage,
                'stage_data': stage_data_copy,
                'reason': reason or '',
                'current_url_index': current_url_index if current_url_index is not None else getattr(parent, 'current_url_index', 0),
                'image_page_url': current_image_page_url,
                'retry_count': retry_count,
                'gallery_metadata': {
                    'title': current_gallery_title,
                    'artist': artist,
                    'parody': parody,
                    'character': character,
                    'group': group,
                    'total_pages': original_total_pages if original_total_pages > 0 else current_total
                },
                'gallery_info': gallery_info_cache,
                'timestamp': time.time()
            }
            
            # StateManager経由で再開ポイントを保存
            if url:
                normalized_url = normalize_url(url)
                state_manager.set_resume_point(normalized_url, resume_data)
            
            # unified_error_resume_managerへの保存
            if url:
                normalized_url = normalize_url(url) if url else ''
                if normalized_url:
                    stage_for_update = stage or 'image_download'
                    self.update_resume_point(normalized_url, stage_for_update, resume_data)
            
            return True
            
        except Exception as e:
            self.logger.log(f"再開ポイント保存エラー: {e}", "error")
            import traceback
            self.logger.log(f"再開ポイント保存エラー詳細: {traceback.format_exc()}", "error")
            return False
    
    def restore_resume_info_detailed(self, normalized_url: str, resume_info: Dict[str, Any], 
                                      options: Dict[str, Any], use_mapping: bool = True,
                                      downloader_context: Optional[Any] = None) -> Tuple[Optional[int], int, Optional[Dict[str, Any]]]:
        """復帰ポイントから復元処理を実行（downloader.py _restore_resume_infoから移行）
        
        Returns:
            Tuple[resume_page, total_pages, download_range_info]
        """
        try:
            if not resume_info:
                return None, 0, None
            
            # downloader_contextから必要な情報を取得
            if downloader_context:
                state_manager = downloader_context.state_manager
                session_manager = downloader_context.session_manager
                range_manager = getattr(downloader_context, 'range_manager', None)
                _get_current_options = getattr(downloader_context, '_get_current_options', lambda: options)
                _get_gallery_pages = getattr(downloader_context, '_get_gallery_pages', None)
            else:
                state_manager = self.state_manager
                session_manager = None
                range_manager = None
                _get_current_options = lambda: options
                _get_gallery_pages = None
            
            # エラーレジューム時は保存された相対ページ番号をそのまま使用
            if not use_mapping:
                download_range_info_from_resume = resume_info.get('download_range_info')
                if download_range_info_from_resume and download_range_info_from_resume.get('enabled'):
                    relative_page = download_range_info_from_resume.get('relative_page')
                    if relative_page and relative_page > 0:
                        resume_page = relative_page
                        relative_total = download_range_info_from_resume.get('relative_total', 0)
                        if relative_total <= 0:
                            url_index = state_manager.get_current_url_index()
                            if url_index is None:
                                url_index = state_manager.get_url_index_by_url(normalized_url)
                            if url_index is not None:
                                existing_progress = state_manager.get_progress_bar(url_index)
                                if existing_progress:
                                    relative_total = existing_progress['state'].get('total', 0)
                        if relative_total <= 0:
                            relative_total = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
                        self.logger.log(f"[エラーレジューム] 保存された相対ページ番号{resume_page}から再開します", "info")
                        download_range_info_from_resume['range_changed'] = False
                        return resume_page, relative_total, download_range_info_from_resume
                    else:
                        saved_page = resume_info.get('page', 0)
                        if saved_page > 0:
                            resume_page = saved_page
                            relative_total = download_range_info_from_resume.get('relative_total', 0)
                            if relative_total <= 0:
                                relative_total = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
                            self.logger.log(f"[エラーレジューム] 保存されたページ番号{resume_page}から再開します（相対ページ番号として解釈）", "info")
                            download_range_info_from_resume['range_changed'] = False
                            return resume_page, relative_total, download_range_info_from_resume
                else:
                    saved_page = resume_info.get('page', 0)
                    if saved_page > 0:
                        resume_page = saved_page
                        total_pages = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
                        self.logger.log(f"[エラーレジューム] 保存されたページ番号{resume_page}から再開します", "info")
                        return resume_page, total_pages, None
                    else:
                        self.logger.log(f"[エラーレジューム] ページ番号が取得できないため、1から開始します", "warning")
                        return 1, 0, None
            
            # 絶対ページ番号を優先的に使用
            saved_page = resume_info.get('page')
            absolute_page_number = resume_info.get('absolute_page_number')
            download_range_info_from_resume = resume_info.get('download_range_info')
            
            if absolute_page_number is not None:
                absolute_page = absolute_page_number
            elif saved_page is not None and saved_page > 0:
                absolute_page = saved_page
            else:
                absolute_page = 1
                self.logger.log(f"[WARNING] 絶対ページ番号が取得できないため、1から開始します")
            
            # URL単位のダウンロード範囲設定を取得
            url_download_range = state_manager.get_url_download_range(normalized_url) if hasattr(state_manager, 'get_url_download_range') else {'enabled': False}
            new_range_enabled = url_download_range.get('enabled')
            
            # 保存されたダウンロード範囲と現在のダウンロード範囲を比較
            range_changed = False
            current_options = _get_current_options()
            
            if download_range_info_from_resume and download_range_info_from_resume.get('enabled'):
                saved_start = download_range_info_from_resume.get('start')
                saved_end = download_range_info_from_resume.get('end')
                
                if use_mapping and range_manager:
                    range_changed = range_manager.is_range_changed(
                        download_range_info_from_resume,
                        current_options
                    )
                    if range_changed:
                        self.logger.log(f"[INFO] ダウンロード範囲が変更されました: 保存時({saved_start}-{saved_end}) → 現在の設定を確認中")
                    else:
                        self.logger.log(f"[INFO] 保存されたダウンロード範囲を復元: {saved_start}-{saved_end}")
                else:
                    range_changed = False
                    self.logger.log(f"[INFO] 保存されたダウンロード範囲を復元: {saved_start}-{saved_end}")
                
                if not range_changed:
                    new_start = saved_start
                    new_end = saved_end
                else:
                    if new_range_enabled:
                        new_start = url_download_range.get('start')
                        new_end = url_download_range.get('end')
                    else:
                        new_start = None
                        new_end = None
            elif new_range_enabled:
                range_changed = True
                new_start_str = current_options.get('download_range_start', '')
                new_end_str = current_options.get('download_range_end', '')
                try:
                    new_start = int(new_start_str) if new_start_str else 0
                    new_end = int(new_end_str) if new_end_str else None
                    self.logger.log(f"[INFO] ダウンロード範囲が有効になりました: 現在({new_start}-{new_end})")
                except (ValueError, TypeError):
                    new_start = None
                    new_end = None
            else:
                if download_range_info_from_resume and download_range_info_from_resume.get('enabled'):
                    range_changed = True
                    self.logger.log(f"[INFO] ダウンロード範囲が無効になりました")
                new_start = None
                new_end = None
            
            if new_range_enabled and (new_start is None or new_end is None):
                new_start = url_download_range.get('start')
                new_end = url_download_range.get('end')
            
            # 絶対ページ番号を新しい範囲にマッピング（長いロジックは省略、必要に応じて downloader.py から移行）
            resume_page = absolute_page  # 簡略化（完全な移行は後続で）
            
            # 総ページ数の取得（簡略化）
            total_pages = resume_info.get('gallery_metadata', {}).get('total_pages', 0)
            
            # download_range_infoの構築
            if download_range_info_from_resume:
                download_range_info_from_resume['range_changed'] = range_changed
                return resume_page, total_pages, download_range_info_from_resume
            elif new_range_enabled:
                download_range_info_from_resume = {
                    'enabled': True,
                    'start': int(current_options.get('download_range_start', '0') or '0'),
                    'end': int(current_options.get('download_range_end', '')) if current_options.get('download_range_end', '') else None,
                    'range_changed': True
                }
                return resume_page, total_pages, download_range_info_from_resume
            else:
                return resume_page, total_pages, {'enabled': False, 'range_changed': True}
            
        except Exception as e:
            self.logger.log(f"復帰情報復元エラー: {e}", "error")
            import traceback
            self.logger.log(f"復帰情報復元エラー詳細: {traceback.format_exc()}", "error")
            return 1, 0, None

