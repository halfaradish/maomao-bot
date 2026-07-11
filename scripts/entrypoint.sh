#!/bin/bash
set -e

echo "=== DiTing Entrypoint ==="

# ═══════════════════════════════════════════════════════════════
# C++ 插件增量编译
# ═══════════════════════════════════════════════════════════════
# 源码挂载后镜像内预编译的 .so 被宿主目录覆盖。
# -nt 守卫：只在 .cpp 比 .so 新或 .so 缺失时才编译。
# table_gen.cpp 变更频率远低于容器重启频率，99% 的启动跳过此步。
CPP_SRC="src/plugins/sub_records/table_gen.cpp"
CPP_SO="src/plugins/sub_records/table_gen.so"
if [ -f "$CPP_SRC" ]; then
    if [ ! -f "$CPP_SO" ] || [ "$CPP_SRC" -nt "$CPP_SO" ]; then
        echo "[entrypoint] Recompiling table_gen.so..."
        g++ -fPIC -shared "$CPP_SRC" -o "$CPP_SO" \
            $(pkg-config --cflags --libs cairo pango pangocairo jsoncpp) \
            -O3
        echo "[entrypoint] C++ plugin recompiled"
    fi
fi

# ═══════════════════════════════════════════════════════════════
# 启动 bot.py（热重载逻辑由 bot.py 内部通过 HOT_RELOAD 环境变量控制）
# ═══════════════════════════════════════════════════════════════
exec python bot.py
