import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asistente MTG — Call Center",
  description: "Asistente conversacional de Magic: The Gathering (RAG + búsqueda de cartas)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
