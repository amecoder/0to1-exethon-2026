import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap font-semibold transition-[background-color,color,box-shadow,transform] duration-150 outline-none select-none focus-visible:ring-[3px] focus-visible:ring-primary-ring active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40 disabled:shadow-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-glow hover:bg-primary-hover",
        secondary: "bg-secondary text-secondary-foreground hover:bg-white/10",
        outline: "border border-border-strong bg-transparent text-foreground hover:bg-white/[0.06]",
        ghost: "text-muted-foreground hover:bg-secondary hover:text-foreground",
        link: "text-primary-text underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 rounded-lg px-4 text-sm",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-13 rounded-xl px-6 text-base",
        icon: "size-9 rounded-lg",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
