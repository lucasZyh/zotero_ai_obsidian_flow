from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

ITEM_TYPE_CN = {
    "journalArticle": "期刊论文",
    "conferencePaper": "会议论文",
    "preprint": "预印本",
    "thesis": "学位论文",
    "book": "图书",
    "bookSection": "图书章节",
    "report": "报告",
    "manuscript": "手稿",
    "presentation": "演示文稿",
    "document": "文档",
    "webpage": "网页",
    "patent": "专利",
    "dataset": "数据集",
}

PAPER_ITEM_TYPES = {
    "journalArticle",
    "conferencePaper",
    "preprint",
    "report",
    "manuscript",
    "thesis",
}


def _load_processed_parent_keys(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    return {str(k).strip() for k in data.keys() if isinstance(k, str) and str(k).strip()}


def _top_type_counts(items: list[dict], topn: int = 10) -> list[tuple[str, int]]:
    bucket: dict[str, int] = {}
    for it in items:
        raw = str(it.get("type_name", "") or "unknown").strip() or "unknown"
        t = ITEM_TYPE_CN.get(raw, raw)
        bucket[t] = bucket.get(t, 0) + 1
    rows = sorted(bucket.items(), key=lambda x: (-x[1], x[0].lower()))
    return rows[:topn]


def _type_split_counts(all_items: list[dict], unprocessed_items: list[dict], topn: int = 10) -> list[dict]:
    total_map: dict[str, int] = {}
    un_map: dict[str, int] = {}
    for it in all_items:
        k = str(it.get("type_name", "") or "unknown").strip() or "unknown"
        total_map[k] = total_map.get(k, 0) + 1
    for it in unprocessed_items:
        k = str(it.get("type_name", "") or "unknown").strip() or "unknown"
        un_map[k] = un_map.get(k, 0) + 1
    rows = sorted(total_map.items(), key=lambda x: (-x[1], x[0].lower()))
    out: list[dict] = []
    for t, total in rows[:topn]:
        un = int(un_map.get(t, 0))
        out.append(
            {
                "type_name": t,
                "total": int(total),
                "unprocessed": un,
                "processed": max(int(total) - un, 0),
            }
        )
    return out


def _top_folder_counts(
    item_ids: list[int],
    item_collection_rows: list[tuple[int, int]],
    collection_rows: list[tuple[int, str, int | None]],
) -> list[tuple[str, int]]:
    collection_name: dict[int, str] = {}
    collection_parent: dict[int, int | None] = {}
    for cid, cname, pcid in collection_rows:
        collection_name[int(cid)] = str(cname or "").strip() or "未命名分类"
        collection_parent[int(cid)] = int(pcid) if pcid is not None else None

    root_cache: dict[int, str] = {}

    def _root_name(cid: int) -> str:
        cid = int(cid)
        if cid in root_cache:
            return root_cache[cid]
        seen: set[int] = set()
        cur = cid
        while True:
            if cur in seen:
                break
            seen.add(cur)
            parent = collection_parent.get(cur)
            if parent is None:
                break
            cur = parent
        out = collection_name.get(cur) or collection_name.get(cid) or "未分类"
        root_cache[cid] = out
        return out

    item_roots: dict[int, set[str]] = {int(i): set() for i in item_ids}
    for iid, cid in item_collection_rows:
        iid_i = int(iid)
        cid_i = int(cid)
        if iid_i in item_roots:
            item_roots[iid_i].add(_root_name(cid_i))

    bucket: dict[str, int] = {}
    for iid in item_ids:
        roots = item_roots.get(int(iid), set())
        if not roots:
            bucket["未分类"] = bucket.get("未分类", 0) + 1
            continue
        for r in roots:
            bucket[r] = bucket.get(r, 0) + 1

    return sorted(bucket.items(), key=lambda x: (-x[1], x[0].lower()))


def _folder_split_counts(
    all_items: list[dict],
    processed_keys: set[str],
    item_collection_rows: list[tuple[int, int]],
    collection_rows: list[tuple[int, str, int | None]],
) -> list[dict]:
    collection_name: dict[int, str] = {}
    collection_parent: dict[int, int | None] = {}
    for cid, cname, pcid in collection_rows:
        collection_name[int(cid)] = str(cname or "").strip() or "未命名分类"
        collection_parent[int(cid)] = int(pcid) if pcid is not None else None

    root_cache: dict[int, str] = {}

    def _root_name(cid: int) -> str:
        cid = int(cid)
        if cid in root_cache:
            return root_cache[cid]
        seen: set[int] = set()
        cur = cid
        while True:
            if cur in seen:
                break
            seen.add(cur)
            parent = collection_parent.get(cur)
            if parent is None:
                break
            cur = parent
        out = collection_name.get(cur) or collection_name.get(cid) or "未分类"
        root_cache[cid] = out
        return out

    item_roots: dict[int, set[str]] = {}
    for iid, cid in item_collection_rows:
        iid_i = int(iid)
        item_roots.setdefault(iid_i, set()).add(_root_name(int(cid)))

    total_map: dict[str, int] = {}
    un_map: dict[str, int] = {}
    for row in all_items:
        iid = int(row.get("item_id", 0) or 0)
        pkey = str(row.get("parent_key", "")).strip()
        roots = item_roots.get(iid, set()) or {"未分类"}
        is_un = pkey not in processed_keys if pkey else True
        for r in roots:
            total_map[r] = total_map.get(r, 0) + 1
            if is_un:
                un_map[r] = un_map.get(r, 0) + 1

    rows = sorted(total_map.items(), key=lambda x: (-x[1], x[0].lower()))
    out: list[dict] = []
    for name, total in rows:
        un = int(un_map.get(name, 0))
        out.append(
            {
                "type_name": name,
                "total": int(total),
                "unprocessed": un,
                "processed": max(int(total) - un, 0),
            }
        )
    return out


def compute_zotero_dashboard_stats(
    zotero_db: str,
    state_file_path: Path,
    copy_db_to_temp_fn: Callable[[str], str],
) -> dict:
    if not Path(zotero_db).exists():
        return {
            "total_items": 0,
            "weekly_new_items": 0,
            "monthly_new_items": 0,
            "unprocessed_items": 0,
            "weekly_unprocessed_items": 0,
            "type_counts_all": [],
            "type_split_all": [],
            "top_folder_counts_all": [],
            "folder_split_all": [],
            "folder_split_papers": [],
            "type_counts_unprocessed": [],
            "type_counts_monthly_new": [],
            "top_folder_counts_monthly_new": [],
            "weekly_titles": [],
            "weekly_unprocessed_titles": [],
        }

    processed_keys = _load_processed_parent_keys(state_file_path)
    week_start = time.localtime()
    days_from_monday = int((week_start.tm_wday + 7) % 7)
    week_start_ts = time.time() - days_from_monday * 86400
    week_start_str = time.strftime("%Y-%m-%d", time.localtime(week_start_ts))
    month_start_str = datetime.now().replace(day=1).strftime("%Y-%m-%d")

    temp_db = copy_db_to_temp_fn(zotero_db)
    conn = None
    try:
        conn = sqlite3.connect(temp_db)
        item_rows = conn.execute(
            """
            SELECT
              i.itemID AS item_id,
              i.key AS parent_key,
              i.dateAdded AS date_added,
              it.typeName AS type_name,
              COALESCE(tt.title, i.key) AS title
            FROM items i
            JOIN libraries l ON l.libraryID = i.libraryID
            JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
            LEFT JOIN (
              SELECT d.itemID AS item_id, v.value AS title
              FROM itemData d
              JOIN fieldsCombined f ON f.fieldID = d.fieldID
              JOIN itemDataValues v ON v.valueID = d.valueID
              WHERE f.fieldName = 'title'
            ) tt ON tt.item_id = i.itemID
            WHERE l.type = 'user'
              AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
              AND i.itemID NOT IN (SELECT itemID FROM itemAttachments)
              AND i.itemID NOT IN (SELECT itemID FROM itemNotes)
              AND it.typeName NOT IN ('attachment', 'note', 'annotation')
            ORDER BY i.dateAdded DESC
            """
        ).fetchall()
        item_collection_rows = conn.execute(
            """
            SELECT ci.itemID AS item_id, ci.collectionID AS collection_id
            FROM collectionItems ci
            JOIN items i ON i.itemID = ci.itemID
            JOIN libraries l ON l.libraryID = i.libraryID
            JOIN itemTypesCombined it ON it.itemTypeID = i.itemTypeID
            WHERE l.type = 'user'
              AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
              AND i.itemID NOT IN (SELECT itemID FROM itemAttachments)
              AND i.itemID NOT IN (SELECT itemID FROM itemNotes)
              AND it.typeName NOT IN ('attachment', 'note', 'annotation')
            """
        ).fetchall()
        collection_rows = conn.execute(
            """
            SELECT c.collectionID, c.collectionName, c.parentCollectionID
            FROM collections c
            JOIN libraries l ON l.libraryID = c.libraryID
            WHERE l.type = 'user'
            """
        ).fetchall()
    finally:
        if conn:
            conn.close()
        Path(temp_db).unlink(missing_ok=True)

    all_items: list[dict] = []
    all_item_ids: list[int] = []
    for item_id, parent_key, date_added, type_name, title in item_rows:
        all_item_ids.append(int(item_id))
        all_items.append(
            {
                "item_id": int(item_id),
                "parent_key": str(parent_key or "").strip(),
                "date_added": str(date_added or "")[:10],
                "type_name": str(type_name or "unknown"),
                "title": str(title or parent_key or "").strip(),
            }
        )

    total_items = len(all_items)
    unprocessed_items = 0
    weekly_new_items = 0
    monthly_new_items = 0
    weekly_unprocessed_items = 0
    unprocessed_rows: list[dict] = []
    monthly_rows: list[dict] = []
    monthly_item_ids: list[int] = []
    weekly_rows: list[dict] = []
    weekly_unprocessed_rows: list[dict] = []
    for row in all_items:
        key = row["parent_key"]
        date_part = row["date_added"]
        is_weekly = bool(date_part and date_part >= week_start_str)
        is_monthly = bool(date_part and date_part >= month_start_str)
        is_processed = key in processed_keys if key else False
        if not is_processed:
            unprocessed_items += 1
            unprocessed_rows.append(row)
        if is_weekly:
            weekly_new_items += 1
            weekly_rows.append({**row, "analyzed": bool(is_processed)})
            if not is_processed:
                weekly_unprocessed_items += 1
                weekly_unprocessed_rows.append({**row, "analyzed": False})
        if is_monthly:
            monthly_new_items += 1
            monthly_rows.append(row)
            monthly_item_ids.append(int(row.get("item_id", 0) or 0))

    return {
        "total_items": total_items,
        "weekly_new_items": weekly_new_items,
        "monthly_new_items": monthly_new_items,
        "unprocessed_items": unprocessed_items,
        "weekly_unprocessed_items": weekly_unprocessed_items,
        "type_counts_all": _top_type_counts(all_items),
        "type_split_all": _type_split_counts(all_items, unprocessed_rows),
        "top_folder_counts_all": _top_folder_counts(all_item_ids, item_collection_rows, collection_rows),
        "folder_split_all": _folder_split_counts(all_items, processed_keys, item_collection_rows, collection_rows),
        "folder_split_papers": _folder_split_counts(
            [x for x in all_items if str(x.get("type_name", "")).strip() in PAPER_ITEM_TYPES],
            processed_keys,
            item_collection_rows,
            collection_rows,
        ),
        "type_counts_unprocessed": _top_type_counts(unprocessed_rows),
        "type_counts_monthly_new": _top_type_counts(monthly_rows),
        "top_folder_counts_monthly_new": _top_folder_counts(monthly_item_ids, item_collection_rows, collection_rows),
        "weekly_titles": weekly_rows,
        "weekly_unprocessed_titles": weekly_unprocessed_rows,
    }
