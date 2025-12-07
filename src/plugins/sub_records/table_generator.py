import os, ctypes, json, platform
import asyncio
from concurrent.futures import ThreadPoolExecutor

# ----------- 动态选择系统加载动态库 -----------
suffix = ".dll" if platform.system() == "Windows" else ".so"
_dll_path = os.path.join(os.path.dirname(__file__), f"libtablegen{suffix}")
_lib = ctypes.CDLL(_dll_path)

# ----------- C 接口定义 -----------
_lib.generate_table_png.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
_lib.generate_table_png.restype  = ctypes.POINTER(ctypes.c_ubyte)

_lib.free_png_buffer.argtypes = [ctypes.c_void_p]
_lib.free_png_buffer.restype  = None

# ----------- 线程池（不阻塞 bot 主线程）-----------
_executor = ThreadPoolExecutor(max_workers=1)

# ----------- 主函数：生成 PNG 字节流 -----------
async def generate_table_png_bytes(headers, rows):
    def _run():
        payload = json.dumps(
            {"rows": len(rows), "cols": len(headers),
             "headers": headers, "data": rows}
        ).encode()

        out_len = ctypes.c_int()
        ptr = _lib.generate_table_png(payload, ctypes.byref(out_len))
        if not ptr:
            raise RuntimeError("C++ 生成失败")

        # 拷贝 C 层返回内存 → Python Bytes
        buf = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ubyte * out_len.value))[0]
        png_bytes = bytes(buf)

        # 释放 malloc 缓冲区，避免内存泄漏
        _lib.free_png_buffer(ptr)
        return png_bytes

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _run)
