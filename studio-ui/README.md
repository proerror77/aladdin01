# 动态漫 Studio UI

本目录是 Aladdin 的本地控制台前端。

## 运行

```bash
python3 studio-ui/server.py --port 4173
```

打开：

```text
http://127.0.0.1:4173/
```

## 数据接入

`server.py` 使用 Python 标准库提供项目读取 API 和受控动作 API。会修改状态或触发 Agent 的动作必须经过前端确认，并且只允许后端白名单里的动作：

- `GET /api/projects`：扫描 `projects/*`，返回项目列表、统计卡片、进度摘要。
- `GET /api/projects/{id}`：返回单个项目的脚本、角色、场景、分镜、交付物、状态文件摘要。
- `GET /media/{repo-relative-path}`：安全读取仓库内图片/视频资产，用于前端预览。
- `GET /api/actions`：返回可执行动作白名单和能力状态。
- `POST /api/actions`：提交动作 job，异步执行并写入日志。
- `GET /api/jobs` / `GET /api/jobs/{id}`：查看最近任务和日志尾部。

前端会优先读取这些 API；如果直接打开 `index.html` 或用普通静态服务器打开，则自动退回静态演示模式。
