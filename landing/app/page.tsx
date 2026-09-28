import { Landing } from "@/modules/landing/Landing";

/**
 * The landing is this deployment's root. It answers sterish.xyz; the dashboard
 * is a separate deployment at app.sterish.xyz.
 *
 * Metadata lives in layout.tsx rather than here: this app has one page, so
 * splitting a title template across two files would only be ceremony.
 */
export default function Page() {
  return <Landing />;
}
