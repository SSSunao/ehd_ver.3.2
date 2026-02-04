# -*- coding: utf-8 -*-
"""
非同期実行クラス - 非同期処理を外側に集約
⭐修正: ThreadPoolExecutorでスレッド数を制限⭐
"""

import threading
import time
import traceback
from typing import Callable, Any, Optional
from concurrent.futures import ThreadPoolExecutor, Future
from core.interfaces import IAsyncExecutor

class AsyncExecutor(IAsyncExecutor):
    """非同期処理を管理するクラス
    
    ⭐重要: ThreadPoolExecutorでスレッド数を制限⭐
    無制限なスレッド生成を防ぎ、リソース枯渇を防ぐ
    """
    
    def __init__(self, root, max_workers: int = 3):
        """
        Args:
            root: Tkinterのrootウィジェット
            max_workers: 最大スレッド数（デフォルト3）
        """
        self.root = root
        self.executor_thread = None
        self.task_queue = []
        self.queue_lock = threading.Lock()
        self.running = False
        
        # ⭐ThreadPoolExecutorでスレッド数を制限⭐
        self._thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="Download-"
        )
        print(f"[AsyncExecutor] ThreadPoolExecutor初期化: max_workers={max_workers}")
    
    def _handle_error(self, error: Exception, context: str):
        """エラーハンドリング（統一処理）"""
        error_msg = f"[{context}] Error: {type(error).__name__}: {str(error)}"
        print(error_msg)
        # デバッグモードの場合はスタックトレースも出力
        import sys
        if hasattr(sys, 'gettrace') and sys.gettrace() is not None:
            traceback.print_exc()
    
    def execute_async(self, func: Callable, *args, **kwargs):
        """非同期で関数を実行"""
        def async_wrapper():
            try:
                func(*args, **kwargs)
            except Exception as e:
                self._handle_error(e, "AsyncExecutor.execute_async")
        
        thread = threading.Thread(target=async_wrapper, daemon=True)
        thread.start()
        return thread
    
    def execute_after(self, delay_ms: int, func: Callable, *args, **kwargs):
        """指定時間後にGUIスレッドで関数を実行"""
        def delayed_wrapper():
            try:
                func(*args, **kwargs)
            except Exception as e:
                self._handle_error(e, "AsyncExecutor.execute_after")
        
        self.root.after(delay_ms, delayed_wrapper)
    
    def execute_gui_async(self, func: Callable, *args, **kwargs):
        """GUIスレッドで非同期実行"""
        def gui_wrapper():
            try:
                func(*args, **kwargs)
            except Exception as e:
                self._handle_error(e, "AsyncExecutor.execute_gui_async")
        
        self.root.after(0, gui_wrapper)
    
    def execute_in_thread(self, func: Callable, *args, **kwargs) -> Future:
        """
        専用スレッドで実行
        
        ⭐修正: ThreadPoolExecutorを使用してスレッド数を制限⭐
        無制限なスレッド生成を防ぎ、同時実行数を制限する
        
        Args:
            func: 実行する関数
            *args: 関数の引数
            **kwargs: 関数のキーワード引数
            
        Returns:
            Futureオブジェクト
        """
        def thread_wrapper():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._handle_error(e, "AsyncExecutor.execute_in_thread")
                raise
        
        # ⭐ThreadPoolExecutorで実行（スレッド数制限）⭐
        future = self._thread_pool.submit(thread_wrapper)
        return future
