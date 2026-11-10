from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base

RawYaml = Text().with_variant(LONGTEXT, "mysql")


class ManifestBundle(Base):
    """一次 GitOps 导出的 K8s 清单包：原始 YAML + 解析后的文档树。"""

    __tablename__ = "manifest_bundles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="gitops")
    cluster: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    k8s_version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    namespace_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_tree: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    raw_yaml: Mapped[str] = mapped_column(RawYaml, nullable=False, default="")
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    imported_by: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
