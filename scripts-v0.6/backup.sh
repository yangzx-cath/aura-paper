#!/usr/bin/env bash
# Pack the book library, and on request the working folders, into one tar.
#
#   data/   the library: source.pdf plus the published pub/ of every book
#   out/    the working folders: stage json, crops, clips and logs
#
# The library alone is what a reader needs; out/ only keeps the stage
# history and saves paying for a render again. .env holds the keys and is
# never packed, so keep a copy of it somewhere else.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
into="$HOME"
full=0

# --full adds out/, --into moves the tar off the default folder.
while [[ $# -gt 0 ]]; do
    case "$1" in
        --full)
            full=1
            shift
            ;;
        --into)
            into="${2:?--into needs a folder}"
            shift 2
            ;;
        -h|--help)
            echo "usage: $(basename "$0") [--full] [--into FOLDER]"
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            exit 2
            ;;
    esac
done

folders=(data)
kind=data
if [[ $full -eq 1 ]]; then
    folders=(data out)
    kind=full
fi

mkdir -p "$into"
stamp="$(date +%F-%H%M)"
target="$into/aura-$kind-$stamp.tar"

cd "$root"
tar -cf "$target" "${folders[@]}"

size="$(du -h "$target" | cut -f1)"
echo "backup   $target"
echo "size     $size"
if [[ -f .env ]]; then
    echo "note     .env is not in the tar, keep a copy of it"
fi
