"use client";
import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import { getUploadedMB, formatMB, estimateSessionUsage } from "@/lib/dataUsage";

/**
 * ACC-04: Data-cost transparency.
 *
 * Shows MB uploaded this session so students on prepaid data plans know
 * what the platform costs them. Displayed in the runner footer.
 */
export function DataUsageIndicator({ itemCount }: { itemCount?: number }) {
  const [mb, setMb] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setMb(getUploadedMB()), 2000);
    return () => clearInterval(interval);
  }, []);

  if (mb < 0.01 && !itemCount) return null;

  const estimated = itemCount ? estimateSessionUsage(itemCount) : 0;

  return (
    <div
      className="flex items-center gap-1.5 text-[10px] text-muted"
      title="Data used this session"
    >
      <Database size={10} />
      <span>
        {formatMB(mb)} uploaded
        {estimated > 0 && (
          <span className="opacity-60"> · ~{formatMB(estimated)} estimated</span>
        )}
      </span>
    </div>
  );
}
