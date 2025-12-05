"""
カスタム例外クラス

アプリケーション固有のエラーを定義
エラーメッセージ・コード・対処法を統一管理
"""
from typing import List, Optional


class ApplicationError(Exception):
    """
    アプリケーション基本例外

    全てのカスタム例外の基底クラス
    """

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        suggestions: Optional[List[str]] = None,
        details: Optional[dict] = None
    ):
        self.message = message
        self.code = code
        self.suggestions = suggestions or []
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """JSON レスポンス用の辞書に変換"""
        return {
            "success": False,
            "error": self.message,
            "error_code": self.code,
            "suggestions": self.suggestions,
            "details": self.details
        }


class FreeeAPIError(ApplicationError):
    """
    freee API 固有エラー

    API呼び出し時のエラーを統一管理
    """

    # エラーコード定義
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_MISSING = "TOKEN_MISSING"
    COMPANY_NOT_FOUND = "COMPANY_NOT_FOUND"
    RATE_LIMIT = "RATE_LIMIT"
    API_ERROR = "API_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"

    def __init__(
        self,
        message: str,
        code: str = "API_ERROR",
        suggestions: Optional[List[str]] = None,
        details: Optional[dict] = None,
        status_code: Optional[int] = None
    ):
        self.status_code = status_code
        super().__init__(message, code, suggestions, details)

    @classmethod
    def token_expired(cls) -> "FreeeAPIError":
        """トークン有効期限切れ"""
        return cls(
            message="アクセストークンの有効期限が切れています",
            code=cls.TOKEN_EXPIRED,
            suggestions=[
                "https://app.secure.freee.co.jp/developers/start_guides/new_company からAPIを取得する"
            ],
            status_code=401
        )

    @classmethod
    def token_invalid(cls) -> "FreeeAPIError":
        """トークン無効"""
        return cls(
            message="アクセストークンが無効です",
            code=cls.TOKEN_INVALID,
            suggestions=[
                "トークンを再確認してください",
                "トークンの先頭・末尾に余分な空白がないか確認"
            ],
            status_code=401
        )

    @classmethod
    def token_missing(cls) -> "FreeeAPIError":
        """トークン未設定"""
        return cls(
            message="アクセストークンが設定されていません",
            code=cls.TOKEN_MISSING,
            suggestions=[
                "https://app.secure.freee.co.jp/developers/start_guides/new_company からAPIを取得する"
            ],
            status_code=401
        )

    @classmethod
    def company_not_found(cls, company_id: int = None) -> "FreeeAPIError":
        """事業所未発見"""
        return cls(
            message=f"事業所が見つかりません (ID: {company_id})" if company_id else "事業所が見つかりません",
            code=cls.COMPANY_NOT_FOUND,
            suggestions=[
                "事業所IDを確認してください",
                "トークンに紐づく事業所か確認してください"
            ],
            status_code=404
        )

    @classmethod
    def rate_limit(cls) -> "FreeeAPIError":
        """レート制限"""
        return cls(
            message="APIリクエスト制限に達しました",
            code=cls.RATE_LIMIT,
            suggestions=[
                "しばらく待ってから再試行してください",
                "1分間に10リクエストが上限です"
            ],
            status_code=429
        )


class ValidationError(ApplicationError):
    """
    入力値検証エラー

    ユーザー入力やリクエストパラメータの検証エラー
    """

    # エラーコード定義
    INVALID_DATE = "INVALID_DATE"
    INVALID_FILE = "INVALID_FILE"
    INVALID_FORMAT = "INVALID_FORMAT"
    MISSING_FIELD = "MISSING_FIELD"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"

    @classmethod
    def invalid_date(cls, field: str, value: str) -> "ValidationError":
        """日付形式エラー"""
        return cls(
            message=f"日付形式が不正です: {field}={value}",
            code=cls.INVALID_DATE,
            suggestions=[
                "YYYY-MM-DD形式で入力してください",
                "例: 2024-06-01"
            ],
            details={"field": field, "value": value}
        )

    @classmethod
    def invalid_file(cls, filename: str, allowed: List[str]) -> "ValidationError":
        """ファイル形式エラー"""
        return cls(
            message=f"許可されていないファイル形式です: {filename}",
            code=cls.INVALID_FILE,
            suggestions=[
                f"許可される形式: {', '.join(allowed)}"
            ],
            details={"filename": filename, "allowed": allowed}
        )

    @classmethod
    def file_too_large(cls, filename: str, size_mb: float, max_mb: float) -> "ValidationError":
        """ファイルサイズ超過"""
        return cls(
            message=f"ファイルサイズが大きすぎます: {filename} ({size_mb:.1f}MB)",
            code=cls.FILE_TOO_LARGE,
            suggestions=[
                f"最大サイズ: {max_mb}MB"
            ],
            details={"filename": filename, "size_mb": size_mb, "max_mb": max_mb}
        )

    @classmethod
    def missing_field(cls, field: str) -> "ValidationError":
        """必須フィールド欠落"""
        return cls(
            message=f"必須項目が入力されていません: {field}",
            code=cls.MISSING_FIELD,
            suggestions=[
                f"{field}を入力してください"
            ],
            details={"field": field}
        )


class FileOperationError(ApplicationError):
    """
    ファイル操作エラー

    アップロード・保存・読み込みエラー
    """

    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    WRITE_ERROR = "WRITE_ERROR"
    READ_ERROR = "READ_ERROR"

    @classmethod
    def path_traversal(cls) -> "FileOperationError":
        """パストラバーサル検出"""
        return cls(
            message="不正なファイルパスが検出されました",
            code=cls.PATH_TRAVERSAL,
            suggestions=[
                "ファイルパスを確認してください"
            ]
        )

    @classmethod
    def file_not_found(cls, path: str) -> "FileOperationError":
        """ファイル未発見"""
        return cls(
            message=f"ファイルが見つかりません: {path}",
            code=cls.FILE_NOT_FOUND,
            suggestions=[
                "ファイルパスを確認してください"
            ],
            details={"path": path}
        )


class TaxInspectionError(ApplicationError):
    """
    税務調査エラー

    税務チェック処理中のエラー
    """

    NO_DATA = "NO_DATA"
    INVALID_DEAL = "INVALID_DEAL"
    CALCULATION_ERROR = "CALCULATION_ERROR"

    @classmethod
    def no_data(cls) -> "TaxInspectionError":
        """データなし"""
        return cls(
            message="チェック対象のデータがありません",
            code=cls.NO_DATA,
            suggestions=[
                "freeeからデータを取得してください",
                "日付範囲を確認してください"
            ]
        )

    @classmethod
    def invalid_deal(cls, deal_id: int, reason: str) -> "TaxInspectionError":
        """不正な取引データ"""
        return cls(
            message=f"取引データが不正です (ID: {deal_id}): {reason}",
            code=cls.INVALID_DEAL,
            details={"deal_id": deal_id, "reason": reason}
        )
