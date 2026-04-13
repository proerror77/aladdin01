# 职场MBTI 剧本生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为职场MBTI系列生成 16 集完整剧本（ep01–ep16），每集对应一种 MBTI 类型配角，格式与 ep00 一致。

**Architecture:** 先生成全部 16 集大纲（一次性，供用户确认），确认后逐集展开完整剧本。每集剧本存为 `projects/mbti/script/epXX.md`，格式严格沿用 ep00 模板（4场景 + 画面设计 + 主角独白 + 配角对白）。

**Tech Stack:** 纯文本创作，Markdown 格式，参考 `projects/mbti/state/ontology/world-model.yaml` 和各角色 YAML 档案。

---

## 文件结构

| 文件 | 用途 |
|------|------|
| `projects/mbti/script/ep00.md` | 已有，模板参考 |
| `projects/mbti/script/ep01.md` | ENFP 林曉彤 |
| `projects/mbti/script/ep02.md` | ESFP 陳大勇 |
| `projects/mbti/script/ep03.md` | ENTJ 王建國 |
| `projects/mbti/script/ep04.md` | ENTP 蘇哲明 |
| `projects/mbti/script/ep05.md` | INFP 葉雨晴 |
| `projects/mbti/script/ep06.md` | INFJ 莫靜言 |
| `projects/mbti/script/ep07.md` | ENFJ 張明輝 |
| `projects/mbti/script/ep08.md` | INTJ 謝冷川 |
| `projects/mbti/script/ep09.md` | INTP 周思遠 |
| `projects/mbti/script/ep10.md` | ISTJ 林德正 |
| `projects/mbti/script/ep11.md` | ISFJ 陳美玲 |
| `projects/mbti/script/ep12.md` | ESTJ 黃志強 |
| `projects/mbti/script/ep13.md` | ESFJ 劉曉華 |
| `projects/mbti/script/ep14.md` | ISTP 方銳 |
| `projects/mbti/script/ep15.md` | ISFP 吳小藍 |
| `projects/mbti/script/ep16.md` | ESTP 高飛 |
| `projects/mbti/docs/episode-outlines.md` | 16集大纲汇总（用户确认用） |
| `projects/mbti/docs/character-relationship-map.md` | 人物关系图（文字版） |

---

## 剧本格式规范（每集必须遵守）

```markdown
# 职场MBTI — epXX：[集名]

**主角**：INTJ 绿发女生
**配角**：[MBTI类型] [角色名] — [职位]
**集数**：epXX

---

## 【场景一：[场景名]】

**画面设计**：
[视觉描述，100字以内，包含环境、氛围、视觉特效]

**主角独白**（[情绪标注]）：
> [独白内容，带史诗感+自嘲，金句密度高]

---

## 【场景二：[场景名]】

**画面设计**：
[视觉描述]

**[配角名]**（[情绪标注]）：
> "[配角对白，完全符合该MBTI特征]"

**主角独白**（[情绪标注]）：
> [独白内容，包含内心OS，用*斜体*标注]

---

## 【场景三：[场景名]】
[同上格式]

---

## 【场景四：[场景名]】
[同上格式，结尾主角回归现实，继续扮演"优秀员工"]
```

---

## Task 1: 生成 16 集大纲汇总

**Files:**
- Create: `projects/mbti/docs/episode-outlines.md`

- [ ] **Step 1: 读取所有角色档案**

读取 `projects/mbti/state/ontology/world-model.yaml` 和 `projects/mbti/assets/characters/profiles/` 下所有 YAML 文件，确认每集配角的核心冲突点。

- [ ] **Step 2: 为每集写一段大纲（约150字）**

每集大纲包含：
- 集名（一句话点题）
- 本集核心冲突/互动
- 4个场景的标题和一句话描述
- 本集金句（主角独白的高光时刻）

