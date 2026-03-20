"""Sub2Api 通用能力。

提供：
- 配置读取与认证
- 连接测试
- 池状态获取
- 自动上传阈值判断
- 自动维护
- 调用独立 Sync HTTP 服务上传
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as cffi_requests
import requests

logger = logging.getLogger(__name__)

SUB2API_ABNORMAL_STATUSES = {"error", "disabled"}


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store

        return config_store.get(key, "")
    except Exception:
        return ""


def set_config_value(key: str, value: str) -> None:
    try:
        from core.config_store import config_store

        config_store.set(key, str(value or ""))
    except Exception:
        pass


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _extract_page_payload(body: Any) -> Dict[str, Any]:
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            return data
        return body
    return {}


def _normalize_status(status: Any) -> str:
    return str(status or "").strip().lower()


def is_abnormal_status(status: Any) -> bool:
    return _normalize_status(status) in SUB2API_ABNORMAL_STATUSES


def login_sub2api(base_url: str, email: str, password: str) -> Tuple[bool, str, str]:
    if not base_url:
        return False, "", "Sub2Api 平台地址未配置"
    if not email:
        return False, "", "Sub2Api 管理员邮箱未配置"
    if not password:
        return False, "", "Sub2Api 管理员密码未配置"

    login_url = base_url.rstrip("/") + "/api/v1/auth/login"
    try:
        resp = cffi_requests.post(
            login_url,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={"email": email, "password": password},
            proxies=None,
            verify=False,
            timeout=20,
            impersonate="chrome110",
        )
        data = resp.json() if resp.text else {}
        if resp.status_code != 200:
            detail = ""
            if isinstance(data, dict):
                detail = str(data.get("message") or data.get("detail") or "")
            return False, "", detail or f"登录失败: HTTP {resp.status_code}"
        token = (
            data.get("token")
            or data.get("access_token")
            or (data.get("data") or {}).get("token")
            or (data.get("data") or {}).get("access_token")
            or ""
        )
        token = str(token or "").strip()
        if not token:
            return False, "", "登录成功但未返回 access_token"
        return True, token, "登录成功"
    except Exception as e:
        return False, "", f"登录异常: {e}"


def verify_sub2api_token(base_url: str, bearer_token: str) -> Tuple[bool, str]:
    if not base_url:
        return False, "Sub2Api 平台地址未配置"
    token = str(bearer_token or "").strip()
    if not token:
        return False, "Sub2Api Bearer Token 未配置"

    verify_url = base_url.rstrip("/") + "/api/v1/admin/accounts"
    try:
        resp = cffi_requests.get(
            verify_url,
            headers=_headers(token),
            params={"page": 1, "page_size": 1, "platform": "openai", "type": "oauth"},
            proxies=None,
            verify=False,
            timeout=15,
            impersonate="chrome110",
        )
        if resp.status_code == 200:
            return True, "Bearer Token 可用"
        if resp.status_code == 401:
            return False, "Bearer Token 无效"
        return False, f"验证失败: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"验证异常: {e}"


def resolve_sub2api_auth(
    base_url: str = "",
    bearer_token: str = "",
    admin_email: str = "",
    admin_password: str = "",
) -> Tuple[bool, str, str]:
    resolved_base_url = str(base_url or get_config_value("sub2api_base_url")).strip()
    resolved_token = str(bearer_token or get_config_value("sub2api_bearer_token")).strip()
    resolved_email = str(admin_email or get_config_value("sub2api_admin_email")).strip()
    resolved_password = str(admin_password or get_config_value("sub2api_admin_password")).strip()

    if resolved_token:
        ok, msg = verify_sub2api_token(resolved_base_url, resolved_token)
        if ok:
            return True, resolved_token, "Bearer Token 可用"
        logger.warning(f"Sub2Api Bearer Token 校验失败，将尝试账号密码重新登录: {msg}")

    ok, new_token, msg = login_sub2api(resolved_base_url, resolved_email, resolved_password)
    if not ok:
        return False, "", msg
    set_config_value("sub2api_bearer_token", new_token)
    return True, new_token, msg


def _request(method: str, base_url: str, bearer_token: str, path: str, **kwargs):
    url = base_url.rstrip("/") + path
    return cffi_requests.request(
        method,
        url,
        headers=_headers(bearer_token),
        proxies=None,
        verify=False,
        timeout=kwargs.pop("timeout", 20),
        impersonate="chrome110",
        **kwargs,
    )


def list_sub2api_accounts(base_url: str, bearer_token: str, page_size: int = 100) -> List[Dict[str, Any]]:
    page = 1
    all_items: List[Dict[str, Any]] = []
    while True:
        resp = _request(
            "GET",
            base_url,
            bearer_token,
            "/api/v1/admin/accounts",
            params={"page": page, "page_size": page_size, "platform": "openai", "type": "oauth"},
            timeout=20,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"获取账号列表失败: HTTP {resp.status_code} {resp.text[:200]}")
        body = resp.json() if resp.text else {}
        data = _extract_page_payload(body)
        items = data.get("items") if isinstance(data.get("items"), list) else []
        all_items.extend([item for item in items if isinstance(item, dict)])
        total = to_int(data.get("total"), 0)
        if len(items) < page_size or (total > 0 and page * page_size >= total):
            break
        page += 1
    return all_items


def _parse_time(raw: Any) -> float:
    text = str(raw or "").strip()
    if not text:
        return 0.0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            continue
    return 0.0


def normalize_account_id(raw: Any) -> Optional[int]:
    try:
        account_id = int(raw)
    except (TypeError, ValueError):
        return None
    return account_id if account_id > 0 else None


def _account_sort_key(item: Dict[str, Any]) -> tuple[float, int]:
    updated = _parse_time(item.get("updated_at") or item.get("updatedAt"))
    account_id = normalize_account_id(item.get("id")) or 0
    return (updated, account_id)


def _account_identity(item: Dict[str, Any]) -> Dict[str, str]:
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    credentials = item.get("credentials") if isinstance(item.get("credentials"), dict) else {}
    email = str(extra.get("email") or item.get("name") or "").strip().lower()
    refresh_token = str(credentials.get("refresh_token") or "").strip()
    return {"email": email, "refresh_token": refresh_token}


def _build_duplicate_delete_ids(all_accounts: List[Dict[str, Any]]) -> List[int]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in all_accounts:
        account_id = normalize_account_id(item.get("id"))
        if account_id is None:
            continue
        identity = _account_identity(item)
        email = identity["email"]
        refresh_token = identity["refresh_token"]
        if email:
            groups.setdefault(f"email:{email}", []).append(item)
        if refresh_token:
            groups.setdefault(f"rt:{refresh_token}", []).append(item)

    duplicate_delete_ids: set[int] = set()
    for items in groups.values():
        if len(items) <= 1:
            continue
        keep = max(items, key=_account_sort_key)
        keep_id = normalize_account_id(keep.get("id"))
        for item in items:
            account_id = normalize_account_id(item.get("id"))
            if account_id is not None and account_id != keep_id:
                duplicate_delete_ids.add(account_id)
    return sorted(duplicate_delete_ids, reverse=True)


def refresh_sub2api_account(base_url: str, bearer_token: str, account_id: int) -> bool:
    resp = _request("POST", base_url, bearer_token, f"/api/v1/admin/accounts/{account_id}/refresh", timeout=30)
    return resp.status_code in (200, 201)


def delete_sub2api_account(base_url: str, bearer_token: str, account_id: int) -> bool:
    resp = _request("DELETE", base_url, bearer_token, f"/api/v1/admin/accounts/{account_id}", timeout=20)
    return resp.status_code in (200, 204)


def get_sub2api_pool_status(
    base_url: str = "",
    bearer_token: str = "",
    admin_email: str = "",
    admin_password: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    resolved_base_url = str(base_url or get_config_value("sub2api_base_url")).strip()
    ok, token, msg = resolve_sub2api_auth(
        resolved_base_url,
        bearer_token=bearer_token,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    if not ok:
        return False, msg, {}
    try:
        accounts = list_sub2api_accounts(resolved_base_url, token)
        abnormal = sum(1 for item in accounts if is_abnormal_status(item.get("status")))
        total = len(accounts)
        normal = max(0, total - abnormal)
        return True, f"连接成功，共 {total} 个账号，{normal} 正常，{abnormal} 异常", {
            "total": total,
            "normal": normal,
            "error": abnormal,
        }
    except Exception as e:
        return False, f"获取 Sub2Api 池状态失败: {e}", {}


def should_upload_sub2api(min_candidates: int = 0) -> Tuple[bool, str]:
    threshold = max(0, to_int(min_candidates, to_int(get_config_value("sub2api_min_candidates"), 0)))
    if threshold <= 0:
        return True, ""
    ok, msg, status = get_sub2api_pool_status()
    if not ok:
        return True, f"Sub2Api 状态获取失败，继续尝试同步: {msg}"
    normal = to_int(status.get("normal"), 0)
    if normal >= threshold:
        return False, f"Sub2Api 正常账号已达目标阈值（{normal}/{threshold}），跳过同步"
    return True, ""


def test_sub2api_connection(
    sync_url: str = "",
    base_url: str = "",
    bearer_token: str = "",
    admin_email: str = "",
    admin_password: str = "",
) -> Tuple[bool, str]:
    resolved_sync_url = str(sync_url or get_config_value("sub2api_sync_url")).strip()
    if resolved_sync_url:
        health_url = resolved_sync_url.rstrip("/")
        if health_url.endswith("/sync"):
            health_url = health_url[:-5]
        health_url = health_url.rstrip("/") + "/health"
        try:
            resp = cffi_requests.get(
                health_url,
                headers={"Accept": "application/json"},
                proxies=None,
                verify=False,
                timeout=10,
                impersonate="chrome110",
            )
            if resp.status_code != 200:
                return False, f"Sync 服务不可用: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Sync 服务不可用: {e}"

    ok, msg, _status = get_sub2api_pool_status(
        base_url=base_url,
        bearer_token=bearer_token,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    return ok, msg


def maintain_sub2api_pool(
    base_url: str = "",
    bearer_token: str = "",
    admin_email: str = "",
    admin_password: str = "",
    refresh_abnormal_accounts: bool = True,
    delete_abnormal_accounts: bool = True,
    dedupe_duplicate_accounts: bool = True,
) -> Tuple[bool, str, Dict[str, Any]]:
    resolved_base_url = str(base_url or get_config_value("sub2api_base_url")).strip()
    ok, token, msg = resolve_sub2api_auth(
        resolved_base_url,
        bearer_token=bearer_token,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    if not ok:
        return False, msg, {}

    try:
        accounts = list_sub2api_accounts(resolved_base_url, token)
        abnormal_ids = [
            account_id
            for item in accounts
            for account_id in [normalize_account_id(item.get("id"))]
            if account_id is not None and is_abnormal_status(item.get("status"))
        ]

        refreshed_ok = 0
        refreshed_fail = 0
        if refresh_abnormal_accounts:
            for account_id in abnormal_ids:
                if refresh_sub2api_account(resolved_base_url, token, account_id):
                    refreshed_ok += 1
                else:
                    refreshed_fail += 1

        if refresh_abnormal_accounts and abnormal_ids:
            time.sleep(2)
            accounts = list_sub2api_accounts(resolved_base_url, token)

        remaining_abnormal_ids = [
            account_id
            for item in accounts
            for account_id in [normalize_account_id(item.get("id"))]
            if account_id is not None and is_abnormal_status(item.get("status"))
        ]

        deleted_abnormal = 0
        if delete_abnormal_accounts:
            for account_id in remaining_abnormal_ids:
                if delete_sub2api_account(resolved_base_url, token, account_id):
                    deleted_abnormal += 1

        if delete_abnormal_accounts and remaining_abnormal_ids:
            accounts = list_sub2api_accounts(resolved_base_url, token)

        duplicate_delete_ids = _build_duplicate_delete_ids(accounts) if dedupe_duplicate_accounts else []
        deleted_duplicates = 0
        for account_id in duplicate_delete_ids:
            if delete_sub2api_account(resolved_base_url, token, account_id):
                deleted_duplicates += 1

        summary = {
            "refreshed_ok": refreshed_ok,
            "refreshed_fail": refreshed_fail,
            "remaining_abnormal": len(remaining_abnormal_ids),
            "deleted_abnormal": deleted_abnormal,
            "duplicate_candidates": len(duplicate_delete_ids),
            "deleted_duplicates": deleted_duplicates,
        }
        return True, (
            f"维护完成：测活成功 {refreshed_ok}，测活失败 {refreshed_fail}，"
            f"删除异常 {deleted_abnormal}，删除重复 {deleted_duplicates}"
        ), summary
    except Exception as e:
        return False, f"Sub2Api 维护失败: {e}", {}


def upload_to_sub2api_http_sync(
    token_data: dict,
    sync_url: str = None,
    base_url: str = None,
    bearer_token: str = None,
    admin_email: str = None,
    admin_password: str = None,
) -> Tuple[bool, str]:
    """通过独立 Sub2Api Sync HTTP 服务上传账号。"""
    if not sync_url:
        sync_url = get_config_value("sub2api_sync_url")
    if not base_url:
        base_url = get_config_value("sub2api_base_url")
    if not bearer_token:
        bearer_token = get_config_value("sub2api_bearer_token")
    if not admin_email:
        admin_email = get_config_value("sub2api_admin_email")
    if not admin_password:
        admin_password = get_config_value("sub2api_admin_password")

    sync_url = (sync_url or "").strip()
    base_url = (base_url or "").strip()
    bearer_token = (bearer_token or "").strip()
    admin_email = (admin_email or "").strip()
    admin_password = (admin_password or "").strip()

    if not sync_url:
        return False, "Sub2Api Sync URL 未配置"

    if base_url:
        ok, resolved_token, auth_msg = resolve_sub2api_auth(
            base_url=base_url,
            bearer_token=bearer_token,
            admin_email=admin_email,
            admin_password=admin_password,
        )
        if not ok:
            return False, auth_msg
        bearer_token = resolved_token
        set_config_value("sub2api_bearer_token", bearer_token)

    url = sync_url.rstrip("/")
    if not url.endswith("/sync"):
        url = url + "/sync"

    payload = {
        "token_data": token_data,
        "base_url": base_url,
        "bearer": bearer_token,
        "check_before": True,
        "check_after": True,
    }
    if not base_url:
        payload.pop("base_url")
    if not bearer_token:
        payload.pop("bearer")

    try:
        resp = requests.post(
            url,
            headers={"Accept": "application/json"},
            json=payload,
            timeout=30,
        )
        body_text = resp.text[:400]
        data = {}
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code in (200, 201) and bool(data.get("ok")):
            result = data.get("result") if isinstance(data.get("result"), dict) else {}
            reason = str(result.get("reason") or "")
            if reason == "updated_existing_before_create":
                return True, f"Sub2Api 已更新现有账号 id={result.get('existing_id')}"
            if result.get("skipped"):
                return True, "Sub2Api 已存在该账号，已跳过"
            return True, "Sub2Api 同步成功"

        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("detail") or data.get("message") or body_text)
        else:
            detail = body_text
        return False, f"Sub2Api 同步失败: HTTP {resp.status_code} - {detail}"
    except Exception as e:
        logger.error(f"Sub2Api Sync 上传异常: {e}")
        return False, f"上传异常: {str(e)}"
