import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sterish — Audited Skill Marketplace for AI Agents',
  description:
    'On-chain audited skill registry and trust scoring for AI agents on Stellar.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
        <header className="border-b border-[var(--color-border)] px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <h1 className="text-xl font-bold tracking-wider">STERISH</h1>
            <nav className="flex gap-4 text-sm text-[var(--color-muted)]">
              <a href="#">Registry</a>
              <a href="#">API Docs</a>
              <a
                href="https://github.com/Lin1er/sterish"
                target="_blank"
                rel="noopener noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