格式示例：
```markdown
## ep01 — ENFP 林曉彤：《创意炸弹来袭》

**核心冲突**：林曉彤的天马行空创意让主角精心准备的三周计划瞬间作废，但偏偏老板觉得很有趣。

**场景一**：清晨，主角到公司，发现林曉彤已经把整个白板贴满了便利贴（主角独白：职场生存法则第一条）
**场景二**：会议室，林曉彤提出颠覆性提案，主角三周计划作废（核心冲突爆发）
**场景三**：茶水间，主角试图用逻辑说服林曉彤，林曉彤用直觉反将一军
**场景四**：下班，主角独自坐在工位，承认林曉彤的直觉有时比自己的逻辑更准

**本集金句**：「她的熱情是一種天然災害，我的計畫表在她面前的平均壽命是十七分鐘。」
```

- [ ] **Step 3: 写入文件**

将 16 集大纲全部写入 `projects/mbti/docs/episode-outlines.md`。

- [ ] **Step 4: 等待用户确认**

输出提示：「16集大纲已生成，请查看 `projects/mbti/docs/episode-outlines.md`，确认后继续展开完整剧本。」

---

## Task 2: 生成人物关系图

**Files:**
- Create: `projects/mbti/docs/character-relationship-map.md`

- [ ] **Step 1: 写人物关系图（文字版）**

格式：
```markdown
# 职场MBTI 人物关系图

## 主角（INTJ）的职场宇宙

### 高张力关系（主角内心消耗大）
- ENTJ 王建國：低温竞争，互为对手，暗自尊重
- ENTP 蘇哲明：智识享受+时间谋杀，恨他但承认他是对的
- ESTP 高飛：极度消耗，他欠主角的已多到无法计算
- INTP 周思遠：deadline崩溃，标准比主角还高

### 中张力关系（主角需要但有摩擦）
- ENFP 林曉彤：天然灾害，暗自佩服其直觉
- ISTJ 林德正：功能性依赖，创新受历史审判
- ESTJ 黃志強：需要其执行力但不要其框架
- INFP 葉雨晴：道德困境，保护欲

### 低张力关系（主角防御漏洞）
- INFJ 莫靜言：被看穿的不适，深层信任，唯一看穿主角的人
- ENFJ 張明輝：温暖攻势，防御漏洞，无法逻辑抵抗
- ISFJ 陳美玲：情绪系统报错，功能性感激
- ESFJ 劉曉華：纯粹功能性感激，欠人情

### 同类认可关系（主角最舒适）
- ISTP 方銳：最接近灵魂伴侣，互不打扰的最高尊重
- INTJ 謝冷川：错误镜像，低温战争但最接近友谊
- ISFP 吳小藍：认识论危机，无法解释的佩服
- ESFP 陳大勇：困惑+无奈，承认其魅力
```

- [ ] **Step 2: 写入文件**

---

## Task 3: 展开 ep01–ep04 完整剧本

**Files:**
- Create: `projects/mbti/script/ep01.md` — ENFP 林曉彤
- Create: `projects/mbti/script/ep02.md` — ESFP 陳大勇
- Create: `projects/mbti/script/ep03.md` — ENTJ 王建國
- Create: `projects/mbti/script/ep04.md` — ENTP 蘇哲明

每集要求：
- 严格遵守格式规范
- 4个场景，每场有画面设计+主角独白+配角对白
- 配角行为完全符合该MBTI特征
- 主角内心OS用*斜体*标注
- 结尾主角回归现实

- [ ] **Step 1: 写 ep01（ENFP 林曉彤）**

参考档案：`projects/mbti/assets/characters/profiles/ep01-enfp-林曉彤.yaml`

核心：林曉彤的创意炸弹 vs 主角的精密计划，主角最终暗自承认她的直觉有时比逻辑更准。

- [ ] **Step 2: 写 ep02（ESFP 陳大勇）**

参考档案：`projects/mbti/assets/characters/profiles/ep02-esfp-陳大勇.yaml`

核心：陳大勇用即兴简报拿下主角准备两周的大客户，主角的"他看了三页，第一页是封面"。

- [ ] **Step 3: 写 ep03（ENTJ 王建國）**

参考档案：`projects/mbti/assets/characters/profiles/ep03-entj-王建國.yaml`

核心：两个强者的高压对决，主角发现他说的是对的，这让主角更生气。

- [ ] **Step 4: 写 ep04（ENTP 蘇哲明）**

参考档案：`projects/mbti/assets/characters/profiles/ep04-entp-蘇哲明.yaml`

