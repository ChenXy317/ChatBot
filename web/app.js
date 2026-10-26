/**
 * QQ 接管控制台 · 前端核心交互控制器
 */

document.addEventListener("DOMContentLoaded", () => {
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

  tempSlider.addEventListener("input", e => tempVal.textContent = e.target.value);
  topPSlider.addEventListener("input", e => topPVal.textContent = e.target.value);
  debounceInput.addEventListener("input", e => debounceVal.textContent = `${e.target.value}s`);
  typingInput.addEventListener("input", e => typingVal.textContent = `${e.target.value}s`);

  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) throw new Error("获取配置失败");
      const data = await res.json();

      document.getElementById("api_base").value = data.api_base || "";
      document.getElementById("api_key").value = data.api_key || "";
      document.getElementById("model").value = data.model || "";
      document.getElementById("max_tokens").value = data.max_tokens || 2048;
      document.getElementById("system_prompt").value = data.system_prompt || "";

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
      api_key: document.getElementById("api_key").value.trim(),
      model: document.getElementById("model").value.trim(),
      debounce_delay: parseFloat(debounceInput.value),
      typing_speed: parseFloat(typingInput.value),
      temperature: parseFloat(tempSlider.value),
      top_p: parseFloat(topPSlider.value),
      max_tokens: parseInt(document.getElementById("max_tokens").value, 10),
      system_prompt: document.getElementById("system_prompt").value,
    };

    try {
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("保存接口异常");
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
      await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: masterSwitch.checked }),
      });
      showToast(masterSwitch.checked ? "已开启自动接管" : "已暂停自动接管", "info");
    } catch (err) {
      showToast("切换接管状态失败", "error");
    }
  });

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
      const res = await fetch("/api/config/test", {
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
  const openAddUserModal = document.getElementById("openAddUserModal");
  const closeAddUserModal = document.getElementById("closeAddUserModal");
  const cancelAddUserBtn = document.getElementById("cancelAddUserBtn");
  const addUserForm = document.getElementById("addUserForm");

  async function loadWhitelist() {
    try {
      const res = await fetch("/api/whitelist");
      const list = await res.json();
      if (!list.length) {
        whitelistTableBody.innerHTML = `<tr><td colspan="6" class="table-empty">当前白名单列表为空，请添加允许接管的好友</td></tr>`;
        return;
      }

      whitelistTableBody.innerHTML = list.map(u => `
        <tr>
          <td><span class="qq-badge">${u.user_id}</span></td>
          <td>${escapeHtml(u.remark) || '<span style="color:var(--text-tertiary)">未设置</span>'}</td>
          <td>
            <label class="toggle-switch">
              <input type="checkbox" ${u.is_enabled ? "checked" : ""} onchange="toggleWhitelistUser(${u.user_id}, this.checked)">
              <span class="toggle-track"></span>
            </label>
          </td>
          <td>
            ${u.custom_prompt ? '<span class="tag-badge">专属设定</span>' : '<span style="color:var(--text-tertiary)">默认全局</span>'}
          </td>
          <td style="font-family:var(--font-mono); font-size:12px;">${formatDateTime(u.created_at)}</td>
          <td style="text-align: right;">
            <button class="btn btn-danger-ghost" onclick="deleteWhitelistUser(${u.user_id})" title="移除好友">移除</button>
          </td>
        </tr>
      `).join("");
    } catch (err) {
      showToast("加载白名单失败: " + err.message, "error");
    }
  }

  window.toggleWhitelistUser = async (userId, enabled) => {
    try {
      await fetch(`/api/whitelist/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: enabled }),
      });
      showToast(`已${enabled ? "启用" : "停用"}对 ${userId} 的自动接管`, "info");
    } catch (err) {
      showToast("操作失败: " + err.message, "error");
      loadWhitelist();
    }
  };

  window.deleteWhitelistUser = async userId => {
    try {
      await fetch(`/api/whitelist/${userId}`, { method: "DELETE" });
      showToast(`已从白名单移除好友 ${userId}`, "success");
      loadWhitelist();
    } catch (err) {
      showToast("移除失败: " + err.message, "error");
    }
  };

  openAddUserModal.addEventListener("click", () => addUserModal.classList.add("active"));
  const closeModal = () => addUserModal.classList.remove("active");
  closeAddUserModal.addEventListener("click", closeModal);
  cancelAddUserBtn.addEventListener("click", closeModal);

  addUserForm.addEventListener("submit", async e => {
    e.preventDefault();
    const payload = {
      user_id: parseInt(document.getElementById("new_user_id").value, 10),
      remark: document.getElementById("new_remark").value.trim(),
      custom_prompt: document.getElementById("new_custom_prompt").value.trim() || null,
      is_enabled: true,
    };

    try {
      const res = await fetch("/api/whitelist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "添加失败");
      }
      closeModal();
      addUserForm.reset();
      showToast(`成功添加白名单好友 ${payload.user_id}`, "success");
      loadWhitelist();
    } catch (err) {
      showToast("添加失败: " + err.message, "error");
    }
  });

  // ── 对话历史记录与图片灯箱 ──
  const historyUserSelect = document.getElementById("historyUserSelect");
  const chatContainer = document.getElementById("chatContainer");
  const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
  const lightboxModal = document.getElementById("lightboxModal");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxClose = document.getElementById("lightboxClose");

  async function loadHistoryUsers() {
    try {
      const res = await fetch("/api/whitelist");
      const list = await res.json();
      const currentVal = historyUserSelect.value;
      historyUserSelect.innerHTML = `<option value="">选择白名单好友</option>` +
        list.map(u => `<option value="${u.user_id}" ${currentVal == u.user_id ? "selected" : ""}>${escapeHtml(u.remark) ? `${escapeHtml(u.remark)} (${u.user_id})` : u.user_id}</option>`).join("");
    } catch (err) {
      console.error(err);
    }
  }

  async function loadUserChat(userId) {
    if (!userId) {
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
      const res = await fetch(`/api/messages/${userId}?limit=50`);
      const messages = await res.json();
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
            <span class="message-meta">${formatDateTime(m.created_at)} · ${isUser ? "好友消息" : "接管回复"}</span>
            <div class="message-bubble">${escapeHtml(m.content)}</div>
            ${imagesHtml}
          </div>
        `;
      }).join("");

      chatContainer.scrollTop = chatContainer.scrollHeight;
    } catch (err) {
      chatContainer.innerHTML = `<div class="empty-state"><span>加载历史记录异常: ${err.message}</span></div>`;
    }
  }

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
      const res = await fetch("/api/logs?limit=80");
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

  // ── NapCat 状态轮询 ──
  const napcatBadge = document.getElementById("napcatBadge");
  const statusText = document.getElementById("statusText");

  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        if (data.napcat_connected) {
          napcatBadge.className = "connection-badge online";
          statusText.textContent = "NapCat 协议端已连接";
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
  loadConfig();
  pollStatus();
  setInterval(pollStatus, 4000);
});
