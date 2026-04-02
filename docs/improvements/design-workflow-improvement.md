# 参考图生成流程改进方案

## 问题诊断

### 当前流程的缺陷

```
preprocess-agent → 生成角色档案（只有外貌描述）
                ↓
         design skill → 直接生成参考图（各自为政，风格不统一）
```

**问题**：
1. 缺少全局风格定义
2. 角色档案没有风格标签
3. 没有剧本类型识别
4. 没有风格一致性检查

### 实际案例

**剧本**：《开局青玉蚕》— 玄幻爽剧、反派主角、打脸装逼
**错误生成**：
- 苏夜青玉蚕 → Q版可爱风格（❌ 应该是痞气、腹黑）
- 叶红衣 → 古装写实风格（✅ 正确）
- **风格不统一** → 一个卡通，一个写实

## 改进方案

### 方案 1：增加 Style Analysis Agent（推荐）

```
preprocess-agent → 生成角色档案
                ↓
         style-agent → 分析剧本类型，定义全局风格
                ↓
         design skill → 按统一风格生成参考图
```

#### style-agent 职责

1. **剧本类型识别**
   - 读取剧本内容、角色设定、情节摘要
   - 识别类型：玄幻/现代/古装/科幻/校园/悬疑
   - 识别风格：爽剧/虐剧/沙雕/治愈/热血

2. **视觉风格定义**
   - 画风：写实/半写实/动漫/Q版/水墨
   - 质感：电影感/网剧感/动画感
   - 色调：冷色/暖色/高饱和/低饱和
   - 参考作品：类似的成功案例

3. **输出 style-guide.yaml**
   ```yaml
   project: qyccan
   genre: 玄幻爽剧
   tone: 反派主角、打脸装逼、系统进化

   visual_style:
     art_style: 半写实
     quality: 电影级短剧质感
     color_tone: 高饱和、冷暖对比
     reference: "《赘婿》《庆余年》短剧风格"

   character_style:
     protagonist: 霸气、痞气、反派气质（即使是动物形态）
     female_lead: 高冷御姐、古装武侠
     supporting: 写实人物比例

   prompt_template: |
     {角色描述}，{动作/表情}，
     玄幻短剧风格，半写实画风，电影级质感，
     高饱和度色彩，冷暖对比光影，
     专业角色概念设计，三视图保持一致
   ```

4. **风格一致性规则**
   - 所有角色使用相同的画风标签
   - 所有角色使用相同的质感要求
   - 动物角色也要符合剧本气质（不能可爱化）

#### 集成到流程

```bash
# preprocess 完成后，自动调用 style-agent
~preprocess → outputs/preprocess/{project}-report.md
           ↓
    style-agent → state/style-guide.yaml
           ↓
    ~design → 读取 style-guide.yaml，按统一风格生成
```

### 方案 2：增强 preprocess-agent（轻量级）

在 preprocess-agent 中增加风格分析步骤：

```python
# preprocess-agent 新增步骤
Step 4: 剧本风格分析
- 识别剧本类型（玄幻/现代/古装等）
- 识别剧本基调（爽剧/虐剧/沙雕等）
- 定义视觉风格标签
- 写入 outputs/preprocess/{project}-style.yaml
```

**优点**：不增加新 agent，流程简单
**缺点**：preprocess-agent 职责过重

### 方案 3：~design 前置交互（最简单）

在 ~design 开始前，询问用户：

```
━━━ 视觉风格定义 ━━━

剧本：《开局青玉蚕》
类型：玄幻 - 系统进化 - 沙雕 - 异兽流
主角：腹黑反派、嘴炮王者

请选择视觉风格：
1. 写实电影感（真人短剧，高质感）
2. 半写实风格（玄幻短剧，爽剧质感）
3. 动漫风格（日漫/国漫）
4. 水墨国风（古风意境）

请选择角色气质：
1. 霸气反派风（即使是动物也要有气场）
2. 可爱萌系风（Q版、治愈）
3. 冷峻严肃风（写实、压抑）
```

**优点**：简单直接，用户可控
**缺点**：需要人工介入，不够自动化

## 推荐实施方案

