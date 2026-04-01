# AI 短剧镜头工厂 v0.1 技术设计

**日期**: 2026-04-01  
**版本**: v0.1  
**状态**: Draft

---

## 执行摘要

本文档定义了一个**状态驱动的镜头工厂**架构，而非传统的线性生成流水线。

### 核心理念

**从"prompt 工厂"到"镜头工厂"**：
- 旧模式：剧本 → prompt → 生成视频（不可控）
- 新模式：剧本 → 状态图 → 资产包 → shot packet → 视频（可控 + 可修复）

### 关键洞察

1. **Entity 是静态的，State 是时序的**
   - 不能只有 `Character(苏夜)`
   - 必须有 `CharacterState(苏夜 @ ep01_sc03_sh05)`

2. **跨模型漂移需要共享状态**
   - Nanobanana 和 Seedance 2.0 不能靠 prompt 临时记忆接力
   - 必须靠 Visual Memory 和 Shot Packet 对齐

3. **长叙事是闭环，不是流水线**
   - 规划 → 生成 → 审计 → 修复 → 再生成

---

## 系统架构

### 7 层架构

```
1. Intake 层          接收需求，决定生产模式
2. Planning 层        剧本与分镜规划（结构化数据优先）
3. State 层           可执行状态图（control plane）
4. Asset Factory 层   Nanobanana 资产工厂
5. Shot Compiler 层   编译 shot packet
6. Render 层          Seedance 2.0 镜头渲染
7. Audit/Repair 层    QA + 修复闭环
```

### 数据流

```
User Brief
  ↓
Director Agent → 题材定位 + 预算模式
  ↓
Story Architect Agent → World Bible + Character Bible + Scene Beats
  ↓
Continuity Agent → 状态冲突检查
  ↓
Asset Agent (Nanobanana) → 角色包 + 场景包 + 道具包
  ↓
Memory Agent → 检索最相关 references
  ↓
Shot Compiler Agent → 编译 shot packet
  ↓
Video Agent (Seedance 2.0) → 渲染视频
  ↓
QA Agent → 审计
  ↓
Repair Agent → 局部修复 / 重生
  ↓
Editor Agent → 最终拼接
```

---

## 数据库 Schema

### MVP 技术栈

```
- Postgres: 主状态库
- JSONB: 存 shot packet / state snapshots
- pgvector: 向量检索
- S3/MinIO: 图片、视频存储
- Redis: 任务队列 + cache
```

### 核心表结构

#### projects
```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    genre VARCHAR(100),
    target_episodes INT,
    budget_mode VARCHAR(50), -- fast / stable
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### episodes
```sql
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    episode_number INT NOT NULL,
    title VARCHAR(255),
    status VARCHAR(50), -- planning / asset_gen / rendering / qa / completed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, episode_number)
);
```

#### scenes
```sql
CREATE TABLE scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id UUID REFERENCES episodes(id),
    scene_number INT NOT NULL,
    scene_goal TEXT,
    location VARCHAR(255),
    time_of_day VARCHAR(50), -- day / night / dusk / dawn
    duration_estimate_sec INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(episode_id, scene_number)
);
```

#### shots
```sql
CREATE TABLE shots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scene_id UUID REFERENCES scenes(id),
    shot_number INT NOT NULL,
    shot_id VARCHAR(100) UNIQUE NOT NULL, -- ep01_sc03_sh05
    duration_sec INT NOT NULL,
    camera_type VARCHAR(100),
    camera_movement VARCHAR(100),
    status VARCHAR(50), -- pending / rendering / qa / completed / failed
    shot_packet JSONB, -- 完整的 shot packet
    render_result JSONB, -- 渲染结果
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(scene_id, shot_number)
);
```

#### characters
```sql
CREATE TABLE characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    name VARCHAR(255) NOT NULL,
    tier VARCHAR(50), -- protagonist / supporting / minor
    base_appearance TEXT,
    personality TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, name)
);
```

#### character_states
```sql
CREATE TABLE character_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID REFERENCES characters(id),
    shot_id UUID REFERENCES shots(id),
    variant VARCHAR(100), -- default / snake_green / python_black
    costume VARCHAR(100),
    emotion VARCHAR(100),
    injury VARCHAR(100),
    knowledge_state JSONB, -- ["knows_lie_about_phone"]
    location VARCHAR(255),
    state_snapshot JSONB, -- 完整状态快照
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(character_id, shot_id)
);
```

#### props
```sql
CREATE TABLE props (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, name)
);
```

#### prop_states
```sql
CREATE TABLE prop_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prop_id UUID REFERENCES props(id),
    shot_id UUID REFERENCES shots(id),
    condition VARCHAR(100), -- intact / damaged / destroyed
    location VARCHAR(255),
    in_possession_of UUID REFERENCES characters(id),
    state_snapshot JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(prop_id, shot_id)
);
```

#### assets
```sql
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type VARCHAR(50), -- character_pack / scene_pack / prop_pack / keyframe
    entity_id UUID, -- character_id / scene_id / prop_id
    variant VARCHAR(100),
    angle VARCHAR(50), -- front / side / back
    expression VARCHAR(50), -- neutral / happy / angry
    file_path TEXT NOT NULL,
    file_url TEXT,
    generation_model VARCHAR(100), -- nanobanana / seedance
    generation_params JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### memory_entries
