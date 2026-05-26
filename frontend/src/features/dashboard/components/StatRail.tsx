import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import {
  todayIso,
  useAwaitingBalanceCount,
  useDeparturesTodayCount,
  useNewEnquiriesCount,
} from "../hooks";

interface RailStatProps {
  label: string;
  sublabel?: string;
  value: number | string | undefined;
  to: string;
  loading?: boolean;
  error?: boolean;
  errorLabel: string;
  /** Decorative hue marker on the left edge — picks up service-palette
   *  intent without committing to a specific service. */
  hue: "brand" | "accent" | "sea";
}

function RailStat({ label, sublabel, value, to, loading, error, errorLabel, hue }: RailStatProps) {
  return (
    <Link
      to={to}
      className="bg-card hover:border-brand-300 group focus-visible:ring-ring shadow-card relative block overflow-hidden rounded-lg border px-5 py-4 transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      {/* Edge tick — a thin vertical accent rule on the left of each stat.
          The hue assignment is decorative, not semantic — it just gives
          the rail rhythm rather than three identical cards. */}
      <span
        aria-hidden
        className={cn(
          "absolute top-3 bottom-3 left-0 w-[3px] rounded-r",
          hue === "brand" && "bg-brand-500",
          hue === "accent" && "bg-accent-500",
          hue === "sea" && "bg-info",
        )}
      />
      <div className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 font-serif text-4xl font-semibold tracking-tight tabular-nums",
          error && "text-destructive font-sans text-sm font-normal",
          loading && "text-muted-foreground font-sans text-sm font-normal",
        )}
        style={!error && !loading ? { fontVariationSettings: '"opsz" 144' } : undefined}
      >
        {error ? errorLabel : loading ? "·" : (value ?? "—")}
      </div>
      {sublabel ? <div className="text-muted-foreground mt-0.5 text-xs">{sublabel}</div> : null}
    </Link>
  );
}

/**
 * Side-rail of secondary stats. Reads like the masthead of a magazine:
 * three numerals in serif, set vertically, each linked to its filtered list.
 */
export function StatRail() {
  const { t } = useTranslation("dashboard");
  const today = todayIso();

  const departures = useDeparturesTodayCount();
  const newEnquiries = useNewEnquiriesCount();
  const awaitingBalance = useAwaitingBalanceCount();
  const errorLabel = t("errors.card");

  return (
    <div className="flex flex-col gap-3">
      <RailStat
        label={t("kpis.check_outs_today")}
        value={departures.data}
        to={`/bookings?check_out_after=${today}&check_out_before=${today}&exclude_terminal=true`}
        loading={departures.isLoading}
        error={departures.isError}
        errorLabel={errorLabel}
        hue="sea"
      />
      <RailStat
        label={t("kpis.new_enquiries")}
        sublabel={t("kpis.new_enquiries_sub")}
        value={newEnquiries.data}
        to="/enquiries?status=new"
        loading={newEnquiries.isLoading}
        error={newEnquiries.isError}
        errorLabel={errorLabel}
        hue="accent"
      />
      <RailStat
        label={t("kpis.awaiting_balance")}
        sublabel={t("kpis.awaiting_balance_sub")}
        value={awaitingBalance.data}
        to="/bookings?status=awaiting_balance"
        loading={awaitingBalance.isLoading}
        error={awaitingBalance.isError}
        errorLabel={errorLabel}
        hue="brand"
      />
    </div>
  );
}
