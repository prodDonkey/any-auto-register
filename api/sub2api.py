from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from core.db import AccountModel, get_session

from core.sub2api import (
    get_sub2api_pool_status,
    maintain_sub2api_pool,
    test_sub2api_connection,
    upload_to_sub2api_http_sync,
)

router = APIRouter(prefix="/sub2api", tags=["sub2api"])


class Sub2ApiConfigRequest(BaseModel):
    sync_url: str = ""
    base_url: str = ""
    bearer_token: str = ""
    admin_email: str = ""
    admin_password: str = ""
    refresh_abnormal_accounts: bool = True
    delete_abnormal_accounts: bool = True
    dedupe_duplicate_accounts: bool = True


class Sub2ApiBatchSyncRequest(BaseModel):
    account_ids: list[int]


@router.post("/test")
def test_connection(body: Sub2ApiConfigRequest):
    ok, message = test_sub2api_connection(
        sync_url=body.sync_url,
        base_url=body.base_url,
        bearer_token=body.bearer_token,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
    )
    return {"ok": ok, "message": message}


@router.get("/status")
def pool_status():
    ok, message, status = get_sub2api_pool_status()
    return {"ok": ok, "message": message, "status": status}


@router.post("/maintain")
def maintain(body: Sub2ApiConfigRequest):
    ok, message, detail = maintain_sub2api_pool(
        base_url=body.base_url,
        bearer_token=body.bearer_token,
        admin_email=body.admin_email,
        admin_password=body.admin_password,
        refresh_abnormal_accounts=body.refresh_abnormal_accounts,
        delete_abnormal_accounts=body.delete_abnormal_accounts,
        dedupe_duplicate_accounts=body.dedupe_duplicate_accounts,
    )
    return {"ok": ok, "message": message, "detail": detail}


@router.post("/sync-accounts")
def sync_accounts(body: Sub2ApiBatchSyncRequest, session: Session = Depends(get_session)):
    from platforms.chatgpt.cpa_upload import generate_token_json

    results = []
    seen_ids = set()
    for account_id in body.account_ids or []:
        try:
            normalized_id = int(account_id)
        except (TypeError, ValueError):
            continue
        if normalized_id <= 0 or normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)

        acc = session.get(AccountModel, normalized_id)
        if not acc:
            results.append({"id": normalized_id, "ok": False, "message": "账号不存在"})
            continue
        if acc.platform != "chatgpt":
            results.append({"id": normalized_id, "email": acc.email, "ok": False, "message": "当前仅支持 ChatGPT 账号"})
            continue

        extra = acc.get_extra()

        class _Acc:
            pass

        a = _Acc()
        a.email = acc.email
        a.access_token = extra.get("access_token") or acc.token
        a.refresh_token = extra.get("refresh_token", "")
        a.id_token = extra.get("id_token", "")

        token_data = generate_token_json(a)
        ok, message = upload_to_sub2api_http_sync(token_data)
        results.append({
            "id": acc.id,
            "email": acc.email,
            "ok": ok,
            "message": message,
        })

    success = sum(1 for item in results if item.get("ok"))
    fail = len(results) - success
    return {
        "ok": fail == 0,
        "summary": {
            "total": len(results),
            "success": success,
            "fail": fail,
        },
        "results": results,
    }
