import type { NextConfig } from "next";
import { readFileSync } from "node:fs";
import path from "node:path";

const repositoryRoot = path.resolve(process.cwd(), "..");
const buildBrand = JSON.parse(
  readFileSync(path.join(repositoryRoot, "school", "brand.json"), "utf8"),
) as {
  name: string;
  short_name: string;
  logo: string;
  interface: { result_in_telegram: string };
};

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: repositoryRoot,
  poweredByHeader: false,
  env: {
    NEXT_PUBLIC_BUILD_SCHOOL_NAME: buildBrand.name,
    NEXT_PUBLIC_BUILD_SCHOOL_SHORT_NAME: buildBrand.short_name,
    NEXT_PUBLIC_BUILD_SCHOOL_LOGO: buildBrand.logo,
    NEXT_PUBLIC_BUILD_RESULT_STATUS: buildBrand.interface.result_in_telegram,
  },
  turbopack: {
    root: repositoryRoot,
  },
};

export default nextConfig;
