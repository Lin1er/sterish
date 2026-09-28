import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";

import "./globals.css";

/**
 * The landing's own shell.
 *
 * Deliberately not the dashboard's layout. This deployment answers
 * sterish.xyz, where the visitor has usually never heard of the product, so
 * there is no product nav and no wallet button: a "Connect wallet" control
 * above the fold asks a stranger for something before it has told them
 * anything. The page's own calls to action send them to app.sterish.xyz when
 * they are ready.
 *
 * Fonts are set up exactly as the dashboard does it, because the two
 * deployments have to look like one product.
 */

// JetBrains Mono is OFL, so next/font self-hosts it and nothing is fetched
// from a third party at render time.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

// Satoshi comes from the Fontshare CDN instead: free for commercial use, but
// the ITF licence is not clear about self-hosting it as a webfont, and the CDN
// is the unambiguous route. See docs/brand.md §5.
const SATOSHI_CSS =
  "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap";

export const metadata: Metadata = {
  title: {
    default: "Sterish — audited skills for AI agents on Stellar",
    template: "%s · Sterish",
  },
  description:
    "Sterish audits AI agent skills and writes the verdict on chain, pinned to the hash of the files it read. Check a specific version before installing it.",
  metadataBase: new URL("https://sterish.xyz"),
  openGraph: {
    title: "Sterish — audited skills for AI agents on Stellar",
    description:
      "The verdict is pinned to the hash of the files, not to the name. Check a version before your agent runs it.",
    url: "https://sterish.xyz",
    siteName: "Sterish",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // `dark` is explicit so any `dark:` variant resolves; the token values
    // themselves live on :root, because v1 ships one theme.
    <html lang="en" className={`dark ${jetbrainsMono.variable}`}>
      <head>
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link rel="preconnect" href="https://cdn.fontshare.com" crossOrigin="" />
        <link rel="stylesheet" href={SATOSHI_CSS} />
      </head>
      <body className="flex min-h-dvh flex-col">
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
