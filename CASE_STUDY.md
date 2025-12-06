# よくある確認ポイントと対応例

> 経理チェックでよくある確認事項とその対応方法
>
> **注意**: 本ドキュメントは一般的なパターンを記載した参考情報です。
> 具体的な対応は税理士にご相談ください。
>
> **関連ドキュメント**: `AI_GUIDE.md`（チェック項目）、`FREEE_API_GUIDE.md`（API仕様）

**バージョン**: 1.3.1
**最終更新**: 2025-12-04

---

## 1. 税区分エラー

**→ AI_GUIDE.md #20「税区分設定」に対応**

### パターン

```
経費（旅費交通費、支払手数料など）が「課税売上10%」(21)で登録されている
```

### 検出方法

freee取引データで以下を検索：
```python
# 経費なのに課税売上になっているものを抽出
for deal in deals:
    for detail in deal['details']:
        account_name = detail['account_item_name']
        tax_code = detail['tax_code']
        # 経費系科目 かつ 課税売上(21)
        if account_name in ['旅費交通費', '支払手数料', '消耗品費', ...] and tax_code == 21:
            print(f"要確認: {deal['issue_date']} {account_name} {detail['amount']}円")
```

### 原因

- 銀行明細連携で自動登録される際のfreeeのデフォルト設定
- 手動入力時の選択ミス

### 対応

```
誤: 課税売上10%(21) ← 売上用のコード
正: 課対仕入10%(136) ← 仕入・経費用のコード
```

freee APIまたは画面から修正。件数が多い場合はAPI一括修正が効率的。

---

## 2. 役員報酬の月額変動

**→ AI_GUIDE.md #6「役員報酬の定期同額」に対応**

### パターン

```
役員報酬の支払額が毎月異なる
→ 定期同額給与の要件を満たさない？
```

### 検出方法

freee取引データで以下を検索：
```python
# 役員報酬を月別に集計
officer_payments = {}
for deal in deals:
    for detail in deal['details']:
        if detail['account_item_name'] == '役員報酬':
            month = deal['issue_date'][:7]  # YYYY-MM
            officer_payments[month] = detail['amount']

# 月額が変動しているか確認
amounts = list(officer_payments.values())
if len(set(amounts)) > 1:
    print("役員報酬の月額が変動しています")
    for month, amount in officer_payments.items():
        print(f"  {month}: {amount:,}円")
```

### よくある原因（問題なし）

| 変動要因 | 説明 |
|---------|------|
| 社会保険料控除 | 標準報酬月額改定時に変動 |
| 現物支給 | 社宅家賃控除など |
| 出張日当 | 旅費規程に基づく支給 |
| 立替経費精算 | 実費精算分 |

### 確認ポイント

- **額面（総支給額）**が毎月同額か？
- 変動要因を説明できる規程・資料があるか？

### 対応

額面が同額なら問題なし。変動理由を説明できる「役員報酬変動理由説明書」を作成しておく。

---

## 3. 重複取引の疑い

**→ AI_GUIDE.md #2「現金取引の記帳」に関連**

### パターン

```
同日・同額の取引が複数件
→ 二重計上？
```

### 検出方法

freee取引データで以下を検索：
```python
# 同日・同額の取引をグループ化
from collections import defaultdict
duplicates = defaultdict(list)

for deal in deals:
    for detail in deal['details']:
        key = (deal['issue_date'], abs(detail['amount']))
        duplicates[key].append(deal)

# 2件以上あるものを抽出
for (date, amount), deals_list in duplicates.items():
    if len(deals_list) >= 2:
        print(f"重複疑い: {date} {amount:,}円 × {len(deals_list)}件")
```

### よくある正当なケース

| ケース | 例 |
|-------|-----|
| 複数人分 | 役員2名の出張 = 同額×2件 |
| 往復分 | 航空券の往路・復路 = 同額×2件 |
| 月次支払 | 毎月同日・同額の家賃やリース料 |
| 複数店舗 | 同日に別店舗で同額の仕入 |

### 対応

摘要を確認し、正当な理由があれば摘要を詳細化：
```
変更前: 「航空券」
変更後: 「航空券（東京→大阪 往路）山田太郎」
```

---

## 4. 関係者取引

**→ AI_GUIDE.md #9「関連当事者取引」に対応**

### パターン

```
役員や親族への支払が毎月発生
→ 適切な契約・記録があるか確認が必要
```

### 検出方法

```python
# _INDEX.json から役員名を取得
officers = ['山田太郎', '山田花子']  # INDEX.jsonから

# 摘要に役員名が含まれる取引を検索
for deal in deals:
    description = deal.get('description', '') or ''
    for officer in officers:
        if officer in description:
            print(f"関係者取引: {deal['issue_date']} {description}")
```

### チェックポイント

| 項目 | 確認内容 |
|------|---------|
| 契約書 | 業務委託契約書があるか |
| 業務実態 | 実際に業務を行っているか |
| 金額の妥当性 | 市場価格と比較して適正か |
| 支払証拠 | 振込記録があるか |

### 対応

- 契約書がない → 業務委託契約書を作成
- 金額が不明確 → 業務内容と報酬を明記
- 毎月同額 → 外注費の給与認定リスクを検討

---

## 5. 高額経費（50万円以上）

**→ AI_GUIDE.md #7「高額経費の摘要」に対応**

### パターン

```
50万円以上の経費に摘要がない
→ 内容を明確にしておくと安心
```

### 検出方法

```python
# 50万円以上で摘要がない取引を検索
for deal in deals:
    for detail in deal['details']:
        if abs(detail['amount']) >= 500000:
            description = detail.get('description', '') or ''
            if not description or len(description) < 5:
                print(f"摘要なし高額経費: {deal['issue_date']} "
                      f"{detail['account_item_name']} {detail['amount']:,}円")
```

