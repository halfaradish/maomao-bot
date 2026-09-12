# 新增 vv 插件（这就是VV表情包）实施计划

## 背景与已确认需求

tmp 项目（`C:\Users\LJT\Desktop\tmp\vv.py`）是张维为语录表情包检索器的 CLI 原型：输入台词 → 在 279 期《这就是中国》字幕（约 37 万条）中定位 → 从远程静态帧图库（vv.noxylva.org）Range 请求截出带烧录字幕的 webp 图。功能形态对标 pigSender（发图插件）。

已拍板：①本地检索为主；②命令照搬原型 `随机vv` / `vv说xxx`；③回复 = 图 + 台词 + 出处 + B站链接；④默认开放 + vv 专属群黑名单（自定义黑名单权限点：命令触发 → 群号命中黑名单则拦截，否则放行），超管命令管理。

## 一、数据准备（一次性拷贝，gitignored）

`data/*` 已在 .gitignore，不进版本库。数据统一放 `{NONEBOT_DATA_DIR}/vv/`（沿用 JsonUtils 的 `DiTingData.NONEBOT_DATA_DIR` 惯例，部署即 `/app/data/vv/`）：

| 源（tmp 项目） | 目标 |
|---|---|
| `data/VV/subtitle/*.json`（279 期） | `{NONEBOT_DATA_DIR}/vv/subtitle/` |
| `data/VV/Web/mapping.json` | `{NONEBOT_DATA_DIR}/vv/mapping.json` |
| `data/vv_cache.jsonl`（43MB 检索缓存） | `{NONEBOT_DATA_DIR}/vv/cache.jsonl` |

缓存缺失时插件自动从 subtitle 重建（移植原型 `build_cache`）。部署时需把目录同步到容器挂载卷。

## 二、新增文件

```
src/plugins/vv/
├── __init__.py      # PluginMetadata + 黑名单检查 + 命令注册 + handlers
├── config.py        # Config(BaseModel)：vv_min_ratio=50.0、vv_min_similarity=0.5（get_plugin_config 加载）
├── data_source.py   # 移植 tmp/vv.py：build_cache/load_records/search_local/random_pick/
│                    #   parse_episode/parse_seconds/_load_index/_locate_frame/extract_frame/load_bili_mapping
└── permissions.py   # register_perm_point("vv:use", "VV表情包", "VV表情包使用权限", plugin_name="vv")

src/common/models/vv_models.py   # VvGroupBlacklist 模型（结构镜像 GroupBlacklist：group_id 唯一/reason/created_by/时间戳）
```

- `vv_models.py` 注册进 `src/common/models/__init__.py`，启动时 `auto_register.py` 的 `Base.metadata.create_all` 自动建表（like_plugin_models 同款流程）
- 元数据：`name="这就是VV"`，`PluginGroupEnum.UTILITY` + `PluginBadgeColor.GREEN`，`supported_adapters={"~onebot.v11"}`，extra 带 author/version（pigSender 同款）

## 三、命令设计（两个 matcher，均 priority=5、block=True）

- **随机vv**：`on_regex(r"^随[随机機]\s*[vVｖＶ]{1,2}$")` → `random_pick(similarity≥0.5, 1条)` → 截帧发送
- **vv说xxx**：`on_regex(r"^[vVｖＶ]{1,2}\s*[说說]\s*(.+)$")` → `search_local`（先精确子串、后字符重叠预筛 + difflib 模糊，min_ratio≥50）→ 截帧发送
- **回复格式**（单条消息，pigSender 同款拼装）：`MessageSegment.image(webp字节) + "\n台词：...\n出处：P{集数} @{时间戳}\nB站：https://www.bilibili.com/bangumi/play/epXXX/?t={秒}"`
- **无命中**：回复"没找到相关台词"；**截帧/网络失败**：回复提示 + logger.error
- 不做裸文本触发（CLI 原型把裸文本当检索词，在群里不可行——边界明确）

## 四、黑名单权限点（vv 专属）

- **检查链**（两个 handler 入口，仅群聊事件）：查 `VvGroupBlacklist` 表 → 群号命中 → 静默拦截（logger.info，不回复）；未命中放行；私聊恒放行
- **缓存**：`perm_cache`（TTL 60s），key `vv:bl:{group_id}`，增删后 `clear_pattern("vv:bl:")` 失效
- **管理命令**（`permission=SUPERUSER`）：
  - `vv拉黑 [群号]` — 缺省拉黑当前群（GroupMessageEvent），可带群号远程操作
  - `vv解拉黑 [群号]`
  - `vv黑名单` — 列出已拉黑群

## 五、性能要点

- 43MB 缓存懒加载：首次命令触发时 `asyncio.to_thread(load_records)` + `asyncio.Lock` 防并发重复加载
- 检索（difflib CPU 密集）与截帧（同步 urllib + 重试）均在 `asyncio.to_thread` 中执行，不阻塞事件循环
- `.index` 文件进程内 dict 缓存（保留原型 `_index_cache`）

## 六、明确不做（边界）

- 线上 API 回退（search_online / rag 语义搜索）不移植
- top N 多图输出不做（固定 1 张）
- 字幕数据自动更新 / 缓存重建命令不做（更新 = 手动替换文件 + 删 cache.jsonl，插件自动重建）
- webp 直接发送（NapCat 支持）；若实测异常再考虑 Pillow 转码，不在本期

## 七、验证

1. 冒烟脚本 `test/vv_smoke.py`（项目 test/ 惯例）：不启动 bot，直接调 `data_source` 验证缓存加载、`vv说中国人你要自信` 检索命中、`extract_frame` 出图字节
2. `nb run` 手测：两条命令正常回复、黑名单三命令（拉黑后命令静默、解拉黑恢复）、私聊可用
