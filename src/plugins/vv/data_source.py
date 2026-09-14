"""这就是VV 数据源层 — 移植自 vv.py（数据源: github.com/Cicada000/VV）

全部为同步实现（含阻塞网络请求与 CPU 检索），
调用方必须置于 asyncio.to_thread 中执行，避免阻塞事件循环。

数据目录: {NONEBOT_DATA_DIR}/vv/
- subtitle/*.json  279 期《这就是中国》字幕（git clone github.com/Cicada000/VV --depth 1）
- mapping.json     字幕文件名 -> B 站视频路径
- cache.jsonl      字幕压缩成的单文件检索缓存（缺失时自动从 subtitle 重建）
"""

import difflib
import gzip
import json
import random
import re
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

from nonebot.log import logger

from src.config import DiTingData

VV_DATA_DIR = Path(DiTingData.NONEBOT_DATA_DIR) / "vv"
SUBTITLE_DIR = VV_DATA_DIR / "subtitle"
MAPPING_JSON = VV_DATA_DIR / "mapping.json"
CACHE_FILE = VV_DATA_DIR / "cache.jsonl"

IMAGE_BASE = "https://vv.noxylva.org"
UA = "vv-demo/1.0 (personal bot; https://github.com/Cicada000/VV)"

Record = tuple  # (filename, timestamp, similarity, text)


def http_get(url: str, headers: dict | None = None, timeout: int = 30,
             retries: int = 2) -> tuple[int, bytes]:
    """GET 请求，返回 (status, body)。对网络抖动做简单重试。"""
    req_headers = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx 属于确定性错误，不重试（416 交给调用方处理）
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {url}: {last_err}")


# ---------------------------------------------------------------- 数据层

def build_cache() -> None:
    """把 subtitle/*.json 压成单文件 jsonl 缓存，加速后续加载。"""
    if not SUBTITLE_DIR.is_dir():
        raise RuntimeError(
            f"找不到字幕数据目录: {SUBTITLE_DIR}，"
            "请先拷贝数据（git clone --depth 1 https://github.com/Cicada000/VV）"
        )
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    n_files = n_lines = 0
    with CACHE_FILE.open("w", encoding="utf-8") as out:
        for path in sorted(SUBTITLE_DIR.glob("*.json")):
            try:
                entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"[vv] 跳过无法解析的字幕文件 {path.name}: {e}")
                continue
            for ent in entries:
                text = (ent.get("text") or "").strip()
                ts = (ent.get("timestamp") or "").strip()
                if not text or not ts:
                    continue
                sim = float(ent.get("similarity") or 0.0)
                out.write(json.dumps(
                    {"f": path.name, "t": ts, "s": round(sim, 3), "x": text},
                    ensure_ascii=False,
                ) + "\n")
                n_lines += 1
            n_files += 1
    logger.info(f"[vv] 已从 {n_files} 个字幕文件构建缓存: {n_lines} 条台词")


def load_records() -> list[Record]:
    if not CACHE_FILE.exists():
        build_cache()
    records: list[Record] = []
    with CACHE_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            records.append((o["f"], o["t"], o["s"], o["x"]))
    return records


# ---------------------------------------------------------------- 检索层

_PUNCT_RE = re.compile(r"[\s，。、；：？！“”‘’《》（）\[`\]{}·—…,.:;?!()\"']+")


def normalize(s: str) -> str:
    return _PUNCT_RE.sub("", s)


def match_ratio(query: str, text: str) -> float:
    """关键词在句子中的匹配比例(0-100)。对齐线上 API 的 min_ratio 语义。"""
    if not query:
        return 0.0
    if query in text:
        return 100.0
    return difflib.SequenceMatcher(None, query, text).ratio() * 100.0


def search_local(records: list[Record], query: str, min_ratio: float,
                 min_similarity: float, top: int) -> list[dict]:
    q = normalize(query)
    if not q:
        return []
    # 先找精确子串命中（即 match_ratio=100）
    exact = [
        {"filename": f, "timestamp": t, "similarity": s, "text": x,
         "match_ratio": 100.0, "exact_match": True}
        for f, t, s, x in records
        if s >= min_similarity and q in normalize(x)
    ]
    if exact:
        exact.sort(key=lambda r: -r["similarity"])
        return exact[:top]

    # 无精确命中 -> 模糊匹配。先用字符重叠预筛，再算 SequenceMatcher。
    q_chars = set(q)
    candidates = []
    need = len(q) * min_ratio / 100.0
    for f, t, s, x in records:
        if s < min_similarity:
            continue
        nx = normalize(x)
        if len(q_chars & set(nx)) < need:
            continue
        ratio = match_ratio(q, nx)
        if ratio >= min_ratio:
            candidates.append(
                {"filename": f, "timestamp": t, "similarity": s, "text": x,
                 "match_ratio": round(ratio, 1), "exact_match": False})
    candidates.sort(key=lambda r: (-r["match_ratio"], -r["similarity"]))
    return candidates[:top]


