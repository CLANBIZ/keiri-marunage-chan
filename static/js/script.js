/**
 * バーチャル税務調査～経理丸投げちゃん～ フロントエンドスクリプト
 * セキュリティ強化版: sessionStorage使用、エラーハンドリング改善
 */
document.addEventListener('DOMContentLoaded', () => {
    // ========================================
    // Configuration
    // ========================================
    const API_BASE = '/api';
    const BATCH_SIZE = 50;
    const MAX_RETRIES = 3;
    const TOKEN_VALIDITY_HOURS = 6;
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

    // ========================================
    // State
    // ========================================
    const state = {
        csvFiles: [],
        docsFiles: [],
        uploadAbortController: null,
        isUploading: false
    };

    // ========================================
    // UI Components
    // ========================================
    const ui = {
        toastContainer: document.getElementById('toastContainer'),
        csvDropZone: document.getElementById('csvDropZone'),
        docsDropZone: document.getElementById('docsDropZone'),
        csvInput: document.getElementById('csvInput'),
        docsInput: document.getElementById('docsInput'),
        docsFolderInput: document.getElementById('docsFolderInput'),
        csvFileList: document.getElementById('csvFileList'),
        docsFileList: document.getElementById('docsFileList'),
        csvProgress: document.getElementById('csvProgress'),
        docsProgress: document.getElementById('docsProgress'),
        tokenInput: document.getElementById('accessToken'),
        tokenTimer: document.getElementById('tokenTimer'),
        tokenTimerText: document.getElementById('tokenTimerText'),
        tokenTimerIcon: document.getElementById('tokenTimerIcon')
    };

    // ========================================
    // Utilities
    // ========================================
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            csv: '📊',
            pdf: '📄',
            xlsx: '📗',
            xls: '📗',
            doc: '📘',
            docx: '📘',
            txt: '📝',
            md: '📝',
            json: '📋',
            zip: '📦'
        };
        return icons[ext] || '📁';
    }

    // ========================================
    // Toast Notifications
    // ========================================
    function showToast(message, type = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.setAttribute('role', 'alert');

        const icons = {
            success: '✓',
            error: '✕',
            info: 'ℹ',
            warning: '⚠'
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${escapeHtml(message)}</span>
        `;

        ui.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease-out forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========================================
    // File Validation
    // ========================================
    function validateFile(file, type) {
        const errors = [];

        // Size check
        if (file.size > MAX_FILE_SIZE) {
            errors.push(`${file.name}: ファイルサイズが50MBを超えています`);
        }

        // Extension check
        const ext = file.name.split('.').pop().toLowerCase();
        const allowedCsv = ['csv'];
        const allowedDocs = ['pdf', 'txt', 'md', 'json', 'zip'];

        if (type === 'csv' && !allowedCsv.includes(ext)) {
            errors.push(`${file.name}: CSVファイルのみアップロード可能です`);
        }
        if (type === 'docs' && !allowedDocs.includes(ext)) {
            errors.push(`${file.name}: 許可されていないファイル形式です`);
        }

        return errors;
    }

    // ========================================
    // Folder Drop Support
    // ========================================
    async function getAllFilesFromDataTransfer(items) {
        const files = [];
        const entries = [];

        // DataTransferItemListからエントリを取得
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.webkitGetAsEntry) {
                const entry = item.webkitGetAsEntry();
                if (entry) {
                    entries.push(entry);
                }
            } else if (item.kind === 'file') {
                const file = item.getAsFile();
                if (file) {
                    files.push(file);
                }
            }
        }

        // エントリを再帰的に処理
        for (const entry of entries) {
            const entryFiles = await readEntryRecursively(entry);
            files.push(...entryFiles);
        }

        return files;
    }

    async function readEntryRecursively(entry) {
        const files = [];

        if (entry.isFile) {
            // ファイルの場合
            const file = await new Promise((resolve) => {
                entry.file(resolve);
            });
            files.push(file);
        } else if (entry.isDirectory) {
            // ディレクトリの場合、中身を読み込む
            const reader = entry.createReader();
            const entries = await readAllDirectoryEntries(reader);
            for (const childEntry of entries) {
                const childFiles = await readEntryRecursively(childEntry);
                files.push(...childFiles);
            }
        }

        return files;
    }

    async function readAllDirectoryEntries(reader) {
        const entries = [];
        let batch;

        // readEntriesは一度に100件程度しか返さないことがあるため、
        // 空になるまで繰り返し読み込む
        do {
            batch = await new Promise((resolve) => {
                reader.readEntries(resolve);
            });
            entries.push(...batch);
        } while (batch.length > 0);

        return entries;
    }

    // ========================================
    // Drop Zone Setup
    // ========================================
    function setupDropZone(dropZone, input, type) {
        if (!dropZone || !input) return;

        // Drag events
        ['dragenter', 'dragover'].forEach(event => {
            dropZone.addEventListener(event, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(event => {
            dropZone.addEventListener(event, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('dragover');
            });
        });

        // Drop handler (フォルダ対応)
        dropZone.addEventListener('drop', async (e) => {
            const items = e.dataTransfer.items;
            if (items && items.length > 0) {
                const files = await getAllFilesFromDataTransfer(items);
                if (files.length > 0) {
                    handleFiles(files, type);
                }
            } else {
                // Fallback for browsers without items support
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    handleFiles(files, type);
                }
            }
        });

        // Click handler
        dropZone.addEventListener('click', () => {
            input.click();
        });

        // Keyboard handler (アクセシビリティ)
        dropZone.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                input.click();
            }
        });

        // File input change
        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                handleFiles(input.files, type);
                input.value = ''; // Reset for same file re-upload
            }
        });
    }

    // ========================================
    // File Handling
    // ========================================
    function handleFiles(files, type) {
        const validFiles = [];
        const errors = [];

        Array.from(files).forEach(file => {
            const fileErrors = validateFile(file, type);
            if (fileErrors.length > 0) {
                errors.push(...fileErrors);
            } else {
                validFiles.push(file);
            }
        });

        // Show validation errors
        errors.forEach(error => showToast(error, 'error'));

        if (validFiles.length === 0) return;

        // Add to state
        if (type === 'csv') {
            state.csvFiles = [...state.csvFiles, ...validFiles];
            renderFileList('csv');
            uploadFiles(validFiles, 'csv');
        } else {
            state.docsFiles = [...state.docsFiles, ...validFiles];
            renderFileList('docs');
            uploadFiles(validFiles, 'docs');
        }
    }

    // ========================================
    // File List Rendering
    // ========================================
    function renderFileList(type) {
        const files = type === 'csv' ? state.csvFiles : state.docsFiles;
        const container = type === 'csv' ? ui.csvFileList : ui.docsFileList;

        if (!container) return;

        if (files.length === 0) {
            container.innerHTML = '';
            return;
        }

        // Summary
        const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0);

        container.innerHTML = `
            <div class="file-summary">
                <span>${files.length}件のファイル</span>
                <span>${formatFileSize(totalSize)}</span>
            </div>
            ${files.map((file, index) => `
                <div class="file-item" data-index="${index}">
                    <span class="file-icon">${getFileIcon(file.name)}</span>
                    <div class="file-info">
                        <span class="file-name">${escapeHtml(file.name)}</span>
                        <span class="file-size">${formatFileSize(file.size || 0)}</span>
                    </div>
                    <button class="btn-icon" onclick="removeFile('${type}', ${index})"
                            aria-label="${file.name}を削除" title="削除">
                        ✕
                    </button>
                </div>
            `).join('')}
        `;
    }

    // Global function for onclick
    window.removeFile = function(type, index) {
        if (type === 'csv') {
            state.csvFiles.splice(index, 1);
        } else {
            state.docsFiles.splice(index, 1);
        }
        renderFileList(type);
        saveToSessionStorage();
    };

    // ========================================
    // File Upload
    // ========================================
    async function uploadFiles(files, type) {
        const endpoint = type === 'csv' ? '/api/upload/csv' : '/api/upload/docs';
        const progressContainer = type === 'csv' ? ui.csvProgress : ui.docsProgress;
        const progressBar = progressContainer?.querySelector('.progress-bar');

        if (!progressContainer || !progressBar) return;

        state.isUploading = true;
        progressContainer.classList.add('active');
        progressBar.style.width = '0%';

        try {
            // Batch upload
            for (let i = 0; i < files.length; i += BATCH_SIZE) {
                const batch = files.slice(i, i + BATCH_SIZE);
                const formData = new FormData();

                batch.forEach(file => {
                    formData.append('files', file);
                });

                const response = await fetch(endpoint, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`アップロードエラー: ${response.status}`);
                }

                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.error || 'アップロードに失敗しました');
                }

                // Update progress
                const progress = Math.round(((i + batch.length) / files.length) * 100);
                progressBar.style.width = `${progress}%`;

                // Show skipped files if any
                if (result.skipped && result.skipped.length > 0) {
                    result.skipped.forEach(skip => {
                        showToast(`${skip.name}: ${skip.reason}`, 'warning');
                    });
                }
            }

            showToast(`${files.length}件のファイルをアップロードしました`, 'success');
            saveToSessionStorage();

        } catch (error) {
            console.error('Upload error:', error);
            showToast(error.message || 'アップロードに失敗しました', 'error');
        } finally {
            state.isUploading = false;
            setTimeout(() => {
                progressContainer.classList.remove('active');
                progressBar.style.width = '0%';
            }, 1000);
        }
    }

    // ========================================
    // Token Management (sessionStorage使用)
    // ========================================
    async function saveToken() {
        const token = ui.tokenInput.value.trim();

        // sessionStorageに保存（ブラウザタブ閉じると消える = より安全）
        sessionStorage.setItem('freee_token', token);

        if (token && !sessionStorage.getItem('freee_token_time')) {
            sessionStorage.setItem('freee_token_time', Date.now().toString());
        }

        updateTokenTimer();

        if (!token) return;

        try {
            const resp = await fetch(`${API_BASE}/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });
            const result = await resp.json();

            if (result.success) {
                showToast(result.message || 'トークンを保存しました', 'success');
                if (result.company_name) {
                    showToast(`事業所: ${result.company_name}`, 'info');
                }
            } else {
                showToast(result.error || '設定の保存に失敗しました', 'error');
            }
        } catch (e) {
            console.error('Token save error:', e);
            showToast('サーバーとの通信に失敗しました', 'error');
        }
    }

    function updateTokenTimer() {
        const token = ui.tokenInput?.value;
        const tokenTime = sessionStorage.getItem('freee_token_time');

        if (!token || !tokenTime || !ui.tokenTimer) {
            if (ui.tokenTimer) ui.tokenTimer.classList.add('hidden');
            return;
        }

        ui.tokenTimer.classList.remove('hidden');
        const savedTime = parseInt(tokenTime);
        const expiryTime = savedTime + (TOKEN_VALIDITY_HOURS * 60 * 60 * 1000);
        const remaining = expiryTime - Date.now();

        // Reset classes
        ui.tokenTimer.className = 'badge';

        if (remaining <= 0) {
            ui.tokenTimer.classList.add('badge-error');
            if (ui.tokenTimerIcon) ui.tokenTimerIcon.textContent = '⚠';
            if (ui.tokenTimerText) ui.tokenTimerText.textContent = '期限切れ - 再取得してください';
        } else if (remaining < 30 * 60 * 1000) {
            ui.tokenTimer.classList.add('badge-warning');
            if (ui.tokenTimerIcon) ui.tokenTimerIcon.textContent = '⚠';
            if (ui.tokenTimerText) ui.tokenTimerText.textContent = `残り ${Math.ceil(remaining / 60000)}分`;
        } else {
            ui.tokenTimer.classList.add('badge-success');
            if (ui.tokenTimerIcon) ui.tokenTimerIcon.textContent = '✓';
            const hours = Math.floor(remaining / 3600000);
            const mins = Math.floor((remaining % 3600000) / 60000);
            if (ui.tokenTimerText) ui.tokenTimerText.textContent = `有効: 残り${hours}時間${mins}分`;
        }
    }

    // ========================================
    // Session Storage Management
    // ========================================
    function loadFromSessionStorage() {
        const token = sessionStorage.getItem('freee_token');

        if (token && ui.tokenInput) {
            ui.tokenInput.value = token;
        }

        // Restore file lists (names only for display)
        try {
            const savedCsv = JSON.parse(sessionStorage.getItem('csv_files') || '[]');
            const savedDocs = JSON.parse(sessionStorage.getItem('docs_files') || '[]');

            state.csvFiles = savedCsv.map(name => ({ name, size: 0 }));
            state.docsFiles = savedDocs.map(name => ({ name, size: 0 }));

            renderFileList('csv');
            renderFileList('docs');
        } catch (e) {
            console.error('Failed to load saved files', e);
        }

        updateTokenTimer();
        setInterval(updateTokenTimer, 60000); // Update every minute
    }

    function saveToSessionStorage() {
        sessionStorage.setItem('csv_files', JSON.stringify(state.csvFiles.map(f => f.name)));
        sessionStorage.setItem('docs_files', JSON.stringify(state.docsFiles.map(f => f.name)));
    }

    // ========================================
    // Debounced Save
    // ========================================
    let saveTimeout = null;
    function debouncedSave() {
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(saveToken, 800);
    }

    // ========================================
    // Initialization
    // ========================================
    setupDropZone(ui.csvDropZone, ui.csvInput, 'csv');
    setupDropZone(ui.docsDropZone, ui.docsInput, 'docs');

    // Folder input for docs
    if (ui.docsFolderInput) {
        ui.docsFolderInput.addEventListener('change', () => {
            handleFiles(ui.docsFolderInput.files, 'docs');
            ui.docsFolderInput.value = '';
        });
    }

    // Token input handler
    if (ui.tokenInput) {
        ui.tokenInput.addEventListener('input', () => {
            // Reset timer on new token
            if (ui.tokenInput.value !== sessionStorage.getItem('freee_token')) {
                sessionStorage.setItem('freee_token_time', Date.now().toString());
            }
            debouncedSave();
        });
    }

    // Load saved state
    loadFromSessionStorage();

    console.log('バーチャル税務調査～経理丸投げちゃん～ v1.0.0 - initialized');
});

// ========================================
// バーチャル税務調査～経理丸投げちゃん～
// Copyright (c) 2025 株式会社CLAN (https://clanbiz.net/keiri-marunage-chan-LP/)
// Licensed under MIT License
// ========================================
