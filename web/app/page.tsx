import { startDiagnostic } from "./actions";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8 bg-[#F4F1EA] text-stone-900">
      <div className="max-w-xl text-center space-y-4">
        <h1 className="text-4xl font-serif tracking-tight">Is your website costing you customers?</h1>
        <p className="text-stone-600">
          Enter your site and we&rsquo;ll run a free check — design, speed, mobile, and what your
          industry&rsquo;s best sites have that yours doesn&rsquo;t. No signup to see the verdict.
        </p>
      </div>

      <form action={startDiagnostic} className="flex w-full max-w-md gap-2">
        <input
          name="domain"
          type="text"
          required
          placeholder="yourshop.com"
          className="flex-1 rounded-lg border border-stone-300 bg-white px-4 py-3 outline-none focus:border-stone-500"
        />
        <button
          type="submit"
          className="rounded-lg bg-stone-900 px-5 py-3 font-medium text-white hover:bg-stone-700"
        >
          Check my site
        </button>
      </form>

      <p className="text-xs text-stone-500">Free diagnostic · we only rebuild sites their owners ask us to.</p>
    </main>
  );
}
