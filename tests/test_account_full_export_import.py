# -*- coding: utf-8 -*-
"""完整导出格式回流导入：邮箱---邮箱接码API---密码---https://2fa.run/----2FA:密钥。"""
import json

import pytest

from core import account_import, db, live_check_service
from core.account_import import parse_existing_account_text

SAMPLE_EMAIL = "mask-submit@outputgarment-mail.jiayuhongwedding.com"
SAMPLE_RAW_API = (
    "https//mail.antsgo.xyz/pick-mail?code=9490d85567502658b9041dfa2c30a816f3f5fac3"
    "&mail=mask-submit%40outputgarment-mail.jiayuhongwedding.com"
)
SAMPLE_CODE_URL = SAMPLE_RAW_API.replace("https//", "https://", 1)
SAMPLE_TOTP = "RIXHEO6GTYZ7CX6CUN4OLKVSYCSOKVKZ"
SAMPLE_LINE = f"{SAMPLE_EMAIL}---{SAMPLE_RAW_API}------https://2fa.run/----2FA:{SAMPLE_TOTP}"


def test_parser_recognizes_full_export_line_with_empty_password():
    records, errors = parse_existing_account_text(SAMPLE_LINE)

    assert errors == []
    assert records == [{
        "email": SAMPLE_EMAIL,
        "password": "",
        "totp_secret": SAMPLE_TOTP,
        "access_token": "",
        "email_api": SAMPLE_RAW_API,
        "from_full_export": True,
    }]


@pytest.mark.parametrize(
    "line, email_api, password",
    [
        # 站点占位 + 四段齐全
        ("a@b.com---gptmail---Pass123---https://2fa.run/----2FA:ABC", "gptmail", "Pass123"),
        # 空密码段被相邻 “---” 收拢成 “------”
        ("a@b.com---gptmail------https://2fa.run/----2FA:ABC", "gptmail", ""),
        # 接码API 与密码都为空
        ("a@b.com---------https://2fa.run/----2FA:ABC", "", ""),
        # 没有站点占位，但仍是“邮箱/接码API/密码”三段
        ("a@b.com---gptmail---Pass123----2FA:ABC", "gptmail", "Pass123"),
    ],
)
def test_parser_full_export_variants(line, email_api, password):
    records, errors = parse_existing_account_text(line)

    assert errors == []
    assert len(records) == 1
    assert records[0]["email"] == "a@b.com"
    assert records[0]["email_api"] == email_api
    assert records[0]["password"] == password
    assert records[0]["totp_secret"] == "ABC"
    assert records[0]["from_full_export"] is True


def test_parser_full_export_supports_trailing_at():
    records, errors = parse_existing_account_text(
        "a@b.com---gptmail------https://2fa.run/----2FA:ABC---eyJ.d-e-f"
    )

    assert errors == []
    assert records[0]["totp_secret"] == "ABC"
    assert records[0]["access_token"] == "eyJ.d-e-f"


def test_parser_full_export_requires_totp():
    records, errors = parse_existing_account_text(
        "a@b.com---gptmail---Pass123---https://2fa.run/----2FA:"
    )

    assert records == []
    assert errors[0]["reason"] == "邮箱和 2FA 都不能为空"


def test_parser_legacy_line_strips_twofa_prefix_without_export_marker():
    records, errors = parse_existing_account_text("a@b.com---pw----2FA:ABC")

    assert errors == []
    assert records == [{
        "email": "a@b.com",
        "password": "pw",
        "totp_secret": "ABC",
        "access_token": "",
    }]


def test_normalize_code_url_repairs_missing_colon():
    assert db._normalize_generic_api_code_url(SAMPLE_RAW_API) == SAMPLE_CODE_URL
    assert db._normalize_generic_api_code_url("--https://x/y") == "https://x/y"
    assert db._normalize_generic_api_code_url("https://2fa.run/") == "https://2fa.run/"
    # 来源标识不是链接，原样保留
    assert db._normalize_generic_api_code_url("gptmail") == "gptmail"


def _patch_import(monkeypatch, accounts, pool):
    monkeypatch.setattr(db, "_load_accounts", lambda: accounts)
    monkeypatch.setattr(db, "_save_accounts", lambda rows: None)
    monkeypatch.setattr(db, "_load_generic_api_emails", lambda: pool)
    saved_pools = []
    monkeypatch.setattr(db, "_save_generic_api_emails", lambda rows: saved_pools.append(list(rows)))
    return saved_pools


