import { LogOut, User as UserIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export interface TopbarUser {
  email: string;
  first_name: string;
  last_name: string;
}

function initials(first: string, last: string): string {
  return `${first[0] ?? ""}${last[0] ?? ""}`.toUpperCase() || "?";
}

export function Topbar({ user, onSignOut }: { user: TopbarUser | null; onSignOut: () => void }) {
  const { t } = useTranslation("common");
  return (
    <header className="bg-card border-border flex h-14 items-center justify-between border-b px-4">
      <div className="flex items-center gap-3">
        <div className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded text-sm font-semibold">
          VC
        </div>
        <span className="text-foreground text-sm font-semibold">Villa Collective</span>
      </div>
      <div className="flex items-center gap-2">
        {user ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <Avatar className="size-7">
                  <AvatarFallback>{initials(user.first_name, user.last_name)}</AvatarFallback>
                </Avatar>
                <span className="hidden sm:inline">{user.email}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="flex flex-col">
                <span>
                  {user.first_name} {user.last_name}
                </span>
                <span className="text-muted-foreground text-xs font-normal">{user.email}</span>
              </DropdownMenuLabel>
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