### 阶段 1：立即修复（本次）

1. **手动定义风格**
   ```bash
   # 创建 state/qyccan-style-guide.yaml
   project: qyccan
   visual_style: 玄幻短剧、半写实、电影级质感、反派气质
   ```

2. **重新生成参考图**
   - 使用统一的风格标签
   - 所有角色都加上"玄幻短剧风格、半写实画风、电影级质感"
   - 苏夜的三个形态都要有"霸气、痞气、反派气质"

### 阶段 2：流程改进（下次迭代）

1. **创建 style-agent**
   ```
   .claude/agents/style-agent.md
   ```

2. **修改 preprocess skill**
   ```bash
   ~preprocess → preprocess-agent → style-agent → 输出 style-guide.yaml
   ```

3. **修改 design skill**
   ```bash
   ~design → 读取 style-guide.yaml → 按统一风格生成
   ```

### 阶段 3：质量保证（长期）

1. **增加风格一致性检查**
   - gate-agent 在审核参考图时检查风格一致性
   - 对比所有角色的画风、质感、色调

2. **增加风格模板库**
   ```
   config/visual-styles/
   ├── xuanhuan-shuangju.yaml    # 玄幻爽剧
   ├── xiandai-dushi.yaml        # 现代都市
   ├── gufeng-wuxia.yaml         # 古风武侠
   └── keai-zhiyu.yaml           # 可爱治愈
   ```

## 关键改进点

### 1. 角色档案增加风格字段

```yaml
# assets/characters/profiles/suye.yaml
name: 苏夜
tier: protagonist
visual_style:
  art_style: 半写实
  quality: 电影级短剧质感
  character_vibe: 霸气、痞气、反派气质、腹黑
  color_palette: 碧绿（青玉蚕）→ 碧绿金瞳（碧鳞蛇）→ 漆黑金鳞（玄冥蟒）
variants:
  - variant_id: qingyucan
    appearance: 通体碧绿的蚕，肥嘟嘟但眼神欠揍
    vibe: 痞气、腹黑、嘴炮（不是可爱！）
```

### 2. 提示词模板统一

```python
# 所有角色使用相同的风格后缀
STYLE_SUFFIX = """
玄幻短剧风格，半写实画风，电影级质感，
高饱和度色彩，冷暖对比光影，
专业角色概念设计，三视图保持一致
"""

prompt = f"{角色描述}，{气质特征}，{STYLE_SUFFIX}"
```

### 3. 生成前风格检查

```python
# design skill 开始前
def validate_style_consistency():
    style_guide = read_yaml("state/style-guide.yaml")

    # 检查所有角色档案是否有 visual_style 字段
    for profile in glob("assets/characters/profiles/*.yaml"):
        if "visual_style" not in profile:
            raise Error("角色档案缺少 visual_style 字段")

    # 检查风格是否一致
    styles = [p.visual_style.art_style for p in profiles]
    if len(set(styles)) > 1:
        raise Error("角色风格不一致")
```

## 实施优先级

| 优先级 | 改进项 | 工作量 | 影响 |
|--------|--------|--------|------|
| 🔥 P0 | 手动创建 style-guide.yaml | 10 分钟 | 立即修复本次问题 |
| 🔥 P0 | 重新生成参考图（统一风格） | 30 分钟 | 立即修复本次问题 |
| 🟡 P1 | 创建 style-agent | 2 小时 | 自动化风格定义 |
| 🟡 P1 | 角色档案增加 visual_style 字段 | 1 小时 | 结构化风格信息 |
| 🟢 P2 | 风格一致性检查 | 1 小时 | 质量保证 |
| 🟢 P2 | 风格模板库 | 2 小时 | 可复用性 |

## 总结

**核心问题**：缺少全局风格定义和一致性保证

**解决方案**：
1. 立即：手动定义风格 + 重新生成
2. 短期：增加 style-agent 自动分析
3. 长期：风格模板库 + 一致性检查

**关键原则**：
- 先定义风格，再生成图片
- 所有角色使用统一的风格标签
- 风格要符合剧本类型和基调
- 动物角色也要符合剧本气质
