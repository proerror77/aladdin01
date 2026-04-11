#!/usr/bin/env -S /Users/proerror/Documents/aladdin01/.venv/bin/python
"""
vectordb-manager.py — LanceDB 向量库管理

用法:
  python3 scripts/vectordb-manager.py init
  python3 scripts/vectordb-manager.py upsert-world-model state/ontology/ep01-world-model.json
  python3 scripts/vectordb-manager.py upsert-asset assets/packs/characters/苏夜-default-front.png
  python3 scripts/vectordb-manager.py search-assets "苏夜 青玉蚕 正面" --type character --n 3
  python3 scripts/vectordb-manager.py search-entities "黑雾森林 夜晚" --type scene --n 3
  python3 scripts/vectordb-manager.py search-relations "苏夜 叶红衣 契约" --episode ep01 --n 3
  python3 scripts/vectordb-manager.py get-state suye ep01 shot-05
  python3 scripts/vectordb-manager.py index-assets assets/packs/
  python3 scripts/vectordb-manager.py stats
"""

import sys
import os
import json
import argparse
import re
from pathlib import Path

# 依赖检查
try:
    import lancedb
except ImportError:
    print("ERROR: lancedb 未安装，请运行: pip3 install lancedb", file=sys.stderr)
    sys.exit(1)

try:
    import pyarrow as pa
except ImportError:
    print("ERROR: pyarrow 未安装，请运行: pip3 install pyarrow", file=sys.stderr)
    sys.exit(1)

# 可选：本地 embedding（优先）
try:
    from sentence_transformers import SentenceTransformer
    _EMBEDDING_MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    _USE_LOCAL_EMBED = True
except ImportError:
    _USE_LOCAL_EMBED = False

# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("VECTORDB_PATH", "state/vectordb/lancedb")
EMBED_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2 维度

TABLE_ENTITIES  = "entities"   # 角色 / 场景 / 道具 实体
TABLE_ASSETS    = "assets"     # 资产文件索引（图片路径）
TABLE_STATES    = "states"     # 每个 shot 的角色/场景状态快照
TABLE_RELATIONS = "relations"  # 实体关系


def _table_names(db) -> set[str]:
    """兼容 LanceDB 新旧接口，返回当前所有表名。"""
    if hasattr(db, "list_tables"):
        raw_names = db.list_tables()
    else:
        raw_names = db.table_names()

    if hasattr(raw_names, "tables"):
        raw_names = raw_names.tables

    names: set[str] = set()
    for item in raw_names:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, (tuple, list)) and item:
            names.add(str(item[0]))
        else:
            names.add(str(item))
    return names

# ──────────────────────────────────────────────────────────────────────────────
# Embedding
# ──────────────────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """将文本转换为向量。优先用本地模型，否则用简单哈希降级。"""
    if _USE_LOCAL_EMBED:
        return _EMBEDDING_MODEL.encode(text, normalize_embeddings=True).tolist()
    else:
        # 降级：基于字符哈希的确定性伪向量（可用，但语义质量低）
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vec = [(b / 255.0 - 0.5) * 2 for b in h]  # 32 维
        # 填充到 EMBED_DIM
        while len(vec) < EMBED_DIM:
            vec.extend(vec)
        return vec[:EMBED_DIM]

# ──────────────────────────────────────────────────────────────────────────────
# Schema 定义
# ──────────────────────────────────────────────────────────────────────────────

def _entity_schema():
    return pa.schema([
        pa.field("id",          pa.utf8()),          # "suye_ep01"
        pa.field("name",        pa.utf8()),           # "苏夜"
        pa.field("entity_type", pa.utf8()),           # character / scene / prop / creature / vfx / skill
        pa.field("episode",     pa.utf8()),           # "ep01"
        pa.field("tier",        pa.utf8()),           # protagonist / supporting / minor
        pa.field("variant",     pa.utf8()),           # "default" / "snake_green"
        pa.field("description", pa.utf8()),           # 合并的文本描述
        pa.field("metadata",    pa.utf8()),           # JSON 字符串（原始字段）
        pa.field("project",     pa.string()),          # 项目隔离
        pa.field("vector",      pa.list_(pa.float32(), EMBED_DIM)),
    ])

