import type { Metadata } from "next";
import { Cinzel, EB_Garamond } from "next/font/google";
import "./globals.css";

// Cinzel: display grabado/épico (marca y etiquetas). EB Garamond: serif de libro
// para leer las reglas como un tomo. Cargadas con next/font (self-hosted, sin CLS).
const display = Cinzel({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
});
const body = EB_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "Códice de Reglas — Asistente MTG",
  description:
    "Asistente conversacional de Magic: The Gathering. Cada veredicto cita su fuente.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${display.variable} ${body.variable}`}>
      <body>{children}</body>
    </html>
  );
}
