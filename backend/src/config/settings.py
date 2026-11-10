"""集中配置：全部来自环境变量，默认值与 .env.example 保持一致。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # ---- 数据库（MySQL 8.0）----
    DB_NAME: str = "policyeval"
    DB_USER: str = "policyeval"
    DB_PASSWORD: str = "policyeval_pw_2026"
    DB_ROOT_PASSWORD: str = "policyeval_root_pw_2026"
    DB_HOST: str = "db"
    DB_PORT: int = 3306

    # ---- 认证 ----
    JWT_SECRET: str = "policyeval-jwt-secret-lanchuan-bank-2026q4-9f3c"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_DAYS: int = 7

    # ---- 运行时 ----
    REDIS_URL: str = "redis://redis:6379/0"
    SEED_DEMO: bool = True

    # ---- 限流 / 每日配额 ----
    RATE_LIMIT_PER_MINUTE: int = 240
    DAILY_QUOTA_ADMIN: int = 6000
    DAILY_QUOTA_ENGINEER: int = 3600
    DAILY_QUOTA_OWNER: int = 1800

    # ---- 平台默认配额阈值（命名空间无 ResourceQuota 时兜底）----
    PLATFORM_QUOTA_CPU_REQ: float = 48.0
    PLATFORM_QUOTA_MEM_REQ_GIB: float = 96.0
    PLATFORM_QUOTA_CPU_LIM: float = 96.0
    PLATFORM_QUOTA_MEM_LIM_GIB: float = 192.0

    # ---- DSL 安全边界 ----
    DSL_MAX_LENGTH: int = 4000
    DSL_MAX_DEPTH: int = 24
    DSL_MAX_EVIDENCE: int = 40
    REGEX_MAX_LENGTH: int = 120

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    def daily_quota_for(self, role: str) -> int:
        return {
            "admin": self.DAILY_QUOTA_ADMIN,
            "engineer": self.DAILY_QUOTA_ENGINEER,
            "owner": self.DAILY_QUOTA_OWNER,
        }.get(role, 1200)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
