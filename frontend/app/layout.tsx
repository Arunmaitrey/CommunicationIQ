import type { Metadata } from "next";
import "./globals.css";
import { RoleProvider } from "@/components/RoleProvider";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";

/* Typefaces for the Campus theme.
 *
 *  Loaded through next/font rather than a <link> to fonts.googleapis.com, and
 *  that is not a preference. These get downloaded at build time and served
 *  from our own origin, so the theme still renders on a laptop running a
 *  smoke test on a LAN with no internet — which is exactly the situation the
 *  product is tested in. A Google Fonts link would silently fall back to
 *  system-ui there and the theme would look like a different theme.
 *
 *  `display: swap` so text is readable immediately rather than invisible
 *  while a face loads. Only the weights actually used are requested.
 */
export const metadata: Metadata = {
  title: "Fluenzee",
  description:
    "Placement-readiness assessment and training — simulate the real test, diagnose the real gap.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="campus"
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider>
          <ToastProvider>
            <RoleProvider>{children}</RoleProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
