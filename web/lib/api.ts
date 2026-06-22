// Server-side client for the control-plane API. Import only from server components / server actions
// (it reads server env) so the tenant token never reaches the browser.

const BASE = process.env.API_BASE_URL ?? "http://127.0.0.1:8099";
const TOKEN = process.env.WS_TENANT_TOKEN ?? "";

export type ApiResult<T = Record<string, unknown>> = { status: number; body: T };

export async function api<T = Record<string, unknown>>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  let status = 0;
  let body = {} as T;
  try {
    const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
    status = res.status;
    body = (await res.json().catch(() => ({}))) as T;
  } catch {
    // API unreachable — surface as a 0 so the UI can show a friendly message.
    status = 0;
  }
  return { status, body };
}

// Domain → project slug (mirrors how the studio names client folders).
export function slugify(domain: string): string {
  let d = domain.trim().toLowerCase();
  d = d.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0];
  d = d.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return d || "site";
}
