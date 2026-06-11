import { z } from "zod";
import i18n from "i18next";

/**
 * Bridge Zod's default validation errors to the `common:zod.*` namespace.
 *
 * Authors of schemas should prefer passing an explicit i18n key as the
 * message (e.g. `z.string().min(1, { message: "auth:errors.password_required" })`).
 * When no message is supplied, this map produces a translated default from
 * the active locale.
 */
export const zodErrorMap: z.core.$ZodErrorMap = (issue) => {
  const t = i18n.getFixedT(null, "common");

  switch (issue.code) {
    case "invalid_type":
      return { message: t("zod.invalid_type") };
    case "invalid_format":
      if (issue.format === "email") {
        return { message: t("zod.invalid_email") };
      }
      return { message: t("zod.invalid_string") };
    case "too_small":
      if (issue.origin === "number" || issue.origin === "int") {
        return {
          message: t("zod.number_too_small", { minimum: String(issue.minimum) }),
        };
      }
      if (issue.minimum === 1) {
        return { message: t("zod.required") };
      }
      return {
        message: t("zod.too_small", { minimum: String(issue.minimum) }),
      };
    case "too_big":
      if (issue.origin === "number" || issue.origin === "int") {
        return {
          message: t("zod.number_too_big", { maximum: String(issue.maximum) }),
        };
      }
      return {
        message: t("zod.too_big", { maximum: String(issue.maximum) }),
      };
    case "custom":
      return { message: t("zod.custom") };
  }

  return undefined;
};
