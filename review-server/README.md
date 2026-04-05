# Review Server

审核 UI + Webhook 接收 + Trace 查看，三合一轻量 FastAPI 服务。

## 功能

- **审核页面**：展示待审核内容（文字/图片/视频），支持 Approve / Redo / Abort 操作
- **Webhook 接收**：接收飞书卡片按钮回调
- **Trace 查看**：可视化 Agent Trace Log
- **资产服务**：提供角色图/场景图/视频的文件访问

## 安装

```bash
cd review-server
pip install -r requirements.txt
```

依赖：
- `fastapi` >= 0.104.0
- `uvicorn` >= 0.24.0
- `jinja2` >= 3.1.2
- `httpx` >= 0.25.0
- `pyyaml` >= 6.0
- `python-multipart` >= 0.0.6

## 启动

```bash
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REVIEW_SERVER_URL` | 外部可访问的 URL | `http://localhost:8080` |
| `PROJECT_ROOT` | 项目根目录 | `..`（server.py 的上级目录） |
| `CLAUDE_TRIGGER_ID` | Claude Code Remote Trigger ID | （空，可选） |
| `CLAUDE_TRIGGER_TOKEN` | Claude Code API Token | （空，可选） |

`CLAUDE_TRIGGER_ID` 和 `CLAUDE_TRIGGER_TOKEN` 用于审核完成后自动唤醒 Claude Code session 继续 E2E 流程。

## API 路由

### 审核页面

| 路由 | 方法 | 说明 |
|------|------|------|
| `/review/{review_id}` | GET | 渲染审核页面 |
| `/review/{review_id}/approve` | POST | 通过审核 |
| `/review/{review_id}/redo` | POST | 请求重做（附 reason） |
| `/review/{review_id}/abort` | POST | 终止流程 |

### Redo 请求体

```json
{
  "reason": "主角服装颜色不对",
  "selected_items": ["shot-03", "shot-07"]
}
```

### Trace 查看

| 路由 | 方法 | 说明 |
|------|------|------|
| `/traces` | GET | Trace session 列表 |
| `/traces/{session_id}` | GET | 查看 session 详情 |

### 静态资产

| 路由 | 方法 | 说明 |
|------|------|------|
| `/assets/{path}` | GET | 项目资产文件访问 |

## 审核流程

```
Claude Code agent 写 state/reviews/{id}.json
       ↓
notify.sh 发飞书卡片（摘要 + 链接）
       ↓
用户点击链接打开 Review Server 页面
       ↓
用户操作（Approve / Redo / Abort）
       ↓
Review Server 写入 response → 触发 Remote Trigger
       ↓
新 Claude Code session 读取 response，继续流程
```

## 审核状态文件

位于 `state/reviews/{review_id}.json`，格式：

```json
{
  "id": "review-ep01-outline-20260401",
  "project": "jiuba",
  "type": "text",
  "status": "pending",
  "checkpoint": "outline_confirmation",
  "summary": "大纲摘要...",
  "assets": ["outputs/scriptwriter/jiuba/outline.md"],
  "response": null
}
```

`status` 取值：`pending` → `approved` / `redo` / `aborted`

## 目录结构

```
review-server/
├── server.py          # FastAPI 应用
├── requirements.txt   # Python 依赖
├── static/            # 静态资源（CSS/JS）
└── templates/         # Jinja2 模板
    ├── text_review.html
    ├── visual_review.html
    └── ...
```
