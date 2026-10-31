import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, money, type Checkout as CheckoutSession, type Order } from "../api";

const NUVEI_SCRIPT = "https://cdn.safecharge.com/safecharge_resources/v1/checkout/checkout.js";

// The popup the staff page opens for a card sale. The processor session is
// handed over through sessionStorage, same origin, keyed by order; it is
// never in the URL. The order is paid only when the API says so.
export function PayWindow() {
  const { orderId } = useParams();
  const id = Number(orderId);
  const [order, setOrder] = useState<Order | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const rendered = useRef(false);
  const session = (() => {
    try {
      const raw = sessionStorage.getItem(`checkout:${id}`);
      return raw ? (JSON.parse(raw) as CheckoutSession) : null;
    } catch {
      return null;
    }
  })();

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
    if (!order || order.status !== "pending_payment" || !session || session.processor !== "nuvei") return;
    if (rendered.current) return;
    rendered.current = true;
    const script = document.createElement("script");
    script.src = NUVEI_SCRIPT;
    script.onload = () =>
      window.checkout({
        sessionToken: session.session_token,
        env: session.parameters.env,
        merchantId: session.parameters.merchantId,
        merchantSiteId: session.parameters.merchantSiteId,
        country: "CA",
        locale: "en_CA",
        currency: session.parameters.currency,
        amount: session.parameters.amount,
        renderTo: "#checkout",
        onResult: () => void refresh(),
      });
    script.onerror = () => setProblem("The card form could not be loaded.");
    document.head.appendChild(script);
  }, [order, session, refresh]);

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
      {order.status === "pending_payment" && !session && (
        <p className="problem">This window has no card session. Close it and start the sale again.</p>
      )}
      {order.status === "pending_payment" && session?.processor === "nuvei" && <div id="checkout" />}
      {order.status === "pending_payment" && session?.processor === "fake" && (
        <div>
          <p className="label">Development: no card form. The fake processor approves on request.</p>
          <button onClick={() => api.fakeApprove(order.id).then(() => refresh())}>
            Simulate approved card payment
          </button>
        </div>
      )}
    </section>
  );
}
