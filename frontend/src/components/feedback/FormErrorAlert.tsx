interface Props {
  message: string | null;
}

export function FormErrorAlert({ message }: Props) {
  if (!message) return null;
  return (
    <div
      className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
      role="alert"
    >
      {message}
    </div>
  );
}
