import { apiGet, apiSend } from "@/lib/api/client";
import type { QueryParams } from "@/lib/api/url";
import type { Paginated } from "@/types/api";
import {
  currenciesListResponseSchema,
  currencySchema,
  type Currency,
  type CurrencyFilters,
  type CurrencyWriteInput,
} from "./schemas";

function toQuery(filters: CurrencyFilters): QueryParams {
  return {
    search: filters.search || undefined,
    page: filters.page && filters.page > 1 ? filters.page : undefined,
  };
}

export async function fetchCurrencies(filters: CurrencyFilters): Promise<Paginated<Currency>> {
  const data = await apiGet<unknown>("/currencies", { query: toQuery(filters) });
  return currenciesListResponseSchema.parse(data);
}

export async function fetchCurrency(code: string): Promise<Currency> {
  const data = await apiGet<unknown>(`/currencies/${code}`);
  return currencySchema.parse(data);
}

export async function createCurrency(body: CurrencyWriteInput): Promise<Currency> {
  const data = await apiSend<unknown>("POST", "/currencies", body);
  return currencySchema.parse(data);
}

export async function updateCurrency(
  code: string,
  body: Partial<CurrencyWriteInput>,
): Promise<Currency> {
  const data = await apiSend<unknown>("PATCH", `/currencies/${code}`, body);
  return currencySchema.parse(data);
}

export async function deleteCurrency(code: string): Promise<void> {
  await apiSend<void>("DELETE", `/currencies/${code}`);
}
