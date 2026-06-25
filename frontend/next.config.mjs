/** @type {import('next').NextConfig} */
const nextConfig = {
  // URL del backend FastAPI; configurable por entorno en despliegue.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};

export default nextConfig;
