const appShell = document.querySelector(".app-shell");
const pageTitle = document.querySelector("#pageTitle");
const crumb = document.querySelector("#crumb");
const clock = document.querySelector("#clock");
const toast = document.querySelector("#toast");
const palette = document.querySelector("#commandPalette");
const actionPanel = document.querySelector("#actionPanel");
const actionPanelTitle = document.querySelector("#actionPanelTitle");
const actionPanelBody = document.querySelector("#actionPanelBody");

const pageMeta = {
  hub: {
    title: "从故事到分镜图的漫剧生产工作台",
    crumb: "动态漫 STUDIO / PROJECT HUB / 项目中心",
  },
  workbench: {
    title: "项目工作台",
    crumb: "动态漫 STUDIO / WORKBENCH / 项目工作台",
  },
  assets: {
    title: "数字资产",
    crumb: "动态漫 STUDIO / ASSETS / 数字资产",
  },
  script: {
    title: "故事 / 剧情地图 / 分集脚本",
    crumb: "动态漫 STUDIO / SCRIPT / 剧本与流程",
  },
  storyboard: {
    title: "分镜表",
    crumb: "动态漫 STUDIO / STORYBOARD / 分镜表",
  },
  export: {
    title: "导出",
    crumb: "动态漫 STUDIO / EXPORT / 导出",
  },
  models: {
    title: "模型设置",
    crumb: "动态漫 STUDIO / MODELS / 模型设置",
  },
};

const studioState = {
  connected: false,
  projects: [],
  detail: null,
  config: null,
  actions: [],
  actionCapabilities: {},
  jobs: [],
  pendingAction: null,
  activeJobId: "",
  activeProjectId: "",
  selectedSource: "故事种子",
  selectedScriptIndex: 0,
  selectedShotIndex: 0,
  nodeStep: 1,
};

let visibleToastTimer = 0;
let jobPollTimer = 0;

function showToast(message) {
  window.clearTimeout(visibleToastTimer);
  toast.textContent = message;
  toast.classList.add("is-visible");
  visibleToastTimer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
  }, 2600);
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return map[char];
  });
}

function currentProjectLabel() {
  const detail = studioState.detail;
  if (!detail) return "未选择项目";
  return detail.name || detail.title || detail.id || "未选择项目";
}

function pageTitleFor(viewName) {
  const meta = pageMeta[viewName];
  if (!meta) return "";
  if (viewName === "hub" || viewName === "models") return meta.title;
  return `${currentProjectLabel()} · ${meta.title}`;
}

function refreshPageChrome() {
  const viewName = appShell.dataset.view || "hub";
  const meta = pageMeta[viewName] || pageMeta.hub;
  pageTitle.textContent = pageTitleFor(viewName);
  crumb.textContent = meta.crumb;
}

function switchView(viewName, options = {}) {
  const { updateUrl = true } = options;
  const meta = pageMeta[viewName];
  if (!meta) return;

  appShell.dataset.view = viewName;
  refreshPageChrome();

  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-current", view.dataset.view === viewName);
  });

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.viewTarget === viewName);
  });

  closePalette();
  document.querySelector(".main-scroll").scrollTo({ top: 0, behavior: "smooth" });

  if (updateUrl) {
    const nextUrl = viewName === "hub" ? window.location.pathname : `#${viewName}`;
    window.history.replaceState(null, "", nextUrl);
  }
}

function openPalette() {
  palette.hidden = false;
  palette.querySelector(".command-list button")?.focus();
}

function closePalette() {
  palette.hidden = true;
}

function openActionPanel(title, html) {
  if (!actionPanel || !actionPanelTitle || !actionPanelBody) return;
  actionPanelTitle.textContent = title;
  actionPanelBody.innerHTML = html;
  actionPanel.hidden = false;
  actionPanel.querySelector("button, a, input, textarea")?.focus();
}

function closeActionPanel() {
  if (actionPanel) actionPanel.hidden = true;
}

function repoMediaUrl(path = "") {
  return `/media/${String(path).split("/").map(encodeURIComponent).join("/")}`;
}

function keyValueRows(rows = []) {
  return `
    <div class="action-list">
      ${rows.map(([label, value]) => `
        <div class="action-row">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value || "—")}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function commandButton(command, label = "复制命令") {
  if (!command) return "";
  return `<button class="copy-button" type="button" data-action="copy-command" data-command="${escapeHtml(command)}">${escapeHtml(label)}</button>`;
}

function actionButton(actionId, label = "准备动作", className = "copy-button") {
  return `<button class="${escapeHtml(className)}" type="button" data-action="prepare-action" data-action-id="${escapeHtml(actionId)}">${escapeHtml(label)}</button>`;
}

