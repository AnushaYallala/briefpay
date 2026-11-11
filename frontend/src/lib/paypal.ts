/** Loading PayPal's own button script. We never see the supporter's card or login: PayPal's popup does that, and tells our server
 * only that an order was approved. The `client-id` decides sandbox or live, so a sandbox id can only ever reach the sandbox. */

export const PAYPAL_CLIENT_ID = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID ?? "";

export type PayPalButtonsOptions = {
  style?: Record<string, unknown>;
  createOrder: () => Promise<string>;
  onApprove: (data: { orderID: string }) => Promise<void>;
  onCancel?: () => void;
  onError?: (err: unknown) => void;
};

export type PayPalButtons = { render: (target: HTMLElement) => Promise<void>; close: () => Promise<void> };
export type PayPalNamespace = { Buttons: (options: PayPalButtonsOptions) => PayPalButtons };

let loading: Promise<PayPalNamespace> | null = null;

export function loadPayPal(clientId: string, currency: string): Promise<PayPalNamespace> {
  const w = window as unknown as { paypal?: PayPalNamespace };
  if (w.paypal) return Promise.resolve(w.paypal);
  if (loading) return loading;
  loading = new Promise<PayPalNamespace>((resolve, reject) => {
    const s = document.createElement("script");
    // intent=authorize: the supporter's money is only HELD; our server captures it later, and only if the goal is met.
    s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=${encodeURIComponent(currency)}&intent=authorize&components=buttons`;
    s.async = true;
    s.onload = () => (w.paypal ? resolve(w.paypal) : (loading = null, reject(new Error("PayPal's button did not load."))));
    s.onerror = () => { loading = null; reject(new Error("PayPal's button could not be loaded. Check your connection and try again.")); };
    document.head.appendChild(s);
  });
  return loading;
}