核心：30分钟会议变2小时哲学辩论，什么决定都没做，主角：「他是對的。我恨他。」

- [ ] **Step 5: Commit**

```bash
git add projects/mbti/script/ep01.md projects/mbti/script/ep02.md projects/mbti/script/ep03.md projects/mbti/script/ep04.md
git commit -m "feat(mbti): add ep01-ep04 scripts (ENFP/ESFP/ENTJ/ENTP)"
```

---

## Task 4: 展开 ep05–ep08 完整剧本

**Files:**
- Create: `projects/mbti/script/ep05.md` — INFP 葉雨晴
- Create: `projects/mbti/script/ep06.md` — INFJ 莫靜言
- Create: `projects/mbti/script/ep07.md` — ENFJ 張明輝
- Create: `projects/mbti/script/ep08.md` — INTJ 謝冷川

- [ ] **Step 1: 写 ep05（INFP 葉雨晴）**

参考档案：`projects/mbti/assets/characters/profiles/ep05-infp-葉雨晴.yaml`

核心：deadline前两小时葉雨晴还在"醞釀"，主角说"你有一百二十分鐘"，她写出本季最好文案然后哭了。主角：「我不知道該道歉還是該說謝謝。」

- [ ] **Step 2: 写 ep06（INFJ 莫靜言）**

参考档案：`projects/mbti/assets/characters/profiles/ep06-infj-莫靜言.yaml`

核心：莫靜言看穿主角所有伪装，说"你今天很辛苦"，主角差点崩溃，用三秒重新组装自己说"我沒事"。莫靜言："我知道。"然后走了。

- [ ] **Step 3: 写 ep07（ENFJ 張明輝）**

参考档案：`projects/mbti/assets/characters/profiles/ep07-enfj-張明輝.yaml`

核心：张明辉的温暖攻势让主角的防御机制出现漏洞，主角想说"我喜歡一個人扛"，但只说了"謝謝"。

- [ ] **Step 4: 写 ep08（INTJ 謝冷川）**

参考档案：`projects/mbti/assets/characters/profiles/ep08-intj-謝冷川.yaml`

核心：两个INTJ的低温战争，白板前框架相同结论相反，对视三秒后各自继续写。「他是我，但他是錯的那個我。」

- [ ] **Step 5: Commit**

```bash
git add projects/mbti/script/ep05.md projects/mbti/script/ep06.md projects/mbti/script/ep07.md projects/mbti/script/ep08.md
git commit -m "feat(mbti): add ep05-ep08 scripts (INFP/INFJ/ENFJ/INTJ)"
```

---

## Task 5: 展开 ep09–ep12 完整剧本

**Files:**
- Create: `projects/mbti/script/ep09.md` — INTP 周思遠
- Create: `projects/mbti/script/ep10.md` — ISTJ 林德正
- Create: `projects/mbti/script/ep11.md` — ISFJ 陳美玲
- Create: `projects/mbti/script/ep12.md` — ESTJ 黃志強

- [ ] **Step 1: 写 ep09（INTP 周思遠）**

参考档案：`projects/mbti/assets/characters/profiles/ep09-intp-周思遠.yaml`

核心：上线前一小时周思遠说"我發現了一個更好的架構"，主角："不是。時候。"他的时间感知停留在非线性维度。

- [ ] **Step 2: 写 ep10（ISTJ 林德正）**

参考档案：`projects/mbti/assets/characters/profiles/ep10-istj-林德正.yaml`

核心：主角提出新流程，林德正翻出2019年会议记录列出三个问题，主角说"那我們解決這三個問題"，林德正第一次露出不确定算不算微笑的表情。

- [ ] **Step 3: 写 ep11（ISFJ 陳美玲）**

参考档案：`projects/mbti/assets/characters/profiles/ep11-isfj-陳美玲.yaml`

核心：主角连续加班三天，陳美玲放便当在桌上，主角把她的优先级从"背景人物"升级为"关键基础设施"。

- [ ] **Step 4: 写 ep12（ESTJ 黃志強）**

参考档案：`projects/mbti/assets/characters/profiles/ep12-estj-黃志強.yaml`

