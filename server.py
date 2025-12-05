"""
バーチャル税務調査～経理丸投げちゃん～ - 軽量APIサーバー
Flask + 静的HTML版

使い方:
    python server.py

ブラウザで http://localhost:5000 を開く

MCPサーバーとの連携:
    このサーバーはファイルを data/uploads/ に保存し、
    MCPサーバー経由でClaude Codeがアクセスできるようにします。
"""
import os
import sys
import json
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# コアモジュールをインポートするためにパスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.freee_client import FreeeClient
from core.tax_inspector import TaxInspector
from core.bank_parser import BankCSVParser

app = Flask(__name__, static_folder='static')

# セキュリティ: CORS設定（ローカル環境のみ許可 - 最小限に制限）
CORS(app, origins=[
    'http://localhost:5000',
    'http://127.0.0.1:5000'
])

# ========================================
# セキュリティ設定
# ========================================
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES_PER_REQUEST = 100  # 1リクエストあたりの最大ファイル数
ALLOWED_CSV_EXTENSIONS = {'.csv'}
ALLOWED_DOC_EXTENSIONS = {'.pdf', '.txt', '.md', '.json', '.zip'}

app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * MAX_FILES_PER_REQUEST

# ========================================
# ファイル保存設定（MCP連携用）
# ========================================
DATA_DIR = Path(__file__).parent / "data"
UPLOAD_CSV_DIR = DATA_DIR / "uploads" / "csv"
UPLOAD_DOCS_DIR = DATA_DIR / "uploads" / "docs"
CONFIG_FILE = DATA_DIR / "mcp_config.json"

# ディレクトリ作成
UPLOAD_CSV_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DOCS_DIR.mkdir(parents=True, exist_ok=True)

def safe_filename(filename):
    """日本語対応の安全なファイル名変換（パストラバーサル対策強化）"""
    import re
    import unicodedata
    from urllib.parse import unquote

    # URLデコード（%2F等の対策）
    filename = unquote(filename)
    # 正規化
    filename = unicodedata.normalize('NFC', filename)
    # パス区切り文字を除去
    filename = filename.replace('/', '_').replace('\\', '_')
    # 親ディレクトリ参照を除去
    filename = filename.replace('..', '_')
    # 危険な文字を除去
    filename = re.sub(r'[\x00-\x1f\x7f<>:"|?*]', '', filename)
    # 先頭・末尾の空白とドットを除去
    filename = filename.strip(' .')
    # 再度パス区切りチェック（多重エンコード対策）
    if '/' in filename or '\\' in filename or '..' in filename:
        filename = re.sub(r'[/\\]', '_', filename).replace('..', '_')
    # 空なら代替名
    if not filename:
        filename = 'unnamed_file'
    return filename


def validate_file_extension(filename, allowed_extensions):
    """ファイル拡張子のホワイトリスト検証"""
    ext = Path(filename).suffix.lower()
    return ext in allowed_extensions


def validate_file_path(filepath, base_dir):
    """ファイルパスがベースディレクトリ内にあることを確認（パストラバーサル対策）"""
    try:
        resolved = Path(filepath).resolve()
        base_resolved = Path(base_dir).resolve()
        return resolved.is_relative_to(base_resolved)
    except (ValueError, RuntimeError):
        return False

def load_mcp_config():
    """MCP設定を読み込み"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {"token": "", "files": [], "results": []}

def save_mcp_config(config):
    """MCP設定を保存"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

# ========================================
# 静的ファイル配信
# ========================================

