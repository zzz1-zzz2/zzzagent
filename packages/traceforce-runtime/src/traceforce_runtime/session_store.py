"""会话仓库：在 workspace 内创建、列出、恢复、删除和分叉 JSONL 会话。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from traceforce_runtime.session import Session


class SessionMeta(BaseModel):
    """会话元信息（list() 用）。"""

    id: str
    path: Path
    created_at: str
    entries: int


class SessionStore:
    """会话仓库：每个会话对应 workspace/root 下的一个 JSONL 文件。"""

    def __init__(self, root: str | Path = ".traceforce/sessions",
                 workspace: str | Path | None = None):
        """workspace 默认 Path.cwd()；相对 root 位于 workspace 下。"""
        self.workspace = Path(workspace) if workspace else Path.cwd()
        root_path = Path(root)
        self.root = root_path if root_path.is_absolute() else self.workspace / root_path

    def create(self) -> Session:
        """新会话：写 <root>/<id>.jsonl（不含 system）。Session.cwd = workspace。"""
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            sid = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
            path = self.root / f"{sid}.jsonl"
            if not path.exists():
                session = Session(path=path, cwd=str(self.workspace))
                session.id = sid
                session.save()
                return session

    def list(self) -> list[SessionMeta]:
        """全部会话，按 created_at 倒序（新→旧）。损坏/缺字段文件跳过。"""
        metas: list[SessionMeta] = []
        for f in self.root.glob("*.jsonl"):
            try:
                with open(f, encoding="utf-8") as fh:
                    header = json.loads(fh.readline())
                    entries = sum(1 for _ in fh)
                metas.append(
                    SessionMeta(
                        id=header["id"], path=f,
                        created_at=header["created_at"], entries=entries,
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue
        metas.sort(key=lambda m: m.created_at, reverse=True)
        return metas

    def _resolve(self, id_or_prefix: str) -> Path:
        """全 id 或唯一前缀 → 文件路径；未找到/歧义 → ValueError。"""
        matches: list[Path] = []
        for f in self.root.glob("*.jsonl"):
            try:
                with open(f, encoding="utf-8") as fh:
                    header = json.loads(fh.readline())
                if header.get("id", "").startswith(id_or_prefix):
                    matches.append(f)
            except (json.JSONDecodeError, KeyError):
                continue
        if not matches:
            raise ValueError(f"Session not found: {id_or_prefix}")
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous session prefix {id_or_prefix!r}: "
                f"candidates {[m.stem for m in matches]}"
            )
        return matches[0]

    def open(self, id_or_prefix: str) -> Session:
        """按 id 或唯一前缀打开会话（恢复整棵树）。"""
        return Session.load(self._resolve(id_or_prefix))

    def delete(self, id_or_prefix: str) -> None:
        """删除会话文件。未找到 → ValueError。"""
        self._resolve(id_or_prefix).unlink()

    def fork(self, id_or_prefix: str, entry_id: str) -> Session:
        """从某会话 entry 分叉：复制根→entry 路径为新会话（新 id/路径，独立演化）。"""
        src = self.open(id_or_prefix)
        new = self.create()
        for entry in src.tree.get_path_to_entry(entry_id):
            new.add_message(entry.role, entry.content, **entry.metadata)
        return new