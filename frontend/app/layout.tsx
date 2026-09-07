import type { Metadata } from "next";
import { Sora } from "next/font/google";
import "./globals.css";
import { RoleProvider } from "@/components/RoleProvider";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";

/* Display face for the Aurora theme's headings — self-hosted at build time
 * via next/font (downloaded once, served from our own origin), exactly the
 * property the file comment below already asks for. Only the weights the
 * theme actually uses. Every other theme's headings are unaffected: the
 * variable this produces is only referenced from `[data-theme="aurora"]`
 * selectors in globals.css. */
const sora = Sora({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-sora",
  display: "swap",
});

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
  title: "Fluenzee AI",
  description:
    "Placement-readiness assessment and training — simulate the real test, diagnose the real gap.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="aurora"
      className={sora.variable}
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
