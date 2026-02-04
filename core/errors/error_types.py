# -*- coding: utf-8 -*-
"""
エラー処理の型定義とEnum（Phase 1: マジック文字列削除）
"""

from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from core.errors.enhanced_error_handler import ErrorContext


class DownloadStage(Enum):
    """ダウンロードステージの定義"""
    INITIAL = "initial"
    GALLERY_INFO = "gallery_info"
    IMAGE_LIST = "image_list"
    IMAGE_DOWNLOAD = "image_download"
    IMAGE_PROCESSING = "image_processing"
    COMPRESSION = "compression"
    TORRENT = "torrent"
    COMPLETED = "completed"


class ErrorAction(Enum):
    """エラー発生時のアクション"""
    RETRY = "retry"
    SKIP_IMAGE = "skip_image"
    SKIP_URL = "skip_url"
    PAUSE = "pause"
    ABORT = "abort"
    MANUAL = "manual"
    CONTINUE = "continue"


@dataclass
class RetryResult:
    """
    リトライ処理の結果（Result型パターン）
    
    エラー処理を例外ではなく明示的な戻り値で表現することで、
    制御フローを明確にし、エラーハンドリングを強制する。
    """
    success: bool
    data: Any = None
    error: Optional[Exception] = None
    action: Optional[ErrorAction] = None
    reason: str = ""
    retry_count: int = 0
    skip_reason: str = ""
    
    @classmethod
    def success_result(cls, data: Any, retry_count: int = 0) -> 'RetryResult':
        """成功結果を生成"""
        return cls(success=True, data=data, retry_count=retry_count)
    
    @classmethod
    def failure_result(cls, error: Exception, action: ErrorAction, 
                      reason: str = "", skip_reason: str = "", 
                      retry_count: int = 0) -> 'RetryResult':
        """失敗結果を生成"""
        return cls(
            success=False,
            error=error,
            action=action,
            reason=reason,
            skip_reason=skip_reason,
            retry_count=retry_count
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（後方互換性）"""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'action': self.action.value if self.action else None,
            'reason': self.reason,
            'retry_count': self.retry_count,
            'skip_reason': self.skip_reason,
            'status': 'success' if self.success else 'failure'  # 後方互換性
        }


@dataclass
class DownloadContext:
    """
    ダウンロードコンテキスト情報（DTO - Data Transfer Object）
    
    レイヤー間でダウンロード情報を転送するための専用オブジェクト。
    不変性を重視し、必要な情報のみを保持する。
    """
    url: str
    page_num: int
    total_pages: int
    image_url: Optional[str] = None
    save_path: Optional[str] = None
    gallery_id: Optional[str] = None
    
    def to_stage_data(self) -> Dict[str, Any]:
        """ErrorContextのstage_data形式に変換"""
        return {
            'page_num': self.page_num,
            'total_pages': self.total_pages,
            'image_url': self.image_url,
            'save_path': self.save_path,
            'gallery_id': self.gallery_id
        }


class ErrorContextFactory:
    """
    ErrorContextのファクトリクラス（Factory Pattern）
    
    オブジェクト生成ロジックを集約し、呼び出し側を簡素化する。
    """
    
    @staticmethod
    def create_for_image_download(download_ctx: DownloadContext, 
                                  retry_count: int = 0) -> 'ErrorContext':
        """画像ダウンロード用のErrorContextを生成"""
        from core.errors.enhanced_error_handler import ErrorContext
        
        return ErrorContext(
            url=download_ctx.image_url or download_ctx.url,
            stage=DownloadStage.IMAGE_DOWNLOAD.value,
            page_index=download_ctx.page_num,
            retry_count=retry_count,
            stage_data=download_ctx.to_stage_data()
        )
    
    @staticmethod
    def create_for_gallery_info(url: str, gallery_id: str = "") -> 'ErrorContext':
        """ギャラリー情報取得用のErrorContextを生成"""
        from core.errors.enhanced_error_handler import ErrorContext
        
        return ErrorContext(
            url=url,
            stage=DownloadStage.GALLERY_INFO.value,
            gallery_id=gallery_id
        )
    
    @staticmethod
    def create_for_image_processing(download_ctx: DownloadContext) -> 'ErrorContext':
        """画像処理用のErrorContextを生成"""
        from core.errors.enhanced_error_handler import ErrorContext
        
        return ErrorContext(
            url=download_ctx.url,
            stage=DownloadStage.IMAGE_PROCESSING.value,
            page_index=download_ctx.page_num,
            stage_data=download_ctx.to_stage_data()
        )
