import { useEffect, useState } from "react";

import { apiFetch } from "./api/client";
import type { HealthResponse } from "./types/health";

export default function App() {
  const [status, setStatus] = useState<string>("checking…");

  useEffect(() => {
    apiFetch<HealthResponse>("/health")
      .then((h) => setStatus(h.status))
      .catch(() => setStatus("unavailable"));
  }, []);

  return (
    <main>
      <h1>DocVault</h1>
      <p>
        API status: <strong data-testid="api-status">{status}</strong>
      </p>
    </main>
  );
}
