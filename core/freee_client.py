"""
freee API クライアント
"""
import os
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Deal:
    """取引データ"""
    id: int
    issue_date: str
    type: str  # income or expense
    amount: int
    details: List[Dict]
    payments: List[Dict]


class FreeeClient:
    """freee会計APIクライアント"""

    BASE_URL = "https://api.freee.co.jp/api/1"

    def __init__(self, access_token: Optional[str] = None, company_id: Optional[int] = None):
        self.access_token = access_token or os.getenv("FREEE_ACCESS_TOKEN")
        self.company_id = company_id or int(os.getenv("FREEE_COMPANY_ID", "0"))

        if not self.access_token:
            raise ValueError("freeeアクセストークンが設定されていません")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Api-Version": "2020-06-15",
            "Content-Type": "application/json"
        }

    def get_companies(self) -> List[Dict]:
        """事業所一覧を取得"""
        url = f"{self.BASE_URL}/companies"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json().get("companies", [])

    def get_company(self) -> Dict:
        """事業所情報を取得"""
        if not self.company_id:
            raise ValueError("事業所IDが設定されていません")
        url = f"{self.BASE_URL}/companies/{self.company_id}"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json().get("company", {})

    def get_deals(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Deal]:
        """取引一覧を取得"""
        url = f"{self.BASE_URL}/deals"
        all_deals = []
        offset = 0

        while True:
            params = {
                "company_id": self.company_id,
                "limit": limit,
                "offset": offset
            }
            if start_date:
                params["start_issue_date"] = start_date
            if end_date:
                params["end_issue_date"] = end_date

            resp = requests.get(url, headers=self.headers, params=params)
            resp.raise_for_status()

            deals = resp.json().get("deals", [])
            if not deals:
                break

            for d in deals:
                all_deals.append(Deal(
                    id=d["id"],
                    issue_date=d["issue_date"],
                    type=d["type"],
                    amount=d.get("amount", 0),
                    details=d.get("details", []),
                    payments=d.get("payments", [])
                ))

            offset += limit
            if len(deals) < limit:
                break

        return all_deals

    def get_deal(self, deal_id: int) -> Optional[Deal]:
        """取引詳細を取得"""
        url = f"{self.BASE_URL}/deals/{deal_id}"
        params = {"company_id": self.company_id}
        resp = requests.get(url, headers=self.headers, params=params)

        if resp.status_code == 200:
            d = resp.json().get("deal", {})
            return Deal(
                id=d["id"],
                issue_date=d["issue_date"],
                type=d["type"],
                amount=d.get("amount", 0),
                details=d.get("details", []),
                payments=d.get("payments", [])
            )
        return None

    def update_deal(self, deal_id: int, data: Dict) -> bool:
        """取引を更新"""
        url = f"{self.BASE_URL}/deals/{deal_id}"
        data["company_id"] = self.company_id
        resp = requests.put(url, headers=self.headers, json=data)
        return resp.status_code == 200

    def delete_deal(self, deal_id: int) -> bool:
        """取引を削除"""
        url = f"{self.BASE_URL}/deals/{deal_id}"
        params = {"company_id": self.company_id}
        resp = requests.delete(url, headers=self.headers, params=params)
        return resp.status_code == 204

    def create_deal(self, data: Dict) -> Optional[int]:
        """取引を作成"""
        url = f"{self.BASE_URL}/deals"
        data["company_id"] = self.company_id
        resp = requests.post(url, headers=self.headers, json=data)

        if resp.status_code == 201:
            return resp.json().get("deal", {}).get("id")
        return None

    def get_account_items(self) -> Dict[int, str]:
        """勘定科目マスタを取得"""
        url = f"{self.BASE_URL}/account_items"
        params = {"company_id": self.company_id}
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()

        return {
            item["id"]: item["name"]
            for item in resp.json().get("account_items", [])
        }

    def get_tax_codes(self) -> Dict[int, str]:
        """税区分マスタを取得"""
        url = f"{self.BASE_URL}/taxes/codes"
        params = {"company_id": self.company_id}
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()

        return {
            item["code"]: item["name"]
            for item in resp.json().get("taxes", [])
        }
