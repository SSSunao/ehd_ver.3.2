"""エラーコンテキスト標準化 - Phase 1"""
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any
import json

@dataclass
class ErrorContext:
    """
    エラー発生時のコンテキスト情報
    
    エラーログに必要な情報を構造化して保持することで、
    デバッグを容易にし、エラー原因の特定を迅速化する。
    
    Attributes:
        operation: 実行していた操作（例: "download", "progress_update"）
        url: 対象URL（オプション）
        url_index: URLインデックス（オプション）
        file_path: ファイルパス（オプション）
        error_message: エラーメッセージ（オプション）
        additional_info: 追加情報（オプション）
    """
    operation: str
    url: Optional[str] = None
    url_index: Optional[int] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    def to_json(self, indent: int = 2) -> str:
        """
        JSON文字列に変換
        
        Args:
            indent: インデント幅
            
        Returns:
            JSON文字列
        """
        return json.dumps(asdict(self), indent=indent, ensure_ascii=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        辞書に変換
        
        Returns:
            辞書形式のコンテキスト
        """
        return asdict(self)
    
    def add_info(self, key: str, value: Any) -> 'ErrorContext':
        """
        追加情報を設定（チェーンメソッド）
        
        Args:
            key: 情報のキー
            value: 情報の値
            
        Returns:
            自身（メソッドチェーン用）
            
        Examples:
            >>> context = ErrorContext.for_download("https://example.com")
            >>> context.add_info("retry_count", 3).add_info("last_error", "timeout")
        """
        if self.additional_info is None:
            self.additional_info = {}
        self.additional_info[key] = value
        return self
    
    @classmethod
    def for_download(cls, url: str, url_index: Optional[int] = None) -> 'ErrorContext':
        """
        ダウンロード用コンテキストを作成
        
        Args:
            url: ダウンロード対象URL
            url_index: URLインデックス（オプション）
            
        Returns:
            ErrorContextインスタンス
        """
        return cls(operation="download", url=url, url_index=url_index)
    
    @classmethod
    def for_progress_update(cls, url_index: int, url: Optional[str] = None) -> 'ErrorContext':
        """
        プログレス更新用コンテキストを作成
        
        Args:
            url_index: URLインデックス
            url: URL（オプション）
            
        Returns:
            ErrorContextインスタンス
        """
        return cls(operation="progress_update", url_index=url_index, url=url)
    
    @classmethod
    def for_file_operation(cls, file_path: str, operation: str = "file_operation") -> 'ErrorContext':
        """
        ファイル操作用コンテキストを作成
        
        Args:
            file_path: ファイルパス
            operation: 操作名（デフォルト: "file_operation"）
            
        Returns:
            ErrorContextインスタンス
        """
        return cls(operation=operation, file_path=file_path)
    
    @classmethod
    def for_network_request(cls, url: str, method: str = "GET") -> 'ErrorContext':
        """
        ネットワークリクエスト用コンテキストを作成
        
        Args:
            url: リクエストURL
            method: HTTPメソッド（デフォルト: "GET"）
            
        Returns:
            ErrorContextインスタンス
        """
        return cls(
            operation="network_request",
            url=url,
            additional_info={"method": method}
        )
    
    @classmethod
    def for_parsing(cls, url: Optional[str] = None, content_type: Optional[str] = None) -> 'ErrorContext':
        """
        HTML/JSONパース用コンテキストを作成
        
        Args:
            url: パース対象のURL（オプション）
            content_type: コンテンツタイプ（例: "html", "json"）
            
        Returns:
            ErrorContextインスタンス
        """
        context = cls(operation="parsing", url=url)
        if content_type:
            context.add_info("content_type", content_type)
        return context


@dataclass
class ValidationError:
    """
    バリデーションエラー情報
    
    複数のバリデーションエラーを収集するために使用。
    
    Attributes:
        field_name: フィールド名
        error_message: エラーメッセージ
        invalid_value: 不正な値（オプション）
    """
    field_name: str
    error_message: str
    invalid_value: Optional[Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return asdict(self)


class ValidationErrorCollection:
    """
    バリデーションエラーのコレクション
    
    複数のバリデーションエラーを収集し、一度に報告する。
    """
    
    def __init__(self):
        self.errors: list[ValidationError] = []
    
    def add_error(self, field_name: str, error_message: str, invalid_value: Optional[Any] = None) -> None:
        """
        エラーを追加
        
        Args:
            field_name: フィールド名
            error_message: エラーメッセージ
            invalid_value: 不正な値（オプション）
        """
        self.errors.append(ValidationError(field_name, error_message, invalid_value))
    
    def has_errors(self) -> bool:
        """エラーが存在するか"""
        return len(self.errors) > 0
    
    def get_error_messages(self) -> list[str]:
        """すべてのエラーメッセージを取得"""
        return [f"{e.field_name}: {e.error_message}" for e in self.errors]
    
    def to_json(self, indent: int = 2) -> str:
        """JSON文字列に変換"""
        return json.dumps(
            [e.to_dict() for e in self.errors],
            indent=indent,
            ensure_ascii=False
        )
    
    def raise_if_errors(self, context: Optional[ErrorContext] = None) -> None:
        """
        エラーが存在する場合に例外を投げる
        
        Args:
            context: エラーコンテキスト（オプション）
            
        Raises:
            ValueError: エラーが存在する場合
        """
        if self.has_errors():
            error_message = "\n".join(self.get_error_messages())
            if context:
                raise ValueError(f"Validation failed:\n{error_message}\n\nContext:\n{context.to_json()}")
            else:
                raise ValueError(f"Validation failed:\n{error_message}")


# 使用例のドキュメント
"""
使用例:

1. ダウンロードエラー:
    try:
        download_image(url)
    except Exception as e:
        context = ErrorContext.for_download(url, url_index=5)
        context.add_info("retry_count", 3).add_info("timeout", 30)
        logger.error(f"Download failed: {e}\\n{context.to_json()}")

2. プログレス更新エラー:
    if url_index is None:
        context = ErrorContext.for_progress_update(url_index, url)
        context.add_info("available_indices", list(progress_bars.keys()))
        raise ValueError(f"Invalid url_index\\n{context.to_json()}")

3. 複数のバリデーションエラー:
    errors = ValidationErrorCollection()
    
    if not url:
        errors.add_error("url", "URL must not be empty", url)
    
    if total_pages <= 0:
        errors.add_error("total_pages", "must be positive", total_pages)
    
    context = ErrorContext.for_download(url)
    errors.raise_if_errors(context)  # エラーがあれば例外
"""
