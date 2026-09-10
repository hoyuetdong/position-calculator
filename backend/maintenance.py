"""只清理可重建嘅舊行情 cache；交易紀錄永遠保留。"""
import os
import time
from pathlib import Path


def clean_cache(root: Path, max_age=86400, now=None):
    now = time.time() if now is None else now
    removed = 0
    for relative in ('.next/cache/fetch-cache', '.next/standalone/.next/cache/fetch-cache'):
        directory = root / relative
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.iterdir():
            try:
                if path.is_file() and not path.is_symlink() and now - path.stat().st_mtime > max_age:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                pass
    return removed


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    print(f'已清理 {clean_cache(root)} 個過期行情 cache 檔案')
