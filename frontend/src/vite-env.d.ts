/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly LEGACY_CUSTOMER_APP_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
