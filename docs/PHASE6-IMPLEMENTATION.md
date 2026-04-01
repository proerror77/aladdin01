# Phase 6: Audit & Repair 实现文档

## 概述

Phase 6 实现了视频质量审计和自动修复功能，包括 3 种 QA 检查和 3 种修复策略。

## 实现文件

### Agents

1. **`.claude/agents/qa-agent.md`** - 质量审计 Agent
   - 执行 3 种 QA：Symbolic（硬逻辑）、Visual（画面）、Semantic（戏剧）
   - 输出审计结果和修复策略建议

2. **`.claude/agents/repair-agent.md`** - 修复决策 Agent
   - 根据 QA 结果执行修复策略：pass / local_repair / regenerate
   - 支持最大重试次数配置（默认 3 次）

### 辅助脚本

1. **`scripts/compare_faces.py`** - 脸部相似度比较
   - 使用 face_recognition 库（可选）
   - 输出相似度分数（0-1）

2. **`scripts/compare_backgrounds.py`** - 背景相似度比较
   - 使用 OpenCV + SSIM 算法（可选）
   - 输出相似度分数（0-1）

3. **`scripts/test-phase6.sh`** - Phase 6 测试脚本
   - 验证文件结构和语法
   - 检查关键功能完整性

## QA 类型

### 1. Symbolic QA（硬逻辑检查）

检查项：
- 角色是否突然换装
- 伤势是否消失
- 道具是否凭空出现
- 知识状态是否合理

实现方式：使用 jq 比较前后镜次的状态文件。

### 2. Visual QA（画面检查）

检查项：
- 脸像不像（与 reference 对比）
- 衣服是否漂色
- 道具是否消失
- 背景是否跳变

实现方式：
- 提取关键帧（首帧、中间帧、尾帧）
- 使用图像相似度算法或 LLM 辅助判断

### 3. Semantic QA（戏剧检查）

检查项：
- 角色情绪是否跳太快
- 对白口吻是否崩
- 镜头语言是否符合戏剧目标

实现方式：使用 LLM 辅助判断。

## 修复策略

### 1. pass（直接通过）

条件：`high_severity_count == 0 && medium_severity_count == 0`

操作：无需修复，直接标记为完成。

### 2. local_repair（局部修复）

条件：`high_severity_count <= 1`

修复方法：
- `face_mismatch` → `repair_face_with_nanobanana`（用 Nanobanana 修复关键帧）
- `costume_change` → `adjust_prompt_and_regenerate`（调整 prompt 重新生成）
- `prop_disappeared` → `repair_prop_with_seedance`（Seedance 局部编辑）
- `background_jump` → `use_prev_frame_as_reference`（调整前一帧作为参考）

### 3. regenerate（重新生成）

条件：`high_severity_count > 1`

流程：
1. 分析失败原因
2. 调整策略：
   - `change_reference`（换一组参考图）
   - `adjust_prompt`（调整 prompt）
   - `change_model`（换模型）
3. 调用 gen-worker 重新生成
4. 重新审计
5. 最大重试 3 次

## 输出文件

### 审计结果

`state/audit/{ep}-shot-{N}-audit.json`：

```json
{
  "shot_id": "ep01-shot-05",
  "audit_timestamp": "2026-04-01T10:00:00Z",
  "passed": false,
  "issues": [
    {
      "type": "symbolic",
      "items": [
        {
          "type": "costume_change",
          "character": "苏夜",
          "severity": "high"
        }
      ]
    },
    {
      "type": "visual",
      "items": [
        {
          "type": "face_mismatch",
          "character": "苏夜",
          "similarity": 0.65,
          "severity": "high"
        }
      ]
    }
  ],
  "repair_action": "local_repair"
}
```

### 修复历史

`state/audit/{ep}-shot-{N}-repair-history.json`：

```json
[
  {
    "timestamp": "2026-04-01T10:05:00Z",
    "attempt": 1,
    "repair_action": "local_repair",
    "adjustment": "adjust_prompt",
    "result": "success"
  }
]
```

## 依赖库（可选）

### Python 库

```bash
# 脸部相似度比较
pip install face_recognition

# 背景相似度比较
pip install opencv-python scikit-image
```

注意：这些库是可选的。如果未安装，脚本会返回默认相似度值。

## 使用方式

### 单独调用

```bash
# QA 审计
qa-agent ep01 ep01-shot-05 session-id

# 修复
repair-agent ep01 ep01-shot-05 session-id 3
```

### 集成到 ~start / ~batch

在 Phase 5（视频生成）之后添加 Phase 6：

```bash
# Phase 6: Audit & Repair
for shot_id in $(yq eval '.shots[].shot_id' outputs/${ep}/visual-direction.yaml); do
    # 审计
    qa-agent "$ep" "$shot_id" "$session_id"
    
    # 修复
    repair-agent "$ep" "$shot_id" "$session_id" 3
done
```

## 测试

运行测试脚本：

```bash
./scripts/test-phase6.sh
```

测试内容：
- 文件结构完整性
- Python 脚本语法
- Agent 文档结构
- 关键功能验证

## 注意事项

### 简化实现

当前实现为简化版，以下功能需要在实际生产环境中完善：

1. **图像相似度算法**：当前使用简化实现，实际应集成完整的人脸识别和图像比较算法。

2. **LLM 辅助判断**：Semantic QA 需要调用 LLM API 进行对白口吻和戏剧合理性判断。

3. **修复方法实现**：部分修复方法（如 `repair_prop_with_seedance`）需要等待 Seedance 2.0 视频编辑 API 开放。

4. **Agent 间调用**：repair-agent 需要通过 team-lead 调用 gen-worker 和 qa-agent，当前实现中标注了调用点。

### 阈值调整

可根据实际效果调整以下阈值：

- 脸部相似度阈值：默认 0.7（`compare_faces.py`）
- 背景相似度阈值：默认 0.5（`qa-agent.md`）
- 修复策略决策阈值：
  - `high_severity_count <= 1` → local_repair
  - `high_severity_count > 1` → regenerate

### 性能优化

- Visual QA 可并行处理多个 shots
- 关键帧提取可缓存，避免重复提取
- 图像相似度计算可使用 GPU 加速

## 下一步

1. 在 `~start` 和 `~batch` skills 中集成 Phase 6
2. 测试完整的 E2E 流程
3. 根据实际效果调整阈值和策略
4. 完善修复方法的实现
5. 添加人工审核覆盖机制

## 相关文档

- 实现指南：`docs/V2-IMPLEMENTATION-GUIDE.md` 第 9-10 节
- E2E 流程：`docs/E2E-WORKFLOW-WITH-ONTOLOGY.md`
- 配置文件：`config/shot-packet-schema.yaml`
