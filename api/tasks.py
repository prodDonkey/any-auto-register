from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from typing import Optional
from pathlib import Path
from core.db import TaskLog, engine
import time, json, asyncio, threading

router = APIRouter(prefix="/tasks", tags=["tasks"])

_tasks: dict = {}
_tasks_lock = threading.Lock()

MAX_FINISHED_TASKS = 200
CLEANUP_THRESHOLD = 250
TOKEN_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "tokens"


def _cleanup_old_tasks():
    """Remove oldest finished tasks when the dict grows too large."""
    with _tasks_lock:
        finished = [
            (tid, t) for tid, t in _tasks.items()
            if t.get("status") in ("done", "failed")
        ]
        if len(finished) <= MAX_FINISHED_TASKS:
            return
        finished.sort(key=lambda x: x[0])
        to_remove = finished[: len(finished) - MAX_FINISHED_TASKS]
        for tid, _ in to_remove:
            del _tasks[tid]


class RegisterTaskRequest(BaseModel):
    platform: str
    email: Optional[str] = None
    password: Optional[str] = None
    count: int = 1
    concurrency: int = 1
    proxy: Optional[str] = None
    executor_type: str = "protocol"
    captcha_solver: str = "yescaptcha"
    extra: dict = Field(default_factory=dict)


def _log(task_id: str, msg: str):
    """向任务追加一条日志"""
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].setdefault("logs", []).append(entry)
    print(entry)


