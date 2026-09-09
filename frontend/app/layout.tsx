import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";

import { Footer } from "@/components/layouts/Footer";
import { Header } from "@/components/layouts/Header";
import { Providers } from "./providers";
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

/**
 * Named in the footer so nobody has to guess which chain they are looking at.
 * Read from env rather than from GET /health on purpose: the layout wraps every
 * page, and making it await the API would put a network call in front of every
 * render, including the 404 that has to answer with a real status code.
 */
const STELLAR_NETWORK = process.env.NEXT_PUBLIC_STELLAR_NETWORK ?? "testnet";

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
        <Providers>
          <Header />
          <main className="min-h-[60vh]">{children}</main>
          <Footer network={STELLAR_NETWORK} />
        </Providers>
      </body>
    </html>
  );
}
