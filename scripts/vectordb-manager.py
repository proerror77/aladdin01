#!/usr/bin/env -S /Users/proerror/Documents/aladdin01/.venv/bin/python
"""
vectordb-manager.py — LanceDB 向量库管理

用法:
  python3 scripts/vectordb-manager.py init
  python3 scripts/vectordb-manager.py upsert-world-model state/ontology/ep01-world-model.json
  python3 scripts/vectordb-manager.py upsert-asset assets/packs/characters/苏夜-default-front.png
  python3 scripts/vectordb-manager.py search-assets "苏夜 青玉蚕 正面" --type character --n 3
  python3 scripts/vectordb-manager.py search-entities "黑雾森林 夜晚" --type scene --n 3
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

DB_PATH = "state/vectordb/lancedb"
EMBED_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2 维度

TABLE_ENTITIES  = "entities"   # 角色 / 场景 / 道具 实体
TABLE_ASSETS    = "assets"     # 资产文件索引（图片路径）
TABLE_STATES    = "states"     # 每个 shot 的角色/场景状态快照
TABLE_RELATIONS = "relations"  # 实体关系

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
        pa.field("entity_type", pa.utf8()),           # character / scene / prop
        pa.field("episode",     pa.utf8()),           # "ep01"
        pa.field("tier",        pa.utf8()),           # protagonist / supporting / minor
        pa.field("variant",     pa.utf8()),           # "default" / "snake_green"
        pa.field("description", pa.utf8()),           # 合并的文本描述
        pa.field("metadata",    pa.utf8()),           # JSON 字符串（原始字段）
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
        pa.field("vector",       pa.list_(pa.float32(), EMBED_DIM)),
    ])

# ──────────────────────────────────────────────────────────────────────────────
# 初始化
# ──────────────────────────────────────────────────────────────────────────────

def cmd_init(args):
    Path(DB_PATH).mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(DB_PATH)

    for name, schema in [
        (TABLE_ENTITIES,  _entity_schema()),
        (TABLE_ASSETS,    _asset_schema()),
        (TABLE_STATES,    _state_schema()),
        (TABLE_RELATIONS, _relation_schema()),
    ]:
        if name not in db.table_names():
            db.create_table(name, schema=schema)
            print(f"✓ 创建表: {name}")
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
    db = lancedb.connect(DB_PATH)

    # ── 角色实体 ──────────────────────────────────────────
    characters = wm.get("entities", {}).get("characters", [])
    entity_rows = []
    for c in characters:
        # 为每个变体都存一行
        variants = c.get("variants", {"default": {"appearance": c.get("physical", {}).get("form", "")}})
        for v_id, v_data in variants.items():
            appearance = v_data.get("appearance", "")
            abilities  = ", ".join([a.get("name", "") if isinstance(a, dict) else str(a)
                                    for a in c.get("abilities", [])])
            desc = f"{c['name']} {v_data.get('label', v_id)} {appearance} {abilities}"
            entity_rows.append({
                "id":          f"{c['id']}_{episode}_{v_id}",
                "name":        c["name"],
                "entity_type": "character",
                "episode":     episode,
                "tier":        c.get("tier", "minor"),
                "variant":     v_id,
                "description": desc.strip(),
                "metadata":    json.dumps(c, ensure_ascii=False),
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
            rows.append(_parse_asset_path(str(img_path)))
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
    results = (
        tbl.search(vec)
           .limit(n * 3)         # 多取一些，再用 where 过滤
           .to_list()
    )

    # 过滤类型
    if atype:
        results = [r for r in results if r["asset_type"] == atype]

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

    vec     = embed(query)
    results = tbl.search(vec).limit(n * 3).to_list()

    if etype:
        results = [r for r in results if r["entity_type"] == etype]
    if episode:
        results = [r for r in results if r["episode"] == episode]

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
            "vector":       embed(desc),
        })

    if rows:
        tbl.add(rows)
        print(f"✓ 写入状态快照: {len(rows)} 条 (shot={shot_id})")

def cmd_get_state(args):
    """查询某角色在指定集某 shot 的状态。"""
    character_id = args.character_id
    episode      = args.episode
    shot_id      = args.shot_id

    db  = lancedb.connect(DB_PATH)
    tbl = db.open_table(TABLE_STATES)

    row_id = f"{character_id}_{episode}_{shot_id}"
    results = tbl.search([0.0] * EMBED_DIM).where(
        f"character_id = '{character_id}' AND episode = '{episode}'"
    ).limit(50).to_list()

    if not results:
        print(json.dumps({"found": False, "character_id": character_id}))
        return

    # 找最近的 shot（按 shot 编号倒序取最近的）
    def shot_num(r):
        m = re.search(r"shot-?0*(\d+)$", r["shot_id"])
        return int(m.group(1)) if m else 0

    target_num = shot_num({"shot_id": shot_id})
    candidates = [r for r in results if shot_num(r) <= target_num]
    if not candidates:
        candidates = results

    candidates.sort(key=shot_num, reverse=True)
    best = candidates[0]
    best["props"]     = json.loads(best.get("props", "[]"))
    best["knowledge"] = json.loads(best.get("knowledge", "[]"))
    best.pop("vector", None)
    print(json.dumps(best, ensure_ascii=False, indent=2))

# ──────────────────────────────────────────────────────────────────────────────
# 统计
# ──────────────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    db = lancedb.connect(DB_PATH)
    print("=== LanceDB 统计 ===")
    for tname in [TABLE_ENTITIES, TABLE_ASSETS, TABLE_STATES, TABLE_RELATIONS]:
        if tname in db.table_names():
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
    p_sa.add_argument("--type", choices=["character", "scene", "prop", "creature", "vfx"], default=None)
    p_sa.add_argument("--n", type=int, default=3)

    p_se = sub.add_parser("search-entities", help="语义检索实体")
    p_se.add_argument("query", help="查询文本")
    p_se.add_argument("--type", choices=["character", "scene", "prop", "creature", "vfx"], default=None)
    p_se.add_argument("--episode", default=None)
    p_se.add_argument("--n", type=int, default=5)

    p_us = sub.add_parser("upsert-state", help="写入 shot 状态快照")
    p_us.add_argument("path", help="shot-packet.json 路径")

    p_gs = sub.add_parser("get-state", help="查询角色在某 shot 的状态")
    p_gs.add_argument("character_id")
    p_gs.add_argument("episode")
    p_gs.add_argument("shot_id")

    sub.add_parser("stats", help="查看统计信息")

    args = p.parse_args()

    dispatch = {
        "init":             cmd_init,
        "upsert-world-model": cmd_upsert_world_model,
        "upsert-asset":     cmd_upsert_asset,
        "index-assets":     cmd_index_assets,
        "search-assets":    cmd_search_assets,
        "search-entities":  cmd_search_entities,
        "upsert-state":     cmd_upsert_state,
        "get-state":        cmd_get_state,
        "stats":            cmd_stats,
    }

    if args.cmd not in dispatch:
        p.print_help()
        sys.exit(1)

    dispatch[args.cmd](args)

if __name__ == "__main__":
    main()
