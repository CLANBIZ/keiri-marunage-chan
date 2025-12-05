"""
書類スキャナー
法人書類の存在チェックと内容分析
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Document:
    """書類情報"""
    filename: str
    filepath: str
    type: str
    category: str
    size: int
    content: Optional[bytes] = None


class DocumentScanner:
    """書類スキャナー"""

    # 書類カテゴリとキーワード
    DOCUMENT_PATTERNS = {
        "定款": ["定款", "articles", "incorporation"],
        "登記簿謄本": ["登記", "謄本", "履歴事項"],
        "株主総会議事録": ["株主総会", "議事録", "shareholders"],
        "取締役会議事録": ["取締役会", "役員会", "board"],
        "役員報酬規程": ["役員報酬", "報酬規程"],
        "旅費規程": ["旅費", "出張"],
        "経費規程": ["経費規程", "精算規程"],
        "社宅規程": ["社宅", "住宅"],
        "就業規則": ["就業規則", "就業規定"],
        "賃金規程": ["賃金", "給与規程"],
        "契約書": ["契約書", "契約", "agreement"],
        "決算書": ["決算", "貸借対照表", "損益計算書", "balance", "income"],
        "申告書": ["申告", "確定申告", "法人税"],
        "領収書": ["領収", "receipt"],
        "請求書": ["請求", "invoice"],
        "稟議書": ["稟議", "approval"],
        "出張報告書": ["出張報告", "travel report"],
    }

    # 必須書類リスト
    REQUIRED_DOCUMENTS = [
        "定款",
        "登記簿謄本",
        "株主総会議事録",
        "役員報酬規程",
        "決算書",
    ]

    # 推奨書類リスト
    RECOMMENDED_DOCUMENTS = [
        "取締役会議事録",
        "旅費規程",
        "経費規程",
        "就業規則",
        "賃金規程",
    ]

    def __init__(self):
        self.documents: List[Document] = []

    def scan_files(self, files: List[Dict]) -> List[Document]:
        """アップロードされたファイルをスキャン"""
        self.documents = []

        for file_info in files:
            filename = file_info.get("name", "")
            content = file_info.get("content", b"")
            size = file_info.get("size", len(content))

            doc_type = self._detect_document_type(filename)
            category = self._detect_category(filename)

            self.documents.append(Document(
                filename=filename,
                filepath=file_info.get("path", ""),
                type=doc_type,
                category=category,
                size=size,
                content=content if size < 10_000_000 else None  # 10MB以上は内容を保持しない
            ))

        return self.documents

    def scan_directory(self, directory: str) -> List[Document]:
        """ディレクトリをスキャン"""
        self.documents = []
        path = Path(directory)

        if not path.exists():
            raise ValueError(f"ディレクトリが存在しません: {directory}")

        for file_path in path.rglob("*"):
            if file_path.is_file():
                doc_type = self._detect_document_type(file_path.name)
                category = self._detect_category(file_path.name)

                self.documents.append(Document(
                    filename=file_path.name,
                    filepath=str(file_path),
                    type=doc_type,
                    category=category,
                    size=file_path.stat().st_size
                ))

        return self.documents

    def _detect_document_type(self, filename: str) -> str:
        """ファイルタイプを検出"""
        ext = Path(filename).suffix.lower()
        type_map = {
            ".pdf": "PDF",
            ".jpg": "画像",
            ".jpeg": "画像",
            ".png": "画像",
            ".xlsx": "Excel",
            ".xls": "Excel",
            ".docx": "Word",
            ".doc": "Word",
            ".csv": "CSV",
            ".txt": "テキスト",
        }
        return type_map.get(ext, "不明")

    def _detect_category(self, filename: str) -> str:
        """書類カテゴリを検出"""
        filename_lower = filename.lower()

        for category, patterns in self.DOCUMENT_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in filename_lower:
                    return category

        return "その他"

    def check_completeness(self) -> Dict:
        """書類の完備性をチェック"""
        found_categories = set(doc.category for doc in self.documents)

        # 必須書類チェック
        missing_required = []
        for doc_type in self.REQUIRED_DOCUMENTS:
            if doc_type not in found_categories:
                missing_required.append(doc_type)

        # 推奨書類チェック
        missing_recommended = []
        for doc_type in self.RECOMMENDED_DOCUMENTS:
            if doc_type not in found_categories:
                missing_recommended.append(doc_type)

        # スコア計算
        total_required = len(self.REQUIRED_DOCUMENTS)
        found_required = total_required - len(missing_required)
        score = int((found_required / total_required) * 100)

        return {
            "total_files": len(self.documents),
            "categories_found": list(found_categories),
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
            "completeness_score": score,
            "status": "OK" if not missing_required else "要対応"
        }

    def get_summary(self) -> Dict:
        """サマリーを取得"""
        completeness = self.check_completeness()

        # カテゴリ別集計
        category_counts = {}
        for doc in self.documents:
            category_counts[doc.category] = category_counts.get(doc.category, 0) + 1

        return {
            "total_files": len(self.documents),
            "by_category": category_counts,
            "completeness": completeness
        }