@app.route('/')
def index():
    """メインページ"""
    return send_from_directory('.', 'index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """静的ファイル（CSS, JS, Images）"""
    return send_from_directory('static', filename)


# ========================================
# API エンドポイント
# ========================================

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """freee接続テスト"""
    try:
        data = request.json
        token = data.get('token')
        company_id = data.get('company_id')

        if not token or not company_id:
            return jsonify({'success': False, 'error': 'トークンと事業所IDが必要です'})

        client = FreeeClient(access_token=token, company_id=int(company_id))
        company = client.get_company()

        return jsonify({
            'success': True,
            'company_name': company.get('display_name', company.get('name', ''))
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """freeeデータを取得して分析"""
    try:
        data = request.json
        token = data.get('token')
        company_id = data.get('company_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        fiscal_month = data.get('fiscal_month', 5)

        if not token or not company_id:
            return jsonify({'success': False, 'error': 'トークンと事業所IDが必要です'})

        # freeeクライアント初期化
        client = FreeeClient(access_token=token, company_id=int(company_id))

        # マスタデータ取得
        account_map = client.get_account_items()
        tax_map = client.get_tax_codes()

        # 取引データ取得
        deals = client.get_deals(start_date=start_date, end_date=end_date)

        # Deal オブジェクトを辞書に変換
        deals_dict = [
            {
                "id": d.id,
                "issue_date": d.issue_date,
                "type": d.type,
                "amount": d.amount,
                "details": d.details,
                "payments": d.payments
            }
            for d in deals
        ]

        # 厳格10項目チェック実行
        inspector = TaxInspector(account_map=account_map, tax_map=tax_map)

        current_year = datetime.now().year
        period_boundary = f"{current_year}-{fiscal_month:02d}-01"

        result = inspector.inspect_all(deals_dict, period_boundary=period_boundary)

        # 結果を整形
        issues = [
            {
                'category': issue.category,
                'title': issue.title,
                'description': issue.description,
                'risk_level': issue.risk_level.value,
                'deal_id': issue.deal_id,
                'amount': issue.amount,
                'suggestion': issue.suggestion
            }
            for issue in result.issues
        ]

        return jsonify({
            'success': True,
            'deal_count': len(deals),
            'errors': result.errors,
            'warnings': result.warnings,
            'issues': issues,
            'report': result.report,
            'details': result.details
        })

    except Exception as e:
        # エラーログは内部のみ、クライアントには安全なメッセージ
        import logging
        logging.error(f"Analyze error: {e}")
        return jsonify({'success': False, 'error': translate_error(str(e))})


@app.route('/api/parse-csv', methods=['POST'])
def parse_csv():
    """銀行CSVを解析"""
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'error': 'ファイルがありません'})

        files = request.files.getlist('files')
        bank_type = request.form.get('bank_type', 'auto')

        # 銀行タイプのマッピング
        bank_type_map = {
            'auto': '自動検出',
            'rakuten': '楽天銀行',
            'sbi': '住信SBIネット銀行',
            'mufg': '三菱UFJ銀行',
            'mizuho': 'みずほ銀行',
            'freee': 'freee形式'
        }

        parser = BankCSVParser(bank_type=bank_type_map.get(bank_type, '自動検出'))

        results = []
        for file in files:
            content = file.read()
            transactions = parser.parse(content, file.filename)

            total_income = sum(t.amount for t in transactions if t.type == 'income')
            total_expense = sum(t.amount for t in transactions if t.type == 'expense')

            results.append({
                'filename': file.filename,
                'transaction_count': len(transactions),
                'total_income': total_income,
                'total_expense': total_expense
            })

        return jsonify({
            'success': True,
            'results': results
        })

    except Exception as e:
        import logging
        logging.error(f"CSV parse error: {e}")
        return jsonify({'success': False, 'error': 'CSVの解析に失敗しました'})


@app.route('/api/health', methods=['GET'])
def health():
    """ヘルスチェック"""
    return jsonify({
        'status': 'ok',
        'version': '1.0.0',
        'name': 'バーチャル税務調査～経理丸投げちゃん～'
    })


# ========================================
# freee API連携エンドポイント（AI向け）
# ========================================

@app.route('/api/freee/deals', methods=['GET'])
def get_freee_deals():
    """
    freee取引データを取得（AI向けエンドポイント）

    クエリパラメータ:
        start_date: 開始日 (YYYY-MM-DD)
        end_date: 終了日 (YYYY-MM-DD)
        limit: 取得件数上限 (デフォルト: 全件)

    使用例:
        curl "http://localhost:5000/api/freee/deals?start_date=2024-05-01&end_date=2025-12-03"
    """
    try:
        config = load_mcp_config()
        token = config.get('token')
        company_id = config.get('company_id')

        if not token:
            return jsonify({'success': False, 'error': 'トークンが設定されていません。WebUIでトークンを入力してください。'})
        if not company_id:
            return jsonify({'success': False, 'error': '事業所IDが設定されていません。WebUIで事業所IDを入力してください。'})

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        client = FreeeClient(access_token=token, company_id=int(company_id))

        # マスタデータ取得
        account_map = client.get_account_items()
        tax_map = client.get_tax_codes()

        # 取引データ取得
        deals = client.get_deals(start_date=start_date, end_date=end_date)

        # レスポンス用に整形
        deals_data = []
        for d in deals:
            deal_dict = {
                'id': d.id,
                'issue_date': d.issue_date,
                'type': d.type,
                'amount': d.amount,
                'details': []
            }
            for detail in d.details:
                deal_dict['details'].append({
                    'account_item_id': detail.get('account_item_id'),
                    'account_name': account_map.get(detail.get('account_item_id'), ''),
                    'tax_code': detail.get('tax_code'),
                    'tax_name': tax_map.get(detail.get('tax_code'), ''),
                    'amount': detail.get('amount'),
                    'description': detail.get('description', '')
                })
            deals_data.append(deal_dict)

        return jsonify({
            'success': True,
            'count': len(deals_data),
            'deals': deals_data
        })

    except Exception as e:
        return jsonify({'success': False, 'error': translate_error(str(e))})


@app.route('/api/freee/fix-tax', methods=['POST'])
def fix_tax_codes():
    """
    税区分エラーを一括修正（AI向けエンドポイント）

    リクエストボディ:
        {
            "fixes": [
                {"deal_id": 123, "old_tax_code": 21, "new_tax_code": 136},
                ...
            ]
        }

    使用例:
        curl -X POST http://localhost:5000/api/freee/fix-tax \
            -H "Content-Type: application/json" \
            -d '{"fixes": [{"deal_id": 123, "old_tax_code": 21, "new_tax_code": 136}]}'
    """
    try:
        config = load_mcp_config()
        token = config.get('token')
        company_id = config.get('company_id')

        if not token:
            return jsonify({'success': False, 'error': 'トークンが設定されていません'})
        if not company_id:
            return jsonify({'success': False, 'error': '事業所IDが設定されていません'})

        data = request.json
        fixes = data.get('fixes', [])

        if not fixes:
            return jsonify({'success': False, 'error': '修正対象が指定されていません'})

        import requests as req
        BASE_URL = 'https://api.freee.co.jp/api/1'
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Api-Version': '2020-06-15',
            'Content-Type': 'application/json'
        }

        results = []
        for fix in fixes:
            deal_id = fix.get('deal_id')
            new_tax_code = fix.get('new_tax_code')

            try:
                # 取引詳細を取得（タイムアウト30秒）
                resp = req.get(f'{BASE_URL}/deals/{deal_id}',
                              headers=headers,
                              params={'company_id': company_id},
                              timeout=30)

                if resp.status_code != 200:
                    results.append({
                        'deal_id': deal_id,
                        'success': False,
                        'error': '取引が見つかりません'
                    })
                    continue

                deal = resp.json().get('deal', {})

                # 詳細を更新
                new_details = []
                for d in deal.get('details', []):
                    new_details.append({
                        'account_item_id': d['account_item_id'],
                        'tax_code': new_tax_code if d.get('tax_code') == fix.get('old_tax_code') else d.get('tax_code'),
                        'amount': d['amount'],
                        'description': d.get('description', '')
                    })

                update_data = {
                    'company_id': company_id,
                    'issue_date': deal['issue_date'],
                    'type': deal['type'],
                    'details': new_details
                }

                # 更新実行（タイムアウト30秒）
                update_resp = req.put(f'{BASE_URL}/deals/{deal_id}',
                                     headers=headers,
                                     json=update_data,
                                     timeout=30)

                if update_resp.status_code == 200:
                    results.append({
                        'deal_id': deal_id,
                        'success': True,
                        'message': f'税区分を{fix.get("old_tax_code")}→{new_tax_code}に修正'
                    })
                else:
                    error_msg = update_resp.json().get('errors', [{}])[0].get('messages', ['更新失敗'])
                    results.append({
                        'deal_id': deal_id,
                        'success': False,
                        'error': translate_error(str(error_msg))
                    })

            except Exception as e:
                results.append({
                    'deal_id': deal_id,
                    'success': False,
                    'error': translate_error(str(e))
                })

        success_count = sum(1 for r in results if r.get('success'))
        return jsonify({
            'success': True,
            'total': len(fixes),
            'succeeded': success_count,
            'failed': len(fixes) - success_count,
            'results': results
        })

    except Exception as e:
        return jsonify({'success': False, 'error': translate_error(str(e))})


def translate_error(error_msg):
    """エラーメッセージを日本語に翻訳（セキュリティ: 内部詳細を隠蔽）"""
    translations = {
        'expired_access_token': 'アクセストークンの有効期限が切れています。再取得してください。',
        'invalid_access_token': 'アクセストークンが無効です。',
        'rate limit exceeded': 'APIリクエスト制限を超えました。しばらく待ってから再試行してください。',
        'Unauthorized': '認証エラー: トークンを確認してください。',
        'Not Found': '取引が見つかりません。',
        '現在選択している会計年度の期首日以前の取引を編集することができません': '年度締め済みのため編集できません。freeeで年度締めを巻き戻す必要があります。',
        'Connection refused': 'サーバーに接続できません。',
        'timeout': 'リクエストがタイムアウトしました。',
        'ReadTimeout': 'リクエストがタイムアウトしました。',
        'ConnectTimeout': '接続がタイムアウトしました。',
        'ConnectionError': 'ネットワーク接続エラーが発生しました。',
        'SSLError': 'セキュア接続に失敗しました。',
        'JSONDecodeError': 'サーバーからの応答が不正です。',
        'KeyError': 'データ処理中にエラーが発生しました。',
        'ValueError': '入力データが不正です。',
        'TypeError': '処理中にエラーが発生しました。',
        'freeeアクセストークンが設定されていません': 'トークンが未設定です。WebUIでトークンを入力してください。',
    }

    for key, value in translations.items():
        if key.lower() in error_msg.lower():
            return value

    # 内部エラー詳細を隠蔽（パス情報やスタックトレースを含む場合）
    if any(x in error_msg for x in ['Traceback', 'File "', '\\', 'line ']):
        return '処理中にエラーが発生しました。'

    return error_msg


# ========================================
# MCP連携用エンドポイント
# ========================================

@app.route('/api/token', methods=['GET', 'POST'])
def handle_token():
    """トークンの保存・取得（MCP連携用）"""
    config = load_mcp_config()

    if request.method == 'POST':
        data = request.json
        token = data.get('token', '')
        config['token'] = token
        
        message = 'トークンを保存しました'
        company_name = ''

        # 事業所ID自動取得
        if token:
            try:
                # company_id なしでクライアント初期化
                client = FreeeClient(access_token=token, company_id=0) 
                companies = client.get_companies()
                
                if companies:
                    # 最初の事業所を自動選択
                    company = companies[0]
                    config['company_id'] = company['id']
                    company_name = company.get('display_name', company.get('name', ''))
                    message = f'トークンを保存し、事業所「{company_name}」を自動設定しました'
                else:
                    message = 'トークンを保存しましたが、事業所が見つかりませんでした'
                    
            except Exception as e:
                print(f"事業所自動取得エラー: {e}")
                message = 'トークンを保存しましたが、事業所情報の取得に失敗しました'
        
        save_mcp_config(config)
        return jsonify({
            'success': True, 
            'message': message,
            'company_name': company_name,
            'company_id': config.get('company_id')
        })
    else:
        # GETの場合はトークンの存在確認のみ
        has_token = bool(config.get('token'))
        company_id = config.get('company_id')
        return jsonify({'success': True, 'has_token': has_token, 'company_id': company_id})


@app.route('/api/upload/csv', methods=['POST'])
def upload_csv():
    """CSVファイルをアップロード（MCP連携用）"""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'ファイルがありません'})

    files = request.files.getlist('files')

    # ファイル数制限
    if len(files) > MAX_FILES_PER_REQUEST:
        return jsonify({
            'success': False,
            'error': f'一度にアップロードできるファイルは{MAX_FILES_PER_REQUEST}件までです'
        })

    saved_files = []
    skipped_files = []

    for file in files:
        if file.filename:
            # 拡張子検証
            if not validate_file_extension(file.filename, ALLOWED_CSV_EXTENSIONS):
                skipped_files.append({'name': file.filename, 'reason': 'CSVファイルのみ許可'})
                continue

            filename = safe_filename(file.filename)
            filepath = UPLOAD_CSV_DIR / filename

            # パストラバーサル最終チェック
            if not validate_file_path(filepath, UPLOAD_CSV_DIR):
                skipped_files.append({'name': file.filename, 'reason': '不正なファイルパス'})
                continue

            file.save(str(filepath))
            saved_files.append({
                'name': filename,
                'size': filepath.stat().st_size
            })

    return jsonify({
        'success': True,
        'files': saved_files,
        'skipped': skipped_files,
        'message': f'{len(saved_files)}件アップロード完了' + (f'、{len(skipped_files)}件スキップ' if skipped_files else '')
    })


