import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import type { EnquiryId } from "@/lib/query/keys";
import { useAssignEnquiry } from "../hooks";

interface AssignDialogProps {
  enquiryId: EnquiryId;
  currentUserId: number | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// TODO: replace the numeric user-id input with a real operator picker once
// /users (or similar) is exposed by the API. KISS for now.
export function AssignDialog({ enquiryId, currentUserId, open, onOpenChange }: AssignDialogProps) {
  const mutation = useAssignEnquiry(enquiryId);
  const [value, setValue] = useState<string>(currentUserId != null ? String(currentUserId) : "");
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setValue(currentUserId != null ? String(currentUserId) : "");
      setTopLevelError(null);
    }
  }, [open, currentUserId]);

  const handleSubmit = async () => {
    setTopLevelError(null);
    const trimmed = value.trim();
    const userId = trimmed === "" ? null : Number(trimmed);
    if (trimmed !== "" && !Number.isInteger(userId)) {
      setTopLevelError("User id must be an integer or blank to unassign.");
      return;
    }
    try {
      await mutation.mutateAsync({ user: userId });
      toast.success(userId == null ? "Enquiry unassigned" : "Enquiry assigned");
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        setTopLevelError(error.detail);
      } else {
        toast.error("Something went wrong");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Assign enquiry</DialogTitle>
          <DialogDescription>
            Enter the user id of the operator to assign. Leave blank to unassign.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="assign-user-id">User id</Label>
            <Input
              id="assign-user-id"
              type="number"
              inputMode="numeric"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
          </div>
          {topLevelError ? (
            <div
              className="bg-destructive/10 text-destructive border-destructive/40 rounded-md border p-3 text-sm"
              role="alert"
            >
              {topLevelError}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Assign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
