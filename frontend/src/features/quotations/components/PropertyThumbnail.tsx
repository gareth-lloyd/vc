import { cn } from "@/lib/cn";

interface Props {
  src: string | null | undefined;
  // Fallback initial shown when there is no image (e.g. the property name).
  fallbackText?: string | null;
  // Localised alt text — supplied by the caller (i18n stays at the call site).
  alt: string;
  className?: string;
}

// Small inline thumbnail for quote line rows. Mirrors MediaTab's image
// render (4:3, object-cover, rounded, text fallback) but sized for a row.
export function PropertyThumbnail({ src, fallbackText, alt, className }: Props) {
  return (
    <div
      className={cn(
        "bg-muted text-muted-foreground relative aspect-[4/3] w-12 shrink-0 overflow-hidden rounded",
        className,
      )}
    >
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-cover" draggable={false} />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-xs font-medium">
          {fallbackText?.trim()?.charAt(0).toUpperCase() || "—"}
        </div>
      )}
    </div>
  );
}
