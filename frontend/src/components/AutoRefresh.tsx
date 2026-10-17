"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Periodically re-triggers the server-side data fetch on this page
 * (which is already `dynamic = "force-dynamic"`, so nothing is cached -
 * this just re-runs it on an interval instead of only on manual reload).
 * Minimal by design: no new API calls, no new endpoints, just makes the
 * existing dashboard genuinely live rather than "correct on refresh."
 */
export default function AutoRefresh({ intervalSeconds = 30 }: { intervalSeconds?: number }) {
  const router = useRouter();

  useEffect(() => {
    const id = setInterval(() => router.refresh(), intervalSeconds * 1000);
    return () => clearInterval(id);
  }, [router, intervalSeconds]);

  return null;
}
