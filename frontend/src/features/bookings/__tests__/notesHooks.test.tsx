import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { server } from "@/test/msw/server";
import { queryKeys } from "@/lib/query/keys";
import type { Paginated } from "@/types/api";
import {
  useCreateBookingNote,
  useDeleteBookingNote,
  useToggleBookingNotePin,
  useUpdateBookingNote,
} from "../hooks";
import type { BookingNote } from "../schemas";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

const BOOKING_ID = 51;

function makeNote(overrides: Partial<BookingNote> = {}): BookingNote {
  return {
    id: 1,
    booking: BOOKING_ID,
    author: 1,
    kind: "general",
    body: "hello",
    is_pinned: false,
    visibility: "staff_only",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

function wrapperWith(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  vi.mocked(toast.success).mockClear();
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  server.resetHandlers();
});

describe("useCreateBookingNote", () => {
  it("POSTs the body, returns the parsed note, invalidates the notes cache", async () => {
    const client = createClient();
    const notesKey = queryKeys.bookings.notes(BOOKING_ID);
    client.setQueryData<Paginated<BookingNote>>(notesKey, {
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    let receivedBody: unknown = null;
    server.use(
      http.post(`/api/v1/bookings/${BOOKING_ID}/notes`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeNote({ id: 100, body: "new note" }), { status: 201 });
      }),
    );

    const { result } = renderHook(() => useCreateBookingNote(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    let returned: BookingNote | undefined;
    await act(async () => {
      returned = await result.current.mutateAsync({
        body: "new note",
        kind: "general",
        visibility: "staff_only",
        is_pinned: false,
      });
    });

    expect(returned?.id).toBe(100);
    expect(receivedBody).toMatchObject({ body: "new note", kind: "general" });
    const state = client.getQueryState(notesKey);
    expect(state?.isInvalidated).toBe(true);
  });
});

describe("useUpdateBookingNote", () => {
  it("PATCHes the right URL with a partial body", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/notes/7`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(makeNote({ id: 7, body: "edited" }));
      }),
    );

    const client = createClient();
    const { result } = renderHook(() => useUpdateBookingNote(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ noteId: 7, input: { body: "edited" } });
    });

    expect(receivedBody).toEqual({ body: "edited" });
  });
});

describe("useDeleteBookingNote", () => {
  it("issues DELETE and tolerates 204", async () => {
    let deletedPath: string | null = null;
    server.use(
      http.delete(`/api/v1/bookings/${BOOKING_ID}/notes/9`, ({ request }) => {
        deletedPath = new URL(request.url).pathname;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const client = createClient();
    const { result } = renderHook(() => useDeleteBookingNote(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ noteId: 9 });
    });

    expect(deletedPath).toBe(`/api/v1/bookings/${BOOKING_ID}/notes/9`);
  });
});

describe("useToggleBookingNotePin", () => {
  it("optimistically writes the new pin value to the cache before the server returns", async () => {
    const client = createClient();
    const notesKey = queryKeys.bookings.notes(BOOKING_ID);
    const initial: Paginated<BookingNote> = {
      count: 1,
      next: null,
      previous: null,
      results: [makeNote({ id: 5, is_pinned: false })],
    };
    client.setQueryData(notesKey, initial);

    let resolveServer: () => void = () => {};
    const serverPending = new Promise<void>((resolve) => {
      resolveServer = resolve;
    });

    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/notes/5`, async () => {
        await serverPending;
        return HttpResponse.json(makeNote({ id: 5, is_pinned: true }));
      }),
    );

    const { result } = renderHook(() => useToggleBookingNotePin(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    let mutatePromise: Promise<unknown> | undefined;
    await act(async () => {
      mutatePromise = result.current.mutateAsync({ noteId: 5, is_pinned: true });
      await Promise.resolve();
    });

    await waitFor(() => {
      const cached = client.getQueryData<Paginated<BookingNote>>(notesKey);
      expect(cached?.results[0]?.is_pinned).toBe(true);
    });

    resolveServer();
    await act(async () => {
      await mutatePromise;
    });
  });

  it("rolls back to the snapshot on error and calls toast.error", async () => {
    const client = createClient();
    const notesKey = queryKeys.bookings.notes(BOOKING_ID);
    const initial: Paginated<BookingNote> = {
      count: 1,
      next: null,
      previous: null,
      results: [makeNote({ id: 5, is_pinned: false })],
    };
    client.setQueryData(notesKey, initial);

    server.use(
      http.patch(`/api/v1/bookings/${BOOKING_ID}/notes/5`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useToggleBookingNotePin(BOOKING_ID), {
      wrapper: wrapperWith(client),
    });

    await act(async () => {
      await result.current.mutateAsync({ noteId: 5, is_pinned: true }).catch(() => {});
    });

    await waitFor(() => {
      const cached = client.getQueryData<Paginated<BookingNote>>(notesKey);
      expect(cached?.results[0].is_pinned).toBe(false);
    });
    expect(toast.error).toHaveBeenCalled();
  });
});
