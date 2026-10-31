import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, money, type Checkout as CheckoutSession, type Order } from "../api";
import { CardForm } from "../CardForm";

// The popup the staff page opens for a card sale. The processor session is
// handed over through sessionStorage, same origin, keyed by order; it is
// never in the URL. Opened without one (a reopened sale, a reload), it asks
// the API for a fresh session. The order is paid only when the API says so.
export function PayWindow() {
  const { orderId } = useParams();
  const id = Number(orderId);
  const [order, setOrder] = useState<Order | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [session, setSession] = useState<CheckoutSession | null>(() => {
    try {
      const raw = sessionStorage.getItem(`checkout:${id}`);
      return raw ? (JSON.parse(raw) as CheckoutSession) : null;
    } catch {
      return null;
    }
  });

  const refresh = useCallback(
    () => api.staffOrderStatus(id).then(setOrder).catch(() => setProblem("Order not found.")),
    [id],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!order || order.status !== "pending_payment") return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [order, refresh]);

  useEffect(() => {
    if (session || !order || order.status !== "pending_payment" || order.payment_method !== "card") return;
    api
      .staffReopenCheckout(id)
      .then((reopened) => setSession(reopened.checkout))
      .catch(() => setProblem("The card form could not be reopened. Close this window and try again."));
  }, [session, order, id]);

  useEffect(() => {
    if (order?.status === "paid") sessionStorage.removeItem(`checkout:${id}`);
  }, [order, id]);

  if (!order) return <p className="pay">{problem ?? "Loading…"}</p>;

  return (
    <section className="pay">
      <h2>Card payment</h2>
      <ul>
        {order.lines.map((line) => (
          <li key={line.product_name}>
            {line.product_name} <strong>{money(line.amount_cents, order.currency)}</strong>
          </li>
        ))}
      </ul>
      <p className="price">Total {money(order.total_cents, order.currency)}</p>
      {problem && <p className="problem">{problem}</p>}
      {order.status === "paid" && (
        <p className="ok banner">
          Paid. You can close this window.
          <br />
          <button onClick={() => window.close()}>Close</button>
        </p>
      )}
      {order.status === "cancelled" && <p className="inactive">This order was cancelled. Close this window.</p>}
      {order.status === "pending_payment" &&
        (session ? <CardForm orderId={order.id} session={session} onResult={refresh} /> : <p>Opening the card form…</p>)}
    </section>
  );
}