def _asset_schema():
    return pa.schema([
        pa.field("id",          pa.utf8()),           # 文件路径（唯一键）
        pa.field("path",        pa.utf8()),           # "assets/packs/characters/苏夜-default-front.png"
        pa.field("asset_type",  pa.utf8()),           # character / scene / prop
        pa.field("entity_name", pa.utf8()),           # "苏夜"
        pa.field("variant",     pa.utf8()),           # "default"
        pa.field("angle",       pa.utf8()),           # "front" / "side" / "back" / "styleframe"
        pa.field("time_of_day", pa.utf8()),           # "day" / "night" / "dusk" / "dawn"
        pa.field("pack_tier",   pa.int32()),          # 1=packs 2=images 3=降级
        pa.field("description", pa.utf8()),           # 用于 embed 的文本
        pa.field("project",     pa.string()),          # 项目隔离
        pa.field("vector",      pa.list_(pa.float32(), EMBED_DIM)),
    ])

def _state_schema():
    return pa.schema([
        pa.field("id",           pa.utf8()),          # "suye_ep01_shot05"
        pa.field("character_id", pa.utf8()),          # "suye"
        pa.field("episode",      pa.utf8()),          # "ep01"
        pa.field("shot_id",      pa.utf8()),          # "ep01-shot-05"
        pa.field("variant",      pa.utf8()),          # 当前形态
        pa.field("emotion",      pa.utf8()),          # 当前情绪
        pa.field("injury",       pa.utf8()),          # 伤势
        pa.field("props",        pa.utf8()),          # 持有道具 JSON 数组
        pa.field("knowledge",    pa.utf8()),          # 知识状态 JSON 数组
        pa.field("description",  pa.utf8()),          # 合并描述
        pa.field("project",      pa.string()),         # 项目隔离
        pa.field("vector",       pa.list_(pa.float32(), EMBED_DIM)),
    ])

def _relation_schema():
    return pa.schema([
        pa.field("id",           pa.utf8()),          # "suye_yehongyi_contract"
        pa.field("from_entity",  pa.utf8()),          # "suye"
        pa.field("to_entity",    pa.utf8()),          # "yehongyi"
        pa.field("rel_type",     pa.utf8()),          # social / spatial / causal / temporal
        pa.field("relation",     pa.utf8()),          # "契约"
        pa.field("episode",      pa.utf8()),          # "ep01"
        pa.field("description",  pa.utf8()),
        pa.field("project",      pa.string()),         # 项目隔离
        pa.field("vector",       pa.list_(pa.float32(), EMBED_DIM)),
    ])

# ──────────────────────────────────────────────────────────────────────────────
# 初始化
# ──────────────────────────────────────────────────────────────────────────────

def cmd_init(args):
    Path(DB_PATH).mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(DB_PATH)
    table_names = _table_names(db)

    for name, schema in [
        (TABLE_ENTITIES,  _entity_schema()),
        (TABLE_ASSETS,    _asset_schema()),
        (TABLE_STATES,    _state_schema()),
        (TABLE_RELATIONS, _relation_schema()),
    ]:
        if name not in table_names:
            try:
                db.create_table(name, schema=schema)
                print(f"✓ 创建表: {name}")
            except ValueError as exc:
                if "already exists" in str(exc):
                    print(f"  跳过（已存在）: {name}")
                else:
                    raise
        else:
            print(f"  跳过（已存在）: {name}")

    print(f"✓ LanceDB 初始化完成: {DB_PATH}")

# ──────────────────────────────────────────────────────────────────────────────
# 写入世界模型
# ──────────────────────────────────────────────────────────────────────────────