@app.route('/api/upload/docs', methods=['POST'])
def upload_docs():
    """書類ファイルをアップロード（MCP連携用、ZIP展開対応）"""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'ファイルがありません'})

    files = request.files.getlist('files')

    # ファイル数制限
    if len(files) > MAX_FILES_PER_REQUEST:
        return jsonify({
            'success': False,
            'error': f'一度にアップロードできるファイルは{MAX_FILES_PER_REQUEST}件までです'
        })

    saved_files = []
    skipped_files = []
    extracted_files = []  # ZIPから展開されたファイル

    # ZIPから展開可能な拡張子
    extractable_extensions = {'.pdf', '.txt', '.md', '.json', '.xlsx', '.xls', '.doc', '.docx'}

    for file in files:
        if file.filename:
            # 拡張子検証
            if not validate_file_extension(file.filename, ALLOWED_DOC_EXTENSIONS):
                skipped_files.append({
                    'name': file.filename,
                    'reason': f'許可された形式: {", ".join(ALLOWED_DOC_EXTENSIONS)}'
                })
                continue

            filename = safe_filename(file.filename)
            ext = Path(filename).suffix.lower()

            # ZIPファイルの場合は展開
            if ext == '.zip':
                try:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_zip = Path(temp_dir) / filename
                        file.save(str(temp_zip))

                        with zipfile.ZipFile(temp_zip, 'r') as zf:
                            for zip_info in zf.infolist():
                                if zip_info.is_dir():
                                    continue

                                # ファイル名を取得（パスの最後の部分）
                                inner_filename = Path(zip_info.filename).name
                                inner_ext = Path(inner_filename).suffix.lower()

                                # 許可された拡張子のみ展開
                                if inner_ext not in extractable_extensions:
                                    skipped_files.append({
                                        'name': f'{filename}/{zip_info.filename}',
                                        'reason': '許可されていない形式'
                                    })
                                    continue

                                safe_inner = safe_filename(inner_filename)
                                dest_path = UPLOAD_DOCS_DIR / safe_inner

                                # パストラバーサルチェック
                                if not validate_file_path(dest_path, UPLOAD_DOCS_DIR):
                                    skipped_files.append({
                                        'name': f'{filename}/{zip_info.filename}',
                                        'reason': '不正なファイルパス'
                                    })
                                    continue

                                # 展開
                                with zf.open(zip_info) as src, open(dest_path, 'wb') as dst:
                                    dst.write(src.read())

                                extracted_files.append({
                                    'name': safe_inner,
                                    'size': dest_path.stat().st_size,
                                    'from_zip': filename
                                })

                except zipfile.BadZipFile:
                    skipped_files.append({'name': filename, 'reason': '無効なZIPファイル'})
                except Exception as e:
                    skipped_files.append({'name': filename, 'reason': f'展開エラー: {str(e)}'})
                continue

            # 通常ファイル
            filepath = UPLOAD_DOCS_DIR / filename

            # パストラバーサル最終チェック
            if not validate_file_path(filepath, UPLOAD_DOCS_DIR):
                skipped_files.append({'name': file.filename, 'reason': '不正なファイルパス'})
                continue

            file.save(str(filepath))
            saved_files.append({
                'name': filename,
                'size': filepath.stat().st_size
            })

    # 結果をまとめる
    all_saved = saved_files + extracted_files
    zip_msg = f'（ZIP展開: {len(extracted_files)}件）' if extracted_files else ''

    return jsonify({
        'success': True,
        'files': all_saved,
        'skipped': skipped_files,
        'message': f'{len(all_saved)}件アップロード完了{zip_msg}' + (f'、{len(skipped_files)}件スキップ' if skipped_files else '')
    })


