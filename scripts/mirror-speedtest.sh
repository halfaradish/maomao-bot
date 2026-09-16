#!/usr/bin/env bash
# Debian 镜像源测速（只读，只写 /dev/null，不改系统任何东西）
#
# 用途：为 Dockerfile 里 python:3.10-slim（Debian 13 / trixie）的 apt 源选一条快的链路。
# 测三件事，对应 apt 实际体验的三个瓶颈：
#   1. DNS 解析（每次新建连接都要解析；解析慢会让「16 kB 要 43 秒」这种怪现象出现）
#   2. 首字节延迟 TTFB（连接+握手+服务器响应）
#   3. 真实大文件吞吐（apt 下载包的速度）
# 再补一个「小文件连跑 10 次取最慢」，因为 apt 就是被长尾拖死的。
#
# 用法：bash mirror-speedtest.sh        （改镜像列表直接编辑下面的 MIRRORS）

set -u

MIRRORS=(
  mirrors.aliyun.com
  mirrors.tuna.tsinghua.edu.cn
  mirrors.ustc.edu.cn
  mirrors.cloud.tencent.com
  mirrors.huaweicloud.com
  mirrors.163.com
  deb.debian.org
)

# 套件名：默认自动从本机 apt 源里读（避免基础镜像换 Debian 版本后测了个不存在的套件），
# 也可以手动指定：bash mirror-speedtest.sh bookworm
BIG_SUITE="${1:-}"
if [ -z "$BIG_SUITE" ] && [ -r /etc/apt/sources.list.d/debian.sources ]; then
    BIG_SUITE="$(sed -n 's/^Suites:[[:space:]]*\([^ ]*\).*/\1/p' /etc/apt/sources.list.d/debian.sources | head -1)"
fi
BIG_SUITE="${BIG_SUITE:-trixie}"
SMALL_FILE="dists/${BIG_SUITE}/Release"                      # ~250 KB，测延迟
BIG_FILE="dists/${BIG_SUITE}/main/binary-amd64/Packages.gz"  # ~8-9 MB，测吞吐
SEC_FILE="dists/${BIG_SUITE}-security/Release"               # 注意安全源在镜像站上是 /debian-security/ 前缀
TIMEOUT=25
SMALL_TRIES=10

if ! command -v curl >/dev/null 2>&1; then
    echo "缺 curl。先装：apt-get install -y curl"
    echo "（不想装就把下面 curl 换成 wget --server-response --output-document=/dev/null）"
    exit 1
fi

human() { # 字节/秒 → 可读
    awk -v v="$1" 'BEGIN{
        if (v >= 1048576) printf "%.2f MB/s", v/1048576;
        else if (v >= 1024) printf "%.1f KB/s", v/1024;
        else printf "%.0f B/s", v;
    }'
}

printf '%-34s %8s %9s %12s %11s %7s %5s\n' "镜像" "DNS(ms)" "首字节(s)" "吞吐" "小包最慢(s)" "安全源" "失败"

best_mirror=""
best_speed=0

for m in "${MIRRORS[@]}"; do
    base="http://$m/debian"
    dns_max=0; ttfb_sum=0; small_max=0; fails=0; ok=0

    # 0) 安全源是否存在（Dockerfile 把 debian-security 也指到同一站，但路径前缀是 /debian-security/）
    sec_code="$(curl -o /dev/null -sS -m "$TIMEOUT" -w '%{http_code}' "http://$m/debian-security/$SEC_FILE" 2>/dev/null)"
    [ "$sec_code" = "200" ] && sec="OK" || sec="缺(${sec_code:-超时})"

    # 1) 小文件连跑 SMALL_TRIES 次：抓 DNS 与单次耗时的长尾
    for _ in $(seq 1 "$SMALL_TRIES"); do
        out="$(curl -o /dev/null -sS -m "$TIMEOUT" \
            -w '%{http_code} %{time_namelookup} %{time_starttransfer} %{time_total}' \
            "$base/$SMALL_FILE" 2>/dev/null)"
        if [ -z "$out" ]; then fails=$((fails + 1)); continue; fi
        read -r code dn tb tt <<<"$out"
        if [ "$code" != "200" ]; then fails=$((fails + 1)); continue; fi
        ok=$((ok + 1))
        awk -v a="$dn" -v b="$dns_max" 'BEGIN{exit !(a > b)}' && dns_max="$dn"
        awk -v a="$tt" -v b="$small_max" 'BEGIN{exit !(a > b)}' && small_max="$tt"
        ttfb_sum="$(awk -v a="$ttfb_sum" -v b="$tb" 'BEGIN{print a+b}')"
    done

    if [ "$ok" -eq 0 ]; then
        printf '%-34s %8s %9s %12s %11s %7s %5d\n' "$m" "-" "-" "全部失败" "-" "$sec" "$fails"
        continue
    fi

    # 2) 大文件吞吐（真实 apt 下载体验）
    speed=0
    speed_out="$(curl -o /dev/null -sS -m "$TIMEOUT" \
        -w '%{http_code} %{speed_download}' "$base/$BIG_FILE" 2>/dev/null)"
    if [ -n "$speed_out" ]; then
        read -r bcode bspeed <<<"$speed_out"
        [ "$bcode" = "200" ] && speed="${bspeed%%.*}"
    fi

    printf '%-34s %8.0f %9.2f %12s %11.2f %7s %5d\n' \
        "$m" \
        "$(awk -v v="$dns_max" 'BEGIN{print v*1000}')" \
        "$(awk -v s="$ttfb_sum" -v n="$ok" 'BEGIN{print s/n}')" \
        "$(human "$speed")" \
        "$small_max" \
        "$sec" \
        "$fails"

    if [ "$speed" -gt "$best_speed" ] 2>/dev/null; then
        best_speed="$speed"
        best_mirror="$m"
    fi
done

echo
if [ -n "$best_mirror" ]; then
    echo "▶ 吞吐最快：$best_mirror（$(human "$best_speed")）"
    echo
    echo "  选源要点（按重要性排序）："
    echo "   1. 安全源必须是 OK —— Dockerfile 把 debian-security 也指到同一站，缺了会在 apt-get update 直接 404 失败"
    echo "   2. 「小包最慢」要接近「首字节」—— 超过 5 秒说明有长尾卡顿，apt 会被拖成现在这样慢"
    echo "   3. 吞吐够用即可，不必最大"
    echo
    if [ "$best_mirror" = "deb.debian.org" ]; then
        echo "  👉 官方源就是最快的，那最干净的改法不是换域名，而是把 Dockerfile 第 20-21 行两句 sed 整段删掉"
        echo "     （顺带解决浮动 tag + 写死镜像源带来的漂移问题）"
    else
        echo "  确认后改 Dockerfile 第 20-21 行的域名（两句都要改成同一个镜像站）："
        echo "      sed -i 's|deb.debian.org|$best_mirror|g' Dockerfile"
        echo "      sed -i 's|security.debian.org|$best_mirror|g' Dockerfile"
    fi
else
    echo "▶ 没有一个镜像可用：先确认服务器能出网（curl -I http://mirrors.aliyun.com/debian/dists/trixie/Release）"
fi
