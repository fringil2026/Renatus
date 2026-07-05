// DRAFT legal page. Canonical review copy: docs/legal/terms-of-service.md
// Remove the DraftBanner once counsel has reviewed and the brackets are filled.
export const metadata = { title: "Terms of Service" };

function DraftBanner() {
  return (
    <div className="mb-8 rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <strong>DRAFT — pending legal review.</strong> Placeholder copy, not legal advice. Bracketed
      fields must be filled and reviewed by counsel before launch.
    </div>
  );
}

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 text-stone-800">
      <DraftBanner />
      <h1 className="mb-2 text-3xl font-serif">Terms of Service</h1>
      <p className="mb-8 text-sm text-stone-500">Effective date: [EFFECTIVE_DATE]</p>
      <p className="mb-4">
        By using [PRODUCT_NAME] you agree to these Terms. The full text is maintained in{" "}
        <code>docs/legal/terms-of-service.md</code>.
      </p>
      <ul className="mb-6 list-disc space-y-2 pl-6">
        <li>You may only request a rebuild of a website you own or are authorized to manage, and must prove domain control first.</li>
        <li>The diagnostic is free; the rebuild is a one-time fee, then a hosting + edits subscription (cancel anytime).</li>
        <li>Going live is always a human, owner-approved step. We never modify your email records (MX/SPF/DKIM/DMARC).</li>
        <li>You retain ownership of your content and brand assets.</li>
      </ul>
      <p className="text-sm text-stone-500">Contact: [SUPPORT_CONTACT_EMAIL].</p>
    </main>
  );
}