def test_db_import_backfills_code_url_into_generic_api_pool(monkeypatch):
    records, errors = parse_existing_account_text(SAMPLE_LINE)
    assert errors == []
    accounts, pool = [], []
    saved_pools = _patch_import(monkeypatch, accounts, pool)

    inserted, skipped = db.import_existing_accounts(records)

    assert (inserted, skipped) == (1, [])
    account = accounts[0]
    assert account["email_source"] == "generic_api"
    assert account["totp_secret"] == SAMPLE_TOTP
    assert account["access_token"] == ""
    assert json.loads(account["extra_json"])["registration_password"] == ""
    assert account["original_email_line"] == f"{SAMPLE_EMAIL}----{SAMPLE_CODE_URL}"
    assert len(pool) == 1
    assert pool[0]["email"] == SAMPLE_EMAIL
    assert pool[0]["code_url"] == SAMPLE_CODE_URL
    assert pool[0]["status"] == "used"
    assert pool[0]["registered_account_id"] == account["id"]
    assert saved_pools


def test_full_export_line_survives_round_trip(monkeypatch):
    """完整导出行导入后重新导出，应回到同样的行（接码链接按规范补全冒号）。"""
    records, errors = parse_existing_account_text(SAMPLE_LINE)
    assert errors == []
    accounts, pool = [], []
    _patch_import(monkeypatch, accounts, pool)
    db.import_existing_accounts(records)

    line = db._account_full_export_line(accounts[0])

    assert line == f"{SAMPLE_EMAIL}---{SAMPLE_CODE_URL}------https://2fa.run/----2FA:{SAMPLE_TOTP}"
    # 补全冒号后的行可以再次导入
    again, again_errors = parse_existing_account_text(line)
    assert again_errors == []
    assert again[0]["email_api"] == SAMPLE_CODE_URL
    assert again[0]["totp_secret"] == SAMPLE_TOTP


def test_db_import_reuses_existing_pool_row(monkeypatch):
    records, _ = parse_existing_account_text(SAMPLE_LINE)
    accounts = []
    pool = [{"id": 7, "email": SAMPLE_EMAIL, "code_url": "http://old/code", "status": "available"}]
    _patch_import(monkeypatch, accounts, pool)

    inserted, skipped = db.import_existing_accounts(records)

    assert (inserted, skipped) == (1, [])
    assert len(pool) == 1
    assert pool[0]["id"] == 7
    assert pool[0]["code_url"] == SAMPLE_CODE_URL
    assert pool[0]["status"] == "used"


def test_db_import_without_code_url_keeps_imported_source(monkeypatch):
    records, errors = parse_existing_account_text(
        "a@b.com---gptmail------https://2fa.run/----2FA:ABC"
    )
    assert errors == []
    accounts, pool = [], []
    _patch_import(monkeypatch, accounts, pool)

    inserted, skipped = db.import_existing_accounts(records)

    assert (inserted, skipped) == (1, [])
    assert accounts[0]["email_source"] == "imported"
    assert accounts[0]["original_email_line"] == "a@b.com"
    assert pool == []


def test_import_api_accepts_full_export_line(monkeypatch):
    from webui.app import create_app

    monkeypatch.setattr("core.plus_activation_store.recover_interrupted", lambda *a, **k: 0)
    for name in (
        "recover_interrupted_plan_checks", "recover_interrupted_extract_links",
        "recover_interrupted_live_checks", "recover_interrupted_codex_agents",
        "recover_interrupted_totp_setups", "recover_interrupted_email_changes",
    ):
        monkeypatch.setattr(db, name, lambda *a, **k: 0)
    client = create_app(auth_code="test-auth").test_client()

    accounts, pool = [], []
    _patch_import(monkeypatch, accounts, pool)
    monkeypatch.setattr(
        db, "get_account_by_email",
        lambda email: next(
            (row for row in accounts if row["email"].casefold() == str(email).casefold()), None
        ),
    )
    monkeypatch.setattr(account_import, "fetch_account_user_name", lambda *a, **k: {"ok": True, "user_name": "X"})
    monkeypatch.setattr(live_check_service, "enqueue_account_live_check", lambda **k: {"accepted": True})

    response = client.post(
        "/api/accounts/import",
        headers={"X-Auth-Code": "test-auth"},
        json={"text": SAMPLE_LINE},
    )

    body = response.get_json()
    assert response.status_code == 200, body
    assert (body["parsed"], body["inserted"], body["skipped"]) == (1, 1, 0)
    assert body["live_checks_queued"] == 1
    assert accounts[0]["email_source"] == "generic_api"
    payload = response.get_data(as_text=True)
    for secret in (SAMPLE_TOTP, SAMPLE_CODE_URL, SAMPLE_RAW_API):
        assert secret not in payload


if __name__ == "__main__":
    import unittest

    unittest.main()
