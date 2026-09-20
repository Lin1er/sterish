import { permanentRedirect } from "next/navigation";

/**
 * /tokens was Ancung's token preview, built as a PROPOSAL for STE-7 so Nabil
 * could sign the palette off before flows were built on it (its own docstring
 * said to delete it or flag it once signed off). The palette is now signed off
 * and written down in docs/brand.md, so this consolidates onto /brand rather
 * than leaving two pages titled "Design tokens".
 *
 * The reason it is /brand that survived, and not this page: the old page held
 * the values as hand-written literals — `hex: "#122c4f"` alongside
 * `onBg: "13.19:1"` — and had already drifted. Its type comment still described
 * --bg as #0a0a0f, the near-black canvas from before the navy, while the
 * swatches beside it listed the navy. The ratios were right when typed and
 * nothing would have told us when they stopped being right. /brand paints every
 * swatch with var(--token), reads the resolved value back out of the DOM and
 * recomputes contrast in the browser, so it cannot make that mistake.
 *
 * The URL is kept because it may be linked from Linear or a review thread.
 * The old page is in git history at e51998e if any of it is wanted back.
 */
export default function TokensPage() {
  permanentRedirect("/brand");
}
