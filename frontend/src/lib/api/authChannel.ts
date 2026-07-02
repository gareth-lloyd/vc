type Listener = () => void;

const unauthorizedListeners = new Set<Listener>();
const enrollmentListeners = new Set<Listener>();

export const authChannel = {
  onUnauthorized(listener: Listener): () => void {
    unauthorizedListeners.add(listener);
    return () => unauthorizedListeners.delete(listener);
  },
  emitUnauthorized(): void {
    for (const listener of unauthorizedListeners) listener();
  },
  // Emitted on a 403 `tfa_enrollment_required` — a staff user who must enrol
  // in 2FA before using the API. Distinct from `unauthorized` (which logs the
  // user out); the subscriber routes to /enroll-2fa without clearing the
  // session.
  onEnrollmentRequired(listener: Listener): () => void {
    enrollmentListeners.add(listener);
    return () => enrollmentListeners.delete(listener);
  },
  emitEnrollmentRequired(): void {
    for (const listener of enrollmentListeners) listener();
  },
};
