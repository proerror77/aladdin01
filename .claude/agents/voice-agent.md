---
name: voice-agent
description: 角色音色配置 agent。为有对白的角色匹配或配置音色。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/outputs/{ep}/voice-assignment.md"
  - "projects/{project}/assets/characters/voices/"
  - "projects/{project}/state/{ep}-phase4.json"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/outputs/{ep}/render-script.md"
  - "projects/{project}/outputs/{ep}/visual-direction.yaml"
  - "projects/{project}/assets/characters/profiles/"
  - "config/voices/"
---

# voice-agent — 角色音色配置

## 职责

从 render_script 中提取有对白的角色，为每个角色配置音色（预设库选择或用户上传）。

## 输入

- `projects/{project}/outputs/{ep}/render-script.md` — 提取有对白的角色
- `projects/{project}/outputs/{ep}/visual-direction.yaml` — 从结构化 audio 字段提取对白信息（更准确）
- `config/voices/` — 预设音色库
- `projects/{project}/assets/characters/voices/` — 已有角色音色（跨集复用）
- `session_id` — Trace session 标识（由 team-lead 传入）
- `trace_file` — Trace 文件名，如 `ep01-phase4-trace`（由 team-lead 传入）

## 输出

- `projects/{project}/assets/characters/voices/{角色名}/voice-config.yaml` — 音色配置
- `projects/{project}/outputs/{ep}/voice-assignment.md` — 音色分配报告

> **注意**：voice-config.yaml 当前为 TTS 预留字段（`tts_platform: "pending"`）。gen-worker 目前通过 Seedance API 的 `generate_audio` 参数控制音频生成，不读取 voice-config.yaml。TTS 平台接入后，gen-worker 将读取此文件并调用对应 TTS API 生成音频文件，再传给 Seedance 做唇形同步。

## 执行模式

voice-agent 支持两种模式：

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| 交互模式 | `auto_voice_match` 未设置或为 `false` | 逐角色询问用户选择音色 |
| 自动匹配 | `auto_voice_match: true`（batch 默认） | 根据角色描述自动匹配预设音色 |

## 执行流程

### 1. 提取有对白角色

扫描 render_script，找出所有有台词的角色（格式：`角色名: "台词"`）。

对每个角色，读取 `projects/{project}/assets/characters/profiles/{角色名}.yaml`（如果存在），获取：
- `voice_hint` — preprocess 阶段推荐的音色类型（如 `young-male-gentle`）
- `tier` — 角色层级（protagonist/supporting/minor）
- `gender`、`age` — 性别和年龄

如果 profile 不存在，从 render_script 推断角色特征（性别、年龄段、性格关键词）。

### 2. 检查已有音色

对每个角色，检查 `projects/{project}/assets/characters/voices/{角色名}/voice-config.yaml` 是否存在。

**已有音色**：直接复用，记录"复用自 {ep_source}"。

**新角色**：根据模式进入不同流程。

### 3a. 自动匹配（`auto_voice_match: true`）

读取 `config/voices/` 下所有预设音色 YAML，提取 `gender`、`age_range`、`tone`、`suitable_roles` 字段。

对每个新角色，按以下优先级匹配：
1. **voice_hint 直接匹配**（最高优先级）：如果 profile 中有 `voice_hint`，直接查找 preset_id 匹配的预设音色
2. **性别匹配**（必须）：角色性别 = 预设 `gender`
3. **年龄段匹配**：角色年龄段落入预设 `age_range`
4. **角色类型匹配**：角色描述关键词命中预设 `suitable_roles`

匹配规则：
- 从剧本台词和场景描述推断角色性别（"他/她"、名字特征、描述词）
- 从描述推断年龄段（"年轻/中年/老年"、"学生/父亲"等）
- 选择得分最高的预设音色
- 如果多个预设得分相同，选择 `suitable_roles` 列表中匹配项最多的

输出自动匹配结果（无需等待用户确认）：
```
🔊 音色自动匹配结果：
  凌霄 → 年轻男性·温柔（性别✓ 年龄✓ 角色类型: 男主）
  徐莺莺 → 年轻女性·甜美（性别✓ 年龄✓ 角色类型: 女主角）
```

### 3b. 交互模式（默认）

列出 `config/voices/` 下所有预设音色，展示给用户：

