import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "quiet";

const base =
  "inline-flex items-center justify-center gap-2 rounded-chip font-display font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 select-none";
const variants: Record<Variant, string> = {
  primary: "bg-fg text-on-fg hover:opacity-90",
  secondary: "border border-mist bg-surface text-fg hover:border-fg",
  quiet: "text-fg underline-offset-4 hover:underline",
};
const sizes = { md: "h-11 px-5 text-[1rem]", lg: "h-14 px-7 text-[1.15rem]", sm: "h-9 px-4 text-[0.9rem]" };

interface Common {
  variant?: Variant;
  size?: keyof typeof sizes;
  children: ReactNode;
  className?: string;
}

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Common & ComponentProps<"button">) {
  return <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...rest} />;
}

export function LinkButton({
  variant = "primary",
  size = "md",
  className = "",
  href,
  children,
}: Common & { href: string }) {
  return (
    <Link href={href} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}>
      {children}
    </Link>
  );
}
