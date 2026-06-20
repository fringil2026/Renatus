"""Domain-ownership verification — the gate before any scrape-heavy or launch step.

A public "type any domain and we rebuild it" product is an abuse magnet (scraping arbitrary sites,
copyright). So before the engine does anything expensive or destructive for a project, the customer
must prove they control the domain (PRODUCT-PLAN §8, ADR-0001 §10). Three methods, all owner-proving:

* **DNS TXT**  — add ``ws-site-verification=<token>`` as a TXT record on the domain.
* **meta tag** — add ``<meta name="ws-site-verification" content="<token>">`` to the homepage.
* **HTTP file** — serve ``<token>`` at ``/.well-known/ws-site-verification.txt``.

The verification *logic* is pure and fully unit-testable; the two pieces of I/O it needs — DNS
resolution and HTTP fetch — sit behind ``DnsResolver`` / ``HttpFetcher`` seams (real stdlib impls for
production, fakes for tests). ``OAUTH`` is reserved as a future method.
"""

from __future__ import annotations

import re
import secrets
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlparse

from .errors import EngineError
from .models import Ownership, OwnershipStatus, Project, VerificationMethod

_TOKEN_PREFIX = "ws-site-verification"
_WELL_KNOWN_PATH = "/.well-known/ws-site-verification.txt"
_DEFAULT_TTL = timedelta(days=7)


class VerificationError(EngineError):
    """A verification could not be started or run (bad method, etc.)."""


class NotVerifiedError(EngineError):
    """Raised by ``require_verified`` when a gated step runs on an unverified project."""


# --------------------------------------------------------------------------- #
# I/O seams
# --------------------------------------------------------------------------- #
class DnsResolver(ABC):
    @abstractmethod
    def txt_records(self, host: str) -> list[str]:
        """Return the TXT record strings for ``host`` (best-effort; [] on failure)."""


class HttpFetcher(ABC):
    @abstractmethod
    def get_text(self, url: str) -> str | None:
        """Return the body text for a 200 response, or None on any failure/non-200."""


class SystemDnsResolver(DnsResolver):
    """Real TXT lookup: dnspython if present, else `dig`/`nslookup`. Never raises — returns []."""

    def txt_records(self, host: str) -> list[str]:
        try:  # preferred: dnspython
            import dns.resolver  # type: ignore

            answers = dns.resolver.resolve(host, "TXT")
            out: list[str] = []
            for rdata in answers:
                # join chunked strings, strip surrounding quotes
                out.append("".join(s.decode() if isinstance(s, bytes) else str(s) for s in rdata.strings))
            return out
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 - resolution failure is "no records"
            return []
        # fallback: shell tools
        for cmd in (["dig", "+short", "TXT", host], ["nslookup", "-type=TXT", host]):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                continue
            if res.returncode == 0 and res.stdout.strip():
                return [line.strip().strip('"') for line in res.stdout.splitlines() if line.strip()]
        return []


class UrllibFetcher(HttpFetcher):
    """Real HTTP GET via stdlib urllib — bounded, HTTPS, no auth. Returns None on any failure."""

    def __init__(self, *, timeout: float = 10.0, max_bytes: int = 512 * 1024) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes

    def get_text(self, url: str) -> str | None:
        import urllib.request

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "web-studio-verify/1.0"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 - https only below
                if getattr(resp, "status", 200) != 200:
                    return None
                raw = resp.read(self._max_bytes)
            return raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None


class FakeDnsResolver(DnsResolver):
    def __init__(self, records: dict[str, list[str]] | None = None) -> None:
        self.records = records or {}

    def txt_records(self, host: str) -> list[str]:
        return list(self.records.get(host, []))


class FakeFetcher(HttpFetcher):
    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}

    def get_text(self, url: str) -> str | None:
        return self.pages.get(url)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def normalize_domain(domain: str) -> str:
    """Reduce a domain/URL to a bare lowercase host (no scheme, path, port, or trailing dot)."""
    d = (domain or "").strip().lower()
    if "//" not in d:
        d = "//" + d  # let urlparse find the netloc
    host = urlparse(d).hostname or ""
    return host.rstrip(".")


def _expected_token_value(token: str) -> str:
    return f"{_TOKEN_PREFIX}={token}"


