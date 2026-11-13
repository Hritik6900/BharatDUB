import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const base =
  "group inline-flex shrink-0 items-center justify-center gap-2 rounded-chip font-medium tracking-[-0.01em] transition-[background,border-color,opacity,transform] duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40 select-none";
const variants: Record<Variant, string> = {
  primary: "bg-fg text-on-fg hover:opacity-90 shadow-[0_8px_24px_-12px_color-mix(in_oklab,var(--fg)_70%,transparent)]",
  secondary: "border border-line bg-surface text-fg hover:border-fg",
  ghost: "text-fg hover:bg-sunken",
  danger: "bg-danger text-white hover:opacity-90",
};
const sizes = { sm: "h-9 px-4 text-sm", md: "h-11 px-5 text-[0.95rem]", lg: "h-[3.25rem] px-7 text-base" };

interface Common {
  variant?: Variant;
  size?: keyof typeof sizes;
  children: ReactNode;
  className?: string;
}

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Common & ComponentProps<"button">) {
  return <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...rest} />;
}

export function LinkButton({ variant = "primary", size = "md", className = "", href, children, ...rest }: Common & { href: string; target?: string }) {
  return (
    <Link href={href} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...rest}>
      {children}
    </Link>
  );
}
