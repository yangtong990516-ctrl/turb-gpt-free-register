# -*- coding: utf-8 -*-
"""解析已有账号导入文本，并使用 AT 补全最新用户名。"""
import math
import re
from concurrent.futures import ThreadPoolExecutor

from core import db
from core.chatgpt_plan import normalize_token, open_plan_check_proxy, resolve_plan_check_route
from core.session import BrowserSession, close_browser_session


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# 分隔符兼容 ``--``、``---``、``----`` 三种样式；量词贪婪，连续的短横线会
# 视为同一个分隔符（``----`` 不会拆成两个 ``--``）。
_FIELD_SEPARATOR_RE = re.compile(r"-{2,}")

# “完整导出”格式（账号页「下载完整导出」生成，可整行回流导入）：
#     邮箱---邮箱接码API---密码---https://2fa.run/----2FA:密钥
# 2FA 段固定带 “2FA:” 前缀，站点占位固定为 https://2fa.run/，密码段可以为空。
# 只按前三个分隔符切分，因此取码链接里的普通短横线不会影响解析。
_EXPORT_LINE_RE = re.compile(r"^(?P<head>.+?)\s*-{2,}\s*2FA:\s*(?P<totp>.*)$", re.IGNORECASE)
_EXPORT_2FA_URL_RE = re.compile(r"^https?://2fa\.run/?$", re.IGNORECASE)
# 2FA 密钥可能被粘贴成 ``2FA:密钥``（旧格式里只会按普通密钥处理）。
_TWOFA_PREFIX_RE = re.compile(r"^2FA:\s*", re.IGNORECASE)

_LEGACY_FORMAT_HINT = "格式错误，需要邮箱、密码、2FA，可选 AT（分隔符可用 --、--- 或 ----）"
_EXPORT_FORMAT_HINT = (
    "格式错误，需要邮箱---密码---2FA[---AT]，或完整导出的 "
    "邮箱---邮箱接码API---密码---https://2fa.run/----2FA:密钥"
)


def _parse_export_line(line: str) -> dict | None:
    """按“完整导出”格式解析一行；不是该格式（没有 ``2FA:`` 段）时返回 None。

    返回字段：email、email_api（邮箱接码API）、password（可为空）、
    totp_secret、access_token，并标记 ``from_full_export``。空字段会被相邻
    分隔符收拢（``------`` 表示空密码），因此第二段按格式约定固定是接码链接。
    """
    match = _EXPORT_LINE_RE.match(line)
    if match is None:
        return None

    # 2FA 段之后如果还跟了 ``--AT``，按旧格式同样支持。
    tail = [part.strip() for part in _FIELD_SEPARATOR_RE.split(match.group("totp"))]
    totp_secret = (tail[0] if tail else "").replace(" ", "")
    access_token = tail[1].strip() if len(tail) > 1 else ""

    head = match.group("head").strip()
    fields = [part.strip() for part in _FIELD_SEPARATOR_RE.split(head)]
    if fields and _EXPORT_2FA_URL_RE.match(fields[-1] or ""):
        fields.pop()
    elif len(fields) < 3:
        # 既没有站点占位，又拆不出“邮箱/接码API/密码”三段：交给旧格式处理，
        # 例如 “邮箱---密码---2FA:密钥”。
        return None

    return {
        "email": fields[0] if fields else "",
        "email_api": fields[1] if len(fields) > 1 else "",
        "password": fields[2] if len(fields) > 2 else "",
        "totp_secret": totp_secret,
        "access_token": access_token or (fields[3] if len(fields) > 3 else ""),
        "from_full_export": True,
    }


def _parse_legacy_line(line: str) -> dict | None:
    """按 ``邮箱--密码--2FA[--AT]`` 解析一行；分隔符不足时返回 None。"""
    parts = [part.strip() for part in _FIELD_SEPARATOR_RE.split(line, maxsplit=3)]
    if len(parts) not in (3, 4):
        return None
    email, password, totp_secret = parts[:3]
    return {
        "email": email,
        "password": password,
        "totp_secret": _TWOFA_PREFIX_RE.sub("", totp_secret).replace(" ", ""),
        "access_token": parts[3] if len(parts) == 4 else "",
    }


