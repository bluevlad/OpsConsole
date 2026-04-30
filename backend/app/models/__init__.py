"""모든 ORM 모델을 한곳에서 import — SQLAlchemy 메타데이터에 모든 테이블 등록.

다른 모듈에서 단일 모델만 import해도 FK 참조 테이블 메타데이터가 누락되지 않도록 보장.
"""
from app.models.audit import OpsAuditLog, OpsManifestSnapshot
from app.models.change_request import OpsChangeRequest, OpsChangeRequestEvent
from app.models.health import OpsAlertState, OpsHealthSnapshot
from app.models.permission import OpsSectionPermission
from app.models.section import OpsSection, OpsSectionAsset
from app.models.service import OpsService
from app.models.user import OpsUser

__all__ = [
    "OpsAlertState",
    "OpsAuditLog",
    "OpsChangeRequest",
    "OpsChangeRequestEvent",
    "OpsHealthSnapshot",
    "OpsManifestSnapshot",
    "OpsSection",
    "OpsSectionAsset",
    "OpsSectionPermission",
    "OpsService",
    "OpsUser",
]
