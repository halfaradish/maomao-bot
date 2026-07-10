#!/bin/bash
set -e

echo "=== DiTing Entrypoint ==="

# ═══════════════════════════════════════════════════════════════
# Step 1: C++ 插件运行时重编译
# ═══════════════════════════════════════════════════════════════
# 源码挂载时，镜像内预编译的 .so 会被宿主编译覆盖。
# 在容器首次启动（或源码变更后重启）时检测并重新编译。
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
# Step 2: 条件热重载
# ═══════════════════════════════════════════════════════════════
# HOT_RELOAD 由 docker-compose env_file (.env) 传入容器
#   开发：.env 中 HOT_RELOAD=true  → watchfiles 监视 /app/src
#   生产：.env 中不设置 HOT_RELOAD  → 直接启动
if [ "${HOT_RELOAD:-false}" = "true" ]; then
    echo "[entrypoint] HOT_RELOAD=enabled → watching /app/src"
    exec python3 -c "
import sys, subprocess
from watchfiles import run_process

def on_change(changes):
    for change, path in changes:
        print(f'[reload] {change.name}: {path}')

run_process(
    '/app/src',
    target=lambda: subprocess.run([sys.executable, 'bot.py']),
    callback=on_change,
    debounce=500,
    step=200,
    recursive=True,
)
"
else
    echo "[entrypoint] HOT_RELOAD=disabled → starting normally"
    exec python bot.py
fi