def parse_existing_account_text(text: str, *, max_lines: int = 5000) -> tuple[list[dict], list[dict]]:
    """解析已有账号导入文本，返回 (有效记录, 无效行详情)。

    支持两种格式：
      - 旧格式 ``邮箱--密码--2FA[--AT]``；
      - 账号页「完整导出」格式 ``邮箱---邮箱接码API---密码---https://2fa.run/----2FA:密钥``
        （密码段可以为空，导入时会把接码链接回填到通用 API 邮箱池）。

    分隔符兼容 ``--``、``---``、``----`` 三种样式；旧格式只按前三个分隔符切分，
    因此 AT 中的普通短横线不会影响解析。错误详情只返回行号和原因，避免把凭据
    回显到页面。
    """
    records: list[dict] = []
    errors: list[dict] = []
    seen_emails: set[str] = set()
    lines = str(text or "").splitlines()

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if len(records) + len(errors) >= max_lines:
            errors.append({"line": line_number, "reason": f"单次最多导入 {max_lines} 行"})
            break

        record = _parse_export_line(line)
        if record is None:
            record = _parse_legacy_line(line)
        if record is None:
            errors.append({"line": line_number, "reason": f"{_EXPORT_FORMAT_HINT}；或 {_LEGACY_FORMAT_HINT}"})
            continue

        email = record["email"]
        password = record["password"]
        totp_secret = record["totp_secret"]
        if record.get("from_full_export"):
            # 完整导出格式的密码段允许为空（由接码链接兜底登录）。
            if not email or not totp_secret:
                errors.append({"line": line_number, "reason": "邮箱和 2FA 都不能为空"})
                continue
        elif not email or not password or not totp_secret:
            errors.append({"line": line_number, "reason": "邮箱、密码和 2FA 都不能为空"})
            continue
        if not _EMAIL_RE.fullmatch(email):
            errors.append({"line": line_number, "reason": "邮箱格式无效"})
            continue

        email_key = email.casefold()
        if email_key in seen_emails:
            errors.append({"line": line_number, "email": email, "reason": "本次内容中邮箱重复"})
            continue
        seen_emails.add(email_key)
        item = {
            "email": email,
            "password": password,
            "totp_secret": totp_secret,
            "access_token": record["access_token"],
        }
        if record.get("from_full_export"):
            item["email_api"] = record.get("email_api", "")
            item["from_full_export"] = True
        records.append(item)

    return records, errors


_PROFILE_REQUEST_ERROR = "用户名查询请求失败，请稍后重试"


def fetch_account_user_name(access_token: str, *, email: str = "", timeout: float = 15.0) -> dict:
    """使用 AT 查询当前用户名；错误只返回固定消息，不回显凭据或响应。"""
    token = normalize_token(access_token) if isinstance(access_token, str) else ""
    if not token:
        return {"ok": False, "error": "账号缺少 access_token"}
    try:
        timeout_seconds = float(timeout)
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError
        timeout_seconds = max(1.0, min(60.0, timeout_seconds))
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "用户名查询超时配置无效"}

    session = None
    relay = None
    try:
        route = resolve_plan_check_route()
        effective_proxy, relay = open_plan_check_proxy(route, route["proxy"], timeout=timeout_seconds)
        session = BrowserSession(proxy=effective_proxy, detect_exit_geo=False)
        headers = session.get_chatgpt_headers(referer="https://chatgpt.com/")
        headers.pop("content-type", None)
        headers["authorization"] = f"Bearer {token}"
        response = session.get(
            "https://chatgpt.com/backend-api/me", headers=headers,
            timeout=timeout_seconds, allow_redirects=False,
        )
        status = int(response.status_code)
        if not 200 <= status < 300:
            error = {
                401: "AT 已过期或无效，请刷新后重试",
                403: "用户名查询被拒绝，请检查网络后重试",
                429: "用户名查询请求过于频繁，请稍后重试",
            }.get(status, _PROFILE_REQUEST_ERROR)
            return {"ok": False, "error": error}
        try:
            data = response.json()
        except Exception:
            return {"ok": False, "error": "用户名查询响应格式无效"}
        if not isinstance(data, dict):
            return {"ok": False, "error": "用户名查询响应格式无效"}
        expected_email = str(email or "").strip().casefold()
        if expected_email and "email" in data:
            actual_email = data["email"]
            if not isinstance(actual_email, str) or actual_email.strip().casefold() != expected_email:
                return {"ok": False, "error": "AT 对应邮箱与导入邮箱不一致"}
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "error": "用户名查询响应缺少有效姓名"}
        return {"ok": True, "user_name": name.strip()}
    except Exception:
        return {"ok": False, "error": _PROFILE_REQUEST_ERROR}
    finally:
        if session is not None:
            try:
                close_browser_session(session)
            except Exception:
                pass
        if relay is not None:
            try:
                relay.close()
            except Exception:
                pass


def import_existing_accounts(records: list[dict]) -> tuple[int, list[dict], list[dict]]:
    """对解析器验证过的唯一邮箱记录补充姓名，再交由 DB 原子导入。"""
    candidates = []
    skipped_details = []
    for record in records:
        email = record["email"]
        if db.get_account_by_email(email) is not None:
            skipped_details.append({"email": email, "reason": "账号已存在"})
        else:
            candidates.append(dict(record))
    if not candidates:
        return 0, skipped_details, []

    name_details = []
    # 网络查询在 DB 导入锁外执行，单条查询失败仍允许导入账户。
    with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
        futures = [
            executor.submit(fetch_account_user_name, record["access_token"], email=record["email"])
            if record.get("access_token") else None
            for record in candidates
        ]
        for record, future in zip(candidates, futures):
            if future is None:
                continue
            try:
                result = future.result()
            except Exception:
                result = {"ok": False, "error": _PROFILE_REQUEST_ERROR}
            if result.get("ok"):
                record["user_name"] = result["user_name"]
                name_details.append({"email": record["email"], "ok": True, "user_name": result["user_name"]})
            else:
                name_details.append({"email": record["email"], "ok": False, "error": result["error"]})

    inserted, db_skipped = db.import_existing_accounts(candidates)
    skipped_details.extend(db_skipped)
    skipped_emails = {str(item.get("email") or "").strip().casefold() for item in db_skipped}
    name_details = [item for item in name_details if item["email"].strip().casefold() not in skipped_emails]
    return inserted, skipped_details, name_details
