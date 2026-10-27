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

  // ── 账号管理系统 ──
  const overviewOnlineText = document.getElementById("overviewOnlineText");
  const overviewDot = document.getElementById("overviewDot");
  const overviewCurrentQQ = document.getElementById("overviewCurrentQQ");
  const overviewDefaultQQ = document.getElementById("overviewDefaultQQ");
  const overviewProcessStatus = document.getElementById("overviewProcessStatus");
  const accountsTableBody = document.getElementById("accountsTableBody");
  const refreshAccountsBtn = document.getElementById("refreshAccountsBtn");
  const stopNapcatBtn = document.getElementById("stopNapcatBtn");
  const openQrLoginBtn = document.getElementById("openQrLoginBtn");
  const quickLaunchForm = document.getElementById("quickLaunchForm");
  const quickLaunchQQ = document.getElementById("quickLaunchQQ");
  const quickLaunchSubmitBtn = document.getElementById("quickLaunchSubmitBtn");

  // 扫码弹层元素
  const qrModal = document.getElementById("qrModal");
  const closeQrModal = document.getElementById("closeQrModal");
  const cancelQrBtn = document.getElementById("cancelQrBtn");
  const refreshQrBtn = document.getElementById("refreshQrBtn");
  const qrLoading = document.getElementById("qrLoading");
  const qrImage = document.getElementById("qrImage");
  const qrStatusTip = document.getElementById("qrStatusTip");
  let qrPollTimer = null;

  async function loadAccounts() {
    try {
      const res = await fetch("/api/accounts");
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
            const resp = await fetch("/api/accounts/switch", {
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
            const resp = await fetch("/api/accounts/set-default", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ qq }),
            });
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
            const resp = await fetch(`/api/accounts/${qq}`, { method: "DELETE" });
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
        const resp = await fetch("/api/accounts/stop", { method: "POST" });
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
        const resp = await fetch("/api/accounts/switch", {
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

  // ── 扫码登录浮层与轮询 ──
  function openQrModal() {
    if (!qrModal) return;
    qrModal.classList.add("active");
    if (qrImage) qrImage.style.display = "none";
    if (qrLoading) qrLoading.style.display = "flex";
    if (qrStatusTip) qrStatusTip.textContent = "正在拉起 NapCat 扫码服务...";

    // 触发后端以二维码模式启动
    fetch("/api/accounts/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qr_mode: true }),
    }).catch(console.error);

    startQrPolling();
  }

  function closeQrModalFunc() {
    if (qrModal) qrModal.classList.remove("active");
    if (qrPollTimer) {
      clearInterval(qrPollTimer);
      qrPollTimer = null;
    }
  }

  function startQrPolling() {
    if (qrPollTimer) clearInterval(qrPollTimer);
    let attempts = 0;

    qrPollTimer = setInterval(async () => {
      attempts++;
      // 检测是否已经连接网关成功
      try {
        const statusRes = await fetch("/api/status");
        if (statusRes.ok) {
          const sData = await statusRes.json();
          if (sData.napcat_connected) {
            closeQrModalFunc();
            showToast("扫码登录成功！已接管当前 QQ 账号", "success");
            loadAccounts();
            pollStatus();
            return;
          }
        }
      } catch (_) {}

      // 获取二维码图片
      try {
        const qrRes = await fetch(`/api/accounts/qrcode?t=${Date.now()}`);
        if (qrRes.ok) {
          const blob = await qrRes.blob();
          if (qrImage) {
            qrImage.src = URL.createObjectURL(blob);
            qrImage.style.display = "block";
          }
          if (qrLoading) qrLoading.style.display = "none";
        }
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
      const res = await fetch("/api/status");
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
  loadConfig();
  pollStatus();
  setInterval(pollStatus, 4000);
});
