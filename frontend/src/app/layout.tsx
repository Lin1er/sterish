import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: "Sterish: Audited Skill Marketplace for AI Agents",
  description:
    "On-chain audited skill registry and trust scoring for AI agents on Stellar.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // `dark` is set explicitly so shadcn's `dark:` variants resolve. The token
    // values themselves live on :root, because v1 ships one theme only.
    <html lang="en" className={`dark ${geist.variable} ${geistMono.variable}`}>
      <body className="min-h-screen">
        <header className="border-b border-border px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <h1 className="text-xl font-bold tracking-wider">STERISH</h1>
            <nav className="flex gap-4 text-sm text-text-muted">
              <Link className="hover:text-accent-lift" href="/">
                Registry
              </Link>
              <Link className="hover:text-accent-lift" href="/tokens">
                Tokens
              </Link>
              <a
                className="hover:text-accent-lift"
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
