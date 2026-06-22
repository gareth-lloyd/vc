import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useSearchCompanies } from "../hooks";
import type { Company } from "../schemas";
import { companyDisplayName } from "../display";

interface CompanyPickerProps {
  value: Company | null;
  onChange: (company: Company) => void;
  onCreateNew?: () => void;
  disabled?: boolean;
  // Scope the search by status (e.g. only `active` agencies).
  status?: string;
}

export function CompanyPicker({
  value,
  onChange,
  onCreateNew,
  disabled,
  status,
}: CompanyPickerProps) {
  const { t } = useTranslation("companies");
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(handle);
  }, [search]);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setSearch("");
      setDebouncedSearch("");
    }
  }, [open]);

  const query = useSearchCompanies(debouncedSearch, { status });

  const handleSelect = (company: Company) => {
    onChange(company);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-start font-normal"
          disabled={disabled}
        >
          {value ? companyDisplayName(value) : t("placeholders.picker_trigger")}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="p-2">
          <Input
            ref={inputRef}
            placeholder={t("placeholders.picker_search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label={t("aria.picker_search")}
          />
        </div>
        <div className="max-h-60 overflow-y-auto">
          {debouncedSearch.length < 2 ? (
            <p className="text-muted-foreground px-3 py-2 text-sm">{t("empty.picker_min_chars")}</p>
          ) : query.isLoading ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : query.isError ? (
            <p className="text-destructive px-3 py-2 text-sm">{t("errors.picker_search_failed")}</p>
          ) : query.data?.results.length === 0 ? (
            <p className="text-muted-foreground px-3 py-2 text-sm">
              {t("empty.picker_no_results")}
            </p>
          ) : (
            <ul role="listbox" aria-label={t("aria.picker_results")}>
              {query.data?.results.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={value?.id === c.id}
                    className="hover:bg-accent w-full px-3 py-2 text-left text-sm"
                    onClick={() => handleSelect(c)}
                  >
                    <span className="font-medium">{companyDisplayName(c)}</span>
                    {c.town ? (
                      <span className="text-muted-foreground ml-2 text-xs">{c.town}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {onCreateNew ? (
          <div className="border-border border-t p-2">
            <Button
              type="button"
              variant="ghost"
              className="w-full justify-start text-sm"
              onClick={() => {
                setOpen(false);
                onCreateNew();
              }}
            >
              {t("actions.create_new_inline")}
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