def random_pick(records: list[Record], min_similarity: float,
                count: int, seed: int | None = None) -> list[dict]:
    pool = [r for r in records if r[2] >= min_similarity]
    if not pool:
        return []
    rng = random.Random(seed)
    picked = rng.sample(pool, k=min(count, len(pool)))
    return [
        {"filename": f, "timestamp": t, "similarity": s, "text": x,
         "match_ratio": None, "exact_match": None}
        for f, t, s, x in picked
    ]


# ---------------------------------------------------------------- 截帧层
# 移植自网页版 Web/script.js 的 extractFrame():
# 帧图按集数分组打包成 webp，组号 = (集数-1)//10; 组内通过 .index 文件
# （可 gzip）二分定位目标帧在 .webp 中的字节区间，再用 Range 请求取出。

def parse_episode(filename: str) -> int | None:
    m = re.search(r"\[P(\d+)\]", filename)
    return int(m.group(1)) if m else None


def parse_seconds(timestamp: str) -> int | None:
    m = re.match(r"^(\d+)m(\d+)s$", timestamp)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


_index_cache: dict[int, bytes] = {}


def _load_index(group: int) -> bytes:
    if group in _index_cache:
        return _index_cache[group]
    status, data = http_get(f"{IMAGE_BASE}/{group}.index")
    if status != 200 or not data:
        raise RuntimeError(f"拉取索引失败: {group}.index (HTTP {status})")
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if len(data) < 16:
        raise RuntimeError(f"索引数据异常({len(data)} 字节): {group}.index")
    _index_cache[group] = data
    return data


def _locate_frame(index: bytes, folder_id: int, frame: int) -> tuple[int, int | None]:
    """在索引中二分查找 (folder, frame)，返回 (起始字节, 结束字节或 None)。"""
    grid_w, grid_h, folder_count = struct.unpack_from("<III", index, 0)
    if grid_w == 0 or grid_h == 0 or folder_count == 0:
        raise RuntimeError("索引头校验失败，格式可能已变更")
    off = 12 + folder_count * 4
    (file_count,) = struct.unpack_from("<I", index, off)
    off += 4
    lo, hi = 0, file_count - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        rec = off + mid * 16
        cur_folder, cur_frame = struct.unpack_from("<II", index, rec)
        if cur_folder == folder_id and cur_frame == frame:
            (start,) = struct.unpack_from("<Q", index, rec + 8)
            end: int | None = None
            if mid < file_count - 1:
                (end,) = struct.unpack_from("<Q", index, rec + 24)
            return start, end
        if cur_folder < folder_id or (cur_folder == folder_id and cur_frame < frame):
            lo = mid + 1
        else:
            hi = mid - 1
    raise RuntimeError(f"帧未找到: 集 {folder_id} 的第 {frame} 秒")


def extract_frame(folder_id: int, frame: int) -> bytes:
    """返回该集该秒的画面（webp 字节）。"""
    group = (folder_id - 1) // 10
    index = _load_index(group)
    start, end = _locate_frame(index, folder_id, frame)
    url = f"{IMAGE_BASE}/{group}.webp"
    range_header = f"bytes={start}-{end - 1}" if end is not None else f"bytes={start}-"
    try:
        status, data = http_get(url, headers={"Range": range_header})
        if status == 206 and data:
            return data
        # 某些 CDN 对超出末尾的区间返回 416/200，统一走异常分支
        raise RuntimeError(f"Range 请求返回 HTTP {status}")
    except (urllib.error.HTTPError, RuntimeError) as e:
        # 416（区间越界）时退化为开放式区间: bytes=start-
        if "416" in str(e) and end is not None:
            status, data = http_get(url, headers={"Range": f"bytes={start}-"})
            if status == 206 and data:
                return data
        raise RuntimeError(f"截帧失败(集{folder_id} 第{frame}秒): {e}") from e


# ---------------------------------------------------------------- 输出层

def load_bili_mapping() -> dict[str, str]:
    """字幕文件名 -> B 站视频路径。"""
    if not MAPPING_JSON.exists():
        return {}
    mapping = json.loads(MAPPING_JSON.read_text(encoding="utf-8"))
    return {v: k for k, v in mapping.items()}  # 反转: 文件名 -> /bangumi/play/ep.../
