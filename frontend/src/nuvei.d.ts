// Nuvei's checkout.js adds a global once loaded.
interface NuveiCheckoutOptions {
  sessionToken: string;
  env: string;
  merchantId: string;
  merchantSiteId: string;
  country: string;
  locale: string;
  currency: string;
  amount: string;
  renderTo: string;
  onResult: (result: unknown) => void;
}

interface Window {
  checkout: (options: NuveiCheckoutOptions) => void;
}
