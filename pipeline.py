#!/usr/bin/env python3
import argparse
import base64
import hashlib
import http.client
import io
import json
import mimetypes
import re
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zipfile import ZipFile
from zoneinfo import ZoneInfo

@dataclass
class Paper:
    parent_item_id: int
    parent_key: str
    attachment_item_id: int
    attachment_key: str
    attachment_path: str
    attachment_title: str
    date_modified: str
    title: str = ""
    translated_title: str = ""
    abstract: str = ""
    publication_title: str = ""
    date: str = ""
    doi: str = ""
    url: str = ""
    item_type: str = ""
    creators: str = ""
    collections: List[str] = None

    def __post_init__(self):
        if self.collections is None:
            self.collections = []


@dataclass
class ParsedDocument:
    content: str
    content_format: str
    parser_name: str
    truncated: bool
    meta: Dict[str, Any]


PAPER_ITEM_TYPES = {
    "journalArticle",   # 期刊论文
    "conferencePaper",  # 会议论文
    "preprint",         # 预印本
    "report",           # 技术报告
    "manuscript",       # 手稿
}
ENV_PATH = Path(__file__).resolve().parent / ".env"
EASYSCHOLAR_API_URL = "https://www.easyscholar.cc/open/getPublicationRank"
EASYSCHOLAR_KEYS = ("sciif", "sci", "sciUp")
_EASYSCHOLAR_LAST_CALL_TS = 0.0
MINERU_API_BASE = "https://mineru.net/api/v4"
MINERU_POLL_INTERVAL_SEC = 5.0
MINERU_POLL_TIMEOUT_SEC = 600.0
MAX_MULTIMODAL_IMAGES = 6
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def default_provider_config_path() -> str:
    return str(Path(__file__).resolve().parent / ".config" / "providers.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Zotero -> AI -> Obsidian 自动论文精读流程")
    parser.add_argument("--zotero-db", default=str(Path.home() / "Zotero" / "zotero.sqlite"))
    parser.add_argument("--zotero-storage", default=str(Path.home() / "Zotero" / "storage"))
    parser.add_argument("--template", required=True, help="论文分析模板 markdown 路径")
    parser.add_argument(
        "--obsidian-root",
        default=str(Path.home() / "Documents" / "Obsidian" / "论文精读"),
        help="Obsidian 根目录",
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument(
        "--provider-config",
        default=default_provider_config_path(),
        help="供应商配置文件（provider_specs 与默认模型等，不保存 API Key）",
    )
    parser.add_argument("--limit", type=int, default=1, help="每次处理论文数量")
    parser.add_argument("--since-days", type=int, default=0, help="只处理最近 N 天更新的条目，0 表示不过滤")
    parser.add_argument(
        "--collection",
        action="append",
        default=None,
        help="指定 Zotero collection 名称，可重复；用于扫描某一个目录（合集）下的论文",
    )
    parser.add_argument(
        "--collection-item-key",
        action="append",
        default=None,
        help="在指定 collection 中进一步限定条目 key（可重复），用于选择目录下单篇/少量论文",
    )
    parser.add_argument(
        "--parent-item-key",
        action="append",
        default=None,
        help="按父条目 key（可重复）直接查找并处理",
    )
    parser.add_argument(
        "--collection-all-types",
        action="store_true",
        help="按 collection 扫描时不过滤论文类型，处理目录下所有含 PDF 的条目",
    )
    parser.add_argument(
        "--allow-global-scan",
        action="store_true",
        help="允许全局扫描（不建议，默认关闭）",
    )
    parser.add_argument(
        "--pdf-parser",
        choices=["auto", "mineru", "pypdf"],
        default="auto",
        help="PDF 解析方式：默认优先 MinerU，失败回退到本地 pypdf",
    )
    parser.add_argument(
        "--mineru-model-version",
        default="vlm",
        help="MinerU 标准 API 的 model_version",
    )
    parser.add_argument(
        "--mineru-language",
        default="en",
        help="MinerU 标准 API 的 language 参数",
    )
    parser.add_argument("--max-pdf-chars", type=int, default=120000)
    parser.add_argument("--enable-thinking", action="store_true", help="开启深度思考（按供应商能力注入对应参数）")
    parser.add_argument("--state-file", default=".state/processed_items.json")
    parser.add_argument("--force", action="store_true", help="忽略已处理状态，强制重新生成")
    parser.add_argument("--dry-run", action="store_true", help="试运行：仅校验模型连通性并预演流程，不执行论文分析、不写文件")
    return parser.parse_args()


def resolve_provider_specs(provider_config_path: str) -> Dict[str, Dict[str, object]]:
    cfg = load_provider_config(provider_config_path)
    catalog = (cfg.get("provider_specs") or {}) if isinstance(cfg, dict) else {}
    if not isinstance(catalog, dict) or not catalog:
        raise RuntimeError(
            f"供应商目录缺失：请在 {Path(provider_config_path).expanduser()} 中配置 provider_specs"
        )

    merged: Dict[str, Dict[str, object]] = {}
    for name, item in catalog.items():
        if not isinstance(item, dict):
            continue
        models = item.get("models", [])
        if not isinstance(models, list):
            models = []
        merged[str(name)] = {
            "provider_type": item.get("provider_type") or "openai_compatible",
            "env_var": item.get("env_var") or "",
            "default_model": item.get("default_model") or (models[0] if models else ""),
            "models": [m for m in models if isinstance(m, str) and m.strip()],
            "base_url": item.get("base_url"),
        }
    providers_cfg = (cfg.get("providers") or {}) if isinstance(cfg, dict) else {}
    for name, item in providers_cfg.items():
        if not isinstance(item, dict):
            continue
        existing = dict(merged.get(name, {}))
        provider_type = item.get("provider_type") or existing.get("provider_type") or "openai_compatible"
        env_var = existing.get("env_var", "")
        default_model = item.get("model") or existing.get("default_model") or ""
        base_url = item.get("base_url", existing.get("base_url"))
        models = list(existing.get("models", []))
        custom_models = item.get("custom_models", [])
        if isinstance(custom_models, list):
            for m in custom_models:
                if isinstance(m, str) and m.strip() and m not in models:
                    models.append(m)
        if default_model and default_model not in models:
            models.append(default_model)
        merged[name] = {
            "provider_type": provider_type,
            "env_var": env_var,
            "default_model": default_model or (models[0] if models else ""),
            "models": models,
            "base_url": base_url,
        }
    return merged


def default_model_for(provider: str, provider_specs: Dict[str, Dict[str, object]]) -> str:
    spec = provider_specs.get(provider)
    if not spec:
        raise ValueError(f"Unknown provider: {provider}")
    return str(spec["default_model"])


def load_provider_config(path: str) -> Dict[str, object]:
    p = Path(path).expanduser()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_dotenv_values(path: Path = ENV_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = k.strip()
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
    return out


def fetch_easyscholar_rank_info(secret_key: str, publication_name: str) -> Dict[str, str]:
    if not secret_key or not publication_name.strip():
        return {}

    global _EASYSCHOLAR_LAST_CALL_TS
    now = time.monotonic()
    wait = 0.55 - (now - _EASYSCHOLAR_LAST_CALL_TS)
    if wait > 0:
        time.sleep(wait)

    query = urllib.parse.urlencode(
        {
            "secretKey": secret_key,
            "publicationName": publication_name.strip(),
        }
    )
    url = f"{EASYSCHOLAR_API_URL}?{query}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    _EASYSCHOLAR_LAST_CALL_TS = time.monotonic()

    obj = json.loads(body)
    if obj.get("code") != 200 or not isinstance(obj.get("data"), dict):
        return {}

    official = obj["data"].get("officialRank")
    if not isinstance(official, dict):
        return {}
    src = official.get("select") if isinstance(official.get("select"), dict) else official.get("all")
    if not isinstance(src, dict):
        return {}

    out: Dict[str, str] = {}
    for k in EASYSCHOLAR_KEYS:
        v = str(src.get(k, "") or "").strip()
        if not v:
            continue
        out[k] = v
    return out


def provider_env_key(provider: str, spec: Dict[str, object]) -> str:
    env_var = str(spec.get("env_var", "") or "").strip()
    if env_var:
        return env_var
    base = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    return f"{base}_API_KEY" if base else "PROVIDER_API_KEY"


def get_api_key(
    provider: str,
    arg_api_key: Optional[str],
    provider_config_path: str,
    provider_specs: Dict[str, Dict[str, object]],
) -> str:
    if arg_api_key:
        return arg_api_key
    spec = provider_specs.get(provider, {})
    env_var = provider_env_key(provider, spec)
    key = (load_dotenv_values().get(env_var) or "").strip()
    if key:
        return key
    if not key:
        raise RuntimeError(
            f"缺少 API Key，请设置参数 --api-key 或在 {ENV_PATH} 中配置 {env_var}"
        )
    return key

def load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def copy_db_to_temp(db_path: str) -> str:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"找不到 Zotero 数据库: {db_path}")
    tmp = tempfile.NamedTemporaryFile(prefix="zotero_", suffix=".sqlite", delete=False)
    tmp.close()
    shutil.copy2(db_path, tmp.name)
    return tmp.name


def fetch_candidate_papers(conn: sqlite3.Connection, since_days: int, item_keys: Optional[List[str]], limit: int) -> List[Paper]:
    conn.row_factory = sqlite3.Row
    params: List[object] = []
    where = [
        "ia.contentType = 'application/pdf'",
        "ia.parentItemID IS NOT NULL",
        "pi.itemID NOT IN (SELECT itemID FROM deletedItems)",
        "ai.itemID NOT IN (SELECT itemID FROM deletedItems)",
    ]
    if since_days > 0 and not item_keys:
        cutoff = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        where.append("substr(pi.dateModified, 1, 10) >= ?")
        params.append(cutoff)

    if item_keys:
        placeholders = ",".join("?" for _ in item_keys)
        where.append(f"pi.key IN ({placeholders})")
        params.extend(item_keys)

    query = f"""
        SELECT
            pi.itemID AS parent_item_id,
            pi.key AS parent_key,
            ai.itemID AS attachment_item_id,
            ai.key AS attachment_key,
            ia.path AS attachment_path,
            (
                SELECT v.value
                FROM itemData d
                JOIN fieldsCombined f ON f.fieldID = d.fieldID
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE d.itemID = ai.itemID
                  AND f.fieldName = 'title'
                LIMIT 1
            ) AS attachment_title,
            pi.dateModified AS date_modified
        FROM itemAttachments ia
        JOIN items ai ON ai.itemID = ia.itemID
        JOIN items pi ON pi.itemID = ia.parentItemID
        WHERE {' AND '.join(where)}
        ORDER BY pi.dateModified DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    papers: List[Paper] = []
    best_by_parent: Dict[int, sqlite3.Row] = {}

    def _attachment_score(title: str) -> int:
        t = (title or "").strip().lower()
        if "full text pdf" in t:
            return 3
        if t == "pdf":
            return 2
        return 1

    for row in rows:
        pid = row["parent_item_id"]
        old = best_by_parent.get(pid)
        if old is None:
            best_by_parent[pid] = row
            continue
        if _attachment_score(str(row["attachment_title"] or "")) > _attachment_score(str(old["attachment_title"] or "")):
            best_by_parent[pid] = row

    for row in best_by_parent.values():
        papers.append(
            Paper(
                parent_item_id=row["parent_item_id"],
                parent_key=row["parent_key"],
                attachment_item_id=row["attachment_item_id"],
                attachment_key=row["attachment_key"],
                attachment_path=row["attachment_path"],
                attachment_title=str(row["attachment_title"] or ""),
                date_modified=row["date_modified"],
            )
        )

    for p in papers:
        enrich_metadata(conn, p)
    return papers


def fetch_papers_by_collection(
    conn: sqlite3.Connection,
    since_days: int,
    collections: List[str],
    limit: int,
    collection_item_keys: Optional[List[str]] = None,
    papers_only: bool = True,
) -> List[Paper]:
    conn.row_factory = sqlite3.Row
    root_ids = _resolve_collection_root_ids(conn, collections)
    if not root_ids:
        return []
    placeholders = ",".join("?" for _ in root_ids)
    params: List[object] = []
    where = [
        "ia.contentType = 'application/pdf'",
        "ia.parentItemID IS NOT NULL",
        "pi.itemID NOT IN (SELECT itemID FROM deletedItems)",
        "ai.itemID NOT IN (SELECT itemID FROM deletedItems)",
        "ci.collectionID IN (SELECT collectionID FROM selected_collections)",
    ]
    params.extend(root_ids)
    if collection_item_keys:
        key_placeholders = ",".join("?" for _ in collection_item_keys)
        where.append(f"pi.key IN ({key_placeholders})")
        params.extend(collection_item_keys)
    if papers_only:
        type_placeholders = ",".join("?" for _ in sorted(PAPER_ITEM_TYPES))
        where.append(f"it.typeName IN ({type_placeholders})")
        params.extend(sorted(PAPER_ITEM_TYPES))
    if since_days > 0:
        cutoff = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        where.append("substr(pi.dateModified, 1, 10) >= ?")
        params.append(cutoff)

    query = f"""
        WITH RECURSIVE selected_collections(collectionID) AS (
            SELECT c.collectionID
            FROM collections c
            WHERE c.collectionID IN ({placeholders})
            UNION
            SELECT c2.collectionID
            FROM collections c2
            JOIN selected_collections sc ON c2.parentCollectionID = sc.collectionID
        )
        SELECT DISTINCT
            pi.itemID AS parent_item_id,
            pi.key AS parent_key,
            ai.itemID AS attachment_item_id,
            ai.key AS attachment_key,
            ia.path AS attachment_path,
            (
                SELECT v.value
                FROM itemData d
                JOIN fieldsCombined f ON f.fieldID = d.fieldID
                JOIN itemDataValues v ON v.valueID = d.valueID
                WHERE d.itemID = ai.itemID
                  AND f.fieldName = 'title'
                LIMIT 1
            ) AS attachment_title,
            pi.dateModified AS date_modified
        FROM itemAttachments ia
        JOIN items ai ON ai.itemID = ia.itemID
        JOIN items pi ON pi.itemID = ia.parentItemID
        JOIN itemTypesCombined it ON it.itemTypeID = pi.itemTypeID
        JOIN collectionItems ci ON ci.itemID = pi.itemID
        WHERE {' AND '.join(where)}
        ORDER BY pi.dateModified DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    papers: List[Paper] = []
    best_by_parent: Dict[int, sqlite3.Row] = {}

    def _attachment_score(title: str) -> int:
        t = (title or "").strip().lower()
        if "full text pdf" in t:
            return 3
        if t == "pdf":
            return 2
        return 1

    for row in rows:
        pid = row["parent_item_id"]
        old = best_by_parent.get(pid)
        if old is None:
            best_by_parent[pid] = row
            continue
        if _attachment_score(str(row["attachment_title"] or "")) > _attachment_score(str(old["attachment_title"] or "")):
            best_by_parent[pid] = row

    for row in best_by_parent.values():
        papers.append(
            Paper(
                parent_item_id=row["parent_item_id"],
                parent_key=row["parent_key"],
                attachment_item_id=row["attachment_item_id"],
                attachment_key=row["attachment_key"],
                attachment_path=row["attachment_path"],
                attachment_title=str(row["attachment_title"] or ""),
                date_modified=row["date_modified"],
            )
        )
    for p in papers:
        enrich_metadata(conn, p)
    return papers


def list_collections(conn: sqlite3.Connection) -> List[str]:
    _meta, path_by_id, _name_to_ids, _path_to_id = _build_collection_indexes(conn)
    return sorted(path_by_id.values(), key=lambda s: s.casefold())


def list_papers_in_collection(
    conn: sqlite3.Connection, collection_name: str, limit: int = 500, since_days: int = 0
) -> List[Tuple[str, str, str]]:
    root_ids = _resolve_collection_root_ids(conn, [collection_name])
    if not root_ids:
        return []
    root_placeholders = ",".join("?" for _ in root_ids)
    params: List[object] = list(root_ids)
    where_extra = ""
    if since_days > 0:
        cutoff = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d")
        where_extra = "AND substr(pi.dateModified, 1, 10) >= ?"
        params.append(cutoff)
    params.append(limit)
    rows = conn.execute(
        f"""
        WITH RECURSIVE selected_collections(collectionID) AS (
            SELECT c.collectionID
            FROM collections c
            WHERE c.collectionID IN ({root_placeholders})
            UNION
            SELECT c2.collectionID
            FROM collections c2
            JOIN selected_collections sc ON c2.parentCollectionID = sc.collectionID
        )
        SELECT
            pi.key AS item_key,
            COALESCE(idv.value, pi.key) AS title,
            pi.dateModified AS date_modified
        FROM items pi
        JOIN collectionItems ci ON ci.itemID = pi.itemID
        LEFT JOIN itemData id ON id.itemID = pi.itemID
        LEFT JOIN fieldsCombined f ON f.fieldID = id.fieldID AND f.fieldName = 'title'
        LEFT JOIN itemDataValues idv ON idv.valueID = id.valueID
        WHERE ci.collectionID IN (SELECT collectionID FROM selected_collections)
          AND pi.itemID NOT IN (SELECT itemID FROM deletedItems)
          {where_extra}
          AND EXISTS (
              SELECT 1
              FROM itemAttachments ia
              WHERE ia.parentItemID = pi.itemID
                AND ia.contentType = 'application/pdf'
          )
        GROUP BY pi.itemID
        ORDER BY pi.dateModified DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def _build_collection_indexes(
    conn: sqlite3.Connection,
) -> Tuple[Dict[int, Tuple[str, Optional[int]]], Dict[int, str], Dict[str, List[int]], Dict[str, int]]:
    rows = conn.execute(
        """
        SELECT collectionID, collectionName, parentCollectionID
        FROM collections
        WHERE collectionName IS NOT NULL AND trim(collectionName) <> ''
        """
    ).fetchall()
    meta: Dict[int, Tuple[str, Optional[int]]] = {}
    for cid, cname, parent_id in rows:
        meta[int(cid)] = (str(cname).strip(), int(parent_id) if parent_id is not None else None)

    path_by_id: Dict[int, str] = {}

    def _path(cid: int, visiting: set[int]) -> str:
        if cid in path_by_id:
            return path_by_id[cid]
        name, parent = meta.get(cid, ("", None))
        if not name:
            path_by_id[cid] = ""
            return ""
        if parent is None or parent not in meta or parent in visiting:
            path_by_id[cid] = name
            return name
        visiting.add(cid)
        parent_path = _path(parent, visiting)
        visiting.discard(cid)
        out = f"{parent_path}/{name}" if parent_path else name
        path_by_id[cid] = out
        return out

    for cid in list(meta.keys()):
        _path(cid, set())

    name_to_ids: Dict[str, List[int]] = {}
    path_to_id: Dict[str, int] = {}
    for cid, (name, _parent) in meta.items():
        full_path = path_by_id.get(cid, name)
        if full_path:
            path_to_id[full_path] = cid
        name_to_ids.setdefault(name, []).append(cid)
    return meta, path_by_id, name_to_ids, path_to_id


def _resolve_collection_root_ids(conn: sqlite3.Connection, selections: List[str]) -> List[int]:
    if not selections:
        return []
    _meta, _path_by_id, name_to_ids, path_to_id = _build_collection_indexes(conn)
    resolved: List[int] = []
    seen: set[int] = set()
    for raw in selections:
        sel = str(raw or "").strip()
        if not sel:
            continue
        cid = path_to_id.get(sel)
        if cid is not None and cid not in seen:
            seen.add(cid)
            resolved.append(cid)
            continue
        for nid in name_to_ids.get(sel, []):
            if nid not in seen:
                seen.add(nid)
                resolved.append(nid)
    return resolved


def enrich_metadata(conn: sqlite3.Connection, paper: Paper) -> None:
    field_rows = conn.execute(
        """
        SELECT f.fieldName AS field_name, v.value AS field_value
        FROM itemData d
        JOIN fieldsCombined f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE d.itemID = ?
        """,
        (paper.parent_item_id,),
    ).fetchall()
    fields: Dict[str, str] = {row[0]: row[1] for row in field_rows}

    paper.title = fields.get("title", "")
    paper.translated_title = extract_title_translation_from_extra(fields.get("extra", ""))
    paper.abstract = fields.get("abstractNote", "")
    paper.publication_title = fields.get("publicationTitle", "") or fields.get("proceedingsTitle", "")
    paper.date = normalize_zotero_date(fields.get("date", ""))
    paper.doi = fields.get("DOI", "")
    paper.url = fields.get("url", "")

    item_type_row = conn.execute(
        """
        SELECT it.typeName
        FROM items i
        JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
        WHERE i.itemID = ?
        """,
        (paper.parent_item_id,),
    ).fetchone()
    if item_type_row:
        paper.item_type = item_type_row[0]

    creator_rows = conn.execute(
        """
        SELECT c.lastName, c.firstName
        FROM itemCreators ic
        JOIN creators c ON c.creatorID = ic.creatorID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex ASC
        """,
        (paper.parent_item_id,),
    ).fetchall()
    creators: List[str] = []
    for last_name, first_name in creator_rows:
        joined = " ".join(part for part in [first_name, last_name] if part)
        creators.append(joined.strip())
    paper.creators = ", ".join([c for c in creators if c])

    collection_rows = conn.execute(
        """
        SELECT c.collectionName
        FROM collectionItems ci
        JOIN collections c ON c.collectionID = ci.collectionID
        WHERE ci.itemID = ?
        ORDER BY c.collectionName ASC
        """,
        (paper.parent_item_id,),
    ).fetchall()
    paper.collections = [row[0] for row in collection_rows]


def extract_title_translation_from_extra(extra: str) -> str:
    s = str(extra or "")
    if not s.strip():
        return ""
    for line in s.splitlines():
        m = re.match(r"^\s*titleTranslation\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def normalize_zotero_date(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # 智能归一化 Zotero 常见混合日期：
    # - 2026-01-00 2026-01          -> 2026-01
    # - 2026-02-27 2026-02-27 00:00:00 -> 2026-02-27
    # - 2025-00-00 2025             -> 2025
    candidates = re.findall(r"\b\d{4}(?:-\d{2}){0,2}\b", s)
    if not candidates:
        return s

    def _normalize_one(tok: str) -> Tuple[str, int]:
        parts = tok.split("-")
        year = parts[0]
        month = parts[1] if len(parts) >= 2 else ""
        day = parts[2] if len(parts) >= 3 else ""

        mm = int(month) if month.isdigit() else 0
        dd = int(day) if day.isdigit() else 0

        month_ok = 1 <= mm <= 12
        day_ok = 1 <= dd <= 31

        if day_ok and month_ok:
            return f"{year}-{month}-{day}", 3
        if month_ok:
            return f"{year}-{month}", 2
        return year, 1

    best = ""
    best_score = -1
    seen: set[str] = set()
    for tok in candidates:
        norm, score = _normalize_one(tok)
        if norm in seen:
            continue
        seen.add(norm)
        if score > best_score:
            best = norm
            best_score = score

    return best or s


def resolve_pdf_path(zotero_storage: str, paper: Paper) -> Optional[Path]:
    raw = paper.attachment_path or ""
    if raw.startswith("storage:"):
        filename = raw.split(":", 1)[1]
        path = Path(zotero_storage) / paper.attachment_key / filename
        return path

    if raw.startswith("attachments:"):
        rel = raw.split(":", 1)[1]
        return Path.home() / "Zotero" / rel

    # 兜底：若 path 是绝对路径
    p = Path(raw)
    if p.is_absolute():
        return p
    return None


def truncate_content(content: str, max_chars: int) -> Tuple[str, bool]:
    if max_chars <= 0:
        return content, False
    if len(content) <= max_chars:
        return content, False
    return content[:max_chars], True


def extract_pypdf_document(pdf_path: Path, max_chars: int) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    chunks: List[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if not text.strip():
            continue
        remain = max_chars - total
        if remain <= 0:
            break
        text = text[:remain]
        chunks.append(text)
        total += len(text)
    return ParsedDocument(
        content="\n\n".join(chunks),
        content_format="plain_text",
        parser_name="pypdf",
        truncated=total >= max_chars > 0,
        meta={"cache_hit": False},
    )


def parser_cache_key(paper: Paper, parser_name: str, model_version: str) -> str:
    raw = f"{paper.attachment_key}|{paper.date_modified}|{parser_name}|{model_version}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def parser_cache_dir(cache_root: Path, paper: Paper, parser_name: str, model_version: str) -> Path:
    return cache_root / parser_cache_key(paper, parser_name, model_version)


def load_cached_parsed_document(
    cache_root: Path,
    paper: Paper,
    parser_name: str,
    model_version: str,
    max_chars: int,
) -> Optional[ParsedDocument]:
    cache_dir = parser_cache_dir(cache_root, paper, parser_name, model_version)
    meta_path = cache_dir / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    bundle_md_raw = ""
    if isinstance(meta, dict):
        bundle_md_raw = str(meta.get("bundle_markdown_path") or "").strip()
    md_path = Path(bundle_md_raw) if bundle_md_raw else (cache_dir / "full.md")
    if not md_path.exists():
        return None
    try:
        content = md_path.read_text(encoding="utf-8")
    except Exception:
        return None
    clipped, truncated = truncate_content(content, max_chars)
    merged_meta = dict(meta if isinstance(meta, dict) else {})
    merged_meta["cache_hit"] = True
    merged_meta["cache_key"] = cache_dir.name
    bundle_dir = cache_dir / "bundle"
    if bundle_dir.exists():
        merged_meta["bundle_dir"] = str(bundle_dir)
    return ParsedDocument(
        content=clipped,
        content_format="markdown",
        parser_name=parser_name,
        truncated=truncated,
        meta=merged_meta,
    )


def save_cached_parsed_document(
    cache_root: Path,
    paper: Paper,
    parser_name: str,
    model_version: str,
    content: str,
    meta: Dict[str, Any],
) -> None:
    cache_dir = parser_cache_dir(cache_root, paper, parser_name, model_version)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_meta = dict(meta)
    cache_meta["parser_name"] = parser_name
    cache_meta["content_format"] = "markdown"
    cache_meta["cached_at"] = datetime.now().isoformat(timespec="seconds")
    cache_meta["cache_key"] = cache_dir.name
    bundle_markdown_path = str(cache_meta.get("bundle_markdown_path") or "").strip()
    if not bundle_markdown_path:
        (cache_dir / "full.md").write_text(content, encoding="utf-8")
    else:
        (cache_dir / "full.md").unlink(missing_ok=True)
    (cache_dir / "meta.json").write_text(
        json.dumps(cache_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parser_bundle_dir(cache_root: Path, paper: Paper, parser_name: str, model_version: str) -> Path:
    return parser_cache_dir(cache_root, paper, parser_name, model_version) / "bundle"


def mineru_api_json(
    method: str,
    path_or_url: str,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    url = path_or_url if path_or_url.startswith("http") else f"{MINERU_API_BASE}{path_or_url}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    obj = json.loads(body)
    if not isinstance(obj, dict):
        raise RuntimeError("MinerU 返回了非对象响应")
    code = obj.get("code")
    if code not in (0, 200):
        msg = obj.get("msg") or obj.get("message") or "未知错误"
        raise RuntimeError(f"MinerU API 调用失败: code={code}, msg={msg}")
    return obj


def http_request_bytes(
    method: str,
    url: str,
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 120,
) -> Tuple[int, str, bytes]:
    parts = urllib.parse.urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc, timeout=timeout)
    req_headers = dict(headers or {})
    if body is not None and "Content-Length" not in req_headers:
        req_headers["Content-Length"] = str(len(body))
    if "User-Agent" not in req_headers:
        req_headers["User-Agent"] = "zotero-ai-obsidian-flow/1.0"
    try:
        conn.putrequest(method.upper(), path)
        for key, value in req_headers.items():
            conn.putheader(key, value)
        conn.endheaders()
        if body is not None:
            conn.send(body)
        resp = conn.getresponse()
        payload = resp.read()
        return int(resp.status), str(resp.reason), payload
    finally:
        conn.close()


def mineru_upload_file(upload_url: str, pdf_path: Path, timeout: int = 300) -> None:
    data = pdf_path.read_bytes()
    status, reason, payload = http_request_bytes("PUT", upload_url, body=data, timeout=timeout)
    if status >= 400:
        detail = payload.decode("utf-8", errors="ignore")[:300].strip()
        raise RuntimeError(f"MinerU 上传失败: HTTP {status} {reason}; {detail}")


def mineru_download_full_markdown(full_zip_url: str) -> str:
    last_error = ""
    for _ in range(3):
        try:
            payload = mineru_download_zip_payload(full_zip_url)
            return payload_to_markdown(payload)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1.0)
    raise RuntimeError(f"MinerU 下载 full.zip 失败: {last_error}")


def mineru_download_zip_payload(full_zip_url: str) -> bytes:
    status, reason, payload = http_request_bytes(
        "GET",
        full_zip_url,
        headers={"Accept": "application/zip"},
        timeout=120,
    )
    if status >= 400:
        detail = payload.decode("utf-8", errors="ignore")[:300].strip()
        raise RuntimeError(f"HTTP {status} {reason}; {detail}")
    return payload


def payload_to_markdown(zip_payload: bytes) -> str:
    with ZipFile(io.BytesIO(zip_payload)) as zf:
        names = zf.namelist()
        target = next((n for n in names if n.endswith("/full.md")), None)
        if target is None and "full.md" in names:
            target = "full.md"
        if target is None:
            raise RuntimeError("MinerU full.zip 中未找到 full.md")
        return zf.read(target).decode("utf-8", errors="ignore")


def extract_bundle_payload(zip_payload: bytes, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(io.BytesIO(zip_payload)) as zf:
        zf.extractall(output_dir)
        names = zf.namelist()
    target = next((n for n in names if n.endswith("/full.md")), None)
    if target is None and "full.md" in names:
        target = "full.md"
    if target is None:
        raise RuntimeError("MinerU full.zip 中未找到 full.md")
    return output_dir / target


def mineru_extract_bundle(full_zip_url: str, output_dir: Path) -> Path:
    last_error = ""
    for _ in range(3):
        try:
            payload = mineru_download_zip_payload(full_zip_url)
            return extract_bundle_payload(payload, output_dir)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1.0)
    raise RuntimeError(f"MinerU 解压 full.zip 失败: {last_error}")


def mineru_extract_result_entry(result_obj: Dict[str, Any], data_id: str) -> Dict[str, Any]:
    data = result_obj.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("MinerU 返回缺少 data 字段")
    extract_result = data.get("extract_result")
    if not isinstance(extract_result, list):
        raise RuntimeError("MinerU 返回缺少 extract_result 列表")
    for item in extract_result:
        if isinstance(item, dict) and str(item.get("data_id") or "") == data_id:
            return item
    raise RuntimeError("MinerU 结果中未找到目标文件")


def mineru_wait_for_result(token: str, batch_id: str, data_id: str) -> Dict[str, Any]:
    deadline = time.monotonic() + MINERU_POLL_TIMEOUT_SEC
    last_state = ""
    while time.monotonic() < deadline:
        obj = mineru_api_json("GET", f"/extract-results/batch/{batch_id}", token, timeout=60)
        item = mineru_extract_result_entry(obj, data_id)
        state = str(item.get("state") or "").strip().lower()
        if state:
            last_state = state
        if state in {"done", "success", "completed"}:
            return item
        if state in {"failed", "error"}:
            msg = item.get("err_msg") or item.get("message") or "未知错误"
            raise RuntimeError(f"MinerU 解析失败: {msg}")
        time.sleep(MINERU_POLL_INTERVAL_SEC)
    raise RuntimeError(f"MinerU 解析超时，最后状态: {last_state or 'unknown'}")


def extract_mineru_document(
    pdf_path: Path,
    paper: Paper,
    max_chars: int,
    cache_root: Path,
    token: str,
    model_version: str,
    language: str,
) -> ParsedDocument:
    cached = load_cached_parsed_document(cache_root, paper, "mineru", model_version, max_chars)
    if cached is not None:
        return cached

    data_id = f"{paper.attachment_key}-{int(time.time())}"
    payload = {
        "model_version": model_version,
        "language": language,
        "enable_formula": True,
        "enable_table": True,
        "files": [
            {
                "name": pdf_path.name,
                "is_ocr": False,
                "data_id": data_id,
            }
        ]
    }
    created = mineru_api_json("POST", "/file-urls/batch", token, payload=payload, timeout=60)
    data = created.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("MinerU 创建任务失败：缺少 data")
    batch_id = str(data.get("batch_id") or "").strip()
    file_urls = data.get("file_urls")
    if not batch_id or not isinstance(file_urls, list) or not file_urls:
        raise RuntimeError("MinerU 创建任务失败：缺少 batch_id 或 file_urls")
    upload_url = str(file_urls[0] or "").strip()
    if not upload_url:
        raise RuntimeError("MinerU 创建任务失败：缺少上传地址")

    mineru_upload_file(upload_url, pdf_path)
    item = mineru_wait_for_result(token, batch_id, data_id)
    full_zip_url = str(item.get("full_zip_url") or "").strip()
    if not full_zip_url:
        raise RuntimeError("MinerU 返回缺少 full_zip_url")
    upload_host = urllib.parse.urlsplit(upload_url).netloc
    download_host = urllib.parse.urlsplit(full_zip_url).netloc
    try:
        zip_payload = mineru_download_zip_payload(full_zip_url)
        full_md = payload_to_markdown(zip_payload)
        bundle_dir = parser_bundle_dir(cache_root, paper, "mineru", model_version)
        bundle_markdown_path = extract_bundle_payload(zip_payload, bundle_dir)
    except Exception as exc:
        raise RuntimeError(
            f"MinerU 下载解析结果失败: batch={batch_id}, data={data_id}, "
            f"upload_host={upload_host}, download_host={download_host}, error={exc}"
        ) from exc
    save_cached_parsed_document(
        cache_root=cache_root,
        paper=paper,
        parser_name="mineru",
        model_version=model_version,
        content=full_md,
        meta={
            "batch_id": batch_id,
            "data_id": data_id,
            "full_zip_url": full_zip_url,
            "upload_host": upload_host,
            "download_host": download_host,
            "bundle_dir": str(bundle_dir),
            "bundle_markdown_path": str(bundle_markdown_path),
            "cache_hit": False,
        },
    )
    clipped, truncated = truncate_content(full_md, max_chars)
    return ParsedDocument(
        content=clipped,
        content_format="markdown",
        parser_name="mineru",
        truncated=truncated,
        meta={
            "batch_id": batch_id,
            "data_id": data_id,
            "full_zip_url": full_zip_url,
            "upload_host": upload_host,
            "download_host": download_host,
            "bundle_dir": str(bundle_dir),
            "bundle_markdown_path": str(bundle_markdown_path),
            "cache_hit": False,
        },
    )


def extract_document_content(
    pdf_path: Path,
    paper: Paper,
    pdf_parser: str,
    max_chars: int,
    cache_root: Path,
    mineru_token: str,
    mineru_model_version: str,
    mineru_language: str,
) -> ParsedDocument:
    if pdf_parser == "pypdf":
        return extract_pypdf_document(pdf_path, max_chars)

    if pdf_parser == "mineru":
        if not mineru_token:
            raise RuntimeError(f"缺少 MinerU API Token，请在 {ENV_PATH} 中配置 MINERU_API_TOKEN")
        return extract_mineru_document(
            pdf_path=pdf_path,
            paper=paper,
            max_chars=max_chars,
            cache_root=cache_root,
            token=mineru_token,
            model_version=mineru_model_version,
            language=mineru_language,
        )

    if mineru_token:
        try:
            doc = extract_mineru_document(
                pdf_path=pdf_path,
                paper=paper,
                max_chars=max_chars,
                cache_root=cache_root,
                token=mineru_token,
                model_version=mineru_model_version,
                language=mineru_language,
            )
            doc.meta.setdefault("fallback_reason", "")
            return doc
        except Exception as exc:
            fallback = extract_pypdf_document(pdf_path, max_chars)
            fallback.meta["fallback_reason"] = str(exc)
            fallback.meta["cache_hit"] = False
            return fallback

    fallback = extract_pypdf_document(pdf_path, max_chars)
    fallback.meta["fallback_reason"] = "MINERU_API_TOKEN 未配置"
    return fallback


def image_refs_from_markdown(markdown: str) -> List[Tuple[str, int]]:
    refs: List[Tuple[str, int]] = []
    for idx, line in enumerate(markdown.splitlines()):
        for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", line):
            refs.append((match.group(1).strip(), idx))
    return refs


def score_markdown_image(markdown_lines: List[str], line_idx: int) -> int:
    start = max(0, line_idx - 3)
    end = min(len(markdown_lines), line_idx + 4)
    score = 0
    for offset, line in enumerate(markdown_lines[start:end], start=start):
        text = line.lower()
        if "fig." in text or "figure" in text:
            distance = abs(offset - line_idx)
            score = max(score, 100 - distance * 10)
    return score


def select_multimodal_images(parsed_doc: ParsedDocument, max_images: int = MAX_MULTIMODAL_IMAGES) -> List[Path]:
    if parsed_doc.parser_name != "mineru" or parsed_doc.content_format != "markdown":
        return []
    bundle_dir_raw = str(parsed_doc.meta.get("bundle_dir") or "").strip()
    bundle_md_raw = str(parsed_doc.meta.get("bundle_markdown_path") or "").strip()
    if not bundle_dir_raw or not bundle_md_raw:
        return []

    bundle_dir = Path(bundle_dir_raw)
    bundle_md_path = Path(bundle_md_raw)
    if not bundle_dir.exists() or not bundle_md_path.exists():
        return []

    markdown_lines = parsed_doc.content.splitlines()
    ranked: List[Tuple[int, int, Path]] = []
    seen: set[str] = set()
    for ref, line_idx in image_refs_from_markdown(parsed_doc.content):
        clean_ref = ref.strip().strip("<>").strip()
        if not clean_ref or "://" in clean_ref:
            continue
        image_path = (bundle_md_path.parent / clean_ref).resolve()
        if not image_path.exists() or not image_path.is_file():
            continue
        key = str(image_path)
        if key in seen:
            continue
        seen.add(key)
        score = score_markdown_image(markdown_lines, line_idx)
        ranked.append((score, line_idx, image_path))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, _, path in ranked[:max_images]]


def image_path_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(image_path))
    mime_type = mime_type or "application/octet-stream"
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def build_openai_user_content(user_prompt: str, image_paths: List[Path]) -> List[Dict[str, object]]:
    content: List[Dict[str, object]] = [{"type": "text", "text": user_prompt}]
    if image_paths:
        content.append(
            {
                "type": "text",
                "text": f"下面附上从论文中筛选出的 {len(image_paths)} 张关键配图，请结合图像内容理解图表、显微图和流程图。",
            }
        )
        for image_path in image_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_path_to_data_url(image_path)},
                }
            )
    return content


def should_fallback_to_text_on_image_error(exc: Exception) -> bool:
    text = str(exc).lower()
    hints = [
        "image",
        "vision",
        "multimodal",
        "image_url",
        "does not support",
        "not support",
        "unsupported",
        "content part",
        "invalid type",
    ]
    return any(hint in text for hint in hints)


def call_ai(
    provider: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    provider_specs: Dict[str, Dict[str, object]],
    enable_thinking: bool = False,
    image_paths: Optional[List[Path]] = None,
) -> Tuple[str, Dict[str, Any]]:
    spec = provider_specs.get(provider, {})
    provider_type = str(spec.get("provider_type", "openai_compatible"))

    if provider_type == "openai_compatible":
        from openai import OpenAI

        base_url = spec.get("base_url")
        if base_url:
            client = OpenAI(api_key=api_key, base_url=str(base_url))
        else:
            client = OpenAI(api_key=api_key)
        base_req: Dict[str, object] = {
            "model": model,
            "temperature": 0.2,
        }
        if enable_thinking:
            if provider == "qwen":
                # DashScope OpenAI 兼容：通过 extra_body.enable_thinking 开启思考
                base_req["extra_body"] = {"enable_thinking": True}
            elif provider == "deepseek":
                # DeepSeek OpenAI SDK：通过 extra_body.thinking 开启思考
                base_req["extra_body"] = {"thinking": {"type": "enabled"}}
            elif provider == "openai":
                # OpenAI Chat Completions：通过 reasoning_effort 提升推理深度
                base_req["reasoning_effort"] = "high"

        text_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if image_paths:
            multimodal_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_openai_user_content(user_prompt, image_paths)},
            ]
            try:
                resp = client.chat.completions.create(**{**base_req, "messages": multimodal_messages})
                return (resp.choices[0].message.content or "").strip(), {
                    "used_images": True,
                    "image_count": len(image_paths),
                    "fell_back_to_text": False,
                }
            except Exception as exc:
                if not should_fallback_to_text_on_image_error(exc):
                    raise
                resp = client.chat.completions.create(**{**base_req, "messages": text_messages})
                return (resp.choices[0].message.content or "").strip(), {
                    "used_images": False,
                    "image_count": len(image_paths),
                    "fell_back_to_text": True,
                    "image_fallback_reason": str(exc),
                }

        resp = client.chat.completions.create(**{**base_req, "messages": text_messages})
        return (resp.choices[0].message.content or "").strip(), {
            "used_images": False,
            "image_count": 0,
            "fell_back_to_text": False,
        }

    if provider_type == "gemini":
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        m = genai.GenerativeModel(model)
        resp = m.generate_content(
            [
                f"系统要求：\n{system_prompt}",
                f"用户要求：\n{user_prompt}",
            ],
            generation_config={"temperature": 0.2},
        )
        return (resp.text or "").strip(), {
            "used_images": False,
            "image_count": 0,
            "fell_back_to_text": bool(image_paths),
            "image_fallback_reason": "Gemini 图像输入尚未接入当前主流程" if image_paths else "",
        }

    raise ValueError(f"不支持的 provider: {provider}")


def map_existing_dirs_by_name(obsidian_root: Path) -> Dict[str, Path]:
    all_dirs = [d for d in obsidian_root.rglob("*") if d.is_dir()]
    by_name: Dict[str, Path] = {}
    # 同名目录时优先更短路径，减少“命中深层目录”的意外
    for d in sorted(all_dirs, key=lambda p: (len(p.parts), str(p).lower())):
        by_name.setdefault(d.name, d)
    return by_name


def choose_existing_folder_with_ai(
    provider: str,
    model: str,
    api_key: str,
    provider_specs: Dict[str, Dict[str, object]],
    suggested_folder: str,
    paper: Paper,
    existing_dir_names: List[str],
) -> Optional[str]:
    """
    二次目录决策：让 AI 在“已有目录名”与“建议目录”之间做匹配。
    返回命中的已有目录名；若不命中则返回 None（走新建目录或默认目录）。
    """
    cleaned = safe_folder_name(suggested_folder)
    if not cleaned:
        return None
    if not existing_dir_names:
        return None

    # 控制上下文大小，避免目录过多导致提示过长
    candidate_names = sorted({n for n in existing_dir_names if n and n.strip()})[:300]
    if not candidate_names:
        return None

    system_prompt = (
        "你是目录选择助手。任务是将“建议目录”与“已有目录列表”对齐。"
        "若已有目录中存在语义最接近且可复用的目录，返回 EXISTING；否则返回 NEW。"
        "只能输出一行，禁止输出其他内容。"
    )
    user_prompt = textwrap.dedent(
        f"""
        论文标题：{paper.title}
        论文摘要：{paper.abstract[:1200]}
        Zotero合集：{', '.join(paper.collections) if paper.collections else '无'}
        建议目录：{cleaned}

        已有目录列表（仅目录名）：
        {', '.join(candidate_names)}

        输出格式（二选一，仅一行）：
        EXISTING: <已有目录名>
        NEW: <目录名>
        """
    ).strip()
    raw, _ = call_ai(provider, model, api_key, system_prompt, user_prompt, provider_specs)
    raw = raw.strip()
    m = re.match(r"^\s*EXISTING\s*[:：]\s*(.+?)\s*$", raw, flags=re.I)
    if not m:
        return None
    picked = m.group(1).strip()
    return picked if picked in set(candidate_names) else None


def check_model_connectivity(
    provider: str,
    model: str,
    api_key: str,
    provider_specs: Dict[str, Dict[str, object]],
) -> None:
    """
    Dry-run 模式下仅做一次最小化连通性校验，不触发论文分析。
    """
    ping, _ = call_ai(
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt="你是连通性测试助手。请仅回复 OK。",
        user_prompt="连通性测试：只回复 OK",
        provider_specs=provider_specs,
        enable_thinking=False,
    )
    if not ping.strip():
        raise RuntimeError("模型连通性测试失败：返回为空")


def check_mineru_connectivity(token: str, model_version: str, language: str) -> None:
    """
    通过官方 file-urls/batch 接口做最小化联通性校验。
    该检查仅申请上传链接，不上传文件，因此不会进入正式解析流程。
    """
    if not token:
        raise RuntimeError(f"缺少 MinerU API Token，请在 {ENV_PATH} 中配置 MINERU_API_TOKEN")
    probe_id = f"dry-run-probe-{int(time.time())}"
    payload = {
        "model_version": model_version,
        "language": language,
        "enable_formula": True,
        "enable_table": True,
        "files": [
            {
                "name": "connectivity-check.pdf",
                "data_id": probe_id,
            }
        ],
    }
    obj = mineru_api_json("POST", "/file-urls/batch", token, payload=payload, timeout=60)
    data = obj.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("MinerU 连通性测试失败：响应缺少 data")
    batch_id = str(data.get("batch_id") or "").strip()
    file_urls = data.get("file_urls")
    if not batch_id or not isinstance(file_urls, list) or not file_urls or not str(file_urls[0] or "").strip():
        raise RuntimeError("MinerU 连通性测试失败：未拿到有效上传链接")


def safe_folder_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", " ", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:60] if cleaned else "未分类论文"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", " ", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:48] if cleaned else "未命名论文"


def parse_ai_output(text: str) -> Tuple[str, str]:
    folder = ""
    md = text or ""

    # 先提取建议目录（只取首次命中的单行内容）
    m = re.search(r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*建议目录\s*(?:\*\*)?\s*[:：]\s*(.+?)\s*$", md, flags=re.M)
    if m:
        folder = m.group(1).strip()
        # 去掉可能的行尾 markdown 标记
        folder = re.sub(r"\s*[*_`]+\s*$", "", folder).strip()

    # 无条件删除“建议目录：...”行，避免残留到最终 Obsidian 正文
    md = re.sub(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*建议目录\s*(?:\*\*)?\s*[:：].*$\n?",
        "",
        md,
        flags=re.M,
    )

    # 若模型在前面多输出了说明文字，优先从第一个一级标题开始保留正文
    h1 = re.search(r"^\s*#\s+.+$", md, flags=re.M)
    if h1:
        md = md[h1.start():]
    return folder, md.strip()


def normalize_markdown_for_obsidian(md: str) -> str:
    """
    尽量修复 Obsidian 中常见的 Markdown 表格渲染问题：
    1) 确保表格前后有空行
    2) 避免“列表项 + 表格”导致表格不渲染（移除该列表标记）
    """
    lines = md.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")

        if not is_table_line:
            out.append(line)
            i += 1
            continue

        # 收集连续表格块
        j = i
        block: List[str] = []
        while j < len(lines):
            s = lines[j].strip()
            if s.startswith("|") and s.endswith("|"):
                block.append(lines[j])
                j += 1
            else:
                break

        # 若上一行是列表项，且形如“ - xxx: ”，移除列表标记避免表格被吞
        if out:
            prev = out[-1].strip()
            if (
                (prev.startswith("- ") or prev.startswith("* "))
                and (prev.endswith(":") or prev.endswith("："))
            ):
                out[-1] = out[-1].replace("- ", "", 1).replace("* ", "", 1)

        # 表格前空行
        if out and out[-1].strip():
            out.append("")
        out.extend(block)
        # 表格后空行（如果后续还有非空内容）
        if j < len(lines) and lines[j].strip():
            out.append("")

        i = j

    # 压缩多余空行（最多保留一个空行）
    compact: List[str] = []
    blank = False
    for ln in out:
        cur_blank = not ln.strip()
        if cur_blank and blank:
            continue
        compact.append(ln)
        blank = cur_blank
    return "\n".join(compact).strip()


def choose_folder(
    obsidian_root: Path,
    paper: Paper,
    ai_folder: str,
    note_md: str,
    dir_names: Optional[Dict[str, Path]] = None,
) -> Path:
    # 优先命中 Zotero collection 同名目录
    if dir_names is None:
        dir_names = map_existing_dirs_by_name(obsidian_root)

    for cname in paper.collections:
        if cname in dir_names:
            return dir_names[cname]

    # 再采用 AI 建议目录
    ai_folder = safe_folder_name(ai_folder)
    generic = {"未分类", "其他", "默认", "论文", "未分类论文", "文献", "研究"}
    if ai_folder and ai_folder not in generic:
        return obsidian_root / ai_folder

    # 最后兜底到固定目录
    return obsidian_root / "论文精读"


def display_rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def display_short_path(path: Path, root: Path, max_name_len: int = 36) -> str:
    try:
        rel = path.relative_to(root)
    except Exception:
        rel = path
    parent = rel.parent
    name = rel.name
    if len(name) > max_name_len:
        suffix = rel.suffix
        stem = rel.stem
        keep = max(8, max_name_len - len(suffix) - 3)
        name = f"{stem[:keep]}...{suffix}"
    return str(parent / name) if str(parent) != "." else name


def build_prompt(paper: Paper, template_md: str, parsed_doc: ParsedDocument) -> Tuple[str, str]:
    system_prompt = (
        "你是资深科研导师和研究助理。你的输出必须严谨、结构化、中文表达清晰。"
        "对论文未明确给出的信息必须标注‘论文未明确说明’。"
        "优先利用标题层级、表格、公式和列表结构理解论文内容，不要把版面噪声当成事实。"
    )

    translated_line = f"\n        - 标题翻译: {paper.translated_title}" if paper.translated_title else ""
    metadata_block = textwrap.dedent(
        f"""
        【论文元数据】
        - 标题: {paper.title}
        {translated_line}
        - 作者: {paper.creators}
        - 期刊/会议: {paper.publication_title}
        - 年份/日期: {paper.date}
        - DOI: {paper.doi}
        - URL: {paper.url}
        - Zotero条目Key: {paper.parent_key}
        - Zotero合集: {', '.join(paper.collections) if paper.collections else '无'}
        """
    ).strip()

    if parsed_doc.content_format == "markdown":
        source_heading = "【论文结构化解析结果（Markdown）】"
        source_body = f"````markdown\n{parsed_doc.content}\n````"
    else:
        source_heading = "【论文正文摘录（PDF文本）】"
        source_body = parsed_doc.content

    user_prompt = textwrap.dedent(
        f"""
        你需要阅读下面给出的论文内容，并严格按模板输出论文深度分析。

        输出必须满足 Obsidian 可渲染的 Markdown 规范：
        1) 所有表格前后必须空一行
        2) 表格不能嵌套在列表中（不能写在 - 或 * 下面）
        3) 表格必须包含表头分隔行（如 |---|---|）
        4) 表格列使用标准 GitHub Markdown 语法（如 | 列1 | 列2 |）
        5) 禁止输出非标准表格写法
        6) 数学公式请使用 LaTeX：行内公式使用一对 $ 包裹，独立公式块使用一对 $$ 包裹
        7) 若附带论文配图输入，请结合图像内容理解图表、显微图和流程图

        先输出一行：
        建议目录：<一个短目录名，体现论文研究方向，例如“磁纳米测温”/“AI医疗”>

        然后从 “# 1. 基础信息” 开始，完整按模板结构输出 Markdown，不要漏标题层级。

        模板如下：
        {template_md}

        {metadata_block}

        {source_heading}
        {source_body}
        """
    ).strip()
    return system_prompt, user_prompt


def load_state(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def zotero_utc_to_beijing(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return text
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return text


def format_publication_month(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d{4})[/-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})$", text)
    if m:
        return m.group(1)
    return text


def compose_note_markdown(
    paper: Paper,
    note_md: str,
    pdf_path: Path,
    folder_rel: str,
    model: str,
    rank_info: Optional[Dict[str, str]] = None,
) -> str:
    impact_factor = ""
    tag_sci = ""
    tag_sciup = ""
    if rank_info:
        if_val = str(rank_info.get("sciif", "") or "").strip()
        sci_val = str(rank_info.get("sci", "") or "").strip()
        cas_val = str(rank_info.get("sciUp", "") or "").strip()
        if if_val:
            impact_factor = if_val
        if sci_val:
            tag_sci = f"SCI{re.sub(r'\\s+', '', sci_val)}"
        if cas_val:
            tag_sciup = f"中科院{re.sub(r'\\s+', '', cas_val)}"

    rank_tags = [t for t in (tag_sci, tag_sciup) if t]
    tags = ["AI精读"] + [c for c in paper.collections if c] + rank_tags
    unique_tags = []
    seen = set()
    for t in tags:
        raw = str(t).strip()
        # 清理历史格式：例如 sciif:37.6 / sci:Q1 / sciup:xx
        low = raw.lower()
        if low.startswith("sciif:") or low.startswith("sci:") or low.startswith("sciup:"):
            continue
        t = raw
        if t not in seen:
            unique_tags.append(t)
            seen.add(t)

    frontmatter = {
        "标题": paper.title,
    }
    if paper.translated_title:
        frontmatter["标题翻译"] = paper.translated_title
    frontmatter.update({
        "ZoteroKey": paper.parent_key,
        "doi": paper.doi,
        "作者": paper.creators,
        "期刊/会议": paper.publication_title,
        "发表日期": format_publication_month(paper.date),
        "文件夹": folder_rel,
        "AI模型": model,
        "AI精读日期": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tags": unique_tags,
    })
    if impact_factor:
        frontmatter["影响因子"] = impact_factor

    lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            escaped = str(v).replace('"', "'")
            lines.append(f"{k}: \"{escaped}\"")
    lines.append("---")
    lines.append("")
    lines.append(note_md.strip())
    lines.append("")
    lines.append("## 原文链接")
    if paper.url:
        lines.append(f"- URL: {paper.url}")
    if paper.doi:
        lines.append(f"- DOI: {paper.doi}")
    lines.append(f"- Zotero Key: {paper.parent_key}")
    return "\n".join(lines)


def validate_scan_scope(args: argparse.Namespace) -> None:
    if args.collection_item_key and not args.collection:
        raise RuntimeError("使用 --collection-item-key 时，必须同时提供 --collection")
    if args.parent_item_key:
        return
    # 默认要求显式范围，避免无意全库扫描
    if args.collection:
        return
    if args.allow_global_scan:
        return
    raise RuntimeError(
        "请指定扫描范围：使用 --collection 指定 Zotero 目录；"
        "若确实要全库扫描请加 --allow-global-scan"
    )


def remove_path_safely(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except Exception:
        pass


def format_pdf_parse_result(parsed_doc: ParsedDocument) -> str:
    parser_name = parsed_doc.parser_name
    fallback_reason = str(parsed_doc.meta.get("fallback_reason") or "").strip()
    if parser_name == "pypdf" and fallback_reason:
        return "成功（已自动回退到 pypdf）"
    return "成功"


def format_multimodal_result(
    parsed_doc: ParsedDocument,
    provider_type: str,
    image_paths: List[Path],
    ai_meta: Dict[str, Any],
) -> str:
    if ai_meta.get("used_images"):
        return f"成功（已发送 {ai_meta.get('image_count', 0)} 张关键配图）"
    if ai_meta.get("fell_back_to_text") and ai_meta.get("image_count"):
        return "未启用（已自动回退到纯文本模式）"
    if provider_type != "openai_compatible":
        return "未启用（当前 provider 暂不接入图像输入）"
    if parsed_doc.parser_name != "mineru":
        return "未启用（当前解析结果无可用图片）"
    if not image_paths:
        return "未启用（未找到合适配图）"
    return "未启用"


def run() -> int:
    args = parse_args()
    validate_scan_scope(args)
    provider_specs = resolve_provider_specs(args.provider_config)
    if args.provider not in provider_specs:
        raise RuntimeError(f"未找到供应商: {args.provider}，请先在配置中添加")
    model = args.model or default_model_for(args.provider, provider_specs)
    api_key = get_api_key(args.provider, args.api_key, args.provider_config, provider_specs)
    if args.enable_thinking:
        if args.provider in {"qwen", "deepseek"}:
            print(f"[INFO] 已开启深度思考参数（provider={args.provider}）")
        else:
            print(f"[WARN] 当前供应商 {args.provider} 未配置深度思考参数注入，将按普通模式调用")

    template_md = load_template(args.template)
    state_file = Path(args.state_file)
    legacy_parser_cache_root = state_file.parent / "parser_cache"
    if legacy_parser_cache_root.exists():
        remove_path_safely(legacy_parser_cache_root)
    state = load_state(state_file)
    dotenv_values = load_dotenv_values()
    easy_secret_key = (dotenv_values.get("SecretKey") or "").strip()
    mineru_token = (dotenv_values.get("MINERU_API_TOKEN") or "").strip()
    if easy_secret_key:
        print("[INFO] 检测到 SecretKey，已启用期刊等级自动检索（sciif/sci/sciUp）")
    if args.pdf_parser == "mineru" and not mineru_token:
        raise RuntimeError(f"缺少 MinerU API Token，请在 {ENV_PATH} 中配置 MINERU_API_TOKEN")

    papers: List[Paper] = []
    # “处理数量上限”按实际处理数计算，而不是候选检索数。
    # 因此在非 force 且非单篇指定时，适度放大候选抓取范围，避免前几篇都被 SKIP 导致处理 0 篇。
    fetch_limit = args.limit
    if not args.force and not args.collection_item_key:
        fetch_limit = max(args.limit * 10, args.limit + 20)
    temp_db_path = copy_db_to_temp(args.zotero_db)
    try:
        conn = sqlite3.connect(temp_db_path)
        if args.collection:
            papers = fetch_papers_by_collection(
                conn,
                args.since_days,
                args.collection,
                fetch_limit,
                args.collection_item_key,
                papers_only=not args.collection_all_types,
            )
        elif args.parent_item_key:
            key_fetch_limit = max(fetch_limit, len(args.parent_item_key))
            papers = fetch_candidate_papers(conn, args.since_days, args.parent_item_key, key_fetch_limit)
        else:
            papers = fetch_candidate_papers(conn, args.since_days, None, fetch_limit)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        Path(temp_db_path).unlink(missing_ok=True)

    if not papers:
        print("未找到符合条件的论文。")
        return 0

    obsidian_root = Path(args.obsidian_root)
    obsidian_root.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("[DRY-RUN] 模式开启：仅预演流程，不执行论文分析、不写入 Obsidian。")
        check_model_connectivity(args.provider, model, api_key, provider_specs)
        print(f"[DRY-RUN] 模型连通性测试通过: provider={args.provider}, model={model}")
        if args.pdf_parser != "pypdf":
            check_mineru_connectivity(
                token=mineru_token,
                model_version=args.mineru_model_version,
                language=args.mineru_language,
            )
            print(
                "[DRY-RUN] MinerU 连通性测试通过: "
                f"parser={args.pdf_parser}, model_version={args.mineru_model_version}, language={args.mineru_language}"
            )

    processed_count = 0
    with tempfile.TemporaryDirectory(prefix="mineru_parser_cache_") as parser_cache_tmp:
        parser_cache_root = Path(parser_cache_tmp)
        for p in papers:
            if processed_count >= args.limit:
                break
            marker = f"{p.parent_key}:{zotero_utc_to_beijing(p.date_modified)}"
            # 去重按 parent_key 为主，避免“仅做 PDF 批注/附件时间变化”触发重复精读。
            # 旧版本 state value 可能是 key:dateModified，这里仅检查 key 是否存在以保持兼容。
            if not args.force and p.parent_key in state:
                print(f"[SKIP] 条目 {p.parent_key} 已经被处理过（如需重新生成，请在左侧勾选 Force）")
                continue

            pdf_path = resolve_pdf_path(args.zotero_storage, p)
            if not pdf_path or not pdf_path.exists():
                print(f"[WARN] 找不到 PDF，跳过: {p.parent_key} {pdf_path}")
                continue

            print(f"[INFO] 处理论文: {p.title or p.parent_key}")
            folder_suggestion = ""
            note_md = ""
            cache_dir_to_cleanup: Optional[Path] = None
            if not args.dry_run:
                parsed_doc = extract_document_content(
                    pdf_path=pdf_path,
                    paper=p,
                    pdf_parser=args.pdf_parser,
                    max_chars=args.max_pdf_chars,
                    cache_root=parser_cache_root,
                    mineru_token=mineru_token,
                    mineru_model_version=args.mineru_model_version,
                    mineru_language=args.mineru_language,
                )
                if parsed_doc.parser_name == "mineru":
                    cache_dir_to_cleanup = parser_cache_dir(
                        parser_cache_root,
                        p,
                        "mineru",
                        args.mineru_model_version,
                    )
                print(f"[INFO] PDF 解析方法: {parsed_doc.parser_name}")
                print(f"[INFO] PDF 解析结果: {format_pdf_parse_result(parsed_doc)}")
                if not parsed_doc.content.strip():
                    print(f"[WARN] PDF 无可提取文本，跳过: {pdf_path}")
                    continue

                system_prompt, user_prompt = build_prompt(p, template_md, parsed_doc)
                spec = provider_specs.get(args.provider, {})
                provider_type = str(spec.get("provider_type", "openai_compatible"))
                image_paths: List[Path] = []
                if provider_type == "openai_compatible":
                    image_paths = select_multimodal_images(parsed_doc, max_images=MAX_MULTIMODAL_IMAGES)

                ai_raw, ai_meta = call_ai(
                    args.provider,
                    model,
                    api_key,
                    system_prompt,
                    user_prompt,
                    provider_specs,
                    enable_thinking=args.enable_thinking,
                    image_paths=image_paths,
                )
                print(
                    "[INFO] 多模态图像输入: "
                    f"{format_multimodal_result(parsed_doc, provider_type, image_paths, ai_meta)}"
                )
                folder_suggestion, note_md = parse_ai_output(ai_raw)
                note_md = normalize_markdown_for_obsidian(note_md)

            existing_dir_map = map_existing_dirs_by_name(obsidian_root)
            collection_hit = next((existing_dir_map[c] for c in p.collections if c in existing_dir_map), None)
            target_folder = choose_folder(obsidian_root, p, folder_suggestion, note_md, dir_names=existing_dir_map)
            if not args.dry_run and folder_suggestion.strip() and collection_hit is None:
                picked_existing_name = choose_existing_folder_with_ai(
                    provider=args.provider,
                    model=model,
                    api_key=api_key,
                    provider_specs=provider_specs,
                    suggested_folder=folder_suggestion,
                    paper=p,
                    existing_dir_names=list(existing_dir_map.keys()),
                )
                if picked_existing_name:
                    target_folder = existing_dir_map[picked_existing_name]
                    print(f"[INFO] 目录二次决策：命中已有目录 -> {display_rel_path(target_folder, obsidian_root)}")
            folder_rel = str(target_folder.relative_to(obsidian_root))
            filename_base = safe_filename(p.title or p.parent_key)
            out_file = target_folder / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{filename_base}.md"
            out_file_display = display_short_path(out_file, obsidian_root)

            if args.dry_run:
                print("[DRY-RUN] ===== 预演日志（不会实际执行分析/不会写文件） =====")
                print(f"[DRY-RUN] 将处理论文: {p.parent_key}")
                print(f"[DRY-RUN] PDF 路径: {pdf_path}")
                print(f"[DRY-RUN] 将写入: {out_file_display}")
                print(f"[DRY-RUN] 目录决策: collection/规则推断 -> {display_rel_path(target_folder, obsidian_root)}")
            else:
                rank_info: Dict[str, str] = {}
                if easy_secret_key and p.publication_title.strip():
                    try:
                        rank_info = fetch_easyscholar_rank_info(easy_secret_key, p.publication_title)
                        if rank_info:
                            parts = []
                            if rank_info.get("sciif"):
                                parts.append(f"IF {rank_info['sciif']}")
                            if rank_info.get("sci"):
                                parts.append(f"SCI {rank_info['sci']}")
                            if rank_info.get("sciUp"):
                                parts.append(f"中科院 {rank_info['sciUp']}")
                            if parts:
                                print(f"[INFO] 期刊等级: {'  '.join(parts)}")
                    except Exception as e:
                        print(f"[WARN] 期刊等级检索失败（已跳过，不影响主流程）: {e}")

                note_final = compose_note_markdown(
                    p,
                    note_md,
                    pdf_path,
                    folder_rel,
                    model=model,
                    rank_info=rank_info,
                )
                target_folder.mkdir(parents=True, exist_ok=True)
                out_file.write_text(note_final, encoding="utf-8")
                print(f"[OK] 已写入: {out_file_display}")
                state[p.parent_key] = marker
                save_state(state_file, state)
                if cache_dir_to_cleanup is not None:
                    remove_path_safely(cache_dir_to_cleanup)

            processed_count += 1

    print(f"完成，处理 {processed_count} 篇论文。")
    return 0


if __name__ == "__main__":
    sys.exit(run())
