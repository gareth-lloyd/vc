import { LogOut, User as UserIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useUpdateMe } from "@/features/auth/hooks";
import { DEFAULT_LANGUAGE, LANGUAGE_AUTONYMS, SUPPORTED_LANGUAGES } from "@/i18n";

export interface TopbarUser {
  email: string;
  first_name: string;
  last_name: string;
}

function initials(first: string, last: string): string {
  return `${first[0] ?? ""}${last[0] ?? ""}`.toUpperCase() || "?";
}

export function Topbar({ user, onSignOut }: { user: TopbarUser | null; onSignOut: () => void }) {
  const { t, i18n } = useTranslation("common");
  const updateMe = useUpdateMe();
  const currentLanguage = i18n.resolvedLanguage ?? DEFAULT_LANGUAGE;

  const handleLanguageChange = (next: string) => {
    if (next === currentLanguage) return;
    void i18n.changeLanguage(next);
    updateMe.mutate(
      { preferred_language: next },
      {
        onError: () => {
          void i18n.changeLanguage(currentLanguage);
          toast.error(t("errors.generic"));
        },
      },
    );
  };

  return (
    <header
      className="bg-background/80 supports-[backdrop-filter]:bg-background/60 flex h-12 items-center justify-between border-b border-[color:var(--border)] px-5 backdrop-blur"
      style={{
        borderBottomColor: "color-mix(in oklch, var(--brand-200) 60%, transparent)",
      }}
    >
      {/* Wordmark lives in the sidebar now. The topbar carries
          context-of-place: small dated stamp on the left, account chip
          on the right. */}
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground font-mono text-[10px] tracking-[0.24em] uppercase">
          {new Date()
            .toLocaleDateString("en-GB", {
              weekday: "long",
              day: "numeric",
              month: "long",
            })
            .toUpperCase()}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {user ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <Avatar className="ring-accent-500/40 size-7 ring-2 ring-offset-2 ring-offset-[color:var(--background)]">
                  <AvatarFallback className="bg-brand-100 text-brand-800 font-serif text-[11px] font-semibold">
                    {initials(user.first_name, user.last_name)}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden text-xs sm:inline">{user.email}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="flex flex-col">
                <span className="font-serif text-base">
                  {user.first_name} {user.last_name}
                </span>
                <span className="text-muted-foreground text-xs font-normal">{user.email}</span>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
                {t("nav.language")}
              </DropdownMenuLabel>
              <DropdownMenuRadioGroup value={currentLanguage} onValueChange={handleLanguageChange}>
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <DropdownMenuRadioItem key={lang} value={lang}>
                    {LANGUAGE_AUTONYMS[lang]}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>
                <UserIcon className="mr-2 size-4" /> {t("nav.profile")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onSignOut}>
                <LogOut className="mr-2 size-4" /> {t("nav.sign_out")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </header>
  );
}
