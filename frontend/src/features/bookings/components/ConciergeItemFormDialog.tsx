import { useEffect, useState } from "react";
import { useController, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/errors";
import { applyApiErrorToForm } from "@/lib/api/forms";
import type { BookingId } from "@/lib/query/keys";
import { useCreateConciergeItem, useUpdateConciergeItem } from "../hooks";
import {
  CONCIERGE_TIER_OPTIONS,
  CONCIERGE_UNIT_OPTIONS,
  conciergeItemWriteInputSchema,
  type BookingConciergeItem,
  type ConciergeItemWriteInput,
} from "../schemas";

interface CommonProps {
  bookingId: BookingId;
  defaultCurrency: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreateProps extends CommonProps {
  mode: "create";
}

interface EditProps extends CommonProps {
  mode: "edit";
  item: BookingConciergeItem;
}

type Props = CreateProps | EditProps;

function createDefaults(currency: number): ConciergeItemWriteInput {
  return {
    tier: "quintessential",
    name: "",
    description: "",
    quantity: 1,
    unit: "stay",
    unit_price: "0.00",
    currency,
    notes: "",
  };
}

function defaultsFromItem(item: BookingConciergeItem): ConciergeItemWriteInput {
  return {
    tier: item.tier,
    name: item.name,
    description: item.description ?? "",
    quantity: item.quantity,
    unit: item.unit,
    unit_price: item.unit_price,
    currency: item.currency,
    notes: item.notes ?? "",
  };
}

export function ConciergeItemFormDialog(props: Props) {
  const { bookingId, open, onOpenChange, defaultCurrency } = props;
  const isCreate = props.mode === "create";

  const form = useForm<ConciergeItemWriteInput>({
    resolver: zodResolver(conciergeItemWriteInputSchema),
    defaultValues: isCreate ? createDefaults(defaultCurrency) : defaultsFromItem(props.item),
  });
  const tierCtrl = useController({ control: form.control, name: "tier" });
  const unitCtrl = useController({ control: form.control, name: "unit" });
  const [topLevelError, setTopLevelError] = useState<string | null>(null);

  const createMutation = useCreateConciergeItem(bookingId);
  const updateMutation = useUpdateConciergeItem(bookingId);
  const submitting = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (open) {
      form.reset(isCreate ? createDefaults(defaultCurrency) : defaultsFromItem(props.item));
      setTopLevelError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isCreate ? null : props.item.id]);

  const handleSubmit = async (values: ConciergeItemWriteInput) => {
    setTopLevelError(null);
    try {
      if (isCreate) {
        await createMutation.mutateAsync(values);
      } else {
        await updateMutation.mutateAsync({ itemId: props.item.id, input: values });
      }
      toast.success(isCreate ? "Service added" : "Service updated");
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.isClientError()) {
        const { detail } = applyApiErrorToForm(form, error);
        setTopLevelError(detail);
      } else {
        toast.error("Something went wrong");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isCreate ? "Add concierge service" : "Edit concierge service"}</DialogTitle>
          <DialogDescription>
            Services itemise concierge spend; statuses are action-driven elsewhere.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="concierge-name">Service</Label>
            <Input
              id="concierge-name"
              autoFocus
              {...form.register("name")}
              aria-invalid={!!form.formState.errors.name}
            />
            {form.formState.errors.name ? (
              <p className="text-destructive text-sm" role="alert">
                {form.formState.errors.name.message}
              </p>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="concierge-tier">Tier</Label>
              <Select value={tierCtrl.field.value} onValueChange={tierCtrl.field.onChange}>
                <SelectTrigger id="concierge-tier" aria-label="Tier">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONCIERGE_TIER_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="concierge-unit">Unit</Label>
              <Select value={unitCtrl.field.value} onValueChange={unitCtrl.field.onChange}>
                <SelectTrigger id="concierge-unit" aria-label="Unit">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONCIERGE_UNIT_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="concierge-quantity">Quantity</Label>
              <Input
                id="concierge-quantity"
                type="number"
                min={1}
                step={1}
                {...form.register("quantity", { valueAsNumber: true })}
                aria-invalid={!!form.formState.errors.quantity}
              />
              {form.formState.errors.quantity ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.quantity.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="concierge-unit-price">Unit price</Label>
              <Input
                id="concierge-unit-price"
                inputMode="decimal"
                {...form.register("unit_price")}
                aria-invalid={!!form.formState.errors.unit_price}
              />
              {form.formState.errors.unit_price ? (
                <p className="text-destructive text-sm" role="alert">
                  {form.formState.errors.unit_price.message}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="concierge-description">Description</Label>
            <Textarea id="concierge-description" rows={3} {...form.register("description")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="concierge-notes">Notes</Label>
            <Textarea id="concierge-notes" rows={2} {...form.register("notes")} />
          </div>

          {topLevelError ? (
            <p className="text-destructive text-sm" role="alert">
              {topLevelError}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : isCreate ? "Add service" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
