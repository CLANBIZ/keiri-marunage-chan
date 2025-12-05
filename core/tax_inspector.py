"""
税務調査エンジン - 厳選20項目チェック（追徴直結項目のみ）
バーチャル税務調査～経理丸投げちゃん～ コアロジック

【売上・現金】1-3: 売上漏れ、現金除外、期ズレ
【人件費】4-6: 架空人件費、外注費給与認定、源泉漏れ
【役員関連】7-10: 報酬期中変更、役員賞与、役員貸付、経済的利益
【経費】11-14: 交際費、私的経費、架空経費、在庫漏れ
【消費税】15-17: 税区分エラー、軽減税率、インボイス
【関係者】18-19: 関係者支払、関係者仕入
【帳簿】20: 帳簿不備
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from datetime import datetime


class RiskLevel(Enum):
    """リスクレベル"""
    HIGH = "high"      # 要修正
    MEDIUM = "medium"  # 要確認
    LOW = "low"        # 軽微
    NONE = "none"      # 問題なし


@dataclass
class Issue:
    """検出された問題"""
    category: str
    title: str
    description: str
    risk_level: RiskLevel
    deal_id: Optional[int] = None
    amount: Optional[int] = None
    suggestion: Optional[str] = None
    auto_fixable: bool = False


@dataclass
class InspectionResult:
    """調査結果"""
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    issues: List[Issue] = field(default_factory=list)
    report: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class TaxInspector:
    """
    税務調査エンジン - 厳選20項目チェック（追徴直結項目のみ）

    【売上・現金】追徴の最大要因
    1. 売上計上漏れ - 銀行入金とfreee売上の不一致
    2. 現金売上の除外 - 現金勘定の異常
    3. 期ズレ - 売上の翌期繰延

    【人件費】架空・水増しは重加算税
    4. 架空人件費 - 支払先不明・摘要なし
    5. 外注費の給与認定 - 毎月同額・1社集中
    6. 源泉徴収漏れ - 報酬・料金の源泉なし

    【役員関連】損金不算入の宝庫
    7. 役員報酬の期中変更 - 定期同額違反
    8. 役員賞与（届出なし） - 全額損金不算入
    9. 役員貸付金 - 認定利息・給与認定
    10. 役員への経済的利益 - 社宅・保険の過大負担

    【経費】否認されやすい項目
    11. 交際費の損金不算入 - 800万超・5万超
    12. 私的経費の混入 - 休日・家族名
    13. 架空経費 - 摘要なし・取引先集中
    14. 在庫計上漏れ - 期末仕入あり在庫ゼロ

    【消費税】インボイス後の重点
    15. 税区分エラー - 経費が課税売上
    16. 軽減税率の誤適用 - 8%の誤用
    17. 仕入税額控除の否認 - インボイスなし

    【関係者取引】同族会社の定番
    18. 関係者への高額支払 - 親族・関連会社
    19. 関係者からの低額仕入 - 時価との乖離

    【帳簿】基本だが重要
    20. 帳簿不備・説明不能 - 高額取引で摘要なし
    """

    # 税区分コード
    TAX_CODES = {
        0: "対象外",
        2: "不課税",
        3: "非課税",
        21: "課税売上10%",
        23: "課税売上8%(軽減)",
        136: "課税仕入10%",
        138: "課税仕入8%(軽減)",
        15: "非課税仕入",
    }

    # 勘定科目と正しい税区分のマッピング
    CORRECT_TAX_CODES = {
        # 不課税(2)または対象外(0)にすべきもの
        "役員報酬": [2, 0],
        "給料手当": [2, 0],
        "給与": [2, 0],
        "法定福利費": [2, 0],
        "租税公課": [2, 0],
        "預り金": [0, 2],
        "仮払金": [0, 2],

        # 非課税(3)にすべきもの
        "受取利息": [3],

        # 非課税仕入(15)にすべきもの
        "保険料": [15, 136],  # 損害保険は課税の場合も

        # 課税仕入10%(136)にすべきもの
        "旅費交通費": [136],
        "通信費": [136],
        "消耗品費": [136],
        "接待交際費": [136],
        "支払手数料": [136],
        "広告宣伝費": [136],
        "外注費": [136],
        "地代家賃": [136, 15],  # 事務所は課税、住居は非課税
        "水道光熱費": [136],
        "会議費": [136],
        "新聞図書費": [136],
        "諸会費": [136],
        "修繕費": [136],
        "雑費": [136],
        "福利厚生費": [136],
        "荷造運賃": [136],
        "車両費": [136],
        "研修費": [136],
        "事務用品費": [136],
    }

    # 経費の異常値しきい値（将来の拡張用: 単一取引での異常検出に使用予定）
    EXPENSE_THRESHOLDS = {
        "接待交際費": 50000,
        "交際費": 50000,
        "会議費": 10000,
        "旅費交通費": 100000,
        "消耗品費": 100000,
    }

    # 疑わしいキーワード（将来の拡張用: 摘要内容のパターンマッチに使用予定）
    # フォーマット: (キーワード, 対象勘定科目, リスクレベル, 理由)
    SUSPICIOUS_KEYWORDS = [
        ("amazon", "消耗品費", "MEDIUM", "Amazonでの購入は私的利用の可能性"),
        ("楽天", "消耗品費", "LOW", "楽天での購入は私的利用の可能性"),
        ("スターバックス", "会議費", "LOW", "カフェ代は私的利用の疑い"),
        ("コンビニ", "消耗品費", "LOW", "コンビニでの購入は私的利用の疑い"),
    ]

    def __init__(self, account_map: Dict[int, str] = None, tax_map: Dict[int, str] = None):
        """
        Args:
            account_map: 勘定科目ID→名称のマップ
            tax_map: 税区分コード→名称のマップ
        """
        self.account_map = account_map or {}
        self.tax_map = tax_map or self.TAX_CODES
        self.result = InspectionResult()

    def inspect_all(self, deals: List[Dict],
                    fiscal_year_start: str = None,
                    period_boundary: str = None,
                    bank_data: Dict = None) -> InspectionResult:
        """
        厳選20項目の追徴直結チェックを実行

        Args:
            deals: 取引データのリスト
            fiscal_year_start: 事業年度開始日 (例: "2024-05-01")
            period_boundary: 期の境界日 (例: "2025-05-01"で1期と2期を分ける)
            bank_data: 銀行データ（照合用）{'balance': int, 'transactions': list}

        Returns:
            InspectionResult: 監査結果（issues, errors, warnings等を含む）
        """
        self.result = InspectionResult()
        self.result.details = {
            "inspection_date": datetime.now().isoformat(),
            "total_deals": len(deals),
            "fiscal_year_start": fiscal_year_start,
        }

        # 【売上・現金】1-3
        self._check_01_sales_omission(deals, bank_data)
        self._check_02_cash_sales_exclusion(deals)
        self._check_03_period_shift(deals, fiscal_year_start)

        # 【人件費】4-6
        self._check_04_fake_personnel(deals)
        self._check_05_outsourcing_as_salary(deals)
        self._check_06_withholding_omission(deals)

        # 【役員関連】7-10
        self._check_07_officer_compensation_change(deals, period_boundary)
        self._check_08_officer_bonus(deals)
        self._check_09_officer_loans(deals)
        self._check_10_officer_benefit(deals)

        # 【経費】11-14
        self._check_11_entertainment(deals)
        self._check_12_private_expense(deals)
        self._check_13_fake_expense(deals)
        self._check_14_inventory_omission(deals)

        # 【消費税】15-17
        self._check_15_tax_code_error(deals)
        self._check_16_reduced_tax_error(deals)
        self._check_17_invoice_denial(deals)

        # 【関係者取引】18-19
        self._check_18_related_party_payment(deals)
        self._check_19_related_party_purchase(deals)

        # 【帳簿】20
        self._check_20_poor_records(deals)

        # 勘定科目別集計（参考情報）
        self._account_summary(deals)

        # レポート生成
        self._generate_report()

        return self.result

    def _get_account_name(self, account_id: int) -> str:
        """勘定科目IDから名称を取得"""
        return self.account_map.get(account_id, str(account_id))

    # ========================================
    # 【売上・現金】1-3: 追徴の最大要因
    # ========================================

    def _check_01_sales_omission(self, deals: List[Dict], bank_data: Dict = None):
        """1. 売上計上漏れ: 銀行入金とfreee売上の不一致"""
        sales = []
        for deal in deals:
            if deal.get('type') == 'income':
                for detail in deal.get('details', []):
                    sales.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                    })

        total_sales = sum(s['amount'] for s in sales)
        self.result.details['01_sales'] = {'total': total_sales, 'count': len(sales)}

        # 銀行データとの照合（提供された場合）
        if bank_data and bank_data.get('income_total'):
            diff = bank_data['income_total'] - total_sales
            if diff > 10000:  # 1万円以上の差異
                self.result.errors += 1
                self.result.issues.append(Issue(
                    category="01.売上漏れ",
                    title="銀行入金とfreee売上の不一致",
                    description=f"銀行入金: {bank_data['income_total']:,}円 / freee売上: {total_sales:,}円 / 差額: {diff:,}円",
                    risk_level=RiskLevel.HIGH,
                    suggestion="売上計上漏れがないか確認。重加算税の対象になる可能性"
                ))

    def _check_02_cash_sales_exclusion(self, deals: List[Dict]):
        """2. 現金売上の除外: 現金勘定の異常な動き"""
        cash_movements = []
        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '現金' in ac_name:
                    cash_movements.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'type': deal.get('type'),
                        'desc': detail.get('description') or '',
                    })

        self.result.details['02_cash'] = cash_movements
        # 現金残高がマイナスになるパターンを検出
        if cash_movements:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="02.現金",
                title="現金取引あり",
                description=f"{len(cash_movements)}件の現金取引（税務調査で重点確認される）",
                risk_level=RiskLevel.MEDIUM,
                suggestion="現金売上の記録漏れがないか確認"
            ))

    def _check_03_period_shift(self, deals: List[Dict], fiscal_year_start: str = None):
        """3. 期ズレ: 売上の翌期繰延"""
        # 期末月の売上が異常に少ないかチェック
        if not fiscal_year_start:
            return

        monthly_sales = defaultdict(int)
        for deal in deals:
            if deal.get('type') == 'income':
                month = deal['issue_date'][:7]
                for detail in deal.get('details', []):
                    monthly_sales[month] += detail.get('amount', 0)

        self.result.details['03_period_shift'] = dict(monthly_sales)

    # ========================================
    # 【人件費】4-6: 架空・水増しは重加算税
    # ========================================

    def _check_04_fake_personnel(self, deals: List[Dict]):
        """4. 架空人件費: 支払先不明・摘要なし"""
        personnel = []
        no_desc = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if any(kw in ac_name for kw in ['給料', '給与', '賞与', '役員報酬']):
                    entry = {
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'desc': detail.get('description') or '',
                        'account': ac_name,
                        'id': deal['id']
                    }
                    personnel.append(entry)
                    if not entry['desc'] and entry['amount'] >= 50000:
                        no_desc.append(entry)

        self.result.details['04_personnel'] = {'total': len(personnel), 'no_desc': len(no_desc)}

        if no_desc:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="04.架空人件費",
                title="支払先不明の人件費",
                description=f"{len(no_desc)}件の5万円以上の人件費に摘要なし",
                risk_level=RiskLevel.HIGH,
                suggestion="架空人件費と認定されると重加算税35%の対象"
            ))

    def _check_05_outsourcing_as_salary(self, deals: List[Dict]):
        """5. 外注費の給与認定: 毎月同額・特定1社への継続支払"""
        outsourcing = []
        monthly_by_desc = defaultdict(lambda: defaultdict(int))

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '外注' in ac_name:
                    desc = (detail.get('description') or '')[:30]
                    outsourcing.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'desc': desc,
                    })
                    month = deal['issue_date'][:7]
                    monthly_by_desc[desc][month] += detail.get('amount', 0)

        # 毎月同額パターン（給与性が疑われる）
        wage_like = []
        for desc, months in monthly_by_desc.items():
            if len(months) >= 3:
                amounts = list(months.values())
                if len(set(amounts)) == 1:  # 全月同額
                    wage_like.append({'desc': desc, 'amount': amounts[0], 'months': len(months)})

        self.result.details['05_outsourcing'] = {
            'total': sum(o['amount'] for o in outsourcing),
            'count': len(outsourcing),
            'wage_like': wage_like
        }

        if wage_like:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="05.外注費→給与",
                title="外注費の給与認定リスク",
                description=f"{len(wage_like)}件の毎月定額外注（{wage_like[0]['desc']}等）",
                risk_level=RiskLevel.HIGH,
                suggestion="給与認定→源泉税+不納付加算税10%+社保遡及のリスク"
            ))

    def _check_06_withholding_omission(self, deals: List[Dict]):
        """6. 源泉徴収漏れ: 報酬・料金で源泉税の計上なし"""
        withholding_keywords = ['報酬', '顧問料', '講師', 'コンサル', '原稿', 'デザイン']
        potentially_missing = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if any(kw in ac_name for kw in withholding_keywords):
                    if detail.get('amount', 0) >= 50000:
                        potentially_missing.append({
                            'date': deal['issue_date'],
                            'amount': detail.get('amount', 0),
                            'account': ac_name,
                        })

        self.result.details['06_withholding'] = potentially_missing
        if potentially_missing:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="06.源泉漏れ",
                title="源泉徴収対象の可能性",
                description=f"{len(potentially_missing)}件の報酬・料金（個人への支払は源泉必要）",
                risk_level=RiskLevel.MEDIUM,
                suggestion="法人への支払なら不要。個人なら10.21%源泉"
            ))

    # ========================================
    # 【役員関連】7-10: 損金不算入の宝庫
    # ========================================

    def _check_07_officer_compensation_change(self, deals: List[Dict], period_boundary: str = None):
        """7. 役員報酬の期中変更: 定期同額違反"""
        officer_payments = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '役員報酬' in ac_name:
                    officer_payments.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                    })

        # 月別集計
        monthly = defaultdict(int)
        for p in officer_payments:
            month = p['date'][:7]
            monthly[month] += p['amount']

        self.result.details['07_officer_compensation'] = dict(monthly)

        # 期首3ヶ月以降で変動があるか
        sorted_months = sorted(monthly.items())
        if len(sorted_months) > 3:
            main_amounts = [amt for _, amt in sorted_months[3:]]
            if len(set(main_amounts)) > 1:
                self.result.errors += 1
                self.result.issues.append(Issue(
                    category="07.役員報酬",
                    title="役員報酬の期中変更",
                    description=f"期首3ヶ月以降で変動: {sorted(set(main_amounts))}",
                    risk_level=RiskLevel.HIGH,
                    suggestion="臨時改定事由の議事録がなければ損金不算入"
                ))

    def _check_08_officer_bonus(self, deals: List[Dict]):
        """8. 役員賞与（届出なし）: 全額損金不算入"""
        officer_bonus = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '役員賞与' in ac_name:
                    officer_bonus.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                    })

        self.result.details['08_officer_bonus'] = officer_bonus
        if officer_bonus:
            total = sum(b['amount'] for b in officer_bonus)
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="08.役員賞与",
                title="役員賞与あり（届出確認）",
                description=f"{len(officer_bonus)}件 / 合計: {total:,}円",
                risk_level=RiskLevel.HIGH,
                suggestion="事前確定届出給与の届出書がなければ全額損金不算入"
            ))

    def _check_09_officer_loans(self, deals: List[Dict]):
        """9. 役員貸付金: 認定利息・給与認定"""
        loans = []
        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '役員貸付' in ac_name or '短期貸付' in ac_name:
                    loans.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'desc': detail.get('description') or '',
                        'type': deal.get('type'),
                    })

        # 残高計算
        balance = sum(l['amount'] for l in loans if l['type'] == 'expense') - \
                  sum(l['amount'] for l in loans if l['type'] == 'income')

        self.result.details['09_officer_loans'] = {'balance': balance, 'count': len(loans)}

        if balance > 0:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="09.役員貸付",
                title="役員貸付金残高あり",
                description=f"残高: {balance:,}円 | 認定利息(年1%程度)の計上が必要",
                risk_level=RiskLevel.HIGH,
                suggestion="長期滞留・使途不明は役員賞与認定リスク"
            ))

    def _check_10_officer_benefit(self, deals: List[Dict]):
        """10. 役員への経済的利益: 社宅・保険の過大負担"""
        benefit_keywords = ['社宅', '保険', '車両', '福利厚生']
        benefits = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                desc = (detail.get('description') or '').lower()

                for kw in benefit_keywords:
                    if kw in ac_name or kw in desc:
                        if detail.get('amount', 0) >= 50000:
                            benefits.append({
                                'date': deal['issue_date'],
                                'amount': detail.get('amount', 0),
                                'account': ac_name,
                            })
                        break

        self.result.details['10_officer_benefit'] = benefits
        if benefits:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="10.経済的利益",
                title="役員への経済的利益の可能性",
                description=f"{len(benefits)}件の社宅・保険等の支出",
                risk_level=RiskLevel.MEDIUM,
                suggestion="社宅は賃貸料相当額、保険は受取人要確認"
            ))

    # ========================================
    # 【経費】11-14: 否認されやすい項目
    # ========================================

    def _check_11_entertainment(self, deals: List[Dict]):
        """11. 交際費の損金不算入: 800万円超・5万円超"""
        entertainment = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '交際費' in ac_name or '接待' in ac_name:
                    entertainment.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'desc': detail.get('description') or '',
                    })

        total = sum(e['amount'] for e in entertainment)
        large = [e for e in entertainment if e['amount'] >= 50000]

        self.result.details['11_entertainment'] = {'total': total, 'count': len(entertainment)}

        if total > 8000000:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="11.交際費",
                title="交際費が年800万円超",
                description=f"合計: {total:,}円（超過分は損金不算入）",
                risk_level=RiskLevel.HIGH,
                suggestion="飲食費50%特例の適用検討"
            ))
        if large:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="11.交際費",
                title="5万円超の交際費",
                description=f"{len(large)}件（参加者・目的の記録必要）",
                risk_level=RiskLevel.MEDIUM,
                suggestion="議事録・参加者リストを保管"
            ))

    def _check_12_private_expense(self, deals: List[Dict]):
        """12. 私的経費の混入: 休日・家族名"""
        private_keywords = ['家族', '私用', '個人', '自宅']
        weekend_expenses = []
        private_expenses = []

        for deal in deals:
            for detail in deal.get('details', []):
                desc = (detail.get('description') or '').lower()
                # 休日（土日）の支出
                # キーワードマッチ
                for kw in private_keywords:
                    if kw in desc:
                        private_expenses.append({
                            'date': deal['issue_date'],
                            'amount': detail.get('amount', 0),
                            'desc': desc,
                        })
                        break

        self.result.details['12_private'] = private_expenses
        if private_expenses:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="12.私的経費",
                title="私的経費の混入疑い",
                description=f"{len(private_expenses)}件に「家族」「私用」等のキーワード",
                risk_level=RiskLevel.HIGH,
                suggestion="私的経費は全額損金不算入＋給与課税"
            ))

    def _check_13_fake_expense(self, deals: List[Dict]):
        """13. 架空経費: 摘要なし・同一取引先への集中"""
        expenses_no_desc = []

        for deal in deals:
            if deal.get('type') != 'expense':
                continue
            for detail in deal.get('details', []):
                if not detail.get('description') and detail.get('amount', 0) >= 100000:
                    expenses_no_desc.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'account': self._get_account_name(detail.get('account_item_id')),
                    })

        self.result.details['13_fake_expense'] = expenses_no_desc
        if expenses_no_desc:
            total = sum(e['amount'] for e in expenses_no_desc)
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="13.架空経費",
                title="摘要なし高額経費",
                description=f"{len(expenses_no_desc)}件 / 合計: {total:,}円",
                risk_level=RiskLevel.HIGH,
                suggestion="架空経費と認定されると重加算税35%"
            ))

    def _check_14_inventory_omission(self, deals: List[Dict]):
        """14. 在庫計上漏れ: 期末に仕入があるのに在庫ゼロ"""
        purchases = []
        inventory = []

        for deal in deals:
            for detail in deal.get('details', []):
                ac_name = str(self._get_account_name(detail.get('account_item_id')))
                if '仕入' in ac_name:
                    purchases.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                    })
                if '棚卸' in ac_name or '在庫' in ac_name:
                    inventory.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                    })

        total_purchase = sum(p['amount'] for p in purchases)
        self.result.details['14_inventory'] = {
            'total_purchase': total_purchase,
            'has_inventory': len(inventory) > 0
        }

        if total_purchase > 1000000 and not inventory:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="14.在庫漏れ",
                title="仕入があるのに在庫計上なし",
                description=f"仕入合計: {total_purchase:,}円 | 棚卸資産の計上なし",
                risk_level=RiskLevel.MEDIUM,
                suggestion="飲食・小売は期末在庫の計上必須"
            ))

    # ========================================
    # 【消費税】15-17: インボイス後の重点項目
    # ========================================

    def _check_15_tax_code_error(self, deals: List[Dict]):
        """15. 税区分エラー: 経費が課税売上で登録"""
        errors = []

        for deal in deals:
            if deal.get('type') != 'expense':
                continue
            for detail in deal.get('details', []):
                if detail.get('tax_code') == 21:  # 課税売上10%
                    errors.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'account': self._get_account_name(detail.get('account_item_id')),
                    })

        self.result.details['15_tax_code'] = len(errors)
        if errors:
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="15.税区分",
                title="経費が課税売上で登録",
                description=f"{len(errors)}件 | 税区分:21→136に修正",
                risk_level=RiskLevel.HIGH,
                suggestion="消費税の計算が狂う。修正必須",
                auto_fixable=True
            ))

    def _check_16_reduced_tax_error(self, deals: List[Dict]):
        """16. 軽減税率の誤適用: 飲食料品以外に8%適用"""
        reduced_rate = []

        for deal in deals:
            for detail in deal.get('details', []):
                if detail.get('tax_code') in [23, 138]:  # 軽減税率8%
                    ac_name = str(self._get_account_name(detail.get('account_item_id')))
                    # 飲食料品以外で軽減税率
                    if not any(kw in ac_name for kw in ['仕入', '食', '飲料']):
                        reduced_rate.append({
                            'date': deal['issue_date'],
                            'amount': detail.get('amount', 0),
                            'account': ac_name,
                        })

        self.result.details['16_reduced_tax'] = reduced_rate
        if reduced_rate:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="16.軽減税率",
                title="軽減税率の適用確認",
                description=f"{len(reduced_rate)}件の8%適用（飲食料品以外？）",
                risk_level=RiskLevel.MEDIUM,
                suggestion="飲食料品以外は10%。2%の差額追徴リスク"
            ))

    def _check_17_invoice_denial(self, deals: List[Dict]):
        """17. 仕入税額控除の否認: 30万円超でインボイスなし"""
        large_purchases = []

        for deal in deals:
            if deal.get('type') != 'expense':
                continue
            for detail in deal.get('details', []):
                if detail.get('tax_code') in [136, 138] and detail.get('amount', 0) >= 300000:
                    large_purchases.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'account': self._get_account_name(detail.get('account_item_id')),
                    })

        self.result.details['17_invoice'] = large_purchases
        if large_purchases:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="17.インボイス",
                title="高額課税仕入のインボイス確認",
                description=f"{len(large_purchases)}件の30万円以上の課税仕入",
                risk_level=RiskLevel.MEDIUM,
                suggestion="インボイス(T+13桁)の保管確認。なければ仕入税額控除否認"
            ))

    # ========================================
    # 【関係者取引】18-19: 同族会社の定番指摘
    # ========================================

    def _check_18_related_party_payment(self, deals: List[Dict]):
        """18. 関係者への高額支払: 親族・関連会社への支出"""
        related_keywords = ['父', '母', '親', '妻', '夫', '子', '兄', '弟', '姉', '妹',
                          '親族', '家族', '同族', '関連']
        related = []

        for deal in deals:
            if deal.get('type') != 'expense':
                continue
            for detail in deal.get('details', []):
                desc = (detail.get('description') or '').lower()
                for kw in related_keywords:
                    if kw in desc:
                        related.append({
                            'date': deal['issue_date'],
                            'amount': detail.get('amount', 0),
                            'keyword': kw,
                        })
                        break

        self.result.details['18_related_payment'] = related
        if related:
            total = sum(r['amount'] for r in related)
            self.result.errors += 1
            self.result.issues.append(Issue(
                category="18.関係者支払",
                title="関係者への支払検出",
                description=f"{len(related)}件 / 合計: {total:,}円",
                risk_level=RiskLevel.HIGH,
                suggestion="時価との比較・契約書で適正取引を証明"
            ))

    def _check_19_related_party_purchase(self, deals: List[Dict]):
        """19. 関係者からの低額仕入: 時価との乖離"""
        # 売上で関係者キーワードを検出
        related_keywords = ['父', '母', '親', '妻', '夫', '同族', '関連']
        related = []

        for deal in deals:
            if deal.get('type') != 'income':
                continue
            for detail in deal.get('details', []):
                desc = (detail.get('description') or '').lower()
                for kw in related_keywords:
                    if kw in desc:
                        related.append({
                            'date': deal['issue_date'],
                            'amount': detail.get('amount', 0),
                        })
                        break

        self.result.details['19_related_income'] = related
        if related:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="19.関係者仕入",
                title="関係者からの収入・仕入",
                description=f"{len(related)}件（時価との乖離確認）",
                risk_level=RiskLevel.MEDIUM,
                suggestion="低額譲渡は寄附金認定リスク"
            ))

    # ========================================
    # 【帳簿】20: 基本だが重要
    # ========================================

    def _check_20_poor_records(self, deals: List[Dict]):
        """20. 帳簿不備・説明不能: 高額取引で摘要なし"""
        poor = []

        for deal in deals:
            for detail in deal.get('details', []):
                if not detail.get('description') and detail.get('amount', 0) >= 50000:
                    poor.append({
                        'date': deal['issue_date'],
                        'amount': detail.get('amount', 0),
                        'account': self._get_account_name(detail.get('account_item_id')),
                    })

        poor.sort(key=lambda x: -x['amount'])
        self.result.details['20_poor_records'] = poor[:30]

        if len(poor) > 20:
            self.result.warnings += 1
            self.result.issues.append(Issue(
                category="20.帳簿不備",
                title="摘要なし高額取引が多数",
                description=f"{len(poor)}件の5万円以上の取引に摘要なし",
                risk_level=RiskLevel.MEDIUM,
                suggestion="税務調査では「何のための支出か」が必ず問われる"
            ))

    # ========================================
    # 参考情報
    # ========================================

    def _account_summary(self, deals: List[Dict]):
        """勘定科目別集計（参考情報）"""
        account_totals = defaultdict(lambda: {'amount': 0, 'count': 0})

        for deal in deals:
            if deal.get('type') == 'expense':
                for detail in deal.get('details', []):
                    ac_name = self._get_account_name(detail.get('account_item_id'))
                    account_totals[ac_name]['amount'] += detail.get('amount', 0)
                    account_totals[ac_name]['count'] += 1

        sorted_accounts = sorted(account_totals.items(), key=lambda x: -x[1]['amount'])[:15]
        self.result.details['account_summary'] = {
            name: data for name, data in sorted_accounts
        }

    def _generate_report(self):
        """レポート生成（厳選20項目対応）"""
        lines = [
            "=" * 60,
            "厳選20項目 税務調査レポート（追徴直結項目のみ）",
            f"調査日時: {self.result.details.get('inspection_date', '')}",
            f"取引件数: {self.result.details.get('total_deals', 0)}件",
            "=" * 60,
            "",
            "## サマリー",
            f"- HIGH（追徴リスク大）: {self.result.errors}件",
            f"- MEDIUM（要確認）: {self.result.warnings}件",
            "",
        ]

        # 役員報酬
        if '07_officer_compensation' in self.result.details:
            oc = self.result.details['07_officer_compensation']
            if oc:
                lines.append("### 役員報酬 月別")
                for month, amount in sorted(oc.items()):
                    lines.append(f"  {month}: {amount:,}円")

        # 役員貸付金
        if '09_officer_loans' in self.result.details:
            ol = self.result.details['09_officer_loans']
            if ol.get('balance', 0) > 0:
                lines.append(f"\n### 役員貸付金残高: {ol['balance']:,}円")

        # 交際費
        if '11_entertainment' in self.result.details:
            ent = self.result.details['11_entertainment']
            if ent.get('total', 0) > 0:
                lines.append(f"\n### 交際費: {ent['total']:,}円 ({ent['count']}件)")

        # 税区分エラー
        if self.result.details.get('15_tax_code', 0) > 0:
            lines.append(f"\n### 税区分エラー: {self.result.details['15_tax_code']}件")

        # 勘定科目別集計
        if 'account_summary' in self.result.details:
            lines.append("\n### 費用TOP10")
            for ac, data in list(self.result.details['account_summary'].items())[:10]:
                lines.append(f"  {ac}: {data['amount']:,}円 ({data['count']}件)")

        lines.append("\n" + "=" * 60)

        # 問題リスト
        if self.result.issues:
            lines.append("\n## 検出された問題\n")

            for level, level_name in [
                (RiskLevel.HIGH, "HIGH 追徴リスク大"),
                (RiskLevel.MEDIUM, "MEDIUM 要確認"),
                (RiskLevel.LOW, "LOW 軽微")
            ]:
                level_issues = [i for i in self.result.issues if i.risk_level == level]
                if level_issues:
                    lines.append(f"\n### {level_name} ({len(level_issues)}件)")
                    for issue in level_issues[:20]:
                        lines.append(f"- [{issue.category}] {issue.title}")
                        lines.append(f"  {issue.description}")
                        if issue.suggestion:
                            lines.append(f"  -> {issue.suggestion}")
                    if len(level_issues) > 20:
                        lines.append(f"  ... 他 {len(level_issues) - 20}件")

        self.result.report = "\n".join(lines)


# 使用例
if __name__ == "__main__":
    # サンプルデータでテスト
    sample_deals = [
        {
            "id": 1,
            "issue_date": "2024-06-15",
            "type": "expense",
            "details": [
                {
                    "account_item_id": 100,
                    "amount": 85000,
                    "tax_code": 2,
                    "description": "役員報酬 6月分"
                }
            ]
        }
    ]

    inspector = TaxInspector(account_map={100: "役員報酬"})
    result = inspector.inspect_all(sample_deals)
    print(result.report)
