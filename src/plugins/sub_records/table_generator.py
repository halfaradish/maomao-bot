import os, ctypes, json, platform, time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from nonebot import logger

# ----------- 动态库定位 -----------
# 按顺序尝试，取第一个能加载成功的：
#   1. 插件目录          —— Windows 本地开发的 DLL，或手工编译的产物
#   2. 仓库根 libs/      —— Dockerfile 在镜像里预编译（不在源码挂载范围内，不会被宿主覆盖）
#   3. 插件目录旧名字     —— 旧版 entrypoint.sh 的产物，过渡期保留：镜像未重建时靠它兜底
suffix = ".dll" if platform.system() == "Windows" else ".so"
_current_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
_candidates = [
    os.path.join(_current_dir, f"libtablegen{suffix}"),
    os.path.join(_repo_root, "libs", f"libtablegen{suffix}"),
    os.path.join(_current_dir, f"table_gen{suffix}"),
]


def _prepare_dll_search_path():
    """解决 Python 3.8+ (Windows) 下 ctypes 不搜索依赖 DLL 所在目录的问题。"""
    if platform.system() != "Windows" or not hasattr(os, "add_dll_directory"):
        return
    for directory in (_current_dir, r"C:\msys64\mingw64\bin"):
        if os.path.isdir(directory):
            os.add_dll_directory(directory)


def _load_library():
    """按候选路径依次尝试加载，返回 (lib, 失败原因)。"""
    _prepare_dll_search_path()
    failures = []
    for path in _candidates:
        if not os.path.exists(path):
            failures.append(f"{path}（文件不存在）")
            continue
        try:
            lib = ctypes.CDLL(path)
        except OSError as e:
            failures.append(f"{path}（{e}）")
            continue
        logger.success(f"[sub_records] 动态库加载成功：{path}")
        return lib, None
    return None, "；".join(failures)


_lib, _load_error = _load_library()

# ----------- C 接口定义 -----------
if _lib is not None:
    _lib.generate_table_png.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    _lib.generate_table_png.restype = ctypes.POINTER(ctypes.c_ubyte)

    _lib.free_png_buffer.argtypes = [ctypes.c_void_p]
    _lib.free_png_buffer.restype = None
else:
    # 图片生成不可用不影响插件导入，过题的文本统计照常工作
    logger.error(
        "[sub_records] 动态库加载失败，过题表格图片将不可用。"
        "容器内请重启服务让 entrypoint.sh 重新编译，或重新构建镜像。\n"
        f"[sub_records] 已尝试：{_load_error}"
    )

# ----------- 线程池（避免阻塞 NoneBot 主线程）-----------
_executor = ThreadPoolExecutor(max_workers=1)


# ----------- 主函数 -----------
def _render_png(headers, rows):
    payload = json.dumps(
        {"rows": len(rows), "cols": len(headers),
         "headers": headers, "data": rows}
    ).encode()

    start = time.perf_counter()

    out_len = ctypes.c_int()
    ptr = _lib.generate_table_png(payload, ctypes.byref(out_len))
    if not ptr:
        raise RuntimeError("C++ 生成图片返回空指针")

    try:
        buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value))[0]
        png_bytes = bytes(buf)
    finally:
        _lib.free_png_buffer(ptr)

    cost = (time.perf_counter() - start) * 1000
    logger.info(f"🚀 PNG 生成耗时: {cost:.2f} ms")
    return png_bytes


async def generate_table_png_bytes(headers, rows):
    """生成表格 PNG，失败返回 None（由调用方决定如何提示用户）。"""
    if _lib is None:
        logger.error("生成 PNG 失败：动态库不可用")
        return None

    def _run():
        try:
            return _render_png(headers, rows)
        except Exception as e:
            logger.error(f"生成 PNG 时出错: {e}", exc_info=True)
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _run)
