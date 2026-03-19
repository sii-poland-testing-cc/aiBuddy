/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@llamaindex/chat-ui"],
  async redirects() {
    return [
      {
        source: "/chat/:projectId",
        destination: "/project/:projectId?mode=audit",
        permanent: true,
      },
      {
        source: "/context/:projectId",
        destination: "/project/:projectId?mode=context",
        permanent: true,
      },
      {
        source: "/requirements/:projectId",
        destination: "/project/:projectId?mode=requirements",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
