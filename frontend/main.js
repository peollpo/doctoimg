// ===== 认证管理 =====
const AUTH_TOKEN_KEY = 'doctoimg_token';
const AUTH_USER_KEY = 'doctoimg_user';

const getToken = () => localStorage.getItem(AUTH_TOKEN_KEY);
const setToken = (token) => localStorage.setItem(AUTH_TOKEN_KEY, token);
const removeToken = () => localStorage.removeItem(AUTH_TOKEN_KEY);

const getUser = () => {
  const userJson = localStorage.getItem(AUTH_USER_KEY);
  return userJson ? JSON.parse(userJson) : null;
};
const setUser = (user) => localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
const removeUser = () => localStorage.removeItem(AUTH_USER_KEY);

const strapiBase = 'http://localhost:1337';
const apiBase = window.location.origin;

// ===== DOM 元素 =====
const loginPanel = document.getElementById('login-panel');
const mainPanel = document.getElementById('main-panel');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const uploadForm = document.getElementById('upload-form');
const logoutBtn = document.getElementById('logout-btn');
const userEmailSpan = document.getElementById('user-email');
const tasksContainer = document.getElementById('tasks');
const template = document.getElementById('task-template');
const colorPicker = document.getElementById('color-picker');
const imagePicker = document.getElementById('image-picker');
const fileInput = document.getElementById('file-input');
const folderBtn = document.getElementById('folder-btn');
const fileCount = document.getElementById('file-count');

const pollIntervals = new Map();
const activeBatches = new Map(); // 跟踪活跃的批次: batch_id -> {taskIds: Set, completed: Set, container: Element}

// ===== 文件夹处理逻辑 =====
const ALLOWED_EXTENSIONS = ['.doc', '.docx', '.pdf'];

const filterDocumentFiles = (files) => {
  return Array.from(files).filter(file => {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    return ALLOWED_EXTENSIONS.includes(ext);
  });
};

const updateFileCount = (count) => {
  if (count > 0) {
    fileCount.textContent = `${count} document(s) selected`;
    fileCount.hidden = false;
  } else {
    fileCount.hidden = true;
  }
};

folderBtn.addEventListener('click', () => {
  // 创建隐藏的文件夹选择input
  const folderInput = document.createElement('input');
  folderInput.type = 'file';
  folderInput.webkitdirectory = true;
  folderInput.multiple = true;

  folderInput.onchange = (e) => {
    const allFiles = e.target.files;
    const documentFiles = filterDocumentFiles(allFiles);

    if (documentFiles.length === 0) {
      alert('No supported documents found in the selected folder (.doc, .docx, .pdf)');
      return;
    }

    // 将文件列表转移到主文件输入
    const dataTransfer = new DataTransfer();
    documentFiles.forEach(file => dataTransfer.items.add(file));
    fileInput.files = dataTransfer.files;

    updateFileCount(documentFiles.length);
  };

  folderInput.click();
});

fileInput.addEventListener('change', (e) => {
  const files = filterDocumentFiles(e.target.files);
  updateFileCount(files.length);
});

// ===== 登录逻辑 =====
const showError = (message) => {
  loginError.textContent = message;
  loginError.hidden = false;
};

const hideError = () => {
  loginError.hidden = true;
};

const showMainPanel = (user) => {
  loginPanel.hidden = true;
  mainPanel.hidden = false;
  userEmailSpan.textContent = user.email || user.username || 'User';
};

const showLoginPanel = () => {
  loginPanel.hidden = false;
  mainPanel.hidden = true;
  hideError();
};

const login = async (identifier, password) => {
  try {
    const res = await fetch(`${strapiBase}/api/auth/local`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password }),
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.message?.[0]?.messages?.[0]?.message || 'Login failed');
    }

    const data = await res.json();
    setToken(data.jwt);
    setUser(data.user);
    return data.user;
  } catch (error) {
    throw error;
  }
};

const logout = () => {
  removeToken();
  removeUser();
  showLoginPanel();
  tasksContainer.innerHTML = '';
  pollIntervals.forEach((interval) => clearInterval(interval));
  pollIntervals.clear();
};

// ===== 任务管理 =====
const setStatusMessage = (taskEl, message) => {
  const detail = taskEl.querySelector('.detail');
  detail.textContent = message || '';
};

const setState = (taskEl, state) => {
  taskEl.querySelector('.state').textContent = state;
};

const setDownload = (taskEl, url) => {
  const link = taskEl.querySelector('.download');
  if (url) {
    link.onclick = async (e) => {
      e.preventDefault();
      const token = getToken();
      if (!token) {
        logout();
        alert('Please log in first');
        return;
      }

      try {
        const res = await fetch(url, {
          headers: { 'Authorization': `Bearer ${token}` },
        });

        if (res.status === 401) {
          logout();
          alert('Session expired. Please log in again.');
          return;
        }

        if (!res.ok) {
          throw new Error('Download failed');
        }

        const blob = await res.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `result-${Date.now()}.zip`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        document.body.removeChild(a);
      } catch (error) {
        alert(`Download failed: ${error.message}`);
      }
    };
    link.hidden = false;
  } else {
    link.hidden = true;
  }
};

