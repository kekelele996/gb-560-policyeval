"""模型注册入口：alembic / create_all 通过本模块拿到全部表。"""
from src.config.database import Base
from src.models.audit_log import AuditLog
from src.models.evaluation_run import EvaluationRun
from src.models.exemption import Exemption
from src.models.manifest_bundle import ManifestBundle
from src.models.policy_rule import PolicyRule
from src.models.remediation_advice import RemediationAdvice
from src.models.user import User
from src.models.violation import Violation

__all__ = [
    "Base",
    "AuditLog",
    "EvaluationRun",
    "Exemption",
    "ManifestBundle",
    "PolicyRule",
    "RemediationAdvice",
    "User",
    "Violation",
]
