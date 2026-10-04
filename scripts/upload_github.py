"""Заливка проекта в GitHub-репозиторий через API (одним коммитом, без git).

Читает токен из .gh_token (не входит в репозиторий).
Запуск: python scripts/upload_github.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".gh_token"
OWNER = "vedmakkm-lab"
REPO = "steam-gift-bot"

INCLUDE_FILES = [
    "alembic.ini",
    "main.py",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "render.yaml",
    "README.md",
    ".env.example",
    ".gitignore",
    ".dockerignore",
]
INCLUDE_DIRS = ["bot", "migrations", "scripts"]
EXCLUDE_NAMES = {
    "__pycache__", ".venv", "venv", ".env", ".gh_token",
    "logs", "backups", ".git", ".idea", ".vscode",
}
EXCLUDE_SUFFIX = (".db", ".db-wal", ".db-shm", ".pyc", ".log")


def collect_files() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.is_file():
            files.append(p)
    for d in INCLUDE_DIRS:
        for p in (ROOT / d).rglob("*"):
            if p.is_file():
                if any(part in EXCLUDE_NAMES for part in p.parts):
                    continue
                if p.suffix in EXCLUDE_SUFFIX or p.name.endswith((".db-wal", ".db-shm")):
                    continue
                files.append(p)
    return sorted(set(files))


async def api(session: aiohttp.ClientSession, method: str, url: str, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "steam-gift-bot-deploy",
    }
    async with session.request(method, url, headers=headers, json=payload) as resp:
        text = await resp.text()
        if resp.status >= 300:
            raise RuntimeError(f"{method} {url} -> {resp.status}: {text[:500]}")
        return json.loads(text) if text else {}


# Первый токен (render-deploy) имеет Contents: read+write — его и используем для заливки.
TOKEN = [ln.strip() for ln in TOKEN_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()][0]


async def main() -> None:
    files = collect_files()
    print(f"Файлов к загрузке: {len(files)}")
    async with aiohttp.ClientSession() as session:
        # 0. текущее состояние ветки main (если есть)
        base_commit_sha = None
        async with session.get(
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs/heads/main",
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"},
        ) as resp:
            if resp.status == 200:
                base_commit_sha = (await resp.json())["object"]["sha"]
                print("существующий main:", base_commit_sha)

        if base_commit_sha is None:
            # пустой репозиторий: первый файл через Contents API
            readme = ROOT / "README.md"
            first = await api(
                session,
                "PUT",
                f"https://api.github.com/repos/{OWNER}/{REPO}/contents/README.md",
                {
                    "message": "Initial commit",
                    "content": base64.b64encode(readme.read_bytes()).decode(),
                },
            )
            base_commit_sha = first["commit"]["sha"]
            print("первый коммит:", base_commit_sha)

        # 1. блобы
        tree = []
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            blob = await api(
                session,
                "POST",
                f"https://api.github.com/repos/{OWNER}/{REPO}/git/blobs",
                {"content": base64.b64encode(content).decode(), "encoding": "base64"},
            )
            tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"blob-ов: {len(tree)}")

        tree_res = await api(
            session,
            "POST",
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/trees",
            {"base_tree": base_commit_sha, "tree": tree},
        )
        print("tree:", tree_res["sha"])

        # 2. коммит
        commit = await api(
            session,
            "POST",
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/commits",
            {
                "message": "Fix subscription check for left users; dedupe channels",
                "tree": tree_res["sha"],
                "parents": [base_commit_sha],
            },
        )
        print("commit:", commit["sha"])

        # 3. обновить main
        await api(
            session,
            "PATCH",
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs/heads/main",
            {"sha": commit["sha"], "force": False},
        )

        # 4. проверка
        repo = await api(session, "GET", f"https://api.github.com/repos/{OWNER}/{REPO}")
        print("default_branch:", repo["default_branch"], "| private:", repo["private"])
    print("UPLOAD_OK")


if __name__ == "__main__":
    asyncio.run(main())
