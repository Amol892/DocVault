import { apiClient } from "./client";
import type { ActivityLogEntry, Paginated } from "@/types";

export const activityApi = {
  list(workspaceId: string, page = 1): Promise<Paginated<ActivityLogEntry>> {
    return apiClient.get<Paginated<ActivityLogEntry>>(`/workspaces/${workspaceId}/activity`, {
      page,
    });
  },
};
