// 控制台前端交互逻辑

document.addEventListener("DOMContentLoaded", () => {
  // ── 选项卡切换 ──
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(`pane-${targetTab}`);
      if (targetPane) targetPane.classList.add("active");

      if (targetTab === "whitelist") loadWhitelist();
      if (targetTab === "history") loadHistoryUsers();
      if (targetTab === "logs") loadLogs();
    });
  });

  // ── 配置加载与保存 ──
  const configForm = document.getElementById("configForm");
  const saveStatus = document.getElementById("saveStatus");
  const tempSlider = document.getElementById("temperature");
  const tempVal = document.getElementById("tempVal");
  const topPSlider = document.getElementById("top_p");
  const topPVal = document.getElementById("toppVal");
  const masterSwitch = document.getElementById("masterSwitch");

  tempSlider.addEventListener("input", e => tempVal.textContent = e.target.value);
  topPSlider.addEventListener("input", e => topPVal.textContent = e.target.value);

  async function loadConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) throw new Error("获取配置失败");
      const data = await res.json();

      document.getElementById("api_base").value = data.api_base || "";
      document.getElementById("api_key").value = data.api_key || "";
      document.getElementById("model").value = data.model || "";
      document.getElementById("debounce_delay").value = data.debounce_delay || 1.5;
      document.getElementById("typing_speed").value = data.typing_speed || 0.15;
      document.getElementById("max_tokens").value = data.max_tokens || 2048;
      document.getElementById("system_prompt").value = data.system_prompt || "";

      tempSlider.value = data.temperature;
      tempVal.textContent = data.temperature;
      topPSlider.value = data.top_p;
      topPVal.textContent = data.top_p;

      masterSwitch.checked = data.is_enabled;
    } catch (err) {
      console.error(err);
    }
  }

  configForm.addEventListener("submit", async e => {
    e.preventDefault();
    saveStatus.textContent = "保存中...";

    const payload = {
      api_base: document.getElementById("api_base").value.trim(),
      api_key: document.getElementById("api_key").value.trim(),
      model: document.getElementById("model").value.trim(),
      debounce_delay: parseFloat(document.getElementById("debounce_delay").value),
      typing_speed: parseFloat(document.getElementById("typing_speed").value),
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
      if (!res.ok) throw new Error("保存失败");
      saveStatus.textContent = "配置已保存";
      setTimeout(() => saveStatus.textContent = "", 3000);
    } catch (err) {
      saveStatus.textContent = "保存失败: " + err.message;
    }
  });

  // 总开关快捷切换
  masterSwitch.addEventListener("change", async () => {
    try {
      await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: masterSwitch.checked }),
      });
    } catch (err) {
      console.error("更新开关状态失败:", err);
    }
  });

  // 连通性测试
  const testConnBtn = document.getElementById("testConnBtn");
  testConnBtn.addEventListener("click", async () => {
    testConnBtn.disabled = true;
    testConnBtn.textContent = "测试中...";

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
      if (data.success) {
        alert(`连接成功！\n耗时: ${data.latency_ms}ms\n模型回复: ${data.reply}`);
      } else {
        alert(`连接失败！\n耗时: ${data.latency_ms}ms\n错误: ${data.error}`);
      }
    } catch (err) {
      alert("请求测试接口失败: " + err.message);
    } finally {
      testConnBtn.disabled = false;
      testConnBtn.textContent = "连通性测试";
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
        whitelistTableBody.innerHTML = `<tr><td colspan="6" class="text-center">暂无白名单用户</td></tr>`;
        return;
      }

      whitelistTableBody.innerHTML = list.map(u => `
        <tr>
          <td><strong>${u.user_id}</strong></td>
          <td>${u.remark || "-"}</td>
          <td>
            <label class="switch-container">
              <input type="checkbox" ${u.is_enabled ? "checked" : ""} onchange="toggleWhitelistUser(${u.user_id}, this.checked)">
              <span class="switch-slider"></span>
            </label>
          </td>
          <td>${u.custom_prompt ? "已配置" : "默认"}</td>
          <td>${new Date(u.created_at).toLocaleString()}</td>
          <td>
            <button class="btn btn-danger" onclick="deleteWhitelistUser(${u.user_id})">移除</button>
          </td>
        </tr>
      `).join("");
    } catch (err) {
      console.error(err);
    }
  }

  window.toggleWhitelistUser = async (userId, enabled) => {
    try {
      await fetch(`/api/whitelist/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: enabled }),
      });
    } catch (err) {
      alert("更新失败: " + err.message);
      loadWhitelist();
    }
  };

  window.deleteWhitelistUser = async userId => {
    if (!confirm(`确定要从白名单移除好友 ${userId} 吗？`)) return;
    try {
      await fetch(`/api/whitelist/${userId}`, { method: "DELETE" });
      loadWhitelist();
    } catch (err) {
      alert("移除失败: " + err.message);
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
      loadWhitelist();
    } catch (err) {
      alert("添加失败: " + err.message);
    }
  });

  // ── 对话历史记录 ──
  const historyUserSelect = document.getElementById("historyUserSelect");
  const chatContainer = document.getElementById("chatContainer");
  const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");

  async function loadHistoryUsers() {
    try {
      const res = await fetch("/api/whitelist");
      const list = await res.json();
      historyUserSelect.innerHTML = `<option value="">选择好友 QQ</option>` +
        list.map(u => `<option value="${u.user_id}">${u.remark ? `${u.remark} (${u.user_id})` : u.user_id}</option>`).join("");
    } catch (err) {
      console.error(err);
    }
  }

  async function loadUserChat(userId) {
    if (!userId) {
      chatContainer.innerHTML = `<div class="chat-placeholder">请选择好友查看对话历史</div>`;
      return;
    }
    chatContainer.innerHTML = `<div class="chat-placeholder">加载中...</div>`;

    try {
      const res = await fetch(`/api/messages/${userId}?limit=50`);
      const messages = await res.json();
      if (!messages.length) {
        chatContainer.innerHTML = `<div class="chat-placeholder">该好友暂无聊天记录</div>`;
        return;
      }

      chatContainer.innerHTML = messages.map(m => {
        const isUser = m.role === "user";
        const imagesHtml = (m.image_urls || []).map(url => `
          <a href="${url}" target="_blank"><img src="${url}" class="chat-img-thumb" alt="图片"></a>
        `).join("");

        return `
          <div class="chat-bubble ${isUser ? "user" : "assistant"}">
            <span class="bubble-meta">${new Date(m.created_at).toLocaleTimeString()} · ${isUser ? "好友" : "接管回复"}</span>
            <div>${escapeHtml(m.content)}</div>
            ${imagesHtml}
          </div>
        `;
      }).join("");

      chatContainer.scrollTop = chatContainer.scrollHeight;
    } catch (err) {
      chatContainer.innerHTML = `<div class="chat-placeholder">加载历史记录失败: ${err.message}</div>`;
    }
  }

  historyUserSelect.addEventListener("change", e => loadUserChat(e.target.value));
  refreshHistoryBtn.addEventListener("click", () => loadUserChat(historyUserSelect.value));

  // ── 系统日志 ──
  const logViewer = document.getElementById("logViewer");
  const refreshLogsBtn = document.getElementById("refreshLogsBtn");

  async function loadLogs() {
    try {
      const res = await fetch("/api/logs?limit=50");
      const logs = await res.json();
      if (!logs.length) {
        logViewer.innerHTML = `<div class="log-line">暂无日志</div>`;
        return;
      }
      logViewer.innerHTML = logs.map(l => `
        <div class="log-line ${l.level === "ERROR" ? "error" : ""}">
          [${new Date(l.created_at).toLocaleTimeString()}] [${l.level}] [${l.source}]: ${escapeHtml(l.message)}
        </div>
      `).join("");
      logViewer.scrollTop = logViewer.scrollHeight;
    } catch (err) {
      console.error(err);
    }
  }

  refreshLogsBtn.addEventListener("click", loadLogs);

  // ── 状态轮询 ──
  const napcatStatus = document.getElementById("napcatStatus");
  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        if (data.napcat_connected) {
          napcatStatus.className = "status-indicator online";
          napcatStatus.querySelector(".status-text").textContent = "NapCat 在线";
        } else {
          napcatStatus.className = "status-indicator";
          napcatStatus.querySelector(".status-text").textContent = "NapCat 未连接";
        }
      }
    } catch (err) {
      napcatStatus.className = "status-indicator";
      napcatStatus.querySelector(".status-text").textContent = "后端离线";
    }
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // 初始化执行
  loadConfig();
  pollStatus();
  setInterval(pollStatus, 5000);
});
