import type { MetadataRoute } from "next";

const BASE_URL = "https://trace.example";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "",
    "/try-it",
    "/naive-vs-protected",
    "/marketplace",
    "/pricing",
    "/outcomes",
    "/audit",
    "/about",
    "/privacy",
    "/terms",
  ];

  return routes.map((route) => ({
    url: `${BASE_URL}${route}`,
    lastModified: new Date(),
    changeFrequency: "weekly" as const,
    priority: route === "" ? 1 : 0.7,
  }));
}
