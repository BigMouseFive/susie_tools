// ===== 全局状态 =====
let jobsData = [];      // 当前任务列表缓存
let sseSource = null;   // EventSource 实例

// ===== DOM 元素 =====
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileNameEl = document.getElementById('fileName');
const startBtn = document.getElementById('startBtn');
const uploadStatus = document.getElementById('uploadStatus');

const queueSizeEl = document.getElementById('queueSize');
const runningCountEl = document.getElementById('runningCount');
const completedCountEl = document.getElementById('completedCount');
const currentTaskEl = document.getElementById('currentTask');
const jobsTbody = document.getElementById('jobsTbody');

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    initUpload();
    loadJobs();
    connectSSE();
});

// ===== 上传交互 =====
function initUpload() {
    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFile(files[0]);
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
    });

    startBtn.addEventListener('click', startUpload);
}

function handleFile(file) {
    const ok = file.name.endsWith('.csv') || file.name.endsWith('.txt');
    if (!ok) {
        showStatus('仅支持 .csv 和 .txt 格式', 'error');
        return;
    }
    fileInput._selectedFile = file;
    fileNameEl.textContent = file.name;
    fileInfo.style.display = 'flex';
    uploadStatus.textContent = '';
    uploadStatus.className = 'upload-status';
}

async function startUpload() {
    const file = fileInput._selectedFile;
    if (!file) return;

    startBtn.disabled = true;
    startBtn.textContent = '上传中...';
    showStatus('正在解析并创建任务...', 'info');

    const form = new FormData();
    form.append('file', file);

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: form });
        const data = await res.json();
        if (data.success) {
            showStatus(`任务创建成功: ${data.total} 个 URL 已入队`, 'success');
            fileInput._selectedFile = null;
            fileInfo.style.display = 'none';
            fileInput.value = '';
            loadJobs();
        } else {
            showStatus(data.error || '上传失败', 'error');
        }
    } catch (err) {
        showStatus('网络错误: ' + err.message, 'error');
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = '开始提取';
    }
}

function showStatus(msg, type) {
    uploadStatus.textContent = msg;
    uploadStatus.className = 'upload-status ' + type;
}

// ===== SSE 实时推送 =====
function connectSSE() {
    if (sseSource) {
        try { sseSource.close(); } catch (e) {}
    }

    sseSource = new EventSource('/api/stream');

    sseSource.addEventListener('status', (e) => {
        try {
            const data = JSON.parse(e.data);
            updateStatusPanel(data);
        } catch (err) {}
    });

    sseSource.addEventListener('progress', (e) => {
        try {
            const data = JSON.parse(e.data);
            handleProgress(data);
        } catch (err) {}
    });

    sseSource.addEventListener('job_added', (e) => {
        try {
            const job = JSON.parse(e.data);
            addOrUpdateJob(job);
        } catch (err) {}
    });

    sseSource.addEventListener('job_complete', (e) => {
        try {
            const data = JSON.parse(e.data);
            const job = data.job || data;
            addOrUpdateJob(job);
            updateCurrentTask(null);
        } catch (err) {}
    });

    sseSource.addEventListener('job_cancelled', (e) => {
        loadJobs(); // 全量刷新
    });

    sseSource.onerror = () => {
        console.warn('SSE 断开，5秒后重连...');
        setTimeout(connectSSE, 5000);
    };
}

// ===== 状态面板更新 =====
function updateStatusPanel(data) {
    const jobs = data.jobs || [];
    const queueSize = data.queue_size || 0;

    let running = 0;
    let completed = 0;
    jobs.forEach(j => {
        if (j.status === 'running') running++;
        else if (j.status === 'completed') completed++;
    });

    queueSizeEl.textContent = queueSize;
    runningCountEl.textContent = running;
    completedCountEl.textContent = completed;

    // 更新当前任务显示
    if (data.current) {
        updateCurrentTask(data.current);
    } else if (queueSize === 0 && running === 0) {
        updateCurrentTask(null);
    }

    // 同步任务列表
    jobs.forEach(j => addOrUpdateJob(j));
}