核心：主角提出非常规方案，黃志強说"這不在SOP裡"，主角说"所以我們更新SOP"，黃志強说"給我看你的數據"。

- [ ] **Step 5: Commit**

```bash
git add projects/mbti/script/ep09.md projects/mbti/script/ep10.md projects/mbti/script/ep11.md projects/mbti/script/ep12.md
git commit -m "feat(mbti): add ep09-ep12 scripts (INTP/ISTJ/ISFJ/ESTJ)"
```

---

## Task 6: 展开 ep13–ep16 完整剧本

**Files:**
- Create: `projects/mbti/script/ep13.md` — ESFJ 劉曉華
- Create: `projects/mbti/script/ep14.md` — ISTP 方銳
- Create: `projects/mbti/script/ep15.md` — ISFP 吳小藍
- Create: `projects/mbti/script/ep16.md` — ESTP 高飛

- [ ] **Step 1: 写 ep13（ESFJ 劉曉華）**

参考档案：`projects/mbti/assets/characters/profiles/ep13-esfj-劉曉華.yaml`

核心：主角在会议上说了让人尴尬的话，劉曉華立刻救场，然后用眼神告诉主角"你欠我一個"。主角：「她維持著這個辦公室的社會秩序，如果她消失，這裡會在七十二小時內陷入霍布斯式的自然狀態。」

- [ ] **Step 2: 写 ep14（ISTP 方銳）**

参考档案：`projects/mbti/assets/characters/profiles/ep14-istp-方銳.yaml`

核心：全公司系统当机，方銳一个字都没说，40分钟后发"好了。"主角：「我們的友誼建立在互相不打擾的基礎上，這是最高形式的尊重。」

- [ ] **Step 3: 写 ep15（ISFP 吳小藍）**

参考档案：`projects/mbti/assets/characters/profiles/ep15-isfp-吳小藍.yaml`

核心：主角给了详细需求文件，吳小藍做出来的东西完全不按文件走但好一百倍。主角："你怎麼知道要這樣做？"她说"感覺。"主角：*……*

- [ ] **Step 4: 写 ep16（ESTP 高飛）**

参考档案：`projects/mbti/assets/characters/profiles/ep16-estp-高飛.yaml`

核心：高飛在没告知任何人的情况下答应客户下周交付三个月的工作量，然后对主角说"你肯定有辦法的！"主角深呼吸，打开笔记本。「他欠我的，已經多到無法計算了。」

- [ ] **Step 5: Commit**

```bash
git add projects/mbti/script/ep13.md projects/mbti/script/ep14.md projects/mbti/script/ep15.md projects/mbti/script/ep16.md
git commit -m "feat(mbti): add ep13-ep16 scripts (ESFJ/ISTP/ISFP/ESTP)"
```

---

## Task 7: 最终整合与验收

**Files:**
- Verify: `projects/mbti/script/` — 确认 ep00–ep16 共 17 个文件
- Verify: `projects/mbti/docs/` — 确认大纲、关系图文件存在

- [ ] **Step 1: 验证文件完整性**

```bash
ls projects/mbti/script/
# 预期：ep00.md ep01.md ep02.md ... ep16.md（共17个）

ls projects/mbti/docs/
# 预期：episode-outlines.md character-relationship-map.md
```

- [ ] **Step 2: 格式一致性检查**

确认每集剧本：
- 有4个场景标题
- 有画面设计描述
- 有主角独白（含内心OS斜体）
- 有配角对白
- 结尾回归现实

- [ ] **Step 3: Final commit**

```bash
git add projects/mbti/
git commit -m "feat(mbti): complete 职场MBTI project — 17 episodes + character profiles + world model"
```

---

## 质量标准

每集剧本必须满足：
1. **金句密度**：每集至少 3 句可独立传播的金句
2. **MBTI 准确性**：配角行为让观众一眼认出"我认识这种人"
3. **INTJ 视角一致**：主角永远冷静、策略性、内心戏丰富
4. **史诗感**：画面设计有视觉冲击力，不只是普通办公室描写
5. **自嘲平衡**：讽刺但不刻薄，让各MBTI类型的观众都能笑着认同