def _new_token() -> str:
    return secrets.token_hex(16)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def challenge_instructions(ownership: Ownership) -> dict[str, str]:
    """Human-facing guidance for completing the active challenge (for the API/UI)."""
    host, token, method = ownership.domain, ownership.token, ownership.method
    if method is VerificationMethod.DNS_TXT:
        value = _expected_token_value(token)
        return {
            "method": method.value,
            "location": f"TXT record on {host}",
            "expected_value": value,
            "instructions": f"Add a DNS TXT record to {host} with the value: {value}",
        }
    if method is VerificationMethod.META_TAG:
        tag = f'<meta name="{_TOKEN_PREFIX}" content="{token}">'
        return {
            "method": method.value,
            "location": f"https://{host}/",
            "expected_value": tag,
            "instructions": f"Add this tag to the <head> of your homepage (https://{host}/): {tag}",
        }
    if method is VerificationMethod.HTTP_FILE:
        url = f"https://{host}{_WELL_KNOWN_PATH}"
        return {
            "method": method.value,
            "location": url,
            "expected_value": token,
            "instructions": f"Serve a file at {url} whose contents are exactly: {token}",
        }
    return {"method": method.value if method else "", "instructions": "unsupported method"}


def start_verification(
    domain: str,
    method: VerificationMethod,
    *,
    now: datetime | None = None,
    ttl: timedelta = _DEFAULT_TTL,
    token_factory: Callable[[], str] = _new_token,
) -> Ownership:
    """Issue a challenge: returns a PENDING ``Ownership`` with a fresh token + expiry."""
    if method is VerificationMethod.OAUTH:
        raise VerificationError("OAUTH verification is not implemented in the skeleton")
    if method not in (VerificationMethod.DNS_TXT, VerificationMethod.META_TAG, VerificationMethod.HTTP_FILE):
        raise VerificationError(f"unknown verification method: {method!r}")
    host = normalize_domain(domain)
    if not host:
        raise VerificationError(f"could not derive a host from domain: {domain!r}")
    now = now or datetime.now(timezone.utc)
    return Ownership(
        status=OwnershipStatus.PENDING,
        domain=host,
        method=method,
        token=token_factory(),
        expires=_iso(now + ttl),
    )


@dataclass(slots=True)
class CheckResult:
    verified: bool
    detail: str
    ownership: Ownership  # the updated ownership (VERIFIED on success; unchanged otherwise)


_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"|(\w[\w-]*)\s*=\s*\'([^\']*)\'', re.IGNORECASE)


def _meta_has(html: str, name: str, content: str) -> bool:
    for tag in _META_RE.findall(html):
        attrs: dict[str, str] = {}
        for m in _ATTR_RE.finditer(tag):
            key = (m.group(1) or m.group(3) or "").lower()
            val = m.group(2) if m.group(2) is not None else (m.group(4) or "")
            attrs[key] = val
        if attrs.get("name", "").lower() == name.lower() and attrs.get("content", "") == content:
            return True
    return False


def check_verification(
    ownership: Ownership,
    *,
    resolver: DnsResolver,
    fetcher: HttpFetcher,
    now: datetime | None = None,
) -> CheckResult:
    """Query DNS/HTTP and decide whether the pending challenge is satisfied."""
    if ownership.status is not OwnershipStatus.PENDING or not ownership.token:
        return CheckResult(False, "no pending challenge", ownership)
    now = now or datetime.now(timezone.utc)
    if ownership.expires:
        try:
            if now > datetime.fromisoformat(ownership.expires):
                return CheckResult(False, "challenge expired — start a new one", ownership)
        except ValueError:
            pass

    host, token, method = ownership.domain, ownership.token, ownership.method
    verified = False
    detail = "verification record not found yet"

    if method is VerificationMethod.DNS_TXT:
        want = _expected_token_value(token)
        records = [r.strip().strip('"') for r in resolver.txt_records(host)]
        verified = want in records
        if not verified:
            detail = f"no TXT record on {host} matching {want}"
    elif method is VerificationMethod.META_TAG:
        html = fetcher.get_text(f"https://{host}/")
        if html is None:
            detail = f"could not fetch https://{host}/"
        else:
            verified = _meta_has(html, _TOKEN_PREFIX, token)
            if not verified:
                detail = "homepage reachable but the verification meta tag was not found"
    elif method is VerificationMethod.HTTP_FILE:
        body = fetcher.get_text(f"https://{host}{_WELL_KNOWN_PATH}")
        if body is None:
            detail = f"could not fetch https://{host}{_WELL_KNOWN_PATH}"
        else:
            verified = body.strip() == token
            if not verified:
                detail = "file reachable but contents did not match the token"
    else:
        return CheckResult(False, "unsupported method", ownership)

    if verified:
        return CheckResult(
            True,
            "verified",
            Ownership(
                status=OwnershipStatus.VERIFIED,
                domain=host,
                method=method,
                verified_at=_iso(now),
            ),
        )
    return CheckResult(False, detail, ownership)


def require_verified(project: Project) -> None:
    """Raise ``NotVerifiedError`` unless the project's domain ownership is verified."""
    if not (project.ownership and project.ownership.is_verified):
        raise NotVerifiedError(
            f"domain ownership for {project.slug!r} is not verified; "
            "complete a verification challenge before this step"
        )
