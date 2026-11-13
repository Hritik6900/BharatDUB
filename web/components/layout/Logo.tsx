import Link from "next/link";

export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="10" fill="var(--fg)" />
      <rect x="7.5" y="13" width="3" height="6" rx="1.5" fill="var(--hi)" />
      <rect x="12.5" y="8" width="3" height="16" rx="1.5" fill="var(--bn)" />
      <rect x="17.5" y="10.5" width="3" height="11" rx="1.5" fill="var(--te)" />
      <rect x="22.5" y="14" width="3" height="4" rx="1.5" fill="var(--ta)" />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <Link href="/" aria-label="Bharat Dub, home" className={`inline-flex shrink-0 items-center gap-2.5 ${className}`}>
      <LogoMark />
      <span className="font-display text-[1.35rem] font-semibold leading-none tracking-[-0.04em]">Bharat Dub</span>
    </Link>
  );
}
