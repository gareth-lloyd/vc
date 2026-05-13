type Listener = () => void;

const listeners = new Set<Listener>();

export const authChannel = {
  onUnauthorized(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  emitUnauthorized(): void {
    for (const listener of listeners) listener();
  },
};
