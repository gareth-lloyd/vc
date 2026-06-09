interface DrfPageOpts {
  // A non-null `next` simulates a further page; `count` defaults to the row
  // length but can be overridden to model a total larger than this page.
  next?: string | null;
  previous?: string | null;
  count?: number;
}

export function drfPage<T>(rows: T[], opts: DrfPageOpts = {}) {
  return {
    count: opts.count ?? rows.length,
    next: opts.next ?? null,
    previous: opts.previous ?? null,
    results: rows,
  };
}
