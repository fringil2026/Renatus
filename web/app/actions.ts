"use server";

import { redirect } from "next/navigation";
import { api, slugify } from "@/lib/api";

// Funnel entry: create the project (if new) and kick off the free diagnostic, then go to its page.
export async function startDiagnostic(formData: FormData): Promise<void> {
  const domain = String(formData.get("domain") ?? "").trim();
  if (!domain) return;
  const slug = slugify(domain);

  // Create the project (ignore 409 — already exists, just re-diagnose).
  await api("/v1/projects", {
    method: "POST",
    body: JSON.stringify({ slug, domain: domain.startsWith("http") ? domain : `https://${domain}` }),
  });
  await api(`/v1/projects/${slug}/actions/diagnose`, { method: "POST" });

  redirect(`/projects/${slug}`);
}