const createBatchDownloadButton = (batchId) => {
  const btn = document.createElement('a');
  btn.className = 'download batch-download';
  btn.textContent = 'Download All (Batch)';
  btn.style.background = '#3b82f6';
  btn.onclick = async (e) => {
    e.preventDefault();
    const token = getToken();
    if (!token) {
      logout();
      alert('Please log in first');
      return;
    }

    try {
      const res = await fetch(`${apiBase}/batches/${batchId}/download`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (res.status === 401) {
        logout();
        alert('Session expired. Please log in again.');
        return;
      }

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || 'Batch download failed');
      }

      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `batch-${batchId}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
    } catch (error) {
      alert(`Batch download failed: ${error.message}`);
    }
  };
  return btn;
};

const renderTask = (task) => {
  let taskEl = document.getElementById(`task-${task.task_id}`);
  if (!taskEl) {
    const fragment = template.content.cloneNode(true);
    taskEl = fragment.querySelector('.task');
    taskEl.id = `task-${task.task_id}`;
    taskEl.querySelector('h3').textContent = task.task_id;

    // 如果任务属于批次,添加到批次容器中
    if (task.batch_id && activeBatches.has(task.batch_id)) {
      const batch = activeBatches.get(task.batch_id);
      batch.container.appendChild(fragment);
    } else {
      tasksContainer.prepend(fragment);
    }
  }
  setState(taskEl, task.state);
  setStatusMessage(taskEl, task.detail);
  if (task.download_url) {
    setDownload(taskEl, task.download_url);
  }

  // 批次跟踪逻辑
  if (task.batch_id && task.state === 'completed') {
    const batch = activeBatches.get(task.batch_id);
    if (batch) {
      batch.completed.add(task.task_id);
      // 检查是否所有任务都已完成
      if (batch.completed.size === batch.taskIds.size && !batch.container.querySelector('.batch-download')) {
        const batchBtn = createBatchDownloadButton(task.batch_id);
        batch.container.prepend(batchBtn);
      }
    }
  }
};

const pollTask = (taskId) => {
  if (pollIntervals.has(taskId)) return;
  const interval = setInterval(async () => {
    try {
      const token = getToken();
      if (!token) {
        clearInterval(interval);
        pollIntervals.delete(taskId);
        return;
      }

      const res = await fetch(`${apiBase}/tasks/${taskId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (res.status === 401) {
        logout();
        clearInterval(interval);
        pollIntervals.delete(taskId);
        alert('Session expired. Please log in again.');
        return;
      }

      if (!res.ok) throw new Error(`Failed to fetch status: ${res.status}`);
      const data = await res.json();
      renderTask(data);
      if (data.state === 'completed' || data.state === 'failed') {
        clearInterval(interval);
        pollIntervals.delete(taskId);
      }
    } catch (error) {
      console.error(error);
    }
  }, 3000);
  pollIntervals.set(taskId, interval);
};

const toggleBackgroundControls = (type) => {
  colorPicker.hidden = type !== 'color';
  imagePicker.hidden = type !== 'image';
};

// ===== 事件监听器 =====
loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  hideError();

  const formData = new FormData(loginForm);
  const identifier = formData.get('identifier');
  const password = formData.get('password');

  const submitBtn = loginForm.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Logging in...';

  try {
    const user = await login(identifier, password);
    showMainPanel(user);
    loginForm.reset();
  } catch (error) {
    showError(error.message || 'Login failed. Please check your credentials.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Log In';
  }
});

logoutBtn.addEventListener('click', logout);

uploadForm.addEventListener('change', (event) => {
  if (event.target.name === 'background_type') {
    toggleBackgroundControls(event.target.value);
  }
});

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const token = getToken();
  if (!token) {
    logout();
    alert('Please log in first');
    return;
  }

  const formData = new FormData(uploadForm);
  const bgType = formData.get('background_type');
  if (bgType !== 'color') {
    formData.delete('background_color');
  }
  if (bgType !== 'image') {
    formData.delete('background_image');
  }

  try {
    const submitBtn = uploadForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    const res = await fetch(`${apiBase}/tasks`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });

    if (res.status === 401) {
      logout();
      alert('Session expired. Please log in again.');
      return;
    }

    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(error.detail || 'Upload failed');
    }

    const tasks = await res.json();
    // 处理可能返回的多个任务
    if (Array.isArray(tasks)) {
      // 如果有批次 ID,初始化批次跟踪容器
      if (tasks.length > 0 && tasks[0].batch_id) {
        const batchId = tasks[0].batch_id;
        const batchContainer = document.createElement('div');
        batchContainer.className = 'batch-container';
        batchContainer.style.border = '2px solid #3b82f6';
        batchContainer.style.borderRadius = '12px';
        batchContainer.style.padding = '1rem';
        batchContainer.style.marginBottom = '1.5rem';

        const batchTitle = document.createElement('h3');
        batchTitle.textContent = `Batch: ${batchId.substring(0, 8)}... (${tasks.length} files)`;
        batchTitle.style.marginTop = '0';
        batchTitle.style.color = '#3b82f6';
        batchContainer.appendChild(batchTitle);

        tasksContainer.prepend(batchContainer);

        activeBatches.set(batchId, {
          taskIds: new Set(tasks.map(t => t.task_id)),
          completed: new Set(),
          container: batchContainer
        });
      }

      tasks.forEach(task => {
        renderTask(task);
        pollTask(task.task_id);
      });
    } else {
      renderTask(tasks);
      pollTask(tasks.task_id);
    }

    uploadForm.reset();
    toggleBackgroundControls('none');
    updateFileCount(0);
  } catch (error) {
    alert(error.message);
  } finally {
    uploadForm.querySelector('button[type="submit"]').disabled = false;
  }
});

// ===== 初始化 =====
const init = () => {
  const token = getToken();
  const user = getUser();

  if (token && user) {
    showMainPanel(user);
  } else {
    showLoginPanel();
  }

  toggleBackgroundControls('none');
};

init();
