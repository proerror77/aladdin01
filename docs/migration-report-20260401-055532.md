# 架构迁移报告

**日期**: 2026-04-01 05:55:32
**版本**: v1.0 → v2.0

## 迁移状态

### 目录结构
- [x] state/ontology/
- [x] state/character-states/
- [x] state/shot-packets/
- [x] state/audit/
- [x] assets/packs/

### Agents
- [x] ontology-builder-agent
- [ ] asset-factory-agent
- [ ] memory-agent
- [ ] shot-compiler-agent
- [ ] qa-agent
- [ ] repair-agent

### Skills
- [x] build-ontology
- [ ] asset-factory
- [ ] compile-shots
- [ ] qa
- [ ] repair

### 配置文件
- [x] config/ontology/world-model-schema.yaml
- [x] config/shot-packet-schema.yaml
- [x] config/nanobanana/nanobanana-config.yaml

### 环境变量
- [x] TUZI_API_KEY
- [x] ARK_API_KEY

### 数据迁移
- [x] 现有角色参考图已保留
- [x] 现有场景参考图已保留
- [x] progress.json 已保留

## 下一步

1. 设置环境变量（如未设置）:
   ```bash
   export TUZI_API_KEY="..."
   export ARK_API_KEY="..."
   ```

2. 为现有剧本构建本体:
   ```bash
   ~build-ontology --all
   ```

3. 生成资产包:
   ```bash
   ~asset-factory
   ```

4. 测试新流程:
   ```bash
   ~start ep01
   ```

## 回滚方案

如需回滚到 v1.0:
```bash
# 恢复 Seedance 配置
cp config/platforms/seedance-v2.yaml.backup config/platforms/seedance-v2.yaml

# 删除新增目录（可选）
rm -rf state/ontology state/character-states state/shot-packets state/audit
rm -rf assets/packs
```
