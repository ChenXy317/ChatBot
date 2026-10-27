/**
 * QQ 接管控制台 · 前端核心交互控制器
 */

document.addEventListener("DOMContentLoaded", () => {
  const authGate = document.getElementById("authGate");
  const authForm = document.getElementById("authForm");
  const dashboardTokenInput = document.getElementById("dashboardToken");
  const authError = document.getElementById("authError");

  function getDashboardToken() {
    return sessionStorage.getItem("chatbot_dashboard_token") || "";
  }

  function showAuthGate(message = "") {
    if (authGate) authGate.hidden = false;
    if (authError) {
      authError.textContent = message;
      authError.hidden = !message;
    }
  }

  function hideAuthGate() {
    if (authGate) authGate.hidden = true;
    if (dashboardTokenInput) dashboardTokenInput.value = "";
  }

  async function apiFetch(url, options = {}, retried = false) {
    const headers = new Headers(options.headers || {});
    const token = getDashboardToken();
    if (token) headers.set("X-Dashboard-Token", token);
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401 && !retried) {
      sessionStorage.removeItem("chatbot_dashboard_token");
      showAuthGate("请输入正确的控制台口令");
      throw new Error("需要控制台口令");
    }
    return response;
  }

  if (authForm) {
    authForm.addEventListener("submit", async event => {
      event.preventDefault();
      const token = dashboardTokenInput.value.trim();
      try {
        const res = await fetch("/api/auth/check", {
          headers: token ? { "X-Dashboard-Token": token } : {},
        });
        if (!res.ok) throw new Error(res.status === 401 ? "口令不正确" : "服务暂不可用");
        const result = await res.json();
        if (result.required) {
          sessionStorage.setItem("chatbot_dashboard_token", token);
        } else {
          sessionStorage.removeItem("chatbot_dashboard_token");
        }
        hideAuthGate();
        loadConfig();
        pollStatus();
      } catch (error) {
        showAuthGate(error.message);
      }
    });
  }

  async function initializeDashboard() {
    const token = getDashboardToken();
    try {
      const res = await fetch("/api/auth/check", {
        headers: token ? { "X-Dashboard-Token": token } : {},
      });
      if (res.status === 401) {
        sessionStorage.removeItem("chatbot_dashboard_token");
        showAuthGate(token ? "控制台口令已失效，请重新输入" : "");
        return;
      }
      if (!res.ok) throw new Error("无法连接本地控制台");
      const result = await res.json();
      if (result.required && !token) {
        showAuthGate();
        return;
      }
      hideAuthGate();
      loadConfig();
      pollStatus();
      loadAccounts();
      setInterval(pollStatus, 4000);
    } catch (error) {
      showAuthGate(error.message);
    }
  }

  // ── Toast 通知系统 ──
  const toastContainer = document.getElementById("toastContainer");

  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.2s";
      setTimeout(() => toast.remove(), 200);
    }, 3200);
  }

  // ── 选项卡切换 ──
  const navItems = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");

  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const targetTab = item.getAttribute("data-tab");
      navItems.forEach(i => i.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      item.classList.add("active");
      const targetPane = document.getElementById(`pane-${targetTab}`);
      if (targetPane) {
        targetPane.classList.add("active");
      }

      if (targetTab === "accounts") loadAccounts();
      if (targetTab === "whitelist") loadWhitelist();
      if (targetTab === "history") loadHistoryUsers();
      if (targetTab === "logs") loadLogs();
    });
  });

  // ── 配置管理与数值双向绑定 ──
  const configForm = document.getElementById("configForm");
  const saveConfigBtn = document.getElementById("saveConfigBtn");
  const tempSlider = document.getElementById("temperature");
  const tempVal = document.getElementById("tempVal");
  const topPSlider = document.getElementById("top_p");
  const topPVal = document.getElementById("toppVal");
  const debounceInput = document.getElementById("debounce_delay");
  const debounceVal = document.getElementById("debounceVal");
  const typingInput = document.getElementById("typing_speed");
  const typingVal = document.getElementById("typingVal");
  const masterSwitch = document.getElementById("masterSwitch");
  const restartAppBtn = document.getElementById("restartAppBtn");

  tempSlider.addEventListener("input", e => tempVal.textContent = e.target.value);
  topPSlider.addEventListener("input", e => topPVal.textContent = e.target.value);
  debounceInput.addEventListener("input", e => debounceVal.textContent = `${e.target.value}s`);
  typingInput.addEventListener("input", e => typingVal.textContent = `${e.target.value}s`);

  async function loadConfig() {
    try {
      const res = await apiFetch("/api/config");
      if (!res.ok) throw new Error("获取配置失败");
      const data = await res.json();

      document.getElementById("api_base").value = data.api_base || "";
      document.getElementById("api_key").value = "";
      document.getElementById("api_key").placeholder = data.api_key_set
        ? "已保存密钥；留空表示不修改"
        : "sk-...";
      document.getElementById("model").value = data.model || "";
      document.getElementById("max_tokens").value = data.max_tokens || 2048;
      document.getElementById("role_prompt").value = data.role_prompt || "";
      document.getElementById("output_prompt").value = data.output_prompt || "";

      debounceInput.value = data.debounce_delay;
      debounceVal.textContent = `${data.debounce_delay}s`;

      typingInput.value = data.typing_speed;
      typingVal.textContent = `${data.typing_speed}s`;

      tempSlider.value = data.temperature;
      tempVal.textContent = data.temperature;

      topPSlider.value = data.top_p;
      topPVal.textContent = data.top_p;

      masterSwitch.checked = data.is_enabled;
    } catch (err) {
      showToast("加载配置失败: " + err.message, "error");
    }
  }

  configForm.addEventListener("submit", async e => {
    e.preventDefault();
    saveConfigBtn.disabled = true;

    const payload = {
      api_base: document.getElementById("api_base").value.trim(),
      api_key: document.getElementById("api_key").value.trim() || undefined,
      model: document.getElementById("model").value.trim(),
      debounce_delay: parseFloat(debounceInput.value),
      typing_speed: parseFloat(typingInput.value),
      temperature: parseFloat(tempSlider.value),
      top_p: parseFloat(topPSlider.value),
      max_tokens: parseInt(document.getElementById("max_tokens").value, 10),
      role_prompt: document.getElementById("role_prompt").value,
      output_prompt: document.getElementById("output_prompt").value,
    };

    try {
      const res = await apiFetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("保存接口异常");
      const saved = await res.json();
      document.getElementById("api_key").value = "";
      document.getElementById("api_key").placeholder = saved.api_key_set
        ? "已保存密钥；留空表示不修改"
        : "sk-...";
      showToast("配置已成功更新并生效", "success");
    } catch (err) {
      showToast("保存失败: " + err.message, "error");
    } finally {
      saveConfigBtn.disabled = false;
    }
  });

  // 全局总开关切换
  masterSwitch.addEventListener("change", async () => {
    try {
      const res = await apiFetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: masterSwitch.checked }),
      });
      if (!res.ok) throw new Error("切换接口异常");
      showToast(masterSwitch.checked ? "已开启自动接管" : "已暂停自动接管", "info");
    } catch (err) {
      masterSwitch.checked = !masterSwitch.checked;
      showToast("切换接管状态失败", "error");
    }
  });

  if (restartAppBtn) {
    restartAppBtn.addEventListener("click", async () => {
      if (!confirm("重启服务后，当前会话会断开。确定继续吗？")) return;
      restartAppBtn.disabled = true;
      try {
        const res = await apiFetch("/api/system/shutdown", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ restart: true }),
        });
        if (!res.ok) throw new Error("重启接口异常");
        showToast("服务正在重启，请稍候刷新页面", "info");
      } catch (error) {
        showToast("重启失败: " + error.message, "error");
        restartAppBtn.disabled = false;
      }
    });
  }

  // ── 连通性测试 ──
  const testConnBtn = document.getElementById("testConnBtn");
  const testResultBox = document.getElementById("testResultBox");
  const testBadge = document.getElementById("testBadge");
  const testLatency = document.getElementById("testLatency");
  const testContent = document.getElementById("testContent");

  testConnBtn.addEventListener("click", async () => {
    testConnBtn.disabled = true;
    testResultBox.style.display = "flex";
    testBadge.className = "test-badge";
    testBadge.textContent = "测试中";
    testLatency.textContent = "...";
    testContent.textContent = "正在向目标模型端点发送探测消息...";

    const payload = {
      api_base: document.getElementById("api_base").value.trim(),
      api_key: document.getElementById("api_key").value.trim(),
      model: document.getElementById("model").value.trim(),
    };

    try {
      const res = await apiFetch("/api/config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      testLatency.textContent = `${data.latency_ms} ms`;

      if (data.success) {
        testBadge.className = "test-badge success";
        testBadge.textContent = "连接正常";
        testContent.textContent = `响应内容: "${data.reply}"`;
      } else {
        testBadge.className = "test-badge error";
        testBadge.textContent = "连接失败";
        testContent.textContent = `错误详情: ${data.error || "未知异常"}`;
      }
    } catch (err) {
      testBadge.className = "test-badge error";
      testBadge.textContent = "请求错误";
      testContent.textContent = err.message;
    } finally {
      testConnBtn.disabled = false;
    }
  });

  // ── 白名单管理 ──
  const whitelistTableBody = document.getElementById("whitelistTableBody");
  const addUserModal = document.getElementById("addUserModal");
  const friendModalTitle = document.getElementById("friendModalTitle");
  const openAddUserModal = document.getElementById("openAddUserModal");
  const closeAddUserModal = document.getElementById("closeAddUserModal");
  const cancelAddUserBtn = document.getElementById("cancelAddUserBtn");
  const addUserForm = document.getElementById("addUserForm");
  const newUserIdInput = document.getElementById("new_user_id");
  const newCustomPromptInput = document.getElementById("new_custom_prompt");
  const saveFriendBtn = document.getElementById("saveFriendBtn");
  let editingFriendId = null;

  async function loadWhitelist() {
    try {
      const res = await apiFetch("/api/whitelist");
      const list = await res.json();
      if (!list.length) {
        whitelistTableBody.innerHTML = `<tr><td colspan="5" class="table-empty">当前白名单列表为空，请添加允许接管的好友</td></tr>`;
        return;
      }

      whitelistTableBody.innerHTML = list.map(u => `
        <tr>
          <td><span class="qq-badge">${u.user_id}</span></td>
          <td>
            <label class="toggle-switch">
              <input type="checkbox" ${u.is_enabled ? "checked" : ""} onchange="toggleWhitelistUser(${u.user_id}, this.checked)">
              <span class="toggle-track"></span>
            </label>
          </td>
          <td class="prompt-preview">${u.custom_prompt ? escapeHtml(u.custom_prompt) : '<span style="color:var(--text-tertiary)">未设置</span>'}</td>
          <td style="font-family:var(--font-mono); font-size:12px;">${formatDateTime(u.created_at)}</td>
          <td style="text-align: right;">
            <div class="action-btns">
              <button class="btn btn-secondary btn-xs" onclick="editWhitelistUser(${u.user_id})">编辑</button>
              <button class="btn btn-danger-ghost" onclick="deleteWhitelistUser(${u.user_id})" title="移除好友">移除</button>
            </div>
          </td>
        </tr>
      `).join("");
    } catch (err) {
      showToast("加载白名单失败: " + err.message, "error");
    }
  }

  window.toggleWhitelistUser = async (userId, enabled) => {
    try {
      const res = await apiFetch(`/api/whitelist/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: enabled }),
      });
      if (!res.ok) throw new Error("操作接口异常");
      showToast(`已${enabled ? "启用" : "停用"}对 ${userId} 的自动接管`, "info");
    } catch (err) {
      showToast("操作失败: " + err.message, "error");
      loadWhitelist();
    }
  };

  window.deleteWhitelistUser = async userId => {
    try {
      const res = await apiFetch(`/api/whitelist/${userId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("删除接口异常");
      showToast(`已从白名单移除好友 ${userId}`, "success");
      loadWhitelist();
    } catch (err) {
      showToast("移除失败: " + err.message, "error");
    }
  };

  function openFriendModal(user = null) {
    editingFriendId = user ? user.user_id : null;
    friendModalTitle.textContent = user ? "编辑好友配置" : "添加好友至接管白名单";
    saveFriendBtn.textContent = user ? "保存修改" : "确认添加";
    newUserIdInput.value = user ? user.user_id : "";
    newUserIdInput.disabled = Boolean(user);
    newCustomPromptInput.value = user ? user.custom_prompt || "" : "";
    addUserModal.classList.add("active");
  }

  window.editWhitelistUser = async userId => {
    try {
      const res = await apiFetch("/api/whitelist");
      if (!res.ok) throw new Error("获取好友配置失败");
      const users = await res.json();
      const user = users.find(item => Number(item.user_id) === Number(userId));
      if (!user) throw new Error("未找到该好友");
      openFriendModal(user);
    } catch (error) {
      showToast("加载好友配置失败: " + error.message, "error");
    }
  };

  openAddUserModal.addEventListener("click", () => openFriendModal());
  const closeModal = () => addUserModal.classList.remove("active");
  closeAddUserModal.addEventListener("click", closeModal);
  cancelAddUserBtn.addEventListener("click", closeModal);

  addUserForm.addEventListener("submit", async e => {
    e.preventDefault();
    const payload = {
      custom_prompt: newCustomPromptInput.value.trim() || null,
    };

    try {
      const isEditing = editingFriendId !== null;
      const url = isEditing ? `/api/whitelist/${editingFriendId}` : "/api/whitelist";
      const body = isEditing
        ? payload
        : {
            ...payload,
            user_id: parseInt(newUserIdInput.value, 10),
            is_enabled: true,
          };
      const res = await apiFetch(url, {
        method: isEditing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "添加失败");
      }
      closeModal();
      addUserForm.reset();
      showToast(isEditing ? "好友配置已更新" : `成功添加白名单好友 ${body.user_id}`, "success");
      loadWhitelist();
    } catch (err) {
      showToast("添加失败: " + err.message, "error");
    }
  });

  // ── 对话历史记录与图片灯箱 ──
  const historyUserSelect = document.getElementById("historyUserSelect");
  const chatContainer = document.getElementById("chatContainer");
  const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
  const clearHistoryBtn = document.getElementById("clearHistoryBtn");
  const historyRecordCount = document.getElementById("historyRecordCount");
  const lightboxModal = document.getElementById("lightboxModal");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxClose = document.getElementById("lightboxClose");
  const messageEditModal = document.getElementById("messageEditModal");
  const messageEditForm = document.getElementById("messageEditForm");
  const editMessageContent = document.getElementById("edit_message_content");
  const editMessageImages = document.getElementById("edit_message_images");
  const closeMessageEditModal = document.getElementById("closeMessageEditModal");
  const cancelMessageEditBtn = document.getElementById("cancelMessageEditBtn");
  const saveMessageBtn = document.getElementById("saveMessageBtn");
  let editingMessageId = null;
  let currentHistoryUserId = "";

  async function loadHistoryUsers() {
    try {
      const [whitelistRes, ownersRes] = await Promise.all([
        apiFetch("/api/whitelist"),
        apiFetch("/api/message-users"),
      ]);
      if (!whitelistRes.ok || !ownersRes.ok) throw new Error("获取消息好友列表失败");
      const whitelist = await whitelistRes.json();
      const owners = await ownersRes.json();
      const userMap = new Map();
      whitelist.forEach(user => {
        userMap.set(String(user.user_id), { user_id: user.user_id, message_count: 0 });
      });
      owners.forEach(owner => {
        userMap.set(String(owner.user_id), {
          user_id: owner.user_id,
          message_count: owner.message_count,
        });
      });
      const list = Array.from(userMap.values())
        .sort((a, b) => Number(a.user_id) - Number(b.user_id));
      const currentVal = historyUserSelect.value;
      historyUserSelect.innerHTML = `<option value="">选择白名单好友</option>` +
        list.map(u => `<option value="${u.user_id}" ${currentVal == u.user_id ? "selected" : ""}>${u.user_id}${u.message_count ? ` · ${u.message_count} 条` : ""}</option>`).join("");
    } catch (err) {
      console.error(err);
    }
  }

  async function loadUserChat(userId) {
    currentHistoryUserId = userId || "";
    clearHistoryBtn.disabled = !currentHistoryUserId;
    if (!userId) {
      historyRecordCount.textContent = "0 条";
      chatContainer.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span>请从上方选择指定好友以加载历史会话</span>
        </div>
      `;
      return;
    }

    try {
      const res = await apiFetch(`/api/messages/${userId}`);
      if (!res.ok) throw new Error("获取历史消息失败");
      const messages = await res.json();
      historyRecordCount.textContent = `${messages.length} 条`;
      if (!messages.length) {
        chatContainer.innerHTML = `<div class="empty-state"><span>该好友暂无聊天消息记录</span></div>`;
        return;
      }

      chatContainer.innerHTML = messages.map(m => {
        const isUser = m.role === "user";
        const imagesHtml = (m.image_urls || []).map(url => `
          <img src="${url}" class="chat-thumb-img" alt="图片" onclick="openLightbox('${url}')">
        `).join("");

        return `
          <div class="message-row ${isUser ? "user" : "assistant"}">
            <div class="message-meta-row">
              <span class="message-meta">${formatDateTime(m.created_at)} · ${isUser ? "好友消息" : "接管回复"}</span>
              <div class="message-actions">
                <button class="btn btn-secondary btn-xs" onclick="editHistoryMessage(${m.id})">编辑</button>
                <button class="btn btn-danger-ghost" onclick="deleteHistoryMessage(${m.id})">删除</button>
              </div>
            </div>
            <div class="message-bubble">${escapeHtml(m.content)}</div>
            ${imagesHtml}
          </div>
        `;
      }).join("");

      chatContainer.scrollTop = chatContainer.scrollHeight;
    } catch (err) {
      historyRecordCount.textContent = "0 条";
      chatContainer.innerHTML = `<div class="empty-state"><span>加载历史记录异常: ${err.message}</span></div>`;
    }
  }

  window.editHistoryMessage = async messageId => {
    try {
      const res = await apiFetch(`/api/messages/${currentHistoryUserId}`);
      if (!res.ok) throw new Error("获取历史消息失败");
      const messages = await res.json();
      const message = messages.find(item => Number(item.id) === Number(messageId));
      if (!message) throw new Error("未找到该消息");
      editingMessageId = message.id;
      editMessageContent.value = message.content || "";
      editMessageImages.value = (message.image_urls || []).join("\n");
      messageEditModal.classList.add("active");
    } catch (error) {
      showToast("加载消息失败: " + error.message, "error");
    }
  };

  function closeMessageEditor() {
    messageEditModal.classList.remove("active");
    editingMessageId = null;
  }

  window.deleteHistoryMessage = async messageId => {
    if (!confirm("确定删除这条历史消息吗？删除后模型将不再读取它。")) return;
    try {
      const res = await apiFetch(`/api/messages/${messageId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("删除接口异常");
      showToast("历史消息已删除", "success");
      loadHistoryUsers();
      loadUserChat(currentHistoryUserId);
    } catch (error) {
      showToast("删除失败: " + error.message, "error");
    }
  };

  messageEditForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (editingMessageId === null) return;
    saveMessageBtn.disabled = true;
    try {
      const imageUrls = editMessageImages.value
        .split(/\r?\n/)
        .map(value => value.trim())
        .filter(Boolean);
      const res = await apiFetch(`/api/messages/${editingMessageId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: editMessageContent.value.trim(),
          image_urls: imageUrls,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "保存接口异常");
      closeMessageEditor();
      showToast("历史消息已更新", "success");
      loadUserChat(currentHistoryUserId);
    } catch (error) {
      showToast("保存失败: " + error.message, "error");
    } finally {
      saveMessageBtn.disabled = false;
    }
  });

  closeMessageEditModal.addEventListener("click", closeMessageEditor);
  cancelMessageEditBtn.addEventListener("click", closeMessageEditor);
  messageEditModal.addEventListener("click", event => {
    if (event.target === messageEditModal) closeMessageEditor();
  });

  clearHistoryBtn.addEventListener("click", async () => {
    if (!currentHistoryUserId) return;
    if (!confirm(`确定清空好友 ${currentHistoryUserId} 的全部历史消息吗？此操作不可恢复。`)) return;
    clearHistoryBtn.disabled = true;
    try {
      const res = await apiFetch(`/api/messages/user/${currentHistoryUserId}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "清空接口异常");
      showToast(`已清空 ${data.deleted || 0} 条历史消息`, "success");
      loadHistoryUsers();
      loadUserChat(currentHistoryUserId);
    } catch (error) {
      showToast("清空失败: " + error.message, "error");
    } finally {
      clearHistoryBtn.disabled = !currentHistoryUserId;
    }
  });

  historyUserSelect.addEventListener("change", e => loadUserChat(e.target.value));
  refreshHistoryBtn.addEventListener("click", () => loadUserChat(historyUserSelect.value));

  // 灯箱事件
  window.openLightbox = url => {
    lightboxImg.src = url;
    lightboxModal.classList.add("active");
  };
  const closeLightbox = () => lightboxModal.classList.remove("active");
  lightboxClose.addEventListener("click", closeLightbox);
  lightboxModal.addEventListener("click", e => {
    if (e.target === lightboxModal) closeLightbox();
  });

  // ── 运行日志终端 ──
  const logViewer = document.getElementById("logViewer");
  const refreshLogsBtn = document.getElementById("refreshLogsBtn");

  async function loadLogs() {
    try {
      const res = await apiFetch("/api/logs?limit=80");
      const logs = await res.json();
      if (!logs.length) {
        logViewer.innerHTML = `<div class="log-empty">暂无系统事件记录</div>`;
        return;
      }

      logViewer.innerHTML = logs.map(l => {
        const levelClass = l.level === "ERROR" ? "level-error" : (l.level === "WARN" ? "level-warn" : "");
        return `
          <div class="log-item">
            <span class="log-time">[${formatDateTime(l.created_at)}]</span>
            <span class="log-tag ${levelClass}">[${l.level}]</span>
            <span class="log-tag">[${l.source}]</span>
            <span class="log-text">${escapeHtml(l.message)}</span>
          </div>
        `;
      }).join("");

      logViewer.scrollTop = logViewer.scrollHeight;
    } catch (err) {
      console.error(err);
    }
  }

  refreshLogsBtn.addEventListener("click", () => {
    loadLogs();
    showToast("日志已刷新", "info");
  });

  // ── 账号管理系统 ──
  const overviewOnlineText = document.getElementById("overviewOnlineText");
  const overviewDot = document.getElementById("overviewDot");
  const overviewCurrentQQ = document.getElementById("overviewCurrentQQ");
  const overviewDefaultQQ = document.getElementById("overviewDefaultQQ");
  const overviewProcessStatus = document.getElementById("overviewProcessStatus");
  const overviewLoginPhase = document.getElementById("overviewLoginPhase");
  const accountsTableBody = document.getElementById("accountsTableBody");
  const refreshAccountsBtn = document.getElementById("refreshAccountsBtn");
  const stopNapcatBtn = document.getElementById("stopNapcatBtn");
  const openQrLoginBtn = document.getElementById("openQrLoginBtn");
  const quickLaunchForm = document.getElementById("quickLaunchForm");
  const quickLaunchQQ = document.getElementById("quickLaunchQQ");
  const quickLaunchSubmitBtn = document.getElementById("quickLaunchSubmitBtn");
  const sendTestForm = document.getElementById("sendTestForm");
  const testMessageUserId = document.getElementById("testMessageUserId");
  const testMessageText = document.getElementById("testMessageText");
  const sendTestBtn = document.getElementById("sendTestBtn");

  // 扫码弹层元素
  const qrModal = document.getElementById("qrModal");
  const closeQrModal = document.getElementById("closeQrModal");
  const cancelQrBtn = document.getElementById("cancelQrBtn");
  const refreshQrBtn = document.getElementById("refreshQrBtn");
  const qrLoading = document.getElementById("qrLoading");
  const qrImage = document.getElementById("qrImage");
  const qrStatusTip = document.getElementById("qrStatusTip");
  const qrLoginStatus = document.getElementById("qrLoginStatus");
  const qrErrorMessage = document.getElementById("qrErrorMessage");
  let qrPollTimer = null;
  let qrObjectUrl = null;

  const loginPhaseLabels = {
    offline: "离线",
    starting: "正在拉起 NapCat 协议端...",
    generating_qrcode: "正在生成二维码",
    waiting_qrcode: "等待扫码",
    qrcode_scanned: "二维码已扫描，等待确认",
    initializing: "正在初始化账号",
    ready: "登录成功",
  };

  function renderLoginState(status) {
    const phase = status.login_phase || "";
    const label = loginPhaseLabels[phase] || (status.is_login ? "登录成功" : "等待 QR 登录服务");
    if (overviewLoginPhase) overviewLoginPhase.textContent = label;
    if (qrLoginStatus) qrLoginStatus.textContent = label;
    if (qrErrorMessage) {
      if (phase === "starting" || phase === "waiting_qrcode" || !status.login_error) {
        qrErrorMessage.textContent = "";
        qrErrorMessage.style.display = "none";
      } else {
        qrErrorMessage.textContent = status.login_error;
        qrErrorMessage.style.display = "block";
      }
    }
    return label;
  }

  async function refreshLoginStatus() {
    const res = await apiFetch("/api/accounts/login-status", { cache: "no-store" });
    if (!res.ok) throw new Error("登录状态接口请求失败");
    const status = await res.json();
    renderLoginState(status);
    return status;
  }

  async function pollQrLogin() {
    try {
      const status = await refreshLoginStatus();
      if (status.is_login) {
        closeQrModalFunc();
        showToast("QQ 登录成功，正在接入控制台", "success");
        loadAccounts();
        pollStatus();
        return true;
      }
      if ((status.qrcode_url || status.has_qrcode) && qrImage) {
        await loadLoginQr(status);
      }
      if (qrStatusTip && !status.qrcode_url && !status.has_qrcode) {
        qrStatusTip.textContent = "NapCat 正在生成登录二维码...";
      }
    } catch (err) {
      if (qrErrorMessage) {
        qrErrorMessage.textContent = `登录服务暂时不可用，正在等待 NapCat: ${err.message}`;
        qrErrorMessage.style.display = "block";
      }
    }
    return false;
  }

  async function loadLoginQr(status) {
    if (!qrImage) return false;
    try {
      const res = await apiFetch(`/api/accounts/qrcode?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return false;
      const blob = await res.blob();
      if (!blob || blob.size < 50) return false;
      if (qrObjectUrl) URL.revokeObjectURL(qrObjectUrl);
      qrObjectUrl = URL.createObjectURL(blob);
      qrImage.src = qrObjectUrl;
      qrImage.style.display = "block";
      if (qrLoading) qrLoading.style.display = "none";
      if (qrErrorMessage) {
        qrErrorMessage.textContent = "";
        qrErrorMessage.style.display = "none";
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  async function loadAccounts() {
    try {
      const res = await apiFetch("/api/accounts");
      if (!res.ok) throw new Error("获取账号列表失败");
      const data = await res.json();

      // 更新概览指标
      if (data.is_connected) {
        if (overviewDot) overviewDot.className = "badge-dot online";
        if (overviewOnlineText) overviewOnlineText.textContent = "在线运行中";
      } else {
        if (overviewDot) overviewDot.className = "badge-dot";
        if (overviewOnlineText) overviewOnlineText.textContent = "离线";
      }

      const curNick = data.online_nickname ? `${data.online_nickname} · ` : "";
      if (overviewCurrentQQ) overviewCurrentQQ.textContent = data.online_qq ? `${curNick}${data.online_qq}` : "-";
      if (overviewDefaultQQ) overviewDefaultQQ.textContent = data.default_account || "-";
      if (overviewProcessStatus) overviewProcessStatus.textContent = data.is_process_running ? "运行中 (QQ.exe)" : "已停止";
      renderLoginState(data.napcat_status || {});

      // 渲染账号表格
      if (!accountsTableBody) return;
      if (!data.accounts || data.accounts.length === 0) {
        accountsTableBody.innerHTML = `
          <tr>
            <td colspan="5" class="table-empty">暂无已记录的 QQ 账号，可点击右上角“扫码登录新账号”或输入账号快速启动</td>
          </tr>
        `;
        return;
      }

      accountsTableBody.innerHTML = data.accounts.map(acc => {
        let statusBadge = "";
        if (acc.is_online) {
          statusBadge = '<span class="tag-badge tag-online">● 在线接管中</span>';
        } else if (acc.is_default) {
          statusBadge = '<span class="tag-badge tag-default">默认启动</span>';
        } else {
          statusBadge = '<span class="tag-badge">离线就绪</span>';
        }

        const wsBadge = acc.has_ws_config
          ? '<span class="tag-badge tag-ws-ok">已对齐 (8090)</span>'
          : '<span class="tag-badge tag-ws-no">待补全</span>';

        return `
          <tr>
            <td><strong style="font-family: var(--font-mono); font-size: 14px;">${escapeHtml(acc.qq)}</strong></td>
            <td>${statusBadge}</td>
            <td>${wsBadge}</td>
            <td style="color: var(--text-secondary); font-size: 12px;">${acc.last_active || "无记录"}</td>
            <td style="text-align: right;">
              <div class="action-btns">
                <button class="btn btn-secondary btn-xs btn-switch" data-qq="${escapeHtml(acc.qq)}" title="停止当前并以此账号启动 NapCat">
                  切换并启动
                </button>
                <button class="btn btn-secondary btn-xs btn-set-default" data-qq="${escapeHtml(acc.qq)}" title="设为默认启动账号">
                  设为默认
                </button>
                <button class="btn btn-secondary btn-xs btn-del-acc" data-qq="${escapeHtml(acc.qq)}" title="删除本地凭据">
                  删除
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

      // 绑定表格内部按钮
      accountsTableBody.querySelectorAll(".btn-switch").forEach(btn => {
        btn.addEventListener("click", async () => {
          const qq = btn.getAttribute("data-qq");
          btn.disabled = true;
          showToast(`正在切换至账号 ${qq}...`, "info");
          try {
            const resp = await apiFetch("/api/accounts/switch", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ qq, auto_start: true }),
            });
            const rData = await resp.json();
            if (rData.success) {
              showToast(rData.message || `已拉起账号 ${qq}`, "success");
            } else {
              showToast(rData.message || "切换失败", "error");
            }
          } catch (e) {
            showToast("切换异常: " + e.message, "error");
          } finally {
            btn.disabled = false;
            setTimeout(loadAccounts, 1500);
            setTimeout(pollStatus, 2000);
          }
        });
      });

      accountsTableBody.querySelectorAll(".btn-set-default").forEach(btn => {
        btn.addEventListener("click", async () => {
          const qq = btn.getAttribute("data-qq");
          try {
            const resp = await apiFetch("/api/accounts/set-default", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ qq }),
            });
        if (!resp.ok) throw new Error("设置默认账号接口异常");
            const rData = await resp.json();
            if (rData.success) {
              showToast(`已设为默认账号: ${qq}`, "success");
              loadAccounts();
            }
          } catch (e) {
            showToast("设置失败: " + e.message, "error");
          }
        });
      });

      accountsTableBody.querySelectorAll(".btn-del-acc").forEach(btn => {
        btn.addEventListener("click", async () => {
          const qq = btn.getAttribute("data-qq");
          if (!confirm(`确定要移除账号 ${qq} 的本地配置文件吗？`)) return;
          try {
            const resp = await apiFetch(`/api/accounts/${qq}`, { method: "DELETE" });
            const rData = await resp.json();
            if (rData.success) {
              showToast(`已移除账号 ${qq}`, "info");
              loadAccounts();
            } else {
              showToast(rData.detail || "删除失败", "error");
            }
          } catch (e) {
            showToast("删除异常: " + e.message, "error");
          }
        });
      });

    } catch (err) {
      showToast("加载账号信息失败: " + err.message, "error");
    }
  }

  // 刷新账号
  if (refreshAccountsBtn) {
    refreshAccountsBtn.addEventListener("click", () => {
      loadAccounts();
      showToast("已刷新账号列表", "info");
    });
  }

  // 停止 NapCat
  if (stopNapcatBtn) {
    stopNapcatBtn.addEventListener("click", async () => {
      if (!confirm("确定要停止当前运行的 NapCat / QQ 进程吗？")) return;
      stopNapcatBtn.disabled = true;
      try {
        const resp = await apiFetch("/api/accounts/stop", { method: "POST" });
        const data = await resp.json();
        showToast(data.message || "已发送停止指令", "info");
      } catch (e) {
        showToast("停止进程异常: " + e.message, "error");
      } finally {
        stopNapcatBtn.disabled = false;
        setTimeout(loadAccounts, 1000);
        setTimeout(pollStatus, 1500);
      }
    });
  }

  // 快速启动表单
  if (quickLaunchForm) {
    quickLaunchForm.addEventListener("submit", async e => {
      e.preventDefault();
      const qq = quickLaunchQQ.value.trim();
      if (!qq) return;
      quickLaunchSubmitBtn.disabled = true;
      showToast(`正在启动账号 ${qq}...`, "info");
      try {
        const resp = await apiFetch("/api/accounts/switch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ qq, auto_start: true }),
        });
        const data = await resp.json();
        if (data.success) {
          showToast(data.message || `已拉起账号 ${qq}`, "success");
          quickLaunchQQ.value = "";
        } else {
          showToast(data.message || "启动失败", "error");
        }
      } catch (err) {
        showToast("启动异常: " + err.message, "error");
      } finally {
        quickLaunchSubmitBtn.disabled = false;
        setTimeout(loadAccounts, 1500);
        setTimeout(pollStatus, 2000);
      }
    });
  }

  if (sendTestForm) {
    sendTestForm.addEventListener("submit", async event => {
      event.preventDefault();
      const userId = parseInt(testMessageUserId.value, 10);
      const message = testMessageText.value.trim();
      if (!Number.isInteger(userId) || !message) return;
      sendTestBtn.disabled = true;
      try {
        const res = await apiFetch("/api/system/send-test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, message }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "发送失败");
        showToast(data.message || "测试消息已发送", "success");
        testMessageText.value = "";
      } catch (error) {
        showToast("测试消息发送失败: " + error.message, "error");
      } finally {
        sendTestBtn.disabled = false;
      }
    });
  }

  // ── 扫码登录浮层与轮询 ──
  function openQrModal() {
    if (!qrModal) return;
    qrModal.classList.add("active");
    if (qrImage) qrImage.style.display = "none";
    if (qrLoading) qrLoading.style.display = "flex";
    if (qrStatusTip) qrStatusTip.textContent = "正在拉起 NapCat 扫码服务...";
    if (qrErrorMessage) {
      qrErrorMessage.textContent = "";
      qrErrorMessage.style.display = "none";
    }

    // 触发后端以二维码模式启动
    apiFetch("/api/accounts/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qr_mode: true }),
    }).catch(console.error);

    startQrPolling();
    pollQrLogin();
  }

  function closeQrModalFunc() {
    if (qrModal) qrModal.classList.remove("active");
    if (qrPollTimer) {
      clearInterval(qrPollTimer);
      qrPollTimer = null;
    }
    if (qrObjectUrl) {
      URL.revokeObjectURL(qrObjectUrl);
      qrObjectUrl = null;
    }
  }

  function startQrPolling() {
    if (qrPollTimer) clearInterval(qrPollTimer);
    let attempts = 0;

    qrPollTimer = setInterval(async () => {
      attempts++;
      try {
        await pollQrLogin();
      } catch (_) {}

      if (attempts > 120) {
        closeQrModalFunc();
        showToast("扫码等待超时，请重新点击扫码登录", "error");
      }
    }, 1500);
  }

  if (openQrLoginBtn) openQrLoginBtn.addEventListener("click", openQrModal);
  if (closeQrModal) closeQrModal.addEventListener("click", closeQrModalFunc);
  if (cancelQrBtn) cancelQrBtn.addEventListener("click", closeQrModalFunc);
  if (refreshQrBtn) {
    refreshQrBtn.addEventListener("click", () => {
      startQrPolling();
      showToast("正在重新探测二维码...", "info");
    });
  }

  // ── NapCat 状态轮询 ──
  const napcatBadge = document.getElementById("napcatBadge");
  const statusText = document.getElementById("statusText");

  async function pollStatus() {
    try {
      const res = await apiFetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        if (data.napcat_connected) {
          napcatBadge.className = "connection-badge online";
          const nick = data.current_nickname ? `${data.current_nickname} · ` : "";
          statusText.textContent = `已连接: ${nick}${data.current_qq || "QQ"}`;
        } else {
          napcatBadge.className = "connection-badge";
          statusText.textContent = "NapCat 协议端未连接";
        }
      }
    } catch (err) {
      napcatBadge.className = "connection-badge";
      statusText.textContent = "中继后端离线";
    }
  }

  // 键盘快捷键 (ESC 关闭浮层)
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      closeModal();
      closeLightbox();
      closeMessageEditor();
      closeQrModalFunc();
    }
  });

  // 工具辅助函数
  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatDateTime(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  // 启动时初始化
  initializeDashboard();
});
