# freee API連携ガイド

> **AI向け: このファイルを最初に読むこと**
>
> freee APIからデータを取得する際は、このガイドの「AI向けデータ取得」セクションを参照。
> - **server.py起動中**: REST API経由（セクション1.2）
> - **確実性重視**: Python直接（セクション1.1）

**バージョン**: 1.3.1
**最終更新**: 2025-12-04

---

## ⚠️ 最重要: freee API接続は必ずこの手順で

**mcp_config.json の company_id を信用するな。必ず毎回 `/api/1/companies` から始めろ。**

### 正しい接続手順（この順序を絶対に守れ）

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: /api/1/companies を呼ぶ（必須・省略不可）            │
│         ↓                                                   │
│ Step 2: レスポンスから正しい company_id を特定               │
│         ↓                                                   │
│ Step 3: その company_id で他のAPIを呼ぶ                      │
└─────────────────────────────────────────────────────────────┘
```

### Step 1: まず companies API を呼ぶ（絶対に省略するな）

```bash
curl -H "Authorization: Bearer {TOKEN}" "https://api.freee.co.jp/api/1/companies"
```

**このステップの目的:**
1. トークンが有効かどうか確認
2. 使用可能な company_id 一覧を取得

**結果の判断:**
- **401** → トークン期限切れ。ユーザーに再取得を依頼。
- **200** → トークンは有効。Step 2へ。

### Step 2: 正しい company_id を特定（⚠️ 超重要）

```json
// レスポンス例
{
  "companies": [
    {"id": 1234567, "name": "開発用テスト事業所", "role": "admin"},
    {"id": 9876543, "name": "株式会社〇〇", "role": "admin"}
  ]
}
```

**🚨 絶対ルール: 「開発用テスト事業所」は選ぶな！**

freeeでアプリ連携すると「開発用テスト事業所」が自動作成される。
これはダミーデータしか入っていない。ユーザーが税務チェックしたいのは
**本番の事業所（個人事業 or 法人）** である。

**選択の優先順位:**
```
1. _INDEX.json の company_name と一致する事業所
2. 「株式会社〇〇」「〇〇事業」など実際の事業名
3. 上記で判断できない場合はユーザーに確認

❌ 選んではいけない:
   - 「開発用テスト事業所」
   - 「テスト」「サンプル」「demo」を含む名前
```

**選択のコード例:**
```python
companies = res.json()['companies']

# テスト事業所を除外して本番事業所を抽出
real_companies = [c for c in companies
                  if '開発用' not in c['name']
                  and 'テスト' not in c['name']
                  and 'demo' not in c['name'].lower()]

if len(real_companies) == 1:
    company_id = real_companies[0]['id']
    print(f"✅ 事業所: {real_companies[0]['name']}")
elif len(real_companies) > 1:
    # 🚨 必ずユーザーに確認（勝手に選ぶな！）
    print("複数の事業所が見つかりました。どちらに接続しますか？")
    for i, c in enumerate(real_companies, 1):
        print(f"  {i}. {c['name']}")
    # ユーザーの回答を待ってから接続
else:
    print("⚠️ 本番事業所が見つかりません")
```

**🚨 複数事業所がある場合は必ず聞け（勝手に選ぶな）**

```
よくあるケース:
- 個人事業CLAN + 株式会社CLAN（両方持っている）
- 複数の法人を経営
- 顧問先の事業所も見える

❌ ダメ: 勝手に「株式会社CLAN」を選ぶ
✅ 正解: 「どちらに接続しますか？」と聞く

1秒で聞ける質問を省略して、後で修正作業が発生するのは最悪。
```

### Step 3: その company_id で他のAPIを呼ぶ

```bash
curl -H "Authorization: Bearer {TOKEN}" "https://api.freee.co.jp/api/1/deals?company_id=9876543"
```

### ❌ やってはいけない手順（これで失敗する）

```
┌─────────────────────────────────────────────────────────────┐
│ ❌ mcp_config.json から company_id を読む                    │
│         ↓                                                   │
│ ❌ いきなり /api/1/deals を呼ぶ                              │
│         ↓                                                   │
│ ❌ 401エラー → 「トークン期限切れ」と判断                    │
└─────────────────────────────────────────────────────────────┘
```

**なぜダメか:**
- mcp_config.json の company_id は **過去の判断の結果** であり、現在も正しいとは限らない
- トークン再取得時に紐づく事業所が変わることがある
- 401エラーの原因は「トークン切れ」だけではない

### 401エラーの原因は3つある

| 原因 | 説明 | 診断方法 |
|------|------|----------|
| 1. トークン期限切れ | 6時間で失効 | `/api/1/companies` が401 |
| 2. **company_id不一致** | トークンに紐づいていないID | `/api/1/companies` は200、他が401 |
| 3. スコープ不足 | 必要な権限がない | 特定APIだけ401 |

**→ だから最初に `/api/1/companies` を呼べば、原因1と2を一発で判別できる**

---

## 目次

1. [AI向けデータ取得（最重要）](#1-ai向けデータ取得最重要)
2. [トークン取得](#2-トークン取得)
3. [API技術仕様](#3-api技術仕様)
4. [トラブルシューティング](#4-トラブルシューティング)

---

## 1. AI向けデータ取得（最重要）

### 1.1 推奨方法: Pythonで直接freee_client.pyを使用

```python
import json
import sys
sys.path.insert(0, '.')
from core.freee_client import FreeeClient

