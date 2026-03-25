# ~start — 单剧本模式

启动单个剧本的完整生产流水线。

## 使用方式

```
~start
```

在 `script/` 目录下放好剧本文件后运行。

## 执行流程

### 0. 环境变量预检

在开始前验证所有必需的环境变量：
```bash
./scripts/api-caller.sh env-check
```

检查：
- `ARK_API_KEY`
- `IMAGE_GEN_API_URL`
- `IMAGE_GEN_API_KEY`
- `OPENAI_API_KEY`

如果有缺失：
```
❌ 环境变量缺失：
- ARK_API_KEY
- OPENAI_API_KEY

请设置后再运行 ~start
```

### 1. 检测剧本

扫描 `script/` 目录，列出所有 `.md` 文件。

如果有多个文件，询问用户选择哪个：
```
发现以下剧本：
1. ep01.md
2. ep02.md
请选择（输入数字）：
```

如果只有一个文件，直接使用。

如果没有文件：
```
script/ 目录下没有找到剧本文件。
请将剧本放入 script/ 目录（.md 格式），然后重新运行 ~start
```

### 2. 交互式配置

**选择视觉风格**：
```
请选择视觉风格：
1. 写实电影感（真人短剧）
2. 国风古装
3. 现代都市
4. 动漫风格
5. 其他（请描述）
```

**选择目标媒介**：
```
请选择目标媒介：
1. 竖屏短视频（9:16，抖音/快手）
2. 横屏视频（16:9，YouTube/B站）
3. 方形（1:1，Instagram）
```

### 3. 初始化目录和状态

```bash
mkdir -p outputs/{ep}/videos
```

初始化 `state/progress.json`：
```json
{
  "version": "1.0",
  "episodes": {
    "{ep}": {
      "status": "in_progress",
      "current_phase": 0
    }
  }
}
```

### 4. 启动 Agent Team

创建 team，按顺序执行：

**Phase 1 — 合规预检**
```
spawn comply-agent
  输入：script/{ep}.md
  等待完成
```

**Phase 2 — 视觉指导**
```
spawn visual-agent
  输入：outputs/{ep}/render-script.md + 视觉风格 + 目标媒介
  等待完成
```

🔴 **人工确认点 1**
```
视觉指导已完成，请查看：outputs/{ep}/visual-direction.yaml

共 {N} 个镜次，总时长约 {X} 秒。

确认后继续美术指导阶段？(yes/no)
```
- 输入 `yes` → 继续 Phase 3
- 输入 `no` → 进入修改流程（~review revise {ep}）

**Phase 3 — 美术指导**
```
spawn design-agent
  输入：render-script + visual-direction.yaml
  等待完成
```

🔴 **人工确认点 2**
```
参考图已生成，请查看：outputs/{ep}/art-direction-review.md

角色参考图：assets/characters/images/
场景参考图：assets/scenes/images/

确认后继续音色配置阶段？(yes/no)
```
- 输入 `yes` → 继续 Phase 4
- 输入 `no` → 进入修改流程

**Phase 4 — 音色配置**
```
spawn voice-agent
  输入：render-script + visual-direction.yaml
  等待完成（voice-agent 会交互式询问用户）
```

**Phase 5 — 视频生成（并行）**

1. 读取 `outputs/{ep}/visual-direction.yaml`，提取所有镜次数据
2. 为每个镜次组装 gen-worker 参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| ep | 用户选择 | 剧本 ID |
| shot_id | shots[].shot_id | 镜次完整 ID |
| shot_index | shots[].shot_index | 镜次序号 |
| prompt | shots[].prompt | 组装好的 Seedance 提示词 |
| duration | shots[].duration | 视频时长（秒） |
| generation_mode | shots[].generation_mode | `text2video` 或 `img2video` |
| reference_image_path | shots[].references[0].image_path | 参考图路径（如有） |
| dialogue | shots[].audio | 对白内容（唇形同步用） |
| voice_config_path | 根据 shots[].audio 中的角色名查找 | 音色配置路径 |

3. 并行 spawn gen-workers：
```
spawn gen-worker (shot-1 params)
spawn gen-worker (shot-2 params)
...
spawn gen-worker (shot-N params)
等待所有 worker 完成
```

### 5. 汇总结果

读取所有 `state/{ep}-shot-*.json` 文件，统计成功/失败镜次。

生成 `outputs/{ep}/generation-report.md`：

```markdown
# 视频生成报告 - {ep}

## 总览

- 总镜次：{N}
- 成功：{S}
- 失败：{F}
- 生成时间：{timestamp}

## 成功镜次

| 镜次 | 视频文件 | 重试次数 | 改写轮次 |
|------|----------|----------|----------|
| shot-01 | videos/shot-01.mp4 | 0 | 0 |

## 失败镜次（需人工处理）

| 镜次 | 最后使用的提示词 | 失败原因 |
|------|-----------------|----------|
| shot-05 | ... | 3轮改写后仍被拒绝 |

## 输出目录

outputs/{ep}/videos/
```

输出最终结果给用户。