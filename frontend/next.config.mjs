/** Static export (D-010): no Next API routes, no rewrites, client components only, query-parameter routes. */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
