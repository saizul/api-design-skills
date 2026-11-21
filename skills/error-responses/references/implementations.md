# Problem details handlers

Each snippet: one error class for expected problems, one central handler, a generic 500
for everything else (logged with a correlation ID, never returned to the client).

## Node.js / Express

```js
// problems.js
import { randomUUID } from 'node:crypto';

export class Problem extends Error {
  constructor({ type = 'about:blank', title, status, detail, ...extensions }) {
    super(detail || title);
    Object.assign(this, { type, title, status, detail, extensions });
  }
}

export const validationProblem = (errors) =>
  new Problem({
    type: 'https://api.example.com/problems/validation-error',
    title: 'Your request is not valid.',
    status: 422,
    detail: `${errors.length} field(s) are invalid.`,
    errors, // [{ detail, pointer }]
  });

function send(res, body) {
  res.status(body.status).type('application/problem+json').json(body);
}

// Register after all routes: app.use(notFound); app.use(problemHandler);
export function notFound(req, res) {
  send(res, { type: 'about:blank', title: 'Not Found', status: 404 });
}

export function problemHandler(err, req, res, _next) {
  const instance = `urn:uuid:${randomUUID()}`;
  if (err instanceof Problem) {
    const { type, title, status, detail, extensions } = err;
    return send(res, { type, title, status, ...(detail && { detail }), instance, ...extensions });
  }
  if (err.type === 'entity.parse.failed') {
    return send(res, { type: 'about:blank', title: 'Bad Request', status: 400, detail: 'Body is not valid JSON.', instance });
  }
  req.log?.error({ err, instance }) ?? console.error(instance, err);
  send(res, { type: 'about:blank', title: 'Internal Server Error', status: 500, instance });
}
```

Usage: `throw new Problem({ type: 'https://api.example.com/problems/insufficient-funds', title: 'Insufficient funds.', status: 422, detail, balance, currency })`.
Express 5 forwards rejected promises from async handlers to the error handler; on Express 4
wrap async handlers or call `next(err)`.

## Python / FastAPI

```python
# problems.py
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from http import HTTPStatus

log = logging.getLogger(__name__)
MEDIA_TYPE = "application/problem+json"


class Problem(Exception):
    def __init__(self, status: int, title: str, type: str = "about:blank", detail: str | None = None, **ext):
        self.body = {"type": type, "title": title, "status": status, **({"detail": detail} if detail else {}), **ext}


def problem_response(body: dict) -> JSONResponse:
    body.setdefault("instance", f"urn:uuid:{uuid.uuid4()}")
    return JSONResponse(body, status_code=body["status"], media_type=MEDIA_TYPE)


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem):
        return problem_response(dict(exc.body))

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        body = {"type": "about:blank", "title": HTTPStatus(exc.status_code).phrase, "status": exc.status_code}
        if isinstance(exc.detail, str) and exc.status_code < 500:
            body["detail"] = exc.detail
        return problem_response(body)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            loc = list(err.get("loc", []))
            where = loc[0] if loc else "body"
            if where == "body":
                errors.append({"detail": err["msg"], "pointer": "#/" + "/".join(str(p) for p in loc[1:])})
            else:
                errors.append({"detail": err["msg"], "parameter": str(loc[-1])})
        return problem_response(
            {
                "type": "https://api.example.com/problems/validation-error",
                "title": "Your request is not valid.",
                "status": 422,
                "errors": errors,
            }
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        instance = f"urn:uuid:{uuid.uuid4()}"
        log.exception("unhandled error %s", instance)
        return problem_response(
            {"type": "about:blank", "title": "Internal Server Error", "status": 500, "instance": instance}
        )
```

Note: the catch-all `Exception` handler runs in Starlette's `ServerErrorMiddleware`, which
still re-raises for logging; that is expected. Register Starlette's `HTTPException` too if
you raise it directly.

## Python / Flask

```python
import uuid
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


def problem(status, title, type="about:blank", **extra):
    body = {"type": type, "title": title, "status": status, "instance": f"urn:uuid:{uuid.uuid4()}", **extra}
    resp = jsonify(body)
    resp.status_code = status
    resp.mimetype = "application/problem+json"
    return resp


def install(app: Flask):
    @app.errorhandler(HTTPException)
    def _http(exc):
        extra = {"detail": exc.description} if exc.code < 500 else {}
        return problem(exc.code, exc.name, **extra)

    @app.errorhandler(Exception)
    def _unexpected(exc):
        app.logger.exception("unhandled error")
        return problem(500, "Internal Server Error")
```

## PHP / Laravel (11+)

```php
// bootstrap/app.php
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Validation\ValidationException;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;
use Symfony\Component\HttpFoundation\Response;
use Illuminate\Support\Str;

->withExceptions(function (Exceptions $exceptions) {
    $problem = fn (array $body) => response()->json(
        $body + ['instance' => 'urn:uuid:' . Str::uuid()],
        $body['status'],
        ['Content-Type' => 'application/problem+json'],
    );

    $exceptions->render(function (ValidationException $e, $request) use ($problem) {
        if (! $request->expectsJson()) return null;
        $errors = [];
        foreach ($e->errors() as $field => $messages) {
            foreach ($messages as $message) {
                $errors[] = ['detail' => $message, 'pointer' => '#/' . str_replace('.', '/', $field)];
            }
        }
        return $problem([
            'type' => 'https://api.example.com/problems/validation-error',
            'title' => 'Your request is not valid.',
            'status' => 422,
            'errors' => $errors,
        ]);
    });

    $exceptions->render(function (Throwable $e, $request) use ($problem) {
        if (! $request->expectsJson()) return null;
        $status = $e instanceof HttpExceptionInterface ? $e->getStatusCode() : 500;
        $body = ['type' => 'about:blank', 'title' => Response::$statusTexts[$status] ?? 'Error', 'status' => $status];
        if ($status < 500 && $e->getMessage() !== '') $body['detail'] = $e->getMessage();
        return $problem($body);   // Laravel still reports (logs) the exception
    });
})
```

## Plain PHP

```php
function send_problem(int $status, string $title, string $type = 'about:blank', array $extra = []): never
{
    http_response_code($status);
    header('Content-Type: application/problem+json');
    echo json_encode(['type' => $type, 'title' => $title, 'status' => $status]
        + $extra + ['instance' => 'urn:uuid:' . bin2hex(random_bytes(16))], JSON_UNESCAPED_SLASHES);
    exit;
}

set_exception_handler(function (Throwable $e) {
    error_log((string) $e);
    send_problem(500, 'Internal Server Error');
});
```

## Tests to write (any stack)

- Each problem type returns the right status, `Content-Type: application/problem+json`
  and `type`.
- A malformed JSON body returns 400, not 500.
- A thrown unexpected exception returns a 500 body with only `type`, `title`, `status`,
  `instance` (assert no `stack`, `trace`, `exception`, file paths).
- Validation errors carry one item per invalid field with a correct JSON Pointer.