@app.route('/api/files', methods=['GET'])
def list_files():
    """アップロード済みファイル一覧（MCP連携用）"""
    files = []

    # CSV
    if UPLOAD_CSV_DIR.exists():
        for f in UPLOAD_CSV_DIR.iterdir():
            if f.is_file():
                files.append({
                    'name': f.name,
                    'type': 'csv',
                    'size': f.stat().st_size,
                    'path': str(f)
                })

    # Docs
    if UPLOAD_DOCS_DIR.exists():
        for f in UPLOAD_DOCS_DIR.iterdir():
            if f.is_file():
                files.append({
                    'name': f.name,
                    'type': 'docs',
                    'size': f.stat().st_size,
                    'path': str(f)
                })

    return jsonify({'success': True, 'files': files})


@app.route('/api/files/<filename>', methods=['DELETE'])
def delete_file(filename):
    """ファイルを削除（パストラバーサル対策済み）"""
    # ファイル名をサニタイズ
    safe_name = safe_filename(filename)

    # CSVディレクトリを検索
    csv_path = UPLOAD_CSV_DIR / safe_name
    docs_path = UPLOAD_DOCS_DIR / safe_name

    # パストラバーサル対策: 解決後のパスがベースディレクトリ内か確認
    if csv_path.exists() and validate_file_path(csv_path, UPLOAD_CSV_DIR):
        csv_path.unlink()
        return jsonify({'success': True, 'message': f'{safe_name}を削除しました'})
    elif docs_path.exists() and validate_file_path(docs_path, UPLOAD_DOCS_DIR):
        docs_path.unlink()
        return jsonify({'success': True, 'message': f'{safe_name}を削除しました'})
    else:
        return jsonify({'success': False, 'error': 'ファイルが見つかりません'})


