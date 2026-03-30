# 飞书审核集成 + Review Server 设计

## 背景

当前 E2E 流程（`~scriptwriter-to-video`）的 7 个确认点全部依赖 CLI 交互——用户必须盯着终端等。视觉类内容（角色图、场景图、视频）无法在终端有效审核。需要：

1. 确认点通过飞书异步通知，用户不用盯终端
2. 视觉内容通过 Web 页面审核（图片网格、版本对比、视频播放）
3. 审核拒绝时可带原因重做，agent 根据原因修改

## 核心架构

```
Claude Code Session              飞书                    Review Server
      │                           │                          │
      ├── 到达确认点              │                          │
      ├── 写 state/reviews/{id}   │                          │
      ├── 发送卡片 ──────────────→│ 用户看到通知              │
      ├── session 结束            │                          │
      │                           │                          │
      │                     点卡片按钮（文字类）──────────→  │ webhook 回调
      │                     点链接打开 Web（视觉类）──────→  │ 页面审核
      │                           │                          │
      │                           │               写 review response
      │                           │               触发 Remote Trigger
      │                           │                          │
      ├── 新 session（--resume）   │                          │
      ├── 读 review response      │                          │
      ├── approve → 继续          │                          │
      ├── redo → 重跑 + reason    │                          │
      └── terminate → 结束        │                          │
```

## 飞书卡片设计

### 分层策略

| 确认点类型 | 飞书卡片 | 审核方式 |
|-----------|---------|---------|
| 文字类（大纲/质量报告） | 摘要 + 3 按钮 | 卡片按钮直接审 |
| 视觉类（角色图/场景图） | 缩略图 + Web 链接 | Web 页面审核 |
| 视频类（生成的视频） | 摘要 + Web 链接 | Web 页面审核 |

### 卡片按钮

所有卡片统一 3 个操作：
- **通过**：流程继续
- **重做（附原因）**：重跑当前确认点，reason 作为 agent 输入
- **终止**：流程结束

### 各确认点卡片内容

| 确认点 | 摘要字段 | 附件 |
|--------|---------|------|
| 大纲确认 | 剧名、集数、主角、核心冲突 | outline.md |
| 质量报告 | 严重/一般问题数、各维度评分 | review-report.md |
| 主角形象 | 角色名 + 缩略图 | assets/characters/images/ |
| 视觉指导 | 镜次数、总时长 | visual-direction.yaml |
| 美术校验 | 角色/场景引用数、缺失数 | art-direction-review.md |

## Review Server

一个 FastAPI 服务，三合一：审核 UI + Webhook 接收 + Trace 查看。

### 目录结构

```
review-server/
├── server.py              # FastAPI 主服务
├── templates/
│   ├── review.html        # 审核页模板（通用）
│   ├── outline.html       # 大纲审核（文字类）
│   ├── visual.html        # 视觉审核（图片网格 + 版本对比）
│   ├── video.html         # 视频审核（播放器 + 镜次列表）
│   └── trace.html         # Trace 查看页
├── static/                # CSS/JS
├── requirements.txt       # fastapi, uvicorn, jinja2, httpx
└── config.yaml            # 端口、回调地址
```

### 核心路由

```
GET  /review/{review-id}           → 审核页面（根据 type 渲染不同模板）
POST /review/{review-id}/approve   → 通过
POST /review/{review-id}/redo      → 重做（body: {reason, selected_items}）
POST /review/{review-id}/terminate → 终止
POST /webhook/lark                 → 飞书卡片按钮回调
GET  /assets/{path}                → 静态资源代理（角色图/场景图/视频）
GET  /trace/{session-id}           → Trace 查看页
GET  /trace/{session-id}/{ep}      → 单集 trace
```

### 审核页面

**视觉审核页（角色形象）**：

```
┌─────────────────────────────────────────────────────┐
│ 🎬 love-coffee / 阶段 3：主角形象确认（第 2 轮）     │
│                                                     │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│ │  林风-正面   │  │  林风-侧面   │  │  苏晚-正面   │  │
│ │  [图片]     │  │  [图片]     │  │  [图片]     │  │
│ │  v2 ← v1   │  │  v1         │  │  v1         │  │
│ └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
│ 📝 修改意见（可选）：[____________]                  │
│                                                     │
│ [✅ 全部通过]  [🔄 重做选中角色]  [❌ 终止项目]      │
└─────────────────────────────────────────────────────┘
```

### Webhook 处理

```python
@app.post("/webhook/lark")
async def lark_card_callback(request):
    action = parse_lark_action(request)
    review_id = action["review_id"]
    reason = action.get("reason", "")

    write_review_response(review_id, action, reason)
    trigger_resume(review_id)
    update_lark_card(review_id, action)  # 按钮变灰 + 显示结果

@app.post("/review/{review_id}/redo")
async def web_redo(review_id, body):
    write_review_response(review_id, "redo", body.reason, body.selected_items)
    trigger_resume(review_id)
    update_lark_card(review_id, "redo")  # 同步更新飞书卡片
```

### Remote Trigger 唤醒

```python
def trigger_resume(review_id):
    review = read_review(review_id)
    project = review["project"]
    requests.post(
        f"https://api.claude.ai/v1/code/triggers/{TRIGGER_ID}/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": f"~scriptwriter-to-video --resume {project}"}
    )
```