### 対応

| 勘定科目 | 必要な記載 |
|---------|-----------|
| 固定資産 | 品名、型番、設置場所 |
| 外注費 | 業務内容、委託先名 |
| 旅費交通費 | 行先、目的、参加者 |
| 交際費 | 相手先、目的、参加人数 |

### 3点照合

高額資産は以下の3点照合を実施：
```
固定資産台帳 ←→ freee取引 ←→ 銀行入出金
```

---

## 6. 外注費の給与認定リスク

**→ AI_GUIDE.md #5「外注費と給与の区分」に対応**

### パターン

```
特定の外注先に毎月同額を支払
→ 実態は給与では？
```

### 検出方法

```python
# 外注費を取引先別・月別に集計
from collections import defaultdict
outsourcing = defaultdict(lambda: defaultdict(int))

for deal in deals:
    for detail in deal['details']:
        if detail['account_item_name'] == '外注費':
            partner = deal.get('partner_name', '不明')
            month = deal['issue_date'][:7]
            outsourcing[partner][month] += detail['amount']

# 毎月同額の支払先を抽出
for partner, monthly in outsourcing.items():
    amounts = list(monthly.values())
    if len(amounts) >= 3 and len(set(amounts)) == 1:
        print(f"給与認定リスク: {partner} 毎月{amounts[0]:,}円")
```

### 給与認定される可能性が高いケース

| 要素 | 給与的 | 外注的 |
|------|-------|-------|
| 支払形態 | 毎月固定額 | 成果物・時間単価 |
| 指揮命令 | 会社の指示で業務 | 独立して業務 |
| 勤務場所 | 会社指定 | 自由 |
| 機材 | 会社提供 | 自前 |
| 専属性 | この会社のみ | 複数取引先 |

### 対応

- 業務委託契約書で業務内容を明確化
- 成果物ベースの報酬体系に変更
- 請求書を毎月受領

---

## 7. 期末付近の売上・仕入

**→ AI_GUIDE.md #11「期間帰属」に対応**

### パターン

```
期末月の売上が極端に少ない
期末直前に大量の仕入がある
```

### 検出方法

```python
# 月別の売上・仕入を集計
from collections import defaultdict
monthly_sales = defaultdict(int)
monthly_purchases = defaultdict(int)

for deal in deals:
    month = deal['issue_date'][:7]
    for detail in deal['details']:
        if detail['entry_side'] == 'credit':  # 売上
            monthly_sales[month] += detail['amount']
        elif detail['account_item_name'] == '仕入':
            monthly_purchases[month] += detail['amount']

# 期末月（例: 4月決算なら4月）を前年同月と比較
fiscal_end = '2025-04'
prev_year = '2024-04'
print(f"期末売上: {monthly_sales[fiscal_end]:,}円")
print(f"前年同月: {monthly_sales[prev_year]:,}円")
```

### 確認ポイント

| 項目 | 確認すべきこと |
|------|---------------|
| 売上の計上時期 | 適切な期に計上されているか |
| 仕入と在庫の関係 | 期末在庫が適切に計上されているか |

### 対応

- 期末月の売上を前年同月と比較
- 期末在庫の棚卸を確認
- 売上計上基準（出荷基準/検収基準）を確認

---

## 8. 源泉徴収漏れ

**→ AI_GUIDE.md #16「源泉徴収」に対応**

### パターン

```
士業・デザイナー等への報酬に源泉税がない
```

### 検出方法

```python
# 源泉徴収が必要な可能性がある取引を検索
keywords = ['税理士', '弁護士', '司法書士', 'デザイン', 'ライター', '講演', '原稿']

for deal in deals:
    description = str(deal.get('description', ''))
    partner = str(deal.get('partner_name', ''))

    for kw in keywords:
        if kw in description or kw in partner:
            # 源泉税の計上があるか確認
            has_withholding = any(
                '源泉' in str(d.get('description', '')) or
                d['account_item_name'] == '預り金'
                for d in deal['details']
            )
            if not has_withholding:
                print(f"源泉徴収漏れ疑い: {deal['issue_date']} {partner}")
```

### 源泉徴収が必要な報酬

| 種類 | 源泉税率 |
|------|---------|
| 弁護士、税理士、司法書士等 | 10.21% |
| デザイナー、ライター | 10.21% |
| 講演料、原稿料 | 10.21% |
| 外交員報酬 | 10.21% |

### 対応

- 預り金（源泉所得税）の計上を確認
- 不足分は翌月10日までに納付

---

## 実施時の教訓

### 1. 税区分は見落としやすい

銀行明細連携だと自動設定されるため、定期的にチェックが必要。

### 2. 役員報酬の「定期同額」は額面で判断

支払額が変動しても、額面が固定なら問題なし。変動理由を説明できる書類を用意。

### 3. 重複疑いは詳細確認

複数人分、往復分などで正当な場合がある。摘要を詳細化して説明可能にする。

### 4. 3点照合は有効

固定資産台帳・freee・銀行の3点照合で漏れを防止。

### 5. 契約書は先に用意

関係者取引は必ず契約書を作成。後から作成すると疑われる。

### 6. 高額取引は摘要を明確に

50万円以上の取引は、摘要を明確にしておくと確認がスムーズ。

---

*v1.0.0 - 本ドキュメントは一般的なパターンを記載した参考情報です。*
*具体的な対応は税理士にご相談ください。*

---

### フォーク時のお願い

改変・再配布する場合は、以下のクレジット表記を記載してください：

```
Original work: バーチャル税務調査～経理丸投げちゃん～
https://github.com/CLANBIZ/keiri-marunage-chan
Copyright (c) 2025 株式会社CLAN (https://clanbiz.net/keiri-marunage-chan-LP/)
```
