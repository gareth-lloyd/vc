import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useSearchContacts } from "../hooks";
import type { Contact } from "../schemas";
import { contactDisplayName } from "../tabs/PeopleTab";

interface ContactPickerProps {
  value: Contact | null;
  onChange: (contact: Contact) => void;
  onCreateNew?: () => void;
  disabled?: boolean;
}

export function ContactPicker({ value, onChange, onCreateNew, disabled }: ContactPickerProps) {
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

  const query = useSearchContacts(debouncedSearch);

  const handleSelect = (contact: Contact) => {
    onChange(contact);
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
          {value ? contactDisplayName(value) : "Select a contact…"}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <div className="p-2">
          <Input
            ref={inputRef}
            placeholder="Search contacts…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search contacts"
          />
        </div>
        <div className="max-h-60 overflow-y-auto">
          {debouncedSearch.length < 2 ? (
            <p className="text-muted-foreground px-3 py-2 text-sm">
              Type at least 2 characters to search
            </p>
          ) : query.isLoading ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : query.isError ? (
            <p className="text-destructive px-3 py-2 text-sm">Search failed</p>
          ) : query.data?.results.length === 0 ? (
            <p className="text-muted-foreground px-3 py-2 text-sm">No contacts found</p>
          ) : (
            <ul role="listbox" aria-label="Search results">
              {query.data?.results.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={value?.id === c.id}
                    className="hover:bg-accent w-full px-3 py-2 text-left text-sm"
                    onClick={() => handleSelect(c)}
                  >
                    <span className="font-medium">{contactDisplayName(c)}</span>
                    {c.emails?.[0] ? (
                      <span className="text-muted-foreground ml-2 text-xs">
                        {c.emails[0].email}
                      </span>
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
              + Create new contact
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
