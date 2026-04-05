# ~design Workflow Status Report

## 执行时间
2026-03-31

## 项目
qyccan

## 当前状态
⚠️ **BLOCKED** - Image generation API 超时

## 问题诊断

### API 调用失败
所有图像生成 API 调用均超时或失败：
- `curl: (28) Operation timed out after 60002 milliseconds`
- `curl: (16) Error in the HTTP2 framing layer`

### 可能原因
1. TUZI_API_KEY 配置问题（虽然 env-check 通过）
2. 兔子 API 端点不可达或响应慢
3. 模型名称 `nano-banana-vip` 不正确
4. API 配额或限流

## 已扫描资源

### 角色档案（按 tier 分组）

**PROTAGONIST (8 个)**
- suye (苏夜) - 3 variants: qingyucan, bilinse, xuanmingmang
- yehongyi (叶红衣) - 1 variant: default
- 凌霄, 叶红衣, 张烈, 徐莺莺, 林昂, 苏夜 (重复/中文文件名，需清理)

**SUPPORTING (39 个)**
- wangpangzi, xiaofan, yeruyan, zhaowuji, 等

**MINOR (34 个)**
- qinger, 丧尸, 人偶邪灵, 保安/林暮, 等

### 场景档案
25 个场景：
- 479特异对策局, academy-dorm, arena, heiwu-forest, tianfeng-plaza, training-ground, ye-family-gate, ye-family-hall, yehongyi-room, 五星酒店, 冰灯景区, 叶家大厅, 叶家大门, 叶家府邸, 叶红衣闺房, 天风学院广场, 废弃仓库, 擂台, 清风酒吧, 画廊展厅, 练武场, 聚灵阁, 血液储存站, 锦华公寓, 黑雾森林

## 待生成参考图清单

### Stage A: 主角（迭代审核，无次数限制）

#### 苏夜 (suye) - 3 个变体
1. **青玉蚕形态** (qingyucan)
   - 外貌：通体碧绿、肥嘟嘟的蚕宝宝，眼神欠揍，拇指大小
   - 输出：`assets/characters/images/suye_qingyucan_three_view.png`
   - 状态：❌ 待生成

2. **碧鳞蛇形态** (bilinse)
   - 外貌：筷子长，通体覆盖精致碧绿色鳞片的小蛇，金色瞳孔，吐信子
   - 输出：`assets/characters/images/suye_bilinse_three_view.png`
   - 状态：❌ 待生成

3. **玄冥蟒形态** (xuanmingmang)
   - 外貌：长达三米，通体漆黑，头顶有两个小鼓包，黑金鳞片，金色瞳孔
   - 输出：`assets/characters/images/suye_xuanmingmang_three_view.png`
   - 状态：❌ 待生成

#### 叶红衣 (yehongyi) - 1 个变体
1. **常态** (default)
   - 外貌：18岁，红衣似火，高冷御姐脸，眼神透着倔强和落寞，长发，精致锁骨
   - 输出：`assets/characters/images/yehongyi_default_three_view.png`
   - 状态：❌ 待生成

### Stage B: 配角（标准审核，一轮修改机会）
39 个配角，每个生成三视图

### Stage C: 路人（自动通过，只生成正面图）
34 个路人，每个生成正面图

### Stage D: 场景参考图（标准审核）
25 个场景，部分场景需要时间变体（白天/晚上）

## 下一步行动

### 立即行动
1. **排查 API 问题**
   - 验证 TUZI_API_KEY 是否有效
   - 测试 API 端点连通性：`curl -I https://api.tu-zi.com`
   - 确认正确的模型名称（查阅兔子 API 文档）
   - 检查 API 配额和限流设置

2. **备选方案**
   - 配置 IMAGE_GEN_API_URL 和 IMAGE_GEN_API_KEY 使用其他图像生成服务
   - 手动生成参考图并放入 `assets/characters/images/` 和 `assets/scenes/images/`
   - 使用本地 Stable Diffusion 或其他工具生成

### API 修复后
1. 重新运行 `~design` workflow
2. 按 tier 优先级生成：Protagonist → Supporting → Minor → Scenes
3. 每个阶段完成后保存 `state/design-lock.json`
4. 主角形象需要人工审核确认后才锁定

## 幂等性保证
- 生成前检查目标图片文件是否已存在
- 已存在的图片跳过生成，直接进入审核步骤
- `design-lock.json` 记录已审核通过的参考图

## 文件结构
```
assets/
├── characters/
│   ├── profiles/*.yaml      # 角色档案（已存在）
│   └── images/              # 参考图（待生成）
│       ├── suye_qingyucan_three_view.png
│       ├── suye_bilinse_three_view.png
│       ├── suye_xuanmingmang_three_view.png
│       ├── yehongyi_default_three_view.png
│       └── ...
└── scenes/
    ├── profiles/*.yaml      # 场景档案（已存在）
    └── images/              # 场景图（待生成）
        ├── heiwu-forest_default.png
        ├── ye-family-hall_day.png
        ├── ye-family-hall_night.png
        └── ...

state/
├── design-lock.json         # 参考图锁定记录（待创建）
└── design-workflow-status.md # 本报告
```

## 预估工作量
- 主角变体：4 个三视图 = 4 次 API 调用
- 配角：39 个三视图 = 39 次 API 调用
- 路人：34 个正面图 = 34 次 API 调用
- 场景：约 30-40 个场景图（含时间变体）= 30-40 次 API 调用

**总计：约 107-117 次 API 调用**

## 备注
- 部分角色档案存在重复（英文文件名 vs 中文文件名），需要清理
- 主角 `苏夜` 有两个文件：`suye.yaml` 和 `苏夜.yaml`，variants 定义不同
- 建议统一使用英文文件名，中文文件名作为 `name` 字段
