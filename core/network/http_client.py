# -*- coding: utf-8 -*-
"""
統合HTTPクライアント - requests.get/session.getを全て統合
⭐修正: スレッドローカルストレージで各スレッドが独立したセッションを持つ⭐
"""

import requests
import time
from typing import Dict, Any, Optional, Callable
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import threading


class HttpClient:
    """
    統合HTTPクライアント
    全てのHTTPリクエストを一元管理
    
    ⭐重要: スレッドローカルストレージでセッションを管理⭐
    requests.Session()はスレッドセーフではないため、
    各スレッドが独立したセッションを持つことで競合を防ぐ
    """
    
    def __init__(self, parent=None, logger=None):
        """
        Args:
            parent: 親オブジェクト（設定取得用）
            logger: ロガーオブジェクト
        """
        print("[HTTP_CLIENT] ========== HttpClient初期化開始 ==========")
        self.parent = parent
        self.logger = logger
        
        # ⭐スレッドローカルストレージ：各スレッドが独自のセッションを持つ⭐
        self._thread_local = threading.local()
        print(f"[HTTP_CLIENT] スレッドローカルストレージ初期化完了: {id(self._thread_local)}")
        
        # デフォルト設定
        self.default_timeout = 30.0
        self.default_max_retries = 3
        self.default_backoff_factor = 1.0
        print(f"[HTTP_CLIENT] デフォルト設定: timeout={self.default_timeout}, retries={self.default_max_retries}")
        
        # リクエスト統計
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retry_requests': 0,
        }
        print("[HTTP_CLIENT] ========== HttpClient初期化完了 ==========")

    
    def _get_session(self) -> requests.Session:
        """
        スレッドローカルストレージからセッションを取得
        各スレッドが独自のセッションを持つため、ロック不要
        
        Returns:
            現在のスレッド用のrequests.Session
        """
        # ⭐スレッドローカルストレージからセッションを取得⭐
        if not hasattr(self._thread_local, 'session') or self._thread_local.session is None:
            # このスレッド用のセッションを生成
            session = requests.Session()
            
            # リトライ設定
            retry_strategy = Retry(
                total=self.default_max_retries,
                backoff_factor=self.default_backoff_factor,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
            )
            
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # デフォルトヘッダー
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            })
            
            # スレッドローカルストレージに保存
            self._thread_local.session = session
            
            # デバッグログ（print使用でブロック回避）
            thread_id = threading.current_thread().ident
            print(f"[HTTP_CLIENT] スレッド{thread_id}用の新規セッションを生成しました")
        
        return self._thread_local.session
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """
        GETリクエストを実行
        
        Args:
            url: リクエストURL
            **kwargs: requests.getに渡す追加引数
            
        Returns:
            レスポンスオブジェクト
        """
        return self._request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """
        POSTリクエストを実行
        
        Args:
            url: リクエストURL
            **kwargs: requests.postに渡す追加引数
            
        Returns:
            レスポンスオブジェクト
        """
        return self._request('POST', url, **kwargs)
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        HTTPリクエストを実行（内部メソッド）
        
        ⭐修正: スレッドローカルストレージでロック不要⭐
        各スレッドが独自のセッションを持つため、
        ロックなしで完全に並列実行可能
        
        Args:
            method: HTTPメソッド
            url: リクエストURL
            **kwargs: 追加引数
            
        Returns:
            レスポンスオブジェクト
        """
        try:
            # 統計更新
            self.stats['total_requests'] += 1
            
            # タイムアウト設定
            if 'timeout' not in kwargs:
                kwargs['timeout'] = self.default_timeout
            
            # ⭐DEBUG: タイムアウト設定を確認（print使用でブロック回避）⭐
            thread_id = threading.current_thread().ident
            print(f"[HTTP_CLIENT] タイムアウト: {kwargs.get('timeout')}秒, Thread={thread_id}")
            
            # ⭐スレッドローカルストレージからセッションを取得（ロック不要）⭐
            session = self._get_session()
            session_id = id(session)
            print(f"[HTTP_CLIENT] セッション取得: ID={session_id}, Thread={thread_id}")
            
            # ⭐DEBUG: HTTP通信開始（print使用でブロック回避）⭐
            print(f"[HTTP_CLIENT] {method}実行直前: URL={url[:80]}, Thread={thread_id}")
            
            # ⭐HTTP通信を実行（ロック不要）⭐
            if method == 'GET':
                print(f"[HTTP_CLIENT] session.get()呼び出し...")
                response = session.get(url, **kwargs)
                print(f"[HTTP_CLIENT] session.get()完了!")
            elif method == 'POST':
                response = session.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # ⭐DEBUG: HTTP通信完了⭐
            print(f"[HTTP_CLIENT] {method}完了: Status={response.status_code}, Thread={thread_id}")
            
            # ステータスチェック
            response.raise_for_status()
            
            # 統計更新
            self.stats['successful_requests'] += 1
            
            return response
            
        except requests.exceptions.RequestException as e:
            self.stats['failed_requests'] += 1
            self.log(f"HTTPリクエストエラー: {url} - {e}", "error")
            raise
    
    def get_with_retry(
        self, 
        url: str, 
        max_retries: Optional[int] = None,
        retry_delay: float = 1.0,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ) -> requests.Response:
        """
        リトライ付きGETリクエスト
        
        Args:
            url: リクエストURL
            max_retries: 最大リトライ回数
            retry_delay: リトライ間隔（秒）
            on_retry: リトライ時のコールバック
            **kwargs: 追加引数
            
        Returns:
            レスポンスオブジェクト
        """
        if max_retries is None:
            max_retries = self.default_max_retries
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = self.get(url, **kwargs)
                return response
                
            except requests.exceptions.RequestException as e:
                last_error = e
                
                if attempt < max_retries:
                    # リトライ
                    self.stats['retry_requests'] += 1
                    self.log(f"リトライ {attempt + 1}/{max_retries}: {url}", "warning")
                    
                    if on_retry:
                        on_retry(attempt + 1, e)
                    
                    time.sleep(retry_delay)
                else:
                    # リトライ上限
                    break
        
        # 全てのリトライが失敗
        raise last_error
    
    def set_cookies(self, cookies: Dict[str, str]):
        """クッキーを設定"""
        with self._session_lock:
            self._session.cookies.update(cookies)
    
    def set_headers(self, headers: Dict[str, str]):
        """ヘッダーを設定"""
        with self._session_lock:
            self._session.headers.update(headers)
    
    def reset_session(self):
        """セッションをリセット"""
        self._init_session()
        self.log("HTTPセッションをリセットしました", "info")
    
    def get_stats(self) -> Dict[str, int]:
        """統計情報を取得"""
        return self.stats.copy()
    
    def log(self, message: str, level: str = "info"):
        """ログ出力"""
        if self.logger:
            self.logger.log(f"[HttpClient] {message}", level)
        elif self.parent and hasattr(self.parent, 'log'):
            self.parent.log(f"[HttpClient] {message}", level)
    
    def close(self):
        """セッションをクローズ"""
        with self._session_lock:
            if self._session:
                self._session.close()
                self._session = None