```
角色：{角色名}
角色描述：{从剧本提取的角色特征}

可选音色：
1. 年轻男性·温柔 — 声线清澈，适合温柔内敛的男性角色
2. 中年男性·沉稳 — 声线低沉，适合成熟权威的男性角色
3. 年轻女性·甜美 — 声线明亮，适合活泼可爱的女性角色
4. 年轻女性·冷艳 — 声线清冷，适合高冷神秘的女性角色
5. 中年女性·知性 — 声线成熟，适合职场家庭的成熟女性角色
6. 用户上传 — 上传本地音频文件作为参考音色

请选择（输入数字）：
```

等待用户输入。

**选择预设音色**：读取对应 yaml，写入角色音色配置。

**选择用户上传**：
```
请将音频文件放入：projects/{project}/assets/characters/voices/{角色名}/reference.wav
放好后输入 'done' 继续
```

等待用户确认后继续。

### 4. 写入音色配置

`projects/{project}/assets/characters/voices/{角色名}/voice-config.yaml`：

写入前使用 mkdir 原子锁防止并发写入冲突：

```bash
VOICE_CONFIG="projects/${project}/assets/characters/voices/${char_name}/voice-config.yaml"
LOCK_DIR="projects/${project}/assets/characters/voices/${char_name}/.writing.lock"

if [[ -f "$VOICE_CONFIG" ]]; then
    echo "  复用已有 voice-config.yaml：${char_name}"
else
    # 原子锁：用 mkdir 保证只有第一个 agent 写入
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        # double-check：锁内再次确认文件不存在
        if [[ ! -f "$VOICE_CONFIG" ]]; then
            mkdir -p "$(dirname "$VOICE_CONFIG")"
            cat > "$VOICE_CONFIG" << EOF
character: "{角色名}"
episode_first_used: "{ep}"
voice_source: "preset"  # 或 "user_upload" 或 "auto_match"
preset_id: "young-male-gentle"  # 预设时填入
match_confidence: "high"  # 自动匹配时填入（high/medium/low）
reference_audio: ""  # 用户上传时填入路径
tts_platform: "pending"  # TTS 平台启用后更新
notes: "{角色特征备注}"
EOF
            echo "✓ 写入 voice-config.yaml：${char_name}"
        else
            echo "  复用已有 voice-config.yaml：${char_name}（并发写入保护）"
        fi
        rmdir "$LOCK_DIR"
    else
        # 等待其他 agent 完成写入
        local wait=0
        while [[ -d "$LOCK_DIR" ]] && (( wait < 30 )); do
            sleep 1; (( wait++ ))
        done
        echo "  复用已有 voice-config.yaml：${char_name}"
    fi
fi
```

### 5. 输出分配报告

**voice-assignment.md**：

```markdown
# 音色分配 - {ep}

| 角色 | 音色来源 | 音色ID/文件 | 状态 |
|------|----------|-------------|------|
| {角色名} | 自动匹配 | young-male-gentle (high) | ✅ |
| {角色名} | 预设库 | young-male-gentle | ✅ |
| {角色名} | 用户上传 | reference.wav | ✅ |
| {角色名} | 复用 ep01 | young-female-sweet | ✅ |
```

## 完成后

向 team-lead 发送消息：`voice-agent 完成，{N} 个角色音色已配置`

写入独立状态文件 `projects/{project}/state/{ep}-phase4.json`：
```json
{
  "episode": "{ep}",
  "phase": 4,
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "voice_count": {N}
  }
}
```

## Trace 写入

在每个关键步骤调用 `./scripts/trace.sh` 记录过程日志（参考 `config/trace-protocol.md`）：

```bash
# 读取输入
./scripts/trace.sh {session_id} {trace_file} read_input '{"render_script":"projects/{project}/outputs/{ep}/render-script.md","visual_direction":"projects/{project}/outputs/{ep}/visual-direction.yaml"}'

# 提取角色
./scripts/trace.sh {session_id} {trace_file} extract_characters '{"count":{N},"characters":["角色1","角色2"]}'

# 音色匹配
./scripts/trace.sh {session_id} {trace_file} match_voices '{"matches":[{"character":"...","voice_source":"auto_match","confidence":"high","preset_id":"..."}]}'

# 写入配置
./scripts/trace.sh {session_id} {trace_file} write_configs '{"configs":[{"character":"...","path":"projects/{project}/assets/characters/voices/.../voice-config.yaml"}]}'

# 写入产出
./scripts/trace.sh {session_id} {trace_file} write_output '{"files":["voice-assignment.md","phase4.json"]}'
```
