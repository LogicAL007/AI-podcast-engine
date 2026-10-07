import { useEffect, useState } from "react";

type Health = { status: string; version: string };

export function App() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json() as Promise<Health>)
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <main>
      <h1>AI Podcast Engine</h1>
      <p>API: {health ? `${health.status} (v${health.version})` : "unreachable"}</p>
    </main>
  );
}