```sql
CREATE TABLE memory_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_type VARCHAR(50), -- character / prop / background
    entity_id UUID,
    shot_id UUID REFERENCES shots(id),
    asset_ids UUID[], -- 关联的 asset IDs
    embedding VECTOR(1536), -- pgvector
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON memory_entries USING ivfflat (embedding vector_cosine_ops);
```

#### render_tasks
```sql
CREATE TABLE render_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID REFERENCES shots(id),
    task_type VARCHAR(50), -- t2v / i2v / edit / extend
    status VARCHAR(50), -- pending / running / completed / failed
    attempt_number INT DEFAULT 1,
    model VARCHAR(100), -- seedance-1.5-pro / seedance-2.0
    input_params JSONB,
    output_video_path TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
```

#### audit_results
```sql
CREATE TABLE audit_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shot_id UUID REFERENCES shots(id),
    audit_type VARCHAR(50), -- symbolic / visual / semantic
    passed BOOLEAN,
    issues JSONB, -- [{type, severity, description}]
    repair_action VARCHAR(50), -- pass / local_repair / regenerate
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Shot Packet 数据结构

### 完整 Shot Packet 示例

```json
{
  "shot_id": "ep01_sc03_sh05",
  "scene_goal": "女主确认男主在撒谎",
  "duration_sec": 5,
  "dialogue_mode": "external_dub",
  
  "characters": [
    {
      "id": "female_lead",
      "state_ref": "female_lead@ep01_sc03_sh05",
      "ref_assets": [
        "asset://female_face_v1",
        "asset://female_costume_office_v2"
      ],
      "must_preserve": ["face", "hair", "coat_color"]
    }
  ],
  
  "background": {
    "state_ref": "office_night@ep01_sc03_sh05",
    "ref_assets": ["asset://office_night_keyframe_02"]
  },
  
  "camera": {
    "shot_size": "medium_closeup",
    "movement": "slow_push_in",
    "lens_style": "cinematic_85mm",
    "lighting": "cold_blue"
  },
  
  "seedance_inputs": {
    "images": [
      "asset://female_face_v1",
      "asset://office_night_keyframe_02"
    ],
    "videos": [],
    "audios": []
  },
  
  "forbidden_changes": [
    "不要换装",
    "不要改变发型"
  ],
  
  "repair_policy": {
    "max_retries": 2,
    "prefer_local_edit": true
  }
}
```

---

## Agent 架构

### 10 个 Agents

1. **Director Agent** - 生产计划
2. **Story Architect Agent** - 剧本规划
3. **Continuity Agent** - 状态冲突检查
4. **Asset Agent** - Nanobanana 资产生成
5. **Memory Agent** - 检索相关 references
6. **Shot Compiler Agent** - 编译 shot packet
7. **Video Agent** - Seedance 渲染
8. **QA Agent** - 审计
9. **Repair Agent** - 修复决策
10. **Editor Agent** - 最终拼接

---

## 实施路线图

### Phase 1: 最小工厂（2 周）

**交付物**:
- [ ] Postgres schema 创建
- [ ] Nanobanana caller 脚本
- [ ] 为 1 个角色生成定妆包
- [ ] 手动编译 1 个 shot packet
- [ ] 渲染 1 个 shot

### Phase 2-5: 详见完整文档

---

**文档作者**: Claude Code  
**预计完成时间**: 10 周
