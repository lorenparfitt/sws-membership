import { useEffect, useRef, useState } from "react";
import { api, type Checkout as CheckoutSession } from "./api";

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

// The processor's own card form, rendered for one checkout session. Card
// details go from this form to the processor; nothing passes through our API.
// The fake processor has no form, so it shows an approve button instead.
export function CardForm({
  orderId,
  session,
  onResult,
}: {
  orderId: number;
  session: CheckoutSession;
  onResult: () => void;
}) {
  const rendered = useRef(false);
  const [problem, setProblem] = useState<string | null>(null);
  const target = `card-form-${orderId}`;

  useEffect(() => {
    if (session.processor !== "nuvei" || rendered.current) return;
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
          renderTo: `#${target}`,
          onResult,
        });
      })
      .catch(() => setProblem("The card form could not be loaded."));
  }, [session, target, onResult]);

  if (problem) return <p className="problem">{problem}</p>;
  if (session.processor === "fake") {
    return (
      <div>
        <p className="label">Development: no card form. The fake processor approves on request.</p>
        <button onClick={() => api.fakeApprove(orderId).then(onResult)}>Simulate approved card payment</button>
      </div>
    );
  }
  return <div id={target} />;
}
