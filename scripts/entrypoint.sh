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
    # 写临时 .py 文件而非用 python3 -c，因为 watchfiles 内部用
    # multiprocessing spawn 子进程，子进程需要能重新导入 __main__
    # 模块找到 target 函数。-c 的 __main__ 是 built-in，无法 pickle。
    cat > /tmp/_watchbot.py << 'PYEOF'
import sys, subprocess
from watchfiles import run_process

def start_bot():
    try:
        return subprocess.run([sys.executable, 'bot.py'])
    except KeyboardInterrupt:
        pass

def on_change(changes):
    for change, path in changes:
        print(f'[reload] {change.name}: {path}')

if __name__ == '__main__':
    run_process(
        '/app/src',
        '/app/bot.py',
        target=start_bot,
        callback=on_change,
        debounce=500,
        step=200,
        recursive=True,
    )
PYEOF
    exec python3 /tmp/_watchbot.py
else
    echo "[entrypoint] HOT_RELOAD=disabled → starting normally"
    exec python bot.py
fi
