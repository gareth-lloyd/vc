import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ApiError } from "@/lib/api/errors";
import type { BookingId } from "@/lib/query/keys";
import {
  useBookingDamageClaims,
  useDeleteDamageClaimPhoto,
  useUploadDamageClaimPhoto,
} from "../hooks";
import type { DamageClaimPhoto } from "../schemas";

interface Props {
  bookingId: BookingId;
  claimId: number;
  claimReference: string;
  canWrite: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// Pull the inline message out of a 4xx: prefer the image field error the
// serializer emits (e.g. the >10 MB guard), else the top-level detail.
function clientErrorMessage(error: ApiError): string {
  const imageErrors = error.fieldErrors.image;
  if (Array.isArray(imageErrors) && typeof imageErrors[0] === "string") {
    return imageErrors[0];
  }
  return error.detail;
}

export function DamageClaimPhotosDialog({
  bookingId,
  claimId,
  claimReference,
  canWrite,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("bookings");
  const claims = useBookingDamageClaims(bookingId);
  const uploadMutation = useUploadDamageClaimPhoto(bookingId);
  const deleteMutation = useDeleteDamageClaimPhoto(bookingId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [caption, setCaption] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);

  // The claim (and its embedded photos) lives in the list cache; an
  // upload/delete invalidates that query, so the grid re-renders live.
  const claim = claims.data?.results.find((c) => c.id === claimId);
  const photos: DamageClaimPhoto[] = claim?.photos ?? [];

  const handleUpload = async (file: File) => {
    setUploadError(null);
    try {
      await uploadMutation.mutateAsync({ claimId, image: file, caption: caption.trim() });
    } catch (err) {
      // 4xx (e.g. oversize) → inline; 5xx / network → toast, dialog stays open.
      if (err instanceof ApiError && err.isClientError()) {
        setUploadError(clientErrorMessage(err));
      } else {
        toast.error(t("damage_claims.photos.upload_failed"));
      }
    } finally {
      // File + caption are entered and submitted as a unit; reset both after
      // every attempt so a leftover caption can't ride onto the next file.
      setCaption("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (photoId: number) => {
    // Clear any stale upload error so a prior 4xx doesn't linger after a delete.
    setUploadError(null);
    try {
      await deleteMutation.mutateAsync({ claimId, photoId });
    } catch {
      toast.error(t("damage_claims.photos.delete_failed"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("damage_claims.photos.title")}</DialogTitle>
          <DialogDescription>
            {t("damage_claims.photos.description", { reference: claimReference })}
          </DialogDescription>
        </DialogHeader>

        {photos.length === 0 ? (
          <EmptyState
            title={t("damage_claims.photos.empty_title")}
            description={t("damage_claims.photos.empty_description")}
          />
        ) : (
          <ul className="grid grid-cols-3 gap-3">
            {photos.map((photo) => (
              <li key={photo.id} className="space-y-1">
                <a
                  href={photo.image_url ?? undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block"
                >
                  <img
                    src={photo.image_url ?? undefined}
                    alt={photo.caption || t("damage_claims.photos.thumbnail_alt")}
                    className="border-border aspect-square w-full rounded-md border object-cover"
                  />
                </a>
                {photo.caption ? (
                  <p className="text-muted-foreground truncate text-xs">{photo.caption}</p>
                ) : null}
                {canWrite ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive h-auto p-0 text-xs"
                    aria-label={t("damage_claims.photos.delete_for", { id: photo.id })}
                    disabled={deleteMutation.isPending}
                    onClick={() => handleDelete(photo.id)}
                  >
                    {t("common:actions.delete")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {canWrite ? (
          <div className="space-y-2">
            <Input
              placeholder={t("damage_claims.photos.caption_placeholder")}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              aria-label={t("damage_claims.photos.caption_label")}
            />
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              aria-label={t("damage_claims.photos.upload_label")}
              disabled={uploadMutation.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleUpload(file);
              }}
              className="text-sm"
            />
            {uploadError ? <p className="text-destructive text-xs">{uploadError}</p> : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
