"""Сверка локальных файлов с последним коммитом на GitHub (по blob-SHA).

Если расхождений нет — на Render уже стоит актуальный код, перезаливка не нужна.
"""
import asyncio
import base64
import hashlib
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
TOKEN = [ln.strip() for ln in (ROOT / ".gh_token").read_text(encoding="utf-8").splitlines() if ln.strip()][0]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "deploy-check",
    "Accept": "application/vnd.github+json",
}
OWNER, REPO = "vedmakkm-lab", "steam-gift-bot"


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def local_files() -> dict[str, str]:
    from scripts.upload_github import collect_files

    result = {}
    for p in collect_files():
        result[p.relative_to(ROOT).as_posix()] = blob_sha(p.read_bytes())
    return result


async def main() -> None:
    local = local_files()
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        async with s.get(f"https://api.github.com/repos/{OWNER}/{REPO}/commits/main") as r:
            commit = await r.json()
        print("deployed commit:", commit["sha"][:7], "-", commit["commit"]["message"].splitlines()[0])
        tree_sha = commit["commit"]["tree"]["sha"]
        async with s.get(
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/trees/{tree_sha}?recursive=1"
        ) as r:
            tree = await r.json()
        if tree.get("truncated"):
            raise RuntimeError("tree truncated — расширьте сравнение")
        remote = {i["path"]: i["sha"] for i in tree["tree"] if i["type"] == "blob"}
    missing = [p for p in remote if p not in local]
    extra = [p for p in local if p not in remote]
    changed = [p for p in local if p in remote and local[p] != remote[p]]
    print(f"remote files: {len(remote)} | local files: {len(local)}")
    print("отсутствуют локально:", missing or "—")
    print("лишние локально:", extra or "—")
    print("изменённые:", changed or "—")
    if not missing and not extra and not changed:
        print("OK: локальный код идентичен задеплоенному — перезаливка не требуется")
    else:
        print("ТРЕБУЕТСЯ ПЕРЕЗАЛИВКА")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    asyncio.run(main())
