import { useEffect, useState } from "react";
import { api, type Entitlement } from "../api";
import { useAuth } from "../auth";

export function Passes() {
  const { me } = useAuth();
  const [passes, setPasses] = useState<Entitlement[] | null>(null);

  useEffect(() => {
    api.entitlements().then(setPasses);
  }, []);

  return (
    <section>
      <h2>My passes</h2>
      {me && (
        <p className="label">
          Member number <strong>{me.member_number}</strong>. Show this number, or your card, at the Spit.{" "}
          <a href="/api/me/card.pdf" target="_blank" rel="noreferrer">
            Download my card (PDF)
          </a>
        </p>
      )}
      {!passes ? (
        <p>Loading…</p>
      ) : passes.length === 0 ? (
        <p>No passes yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Pass</th>
              <th>Grants</th>
              <th>Valid</th>
              <th>Visits left</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {passes.map((pass) => (
              <tr key={pass.id} className={pass.active ? "" : "inactive"}>
                <td>{pass.product_name}</td>
                <td>{pass.kind.replace("_", " ")}</td>
                <td>
                  {pass.valid_from} to {pass.valid_to}
                </td>
                <td>{pass.visits_remaining ?? "—"}</td>
                <td>{pass.active ? "Active" : "Inactive"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