def _save_task_log(platform: str, email: str, status: str,
                   error: str = "", detail: dict = None):
    """Write a TaskLog record to the database."""
    with Session(engine) as s:
        log = TaskLog(
            platform=platform,
            email=email,
            status=status,
            error=error,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
        s.add(log)
        s.commit()


def _auto_upload_cpa(task_id: str, account):
    """注册成功后自动上传 CPA（仅 chatgpt 平台，且已配置时）"""
    if getattr(account, "platform", "") != "chatgpt":
        return
    try:
        from core.config_store import config_store
        cpa_url = config_store.get("cpa_api_url", "")
        if cpa_url:
            from platforms.chatgpt.cpa_upload import generate_token_json, upload_to_cpa

            class _A: pass
            a = _A()
            a.email = account.email
            extra = account.extra or {}
            a.access_token = extra.get("access_token") or account.token
            a.refresh_token = extra.get("refresh_token", "")
            a.id_token = extra.get("id_token", "")

            token_data = generate_token_json(a)
            ok, msg = upload_to_cpa(token_data)
            _log(task_id, f"  [CPA] {'✓ ' + msg if ok else '✗ ' + msg}")
    except Exception as e:
        _log(task_id, f"  [CPA] 自动上传异常: {e}")


def _auto_upload_sub2api(task_id: str, account):
    """注册成功后自动上传 Sub2Api（仅 chatgpt 平台，且已配置时）。"""
    if getattr(account, "platform", "") != "chatgpt":
        return
    try:
        from core.config_store import config_store
        from core.sub2api import as_bool

        sync_url = config_store.get("sub2api_sync_url", "")
        auto_sync_raw = config_store.get("sub2api_auto_sync", "")
        auto_sync_enabled = bool(sync_url) if str(auto_sync_raw).strip() == "" else as_bool(auto_sync_raw)
        if sync_url and auto_sync_enabled:
            from core.sub2api import should_upload_sub2api, upload_to_sub2api_http_sync
            from platforms.chatgpt.cpa_upload import generate_token_json

            min_candidates = config_store.get("sub2api_min_candidates", "0")
            should_upload, reason = should_upload_sub2api(min_candidates=min_candidates)
            if not should_upload:
                _log(task_id, f"  [Sub2Api] - {reason}")
                return
            if reason:
                _log(task_id, f"  [Sub2Api] - {reason}")

            class _A:
                pass

            a = _A()
            a.email = account.email
            extra = account.extra or {}
            a.access_token = extra.get("access_token") or account.token
            a.refresh_token = extra.get("refresh_token", "")
            a.id_token = extra.get("id_token", "")

            token_data = generate_token_json(a)
            ok, msg = upload_to_sub2api_http_sync(token_data)
            _log(task_id, f"  [Sub2Api] {'✓ ' + msg if ok else '✗ ' + msg}")
    except Exception as e:
        _log(task_id, f"  [Sub2Api] 自动上传异常: {e}")


def _save_local_token_json(task_id: str, account):
    """注册成功后导出本地 token JSON（仅 chatgpt 平台）。"""
    if getattr(account, "platform", "") != "chatgpt":
        return
    try:
        from platforms.chatgpt.cpa_upload import generate_token_json

        class _A: pass
        a = _A()
        a.email = account.email
        extra = account.extra or {}
        a.access_token = extra.get("access_token") or account.token
        a.refresh_token = extra.get("refresh_token", "")
        a.id_token = extra.get("id_token", "")

        token_data = generate_token_json(a)
        TOKEN_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        safe_email = "".join(ch if ch.isalnum() or ch in ("@", ".", "-", "_") else "_" for ch in account.email)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = TOKEN_EXPORT_DIR / f"{timestamp}-{safe_email}.json"
        output_path.write_text(
            json.dumps(token_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _log(task_id, f"  [本地保存] ✓ {output_path}")
    except Exception as e:
        _log(task_id, f"  [本地保存] ✗ {e}")


def _run_register(task_id: str, req: RegisterTaskRequest):
    from core.registry import get
    from core.base_platform import RegisterConfig
    from core.db import save_account
    from core.base_mailbox import MultiMailboxRouter, normalize_mail_config
    from core.config_store import config_store

    with _tasks_lock:
        _tasks[task_id]["status"] = "running"
    success = 0
    errors = []

    try:
        PlatformCls = get(req.platform)
        stored_cfg = config_store.get_all()
        request_extra = {k: v for k, v in (req.extra or {}).items() if v not in (None, "")}
        effective_extra = dict(stored_cfg)
        effective_extra.update(request_extra)

        mail_keys = {
            "mail_provider", "mail_providers", "mail_provider_configs", "mail_strategy",
            "laoudo_auth", "laoudo_email", "laoudo_account_id",
            "tempmail_api_url",
            "duckmail_api_url", "duckmail_provider_url", "duckmail_bearer",
            "freemail_api_url", "freemail_admin_token", "freemail_username", "freemail_password",
            "moemail_api_url",
            "cfworker_api_url", "cfworker_admin_token", "cfworker_domain", "cfworker_fingerprint",
        }
        stored_has_router = any(str(stored_cfg.get(key, "")).strip() for key in ("mail_providers", "mail_provider_configs", "mail_strategy"))
        request_has_router = any(request_extra.get(key) not in (None, "", [], {}) for key in ("mail_providers", "mail_provider_configs", "mail_strategy"))
        if request_has_router:
            mail_cfg_source = dict(stored_cfg)
            for key in mail_keys:
                if key in request_extra:
                    mail_cfg_source[key] = request_extra[key]
        elif stored_has_router:
            mail_cfg_source = dict(stored_cfg)
        else:
            mail_cfg_source = dict(stored_cfg)
            for key in mail_keys:
                if key in request_extra:
                    mail_cfg_source[key] = request_extra[key]

        normalized_mail_cfg = normalize_mail_config(mail_cfg_source)
        effective_extra.update(normalized_mail_cfg)
        mail_router = MultiMailboxRouter(effective_extra)

        config = RegisterConfig(
            executor_type=req.executor_type,
            captcha_solver=req.captcha_solver,
            proxy=req.proxy,
            extra=effective_extra,
        )
        def _do_one(i: int):
            from core.proxy_pool import proxy_pool
            _proxy = req.proxy
            if not _proxy:
                _proxy = proxy_pool.get_next()
            provider_name, mailbox = mail_router.next_mailbox(proxy=_proxy)
            attempt_extra = dict(effective_extra)
            attempt_extra["mail_provider"] = provider_name
            _config = RegisterConfig(
                executor_type=req.executor_type,
                captcha_solver=req.captcha_solver,
                proxy=_proxy,
                extra=attempt_extra,
            )
            _platform = PlatformCls(config=_config, mailbox=mailbox)
            _platform._log_fn = lambda msg: _log(task_id, msg)
            try:
                with _tasks_lock:
                    _tasks[task_id]["progress"] = f"{i+1}/{req.count}"
                _log(task_id, f"开始注册第 {i+1}/{req.count} 个账号")
                if _proxy: _log(task_id, f"使用代理: {_proxy}")
                _log(task_id, f"使用邮箱提供商: {provider_name}")
                account = _platform.register(
                    email=req.email or None,
                    password=req.password,
                )
                mail_router.report_success(provider_name)
                save_account(account)
                _save_local_token_json(task_id, account)
                if _proxy: proxy_pool.report_success(_proxy)
                _log(task_id, f"✓ 注册成功: {account.email}")
                _save_task_log(req.platform, account.email, "success")
                _auto_upload_cpa(task_id, account)
                _auto_upload_sub2api(task_id, account)
                cashier_url = (account.extra or {}).get("cashier_url", "")
                if cashier_url:
                    _log(task_id, f"  [升级链接] {cashier_url}")
                    with _tasks_lock:
                        _tasks[task_id].setdefault("cashier_urls", []).append(cashier_url)
                return True
            except Exception as e:
                mail_router.report_failure(provider_name)
                if _proxy: proxy_pool.report_fail(_proxy)
                _log(task_id, f"✗ 注册失败: {e}")
                _save_task_log(req.platform, req.email or "", "failed", error=str(e))
                return str(e)

        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = min(req.concurrency, req.count, 5)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_do_one, i) for i in range(req.count)]
            for f in as_completed(futures):
                result = f.result()
                if result is True:
                    success += 1
                else:
                    errors.append(result)
    except Exception as e:
        _log(task_id, f"致命错误: {e}")
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)
        return

    with _tasks_lock:
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["success"] = success
        _tasks[task_id]["errors"] = errors
    _log(task_id, f"完成: 成功 {success} 个, 失败 {len(errors)} 个")
    _cleanup_old_tasks()


