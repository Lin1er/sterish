import RegistryBrowser from "@/components/registry-browser";

export default function Home() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <section className="mb-16 text-center">
        <h2 className="text-4xl font-extrabold tracking-tight">
          Audited Skills for <span className="text-keyword">AI Agents</span>
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-text-secondary">
          On-chain registry with multi-stage LLM audit, trust scoring, and a
          USDC licence an agent buys once per skill version, built on Stellar.
        </p>
      </section>

      <section>
        <h3 className="mb-6 text-lg font-bold tracking-wider">
          Registry Browser
        </h3>
        <RegistryBrowser />
      </section>
    </div>
  );
}
