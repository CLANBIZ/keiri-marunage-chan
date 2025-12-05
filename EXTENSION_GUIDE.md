# 拡張ガイド（開発者・税理士・自治体向け）

> **このドキュメントの目的**
>
> 「バーチャル税務調査～経理丸投げちゃん～」を別の会計ソフトや独自の税務ルールに対応させたい
> 開発者・税理士・自治体担当者向けのガイドです。

**バージョン**: 1.0.0
**最終更新**: 2025-12-04

---

## 目次

1. [アーキテクチャ概要](#1-アーキテクチャ概要)
2. [REST API仕様](#2-rest-api仕様)
3. [別の会計ソフトに対応する](#3-別の会計ソフトに対応する)
4. [独自の税務ルールを追加する](#4-独自の税務ルールを追加する)
5. [多言語・多地域対応](#5-多言語多地域対応)
6. [自治体・政府向けカスタマイズ](#6-自治体政府向けカスタマイズ)
7. [税理士事務所向けカスタマイズ](#7-税理士事務所向けカスタマイズ)
8. [大規模データ対応](#8-大規模データ対応自治体大企業向け)
9. [MCP対応](#9-mcpmodel-context-protocol対応)
10. [コントリビューション](#10-コントリビューション)
11. [International Adaptation Guide](#11-international-adaptation-guide-english)

---

## 1. アーキテクチャ概要

### 現在の構成

```
┌─────────────────────────────────────────────────────────────┐
│                        WebUI (index.html)                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      server.py (Flask)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────┬─────────────┬─────────────┬───────────────────┐
│ freee_client│ bank_parser │tax_inspector│ document_scanner  │
│   .py       │    .py      │    .py      │      .py          │
│ (会計API)   │ (銀行CSV)   │ (税務チェック)│ (書類解析)        │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

### 拡張ポイント

| コンポーネント | 拡張方法 |
|--------------|---------|
| freee_client.py | 別の会計ソフト用クライアントに置き換え |
| tax_inspector.py | 税務ルールを追加・変更 |
| bank_parser.py | 銀行CSVフォーマットを追加 |
| AI_GUIDE.md, CASE_STUDY.md | チェック項目・発見パターンを追加 |

---

## 2. REST API仕様

このツールが提供するREST APIエンドポイントの一覧です。

### 2.1 基本情報

- **ベースURL**: `http://localhost:5000`
- **認証**: freee APIトークンをリクエストボディまたはセッションで管理
- **レスポンス形式**: JSON

### 2.2 エンドポイント一覧

#### ファイルアップロード

```
POST /api/upload/bank-csv
Content-Type: multipart/form-data

Request:
  files: CSVファイル（複数可）

Response:
{
  "success": true,
  "files": [
    {"name": "bank_202501.csv", "size": 12345, "rows": 150}
  ]
}

Error:
{
  "success": false,
  "error": "ファイル形式が不正です"
}
```

```
POST /api/upload/receipts
Content-Type: multipart/form-data

Request:
  files: PDF/画像ファイル（複数可、1ファイル50MB以下）

Response:
{
  "success": true,
  "files": [
    {"name": "receipt_001.pdf", "size": 54321}
  ]
}
```

#### freee連携

```
POST /api/freee/auth
Content-Type: application/json

Request:
{
  "access_token": "YOUR_FREEE_ACCESS_TOKEN"
}

Response:
{
  "success": true,
  "company": {"id": 123456, "name": "株式会社サンプル"}
}
```

```
GET /api/freee/deals?start_date=2025-01-01&end_date=2025-12-31

Response:
{
  "success": true,
  "deals": [
    {
      "id": 12345,
      "issue_date": "2025-01-15",
      "type": "expense",
      "amount": 10000,
      "partner_name": "Amazon",
      "details": [...]
    }
  ],
  "total": 150
}
```

```
GET /api/freee/account-items

Response:
{
  "success": true,
  "account_items": [
    {"id": 1, "name": "売上高", "category": "収益"},
    {"id": 101, "name": "旅費交通費", "category": "費用"}
  ]
}
```

#### ファイル管理

```
GET /api/files

Response:
{
  "success": true,
  "bank_csv": ["bank_202501.csv", "bank_202502.csv"],
  "receipts": ["receipt_001.pdf", "receipt_002.jpg"]
}
```

```
DELETE /api/files/{filename}

Response:
{
  "success": true,
  "deleted": "bank_202501.csv"
}
```

### 2.3 エラーレスポンス

すべてのエラーは以下の形式で返されます：

```json
{
  "success": false,
  "error": "エラーメッセージ",
  "code": "ERROR_CODE"
}
```

| コード | 説明 |
|-------|------|
| `TOKEN_EXPIRED` | freeeトークンが期限切れ |
| `TOKEN_INVALID` | freeeトークンが無効 |
| `FILE_TOO_LARGE` | ファイルサイズが50MBを超過 |
| `INVALID_FORMAT` | ファイル形式が不正 |
| `FREEE_API_ERROR` | freee API側のエラー |

---

## 3. 別の会計ソフトに対応する

### 3.1 主要会計ソフトのAPI対応状況（2025年1月時点）

| ソフト名 | API | 料金 | 認証方式 | 備考 |
|---------|-----|------|---------|------|
| **freee会計** | ✅ 公開 | 無料 | OAuth2.0 | 本ツール対応済み |
| **マネーフォワード クラウド** | ✅ 公開 | 無料 | OAuth2.0 | [開発者サイト](https://developer.moneyforward.com/) |
| **弥生会計オンライン** | ✅ 公開 | 無料 | OAuth2.0 | [Misoca API](https://developer.yayoi-kk.co.jp/) 経由 |
| **弥生会計（デスクトップ版）** | ❌ なし | - | - | CSV/仕訳日記帳エクスポートで対応 |
| **勘定奉行クラウド** | ✅ 公開 | 要問合せ | OAuth2.0 | 法人契約が必要 |
| **PCAクラウド** | ✅ 公開 | 要問合せ | API Key | 法人契約が必要 |
| **TKC** | ❌ なし | - | - | CSV出力のみ |
| **ソリマチ会計王** | ❌ なし | - | - | CSV出力のみ |

**対応方法の判断:**
- API公開 → API連携クライアントを作成
- APIなし → CSVエクスポート方式で対応

> **Note:** API仕様は変更されることがあります。実装前に各社の開発者ドキュメントで最新情報を確認してください。

### 3.2 新しい会計クライアントの作成

**Step 1: 基本構造を作成**

```python
# core/your_accounting_client.py

class YourAccountingClient:
    """あなたの会計ソフト用クライアント"""

    def __init__(self, credentials):
        """
        認証情報で初期化

        credentials: dict - API キー、トークン、ユーザー名/パスワードなど
        """
        self.credentials = credentials
        self.base_url = "https://api.your-accounting.com/v1"

    def get_companies(self):
        """
        事業所一覧を取得

        Returns:
            list[dict]: [{"id": "xxx", "name": "会社名"}, ...]
        """
        # 実装
        pass

    def get_deals(self, start_date, end_date, company_id=None):
        """
        取引データを取得

        Args:
            start_date: str - 開始日 (YYYY-MM-DD)
            end_date: str - 終了日 (YYYY-MM-DD)
            company_id: str - 事業所ID（任意）

        Returns:
            list[dict]: 標準化された取引データ
        """
        # 実装
        pass

    def get_account_items(self, company_id=None):
        """
        勘定科目マスタを取得

        Returns:
            list[dict]: [{"id": 1, "name": "売上高", "category": "収益"}, ...]
        """
        # 実装
        pass
```

**Step 2: 標準データフォーマットに変換**

tax_inspector.py が理解できるフォーマットに変換：

```python
# 標準取引データフォーマット
{
    "id": "取引ID",
    "issue_date": "2025-01-15",  # YYYY-MM-DD
    "type": "expense",  # income, expense, transfer
    "amount": 10000,
    "partner_name": "取引先名",
    "description": "摘要",
    "details": [
        {
            "account_item_id": 123,
            "account_item_name": "旅費交通費",
            "amount": 10000,
            "tax_code": 136,  # 税区分コード
            "tax_code_name": "課対仕入10%",
            "description": "明細摘要"
        }
    ]
}
```

**Step 3: server.py で切り替え可能にする**

```python
# server.py

# 会計ソフトの選択（環境変数または設定ファイル）
ACCOUNTING_SOFTWARE = os.environ.get('ACCOUNTING_SOFTWARE', 'freee')

def get_accounting_client(credentials):
    if ACCOUNTING_SOFTWARE == 'freee':
        from core.freee_client import FreeeClient
        return FreeeClient(**credentials)
    elif ACCOUNTING_SOFTWARE == 'moneyforward':
        from core.moneyforward_client import MoneyForwardClient
        return MoneyForwardClient(**credentials)
    elif ACCOUNTING_SOFTWARE == 'yayoi':
        from core.yayoi_client import YayoiClient
        return YayoiClient(**credentials)
    else:
        raise ValueError(f"Unknown accounting software: {ACCOUNTING_SOFTWARE}")
```

### 3.3 APIがない会計ソフトの場合

**CSVエクスポート方式:**

```python
# core/csv_accounting_client.py

class CSVAccountingClient:
    """CSVエクスポートに対応した汎用クライアント"""

    def __init__(self, csv_format='generic'):
        """
        csv_format: 'yayoi', 'obic', 'pca', 'generic' など
        """
        self.csv_format = csv_format

    def load_from_csv(self, file_path):
        """CSVファイルから取引データを読み込む"""
        if self.csv_format == 'yayoi':
            return self._parse_yayoi_csv(file_path)
        elif self.csv_format == 'obic':
            return self._parse_obic_csv(file_path)
        else:
            return self._parse_generic_csv(file_path)

    def _parse_yayoi_csv(self, file_path):
        """弥生会計のCSVフォーマットを解析"""
        # 弥生会計の仕訳日記帳CSVフォーマット
        # 日付, 伝票No, 借方科目, 借方金額, 貸方科目, 貸方金額, 摘要
        pass
```

---

## 4. 独自の税務ルールを追加する

### 4.1 tax_inspector.py の構造

```python
# core/tax_inspector.py

class TaxInspector:
    def __init__(self, rules=None):
        """
        rules: 税務ルールの辞書（Noneなら日本のデフォルトルール）
        """
        self.rules = rules or self.get_default_rules()

    def get_default_rules(self):
        """日本の税務ルール（デフォルト）"""
        return {
            'tax_codes': {
                21: {'name': '課税売上10%', 'type': 'sales'},
                136: {'name': '課対仕入10%', 'type': 'purchase'},
                0: {'name': '対象外', 'type': 'exempt'},
                2: {'name': '非課税', 'type': 'non_taxable'},
            },
            'expense_accounts': ['旅費交通費', '支払手数料', '消耗品費', ...],
            'officer_compensation_rules': {
                'fixed_monthly': True,  # 定期同額給与
                'change_allowed_months': 3,  # 期首から変更可能な月数
            },
            'entertainment_expense_limit': 8000000,  # 交際費限度額（円）
            'withholding_tax_rate': 0.1021,  # 源泉徴収税率
        }
```

### 4.2 独自ルールの追加例

**例1: 海外子会社向け（米国税制）**

```python
# config/tax_rules_us.py

US_TAX_RULES = {
    'tax_codes': {
        1: {'name': 'Taxable Sales', 'type': 'sales'},
        2: {'name': 'Exempt', 'type': 'exempt'},
        3: {'name': 'Out of Scope', 'type': 'out_of_scope'},
    },
    'expense_accounts': ['Travel', 'Office Supplies', 'Professional Fees', ...],
    'depreciation_rules': {
        'MACRS': True,
        'Section_179_limit': 1160000,  # 2023年
    },
    'withholding_tax_rate': 0.24,  # 連邦税率
}
```

**例2: 自治体向け（公会計）**

```python
# config/tax_rules_public.py

PUBLIC_ACCOUNTING_RULES = {
    'account_categories': {
        'assets': ['流動資産', '固定資産', '繰延資産'],
        'liabilities': ['流動負債', '固定負債'],
        'net_assets': ['純資産'],
        'revenues': ['税収等', '国県等補助金', '使用料及び手数料', ...],
        'expenses': ['人件費', '物件費', '維持補修費', '扶助費', ...],
    },
    'budget_check': True,  # 予算対比チェック
    'fiscal_year_start': 4,  # 4月開始
    'double_entry': True,  # 複式簿記
}
```

### 4.3 チェック項目の追加

**AI_GUIDE.md に追記:**

```markdown
## カスタムチェック項目

### 公会計向け追加項目

| # | 項目 | 重要度 | 確認ポイント |
|---|------|--------|-------------|
| 21 | 予算執行率 | ★★★ | 各費目の執行率が適正か |
| 22 | 財源内訳 | ★★★ | 一般財源/特定財源の区分が正しいか |
| 23 | 決算統計分類 | ★★☆ | 地方財政状況調査の分類に準拠しているか |
```

---

## 5. 多言語・多地域対応

### 5.1 翻訳ファイルの構造

```
locales/
├── ja.json    # 日本語（デフォルト）
├── en.json    # English
├── zh.json    # 中文
└── ko.json    # 한국어
```

**locales/ja.json:**
```json
{
  "app_name": "バーチャル税務調査～経理丸投げちゃん～",
  "tax_check": "税務チェック",
  "upload_csv": "銀行CSVをアップロード",
  "errors": {
    "token_expired": "トークンが期限切れです。再取得してください。",
    "no_transactions": "取引データが見つかりません。"
  },
  "tax_codes": {
    "21": "課税売上10%",
    "136": "課対仕入10%"
  }
}
```

**locales/en.json:**
```json
{
  "app_name": "Accounting Assistant",
  "tax_check": "Tax Review",
  "upload_csv": "Upload Bank CSV",
  "errors": {
    "token_expired": "Token has expired. Please refresh.",
    "no_transactions": "No transactions found."
  },
  "tax_codes": {
    "21": "Taxable Sales 10%",
    "136": "Taxable Purchase 10%"
  }
}
```

### 5.2 地域設定

```python
# config/regions.py

REGIONS = {
    'JP': {
        'name': 'Japan',
        'currency': 'JPY',
        'date_format': 'YYYY年MM月DD日',
        'fiscal_year_start': 4,  # 4月
        'tax_rules': 'japan_corporate',
        'locale': 'ja',
    },
    'US': {
        'name': 'United States',
        'currency': 'USD',
        'date_format': 'MM/DD/YYYY',
        'fiscal_year_start': 1,  # 1月（会社による）
        'tax_rules': 'us_federal',
        'locale': 'en',
    },
    'SG': {
        'name': 'Singapore',
        'currency': 'SGD',
        'date_format': 'DD/MM/YYYY',
        'fiscal_year_start': 1,
        'tax_rules': 'singapore_corporate',
        'locale': 'en',
    },
}
```

---

## 6. 自治体・政府向けカスタマイズ

### 6.1 公会計対応

**統一的な基準による地方公会計対応:**

```python
# core/public_accounting_inspector.py

class PublicAccountingInspector:
    """地方公会計向け検査エンジン"""

    def __init__(self):
        self.check_items = [
            '財務書類4表の整合性',
            '固定資産台帳との照合',
            '予算・決算の対比',
            '附属明細書の整合性',
            '注記の妥当性',
        ]

    def check_financial_statements(self, data):
        """財務書類4表（貸借対照表、行政コスト計算書、等）の検査"""
        pass

    def check_fixed_assets(self, data):
        """固定資産台帳との照合"""
        pass
```

### 6.2 予算管理機能

```python
# 予算執行チェック
def check_budget_execution(self, budget_data, actual_data):
    """
    予算と実績の対比チェック

    Returns:
        list[dict]: 予算超過・大幅未消化の項目リスト
    """
    warnings = []
    for category, budget in budget_data.items():
        actual = actual_data.get(category, 0)
        execution_rate = actual / budget if budget > 0 else 0

        if execution_rate > 1.0:
            warnings.append({
                'category': category,
                'type': '予算超過',
                'budget': budget,
                'actual': actual,
                'rate': execution_rate
            })
        elif execution_rate < 0.5:
            warnings.append({
                'category': category,
                'type': '低執行率',
                'budget': budget,
                'actual': actual,
                'rate': execution_rate
            })
    return warnings
```

### 6.3 監査対応機能

```python
# 監査証跡の出力
def generate_audit_trail(self, checks_performed):
    """
    監査人向けの検査証跡を出力

    Returns:
        dict: 監査証跡データ
    """
    return {
        'audit_date': datetime.now().isoformat(),
        'tool_version': '1.0.0',
        'checks_performed': checks_performed,
        'data_sources': [...],
        'methodology': '...',
    }
```

---

## 7. 税理士事務所向けカスタマイズ

### 7.1 複数クライアント管理

```python
# 複数の顧問先を管理
clients = {
    'client_001': {
        'name': '株式会社A',
        'accounting_software': 'freee',
        'credentials': {...},
        'fiscal_year_end': 3,  # 3月決算
        'industry': 'IT',
    },
    'client_002': {
        'name': '有限会社B',
        'accounting_software': 'yayoi',
        'csv_path': '/path/to/exported.csv',
        'fiscal_year_end': 12,  # 12月決算
        'industry': 'retail',
    },
}
```

### 7.2 業種別チェック項目

```python
# 業種別の追加チェック項目
INDUSTRY_CHECKS = {
    'construction': [
        '工事進行基準の適用',
        '外注費と人件費の区分',
        '工事損失引当金',
    ],
    'restaurant': [
        '現金取引の記帳',
        '軽減税率の適用',
        '棚卸資産（食材）',
    ],
    'real_estate': [
        '不動産所得の区分',
        '減価償却の方法',
        '借入金利息の按分',
    ],
    'medical': [
        '社会保険診療報酬',
        '自由診療の区分',
        '医療機器の減価償却',
    ],
}
```

### 7.3 レポートテンプレート

```markdown
# 月次チェック報告書

**顧問先**: {{client_name}}
**対象期間**: {{period}}
**作成日**: {{date}}

## サマリー

- 確認取引数: {{total_transactions}}件
- 要確認事項: {{warnings}}件
- 要修正事項: {{errors}}件

## 詳細

### 要修正事項
{{#each errors}}
- {{date}}: {{description}} ({{amount}}円)
{{/each}}

### 要確認事項
{{#each warnings}}
- {{date}}: {{description}}
{{/each}}

## 次回への引き継ぎ

{{notes}}
```

---

## 8. 大規模データ対応（自治体・大企業向け）

### 8.1 現在の制限値

| 項目 | 現在の制限 | 設定箇所 |
|------|-----------|----------|
| 1ファイルサイズ | 50MB | `server.py` LINE 43: `MAX_FILE_SIZE` |
| 1リクエストのファイル数 | 100件 | `server.py` LINE 44: `MAX_FILES_PER_REQUEST` |
| 1リクエスト合計サイズ | 5GB | 50MB × 100件 |
| freee API取得 | 3,000リクエスト/5分 | freee側の制限 |
| 取引データ | メモリに全件読み込み | ページネーション未実装 |

### 8.2 大規模対応が必要な目安

| 規模 | 現状で対応可能か |
|------|-----------------|
| 年間取引 1,000件未満 | ✅ 問題なし |
| 年間取引 1,000〜10,000件 | ⚠️ 処理に時間がかかる可能性 |
| 年間取引 10,000件以上 | ❌ 改修が必要 |
| 証憑ファイル 100件未満 | ✅ 問題なし |
| 証憑ファイル 100〜1,000件 | ⚠️ 複数回に分けてアップロード |
| 証憑ファイル 1,000件以上 | ❌ 改修が必要 |

### 8.3 大規模対応の改修方法

**AIエージェントに以下の指示をしてください：**

```
このツールを大規模データ（年間取引10万件以上、証憑ファイル数千件）に
対応させたいです。

以下を検索してください：
- "Flask large file upload streaming"
- "Python pagination large dataset"
- "SQLite vs PostgreSQL for large data"
- "Python memory efficient CSV processing"

以下の改修を行ってください：

1. 制限値の引き上げ（server.py）
   - MAX_FILE_SIZE: 50MB → 必要に応じて引き上げ
   - MAX_FILES_PER_REQUEST: 100 → 必要に応じて引き上げ
   - ただしメモリ使用量に注意

2. ページネーション対応（freee API）
   - 取引データを一括取得ではなく分割取得
   - offset/limit パラメータの活用
   - プログレス表示の追加

3. ストリーミングアップロード
   - 大きなファイルをチャンク単位で処理
   - メモリ使用量の削減

4. データベース導入（オプション）
   - ファイルベース（JSON）→ SQLite または PostgreSQL
   - 大量データの検索・集計が高速に

5. バッチ処理対応
   - 全件一括処理 → 分割バッチ処理
   - 途中経過の保存と再開機能

6. 非同期処理（オプション）
   - 長時間処理をバックグラウンドで実行
   - 処理状況をポーリングで確認
```

### 8.4 具体的な改修ポイント

#### 制限値の変更

```python
# server.py を編集

# 現在
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES_PER_REQUEST = 100

# 大規模対応（例）
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MAX_FILES_PER_REQUEST = 1000
```

#### ページネーション対応

```python
# core/freee_client.py を編集

def get_deals_paginated(self, start_date, end_date, page_size=100):
    """
    取引データをページ単位で取得（大規模対応）

    Yields:
        list: 各ページの取引データ
    """
    offset = 0
    while True:
        params = {
            'company_id': self.company_id,
            'start_date': start_date,
            'end_date': end_date,
            'limit': page_size,
            'offset': offset
        }
        res = self._request('GET', '/deals', params=params)
        deals = res.get('deals', [])

        if not deals:
            break

        yield deals
        offset += page_size

        # レート制限対策
        time.sleep(0.1)
```

#### メモリ効率の良いCSV処理

```python
# core/bank_parser.py を編集

def parse_large_csv(file_path, chunk_size=10000):
    """
    大きなCSVをチャンク単位で処理

    Yields:
        DataFrame: 各チャンクのデータ
    """
    import pandas as pd

    for chunk in pd.read_csv(file_path, chunksize=chunk_size, encoding='utf-8'):
        yield chunk
```

### 8.5 自治体特有の考慮事項

| 考慮事項 | 対応方針 |
|---------|---------|
| 年度またぎのデータ | 年度ごとにフォルダ分け、年度指定で処理 |
| 複数部署のデータ | 部署コードでフィルタリング |
| 監査証跡 | 処理ログをファイル出力、改ざん防止 |
| セキュリティ要件 | 閉域網での運用、暗号化保存 |
| 可用性要件 | エラー時の再開機能、バックアップ |

### 8.6 パフォーマンス改善の優先順位

```
1. ページネーション対応（効果大・実装易）
   ↓
2. 制限値の引き上げ（効果中・実装易）
   ↓
3. ストリーミング処理（効果大・実装中）
   ↓
4. データベース導入（効果大・実装難）
   ↓
5. 非同期処理（効果中・実装難）
```

---

## 9. MCP（Model Context Protocol）対応

### 9.1 MCPとは

MCPは、AIエージェント（Claude、ChatGPT等）が外部ツールと連携するための標準プロトコルです。
MCP対応すると、AIエージェントがこのツールの機能を直接呼び出せるようになります。

### 9.2 現状の連携方式

現在このツールは以下の方式でAIエージェントと連携しています：

```
AIエージェント → REST API (localhost:5000) → server.py → freee API
                ↓
            data/mcp_config.json（設定共有）
            data/uploads/（ファイル共有）
```

### 9.3 正式なMCPサーバーを作成したい場合

**AIエージェントに以下の指示をしてください：**

```
このツールをMCP（Model Context Protocol）対応させたいです。

以下を検索してください：
- "Model Context Protocol specification"
- "MCP server implementation Python"
- "Claude MCP server example"
- "Anthropic MCP documentation"

調査結果に基づいて：
1. MCPサーバーの基本構造を作成（mcp_server.py）
2. 以下のツールをMCP経由で公開：
   - get_deals: freee取引データ取得
   - check_tax: 税務チェック実行
   - upload_file: ファイルアップロード
   - get_report: レポート生成
3. 既存のserver.pyのロジックを再利用
4. README.mdにMCP設定方法を追記

MCPサーバーの雛形を作成してください。
```

### 9.4 MCP対応のメリット

| 方式 | メリット | デメリット |
|------|---------|-----------|
| 現在（REST API） | シンプル、ブラウザUIあり | AIが直接呼べない |
| MCP対応 | AIが直接ツールを呼べる | 実装が複雑 |
| 両方併用 | 柔軟性が高い | メンテナンス増 |

---

## 10. コントリビューション

### 10.1 プルリクエストの送り方

```bash
# 1. フォーク
# GitHubで「Fork」ボタンをクリック

# 2. クローン
git clone https://github.com/your-username/keiri-marunage-chan.git

# 3. ブランチ作成
git checkout -b feature/add-moneyforward-support

# 4. 変更をコミット
git add .
git commit -m "Add MoneyForward accounting client"

# 5. プッシュ
git push origin feature/add-moneyforward-support

# 6. プルリクエスト作成
# GitHubでPull Requestを作成
```

### 10.2 新しい会計ソフト対応を追加する場合

**必要なファイル:**
1. `core/{software}_client.py` - APIクライアント
2. `docs/{software}_setup.md` - セットアップガイド
3. テストデータ（可能であれば）

**プルリクエストに含めてほしい情報:**
- 対応した会計ソフトの名前とバージョン
- APIドキュメントへのリンク
- テスト方法の説明

### 10.3 税務ルールを追加する場合

**必要なファイル:**
1. `config/tax_rules_{region}.py` - 税務ルール定義
2. `AI_GUIDE.md` への追記 - チェック項目
3. `CASE_STUDY.md` への追記 - 発見パターン

### 10.4 連絡先

- **GitHub Issues**: バグ報告・機能要望
- **Pull Requests**: コード貢献
- **Discussions**: 質問・議論

---

## 11. International Adaptation Guide (English)

> **For developers outside Japan**
>
> This section provides instructions for adapting this tool to your country's accounting standards and tax regulations.
> All instructions are designed to be given directly to Claude Code (recommended).

### 11.1 Quick Start: Adapt to Your Country

**After forking this repository, give this instruction to your AI agent:**

```
Read EXTENSION_GUIDE.md section 8 and help me adapt this accounting tool for [YOUR COUNTRY].
Search the web for "[YOUR COUNTRY] corporate tax rules [CURRENT YEAR]" and
"[YOUR COUNTRY] accounting standards" to understand the local requirements.
Then modify the following files:
1. core/tax_inspector.py - Add tax rules for [YOUR COUNTRY]
2. AI_GUIDE.md - Update check items for local regulations
3. CASE_STUDY.md - Add common issues specific to [YOUR COUNTRY]
4. locales/[lang].json - Translate UI strings
```

### 11.2 Country-Specific Search Instructions

> **Important:** Tax rules, rates, and regulations change frequently.
> Always instruct your AI agent to search for the **current year's** information.
> The search keywords below are starting points - your AI will find the latest details.

#### Template for Any Country

**Give this instruction to your AI agent:**

```
Help me adapt this accounting tool for [COUNTRY] businesses.

Step 1: Search for current tax rules
- "[COUNTRY] corporate tax rate [CURRENT YEAR]"
- "[COUNTRY] VAT/GST/sales tax rates [CURRENT YEAR]"
- "[COUNTRY] accounting standards requirements"
- "[COUNTRY] tax filing deadlines"
- "[COUNTRY] e-invoicing requirements"
- "[COUNTRY] payroll tax obligations"

Step 2: Search for local terminology
- "[COUNTRY] chart of accounts standard"
- "[COUNTRY] tax code categories"
- "[COUNTRY] deductible expenses list"

Step 3: Update the codebase
Based on your research, modify:
- core/tax_inspector.py (tax rules and rates)
- AI_GUIDE.md (check items for local compliance)
- CASE_STUDY.md (common local issues)

Always note the date of your research and the tax year the rules apply to.
```

---

#### Country-Specific Search Keywords

| Region | AI Agent Search Instructions |
|--------|------------------------------|
| 🇺🇸 **US** | `"IRS business tax [YEAR]"`, `"US GAAP requirements"`, `"state sales tax nexus"`, `"Form 1120 requirements"` |
| 🇬🇧 **UK** | `"HMRC corporate tax [YEAR]"`, `"UK VAT rates"`, `"Making Tax Digital"`, `"FRS 102 standards"` |
| 🇩🇪 **Germany** | `"Umsatzsteuer [YEAR]"`, `"Körperschaftsteuer"`, `"GoBD requirements"`, `"HGB accounting"` |
| 🇫🇷 **France** | `"TVA France [YEAR]"`, `"impôt sur les sociétés"`, `"Plan Comptable Général"`, `"Factur-X"` |
| 🇸🇬 **Singapore** | `"IRAS GST [YEAR]"`, `"Singapore corporate tax"`, `"SFRS standards"` |
| 🇦🇺 **Australia** | `"ATO GST [YEAR]"`, `"Australian corporate tax"`, `"Single Touch Payroll"`, `"AASB standards"` |
| 🇨🇦 **Canada** | `"CRA GST HST [YEAR]"`, `"Canadian corporate tax"`, `"ASPE standards"`, `"CPP EI rates"` |
| 🇮🇳 **India** | `"India GST rates [YEAR]"`, `"Indian corporate tax"`, `"Ind AS standards"`, `"TDS rates"` |
| 🇧🇷 **Brazil** | `"ICMS IPI PIS COFINS [YEAR]"`, `"IRPJ CSLL"`, `"Nota Fiscal Eletrônica"` |
| 🇰🇷 **Korea** | `"부가가치세 [YEAR]"`, `"법인세"`, `"K-IFRS"`, `"전자세금계산서"` |
| 🇨🇳 **China** | `"增值税 [YEAR]"`, `"企业所得税"`, `"中国会计准则"`, `"发票 requirements"` |
| 🇪🇺 **EU General** | `"EU VAT rules [YEAR]"`, `"IFRS standards"`, `"EU e-invoicing directive"` |
| 🌏 **Other** | `"[COUNTRY] corporate tax [YEAR]"`, `"[COUNTRY] VAT GST"`, `"[COUNTRY] accounting standards"` |

---

### 11.3 Universal Adaptation Checklist

**Give this to your AI agent for any country:**

```
Help me adapt this accounting tool for [COUNTRY]. Please:

1. RESEARCH (Web Search)
   - Search "[COUNTRY] corporate tax rates [YEAR]"
   - Search "[COUNTRY] VAT/GST/sales tax rules"
   - Search "[COUNTRY] accounting standards GAAP/IFRS"
   - Search "[COUNTRY] payroll tax requirements"
   - Search "[COUNTRY] e-invoicing requirements"

2. MODIFY TAX RULES (core/tax_inspector.py)
   - Update tax code mappings for [COUNTRY]
   - Add local tax rate calculations
   - Implement country-specific deduction rules

3. UPDATE CHECK ITEMS (AI_GUIDE.md)
   - Modify the 20-item checklist for local requirements
   - Add country-specific compliance checks
   - Update deadlines and thresholds

4. ADD CASE STUDIES (CASE_STUDY.md)
   - Add common mistakes specific to [COUNTRY]
   - Include local regulatory pitfalls
   - Add detection code for local issues

5. TRANSLATE (locales/[lang].json)
   - Translate all UI strings
   - Use local accounting terminology
   - Localize date/currency formats

6. UPDATE DOCUMENTATION
   - Translate README.md or create README.[lang].md
   - Update TROUBLESHOOTING.md for local software
   - Add local accounting software integration if available
```

### 11.4 Integrating with Your Accounting Software

**If you want to integrate with a specific accounting software, give this instruction to your AI agent:**

```
I want to integrate this tool with [SOFTWARE NAME] in [COUNTRY].
Please search for:
- "[SOFTWARE NAME] API documentation"
- "[SOFTWARE NAME] API pricing"
- "[SOFTWARE NAME] developer portal"
- "[SOFTWARE NAME] REST API authentication"

Then help me:
1. Determine if an API is available and what it costs
2. Create a new client file: core/[software]_client.py
3. Map their data format to our standard format
4. Handle authentication (OAuth, API key, etc.)

If no API is available, search for:
- "[SOFTWARE NAME] CSV export format"
- "[SOFTWARE NAME] data export options"

And help me create a CSV import adapter instead.
```

**Note:** API availability, pricing, and features change frequently. Always have your AI agent search for the latest information rather than relying on static documentation.

### 11.5 Contributing Your Country's Adaptation

**After successfully adapting for your country, consider contributing back:**

```bash
# 1. Fork and clone
git clone https://github.com/YOUR-USERNAME/keiri-marunage-chan.git

# 2. Create a branch for your country
git checkout -b feature/add-[COUNTRY]-support

# 3. Add your changes
# - core/tax_rules_[country].py
# - locales/[lang].json
# - docs/[COUNTRY]_GUIDE.md

# 4. Submit a Pull Request with:
# - Country name and tax year
# - List of supported tax rules
# - Any known limitations
# - Test cases if possible
```

---

## 質問・疑問があったら

このドキュメントに書いていないことや、より詳しく知りたいことがあれば、**AIエージェントに直接聞いてみてください**。

たいていのことはAIの方が詳しく答えられます。

**例:**
```
「マネーフォワードのAPIで取引データを取得する方法についてウェブサーチして」
「公会計の複式簿記対応について調べて」
「Pythonでページネーション処理を実装するベストプラクティスをウェブサーチして」
```

AIに「〇〇についてウェブサーチして」と伝えれば、最新情報を調べて教えてくれます。

---

*このドキュメントは開発者・税理士・自治体担当者向けです。*
*一般ユーザー向け情報はREADME.mdを参照してください。*

**Original work: バーチャル税務調査～経理丸投げちゃん～**
**https://github.com/CLANBIZ/keiri-marunage-chan**
**Copyright (c) 2025 株式会社CLAN (https://clanbiz.net/keiri-marunage-chan-LP/)**
**MIT License**
