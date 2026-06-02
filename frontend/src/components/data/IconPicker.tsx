import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { iconNames } from "lucide-react/dynamic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { FeatureIcon } from "./FeatureIcon";

/** Cap rendered icons — the full set is ~1600; rendering all defeats lazy loading. */
const MAX_RESULTS = 60;
const ALL_ICON_NAMES: readonly string[] = iconNames;

interface IconPickerProps {
  value: string;
  onChange: (name: string) => void;
  id?: string;
  "aria-label"?: string;
  disabled?: boolean;
}

/**
 * Searchable visual picker over the lucide icon set. Emits a kebab-case icon
 * name (or "" when cleared) — stored directly in `Feature.icon` /
 * `FeatureCategory.icon` and rendered elsewhere via `FeatureIcon`.
 */
export function IconPicker({
  value,
  onChange,
  id,
  disabled,
  "aria-label": ariaLabel,
}: IconPickerProps) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setSearch("");
    }
  }, [open]);

  const query = search.trim().toLowerCase();
  const allMatches = useMemo(
    () => (query ? ALL_ICON_NAMES.filter((n) => n.includes(query)) : ALL_ICON_NAMES),
    [query],
  );
  const matches = useMemo(() => allMatches.slice(0, MAX_RESULTS), [allMatches]);
  const overflow = allMatches.length - matches.length;

  const handleSelect = (name: string) => {
    onChange(name);
    setOpen(false);
  };

  const handleClear = () => {
    onChange("");
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={ariaLabel}
          className="w-full justify-start gap-2 font-normal"
          disabled={disabled}
        >
          <FeatureIcon name={value} className="size-4 shrink-0" />
          <span className={cn("truncate", !value && "text-muted-foreground")}>
            {value || t("iconPicker.placeholder")}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <div className="flex items-center gap-2 p-2">
          <Input
            ref={inputRef}
            placeholder={t("iconPicker.search_placeholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label={t("iconPicker.search_placeholder")}
          />
          {value ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0"
              aria-label={t("iconPicker.clear")}
              onClick={handleClear}
            >
              <X className="size-4" />
            </Button>
          ) : null}
        </div>
        {matches.length === 0 ? (
          <p className="text-muted-foreground px-3 py-6 text-center text-sm">
            {t("iconPicker.no_results")}
          </p>
        ) : (
          <>
            <div
              role="listbox"
              aria-label={ariaLabel ?? t("iconPicker.placeholder")}
              className="grid max-h-60 grid-cols-6 gap-1 overflow-y-auto p-2"
            >
              {matches.map((name) => (
                <button
                  key={name}
                  type="button"
                  role="option"
                  aria-selected={value === name}
                  aria-label={name}
                  title={name}
                  className={cn(
                    "hover:bg-accent flex aspect-square items-center justify-center rounded-md",
                    value === name && "bg-accent ring-ring ring-2",
                  )}
                  onClick={() => handleSelect(name)}
                >
                  <FeatureIcon name={name} className="size-5" />
                </button>
              ))}
            </div>
            {overflow > 0 ? (
              <p className="text-muted-foreground border-border border-t px-3 py-2 text-xs">
                {t("iconPicker.more_results", { count: overflow })}
              </p>
            ) : null}
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