# mcp_config.jsonからトークンとcompany_id取得
with open('data/mcp_config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
token = config['token']
company_id = config.get('company_id')

# company_idが未設定の場合、自動取得を試みる
if not company_id:
    temp_client = FreeeClient(access_token=token, company_id=0)
    companies = temp_client.get_companies()
    if companies:
        company_id = companies[0]['id']

# freeeクライアント初期化
client = FreeeClient(access_token=token, company_id=company_id)

# 取引データ取得
deals = client.get_deals(start_date='2024-05-01', end_date='2025-12-03')
print(f'取得件数: {len(deals)}件')
```

**実行コマンド（Windows）:**
```bash
cd C:\Users\atara\Desktop\keiri-marunage-chan
python -X utf8 -c "上記コード"
```

### 1.2 REST API経由でのデータ取得

server.pyを起動している場合、REST APIからもデータ取得可能：

```bash
# 取引データ取得
curl "http://localhost:5000/api/freee/deals?start_date=2024-05-01&end_date=2025-12-03"

# 監査結果エクスポート（CSV）
curl "http://localhost:5000/api/audit/export?format=csv" -o audit_report.csv

# 監査結果エクスポート（JSON）
curl "http://localhost:5000/api/audit/export?format=json" -o audit_report.json
```

**注意**: WebUIでトークンを入力しておく必要があります（事業所IDは自動設定されます）。

---

## 2. トークン取得

### 手順

1. 以下のURLにアクセス：
   https://app.secure.freee.co.jp/developers/start_guides/new_company

2. 画面の指示に従ってアクセストークンを取得

3. 権限設定で以下を有効に：
   - 事業所の参照
   - 取引の参照
   - 取引の更新（任意）
   - 勘定科目の参照
   - 税区分の参照

**注意:**
- アクセストークンは**6時間で期限切れ**

---

## 3. API技術仕様

### 3.1 認証URL

```python
AUTH_URL = "https://accounts.secure.freee.co.jp/public_api/authorize"
TOKEN_URL = "https://accounts.secure.freee.co.jp/public_api/token"
API_BASE = "https://api.freee.co.jp/api/1"
```

### 3.2 主要エンドポイント

- `GET /api/1/companies` : 事業所一覧
- `GET /api/1/deals` : 取引一覧
- `PUT /api/1/deals/{id}` : 取引更新

### 3.3 レート制限

- 通常API: 3,000リクエスト/5分

---

## 4. トラブルシューティング

### 4.1 401 Unauthorized エラー

**⚠️ 冒頭の「最重要」セクションを必ず読むこと**

401エラーが発生した場合の診断フロー：

```
401発生
    ↓
/api/1/companies を呼び出す
    ↓
┌─ 401 → トークン期限切れ → 再取得が必要
│
└─ 200 → トークンは有効
         ↓
    company_id一覧を確認
         ↓
    使用中のcompany_idが一覧に含まれているか？
         ↓
    ┌─ 含まれていない → mcp_config.jsonのcompany_idが間違っている
    │                   → 一覧にあるIDに修正
    │
    └─ 含まれている → スコープ不足の可能性
                      → トークン再取得時に必要な権限を付与
```

### 4.2 その他のエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| expired_access_token | トークン期限切れ（6時間） | トークン再取得 |
| rate limit exceeded | API上限超過 | 10分待機 |
| 404 Not Found | エンドポイント誤り or server.py未起動 | URLを確認 / server.py起動 |
| 403 Forbidden | スコープ不足 | 必要な権限でトークン再取得 |

### 4.3 AIが絶対にやってはいけないこと

1. **401エラーを見て即「トークン期限切れ」と判断する**
   - 必ず `/api/1/companies` で確認してから判断すること

2. **mcp_config.json の company_id を無条件に信用する**
   - `/api/1/companies` のレスポンスと照合すること

3. **ユーザーに「トークンを再取得してください」と安易に言う**
   - 本当にトークンが原因か確認してから言うこと

### 4.4 トークン期限切れ時のアナウンス（必須）

`/api/1/companies` で401が返った場合、以下の文言でユーザーにアナウンスすること：

```
トークン切れです。
初回申請時に届いたメールからアクセストークンを再取得してください。

再取得したらローカルサーバーに入れ替えて、「入れ替えた」と言ってください。
```

**重要:**
- URLは省略せず、そのまま表示すること
- ユーザーが「入れ替えた」と言うまで待機すること
- 入れ替え後は再度 `/api/1/companies` で確認してから作業を再開すること

---

### フォーク時のお願い

改変・再配布する場合は、以下のクレジット表記を記載してください：

```
Original work: バーチャル税務調査～経理丸投げちゃん～
https://github.com/CLANBIZ/keiri-marunage-chan
Copyright (c) 2025 株式会社CLAN (https://clanbiz.net/keiri-marunage-chan-LP/)
```

