import RegistryBrowser from '@/components/registry-browser';

export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      {/* Hero */}
      <section className="mb-16 text-center">
        <h2 className="text-4xl font-extrabold tracking-tight">
          Audited Skills for{' '}
          <span className="text-[var(--color-accent)]">AI Agents</span>
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-[var(--color-muted)]">
          On-chain registry with multi-stage LLM audit, trust scoring, and
          pay-per-use licensing — built on Stellar.
        </p>
      </section>

      {/* Registry Browser */}
      <section>
        <h3 className="mb-6 text-lg font-bold tracking-wider">
          Registry Browser
        </h3>
        <RegistryBrowser />
      </section>
    </div>
  );
}
