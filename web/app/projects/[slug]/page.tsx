import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic"; // always live (no build-time API calls, no caching)

interface Project {
  slug: string;
  stage?: string;
  domain?: string;
  name?: string;
  preview_url?: string;
  ownership?: { status?: string };
  launch_review?: { status?: string };
}
interface Run { id: string; kind: string; status: string }
interface Report { timestamp: string; kind: string }

const STAGE_COPY: Record<string, string> = {
  queued: "Queued…",
  scraping: "Analyzing your site…",
  "baseline-ready": "Ready — choose a concept.",
  prototype: "Prototype built — preview below.",
  "awaiting-owner": "Prototype built — review the preview.",
  "answers-received": "Finalizing your site…",
  final: "Final build complete.",
  "cutover-checked": "Launch-ready.",
  error: "Something went wrong — see runs below.",
};

export default async function ProjectPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [{ status, body: project }, runs, reports] = await Promise.all([
    api<Project>(`/v1/projects/${slug}`),
    api<{ runs: Run[] }>(`/v1/projects/${slug}/runs`),
    api<{ reports: Report[] }>(`/v1/projects/${slug}/reports`),
  ]);

  if (status === 0) {
    return (
      <Shell slug={slug}>
        <p className="text-red-700">Can&rsquo;t reach the backend API. Is it running and is{" "}
        <code>API_BASE_URL</code> set?</p>
      </Shell>
    );
  }
  if (status === 404) {
    return (
      <Shell slug={slug}>
        <p>No project <b>{slug}</b> yet. <Link className="underline" href="/">Start a check →</Link></p>
      </Shell>
    );
  }

  const stage = project.stage ?? "queued";
  const runList = runs.body.runs ?? [];
  const reportList = reports.body.reports ?? [];

  return (
    <Shell slug={slug}>
      <p className="text-stone-600">{project.domain}</p>
      <div className="rounded-lg border border-stone-300 bg-white p-4">
        <div className="text-sm uppercase tracking-wide text-stone-500">Status</div>
        <div className="text-lg">{STAGE_COPY[stage] ?? stage}</div>
        <div className="mt-1 text-xs text-stone-400">stage: {stage}</div>
        {project.preview_url ? (
          <a className="mt-2 inline-block underline" href={project.preview_url} target="_blank" rel="noreferrer">
            Open preview ↗
          </a>
        ) : null}
      </div>

      <section className="space-y-1">
        <h2 className="font-medium">Runs</h2>
        {runList.length === 0 ? (
          <p className="text-stone-500 text-sm">No runs yet.</p>
        ) : (
          <ul className="text-sm">
            {runList.map((r) => (
              <li key={r.id} className="flex justify-between border-b border-stone-200 py-1">
                <span>{r.kind}</span>
                <span className={r.status === "succeeded" ? "text-green-700" : "text-stone-500"}>{r.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-1">
        <h2 className="font-medium">Reports</h2>
        {reportList.length === 0 ? (
          <p className="text-stone-500 text-sm">No reports yet.</p>
        ) : (
          <ul className="text-sm">
            {reportList.map((r) => (
              <li key={`${r.timestamp}-${r.kind}`} className="border-b border-stone-200 py-1">
                {r.kind} <span className="text-stone-400">· {r.timestamp}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link href={`/projects/${slug}`} className="text-sm underline">Refresh</Link>
    </Shell>
  );
}

function Shell({ slug, children }: { slug: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-2xl space-y-6 p-8 bg-[#F4F1EA] min-h-screen text-stone-900">
      <Link href="/" className="text-sm text-stone-500 underline">← Web Studio</Link>
      <h1 className="text-2xl font-serif">{slug}</h1>
      {children}
    </main>
  );
}
