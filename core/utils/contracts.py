"""契約設計ユーティリティ - Phase 1"""
from functools import wraps
from typing import Callable, Any, TypeVar

T = TypeVar('T')

def require(condition: bool, message: str) -> None:
    """
    前提条件（Precondition）をチェックする
    
    関数の開始時に使用し、引数や状態が期待通りであることを保証する。
    
    Args:
        condition: チェックする条件（Falseの場合に例外）
        message: 条件が満たされない場合のエラーメッセージ
        
    Raises:
        ValueError: 条件がFalseの場合
        
    Examples:
        >>> def download(url: str, total: int):
        ...     require(url is not None and url.strip() != "", "url must not be empty")
        ...     require(total > 0, f"total must be positive, got: {total}")
        ...     # ダウンロード処理
    """
    if not condition:
        raise ValueError(f"Precondition failed: {message}")


def ensure(condition: bool, message: str) -> None:
    """
    事後条件（Postcondition）をチェックする
    
    関数の終了前に使用し、結果が期待通りであることを保証する。
    
    Args:
        condition: チェックする条件（Falseの場合に例外）
        message: 条件が満たされない場合のエラーメッセージ
        
    Raises:
        AssertionError: 条件がFalseの場合
        
    Examples:
        >>> def fetch_data(url: str) -> dict:
        ...     data = _internal_fetch(url)
        ...     ensure(data is not None, "fetch result must not be None")
        ...     ensure('title' in data, "fetch result must contain 'title'")
        ...     return data
    """
    if not condition:
        raise AssertionError(f"Postcondition failed: {message}")


def invariant(condition: bool, message: str) -> None:
    """
    不変条件（Invariant）をチェックする
    
    クラスのメソッド開始時・終了時に使用し、オブジェクトの状態が常に一貫していることを保証する。
    
    Args:
        condition: チェックする条件（Falseの場合に例外）
        message: 条件が満たされない場合のエラーメッセージ
        
    Raises:
        AssertionError: 条件がFalseの場合
        
    Examples:
        >>> class DownloadQueue:
        ...     def __init__(self):
        ...         self.urls = []
        ...     
        ...     def add_url(self, url: str):
        ...         invariant(len(self.urls) >= 0, "queue size must be non-negative")
        ...         self.urls.append(url)
        ...         invariant(len(self.urls) > 0, "queue must not be empty after adding")
    """
    if not condition:
        raise AssertionError(f"Invariant failed: {message}")


def precondition(checker: Callable[..., None]) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    前提条件チェックをデコレータとして適用する
    
    Args:
        checker: 前提条件をチェックする関数（引数は元の関数と同じ）
        
    Returns:
        デコレータ関数
        
    Examples:
        >>> def check_args(self, url: str, total: int):
        ...     require(url is not None, "url must not be None")
        ...     require(total > 0, "total must be positive")
        ...
        >>> @precondition(check_args)
        ... def download(self, url: str, total: int):
        ...     # ダウンロード処理
        ...     pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # 前提条件チェック実行
            checker(*args, **kwargs)
            # 元の関数実行
            return func(*args, **kwargs)
        return wrapper
    return decorator


def postcondition(checker: Callable[[T], None]) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    事後条件チェックをデコレータとして適用する
    
    Args:
        checker: 事後条件をチェックする関数（引数は関数の戻り値）
        
    Returns:
        デコレータ関数
        
    Examples:
        >>> def check_result(result: dict):
        ...     ensure(result is not None, "result must not be None")
        ...     ensure('title' in result, "result must contain 'title'")
        ...
        >>> @postcondition(check_result)
        ... def fetch_data(url: str) -> dict:
        ...     # データ取得処理
        ...     return {'title': 'Example', 'images': []}
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # 元の関数実行
            result = func(*args, **kwargs)
            # 事後条件チェック実行
            checker(result)
            return result
        return wrapper
    return decorator
