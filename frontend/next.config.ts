import type { NextConfig } from "next";

import { landingRewriteConfig } from "./src/lib/landingHosts";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // sterish.xyz serves the landing page, app.sterish.xyz serves the dashboard,
  // and both are this one deployment. See src/lib/landingHosts.ts.
  async rewrites() {
    return landingRewriteConfig(process.env.LANDING_HOSTS);
  },
};

export default nextConfig;
