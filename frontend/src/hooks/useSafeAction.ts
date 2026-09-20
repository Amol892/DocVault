import { useCallback } from "react";
import { errorMessage } from "@/api/client";
import { useToast } from "@/hooks/useToast";

export type ActionResult<T> = { ok: true; value: T } | { ok: false };

/**
 * Runs an API call and turns any failure into a toast, so event handlers never leave an
 * unhandled promise rejection and the user always sees why something did not happen.
 */
export function useSafeAction() {
  const toast = useToast();
  return useCallback(
    async <T>(action: () => Promise<T>): Promise<ActionResult<T>> => {
      try {
        return { ok: true, value: await action() };
      } catch (err) {
        toast(errorMessage(err));
        return { ok: false };
      }
    },
    [toast],
  );
}