def cmd_upsert_world_model(args):
    path = args.path
    if not os.path.exists(path):
        print(f"ERROR: 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        wm = json.load(f)

    episode = wm.get("episode", "unknown")
    project = args.project
    db = lancedb.connect(DB_PATH)

    # ── 角色实体 ──────────────────────────────────────────
    characters = wm.get("entities", {}).get("characters", [])
    entity_rows = []
    for c in characters:
        # 为每个变体都存一行
        raw_variants = c.get("variants")
        if isinstance(raw_variants, dict):
            variants = list(raw_variants.items())
        elif isinstance(raw_variants, list) and raw_variants:
            variants = [
                (
                    str(item.get("variant_id", "default")),
                    item,
                )
                for item in raw_variants
                if isinstance(item, dict)
            ]
        else:
            variants = [("default", {"appearance": c.get("physical", {}).get("form", "")})]

        for v_id, v_data in variants:
            appearance = v_data.get("appearance", "")
            abilities  = ", ".join([a.get("name", "") if isinstance(a, dict) else str(a)
                                    for a in c.get("abilities", [])])
            variant_label = v_data.get("label") or v_data.get("variant_label") or v_id
            desc = f"{c['name']} {variant_label} {appearance} {abilities}"
            entity_rows.append({
                "id":          f"{c['id']}_{episode}_{v_id}",
                "name":        c["name"],
                "entity_type": "character",
                "episode":     episode,
                "tier":        c.get("tier", "minor"),
                "variant":     v_id,
                "description": desc.strip(),
                "metadata":    json.dumps(c, ensure_ascii=False),
                "project":     project,
                "vector":      embed(desc),
            })

    # ── 场景实体 ──────────────────────────────────────────
    locations = wm.get("entities", {}).get("locations", [])
    for loc in locations:
        time_variants = loc.get("temporal_variants", ["day", "night"])
        for t in time_variants:
            lighting = loc.get("lighting_rules", {}).get(t, "")
            desc = f"{loc['name']} {t} {loc.get('atmosphere', '')} {lighting}"
            entity_rows.append({
                "id":          f"{loc['id']}_{episode}_{t}",
                "name":        loc["name"],
                "entity_type": "scene",
                "episode":     episode,
                "tier":        "scene",
                "variant":     t,
                "description": desc.strip(),
                "metadata":    json.dumps(loc, ensure_ascii=False),
                "project":     project,
                "vector":      embed(desc),
            })

    # ── 道具实体 ──────────────────────────────────────────
    props = wm.get("entities", {}).get("props", [])
    for prop in props:
        desc = f"{prop['name']} {prop.get('description', '')} {prop.get('significance', '')}"
        entity_rows.append({
            "id":          f"{prop['id']}_{episode}",
            "name":        prop["name"],
            "entity_type": "prop",
            "episode":     episode,
            "tier":        "prop",
            "variant":     prop.get("condition", "intact"),
            "description": desc.strip(),
            "metadata":    json.dumps(prop, ensure_ascii=False),
            "project":     project,
            "vector":      embed(desc),
        })

    # ── 怪物/灵兽实体（v2.1 新增）──────────────────────────
    creatures = wm.get("entities", {}).get("creatures", [])
    for c in creatures:
        variants = c.get("variants", {"normal": c.get("appearance", "")})
        for v_id, v_appearance in variants.items():
            if isinstance(v_appearance, dict):
                v_appearance = v_appearance.get("appearance", str(v_appearance))
            desc = f"{c['name']} {v_id} {v_appearance} {c.get('tier', 'enemy')}"
            entity_rows.append({
                "id":          f"{c['id']}_{episode}_{v_id}",
                "name":        c["name"],
                "entity_type": "creature",
                "episode":     episode,
                "tier":        c.get("tier", "enemy"),
                "variant":     v_id,
                "description": desc.strip(),
                "metadata":    json.dumps(c, ensure_ascii=False),
                "project":     project,
                "vector":      embed(desc),
            })

    # ── 特效/VFX 实体（v2.1 新增）────────────────────────
    vfx_list = wm.get("entities", {}).get("vfx", [])
    for vfx in vfx_list:
        desc = f"{vfx['name']} {vfx.get('visual_description', '')} {vfx.get('seedance_keywords', '')}"
        entity_rows.append({
            "id":          f"{vfx['id']}_{episode}",
            "name":        vfx["name"],
            "entity_type": "vfx",
            "episode":     episode,
            "tier":        "vfx",
            "variant":     vfx.get("owner", ""),
            "description": desc.strip(),
            "metadata":    json.dumps(vfx, ensure_ascii=False),
            "project":     project,
            "vector":      embed(desc),
        })

    # ── 技能实体（v2.2 新增）────────────────────────────
    skills = wm.get("entities", {}).get("skills", [])
    for skill in skills:
        trigger = skill.get("trigger", {})
        if isinstance(trigger, dict):
            trigger_desc = " ".join(
                str(trigger.get(key, ""))
                for key in ("type", "condition", "cooldown_narrative")
                if trigger.get(key)
            )
        else:
            trigger_desc = str(trigger)

        cost = skill.get("cost", {})
        if isinstance(cost, dict):
            cost_desc = " ".join(
                str(cost.get(key, ""))
                for key in ("resource", "side_effect", "visual_side_effect")
                if cost.get(key)
            )
        else:
            cost_desc = str(cost)

        constraints = " ".join(str(item) for item in skill.get("constraints", []) if item)
        scene_restrictions = " ".join(str(item) for item in skill.get("scene_restrictions", []) if item)
        desc = " ".join(
            part for part in [
                str(skill.get("name", "")),
                str(skill.get("owner", "")),
                trigger_desc,
                cost_desc,
                constraints,
                scene_restrictions,
            ] if part
        )
        entity_rows.append({
            "id":          f"{skill['id']}_{episode}",
            "name":        skill["name"],
            "entity_type": "skill",
            "episode":     episode,
            "tier":        "skill",
            "variant":     str(skill.get("level", "")),
            "description": desc.strip(),
            "metadata":    json.dumps(skill, ensure_ascii=False),
            "project":     project,
            "vector":      embed(desc),
        })

    if entity_rows:
        tbl = db.open_table(TABLE_ENTITIES)
        # 删除本集旧数据再插入（幂等）
        try:
            tbl.delete(f"episode = '{episode}'")
        except Exception:
            pass
        tbl.add(entity_rows)
        print(f"✓ 写入实体: {len(entity_rows)} 条（episode={episode}）")

    # ── 关系 ──────────────────────────────────────────────
    # relationships 可能是 dict{type: []} 或 list[]
    raw_rels = wm.get("relationships", {})
    if isinstance(raw_rels, dict):
        relations = []
        for rel_type, items in raw_rels.items():
            if isinstance(items, list):
                for item in items:
                    item.setdefault("type", rel_type)
                    relations.append(item)
    else:
        relations = raw_rels
    rel_rows = []
    for r in relations:
        desc = f"{r.get('from', '')} {r.get('relation', '')} {r.get('to', '')}"
        rel_rows.append({
            "id":          f"{r.get('from','')}_{r.get('to','')}_{r.get('relation','')}_{episode}",
            "from_entity": r.get("from", ""),
            "to_entity":   r.get("to", ""),
            "rel_type":    r.get("type", "social"),
            "relation":    r.get("relation", ""),
            "episode":     episode,
            "description": desc,
            "project":     project,
            "vector":      embed(desc),
        })

    if rel_rows:
        tbl = db.open_table(TABLE_RELATIONS)
        try:
            tbl.delete(f"episode = '{episode}'")
        except Exception:
            pass
        tbl.add(rel_rows)
        print(f"✓ 写入关系: {len(rel_rows)} 条")

    print(f"✓ 世界模型写入完成: {path}")

# ──────────────────────────────────────────────────────────────────────────────
# 索引资产（单个文件）
# ──────────────────────────────────────────────────────────────────────────────

def _parse_asset_path(path: str) -> dict:
    """从文件路径解析资产元信息。"""
    p = Path(path)
    name = p.stem   # e.g. "苏夜-default-front" or "黑雾森林-night-styleframe"
    parts = name.split("-")

    if "packs/characters" in path or "characters/images" in path:
        # 角色资产：{名字}-{variant}-{angle}.png
        # 名字可能含多段（如"叶红衣"），variant/angle 是后缀
        asset_type = "character"
        pack_tier  = 1 if "packs" in path else 2
        angle      = parts[-1] if len(parts) >= 1 else "unknown"
        variant    = parts[-2] if len(parts) >= 2 else "default"
        entity_name = "-".join(parts[:-2]) if len(parts) > 2 else name
        time_of_day = ""
        desc = f"{entity_name} {variant} {angle} 角色参考图"

    elif "packs/scenes" in path or "scenes/images" in path:
        # 场景资产：{名字}-{time_of_day}-styleframe.png 或 {名字}-{time_of_day}.png
        asset_type  = "scene"
        pack_tier   = 1 if "packs" in path else 2
        angle       = parts[-1] if len(parts) >= 1 else "styleframe"
        time_of_day = parts[-2] if len(parts) >= 2 else "day"
        entity_name = "-".join(parts[:-2]) if len(parts) > 2 else name
        variant     = ""
        desc = f"{entity_name} {time_of_day} 场景参考图"

    elif "packs/props" in path or "props" in path:
        asset_type  = "prop"
        pack_tier   = 1 if "packs" in path else 2
        angle       = parts[-1] if len(parts) >= 1 else "view"
        variant     = ""
        time_of_day = ""
        entity_name = "-".join(parts[:-1]) if len(parts) > 1 else name
        desc = f"{entity_name} 道具参考图"

    else:
        asset_type  = "unknown"
        pack_tier   = 3
        angle       = ""
        variant     = ""
        time_of_day = ""
        entity_name = name
        desc = name

    return {
        "id":          path,
        "path":        path,
        "asset_type":  asset_type,
        "entity_name": entity_name,
        "variant":     variant,
        "angle":       angle,
        "time_of_day": time_of_day,
        "pack_tier":   pack_tier,
        "description": desc,
        "vector":      embed(desc),
    }

def cmd_upsert_asset(args):
    path = args.path
    if not os.path.exists(path):
        print(f"WARN: 文件不存在，跳过: {path}", file=sys.stderr)
        return

    db  = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_ASSETS)
    row = _parse_asset_path(path)
    row["project"] = args.project
    try:
        tbl.delete(f"id = '{path}'")
    except Exception:
        pass
    tbl.add([row])
    print(f"✓ 索引资产: {path} → {row['entity_name']} [{row['asset_type']}]")

