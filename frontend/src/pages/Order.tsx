import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, money, type Checkout as CheckoutSession, type Order } from "../api";
import { CardForm } from "../CardForm";

// One order: pay it while it is pending, or see where it ended up.
export function OrderPage() {
  const { orderId } = useParams();
  const id = Number(orderId);
  const location = useLocation();
  const navigate = useNavigate();
  const [session, setSession] = useState<CheckoutSession | null>(
    (location.state as { checkout?: CheckoutSession } | null)?.checkout ?? null,
  );
  const [order, setOrder] = useState<Order | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const refresh = useCallback(() => api.order(id).then(setOrder).catch(() => setProblem("Order not found.")), [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while the processor's notification is on its way.
  useEffect(() => {
    if (!order || order.status !== "pending_payment") return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [order, refresh]);

  // Arrived without a session (reload, closed form, link from the orders
  // page): ask for a fresh one. The order itself is unchanged.
  useEffect(() => {
    if (session || !order || order.status !== "pending_payment" || order.payment_method !== "card") return;
    api
      .reopenCheckout(id)
      .then((reopened) => setSession(reopened.checkout))
      .catch(() => setProblem("The payment form could not be reopened."));
  }, [session, order, id]);

  async function cancel() {
    if (!window.confirm("Cancel this order? Nothing has been charged.")) return;
    await api.cancelOrder(id).catch(() => setProblem("The order could not be cancelled."));
    navigate("/orders");
  }

  if (!order) return <p>{problem ?? "Loading…"}</p>;

  return (
    <section className="card narrow">
      <h2>Order {order.id}</h2>
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
        <p className="ok">
          Paid. Your passes are ready. <Link to="/passes">See my passes</Link>
        </p>
      )}
      {order.status === "cancelled" && <p className="inactive">This order was cancelled.</p>}

      {order.status === "pending_payment" && (
        <>
          {session ? (
            <CardForm orderId={order.id} session={session} onResult={refresh} />
          ) : (
            <p>Opening the payment form…</p>
          )}
          <p className="actions">
            <button className="link" onClick={() => void cancel()}>
              Cancel this order
            </button>
          </p>
        </>
      )}
    </section>
  );
}
