# 环境搭建指南

## 前置条件

| 依赖 | 用途 | 安装方式 |
|------|------|---------|
| [Claude Code](https://claude.ai/code) | Agent 运行时（必需） | `npm install -g @anthropic-ai/claude-code` |
| `bash` (4.0+) | 脚本执行 | macOS 自带 / `brew install bash` |
| `jq` | JSON 处理 | `brew install jq` |
| `python3` | 辅助脚本 | macOS 自带 / `brew install python3` |
| `ffmpeg` | 视频拼接 | `brew install ffmpeg` |
| `shellcheck` | Shell lint（开发） | `brew install shellcheck` |
| `yq` | YAML 处理 | `brew install yq` |

> **macOS 一键安装**：`brew install jq ffmpeg yq shellcheck`

### 可选依赖

| 依赖 | 用途 | 说明 |
|------|------|------|
| `actionbook` (>= 0.6.0) | 浏览器模式视频生成 | 仅 `generation_backend: "browser"` 时需要 |
| `lark-cli` | 飞书通知 | 仅启用飞书审核集成时需要 |
| `yamllint` | YAML 格式校验 | 开发/CI 使用 |

## API Key 申请

### 必需

**火山方舟（ARK_API_KEY）** — 视频生成
- 注册地址：https://www.volcengine.com/product/ark
- 开通 Seedance 模型权限后，在控制台 → API Key 管理中创建

### 推荐

**兔子 API（TUZI_API_KEY）** — 图像生成 + LLM 调用
- 注册地址：https://api.tu-zi.com
- 设置后自动用于图像生成和 Trace 摘要，无需再单独配置 `IMAGE_GEN_API_KEY`

## 环境变量

### 配置方式

推荐在项目根目录创建 `.env` 文件（已在 `.gitignore` 中，不会提交）：

```bash
# .env
ARK_API_KEY=your-ark-key-here
TUZI_API_KEY=your-tuzi-key-here
```

然后在每次使用前 `source .env`，或写入 `~/.zshrc` / `~/.bashrc` 永久生效。

### 完整变量列表

```bash
# 必需
export ARK_API_KEY="..."        # 火山方舟 API Key（Seedance 视频生成）

# 推荐
export TUZI_API_KEY="..."       # 兔子 API Key（图像生成 + LLM）
                                # 设置后自动用于 IMAGE_GEN 和 Nanobanana

# 可选（不设则自动用 TUZI_API_KEY）
export IMAGE_GEN_API_URL="..."  # 自定义图像生成端点
export IMAGE_GEN_API_KEY="..."  # 自定义图像生成 Key
export OPENAI_API_KEY="..."     # OpenAI Moderation API（合规层第三层）
export DEEPSEEK_API_KEY="..."   # Trace LLM 摘要
export LARK_APP_ID="..."        # 飞书应用 ID（审核通知）
export LARK_APP_SECRET="..."    # 飞书应用 Secret（审核通知）
export REVIEW_SERVER_URL="..."  # Review Server 地址（默认 http://localhost:8080）
```

### 验证

```bash
./scripts/api-caller.sh env-check
```

## Dreamina CLI 安装与登录

Dreamina 是默认的视频生成后端（即梦官方 CLI）。

### 安装

```bash
curl -fsSL https://jimeng.jianying.com/cli | bash
```

### 登录

```bash
# 方式 1：浏览器授权（推荐，本地环境）
dreamina login

# 方式 2：终端 QR 码（适合远程/无界面环境）
dreamina login --headless
```

### 验证登录 + 查看余额

```bash
dreamina user_credit
```

> **注意**：每次视频生成消耗 credit，建议先用少量集数测试，确认效果后再批量生成。

### 切换后端

如需切换回 API 模式，编辑 `config/platforms/seedance-v2.yaml`：

```yaml
generation_backend: "api"   # 或 "dreamina"（默认）
```

## Review Server（可选）

用于飞书审核集成的 Web 服务。

```bash
cd review-server
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

额外环境变量：

```bash
export CLAUDE_TRIGGER_ID="..."     # Claude Code Remote Trigger ID
export CLAUDE_TRIGGER_TOKEN="..."  # Claude Code API Token
```

详细信息见 [review-server/README.md](../review-server/README.md)。

## 浏览器模式（备用）

当 Dreamina CLI 不可用时，可通过浏览器操作即梦 Web UI 生成视频。

### 启用

编辑 `config/platforms/seedance-v2.yaml`：

```yaml
generation_backend: "browser"
```

### 首次登录

```bash
./scripts/api-caller.sh jimeng-web setup
# 浏览器弹出，手动登录即梦，登录后 Ctrl+C
```

### 注意事项

- 需要 `actionbook` CLI >= 0.6.0
- 支持 1-3 标签页并行（通过 `seedance-v2.yaml` 的 `browser_backend.concurrency` 配置）
- CSS 选择器可能因即梦 UI 更新而失效

## VectorDB（可选，v2.0）

v2.0 的 `memory-agent` 使用 LanceDB 做语义检索。

```bash
pip install lancedb sentence-transformers
python3 scripts/vectordb-manager.py init
python3 scripts/vectordb-manager.py stats
```

可选环境变量：

```bash
export VECTORDB_PATH="state/vectordb/lancedb"
```

说明：
- `sentence-transformers` 装好后会自动启用本地多语言 embedding
- `memory-agent` 会先查 entities / states / relations，再查 assets
- `gen-worker` / `qa-agent` / `repair-agent` 会在线写入 `upsert-state`

## 目录初始化

首次运行时，以下目录会自动创建，无需手动操作：

```
outputs/         # 产出文件
state/           # 状态文件
state/reviews/   # 审核状态
state/traces/    # Trace 日志
assets/packs/    # v2.0 资产包
```

## 常见问题

### Q: `env-check` 报缺少 ARK_API_KEY

确认环境变量已导出到当前 shell session。如果使用 `.env` 文件，需要先 `source .env`。

### Q: `~command` 命令找不到 / 没有反应

这些命令需要在 **Claude Code** 里运行，不是普通 shell 命令。确认已用 `claude` 命令启动 Claude Code，并且当前目录是项目根目录。

### Q: 图像生成失败

检查 `TUZI_API_KEY` 是否设置。如果使用自定义端点，确认 `IMAGE_GEN_API_URL` 和 `IMAGE_GEN_API_KEY` 都已设置。

### Q: 视频生成超时

Seedance API 生成需要时间（通常 30-120 秒）。`api-caller.sh` 默认超时 300 秒。如果频繁超时，检查网络或 API 状态。

### Q: Dreamina 报 `AigcComplianceConfirmationRequired`

部分模型首次使用需要在即梦 Web 端完成授权确认。打开 https://jimeng.jianying.com 登录后，按提示完成确认即可。

### Q: shellcheck 报错

macOS 自带的 bash 版本较旧（3.x），部分语法不兼容。使用 `brew install bash` 安装 4.0+ 版本。
