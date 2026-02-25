import os, ctypes, json, platform, time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from nonebot import logger

# ----------- 动态选择系统加载动态库 -----------
suffix = ".dll" if platform.system() == "Windows" else ".so"
_current_dir = os.path.dirname(__file__)
_dll_path = os.path.join(_current_dir, f"libtablegen{suffix}")

# 解决 Python 3.8+ (Windows) 下 ctypes 无法加载依赖 DLL 的问题
if platform.system() == "Windows" and hasattr(os, 'add_dll_directory'):
    # 将插件当前目录加入受信任路径 (读取原有的通用 DLL)
    os.add_dll_directory(_current_dir)

    # 将 MSYS2 的编译环境加入受信任路径 (读取最新编译依赖的底层 DLL)
    msys2_bin = r"C:\msys64\mingw64\bin"
    if os.path.exists(msys2_bin):
        os.add_dll_directory(msys2_bin)

if not os.path.exists(_dll_path):
    logger.error(f"未找到动态库: {_dll_path}")
else:
    logger.success(f"加载动态库成功: {_dll_path}")

_lib = ctypes.CDLL(_dll_path)

# ----------- C 接口定义 -----------
_lib.generate_table_png.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
_lib.generate_table_png.restype = ctypes.POINTER(ctypes.c_ubyte)

_lib.free_png_buffer.argtypes = [ctypes.c_void_p]
_lib.free_png_buffer.restype = None

# ----------- 线程池（避免阻塞 NoneBot 主线程）-----------
_executor = ThreadPoolExecutor(max_workers=1)


# ----------- 主函数 -----------
async def generate_table_png_bytes(headers, rows):
    def _run():
        try:
            payload = json.dumps(
                {"rows": len(rows), "cols": len(headers),
                 "headers": headers, "data": rows}
            ).encode()

            start = time.perf_counter()

            out_len = ctypes.c_int()
            ptr = _lib.generate_table_png(payload, ctypes.byref(out_len))
            if not ptr:
                logger.error("⚠ C++ 生成图片返回空指针")
                raise RuntimeError("生成 PNG 失败")

            buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value))[0]
            png_bytes = bytes(buf)
            _lib.free_png_buffer(ptr)

            cost = (time.perf_counter() - start) * 1000
            logger.info(f"🚀 PNG 生成耗时: {cost:.2f} ms")

            return png_bytes

        except Exception as e:
            logger.error(f"生成 PNG 时出错: {e}", exc_info=True)
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _run)