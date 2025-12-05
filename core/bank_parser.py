"""
銀行CSV パーサー
各銀行のCSVフォーマットを統一形式に変換
"""
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import io


@dataclass
class Transaction:
    """統一取引フォーマット"""
    date: str
    description: str
    amount: int
    balance: Optional[int] = None
    type: str = ""  # income or expense
    raw_data: Dict = None


class BankCSVParser:
    """銀行CSVパーサー"""

    # 銀行別のCSV設定
    BANK_CONFIGS = {
        "楽天銀行": {
            "encoding": "shift_jis",
            "date_col": "取引日",
            "description_col": "摘要",
            "deposit_col": "入金額",
            "withdrawal_col": "出金額",
            "balance_col": "残高",
            "date_format": "%Y/%m/%d",
            "skiprows": 0,
        },
        "住信SBIネット銀行": {
            "encoding": "shift_jis",
            "date_col": "日付",
            "description_col": "内容",
            "deposit_col": "入金",
            "withdrawal_col": "出金",
            "balance_col": "残高",
            "date_format": "%Y/%m/%d",
            "skiprows": 0,
        },
        "三菱UFJ銀行": {
            "encoding": "shift_jis",
            "date_col": "日付",
            "description_col": "摘要",
            "deposit_col": "お預り金額",
            "withdrawal_col": "お引出し金額",
            "balance_col": "残高",
            "date_format": "%Y/%m/%d",
            "skiprows": 0,
        },
        "みずほ銀行": {
            "encoding": "shift_jis",
            "date_col": "日付",
            "description_col": "お取引内容",
            "deposit_col": "お預入金額",
            "withdrawal_col": "お引出金額",
            "balance_col": "残高",
            "date_format": "%Y年%m月%d日",
            "skiprows": 0,
        },
        "freee形式": {
            "encoding": "utf-8",
            "date_col": "発生日",
            "description_col": "詳細",
            "amount_col": "金額",
            "type_col": "収支区分",
            "date_format": "%Y-%m-%d",
            "skiprows": 0,
        },
    }

    def __init__(self, bank_type: str = "自動検出"):
        self.bank_type = bank_type

    def parse(self, file_content: bytes, filename: str = "") -> List[Transaction]:
        """CSVをパース"""
        # 自動検出
        if self.bank_type == "自動検出":
            self.bank_type = self._detect_bank_type(file_content, filename)

        if self.bank_type == "freee形式":
            return self._parse_freee(file_content)

        config = self.BANK_CONFIGS.get(self.bank_type)
        if not config:
            raise ValueError(f"未対応の銀行: {self.bank_type}")

        return self._parse_bank_csv(file_content, config)

    def _detect_bank_type(self, content: bytes, filename: str) -> str:
        """銀行タイプを自動検出"""
        # ファイル名から推測
        filename_lower = filename.lower()
        if "rakuten" in filename_lower or "楽天" in filename_lower:
            return "楽天銀行"
        if "sbi" in filename_lower:
            return "住信SBIネット銀行"
        if "mufg" in filename_lower or "三菱" in filename_lower:
            return "三菱UFJ銀行"
        if "mizuho" in filename_lower or "みずほ" in filename_lower:
            return "みずほ銀行"
        if "freee" in filename_lower:
            return "freee形式"

        # 内容から推測
        try:
            text = content.decode("utf-8")
            if "発生日" in text and "収支区分" in text:
                return "freee形式"
        except UnicodeDecodeError:
            pass

        try:
            text = content.decode("shift_jis")
            if "入金額" in text and "出金額" in text:
                return "楽天銀行"
        except UnicodeDecodeError:
            pass

        return "楽天銀行"  # デフォルト

    def _parse_bank_csv(self, content: bytes, config: Dict) -> List[Transaction]:
        """銀行CSVをパース"""
        try:
            df = pd.read_csv(
                io.BytesIO(content),
                encoding=config["encoding"],
                skiprows=config.get("skiprows", 0)
            )
        except Exception as e:
            raise ValueError(f"CSV読み込みエラー: {e}")

        transactions = []
        for _, row in df.iterrows():
            try:
                # 日付
                date_str = str(row[config["date_col"]])
                date = datetime.strptime(date_str, config["date_format"])

                # 金額
                deposit = self._parse_amount(row.get(config.get("deposit_col", ""), 0))
                withdrawal = self._parse_amount(row.get(config.get("withdrawal_col", ""), 0))

                if deposit > 0:
                    amount = deposit
                    tx_type = "income"
                else:
                    amount = withdrawal
                    tx_type = "expense"

                # 残高
                balance = self._parse_amount(row.get(config.get("balance_col", ""), 0))

                transactions.append(Transaction(
                    date=date.strftime("%Y-%m-%d"),
                    description=str(row[config["description_col"]]),
                    amount=amount,
                    balance=balance if balance else None,
                    type=tx_type,
                    raw_data=row.to_dict()
                ))
            except (KeyError, ValueError, TypeError) as e:
                # パースエラーの行はスキップ
                continue

        return transactions

    def _parse_freee(self, content: bytes) -> List[Transaction]:
        """freee形式をパース"""
        try:
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")

        transactions = []
        for _, row in df.iterrows():
            try:
                transactions.append(Transaction(
                    date=str(row["発生日"]),
                    description=str(row.get("詳細", "")),
                    amount=int(row["金額"]),
                    type="income" if row.get("収支区分") == "income" else "expense",
                    raw_data=row.to_dict()
                ))
            except (KeyError, ValueError, TypeError) as e:
                # パースエラーの行はスキップ
                continue

        return transactions

    def _parse_amount(self, value) -> int:
        """金額をパース"""
        if pd.isna(value):
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        # 文字列の場合、カンマや円を除去
        value = str(value).replace(",", "").replace("円", "").replace("¥", "").strip()
        if not value or value == "-":
            return 0
        return int(float(value))