def cmd_index_assets(args):
    """批量索引 assets/ 目录下的所有图片。"""
    root = args.path
    db   = lancedb.connect(DB_PATH)
    tbl  = db.open_table(TABLE_ASSETS)

    rows  = []
    count = 0
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for img_path in Path(root).rglob(ext):
            row = _parse_asset_path(str(img_path))
            row["project"] = args.project
            rows.append(row)
            count += 1
            if len(rows) >= 100:   # 批量提交
                tbl.add(rows)
                rows = []

    if rows:
        tbl.add(rows)

    print(f"✓ 批量索引完成: {count} 个资产 (root={root})")

# ──────────────────────────────────────────────────────────────────────────────
# 语义检索
# ──────────────────────────────────────────────────────────────────────────────

def cmd_search_assets(args):
    """
    语义检索资产。输出 JSON 数组，供 memory-agent 使用。
    """
    query = args.query
    n     = args.n
    atype = args.type   # character / scene / prop / None

    db  = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_ASSETS)

    vec = embed(query)
    where_clauses = []
    # project 过滤（仅当表中有 project 字段时）
    try:
        sample = tbl.to_pandas().columns.tolist()
        if 'project' in sample and args.project != 'default':
            where_clauses.append(f"project = '{args.project}'")
    except Exception:
        pass
    if atype:
        where_clauses.append(f"asset_type = '{atype}'")
    search = tbl.search(vec)
    if where_clauses:
        search = search.where(" AND ".join(where_clauses))
    results = search.limit(n * 3).to_list()

    # 只保留存在的文件
    results = [r for r in results if os.path.exists(r["path"])]

    # 按 pack_tier 升序 + 距离升序 排序
    results.sort(key=lambda r: (r["pack_tier"], r.get("_distance", 0)))

    output = []
    for r in results[:n]:
        output.append({
            "path":        r["path"],
            "entity_name": r["entity_name"],
            "asset_type":  r["asset_type"],
            "variant":     r["variant"],
            "angle":       r["angle"],
            "time_of_day": r["time_of_day"],
            "pack_tier":   r["pack_tier"],
            "score":       round(1 - r.get("_distance", 0), 4),
        })

    print(json.dumps(output, ensure_ascii=False, indent=2))

