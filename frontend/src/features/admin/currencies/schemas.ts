import { z } from "zod";
import { paginated } from "@/lib/api/pagination";

export const currencySchema = z.object({
  id: z.number(),
  code: z.string(),
  name: z.string(),
  symbol: z.string().nullable().optional().default(""),
  decimal_places: z.number().optional().default(2),
  is_active: z.boolean(),
});
export type Currency = z.infer<typeof currencySchema>;

export const currenciesListResponseSchema = paginated(currencySchema);

export const currencyWriteInputSchema = z.object({
  code: z.string().trim().min(3).max(3),
  name: z.string().trim().min(1).max(120),
  symbol: z.string().trim().max(8).optional(),
  decimal_places: z.number().int().min(0).max(8).optional(),
  is_active: z.boolean().optional(),
});
export type CurrencyWriteInput = z.infer<typeof currencyWriteInputSchema>;

export interface CurrencyFilters {
  search?: string;
  page?: number;
}
