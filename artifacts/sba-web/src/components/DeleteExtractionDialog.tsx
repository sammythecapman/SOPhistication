import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useDeleteExtraction,
  getListExtractionsQueryKey,
  getGetExtractionQueryKey,
} from "@workspace/api-client-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useToast } from "@/hooks/use-toast";

export type DeleteExtractionDialogProps = {
  extractionId: number;
  borrowerName?: string | null;
  termsFilename?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
};

export function DeleteExtractionDialog({
  extractionId,
  borrowerName,
  termsFilename,
  open,
  onOpenChange,
  onDeleted,
}: DeleteExtractionDialogProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { mutate, isPending } = useDeleteExtraction();

  const label =
    (borrowerName && borrowerName.trim()) ||
    (termsFilename && termsFilename.trim()) ||
    "this deal";

  const handleConfirm = (e: React.MouseEvent) => {
    // Prevent the default AlertDialog auto-close on click — we control
    // closing ourselves so the dialog stays open on error for retry.
    e.preventDefault();
    mutate(
      { id: extractionId },
      {
        onSuccess: () => {
          toast({
            title: "Extraction deleted",
            description: `Removed extraction for ${label}.`,
          });
          // Invalidate every paginated variant of the listExtractions
          // query — getListExtractionsQueryKey is parameterised by
          // {page, per_page}, so invalidating by the unpaginated prefix
          // covers all currently-cached pages.
          queryClient.invalidateQueries({
            queryKey: getListExtractionsQueryKey().slice(0, 1),
          });
          // Drop the per-extraction detail cache too, so navigating back
          // to /extraction/<deleted-id> doesn't briefly flash stale data
          // before the 404 lands.
          queryClient.removeQueries({
            queryKey: getGetExtractionQueryKey(extractionId),
          });
          onOpenChange(false);
          onDeleted?.();
        },
        onError: (error: unknown) => {
          const message =
            error instanceof Error
              ? error.message
              : "Could not delete the extraction. Please try again.";
          toast({
            variant: "destructive",
            title: "Delete failed",
            description: message,
          });
          // Leave dialog open so the user can retry or cancel.
        },
      },
    );
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this extraction?</AlertDialogTitle>
          <AlertDialogDescription>
            This will permanently delete the extraction for{" "}
            <span className="font-medium text-foreground">{label}</span>. This
            action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isPending}
            className="bg-red-600 text-white hover:bg-red-700 focus:ring-red-600"
          >
            {isPending ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
