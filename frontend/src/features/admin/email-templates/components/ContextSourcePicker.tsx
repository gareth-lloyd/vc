import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ContextSource } from "../schemas";

type SourceKind = ContextSource["kind"];

// The render-context picker shared by the live preview and the test-send dialog:
// None / Booking id / Quotation id / raw JSON. `kind` drives the Select and which
// input shows; the raw text lives here, and the derived `ContextSource` is pushed
// up via `onChange` — a half-typed id resolves to `{ kind: "none" }` rather than
// firing a bad request.
export function ContextSourcePicker({ onChange }: { onChange: (source: ContextSource) => void }) {
  const { t } = useTranslation("admin");
  const [kind, setKind] = useState<SourceKind>("none");
  const [idText, setIdText] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState(false);

  const source = useMemo<ContextSource>(() => {
    if (kind === "booking" || kind === "quotation") {
      const n = Number(idText);
      if (idText && Number.isInteger(n) && n > 0) {
        return kind === "booking"
          ? { kind: "booking", bookingId: n }
          : { kind: "quotation", quotationId: n };
      }
      return { kind: "none" };
    }
    if (kind === "json") {
      if (!jsonText.trim()) return { kind: "json", context: {} };
      try {
        return { kind: "json", context: JSON.parse(jsonText) as Record<string, unknown> };
      } catch {
        return { kind: "none" };
      }
    }
    return { kind: "none" };
  }, [kind, idText, jsonText]);

  useEffect(() => {
    onChange(source);
  }, [source, onChange]);

  const onKindChange = (value: string) => {
    setIdText("");
    setJsonText("");
    setJsonError(false);
    setKind(value as SourceKind);
  };

  const onJsonChange = (raw: string) => {
    setJsonText(raw);
    if (!raw.trim()) {
      setJsonError(false);
      return;
    }
    try {
      JSON.parse(raw);
      setJsonError(false);
    } catch {
      setJsonError(true);
    }
  };

  return (
    <div className="space-y-2">
      <Label>{t("email_templates.preview.context_source")}</Label>
      <Select value={kind} onValueChange={onKindChange}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">{t("email_templates.preview.source_none")}</SelectItem>
          <SelectItem value="booking">{t("email_templates.preview.source_booking")}</SelectItem>
          <SelectItem value="quotation">{t("email_templates.preview.source_quotation")}</SelectItem>
          <SelectItem value="json">{t("email_templates.preview.source_json")}</SelectItem>
        </SelectContent>
      </Select>

      {kind === "booking" || kind === "quotation" ? (
        <Input
          type="number"
          min={1}
          value={idText}
          placeholder={t(
            kind === "booking"
              ? "email_templates.preview.booking_id_placeholder"
              : "email_templates.preview.quotation_id_placeholder",
          )}
          onChange={(e) => setIdText(e.target.value)}
        />
      ) : null}

      {kind === "json" ? (
        <div className="space-y-1">
          <Textarea
            rows={4}
            value={jsonText}
            placeholder={t("email_templates.preview.json_placeholder")}
            onChange={(e) => onJsonChange(e.target.value)}
            className="font-mono text-xs"
          />
          {jsonError ? (
            <p className="text-destructive text-xs" role="alert">
              {t("email_templates.preview.json_invalid")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
