import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <div className="text-center space-y-4">
        <h1 className="text-6xl font-bold" style={{ color: "var(--muted)" }}>404</h1>
        <p className="text-lg" style={{ color: "var(--muted)" }}>
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          href="/"
          className="btn btn-primary"
        >
          Go to Home
        </Link>
      </div>
    </div>
  );
}
