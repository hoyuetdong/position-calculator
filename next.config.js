/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  webpack: (config, { isServer }) => {
    // Handle optional native dependencies
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
        crypto: false,
      }
      // Ignore memcpy module not found (bytebuffer dependency)
      config.resolve.alias = {
        ...config.resolve.alias,
        memcpy: false,
      }
    }
    return config
  },
}

module.exports = nextConfig