# ========================================
# 監査結果エクスポート機能
# ========================================

@app.route('/api/audit/export', methods=['GET'])
def export_audit():
    """
    監査結果をCSV形式でエクスポート

    クエリパラメータ:
        format: 出力形式 ('csv' または 'json', デフォルト: csv)

    使用例:
        curl "http://localhost:5000/api/audit/export?format=csv" -o audit_report.csv
    """
    try:
        import io
        import csv as csv_module
        from flask import Response

        result_file = DATA_DIR / "tax_check_result.json"

        if not result_file.exists():
            return jsonify({'success': False, 'error': '監査結果がありません。先に監査を実行してください。'})

        result_data = json.loads(result_file.read_text(encoding='utf-8'))
        export_format = request.args.get('format', 'csv').lower()

        if export_format == 'json':
            # JSON形式でダウンロード
            response = Response(
                json.dumps(result_data, ensure_ascii=False, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment; filename=audit_report.json'}
            )
            return response

        # CSV形式でエクスポート
        output = io.StringIO()
        writer = csv_module.writer(output)

        # ヘッダー
        writer.writerow(['カテゴリ', 'タイトル', 'リスクレベル', '金額', '説明', '推奨アクション'])

        # 問題リスト
        issues = result_data.get('issues', [])
        for issue in issues:
            writer.writerow([
                issue.get('category', ''),
                issue.get('title', ''),
                issue.get('risk_level', ''),
                issue.get('amount', ''),
                issue.get('description', ''),
                issue.get('suggestion', '')
            ])

        # サマリー行を追加
        writer.writerow([])
        writer.writerow(['=== サマリー ==='])
        writer.writerow(['取引件数', result_data.get('deal_count', 0)])
        writer.writerow(['エラー数', result_data.get('errors', 0)])
        writer.writerow(['警告数', result_data.get('warnings', 0)])

        output.seek(0)

        # BOM付きUTF-8でExcelでも文字化けしないように
        bom = '\ufeff'
        response = Response(
            bom + output.getvalue(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=audit_report.csv'}
        )
        return response

    except Exception as e:
        import logging
        logging.error(f"Export error: {e}")
        return jsonify({'success': False, 'error': 'エクスポートに失敗しました'})


@app.route('/api/audit/save', methods=['POST'])
def save_audit_result():
    """
    監査結果を保存（AI向けエンドポイント）

    リクエストボディ:
        {
            "issues": [...],
            "deal_count": 100,
            "errors": 5,
            "warnings": 10,
            "report": "...",
            "details": {...}
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': '保存するデータがありません'})

        # 保存日時を追加
        data['saved_at'] = datetime.now().isoformat()

        result_file = DATA_DIR / "tax_check_result.json"
        result_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        return jsonify({
            'success': True,
            'message': '監査結果を保存しました',
            'file': str(result_file)
        })

    except Exception as e:
        import logging
        logging.error(f"Save audit error: {e}")
        return jsonify({'success': False, 'error': '保存に失敗しました'})


# ========================================
# メイン
# ========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'false').lower() == 'true'

    print("=" * 60)
    print("バーチャル税務調査～経理丸投げちゃん～")
    print("=" * 60)
    print()
    print(f"  ブラウザで http://localhost:{port} を開いてください")
    print()
    print("  ポート変更: PORT=8080 python server.py")
    print("  デバッグモード: DEBUG=true python server.py")
    print("  終了: Ctrl+C")
    print("=" * 60)

    app.run(host='127.0.0.1', port=port, debug=debug_mode)


# ========================================
# バーチャル税務調査～経理丸投げちゃん～
# Copyright (c) 2025 株式会社CLAN (https://clanbiz.net/keiri-marunage-chan-LP/)
# Licensed under MIT License
# ========================================
