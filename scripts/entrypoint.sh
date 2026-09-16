#!/bin/bash
set -e

echo "=== DiTing Entrypoint ==="

# ═══════════════════════════════════════════════════════════════
# C++ 插件增量编译
# ═══════════════════════════════════════════════════════════════
# 产物编译到 libs/libtablegen.so（不被源码挂载覆盖），镜像里已有一份，
# 只有源码更新、产物缺失或产物依赖在当前镜像里解析不了时才重编译。
# 依赖检查必要的原因：基础镜像换 Debian 大版本时 libjsoncpp 的 soname 会变，
# 旧产物会 dlopen 失败，此时必须重新链接。
CPP_SRC="src/plugins/sub_records/table_gen.cpp"
CPP_SO="libs/libtablegen.so"

needs_rebuild() {
    if [ ! -f "$CPP_SO" ]; then return 0; fi
    if [ "$CPP_SRC" -nt "$CPP_SO" ]; then return 0; fi
    if ! ldd "$CPP_SO" >/dev/null 2>&1; then return 0; fi
    if ldd "$CPP_SO" 2>/dev/null | grep -q "not found"; then return 0; fi
    return 1
}

if [ -f "$CPP_SRC" ] && needs_rebuild; then
    echo "[entrypoint] Recompiling $CPP_SO..."
    mkdir -p "$(dirname "$CPP_SO")"
    g++ -fPIC -shared "$CPP_SRC" -o "$CPP_SO" \
        $(pkg-config --cflags --libs cairo pango pangocairo jsoncpp) \
        -O3
    echo "[entrypoint] C++ plugin recompiled"
fi

# ═══════════════════════════════════════════════════════════════
# 启动 bot.py（热重载逻辑由 bot.py 内部通过 HOT_RELOAD 环境变量控制）
# ═══════════════════════════════════════════════════════════════
exec python bot.py
