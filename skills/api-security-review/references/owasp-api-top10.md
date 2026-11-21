# OWASP API Security Top 10 (2023) mapped to checks

For each category: what to look for, scanner rules that point at it, `rg` patterns to
find candidate code, and the fix. Patterns are starting points; read the surrounding code.

## API1 Broken Object Level Authorization (BOLA / IDOR)

Every request that uses a client-supplied ID must check that the caller may access that
object.

- Scanner: `object-access-review`, `sequential-id`.
- Code patterns:
  ```bash
  rg -n "findById|findByPk|get_object_or_404|\.find\(\s*(req|request)\.(params|query)|::find\(\$request|where\(['\"]id['\"]" src app
  rg -n "params\.(id|\w+Id)|path_params|\{id\}" src app
  ```
- Bad: `Order.findByPk(req.params.id)`. Good: `Order.findOne({ where: { id, customerId: req.user.customerId } })`
  or a policy check (`authorize('view', order)`) on every route, including nested ones,
  exports, and bulk endpoints that accept lists of IDs.
- Test: user A requesting user B's object gets 404 (or 403); repeat for GET, PATCH, DELETE.

## API2 Broken Authentication

- Scanner: `no-security-schemes`, `unauthenticated-operation`, `api-key-in-query`,
  `basic-auth`, `oauth-implicit`, `oauth-password`.
- Check: JWT signature and `alg` pinned (no `none`, no HS/RS confusion), `exp`/`aud`/`iss`
  validated; tokens revocable; login, OTP and password reset rate-limited and locked out;
  reset tokens single-use and short-lived; credentials never in URLs or logs.
  ```bash
  rg -n "jwt\.decode|verify\s*=\s*False|algorithms\s*=|ignoreExpiration|alg.*none" src app
  rg -n "api_key=|apikey=|token=" src app docs
  ```

## API3 Broken Object Property Level Authorization

Mass assignment (client sets `role`, `is_admin`, `price`) and excessive data exposure
(responses include fields the caller should not see).

- Scanner: `open-request-schema`, `sensitive-response-field`.
- Code patterns:
  ```bash
  rg -n "\*\*request\.(json|data)|Object\.assign\([^,]+,\s*req\.body|\.update\(req\.body|fill\(\$request->all\(\)\)|create\(\$request->all\(\)\)|\$guarded\s*=\s*\[\]" src app
  rg -n "res\.json\((user|account|\w+)\)|toJSON|model_dump\(\)|->toArray\(\)" src app
  ```
- Fix: explicit input DTO/allowlist per endpoint and role; explicit response serializers;
  `additionalProperties: false` in request schemas; `writeOnly` for secrets.

## API4 Unrestricted Resource Consumption

- Scanner: `unbounded-page-size`, `unbounded-array`, `unbounded-string-*`,
  `no-rate-limit-response`.
- Check: maximum page size, body size limit, upload size/type limits, query timeouts,
  per-client rate limits, limits on expensive operations (exports, SMS/email sends, AI
  calls), GraphQL-like batch/depth limits.
  ```bash
  rg -n "limit\s*=\s*(req|request)|per_page|page_size|bodyParser|express\.json\(|client_max_body_size|upload_max_filesize" src app config
  ```

## API5 Broken Function Level Authorization

- Scanner: `privileged-path`, `write-without-scope`.
- Check: admin and internal routes require a role/scope check in code, not only a hidden
  URL; write methods check stronger permissions than reads; every route has a deny-by-default
  middleware.
  ```bash
  rg -n "/admin|/internal|isAdmin|is_staff|role\s*===?|hasRole|@PreAuthorize|can\(" src app
  ```

## API6 Unrestricted Access to Sensitive Business Flows

Not visible in a spec. Identify flows where automation hurts the business: purchases of
limited stock, sign-up bonuses, referrals, comment/review posting, ticket booking, OTP/SMS
sending. Check for per-account and per-device limits, bot detection or proof of work,
and anomaly alerts.

## API7 Server Side Request Forgery

- Scanner: `url-input`.
- Code patterns:
  ```bash
  rg -n "requests\.(get|post)\(|httpx\.|fetch\(|axios\.|curl_init|file_get_contents\(\s*\$|Http::get\(|urlopen\(" src app
  ```
- Fix: allowlist schemes and hosts; resolve DNS and block private, loopback, link-local
  (169.254.169.254 metadata) and IPv6 equivalents at connect time; disable redirects or
  re-check each hop; set short timeouts and size limits; never return raw upstream bodies.

## API8 Security Misconfiguration

- Scanner: `plain-http-server`, `auth-responses`.
- Check: HTTPS only + HSTS; CORS not `*` with credentials; verbose errors and stack traces
  disabled (see `error-responses`); unused methods return 405; security headers
  (`Cache-Control: no-store` on personal data, `X-Content-Type-Options: nosniff`); default
  credentials removed; debug endpoints disabled.
  ```bash
  rg -n "Access-Control-Allow-Origin|cors\(|origin:\s*['\"]\*|DEBUG\s*=\s*True|APP_DEBUG=true|stack" src app config .env.example
  ```

## API9 Improper Inventory Management

- Scanner: `mixed-environments`, `no-version`, `deprecated-without-sunset`.
- Check: every deployed host and version is documented; old versions (`/v1` after `/v2`)
  get the same security patches or are retired; staging does not use production data;
  no undocumented "shadow" endpoints (compare router output with the spec).
  ```bash
  # Express: list registered routes, then diff against the spec paths
  rg -n "app\.(get|post|put|patch|delete)\(|router\.(get|post|put|patch|delete)\(|Route::(get|post|put|patch|delete)\(|@(Get|Post|Put|Patch|Delete)Mapping|@app\.(get|post|put|patch|delete)" src app routes
  ```

## API10 Unsafe Consumption of APIs

Not visible in a spec. Data from third-party APIs is untrusted input: validate schemas,
enforce TLS, time out, cap response sizes, do not follow redirects blindly, and do not
pass third-party data into SQL, shell or HTML without the same validation as user input.

  ```bash
  rg -n "json\(\)\[|\.json\(\)\.|response\.data\.|json_decode\(" src app
  ```

## Severity guide

| Severity | Example |
| --- | --- |
| Critical | BOLA on financial or personal data; auth bypass; SSRF to cloud metadata |
| High | Mass assignment of roles; admin endpoint reachable by normal users; no login rate limit |
| Medium | Excessive data exposure of non-secret internal fields; missing page size cap |
| Low | Missing 401/403 docs; HTTP Basic on an internal API over TLS |
