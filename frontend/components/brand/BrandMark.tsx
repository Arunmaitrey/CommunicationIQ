"use client";

/** The product mark. Drawn, not an image file, so it inherits the theme's
 *  brand gradient instead of fighting it in fifteen of sixteen themes. */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <span
      className="inline-flex items-center justify-center rounded-ds font-black shrink-0"
      style={{
        width: size, height: size, fontSize: size * 0.46,
        background: "var(--brand-grad)", color: "#fff", letterSpacing: "-0.04em",
      }}
      aria-hidden
    >
      Fz
    </span>
  );
}

export function BrandLockup({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <BrandMark />
      {/* No second line. The product is built for a client, so attributing it
          to the studio here would be wrong -- the "Powered by Graymatter
          Technologies" mark is the correct and only attribution. */}
      {!compact && (
        <span className="leading-tight">
          <span className="block text-[13px] font-bold">Fluenzee AI</span>
        </span>
      )}
    </span>
  );
}

/** The lockup a signed-in person sees.
 *
 *  A tenant that has uploaded a logo gets their own mark and name; everyone
 *  else gets the product's. The product name stays underneath either way --
 *  a student needs to know which product they are in when they ask for help,
 *  and a college logo alone does not tell them.
 */
export function TenantLockup({ logoUrl, displayName, fallbackName }: {
  logoUrl?: string | null;
  displayName?: string | null;
  fallbackName?: string | null;
}) {
  const name = displayName || fallbackName || "";

  if (!logoUrl && !name) return <BrandLockup />;

  return (
    <span className="inline-flex items-center gap-2 min-w-0">
      {logoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logoUrl}
          alt=""
          width={26}
          height={26}
          className="rounded-ds object-contain shrink-0"
          style={{ width: 26, height: 26, background: "rgba(255,255,255,.10)" }}
          // A broken logo must not leave a torn-image icon in the shell of
          // every page. Hide it and let the name carry the identity.
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
      ) : (
        <BrandMark />
      )}
      <span className="leading-tight min-w-0">
        <span className="block text-[13px] font-bold truncate">{name}</span>
        <span className="block text-[10px] opacity-70">Fluenzee AI</span>
      </span>
    </span>
  );
}
