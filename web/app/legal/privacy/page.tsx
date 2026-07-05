// DRAFT legal page. Canonical review copy: docs/legal/privacy-policy.md
// Remove the DraftBanner once counsel has reviewed and the brackets are filled.
export const metadata = { title: "Privacy Policy" };

function DraftBanner() {
  return (
    <div className="mb-8 rounded-lg border border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <strong>DRAFT — pending legal review.</strong> Placeholder copy, not legal advice. Bracketed
      fields must be filled and reviewed by counsel before launch.
    </div>
  );
}

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16 text-stone-800">
      <DraftBanner />
      <h1 className="mb-2 text-3xl font-serif">Privacy Policy</h1>
      <p className="mb-8 text-sm text-stone-500">Effective date: [EFFECTIVE_DATE]</p>
      <p className="mb-4">
        [LEGAL_ENTITY_NAME] (&ldquo;we&rdquo;) operates [PRODUCT_NAME], a website diagnostic and
        rebuild service. This page summarizes what we collect and why; the full policy is maintained
        in <code>docs/legal/privacy-policy.md</code>.
      </p>
      <ul className="mb-6 list-disc space-y-2 pl-6">
        <li>We fetch and analyze the public pages of the domain you submit for a diagnostic.</li>
        <li>We collect your contact details, rebuild questionnaire answers, and domain-ownership proof.</li>
        <li>Payments are processed by Stripe; we don&rsquo;t store card numbers.</li>
        <li>We don&rsquo;t sell your personal information. Scraped content is used only to rebuild your site.</li>
      </ul>
      <p className="text-sm text-stone-500">
        Questions or data requests: [PRIVACY_CONTACT_EMAIL].
      </p>
    </main>
  );
}
