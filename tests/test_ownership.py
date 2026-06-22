"""Tests for engine.ownership — pure verification logic with fake DNS/HTTP.

No network: DNS and HTTP are exercised through FakeDnsResolver / FakeFetcher, so every method and
edge (success, missing record, expiry, normalization, gating) is deterministic.

    python3 tests/test_ownership.py
    pytest tests/test_ownership.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    FakeDnsResolver,
    FakeFetcher,
    NotVerifiedError,
    Ownership,
    OwnershipStatus,
    Project,
    VerificationError,
    VerificationMethod,
    challenge_instructions,
    check_verification,
    normalize_domain,
    require_verified,
    start_verification,
)

_NOW = datetime(2026, 6, 19, 21, 0, tzinfo=timezone.utc)


def _challenge(method: VerificationMethod, domain="https://acme.example/shop") -> Ownership:
    return start_verification(domain, method, now=_NOW, token_factory=lambda: "TOK123")


# --------------------------------------------------------------------------- #
def test_normalize_domain() -> None:
    assert normalize_domain("https://Acme.Example/shop?x=1") == "acme.example"
    assert normalize_domain("acme.example") == "acme.example"
    assert normalize_domain("http://acme.example:8080/") == "acme.example"
    assert normalize_domain("acme.example.") == "acme.example"


def test_start_sets_pending_with_token_and_expiry() -> None:
    o = _challenge(VerificationMethod.DNS_TXT)
    assert o.status is OwnershipStatus.PENDING
    assert o.domain == "acme.example"
    assert o.token == "TOK123"
    assert datetime.fromisoformat(o.expires) > _NOW
    instr = challenge_instructions(o)
    assert instr["expected_value"] == "ws-site-verification=TOK123"


def test_oauth_not_implemented() -> None:
    try:
        start_verification("acme.example", VerificationMethod.OAUTH, now=_NOW)
    except VerificationError:
        pass
    else:
        raise AssertionError("expected VerificationError for OAUTH")


def test_dns_txt_success_and_failure() -> None:
    o = _challenge(VerificationMethod.DNS_TXT)
    ok = FakeDnsResolver({"acme.example": ['"ws-site-verification=TOK123"', "v=spf1 -all"]})
    res = check_verification(o, resolver=ok, fetcher=FakeFetcher(), now=_NOW)
    assert res.verified and res.ownership.status is OwnershipStatus.VERIFIED and res.ownership.verified_at

    miss = FakeDnsResolver({"acme.example": ["v=spf1 -all"]})
    res = check_verification(o, resolver=miss, fetcher=FakeFetcher(), now=_NOW)
    assert not res.verified and res.ownership.status is OwnershipStatus.PENDING


def test_meta_tag_success_and_failure() -> None:
    o = _challenge(VerificationMethod.META_TAG)
    page = '<html><head><meta charset="utf-8"><meta content="TOK123" name="ws-site-verification"></head></html>'
    f_ok = FakeFetcher({"https://acme.example/": page})
    assert check_verification(o, resolver=FakeDnsResolver(), fetcher=f_ok, now=_NOW).verified

    f_no = FakeFetcher({"https://acme.example/": "<html><head></head></html>"})
    assert not check_verification(o, resolver=FakeDnsResolver(), fetcher=f_no, now=_NOW).verified

    # unreachable homepage
    res = check_verification(o, resolver=FakeDnsResolver(), fetcher=FakeFetcher(), now=_NOW)
    assert not res.verified and "could not fetch" in res.detail


def test_http_file_success_and_failure() -> None:
    o = _challenge(VerificationMethod.HTTP_FILE)
    url = "https://acme.example/.well-known/ws-site-verification.txt"
    assert check_verification(o, resolver=FakeDnsResolver(), fetcher=FakeFetcher({url: "TOK123\n"}), now=_NOW).verified
    assert not check_verification(o, resolver=FakeDnsResolver(), fetcher=FakeFetcher({url: "nope"}), now=_NOW).verified


def test_expired_challenge_does_not_verify() -> None:
    o = _challenge(VerificationMethod.DNS_TXT)
    later = _NOW + timedelta(days=30)
    ok = FakeDnsResolver({"acme.example": ["ws-site-verification=TOK123"]})
    res = check_verification(o, resolver=ok, fetcher=FakeFetcher(), now=later)
    assert not res.verified and "expired" in res.detail


def test_require_verified_gate() -> None:
    unverified = Project(slug="acme")
    try:
        require_verified(unverified)
    except NotVerifiedError:
        pass
    else:
        raise AssertionError("expected NotVerifiedError for an unverified project")

    verified = Project(slug="acme", ownership=Ownership(status=OwnershipStatus.VERIFIED, domain="acme.example"))
    require_verified(verified)  # must not raise


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    total = len(tests)
    print(f"\n{total - failed}/{total} passed" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
