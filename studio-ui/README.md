# 动态漫 Studio UI

本目录是 Aladdin 的本地控制台前端。它用一个 Python 标准库服务器提供静态页面、项目读取 API 和受控动作 API，不引入前端框架或额外服务。

## 运行

```bash
python3 studio-ui/server.py --port 4173
```

打开：

```text
http://127.0.0.1:4173/
```

默认只监听 `127.0.0.1`。如果需要换端口：

```bash
STUDIO_UI_PORT=4180 python3 studio-ui/server.py
```

## 能做什么

- 面向桌面宽屏 Operator Cockpit；日常操作目标是本地制作台，不把移动端作为主要交互场景。
- 浏览 `projects/*` 下的项目、进度、脚本、角色/场景资产、分镜图、视频和交付物。
- 在生产流程页按真实 v2 链路查看 `剧本 → 本体论 → 合规预检 → 视觉指导 → 叙事审查 → Storyboard → 资产工厂 → 美术校验 → Shot Packet → 音色配置 → 视频生成 → QA/Repair → 交付`。
- 在同一个流程页看到当前阶段、待处理审核项、Storyboard 预览、Shot Packet 状态和人物 / 场景关系网。
- 在人物资产页查看角色档案、场景设定、关系网、资产包矩阵和设定资料。
- 预览仓库内媒体文件和脚本文本。
- 从“准备下一步”进入受控动作确认面板，再提交 job、查看日志尾部。
- 通过最近任务列表追踪 job 状态。

## 受控动作

`server.py` 的 `ACTION_REGISTRY` 是唯一动作白名单。前端只能提交 registry 里定义过的动作，不能传入任意 shell 命令。

| 动作 | 范围 | 是否修改 | 是否需要确认 | 执行内容 |
| --- | --- | --- | --- | --- |
| `env_check` | repo | 否 | 否 | `bash scripts/api-caller.sh env-check` |
| `workflow_sync` | project | 是 | 是 | `python scripts/workflow-sync.py --project <id>`，可附带 episode |
| `request_resume` | project | 是 | 是 | 写入继续生成请求；配置远端触发器时尝试触发远端 Agent |
| `trace_summary` | repo | 是 | 是 | `bash scripts/api-caller.sh trace-summary <trace-session>` |

确认规则：

- `requires_confirmation: true` 的动作如果没有 `confirmed: true`，后端返回 `403 confirmation required`。
- `project_id`、`episode`、`trace_session` 都在后端校验；非法项目、非法集数或不存在的 trace session 会返回 `400`。
- job JSON 使用原子写入，避免前端轮询读到半写入状态。

## Job 状态

动作提交后会生成本地 job 文件。前端轮询 job API，不直接读取这些文件：

- job 元数据：`state/ui-actions/jobs/<job-id>.json`
- job 日志：`state/ui-actions/jobs/<job-id>.log`
- 继续生成请求：`state/ui-actions/requests/<job-id>.json`

常见状态：

- `queued`：已经进入队列，后台线程准备执行。
- `running`：子进程或请求写入正在执行。
- `succeeded`：执行完成且退出码为 0，或继续请求已写入/触发成功。
- `failed`：执行失败、参数非法、远端触发失败或子进程非 0 退出。

## API

- `GET /api/projects`：扫描 `projects/*`，返回项目列表、统计卡片、进度摘要。
- `GET /api/projects/{id}`：返回单个项目的脚本、角色、场景、分镜、交付物、状态文件摘要。
- `GET /media/{repo-relative-path}`：安全读取仓库内图片/视频资产，用于前端预览。
- `GET /api/actions`：返回可执行动作白名单和能力状态。
- `POST /api/actions`：提交动作 job，异步执行并写入日志。
- `GET /api/jobs` / `GET /api/jobs/{id}`：查看最近任务和日志尾部。

示例：

```bash
curl http://127.0.0.1:4173/api/actions
curl -X POST http://127.0.0.1:4173/api/actions \
  -H 'Content-Type: application/json' \
  --data '{"action":"env_check"}'
```

需要确认的动作：

```bash
curl -X POST http://127.0.0.1:4173/api/actions \
  -H 'Content-Type: application/json' \
  --data '{"action":"workflow_sync","project_id":"qyccan","confirmed":true}'
```

## 验证

改动服务器或前端脚本后至少跑：

```bash
python3 -m py_compile studio-ui/server.py
node --check studio-ui/app.js
```

对动作链路做 smoke：

```bash
python3 studio-ui/server.py --port 4173
curl http://127.0.0.1:4173/api/actions
curl -X POST http://127.0.0.1:4173/api/actions \
  -H 'Content-Type: application/json' \
  --data '{"action":"env_check"}'
```

确认浏览器里能完成：

- 打开状态面板。
- 准备并提交环境检查。
- 查看 job 日志轮询到完成。
- 打开继续生成请求，确认提交按钮在勾选确认前不可用。

## 注意事项

- 不要把任意命令执行接口暴露到前端；新增动作必须先进入 `ACTION_REGISTRY`，并在后端校验 payload。
- 不要把 API key 写进 job JSON 或日志；配置页只展示环境变量是否存在。
- `state/ui-actions/` 是运行时状态，不是 UI 源码。
- 前端依赖这些 API；直接打开 `index.html` 或用普通静态服务器打开时，动作提交和轮询不可用。