def cmd_search_entities(args):
    """
    语义检索实体（角色/场景/道具）。
    """
    query   = args.query
    n       = args.n
    etype   = args.type   # character / scene / prop / None
    episode = getattr(args, "episode", None)

    db  = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_ENTITIES)

    vec = embed(query)
    where_clauses = []
    try:
        cols = tbl.to_pandas().columns.tolist()
        if 'project' in cols and getattr(args, 'project', 'default') != 'default':
            where_clauses.append(f"project = '{args.project}'")
    except Exception:
        pass
    if etype:
        where_clauses.append(f"entity_type = '{etype}'")
    if episode:
        where_clauses.append(f"episode = '{episode}'")
    search = tbl.search(vec)
    if where_clauses:
        search = search.where(" AND ".join(where_clauses))
    results = search.limit(n).to_list()

    output = []
    for r in results[:n]:
        output.append({
            "id":          r["id"],
            "name":        r["name"],
            "entity_type": r["entity_type"],
            "episode":     r["episode"],
            "variant":     r["variant"],
            "description": r["description"],
            "score":       round(1 - r.get("_distance", 0), 4),
            "metadata":    json.loads(r["metadata"]) if r.get("metadata") else {},
        })

    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_search_relations(args):
    """
    语义检索关系（人物关系 / 因果 / 空间关系）。
    """
    query = args.query
    n = args.n
    rel_type = args.type
    episode = getattr(args, "episode", None)

    db = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_RELATIONS)

    vec = embed(query)
    where_clauses = []
    try:
        cols = tbl.to_pandas().columns.tolist()
        if 'project' in cols and getattr(args, 'project', 'default') != 'default':
            where_clauses.append(f"project = '{args.project}'")
    except Exception:
        pass
    if rel_type:
        where_clauses.append(f"rel_type = '{rel_type}'")
    if episode:
        where_clauses.append(f"episode = '{episode}'")
    results = tbl.search(vec).where(" AND ".join(where_clauses)).limit(n).to_list()

    output = []
    for r in results[:n]:
        output.append({
            "id":          r["id"],
            "from_entity": r["from_entity"],
            "to_entity":   r["to_entity"],
            "rel_type":    r["rel_type"],
            "relation":    r["relation"],
            "episode":     r["episode"],
            "description": r["description"],
            "score":       round(1 - r.get("_distance", 0), 4),
        })

    print(json.dumps(output, ensure_ascii=False, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# 写入 / 查询 角色状态快照
# ──────────────────────────────────────────────────────────────────────────────

def cmd_upsert_state(args):
    """
    写入单个 shot 的角色状态快照。
    从 state/shot-packets/{ep}-{shot_id}.json 读取。
    """
    shot_packet_path = args.path
    if not os.path.exists(shot_packet_path):
        print(f"ERROR: 文件不存在: {shot_packet_path}", file=sys.stderr)
        sys.exit(1)

    with open(shot_packet_path) as f:
        pkt = json.load(f)

    episode  = pkt.get("episode", "unknown")
    shot_id  = pkt.get("shot_id", "unknown")
    project  = args.project
    db       = lancedb.connect(DB_PATH)
    tbl      = db.open_table(TABLE_STATES)
    rows     = []

    for c in pkt.get("characters", []):
        cs   = c.get("current_state", {})
        desc = (f"{c.get('id','')} {c.get('variant','')} "
                f"{cs.get('form','')} {cs.get('costume','')} "
                f"{cs.get('emotion','')} {cs.get('injury','')}")
        rows.append({
            "id":           f"{c.get('id','')}_{episode}_{shot_id}",
            "character_id": c.get("id", ""),
            "episode":      episode,
            "shot_id":      shot_id,
            "variant":      c.get("variant", ""),
            "emotion":      cs.get("emotion", ""),
            "injury":       cs.get("injury", ""),
            "props":        json.dumps(cs.get("props_in_possession", []), ensure_ascii=False),
            "knowledge":    json.dumps(cs.get("knowledge", []), ensure_ascii=False),
            "description":  desc.strip(),
            "project":      project,
            "vector":       embed(desc),
        })

    if rows:
        try:
            tbl.delete(f"episode = '{episode}' AND shot_id = '{shot_id}'")
        except Exception:
            pass
        tbl.add(rows)
        print(f"✓ 写入状态快照: {len(rows)} 条 (shot={shot_id})")

def cmd_get_state(args):
    """查询某角色在指定集某 shot 的状态。"""
    character_id = args.character_id
    episode      = args.episode
    shot_id      = args.shot_id

    db  = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_STATES)

    df = tbl.to_pandas()
    filtered = df[
        (df['character_id'] == character_id) &
        (df['episode'] == episode) &
        (df['project'] == args.project)
    ]

    if filtered.empty:
        print(json.dumps({"found": False, "character_id": character_id}))
        return

    # 找最近的 shot（按 shot 编号倒序取最近的）
    def shot_num(sid):
        m = re.search(r"shot-?0*(\d+)$", str(sid))
        return int(m.group(1)) if m else 0

    target_num = shot_num(shot_id)
    filtered = filtered.copy()
    filtered['_shot_num'] = filtered['shot_id'].apply(shot_num)
    candidates = filtered[filtered['_shot_num'] <= target_num]
    if candidates.empty:
        candidates = filtered

    best = candidates.sort_values('_shot_num', ascending=False).iloc[0]
    result = best.to_dict()
    result.pop('vector', None)
    result.pop('_shot_num', None)
    result["props"]     = json.loads(result.get("props", "[]"))
    result["knowledge"] = json.loads(result.get("knowledge", "[]"))
    print(json.dumps(result, ensure_ascii=False, default=str))

# ──────────────────────────────────────────────────────────────────────────────
# 批量查询（search-batch）
# ──────────────────────────────────────────────────────────────────────────────

def _search_entities_inline(db, q: dict, project: str) -> list:
    tbl = db.open_table(TABLE_ENTITIES)
    vec = embed(q.get("query", ""))
    n = q.get("n", 5)
    where_clauses = []
    try:
        cols = tbl.to_pandas().columns.tolist()
        if 'project' in cols and project != 'default':
            where_clauses.append(f"project = '{project}'")
    except Exception:
        pass
    if q.get("type"):
        where_clauses.append(f"entity_type = '{q['type']}'")
    if q.get("episode"):
        where_clauses.append(f"episode = '{q['episode']}'")
    results = tbl.search(vec).where(" AND ".join(where_clauses)).limit(n).to_list()
    return [{
        "id": r["id"], "name": r["name"], "entity_type": r["entity_type"],
        "episode": r["episode"], "variant": r["variant"],
        "description": r["description"],
        "score": round(1 - r.get("_distance", 0), 4),
        "metadata": json.loads(r["metadata"]) if r.get("metadata") else {},
    } for r in results]


def _search_assets_inline(db, q: dict, project: str) -> list:
    tbl = db.open_table(TABLE_ASSETS)
    vec = embed(q.get("query", ""))
    n = q.get("n", 3)
    where_clauses = []
    try:
        cols = tbl.to_pandas().columns.tolist()
        if 'project' in cols and project != 'default':
            where_clauses.append(f"project = '{project}'")
    except Exception:
        pass
    if q.get("type"):
        where_clauses.append(f"asset_type = '{q['type']}'")
    results = tbl.search(vec).where(" AND ".join(where_clauses)).limit(n).to_list()
    results = [r for r in results if os.path.exists(r["path"])]
    results.sort(key=lambda r: (r["pack_tier"], r.get("_distance", 0)))
    return [{
        "path": r["path"], "entity_name": r["entity_name"],
        "asset_type": r["asset_type"], "variant": r["variant"],
        "angle": r["angle"], "time_of_day": r["time_of_day"],
        "pack_tier": r["pack_tier"],
        "score": round(1 - r.get("_distance", 0), 4),
    } for r in results[:n]]


def _get_state_inline(db, q: dict, project: str) -> dict:
    tbl = db.open_table(TABLE_STATES)
    df = tbl.to_pandas()
    filtered = df[
        (df['character_id'] == q.get("character_id", "")) &
        (df['episode'] == q.get("episode", "")) &
        (df['project'] == project)
    ]
    if filtered.empty:
        return {"found": False, "character_id": q.get("character_id", "")}

    def shot_num(sid):
        m = re.search(r"shot-?0*(\d+)$", str(sid))
        return int(m.group(1)) if m else 0

    target_num = shot_num(q.get("shot_id", ""))
    filtered = filtered.copy()
    filtered['_shot_num'] = filtered['shot_id'].apply(shot_num)
    candidates = filtered[filtered['_shot_num'] <= target_num]
    if candidates.empty:
        candidates = filtered
    best = candidates.sort_values('_shot_num', ascending=False).iloc[0]
    result = best.to_dict()
    result.pop('vector', None)
    result.pop('_shot_num', None)
    result["props"] = json.loads(result.get("props", "[]"))
    result["knowledge"] = json.loads(result.get("knowledge", "[]"))
    return result


def _search_relations_inline(db, q: dict, project: str) -> list:
    tbl = db.open_table(TABLE_RELATIONS)
    vec = embed(q.get("query", ""))
    n = q.get("n", 5)
    where_clauses = []
    try:
        cols = tbl.to_pandas().columns.tolist()
        if 'project' in cols and project != 'default':
            where_clauses.append(f"project = '{project}'")
    except Exception:
        pass
    if q.get("type"):
        where_clauses.append(f"rel_type = '{q['type']}'")
    if q.get("episode"):
        where_clauses.append(f"episode = '{q['episode']}'")
    results = tbl.search(vec).where(" AND ".join(where_clauses)).limit(n).to_list()
    return [{
        "id": r["id"], "from_entity": r["from_entity"],
        "to_entity": r["to_entity"], "rel_type": r["rel_type"],
        "relation": r["relation"], "episode": r["episode"],
        "description": r["description"],
        "score": round(1 - r.get("_distance", 0), 4),
    } for r in results]


def cmd_search_batch(args):
    """批量查询：一次进程启动，执行多个查询，返回 JSON 数组。"""
    batch_input = json.loads(args.batch_json)
    queries = batch_input.get("queries", [])
    results = []

    db = lancedb.connect(DB_PATH)

    for q in queries:
        q_type = q.get("type_cmd", q.get("type"))
        try:
            if q_type == "search-entities":
                result = _search_entities_inline(db, q, args.project)
            elif q_type == "search-assets":
                result = _search_assets_inline(db, q, args.project)
            elif q_type == "get-state":
                result = _get_state_inline(db, q, args.project)
            elif q_type == "search-relations":
                result = _search_relations_inline(db, q, args.project)
            else:
                result = {"error": f"unknown query type: {q_type}"}
        except Exception as e:
            result = {"error": str(e)}
        results.append({"query": q, "result": result})

    print(json.dumps(results, ensure_ascii=False, default=str))

# ──────────────────────────────────────────────────────────────────────────────
# 统计
# ──────────────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    db = lancedb.connect(DB_PATH)
    table_names = _table_names(db)
    print("=== LanceDB 统计 ===")
    for tname in [TABLE_ENTITIES, TABLE_ASSETS, TABLE_STATES, TABLE_RELATIONS]:
        if tname in table_names:
            count = db.open_table(tname).count_rows()
            print(f"  {tname}: {count} 条")
        else:
            print(f"  {tname}: 表不存在（请先运行 init）")
    print(f"  路径: {DB_PATH}")
    print(f"  Embedding: {'sentence-transformers (本地)' if _USE_LOCAL_EMBED else '哈希降级（建议安装 sentence-transformers）'}")

# ──────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="LanceDB 向量库管理")
    p.add_argument("--project", default=os.environ.get("VECTORDB_PROJECT", "default"),
                   help="Project name for data isolation")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("init", help="初始化数据库和表结构")

    p_uwm = sub.add_parser("upsert-world-model", help="写入世界模型 JSON")
    p_uwm.add_argument("path", help="world-model.json 路径")

    p_ua = sub.add_parser("upsert-asset", help="索引单个资产文件")
    p_ua.add_argument("path", help="图片路径")

    p_ia = sub.add_parser("index-assets", help="批量索引资产目录")
    p_ia.add_argument("path", nargs="?", default="assets/", help="资产根目录")

    p_sa = sub.add_parser("search-assets", help="语义检索资产")
    p_sa.add_argument("query", help="查询文本")
    p_sa.add_argument("--type", choices=["character", "scene", "prop", "creature", "vfx", "skill"], default=None)
    p_sa.add_argument("--n", type=int, default=3)

    p_se = sub.add_parser("search-entities", help="语义检索实体")
    p_se.add_argument("query", help="查询文本")
    p_se.add_argument("--type", choices=["character", "scene", "prop", "creature", "vfx", "skill"], default=None)
    p_se.add_argument("--episode", default=None)
    p_se.add_argument("--n", type=int, default=5)

    p_sr = sub.add_parser("search-relations", help="语义检索关系")
    p_sr.add_argument("query", help="查询文本")
    p_sr.add_argument("--type", choices=["social", "spatial", "causal", "temporal", "skill_usage"], default=None)
    p_sr.add_argument("--episode", default=None)
    p_sr.add_argument("--n", type=int, default=5)

    p_us = sub.add_parser("upsert-state", help="写入 shot 状态快照")
    p_us.add_argument("path", help="shot-packet.json 路径")

    p_gs = sub.add_parser("get-state", help="查询角色在某 shot 的状态")
    p_gs.add_argument("character_id")
    p_gs.add_argument("episode")
    p_gs.add_argument("shot_id")

    sub.add_parser("stats", help="查看统计信息")

    p_sb = sub.add_parser("search-batch", help="批量查询（一次进程多个查询）")
    p_sb.add_argument("batch_json", help="JSON string with queries array")

    args = p.parse_args()

    dispatch = {
        "init":             cmd_init,
        "upsert-world-model": cmd_upsert_world_model,
        "upsert-asset":     cmd_upsert_asset,
        "index-assets":     cmd_index_assets,
        "search-assets":    cmd_search_assets,
        "search-entities":  cmd_search_entities,
        "search-relations": cmd_search_relations,
        "upsert-state":     cmd_upsert_state,
        "get-state":        cmd_get_state,
        "search-batch":     cmd_search_batch,
        "stats":            cmd_stats,
    }

    if args.cmd not in dispatch:
        p.print_help()
        sys.exit(1)

    dispatch[args.cmd](args)

if __name__ == "__main__":
    main()
