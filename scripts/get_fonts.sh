#!/usr/bin/env bash
# Download the two open fonts the film needs into resources/fonts.
#
#   NotoSerifSC-Regular.otf    思源宋体，正文语气，字幕的稳妥选择
#   ZCOOLKuaiLe-Regular.ttf    站酷快乐体，圆润俏皮，配绘本画面
#
# Both are SIL Open Font License 1.1, so they may be used and shipped
# with a commercial film. A file that is already there is left alone.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$root/resources/fonts"

serif="https://github.com/notofonts/noto-cjk/raw/main/Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf"
playful="https://github.com/google/fonts/raw/main/ofl/zcoolkuaile/ZCOOLKuaiLe-Regular.ttf"

mkdir -p "$target"

# Fetch one font, unless the file is already in place.
fetch() {
    local url="$1"
    local name="$2"
    local path="$target/$name"
    if [[ -s "$path" ]]; then
        echo "$name  already there"
        return
    fi
    echo "$name  downloading"
    curl -fL --retry 3 --connect-timeout 15 -o "$path.part" "$url"
    if [[ ! -s "$path.part" ]]; then
        rm -f "$path.part"
        echo "$name  came back empty" >&2
        exit 1
    fi
    mv "$path.part" "$path"
}

fetch "$serif" NotoSerifSC-Regular.otf
fetch "$playful" ZCOOLKuaiLe-Regular.ttf

ls -l "$target"

# The name libass wants in force_style, read off the files themselves.
if command -v fc-scan >/dev/null 2>&1; then
    echo
    echo "family names for force_style:"
    fc-scan --format "  %{file}: %{family}\n" "$target"/* 2>/dev/null \
        | sed "s#$target/##"
fi