function updateCurrentTask(current) {
    if (!current) {
        currentTaskEl.innerHTML = '<p class="idle-text">暂无运行中的任务</p>';
        return;
    }
    const asin = extractAsin(current.url) || '';
    currentTaskEl.innerHTML = `
        <div class="task-line"><strong>当前处理:</strong> ${asin || current.url.substring(0, 60)}</div>
        <div class="task-line" style="color:#888;font-size:0.8rem;">${current.url}</div>
    `;
}

function extractAsin(url) {
    if (!url) return '';
    const m = url.match(/\/dp\/([A-Z0-9]{10})/i);
    return m ? m[1].toUpperCase() : '';
}

// ===== 进度处理 =====
function handleProgress(data) {
    const job = jobsData.find(j => j.id === data.job_id);
    if (!job) {
        loadJobs();
        return;
    }

    if (data.type === 'start') {
        job.status = 'running';
        updateCurrentTask({ url: data.url });
    } else if (data.type === 'done' || data.type === 'error') {
        job.processed = data.job_processed || job.processed;
        if (data.type === 'done' && data.status === 'success') {
            job.success = (job.success || 0) + 1;
        } else {
            job.failed = (job.failed || 0) + 1;
        }
    }

    renderJobs();
    updateStatusPanel({
        queue_size: data.queue_left || 0,
        jobs: jobsData,
        current: data.type === 'start' ? { url: data.url } : null
    });
}

// ===== 任务列表管理 =====
async function loadJobs() {
    try {
        const res = await fetch('/api/jobs');
        const data = await res.json();
        jobsData = data.jobs || [];
        renderJobs();
        updateStatusPanel(data);
    } catch (err) {
        console.error('加载任务失败', err);
    }
}

function addOrUpdateJob(job) {
    const idx = jobsData.findIndex(j => j.id === job.id);
    if (idx >= 0) {
        jobsData[idx] = { ...jobsData[idx], ...job };
    } else {
        jobsData.push(job);
    }
    // 按创建时间倒序
    jobsData.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    renderJobs();
}

function renderJobs() {
    if (jobsData.length === 0) {
        jobsTbody.innerHTML = '<tr class="empty-row"><td colspan="7">暂无任务，请上传文件开始</td></tr>';
        return;
    }

    jobsTbody.innerHTML = jobsData.map(job => {
        const total = job.total || 0;
        const processed = job.processed || 0;
        const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
        const isRunning = job.status === 'running';

        let badgeClass = 'badge-pending';
        let badgeText = '等待中';
        if (job.status === 'running') { badgeClass = 'badge-running'; badgeText = '运行中'; }
        else if (job.status === 'completed') { badgeClass = 'badge-completed'; badgeText = '已完成'; }
        else if (job.status === 'cancelled') { badgeClass = 'badge-cancelled'; badgeText = '已取消'; }

        let actions = '';
        if (job.status === 'running' || job.status === 'pending') {
            actions += `<button class="btn btn-danger btn-sm" onclick="cancelJob('${job.id}')">取消</button>`;
        }
        if (job.status === 'completed' || job.status === 'cancelled') {
            actions += `<button class="btn btn-success btn-sm" onclick="downloadJob('${job.id}')">下载</button>`;
        }

        return `
            <tr data-id="${job.id}">
                <td>${escapeHtml(job.name)}</td>
                <td>${total}</td>
                <td>${job.success || 0}</td>
                <td>${job.failed || 0}</td>
                <td class="td-progress">
                    <div class="progress-text">${processed} / ${total} (${pct}%)</div>
                    <div class="progress-mini-bg">
                        <div class="progress-mini-fill ${isRunning ? 'pulsing' : ''}" style="width:${pct}%"></div>
                    </div>
                </td>
                <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                <td class="td-actions">${actions}</td>
            </tr>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== 操作 =====
async function cancelJob(jobId) {
    if (!confirm('确定要取消该任务吗？')) return;
    try {
        const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            loadJobs();
        } else {
            alert(data.error || '取消失败');
        }
    } catch (err) {
        alert('网络错误');
    }
}

function downloadJob(jobId) {
    window.open(`/api/jobs/${jobId}/download`, '_blank');
}

// 暴露到全局供 onclick 使用
window.cancelJob = cancelJob;
window.downloadJob = downloadJob;
