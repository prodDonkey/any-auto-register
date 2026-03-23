from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, func
from pydantic import BaseModel
from core.db import AccountModel, get_session
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
import io, csv, json, logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])
TOKEN_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "tokens"


class AccountCreate(BaseModel):
    platform: str
    email: str
    password: str
    status: str = "registered"
    token: str = ""
    cashier_url: str = ""


class AccountUpdate(BaseModel):
    status: Optional[str] = None
    token: Optional[str] = None
    cashier_url: Optional[str] = None


class ImportRequest(BaseModel):
    platform: str
    lines: list[str]


class ExportJsonRequest(BaseModel):
    platform: Optional[str] = None
    account_ids: list[int] = []


@router.get("")
def list_accounts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    email: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: Session = Depends(get_session),
):
    q = select(AccountModel)
    if platform:
        q = q.where(AccountModel.platform == platform)
    if status:
        q = q.where(AccountModel.status == status)
    if email:
        q = q.where(AccountModel.email.contains(email))
    total = len(session.exec(q).all())
    items = session.exec(q.offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "items": items}


@router.post("")
def create_account(body: AccountCreate, session: Session = Depends(get_session)):
    acc = AccountModel(
        platform=body.platform,
        email=body.email,
        password=body.password,
        status=body.status,
        token=body.token,
        cashier_url=body.cashier_url,
    )
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


@router.get("/stats")
def get_stats(session: Session = Depends(get_session)):
    """统计各平台账号数量和状态分布"""
    accounts = session.exec(select(AccountModel)).all()
    platforms: dict = {}
    statuses: dict = {}
    for acc in accounts:
        platforms[acc.platform] = platforms.get(acc.platform, 0) + 1
        statuses[acc.status] = statuses.get(acc.status, 0) + 1
    return {"total": len(accounts), "by_platform": platforms, "by_status": statuses}


@router.get("/export")
def export_accounts(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    q = select(AccountModel)
    if platform:
        q = q.where(AccountModel.platform == platform)
    if status:
        q = q.where(AccountModel.status == status)
    accounts = session.exec(q).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["platform", "email", "password", "user_id", "region",
                     "status", "cashier_url", "created_at"])
    for acc in accounts:
        writer.writerow([acc.platform, acc.email, acc.password, acc.user_id,
                         acc.region, acc.status, acc.cashier_url,
                         acc.created_at.strftime("%Y-%m-%d %H:%M:%S")])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=accounts.csv"}
    )


def _safe_export_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in (".", "@", "-", "_") else "_" for ch in text)


def _account_json_payload(acc: AccountModel) -> dict:
    extra = acc.get_extra()
    if acc.platform == "kiro":
        return {
            "type": "kiro",
            "email": acc.email,
            "expired": str(extra.get("expiresAt") or ""),
            "id_token": "",
            "account_id": acc.user_id or "",
            "access_token": str(extra.get("accessToken") or acc.token or ""),
            "session_token": str(extra.get("sessionToken") or ""),
            "client_id": str(extra.get("clientId") or ""),
            "client_secret": str(extra.get("clientSecret") or ""),
            "last_refresh": (acc.updated_at or acc.created_at).astimezone().isoformat(timespec="seconds"),
            "refresh_token": str(extra.get("refreshToken") or ""),
            "name": str(extra.get("name") or ""),
        }
    payload = {
        "id": acc.id,
        "platform": acc.platform,
        "email": acc.email,
        "password": acc.password,
        "user_id": acc.user_id,
        "region": acc.region,
        "token": acc.token,
        "status": acc.status,
        "cashier_url": acc.cashier_url,
        "created_at": acc.created_at.isoformat() if acc.created_at else "",
        "updated_at": acc.updated_at.isoformat() if acc.updated_at else "",
    }
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _export_filename(acc: AccountModel) -> str:
    stamp = (acc.updated_at or acc.created_at).astimezone().strftime("%Y%m%d-%H%M%S")
    safe_email = _safe_export_name(acc.email or f"account_{acc.id}")
    if acc.platform == "kiro":
        return f"{stamp}-{safe_email}.json"
    return f"{acc.platform}-{acc.id}-{safe_email}.json"


