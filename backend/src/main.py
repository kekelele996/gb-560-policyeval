"""policyeval backend 入口：uvicorn src.main:app"""
from __future__ import annotations

from src.config.app import create_app
from src.utils.logger import get_logger

logger = get_logger("policyeval.main")

app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
