/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the DocVault API. Defaults to "/api/v1" (proxied by Vite in dev). */
  readonly VITE_API_BASE_URL?: string;
  /** Upload size limit shown/enforced in the UI, in MB. Keep equal to the API's MAX_UPLOAD_MB. */
  readonly VITE_MAX_UPLOAD_MB?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
