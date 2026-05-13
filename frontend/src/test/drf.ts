export function drfPage<T>(rows: T[]) {
  return { count: rows.length, next: null, previous: null, results: rows };
}
