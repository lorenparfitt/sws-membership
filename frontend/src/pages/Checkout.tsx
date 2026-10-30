import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, money, type Checkout as CheckoutSession, type Order } from "../api";

const NUVEI_SCRIPT = "https://cdn.safecharge.com/safecharge_resources/v1/checkout/checkout.js";

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`failed to load ${src}`));
    document.head.appendChild(script);
  });
}

export function Checkout() {
  const { orderId } = useParams();
  const id = Number(orderId);
  const location = useLocation();
  const session = (location.state as { checkout?: CheckoutSession } | null)?.checkout ?? null;
  const [order, setOrder] = useState<Order | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const rendered = useRef(false);

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

  // Nuvei: render its hosted card form into #checkout once.
  useEffect(() => {
    if (!order || order.status !== "pending_payment" || !session || session.processor !== "nuvei") return;
    if (rendered.current) return;
    rendered.current = true;
    loadScript(NUVEI_SCRIPT)
      .then(() => {
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
      })
      .catch(() => setProblem("The card form could not be loaded."));
  }, [order, session, refresh]);

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

      {order.status === "pending_payment" && !session && (
        <p>Waiting for payment to be confirmed… If you closed the card form, start the purchase again.</p>
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
