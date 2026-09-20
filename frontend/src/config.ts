/** Upload size limit in MB. Must match the API's MAX_UPLOAD_MB (PRD FR-5 default: 100). */
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB ?? 100);

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