@router.post("/export-json-local")
def export_accounts_json_local(
    body: ExportJsonRequest,
    session: Session = Depends(get_session),
):
    q = select(AccountModel)
    if body.platform:
        q = q.where(AccountModel.platform == body.platform)
    if body.account_ids:
        q = q.where(AccountModel.id.in_(body.account_ids))
    accounts = session.exec(q).all()
    if not accounts:
        return {"ok": False, "message": "没有可导出的账号", "count": 0, "files": []}

    TOKEN_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    for acc in accounts:
        target_dir = TOKEN_EXPORT_DIR / acc.platform
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = _export_filename(acc)
        output_path = target_dir / filename
        output_path.write_text(
            json.dumps(_account_json_payload(acc), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files.append(str(output_path))

    return {
        "ok": True,
        "message": f"已导出 {len(files)} 个 JSON 文件",
        "count": len(files),
        "dir": str(TOKEN_EXPORT_DIR / (body.platform or "mixed")),
        "files": files,
    }


@router.post("/import")
def import_accounts(
    body: ImportRequest,
    session: Session = Depends(get_session),
):
    """批量导入，每行格式: email password [extra]"""
    created = 0
    for line in body.lines:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        email, password = parts[0], parts[1]
        extra = parts[2] if len(parts) > 2 else ""
        if extra:
            try:
                json.loads(extra)
            except (json.JSONDecodeError, ValueError):
                extra = "{}"
        else:
            extra = "{}"
        acc = AccountModel(platform=body.platform, email=email,
                           password=password, extra_json=extra)
        session.add(acc)
        created += 1
    session.commit()
    return {"created": created}


@router.post("/check-all")
def check_all_accounts(platform: Optional[str] = None,
                       background_tasks: BackgroundTasks = None):
    from core.scheduler import scheduler
    background_tasks.add_task(scheduler.check_accounts_valid, platform)
    return {"message": "批量检测任务已启动"}


@router.get("/{account_id}")
def get_account(account_id: int, session: Session = Depends(get_session)):
    acc = session.get(AccountModel, account_id)
    if not acc:
        raise HTTPException(404, "账号不存在")
    return acc


@router.patch("/{account_id}")
def update_account(account_id: int, body: AccountUpdate,
                   session: Session = Depends(get_session)):
    acc = session.get(AccountModel, account_id)
    if not acc:
        raise HTTPException(404, "账号不存在")
    if body.status is not None:
        acc.status = body.status
    if body.token is not None:
        acc.token = body.token
    if body.cashier_url is not None:
        acc.cashier_url = body.cashier_url
    acc.updated_at = datetime.now(timezone.utc)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


@router.delete("/{account_id}")
def delete_account(account_id: int, session: Session = Depends(get_session)):
    acc = session.get(AccountModel, account_id)
    if not acc:
        raise HTTPException(404, "账号不存在")
    session.delete(acc)
    session.commit()
    return {"ok": True}


@router.post("/{account_id}/check")
def check_account(account_id: int, background_tasks: BackgroundTasks,
                  session: Session = Depends(get_session)):
    acc = session.get(AccountModel, account_id)
    if not acc:
        raise HTTPException(404, "账号不存在")
    background_tasks.add_task(_do_check, account_id)
    return {"message": "检测任务已启动"}


def _do_check(account_id: int):
    from core.db import engine
    from sqlmodel import Session
    with Session(engine) as s:
        acc = s.get(AccountModel, account_id)
    if acc:
        from core.base_platform import Account, RegisterConfig
        from core.registry import get
        try:
            PlatformCls = get(acc.platform)
            plugin = PlatformCls(config=RegisterConfig())
            obj = Account(platform=acc.platform, email=acc.email,
                         password=acc.password, user_id=acc.user_id,
                         region=acc.region, token=acc.token,
                         extra=json.loads(acc.extra_json or "{}"))
            valid = plugin.check_valid(obj)
            with Session(engine) as s:
                a = s.get(AccountModel, account_id)
                if a:
                    a.status = a.status if valid else "invalid"
                    a.updated_at = datetime.now(timezone.utc)
                    s.add(a)
                    s.commit()
        except Exception:
            logger.exception("检测账号 %s 时出错", account_id)
