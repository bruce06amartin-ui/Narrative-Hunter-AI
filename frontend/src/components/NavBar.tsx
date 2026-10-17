import Link from "next/link";
import SearchBar from "@/components/SearchBar";

export default function NavBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-void/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="h-2 w-2 rounded-full bg-amber shadow-[0_0_8px_2px_rgba(255,176,32,0.6)]" />
          <span className="font-display font-bold tracking-tight text-lg text-ink">
            NARRATIVE<span className="text-amber">HUNTER</span>
          </span>
          <span className="hidden sm:inline font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted border border-hairline rounded px-1.5 py-0.5">
            v0.1 mvp
          </span>
        </Link>
        <div className="flex-1 max-w-md">
          <SearchBar />
        </div>
        <nav className="hidden md:flex items-center gap-5 font-mono text-xs uppercase tracking-wider text-ink-muted">
          <Link href="/" className="hover:text-amber transition-colors">
            Dashboard
          </Link>
          <Link href="/alerts" className="hover:text-amber transition-colors">
            Alerts
          </Link>
          <Link href="/wallets" className="hover:text-amber transition-colors">
            Wallets
          </Link>
          <Link href="/paper-trading" className="hover:text-amber transition-colors">
            Paper Trading
          </Link>
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/docs`}
            target="_blank"
            rel="noreferrer"
            className="hover:text-amber transition-colors"
          >
            API Docs
          </a>
        </nav>
      </div>
    </header>
  );
}
