// Webhook signature verification for Node.js 18+ (no dependencies).
// IMPORTANT: pass the raw request body (Buffer) exactly as received, not re-serialised JSON.
//   Express: app.post('/hooks', express.raw({ type: '*/*' }), handler) -> req.body is a Buffer.
import { createHmac, timingSafeEqual } from 'node:crypto';

const DEFAULT_TOLERANCE_SECONDS = 300;

function safeEqual(a, b) {
  const left = Buffer.from(String(a));
  const right = Buffer.from(String(b));
  return left.length === right.length && timingSafeEqual(left, right);
}

function checkTimestamp(timestamp, toleranceSeconds, nowSeconds) {
  const now = nowSeconds ?? Math.floor(Date.now() / 1000);
  const ts = Number.parseInt(String(timestamp), 10);
  if (!Number.isFinite(ts)) throw new Error('invalid timestamp');
  if (toleranceSeconds >= 0 && Math.abs(now - ts) > toleranceSeconds) {
    throw new Error('timestamp outside tolerance');
  }
  return ts;
}

/** Standard Webhooks (webhook-id / webhook-timestamp / webhook-signature). Throws on failure. */
export function verifyStandardWebhook(secret, headers, rawBody, { toleranceSeconds = DEFAULT_TOLERANCE_SECONDS, nowSeconds } = {}) {
  const id = headers['webhook-id'];
  const timestamp = headers['webhook-timestamp'];
  const signatureHeader = headers['webhook-signature'];
  if (!id || !timestamp || !signatureHeader) throw new Error('missing webhook headers');
  const ts = checkTimestamp(timestamp, toleranceSeconds, nowSeconds);
  const key = Buffer.from(secret.startsWith('whsec_') ? secret.slice(6) : secret, 'base64');
  const signed = Buffer.concat([Buffer.from(`${id}.${ts}.`), Buffer.from(rawBody)]);
  const expected = createHmac('sha256', key).update(signed).digest('base64');
  const ok = signatureHeader.split(' ').some((candidate) => {
    const [version, value] = candidate.split(',', 2);
    return version === 'v1' && value !== undefined && safeEqual(value, expected);
  });
  if (!ok) throw new Error('no matching signature');
}

/** GitHub X-Hub-Signature-256. Throws on failure. */
export function verifyGitHubWebhook(secret, signatureHeader, rawBody) {
  const expected = 'sha256=' + createHmac('sha256', secret).update(Buffer.from(rawBody)).digest('hex');
  if (!signatureHeader || !safeEqual(signatureHeader, expected)) throw new Error('signature mismatch');
}

/** Stripe-Signature (t=...,v1=...). Throws on failure. */
export function verifyStripeWebhook(secret, signatureHeader, rawBody, { toleranceSeconds = DEFAULT_TOLERANCE_SECONDS, nowSeconds } = {}) {
  let timestamp;
  const signatures = [];
  for (const item of String(signatureHeader || '').split(',')) {
    const [key, value] = item.trim().split('=', 2);
    if (key === 't') timestamp = value;
    if (key === 'v1' && value) signatures.push(value);
  }
  if (!timestamp || signatures.length === 0) throw new Error('malformed Stripe-Signature');
  const ts = checkTimestamp(timestamp, toleranceSeconds, nowSeconds);
  const expected = createHmac('sha256', secret)
    .update(Buffer.concat([Buffer.from(`${ts}.`), Buffer.from(rawBody)]))
    .digest('hex');
  if (!signatures.some((s) => safeEqual(s, expected))) throw new Error('no matching signature');
}
