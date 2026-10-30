import { useEffect, useState } from "react";

export function App() {
  const [apiStatus, setApiStatus] = useState<string>("checking");

  useEffect(() => {
    fetch("/health")
      .then((response) => response.json())
      .then((body: { status: string }) => setApiStatus(body.status))
      .catch(() => setApiStatus("unreachable"));
  }, []);

  return (
    <main>
      <h1>SWS Membership</h1>
      <p>API: {apiStatus}</p>
    </main>
  );
}
