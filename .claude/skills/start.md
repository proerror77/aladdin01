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

### 2.5 A/B 测试模式（可选）

如果用户输入 `~start --ab` 或在交互中回答 yes：

```
是否启用 A/B 测试模式？(yes/no，默认 no)
```

如果启用：
1. 扫描 `config/ab-testing/variants/` 目录，列出所有 `.yaml` 文件（读取每个文件的 `id` 和 `name` 字段）
2. 展示可用变体列表，让用户选择变体 A 和变体 B：
   ```
   可用变体：
   1. baseline — 基线（原始提示词）
   2. cinematic-v1 — 电影感增强 v1

   变体 A（默认 baseline）：
   变体 B：
   ```
3. 记录 `variant_a_id` 和 `variant_b_id`，后续 Phase 5 使用
4. 提示：A/B 模式将使 API 调用量翻倍（每镜次 2 个变体）

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
| reference_image_url | shots[].references[0].image_url | 参考图 URL（img2video 时必需；本地图片需先上传至 IMAGE_GEN_API 获取 URL） |
| dialogue | shots[].audio | 对白内容（唇形同步用） |
| voice_config_path | `assets/characters/voices/{角色名}/voice-config.yaml` | 音色配置路径（TTS 预留） |

3. 并行 spawn gen-workers：
```
spawn gen-worker (shot-1 params)
spawn gen-worker (shot-2 params)
...
spawn gen-worker (shot-N params)
等待所有 worker 完成
```

**Phase 5 — 视频生成（A/B 模式）**

如果 A/B 模式未启用，执行上述原有逻辑（不变）。

如果 A/B 模式启用：

1. 读取变体 A（`config/ab-testing/variants/{variant_a_id}.yaml`）和变体 B 的配置
2. 对每个镜次 shot：
   a. 获取原始 prompt = `shot.prompt`
   b. 生成 `variant_a_prompt`：
      - `transform_type: passthrough` → 直接使用原始 prompt
      - `transform_type: llm_rewrite` → 将 `rewrite_instruction`（替换 `{original_prompt}` 占位符）发给 LLM 改写
      - 验证 `len(prompt) <= 2000`，超长则截断至 2000 字符并输出警告
   c. 同理生成 `variant_b_prompt`
   d. spawn gen-worker（变体 A）：
      所有原始参数不变，额外传入：
      `prompt=variant_a_prompt`, `output_suffix="-a"`,
      `variant=variant_a_id`, `variant_prompt=variant_a_prompt`
   e. spawn gen-worker（变体 B）：
      同上，`prompt=variant_b_prompt`, `output_suffix="-b"`,
      `variant=variant_b_id`, `variant_prompt=variant_b_prompt`
3. 等待所有 2×N 个 gen-workers 完成
4. 对每个镜次，读取 `state/{ep}-shot-{N}-a.json` 和 `state/{ep}-shot-{N}-b.json`，
   创建 `state/{ep}-shot-{N}-ab-result.json`：
   ```json
   {
     "episode": "{ep}",
     "shot_id": "{shot_id}",
     "shot_index": {N},
     "variant_a": {
       "id": "{variant_a_id}",
       "video_path": "outputs/{ep}/videos/shot-{N}-a.mp4",
       "status": "{从 -a.json 读取}",
       "prompt_used": "{variant_a_prompt}"
     },
     "variant_b": {
       "id": "{variant_b_id}",
       "video_path": "outputs/{ep}/videos/shot-{N}-b.mp4",
       "status": "{从 -b.json 读取}",
       "prompt_used": "{variant_b_prompt}"
     },
     "scoring": { "scored": false }
   }
   ```
5. 输出提示：
   ```
   A/B 视频生成完成！
   共 {N} 个镜次 × 2 变体 = {2N} 个视频
   成功：{S}，失败：{F}

   运行 ~ab-review 进行人工评分
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