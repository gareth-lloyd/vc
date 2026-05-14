import { useTranslation } from "react-i18next";
import { useOutletContext } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { FactList, FactRow } from "@/components/data/FactList";
import { ErrorState } from "@/components/feedback/ErrorState";
import { EmptyState } from "@/components/feedback/EmptyState";
import { formatDate } from "@/lib/format/date";
import { usePropertyDescriptions, usePropertyFeatures, usePropertyRooms } from "../hooks";
import type { PropertyDetail } from "../schemas";

interface DetailsContext {
  property: PropertyDetail;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-foreground text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function DetailsTab() {
  const { t } = useTranslation("properties");
  const { property } = useOutletContext<DetailsContext>();
  const descriptions = usePropertyDescriptions(property.slug || property.id);
  const features = usePropertyFeatures(property.slug || property.id);
  const rooms = usePropertyRooms(property.slug || property.id);

  const dash = t("common.unset");

  return (
    <div className="space-y-8 p-6">
      <Section title={t("details.sections.overview")}>
        <FactList>
          <FactRow label={t("details.fields.name")} value={property.name} />
          <FactRow label={t("details.fields.display_name")} value={property.display_name || dash} />
          <FactRow label={t("details.fields.slug")} value={property.slug || dash} />
          <FactRow
            label={t("details.fields.licence_number")}
            value={property.licence_number || dash}
          />
          <FactRow label={t("details.fields.channel")} value={property.channel || dash} />
          <FactRow label={t("details.fields.legacy_id")} value={property.legacy_id ?? dash} />
          <FactRow label={t("details.fields.created")} value={formatDate(property.created_at)} />
          <FactRow label={t("details.fields.updated")} value={formatDate(property.updated_at)} />
        </FactList>
      </Section>

      <Section title={t("details.sections.description")}>
        {descriptions.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : descriptions.isError ? (
          <ErrorState
            title={t("details.descriptions.error_title")}
            description={t("details.descriptions.error_body")}
            onRetry={() => descriptions.refetch()}
          />
        ) : descriptions.data?.results.length ? (
          <div className="space-y-4">
            {descriptions.data.results.slice(0, 1).map((d) => (
              <div key={d.id} className="border-border bg-card rounded-lg border p-4">
                {d.title ? <h3 className="mb-2 text-sm font-medium">{d.title}</h3> : null}
                {d.body_html ? (
                  <div className="prose-sm" dangerouslySetInnerHTML={{ __html: d.body_html }} />
                ) : (
                  <p className="text-sm whitespace-pre-line">{d.body ?? dash}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title={t("details.descriptions.empty_title")} />
        )}
      </Section>

      <Section title={t("details.sections.features")}>
        {features.isLoading ? (
          <Skeleton className="h-10 w-full" />
        ) : features.isError ? (
          <ErrorState
            title={t("details.features.error_title")}
            description={t("details.features.error_body")}
            onRetry={() => features.refetch()}
          />
        ) : features.data?.results.length ? (
          <div className="flex flex-wrap gap-2">
            {features.data.results.map((f) => (
              <Badge key={f.id} variant="secondary">
                {f.name ?? f.slug ?? `#${f.id}`}
              </Badge>
            ))}
          </div>
        ) : (
          <EmptyState title={t("details.features.empty_title")} />
        )}
      </Section>

      <Section title={t("details.sections.rooms")}>
        {rooms.isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : rooms.isError ? (
          <ErrorState
            title={t("details.rooms.error_title")}
            description={t("details.rooms.error_body")}
            onRetry={() => rooms.refetch()}
          />
        ) : rooms.data?.results.length ? (
          <ul className="border-border bg-card divide-border divide-y rounded-lg border">
            {rooms.data.results.map((room) => (
              <li key={room.id} className="flex items-center justify-between px-4 py-2 text-sm">
                <span>
                  {room.name ?? room.kind ?? t("details.rooms.fallback_name", { id: room.id })}
                </span>
                {room.count ? <span className="text-muted-foreground">×{room.count}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title={t("details.rooms.empty_title")} />
        )}
      </Section>
    </div>
  );
}
