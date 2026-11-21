<?php
// Webhook signature verification for PHP 8.0+ (no dependencies).
// IMPORTANT: verify the raw body: $raw = file_get_contents('php://input');
declare(strict_types=1);

const WEBHOOK_TOLERANCE_SECONDS = 300;

function webhook_check_timestamp(string $timestamp, int $tolerance, ?int $now = null): int
{
    if (!ctype_digit($timestamp)) {
        throw new InvalidArgumentException('invalid timestamp');
    }
    $ts = (int) $timestamp;
    $now ??= time();
    if ($tolerance >= 0 && abs($now - $ts) > $tolerance) {
        throw new RuntimeException('timestamp outside tolerance');
    }
    return $ts;
}

/** Standard Webhooks. $headers keys must be lowercase. Throws on failure. */
function verify_standard_webhook(string $secret, array $headers, string $rawBody, int $tolerance = WEBHOOK_TOLERANCE_SECONDS, ?int $now = null): void
{
    $id = $headers['webhook-id'] ?? '';
    $timestamp = $headers['webhook-timestamp'] ?? '';
    $signatureHeader = $headers['webhook-signature'] ?? '';
    if ($id === '' || $timestamp === '' || $signatureHeader === '') {
        throw new RuntimeException('missing webhook headers');
    }
    $ts = webhook_check_timestamp($timestamp, $tolerance, $now);
    $key = base64_decode(str_starts_with($secret, 'whsec_') ? substr($secret, 6) : $secret, true);
    if ($key === false) {
        throw new InvalidArgumentException('secret is not base64');
    }
    $expected = base64_encode(hash_hmac('sha256', "{$id}.{$ts}.{$rawBody}", $key, true));
    foreach (explode(' ', $signatureHeader) as $candidate) {
        [$version, $value] = array_pad(explode(',', $candidate, 2), 2, '');
        if ($version === 'v1' && hash_equals($expected, $value)) {
            return;
        }
    }
    throw new RuntimeException('no matching signature');
}

/** GitHub X-Hub-Signature-256. Throws on failure. */
function verify_github_webhook(string $secret, string $signatureHeader, string $rawBody): void
{
    $expected = 'sha256=' . hash_hmac('sha256', $rawBody, $secret);
    if (!hash_equals($expected, $signatureHeader)) {
        throw new RuntimeException('signature mismatch');
    }
}

/** Stripe-Signature (t=...,v1=...). Throws on failure. */
function verify_stripe_webhook(string $secret, string $signatureHeader, string $rawBody, int $tolerance = WEBHOOK_TOLERANCE_SECONDS, ?int $now = null): void
{
    $timestamp = '';
    $signatures = [];
    foreach (explode(',', $signatureHeader) as $item) {
        [$key, $value] = array_pad(explode('=', trim($item), 2), 2, '');
        if ($key === 't') {
            $timestamp = $value;
        } elseif ($key === 'v1' && $value !== '') {
            $signatures[] = $value;
        }
    }
    if ($timestamp === '' || $signatures === []) {
        throw new RuntimeException('malformed Stripe-Signature');
    }
    $ts = webhook_check_timestamp($timestamp, $tolerance, $now);
    $expected = hash_hmac('sha256', "{$ts}.{$rawBody}", $secret);
    foreach ($signatures as $signature) {
        if (hash_equals($expected, $signature)) {
            return;
        }
    }
    throw new RuntimeException('no matching signature');
}