## 拒绝退回流程

### 三种审核结果

```
approve   → e2e-progress.json 进入下一阶段 → Remote Trigger 继续
redo      → e2e-progress.json iteration+1 → Remote Trigger 重跑当前阶段
terminate → e2e-progress.json terminated  → 发终止告警卡片
```

### 重做时 reason 传递

| 确认点 | 重做执行者 | reason 用法 |
|--------|-----------|------------|
| 大纲确认 | outline-agent | 修改指令，局部修改大纲 |
| 质量报告 | episode-writer-agent | 指出要改哪几集的什么问题 |
| 主角形象 | ~design | selected_items 指定重新生成哪些角色图 |
| 视觉指导 | visual-agent | 镜次拆分或 prompt 问题 |
| 美术校验 | ~design | 缺失或不满意的参考图 |

### 重做上限

每个确认点最多 5 次重做。超限后发飞书告警：
```
⚠️ 大纲已重做 5 次，达到上限。
[手动编辑后继续]  [终止项目]
```

### 退回范围

重做只回退当前确认点，不影响已完成阶段。

## 审核状态文件

`state/reviews/{review-id}.json`：

```json
{
  "id": "review-20260329-153000-outline",
  "project": "love-coffee",
  "stage": "1_scriptwriter",
  "checkpoint": "outline",
  "type": "text",
  "status": "pending",
  "iteration": 1,
  "max_iterations": 5,
  "created_at": "2026-03-29T15:30:00Z",
  "content": {
    "title": "《咖啡遇上代码》大纲确认",
    "summary": "15集都市爱情，主角：林风×苏晚",
    "files": ["outputs/scriptwriter/love-coffee/outline.md"]
  },
  "assets": [],
  "lark_card_id": "msg_xxxxx",
  "review_url": "https://review.local/review/review-20260329-153000-outline",
  "response": null,
  "history": []
}
```

重做后 `history` 记录每轮：
```json
{
  "history": [
    {
      "iteration": 1,
      "action": "redo",
      "reason": "主角年龄改为 22 岁",
      "responded_at": "2026-03-29T15:45:00Z"
    }
  ],
  "iteration": 2,
  "status": "pending"
}
```

## 异常告警

除审核确认点外，agent 异常也推送飞书（纯通知，不阻塞）：

| 事件 | 卡片内容 |
|------|---------|
| shot 生成失败 | shot ID + 拒绝原因 + trace 链接 |
| 合规拦截比例 >30% | 改写数量 + 严重改写列表 |
| 阶段耗时异常（>3x 预期） | 阶段名 + 耗时 |
| E2E 流程终止 | 终止原因 + 进度快照 |

告警卡片含 Trace 查看链接：`review.local/trace/{session}/ep01/shot-03`

## 新增文件清单

| 文件 | 说明 |
|------|------|
| `review-server/server.py` | FastAPI 主服务 |
| `review-server/templates/*.html` | 审核页 + trace 查看页 |
| `review-server/static/` | CSS/JS |
| `review-server/requirements.txt` | Python 依赖 |
| `config/lark/lark-config.yaml` | 飞书 app 配置 |
| `config/lark/card-templates/*.json` | 卡片模板 |
| `.claude/skills/notify.md` | `~notify` 内部 skill |
| `scripts/notify.sh` | 飞书通知发送脚本 |

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `.claude/skills/scriptwriter-to-video.md` | 确认点改为异步审核模式 |
| `.claude/skills/start.md` | 确认点改为异步审核模式 |
| `.claude/skills/scriptwriter.md` | 确认点改为异步审核模式 |
| `CLAUDE.md` | 新增飞书集成、Review Server、环境变量 |
| `state/progress-schema.yaml` | 新增 review state schema |

## 实施顺序

### Phase 1：基础管道（先跑通一个确认点）

1. `config/lark/` 配置文件
2. `scripts/notify.sh` 发卡片脚本
3. `review-server/` 最小可用版（1 个路由 + 1 个模板 + webhook）
4. `scriptwriter-to-video` 的大纲确认点接入

### Phase 2：全量接入

1. 所有确认点接入飞书通知
2. 3 种审核模板（text / visual / video）
3. 重做流程 + iteration 历史 + reason 传递

### Phase 3：告警 + Trace 可视化

1. 异常告警推送
2. Trace 查看页（复用 review-server）

## 环境变量

```bash
export LARK_APP_ID="cli_xxxxx"
export LARK_APP_SECRET="xxxxx"
export REVIEW_SERVER_URL="http://localhost:8080"
```

## 决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 通知范围 | 全部确认点 + 异常告警 | 用户不想盯终端 |
| 审核交互 | 飞书卡片（文字）+ Web（视觉/视频） | 视觉内容需要图片/视频预览 |
| 拒绝退回 | 重做(附原因) / 终止，在卡片或 Web 上选择 | 重做时 reason 作为 agent 输入 |
| 回调机制 | Webhook → Remote Trigger | 解耦，session 不用挂着等 |
| Web 服务 | FastAPI 三合一（审核+Webhook+Trace） | 轻量，一个服务解决所有问题 |
| 重做上限 | 5 次/确认点 | 防止死循环 |
| 退回范围 | 只回退当前确认点 | 不影响已完成的阶段 |
