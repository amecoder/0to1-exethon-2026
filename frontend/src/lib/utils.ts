import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge the custom type scale (index.css) so `text-title` is a size, not a color.
const twMerge = extendTailwindMerge({
  extend: { classGroups: { "font-size": [{ text: ["title", "hero"] }] } },
});

// shadcn/ui class merger: later Tailwind classes override earlier conflicting ones.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