async function copyText(text, successMessage = "已复制") {
  const value = String(text || "");
  if (!value) {
    showToast("没有可复制内容");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
  } catch (error) {
    const input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  showToast(successMessage);
}

function updateClock() {
  const clockTarget = document.querySelector("#clock");
  if (!clockTarget) return;
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  clockTarget.textContent = formatter.format(new Date()).replaceAll("/", ".");
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function shortPath(path = "") {
  const value = String(path);
  if (value.length <= 54) return value;
  return `...${value.slice(-51)}`;
}

function setControlValue(control, value) {
  if (!control) return;
  const normalized = value === undefined || value === null || value === "" ? "—" : String(value);
  if (control.tagName === "SELECT") {
    const option = Array.from(control.options).find((item) => item.value === normalized || item.textContent === normalized);
    if (option) {
      control.value = option.value;
    } else if (control.options.length) {
      control.options[0].textContent = normalized;
      control.value = control.options[0].value;
    }
    return;
  }
  control.value = normalized;
}

function setPlateImage(element, imageUrl, label) {
  if (!element) return;
  element.textContent = label;
  if (imageUrl) {
    element.classList.add("has-image");
    element.style.setProperty("--plate-image", `url("${imageUrl}")`);
  } else {
    element.classList.remove("has-image");
    element.style.removeProperty("--plate-image");
  }
}

function renderShellData(data = {}) {
  const stats = data.stats || {};
  const livePill = document.querySelector(".live-pill");
  if (livePill) livePill.innerHTML = `<i></i> LOCAL API <time id="clock">${clock.textContent}</time>`;

  const telemetry = document.querySelector(".telemetry");
  if (telemetry) {
    const cells = telemetry.querySelectorAll(".telemetry-grid div");
    if (cells[0]) cells[0].innerHTML = `<span>PROJECTS</span><strong>${stats.projects_total ?? 0}</strong>`;
    if (cells[1]) cells[1].innerHTML = `<span>STATE</span><strong>${stats.state_files ?? 0}</strong>`;
    const operator = telemetry.querySelector(".operator");
    if (operator) {
      operator.innerHTML = `
        <span class="avatar">本</span>
        <div>
          <strong>本地受控 API</strong>
          <small>${escapeHtml(shortPath(data.repo_root || ""))}</small>
        </div>
      `;
    }
  }

  const facts = document.querySelector(".session-facts");
  if (facts) {
    facts.innerHTML = `
      <div><dt>DATA</dt><dd>${stats.projects_total ?? 0} projects</dd></div>
      <div><dt>ROOT</dt><dd>${escapeHtml(shortPath(data.projects_root || "projects"))}</dd></div>
      <div><dt>MODE</dt><dd>Guarded actions</dd></div>
    `;
  }
}

function renderStats(stats = {}) {
  const labels = ["PROJECTS", "SCRIPTS", "ASSETS", "STORYBOARDS", "VIDEOS"];
  const captions = ["本地项目", "分集脚本", "角色 + 场景", "分镜参考", "已生成视频"];
  document.querySelectorAll(".stat-card p").forEach((label, index) => {
    label.textContent = labels[index] || label.textContent;
  });
  document.querySelectorAll(".stat-card span").forEach((caption, index) => {
    caption.textContent = captions[index] || "";
  });
  const cards = document.querySelectorAll(".stat-card strong");
  const values = [
    `${stats.projects_total ?? 0}<small>个</small>`,
    `${stats.scripts ?? 0}<small>集</small>`,
    `${(stats.characters ?? 0) + (stats.scenes ?? 0)}<small>项</small>`,
    `${stats.storyboards ?? 0}<small>张</small>`,
    `${stats.videos ?? 0}<small>条</small>`,
  ];
  values.forEach((value, index) => {
    if (cards[index]) cards[index].innerHTML = value;
  });
}

function renderHubContent(data = {}) {
  const hubGrid = document.querySelector(".hub-grid");
  if (!hubGrid) return;
  hubGrid.classList.add("hub-grid-connected");
  hubGrid.innerHTML = `
    <section class="panel ops-panel project-index-panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">PROJECTS · 本地项目</p>
          <h3>项目目录</h3>
          <p>读取 <code>${escapeHtml(data.projects_root || "projects")}</code> 下的真实文件，不创建、不删除、不触发生成。</p>
        </div>
        <button class="ghost-button" type="button" id="refreshButton">刷新</button>
      </div>
      <div class="project-list" id="projectList"></div>
    </section>
    <section class="panel data-source-panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">DATA SOURCE · 接入状态</p>
          <h3>只读文件系统</h3>
          <p>${escapeHtml(shortPath(data.repo_root || ""))}</p>
        </div>
        <span class="ok-pill">CONNECTED</span>
      </div>
      <div class="source-grid">
        <article><strong>${data.stats?.state_files ?? 0}</strong><span>状态 JSON</span></article>
        <article><strong>${data.stats?.config_files ?? 0}</strong><span>配置文件</span></article>
        <article><strong>${data.stats?.characters ?? 0}</strong><span>角色档案</span></article>
        <article><strong>${data.stats?.scenes ?? 0}</strong><span>场景档案</span></article>
      </div>
      <div class="section-rule"><span>CONFIG · 真实配置</span></div>
      <div class="config-list">
        <div><span>默认视频模型</span><strong>${escapeHtml(data.config?.seedance?.default_model || "未配置")}</strong></div>
        <div><span>生成后端</span><strong>${escapeHtml(data.config?.seedance?.generation_backend || "未配置")}</strong></div>
        <div><span>Dreamina 视频模型</span><strong>${escapeHtml(data.config?.seedance?.video_model || "未配置")}</strong></div>
        <div><span>并发上限</span><strong>${escapeHtml(data.config?.seedance?.max_concurrent_workers || "未配置")}</strong></div>
      </div>
    </section>
  `;
  document.querySelector("#refreshButton")?.addEventListener("click", () => loadStudioData());
  renderProjectList(data.projects || []);
}

function statusText(status) {
  const map = {
    active: "进行中",
    completed: "已交付",
    draft: "草稿",
    pending: "待开始",
  };
  return map[status] || status || "草稿";
}

function statusClass(status) {
  if (status === "completed") return "done";
  if (status === "active") return "hot";
  return "";
}

function actionById(actionId) {
  return studioState.actions.find((item) => item.id === actionId);
}

function jobStatusText(status) {
  const map = {
    queued: "排队中",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
  };
  return map[status] || status || "未知";
}

function isTerminalJob(job) {
  return ["succeeded", "failed"].includes(job?.status);
}

function actionRiskText(action = {}) {
  const map = {
    read: "只读检查",
    write: "会修改项目状态",
    agent: "会写入 Agent 请求",
    external: "可能调用外部 API",
  };
  return map[action.risk] || action.risk || "未标注";
}

function defaultActionPayload(actionId) {
  const detail = studioState.detail;
  const script = currentScript();
  const payload = { action: actionId };
  if (detail?.id && ["workflow_sync", "request_resume"].includes(actionId)) {
    payload.project_id = detail.id;
  }
  if (actionId === "workflow_sync" && script?.episode) {
    payload.episode = script.episode;
  }
  return payload;
}

function actionPayloadRows(payload = {}) {
  const rows = [];
  if (payload.project_id) rows.push(["项目", payload.project_id]);
  if (payload.episode) rows.push(["集数", payload.episode]);
  if (payload.trace_session) rows.push(["Trace", payload.trace_session]);
  if (!rows.length) rows.push(["范围", "仓库级动作"]);
  return rows;
}

function actionRowsHtml(actions = studioState.actions) {
  if (!actions.length) {
    return `<p>动作目录还没有加载；请确认本地 API 已启动。</p>`;
  }
  return `
    <div class="operator-actions">
      ${actions.map((item) => `
        <article class="operator-action-card">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <span>${escapeHtml(item.description || "")}</span>
          </div>
          <em class="${item.mutates ? "warn-pill" : "ok-pill"}">${escapeHtml(actionRiskText(item))}</em>
          ${actionButton(item.id, item.button || "准备动作", "primary-action compact")}
        </article>
      `).join("")}
    </div>
  `;
}

function jobsHtml(jobs = studioState.jobs) {
  if (!jobs.length) return `<p>暂无任务记录。</p>`;
  return `
    <div class="job-list">
      ${jobs.slice(0, 8).map((job) => `
        <button type="button" data-action="open-job" data-job-id="${escapeHtml(job.id)}">
          <span class="job-status ${escapeHtml(job.status || "")}">${escapeHtml(jobStatusText(job.status))}</span>
          <strong>${escapeHtml(job.label || job.action)}</strong>
          <small>${escapeHtml(job.project_id || "repo")} · ${escapeHtml(formatDate(job.updated_at || job.created_at))}</small>
        </button>
      `).join("")}
    </div>
  `;
}

function renderProjectList(projects = []) {
  const projectList = document.querySelector("#projectList");
  if (!projectList || projects.length === 0) return;

  projectList.innerHTML = projects.map((project, index) => {
    const date = formatDate(project.updated_at).replace(" ", "<br>");
    const subtitle = project.headline && project.headline !== project.title
      ? `${project.headline} · ${project.counts?.episodes ?? 0} 集`
      : `${project.counts?.episodes ?? 0} 集 · ${project.counts?.state_files ?? 0} 状态文件`;
    return `
      <article class="project-row" data-project-id="${escapeHtml(project.id)}">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <strong>${escapeHtml(project.name || project.title)}<small>${escapeHtml(subtitle)}</small></strong>
        <em class="${statusClass(project.status)}">${escapeHtml(statusText(project.status))}</em>
        <code>${escapeHtml(project.id)}</code>
        <time>${date}</time>
        <div class="row-actions">
          <button type="button" class="project-open" data-project-id="${escapeHtml(project.id)}" data-view-target="workbench">进入</button>
          <button type="button" class="project-open" data-project-id="${escapeHtml(project.id)}" data-view-target="assets">资产</button>
          <button type="button" class="project-open" data-project-id="${escapeHtml(project.id)}" data-view-target="storyboard">分镜</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderAssetCounts(counts = {}) {
  const summaryCards = document.querySelectorAll(".asset-counts div");
  const values = [
    [counts.characters, "角色"],
    [counts.scenes, "场景"],
    [0, "道具"],
    [counts.storyboards, "参考"],
    [counts.state_files, "提示"],
    [counts.videos, "分镜"],
  ];
  values.forEach(([value, label], index) => {
    if (!summaryCards[index]) return;
    summaryCards[index].innerHTML = `<strong>${value ?? 0}</strong><span>${label}</span>`;
  });
}

function renderWorkbench(detail) {
  if (!detail) return;
  const pipeline = detail.pipeline || [];
  const progress = detail.progress || {};
  const counts = detail.counts || {};
  const stage = document.querySelector(".stage-board");

  if (stage) {
    const eyebrow = stage.querySelector(".panel-head .eyebrow");
    const title = stage.querySelector(".panel-head h2");
    const intro = stage.querySelector(".panel-head p:not(.eyebrow)");
    if (eyebrow) eyebrow.textContent = "CURRENT STAGE · 真实项目状态";
    if (title) title.textContent = `${detail.name} 项目状态`;
    if (intro) {
      intro.textContent = `${detail.headline || detail.name}；读取脚本、资产、状态和产物文件，不触发生成。`;
    }
  }

  const timeline = document.querySelector(".timeline");
  if (timeline && pipeline.length) {
    timeline.innerHTML = pipeline.map((node) => `
      <li class="${node.status === "completed" ? "done" : node.status === "in_progress" ? "active" : ""}">
        <span>${String(node.index).padStart(2, "0")}</span>
        <strong>${escapeHtml(node.name)}</strong>
        <em>${escapeHtml(node.status === "completed" ? "已完成" : node.status === "in_progress" ? "进行中" : "未开始")}</em>
      </li>
    `).join("");
  }

  const progressBar = document.querySelector(".progress-shell i");
  const progressValue = document.querySelector(".progress-shell strong");
  const progressCount = document.querySelector(".progress-shell small");
  if (progressBar) progressBar.style.width = `${progress.percent ?? 0}%`;
  if (progressValue) progressValue.textContent = `${Number(progress.percent ?? 0).toFixed(1)}%`;
  if (progressCount) progressCount.textContent = `${progress.completed_nodes ?? 0} / ${progress.total_nodes ?? 0}`;

  const nodeGrid = document.querySelector(".node-grid");
  if (nodeGrid && pipeline.length) {
    const currentNodeIndex = pipeline.findIndex((node) => detail.current_node?.index === node.index);
    const progressNodeIndex = pipeline.findIndex((node) => node.status === "in_progress");
    const selectedIndex = currentNodeIndex >= 0 ? currentNodeIndex : progressNodeIndex >= 0 ? progressNodeIndex : 0;
    nodeGrid.innerHTML = pipeline.map((node, index) => `
      <button class="node-card ${node.status === "in_progress" ? "active" : ""} ${index === selectedIndex ? "is-selected" : ""}" type="button" data-node-index="${index}">
        <small>ND-${String(node.index).padStart(2, "0")}</small>
        <strong>${escapeHtml(node.name)}</strong>
        <span>${escapeHtml(node.status === "completed" ? "已完成" : node.status === "in_progress" ? "进行中..." : "待开始")}</span>
      </button>
    `).join("");
  }

  const currentNode = detail.current_node || pipeline.find((node) => node.status === "in_progress") || pipeline[pipeline.length - 1];
  document.querySelector(".current-node strong").textContent = currentNode
    ? `ND-${String(currentNode.index).padStart(2, "0")} · ${currentNode.name}`
    : "ND-01 · 故事种子";
  document.querySelector(".current-node p").textContent = `接入 ${detail.name}：${counts.episodes ?? 0} 集脚本、${counts.characters ?? 0} 个角色、${counts.storyboards ?? 0} 张分镜参考。`;
  const currentNodeDl = document.querySelector(".current-node dl");
  if (currentNodeDl) {
    currentNodeDl.innerHTML = `
      <div><dt>来源</dt><dd>${escapeHtml(detail.id)}</dd></div>
      <div><dt>更新于</dt><dd>${escapeHtml(formatDate(detail.updated_at))}</dd></div>
    `;
  }
  document.querySelector(".execute-bar strong").textContent = "提交继续生成请求";
  document.querySelector(".execute-bar em").textContent = "写入请求文件；如配置远端触发器则自动提交";
  renderAssetCounts(counts);
  renderPrecheck(detail);
}

function selectPipelineNode(index) {
  const detail = studioState.detail;
  const node = detail?.pipeline?.[index];
  if (!detail || !node) return;

  document.querySelectorAll(".node-card").forEach((card, cardIndex) => {
    card.classList.toggle("is-selected", cardIndex === index);
  });
  document.querySelector(".current-node strong").textContent = `ND-${String(node.index).padStart(2, "0")} · ${node.name}`;
  document.querySelector(".current-node p").textContent = `节点状态：${node.status === "completed" ? "已完成" : node.status === "in_progress" ? "进行中" : "待开始"}。该页面只读取状态，不直接执行生成。`;
  const currentNodeDl = document.querySelector(".current-node dl");
  if (currentNodeDl) {
    currentNodeDl.innerHTML = `
      <div><dt>来源</dt><dd>${escapeHtml(detail.id)}</dd></div>
      <div><dt>更新于</dt><dd>${escapeHtml(formatDate(detail.updated_at))}</dd></div>
    `;
  }
}

function renderPrecheck(detail) {
  const panel = document.querySelector(".precheck-panel");
  if (!panel || !detail) return;
  const counts = detail.counts || {};
  panel.querySelector(".eyebrow").textContent = "DATA CHECK · 文件完整性";
  panel.querySelector("h3").textContent = "项目数据检查";
  const headBadge = panel.querySelector(".ok-pill");
  if (headBadge) headBadge.textContent = "READ";
  const checks = [
    ["分集脚本", counts.scripts > 0, `${counts.scripts ?? 0} 个 Markdown 脚本`],
    ["角色档案", counts.characters > 0, `${counts.characters ?? 0} 个 YAML 档案`],
    ["场景档案", counts.scenes > 0, `${counts.scenes ?? 0} 个 YAML 档案`],
    ["分镜参考", counts.storyboards > 0, `${counts.storyboards ?? 0} 张图片`],
    ["视频产物", counts.videos > 0, `${counts.videos ?? 0} 个视频文件`],
    ["交付包", (detail.deliverables || []).length > 0, `${(detail.deliverables || []).length} 个交付文件`],
  ];
  const list = panel.querySelector(".check-list");
  if (list) {
    list.innerHTML = checks.map(([name, ok, description]) => `
      <li class="${ok ? "ok" : "warn"}"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(description)}</span><em>${ok ? "存在" : "缺失"}</em></li>
    `).join("");
  }
  const button = panel.querySelector(".ghost-wide");
  if (button) {
    button.textContent = "运行环境检查";
    button.dataset.action = "prepare-action";
    button.dataset.actionId = "env_check";
    delete button.dataset.viewTarget;
  }
}

function renderAssets(detail) {
  if (!detail) return;
  const character = detail.characters?.find((item) => item.tier === "protagonist") || detail.characters?.[0];
  const scene = detail.scenes?.[0];

  if (character) {
    const panel = document.querySelector(".character-panel");
    panel.querySelector("h2").innerHTML = `${escapeHtml(character.code)} <small>${escapeHtml(character.name)} · ${escapeHtml(character.tier || "Character")}</small>`;
    const controls = panel.querySelectorAll("input, select, textarea");
    setControlValue(controls[0], character.name);
    setControlValue(controls[1], character.appearance);
    setControlValue(controls[2], character.gender === "male" ? "男" : character.gender === "female" ? "女" : character.gender);
    setControlValue(controls[3], character.age || character.first_episode);
    setControlValue(controls[4], character.personality);
    setControlValue(controls[5], character.appearance);
    setControlValue(controls[6], character.first_episode || character.path);
    setControlValue(controls[7], Array.isArray(character.aliases) ? character.aliases.join(" · ") : character.aliases);
    setPlateImage(panel.querySelector(".plate.small"), character.image_url, "REF / FRONT");
    const rule = panel.querySelector(".section-rule span");
    if (rule) rule.textContent = "SOURCE PROFILE";
    const profileRow = panel.querySelector(".profile-row");
    if (profileRow) {
      profileRow.innerHTML = `
        <div class="source-list">
          <div><span>档案</span><strong>${escapeHtml(character.path)}</strong></div>
          <div><span>参考图</span><strong>${escapeHtml(character.image_url || "未找到")}</strong></div>
          <div><span>首次出现</span><strong>${escapeHtml(character.first_episode || "未标注")}</strong></div>
        </div>
      `;
    }
  }

  if (scene) {
    const panel = document.querySelector(".scene-panel");
    panel.querySelector("h2").innerHTML = `${escapeHtml(scene.code)} <small>${escapeHtml(scene.name)} · Scene</small>`;
    const controls = panel.querySelectorAll("input, select, textarea");
    setControlValue(controls[0], scene.name);
    setControlValue(controls[1], scene.raw?.time_variants ? `时段 · ${scene.raw.time_variants}` : "场景");
    setControlValue(controls[2], scene.first_episode || "—");
    setControlValue(controls[3], scene.personality || "—");
    setControlValue(controls[4], "来自真实场景档案");
    setControlValue(controls[5], scene.appearance);
    setControlValue(controls[6], scene.path);
    setPlateImage(panel.querySelector(".plate.wide"), scene.image_url, "SCENE PLATE");
    const sceneRule = panel.querySelector(".section-rule span");
    if (sceneRule) sceneRule.textContent = "SOURCE PROFILE";
    const palette = panel.querySelector(".palette");
    if (palette) palette.remove();
    const lightInfo = panel.querySelector(".light-info");
    if (lightInfo) {
      lightInfo.innerHTML = `
        <div class="source-list">
          <div><span>档案</span><strong>${escapeHtml(scene.path)}</strong></div>
          <div><span>参考图</span><strong>${escapeHtml(scene.image_url || "未找到")}</strong></div>
          <div><span>首次出现</span><strong>${escapeHtml(scene.first_episode || "未标注")}</strong></div>
        </div>
      `;
    }
  }

  const promptPanel = document.querySelector(".prompt-panel");
  if (promptPanel) {
    const assetRows = [
      ["项目", detail.id],
      ["脚本", `${detail.scripts?.length ?? 0} 个 Markdown`],
      ["角色", `${detail.characters?.length ?? 0} 个档案`],
      ["场景", `${detail.scenes?.length ?? 0} 个档案`],
      ["分镜图", `${detail.storyboards?.length ?? 0} 张`],
      ["交付物", `${detail.deliverables?.length ?? 0} 个`],
    ];
    promptPanel.innerHTML = `
      <p class="eyebrow">ASSET INDEX · 真实资产索引</p>
      <h2>项目资产</h2>
      <div class="config-list asset-index-list">
        ${assetRows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
      </div>
      <div class="section-rule"><span>RECENT FILES</span></div>
      <div class="source-list">
        ${(detail.deliverables || []).slice(0, 4).map((item) => `<div><span>${escapeHtml(item.episode)}</span><strong>${escapeHtml(item.path)}</strong></div>`).join("") || "<div><span>交付物</span><strong>未找到 deliverables</strong></div>"}
      </div>
    `;
  }
}

function applyScriptToPanels(script, detail) {
  const scriptPanels = document.querySelectorAll(".script-grid .panel");
  if (!script || !detail || scriptPanels.length < 3) return;

  const inputControls = scriptPanels[0].querySelectorAll("textarea");
  setControlValue(inputControls[0], script.excerpt.split("\n").slice(0, 8).join("\n"));
  setControlValue(inputControls[1], `${detail.name} · ${script.path}`);

  const planControls = scriptPanels[1].querySelectorAll("input");
  setControlValue(planControls[0], `${detail.counts?.episodes ?? 0} 集 · ${detail.counts?.storyboards ?? 0} 分镜`);
  setControlValue(planControls[1], script.title);
  setControlValue(planControls[2], detail.current_node?.name || "生产节点");
  setControlValue(planControls[3], `${detail.counts?.characters ?? 0} 角色 · ${detail.counts?.scenes ?? 0} 场景`);
  setControlValue(planControls[4], `${detail.progress?.completed_nodes ?? 0}/${detail.progress?.total_nodes ?? 0}`);
  setControlValue(planControls[5], detail.source || "真实项目文件");

  const mapControls = scriptPanels[2].querySelectorAll("input, select, textarea");
  setControlValue(mapControls[0], script.episode);
  setControlValue(mapControls[2], detail.scenes?.[0]?.name || "—");
  setControlValue(mapControls[3], formatDate(script.updated_at));
  setControlValue(mapControls[4], script.excerpt.split("\n").find((line) => line.includes("△")) || script.title);
}

function selectScript(index) {
  const detail = studioState.detail;
  const script = detail?.scripts?.[index];
  if (!detail || !script) return;
  studioState.selectedScriptIndex = index;
  document.querySelectorAll(".phase-tabs button").forEach((button, buttonIndex) => {
    button.classList.toggle("is-active", buttonIndex === index);
  });
  applyScriptToPanels(script, detail);
  showToast(`已切换到 ${script.episode}`);
}

function renderScript(detail) {
  if (!detail) return;
  const script = detail.scripts?.[0];
  const scriptPanels = document.querySelectorAll(".script-grid .panel");
  if (!script || scriptPanels.length < 3) return;
  studioState.selectedScriptIndex = 0;

  const scriptBoard = document.querySelector(".script-board");
  if (scriptBoard) {
    scriptBoard.querySelector(".eyebrow").textContent = "CURRENT · 真实脚本";
    scriptBoard.querySelector("h2").textContent = `${detail.name} 脚本入口`;
    const intro = scriptBoard.querySelector(".panel-head p:not(.eyebrow)");
    if (intro) intro.textContent = `${detail.scripts?.length ?? 0} 个脚本文件，当前预览 ${script.path}`;
  }

  const phaseTabs = document.querySelector(".phase-tabs");
  if (phaseTabs) {
    phaseTabs.innerHTML = (detail.scripts || []).slice(0, 12).map((item, index) => `
      <button class="${index === 0 ? "is-active" : "done"}" type="button" data-action="select-script" data-script-index="${index}">${escapeHtml(item.episode)} · ${escapeHtml(item.title.replace(/^第\d+集[:：]\s*/, ""))}</button>
    `).join("");
  }

  const phaseGates = document.querySelector(".phase-gates");
  if (phaseGates) {
    const checks = [
      ["脚本文件", (detail.scripts || []).length > 0, `${detail.scripts?.length ?? 0} 个脚本`],
      ["状态记录", (detail.phases || []).length > 0, `${detail.phases?.length ?? 0} 个 phase 状态`],
      ["分镜参考", (detail.storyboards || []).length > 0, `${detail.storyboards?.length ?? 0} 张分镜图`],
    ];
    phaseGates.innerHTML = checks.map(([name, ok, text]) => `
      <article class="gate ${ok ? "ok" : "warn"}"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(text)}</span><em>${ok ? "存在" : "缺失"}</em></article>
    `).join("");
  }

  applyScriptToPanels(script, detail);
}

function renderStoryboard(detail) {
  if (!detail) return;
  const shots = detail.storyboards || [];
  const table = document.querySelector(".shot-table");
  if (!table || shots.length === 0) return;
  const heading = document.querySelector("#storyboardTitle");
  if (heading) heading.textContent = `${detail.name} · ${shots.length} 张分镜参考`;

  table.innerHTML = shots.slice(0, 16).map((shot, index) => `
    <article class="shot-row ${index === 0 ? "selected" : ""}" data-shot-index="${index}">
      <span>SH-${String(shot.shot).padStart(2, "0")}</span>
      <div class="shot-frame has-image" style="--plate-image:url('${escapeHtml(shot.image_url)}')">${escapeHtml(shot.episode)}</div>
      <strong>${escapeHtml(shot.title)}<small>${escapeHtml(shot.status)} · ${escapeHtml(formatDate(shot.updated_at))}</small></strong>
      <p>${escapeHtml(shot.path)}</p>
      <em>${escapeHtml(shot.status)}</em>
    </article>
  `).join("");
  selectShot(0);
}

function selectShot(index) {
  const shots = studioState.detail?.storyboards || [];
  const shot = shots[index];
  if (!shot) return;
  studioState.selectedShotIndex = index;
  document.querySelectorAll(".shot-row").forEach((row, rowIndex) => {
    row.classList.toggle("selected", rowIndex === index);
  });
  const detailPanel = document.querySelector(".shot-detail");
  detailPanel.querySelector("h3").textContent = `${shot.id} · ${shot.status}`;
  setPlateImage(detailPanel.querySelector(".large-frame"), shot.image_url, "PREVIEW");
  const controls = detailPanel.querySelectorAll("textarea, input");
  setControlValue(controls[0], `${shot.title}\n${shot.path}`);
  setControlValue(controls[1], `@${shot.path} 作为构图参考，延续 ${currentProjectLabel()} 的角色与场景约束。`);
  setControlValue(controls[2], shot.episode);
  setControlValue(controls[3], shot.status);
}

function renderExport(detail) {
  if (!detail) return;
  const exportTitle = document.querySelector("#exportTitle");
  if (exportTitle) exportTitle.textContent = `${detail.name} 交付物`;
  const labels = document.querySelectorAll(".deliverable-list label");
  const deliverables = detail.deliverables || [];
  labels.forEach((label, index) => {
    const input = label.querySelector("input");
    const item = deliverables[index];
    if (item) {
      input.checked = true;
      label.lastChild.textContent = ` ${item.episode} / ${item.name}`;
    } else if (index > 1) {
      input.checked = false;
    }
  });

  const queue = document.querySelector(".queue-list");
  if (!queue) return;
  const actions = studioState.actions.length ? studioState.actions : [
    { id: "env_check", label: "环境检查", description: "检查本地生成链路环境变量。", button: "运行检查", risk: "read", mutates: false },
    { id: "workflow_sync", label: "同步项目状态", description: "运行 workflow-sync 同步状态。", button: "确认同步", risk: "write", mutates: true },
    { id: "request_resume", label: "提交继续生成请求", description: "写入 Agent 继续请求。", button: "提交请求", risk: "agent", mutates: true },
  ];
  queue.innerHTML = actions.map((item, index) => `
    <article>
      <span>A-${String(index + 1).padStart(3, "0")}</span>
      <strong>${escapeHtml(item.label)}</strong>
      <em>${escapeHtml(item.description || "")}</em>
      ${actionButton(item.id, item.button || "准备动作")}
    </article>
  `).join("");
}

function renderModels(config = studioState.config) {
  const panel = document.querySelector(".model-console");
  if (!panel || !config) return;
  const seedance = config.seedance || {};
  const endpoints = config.endpoints || {};
  const env = config.env || {};
  panel.innerHTML = `
    <p class="eyebrow">CONFIG · 真实配置文件</p>
    <h2 id="modelsTitle">生成链路配置</h2>
    <div class="model-grid">
      <article><strong>默认视频模型</strong><span>${escapeHtml(seedance.default_model || "未配置")}</span><em class="ok-pill">YAML</em></article>
      <article><strong>生成后端</strong><span>${escapeHtml(seedance.generation_backend || "未配置")}</span><em class="ok-pill">YAML</em></article>
      <article><strong>Dreamina 视频</strong><span>${escapeHtml(seedance.video_model || "未配置")}</span><em class="ok-pill">YAML</em></article>
      <article><strong>图像模型</strong><span>${escapeHtml(seedance.image_model || "未配置")}</span><em class="ok-pill">YAML</em></article>
      <article><strong>分辨率</strong><span>${escapeHtml(seedance.video_resolution || "未配置")}</span><em class="ok-pill">YAML</em></article>
      <article><strong>并发上限</strong><span>${escapeHtml(seedance.max_concurrent_workers || "未配置")}</span><em class="ok-pill">YAML</em></article>
    </div>
    <div class="section-rule"><span>ENDPOINTS</span></div>
    <div class="config-list">
      <div><span>Seedance API</span><strong>${escapeHtml(endpoints.seedance_base_url || "未配置")}</strong></div>
      <div><span>Tuzi API</span><strong>${escapeHtml(endpoints.tuzi_base_url || "未配置")}</strong></div>
    </div>
    <div class="section-rule"><span>ENV PRESENCE · 仅显示是否存在，不显示密钥</span></div>
    <div class="source-grid">
      ${Object.entries(env).map(([key, exists]) => `<article><strong>${exists ? "YES" : "NO"}</strong><span>${escapeHtml(key)}</span></article>`).join("")}
    </div>
    <div class="section-rule"><span>CONFIG FILES</span></div>
    <div class="source-list">
      ${(config.files || []).slice(0, 12).map((file) => `<div><span>file</span><strong>${escapeHtml(file)}</strong></div>`).join("")}
    </div>
  `;
}

function currentScript() {
  const scripts = studioState.detail?.scripts || [];
  return scripts[studioState.selectedScriptIndex] || scripts[0];
}

function currentShot() {
  const shots = studioState.detail?.storyboards || [];
  return shots[studioState.selectedShotIndex] || shots[0];
}

function showStatusPanel() {
  const detail = studioState.detail;
  const stats = {
    projects: studioState.projects.length,
    scripts: detail?.counts?.scripts ?? 0,
    characters: detail?.counts?.characters ?? 0,
    scenes: detail?.counts?.scenes ?? 0,
    storyboards: detail?.counts?.storyboards ?? 0,
    videos: detail?.counts?.videos ?? 0,
  };
  openActionPanel("当前控制台状态", `
    ${keyValueRows([
      ["连接", studioState.connected ? "本地受控 API 已连接" : "未连接 API"],
      ["当前项目", detail?.id || "未选择"],
      ["脚本", `${stats.scripts} 个`],
      ["角色 / 场景", `${stats.characters} / ${stats.scenes}`],
      ["分镜 / 视频", `${stats.storyboards} / ${stats.videos}`],
      ["项目总数", `${stats.projects} 个`],
    ])}
    <div class="section-rule"><span>OPERATOR ACTIONS</span></div>
    ${actionRowsHtml()}
    <div class="section-rule"><span>RECENT JOBS</span></div>
    ${jobsHtml()}
    <div class="action-buttons">
      <button type="button" data-view-target="workbench">项目状态</button>
      <button type="button" data-view-target="script">脚本</button>
      <button type="button" data-view-target="storyboard">分镜</button>
      <button type="button" data-view-target="models">配置</button>
    </div>
  `);
}

async function previewScript() {
  const script = currentScript();
  if (!script) {
    showToast("当前项目没有脚本文件");
    return;
  }
  const url = repoMediaUrl(script.path);
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const text = await response.text();
    openActionPanel(script.title || script.path, `
      ${keyValueRows([
        ["集数", script.episode],
        ["来源", script.path],
        ["更新", formatDate(script.updated_at)],
      ])}
      <pre class="text-preview">${escapeHtml(text.slice(0, 5200))}${text.length > 5200 ? "\n..." : ""}</pre>
      <div class="action-buttons">
        <a class="inline-link" href="${url}" target="_blank" rel="noreferrer">打开原文件</a>
        ${commandButton(`open "${script.path}"`, "复制路径")}
      </div>
    `);
  } catch (error) {
    showToast(`脚本读取失败：${script.path}`);
  }
}

function previewShot() {
  const shot = currentShot();
  if (!shot) {
    showToast("当前项目没有分镜参考图");
    return;
  }
  openActionPanel(`${shot.id} · ${shot.status}`, `
    <img class="preview-media" src="${escapeHtml(shot.image_url)}" alt="${escapeHtml(shot.id)}" />
    ${keyValueRows([
      ["集数", shot.episode],
      ["文件", shot.path],
      ["状态", shot.status],
      ["更新", formatDate(shot.updated_at)],
    ])}
    <div class="action-buttons">
      <a class="inline-link" href="${escapeHtml(shot.image_url)}" target="_blank" rel="noreferrer">打开图片</a>
      ${commandButton(shot.path, "复制路径")}
    </div>
  `);
}

function inspectExport() {
  const detail = studioState.detail;
  if (!detail) {
    showToast("未选择项目");
    return;
  }
  const deliverables = detail.deliverables || [];
  const rows = deliverables.length
    ? deliverables.map((item) => [item.episode || "file", `${item.name} · ${item.path}`])
    : [["交付物", "未找到 deliverables"]];
  openActionPanel(`${detail.name} 交付物`, `
    ${keyValueRows(rows)}
    <div class="section-rule"><span>CLI COMMANDS</span></div>
    <div class="action-list">
      ${(detail.commands || []).map((item) => `
        <div class="action-row">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.command)}</strong>
          ${commandButton(item.command, "复制")}
        </div>
      `).join("")}
    </div>
  `);
}

async function loadActionCatalog() {
  const response = await fetch("/api/actions", { cache: "no-store" });
  if (!response.ok) throw new Error(`actions ${response.status}`);
  const data = await response.json();
  studioState.actions = data.actions || [];
  studioState.actionCapabilities = data.capabilities || {};
}

async function loadJobs() {
  const response = await fetch("/api/jobs", { cache: "no-store" });
  if (!response.ok) throw new Error(`jobs ${response.status}`);
  const data = await response.json();
  studioState.jobs = data.jobs || [];
}

async function ensureActionCatalog() {
  if (studioState.actions.length) return;
  await loadActionCatalog();
}

async function prepareAction(actionId, payload = defaultActionPayload(actionId)) {
  try {
    await ensureActionCatalog();
  } catch (error) {
    showToast("动作目录读取失败");
  }

  const action = actionById(actionId);
  if (!action) {
    showToast(`未知动作：${actionId}`);
    return;
  }

  studioState.pendingAction = { action, payload };
  const canSubmit = !action.requires_confirmation;
  const confirmation = action.requires_confirmation
    ? `
      <label class="confirm-line">
        <input type="checkbox" data-action="toggle-action-confirmation" />
        <span>我确认要执行这个动作，并理解它的影响范围。</span>
      </label>
    `
    : `<p>这个动作不修改项目文件，可以直接提交。</p>`;

  openActionPanel(action.label, `
    <p>${escapeHtml(action.description || "")}</p>
    ${keyValueRows([
      ["动作", action.id],
      ["风险", actionRiskText(action)],
      ["范围", action.scope || "repo"],
      ["修改状态", action.mutates ? "是" : "否"],
    ])}
    <div class="section-rule"><span>PAYLOAD</span></div>
    ${keyValueRows(actionPayloadRows(payload))}
    ${confirmation}
    <div class="action-buttons">
      <button class="primary-action compact" type="button" data-action="submit-action" ${canSubmit ? "" : "disabled"}>${escapeHtml(action.button || "提交")}</button>
      <button type="button" data-action="show-status">查看任务</button>
    </div>
  `);
}

function renderJobPanel(job) {
  if (!job) return;
  const terminal = isTerminalJob(job);
  openActionPanel(`${job.label || job.action} · ${jobStatusText(job.status)}`, `
    ${keyValueRows([
      ["Job ID", job.id],
      ["状态", jobStatusText(job.status)],
      ["项目", job.project_id || "repo"],
      ["命令", job.command || "request file"],
      ["更新", formatDate(job.updated_at)],
      ["退出码", job.exit_code === undefined ? "—" : String(job.exit_code)],
    ])}
    ${job.error ? `<p class="error-text">${escapeHtml(job.error)}</p>` : ""}
    <div class="section-rule"><span>LOG TAIL</span></div>
    <pre class="job-log">${escapeHtml(job.log_tail || "等待日志输出...")}</pre>
    <div class="action-buttons">
      <button type="button" data-action="refresh-job" data-job-id="${escapeHtml(job.id)}">刷新日志</button>
      <button type="button" data-action="show-status">查看所有任务</button>
      ${terminal && job.status === "succeeded" ? `<button type="button" data-action="reload-studio">刷新项目数据</button>` : ""}
    </div>
  `);
}

async function refreshJob(jobId) {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`job ${response.status}`);
  const job = await response.json();
  studioState.activeJobId = job.id;
  renderJobPanel(job);
  if (isTerminalJob(job)) {
    window.clearInterval(jobPollTimer);
    jobPollTimer = 0;
    await loadJobs().catch(() => {});
    showToast(job.status === "succeeded" ? "任务已完成" : "任务失败，请查看日志");
  }
  return job;
}

function startJobPolling(jobId) {
  window.clearInterval(jobPollTimer);
  studioState.activeJobId = jobId;
  jobPollTimer = window.setInterval(() => {
    refreshJob(jobId).catch(() => {
      window.clearInterval(jobPollTimer);
      jobPollTimer = 0;
      showToast("任务日志刷新失败");
    });
  }, 1500);
}

async function submitPendingAction() {
  const pending = studioState.pendingAction;
  if (!pending) {
    showToast("没有准备中的动作");
    return;
  }
  const payload = {
    ...pending.payload,
    action: pending.action.id,
    confirmed: Boolean(pending.action.requires_confirmation),
  };
  const response = await fetch("/api/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  await loadJobs().catch(() => {});
  renderJobPanel(data);
  if (!isTerminalJob(data)) startJobPolling(data.id);
  showToast("任务已提交");
}

function showResumeCommand() {
  const detail = studioState.detail;
  if (!detail?.id) {
    showToast("等待项目状态接入");
    return;
  }
  prepareAction("request_resume", defaultActionPayload("request_resume"));
}

function renderProjectDetail(detail) {
  studioState.detail = detail;
  studioState.activeProjectId = detail.id;
  localStorage.setItem("aladdin-studio-project", detail.id);
  refreshPageChrome();
  renderWorkbench(detail);
  renderAssets(detail);
  renderScript(detail);
  renderStoryboard(detail);
  renderExport(detail);
  renderModels();
}

async function loadProjectDetail(projectId, options = {}) {
  if (!projectId) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`project ${projectId} ${response.status}`);
  const detail = await response.json();
  renderProjectDetail(detail);
  if (options.view) switchView(options.view);
}

async function loadStudioData(options = {}) {
  try {
    const response = await fetch("/api/projects", { cache: "no-store" });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    studioState.connected = true;
    studioState.projects = data.projects || [];
    studioState.config = data.config || null;
    await Promise.allSettled([loadActionCatalog(), loadJobs()]);
    renderShellData(data);
    renderStats(data.stats);
    renderHubContent(data);
    renderModels(data.config);

    const savedProject = localStorage.getItem("aladdin-studio-project");
    const activeProject = studioState.projects.find((item) => item.id === savedProject) || studioState.projects[0];
    if (activeProject) await loadProjectDetail(activeProject.id);
    if (!options.silent) showToast(`已接入 ${studioState.projects.length} 个本地项目`);
  } catch (error) {
    studioState.connected = false;
    if (!options.silent) showToast("未连接本地 API，只显示空占位");
  }
}

function advanceNode() {
  showResumeCommand();
}

document.addEventListener("click", async (event) => {
  const shotRow = event.target.closest(".shot-row");
  if (shotRow) {
    selectShot(Number(shotRow.dataset.shotIndex || 0));
    return;
  }

  const nodeButton = event.target.closest(".node-card[data-node-index]");
  if (nodeButton) {
    selectPipelineNode(Number(nodeButton.dataset.nodeIndex || 0));
    return;
  }

  const projectButton = event.target.closest(".project-open[data-project-id]");
  if (projectButton) {
    event.preventDefault();
    try {
      await loadProjectDetail(projectButton.dataset.projectId, { view: projectButton.dataset.viewTarget || "workbench" });
    } catch (error) {
      showToast(`项目读取失败：${projectButton.dataset.projectId}`);
    }
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const action = actionButton.dataset.action;
    if (action === "show-status") showStatusPanel();
    if (action === "preview-script") await previewScript();
    if (action === "preview-shot") previewShot();
    if (action === "inspect-export") inspectExport();
    if (action === "copy-command") await copyText(actionButton.dataset.command, "已复制命令");
    if (action === "select-script") selectScript(Number(actionButton.dataset.scriptIndex || 0));
    if (action === "prepare-action") await prepareAction(actionButton.dataset.actionId);
    if (action === "toggle-action-confirmation") {
      const submitButton = actionPanelBody?.querySelector('[data-action="submit-action"]');
      if (submitButton) submitButton.disabled = !actionButton.checked;
    }
    if (action === "submit-action") {
      try {
        actionButton.disabled = true;
        await submitPendingAction();
      } catch (error) {
        actionButton.disabled = false;
        showToast(`任务提交失败：${error.message}`);
      }
    }
    if (action === "open-job" || action === "refresh-job") {
      try {
        const job = await refreshJob(actionButton.dataset.jobId);
        if (!isTerminalJob(job)) startJobPolling(job.id);
      } catch (error) {
        showToast("任务读取失败");
      }
    }
    if (action === "reload-studio") await loadStudioData();
    if ([
      "show-status",
      "preview-script",
      "preview-shot",
      "inspect-export",
      "copy-command",
      "select-script",
      "prepare-action",
      "toggle-action-confirmation",
      "submit-action",
      "open-job",
      "refresh-job",
      "reload-studio",
    ].includes(action)) return;
  }

  const targetButton = event.target.closest("[data-view-target]");
  if (targetButton) {
    closeActionPanel();
    switchView(targetButton.dataset.viewTarget);
    return;
  }

  const sourceButton = event.target.closest(".source-option");
  if (sourceButton) {
    document.querySelectorAll(".source-option").forEach((button) => button.classList.remove("is-selected"));
    sourceButton.classList.add("is-selected");
    studioState.selectedSource = sourceButton.dataset.source;
  }
});

document.querySelector("#refreshButton")?.addEventListener("click", () => {
  loadStudioData();
});

document.querySelector("#continueButton")?.addEventListener("click", advanceNode);

document.querySelector("#commandButton")?.addEventListener("click", openPalette);
document.querySelector("#closePalette")?.addEventListener("click", closePalette);
document.querySelector("#closeActionPanel")?.addEventListener("click", closeActionPanel);

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openPalette();
  }

  if (event.key === "Escape" && !palette.hidden) {
    closePalette();
  }

  if (event.key === "Escape" && actionPanel && !actionPanel.hidden) {
    closeActionPanel();
  }
});

palette.addEventListener("click", (event) => {
  if (event.target === palette) closePalette();
});

actionPanel?.addEventListener("click", (event) => {
  if (event.target === actionPanel) closeActionPanel();
});

updateClock();
window.setInterval(updateClock, 1000);

const initialView = window.location.hash.replace("#", "");
if (pageMeta[initialView]) switchView(initialView, { updateUrl: false });

window.addEventListener("hashchange", () => {
  const nextView = window.location.hash.replace("#", "") || "hub";
  switchView(pageMeta[nextView] ? nextView : "hub", { updateUrl: false });
});

loadStudioData({ silent: true });
