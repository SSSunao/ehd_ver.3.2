"""バリデーションユーティリティ - Phase 1"""
from typing import Optional, TypeVar, Dict, Any

T = TypeVar('T')

def require_not_none(value: Optional[T], name: str, default: Optional[T] = None) -> T:
    """
    値がNoneでないことを保証する
    
    Args:
        value: チェックする値
        name: 変数名（エラーメッセージ用）
        default: デフォルト値（指定された場合、Noneの時にこれを返す）
        
    Returns:
        非Noneの値
        
    Raises:
        ValueError: 値がNoneでデフォルトも指定されていない場合
        
    Examples:
        >>> title = require_not_none(gallery_title, "title", default="準備中...")
        >>> url_index = require_not_none(current_url_index, "url_index")  # Noneの場合ValueError
    """
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"{name} must not be None")
    return value


def safe_str(value: Any, maxlen: Optional[int] = None) -> str:
    """
    任意の値を安全に文字列化する（Noneは空文字列に変換）
    
    Args:
        value: 文字列化する値
        maxlen: 最大文字数（指定された場合、切り詰める）
        
    Returns:
        文字列化された値
        
    Examples:
        >>> safe_str(None)
        ''
        >>> safe_str("Long Title", maxlen=5)
        'Long '
        >>> safe_str(12345)
        '12345'
    """
    if value is None:
        return ""
    
    str_value = str(value)
    
    if maxlen is not None and len(str_value) > maxlen:
        return str_value[:maxlen]
    
    return str_value


def safe_format(template: str, **kwargs: Any) -> str:
    """
    Noneを含む可能性のある値を安全にフォーマットする
    
    Args:
        template: フォーマット文字列（{key}形式）
        **kwargs: フォーマット引数（Noneは空文字列に変換される）
        
    Returns:
        フォーマットされた文字列
        
    Examples:
        >>> safe_format("タイトル: {title}", title=None)
        'タイトル: '
        >>> safe_format("進捗: {current}/{total}", current=5, total=10)
        '進捗: 5/10'
        >>> safe_format("URL: {url:.50}", url="https://example.com/very/long/url/...")
        'URL: https://example.com/very/long/url/...'
    """
    safe_kwargs: Dict[str, Any] = {}
    
    for key, value in kwargs.items():
        if value is None:
            safe_kwargs[key] = ""
        else:
            safe_kwargs[key] = value
    
    try:
        return template.format(**safe_kwargs)
    except (KeyError, ValueError) as e:
        # フォーマットエラーの場合、元のテンプレートとエラー情報を返す
        return f"{template} (format error: {e})"


def validate_positive(value: int, name: str) -> int:
    """
    正の整数であることを検証する
    
    Args:
        value: 検証する値
        name: 変数名（エラーメッセージ用）
        
    Returns:
        検証済みの値
        
    Raises:
        ValueError: 値が0以下の場合
        
    Examples:
        >>> validate_positive(10, "total_pages")
        10
        >>> validate_positive(0, "total_pages")
        ValueError: total_pages must be positive, got: 0
    """
    if value <= 0:
        raise ValueError(f"{name} must be positive, got: {value}")
    return value


def validate_url(url: Optional[str], name: str = "url") -> str:
    """
    URLが有効であることを検証する
    
    Args:
        url: 検証するURL
        name: 変数名（エラーメッセージ用）
        
    Returns:
        検証済みのURL
        
    Raises:
        ValueError: URLがNoneまたは空文字列の場合
        
    Examples:
        >>> validate_url("https://example.com")
        'https://example.com'
        >>> validate_url(None)
        ValueError: url must not be empty
        >>> validate_url("  ")
        ValueError: url must not be empty
    """
    if url is None or not url.strip():
        raise ValueError(f"{name} must not be empty")
    return url.strip()


def validate_index(index: Optional[int], name: str, min_value: int = 0) -> int:
    """
    インデックスが有効範囲であることを検証する
    
    Args:
        index: 検証するインデックス
        name: 変数名（エラーメッセージ用）
        min_value: 最小値（デフォルト: 0）
        
    Returns:
        検証済みのインデックス
        
    Raises:
        ValueError: インデックスがNoneまたは範囲外の場合
        
    Examples:
        >>> validate_index(5, "url_index")
        5
        >>> validate_index(None, "url_index")
        ValueError: url_index must not be None
        >>> validate_index(-1, "url_index")
        ValueError: url_index must be >= 0, got: -1
    """
    if index is None:
        raise ValueError(f"{name} must not be None")
    
    if index < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got: {index}")
    
    return index