@router.post("/register")
def create_register_task(
    req: RegisterTaskRequest,
    background_tasks: BackgroundTasks,
):
    task_id = f"task_{int(time.time()*1000)}"
    with _tasks_lock:
        _tasks[task_id] = {"id": task_id, "status": "pending",
                           "progress": f"0/{req.count}", "logs": []}
    background_tasks.add_task(_run_register, task_id, req)
    return {"task_id": task_id}


@router.get("/logs")
def get_logs(platform: str = None, page: int = 1, page_size: int = 50):
    with Session(engine) as s:
        q = select(TaskLog)
        if platform:
            q = q.where(TaskLog.platform == platform)
        q = q.order_by(TaskLog.id.desc())
        total = len(s.exec(q).all())
        items = s.exec(q.offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": items}


@router.get("/{task_id}/logs/stream")
async def stream_logs(task_id: str, since: int = 0):
    """SSE 实时日志流"""
    with _tasks_lock:
        if task_id not in _tasks:
            raise HTTPException(404, "任务不存在")

    async def event_generator():
        sent = since
        while True:
            with _tasks_lock:
                logs = list(_tasks.get(task_id, {}).get("logs", []))
                status = _tasks.get(task_id, {}).get("status", "")
            while sent < len(logs):
                yield f"data: {json.dumps({'line': logs[sent]})}\n\n"
                sent += 1
            if status in ("done", "failed"):
                yield f"data: {json.dumps({'done': True, 'status': status})}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}")
def get_task(task_id: str):
    with _tasks_lock:
        if task_id not in _tasks:
            raise HTTPException(404, "任务不存在")
        return _tasks[task_id]


@router.get("")
def list_tasks():
    with _tasks_lock:
        return list(_tasks.values())
