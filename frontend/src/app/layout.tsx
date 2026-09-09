import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

// Two families, and only two. JetBrains Mono is OFL, so next/font self-hosts it
// and there is no third-party request at render time.
//
// Satoshi is loaded from the Fontshare CDN in <head> instead. It is free for
// commercial use, but the ITF licence is not clear about self-hosting it as a
// webfont, and the CDN is the unambiguous route. If Nabil gets written consent
// from ITF, swap this for next/font/local and drop the preconnects.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

const SATOSHI_CSS =
  "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap";

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
    <html lang="en" className={`dark ${jetbrainsMono.variable}`}>
      <head>
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link
          rel="preconnect"
          href="https://cdn.fontshare.com"
          crossOrigin=""
        />
        <link rel="stylesheet" href={SATOSHI_CSS} />
      </head>
      <body className="min-h-screen">
        <header className="border-b border-border px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <Link href="/" className="text-xl font-bold tracking-wider">
              STERISH
            </Link>
            <nav className="flex gap-4 text-sm text-text-secondary">
              <Link className="hover:text-keyword" href="/">
                Registry
              </Link>
              <Link className="hover:text-keyword" href="/tokens">
                Tokens
              </Link>
              <a
                className="hover:text-keyword"
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
