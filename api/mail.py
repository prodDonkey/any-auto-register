from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.base_mailbox import (
    MultiMailboxRouter,
    build_mail_config_store_payload,
    normalize_mail_config,
)
from core.config_store import config_store

router = APIRouter(prefix="/mail", tags=["mail"])


class MailConfigRequest(BaseModel):
    mail_providers: list[str] = Field(default_factory=list)
    mail_provider_configs: dict = Field(default_factory=dict)
    mail_strategy: str = "round_robin"


@router.get("/config")
def get_mail_config():
    cfg = config_store.get_all()
    return normalize_mail_config(cfg)


@router.post("/config")
def save_mail_config(body: MailConfigRequest):
    payload = build_mail_config_store_payload(
        mail_providers=body.mail_providers,
        mail_provider_configs=body.mail_provider_configs,
        mail_strategy=body.mail_strategy,
    )
    config_store.set_many(payload)
    return {"ok": True}


@router.post("/test")
def test_mail_config():
    cfg = config_store.get_all()
    try:
        router = MultiMailboxRouter(cfg)
    except Exception as e:
        return {"ok": False, "message": str(e), "results": []}

    results = []
    for provider_name, mailbox in router.providers():
        ok, message = mailbox.test_connection()
        results.append({
            "provider": provider_name,
            "ok": ok,
            "message": message,
        })

    all_ok = all(item["ok"] for item in results) if results else False
    return {
        "ok": all_ok,
        "message": "全部通过" if all_ok else "部分失败",
        "results": results,
    }
