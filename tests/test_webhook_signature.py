import json
import os
import shutil
import subprocess

import pytest

from conftest import SKILLS, load_module, run_script

SCRIPT = "webhook-design/scripts/webhook_signature.py"
wh = load_module(SCRIPT)

# Published test vectors.
# Standard Webhooks reference libraries (standard-webhooks/standard-webhooks, test suites).
STD_SECRET = "whsec_" + "MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
STD_ID = "msg_p5jXN8AQM9LWM0D4loKWxJek"
STD_TS = 1614265330
STD_BODY = b'{"test": 2432232314}'
STD_SIG = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="
# GitHub docs, "Validating webhook deliveries".
GH_SECRET = "It's a Secret to Everybody"
GH_BODY = b"Hello, World!"
GH_SIG = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"


def test_standard_vector():
    assert wh.sign_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY) == STD_SIG
    wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY, STD_SIG, now=STD_TS + 10)


def test_standard_multiple_signatures_and_rotation():
    header = "v1,bm90LXRoaXM= " + STD_SIG
    wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY, header, now=STD_TS)


def test_standard_rejects_tampering_and_old_timestamps():
    with pytest.raises(wh.VerificationError):
        wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY + b" ", STD_SIG, now=STD_TS)
    with pytest.raises(wh.VerificationError):
        wh.verify_standard(STD_SECRET, "msg_other", STD_TS, STD_BODY, STD_SIG, now=STD_TS)
    with pytest.raises(wh.VerificationError, match="tolerance"):
        wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY, STD_SIG, now=STD_TS + 301)
    wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY, STD_SIG, tolerance=-1, now=STD_TS + 10**6)
    with pytest.raises(wh.VerificationError):
        wh.verify_standard(STD_SECRET, STD_ID, STD_TS, STD_BODY, "v2," + STD_SIG[3:], now=STD_TS)


def test_standard_bad_secret():
    with pytest.raises(ValueError):
        wh.sign_standard("whsec_not base64!", STD_ID, STD_TS, STD_BODY)


def test_github_vector():
    assert wh.sign_github(GH_SECRET, GH_BODY) == GH_SIG
    wh.verify_github(GH_SECRET, GH_BODY, GH_SIG)
    with pytest.raises(wh.VerificationError):
        wh.verify_github(GH_SECRET, GH_BODY, GH_SIG.upper())
    with pytest.raises(wh.VerificationError):
        wh.verify_github("wrong", GH_BODY, GH_SIG)


def test_stripe_roundtrip():
    header = wh.sign_stripe("test-stripe-secret", 1700000000, b'{"id":"evt_1"}')
    assert header.startswith("t=1700000000,v1=")
    wh.verify_stripe("test-stripe-secret", b'{"id":"evt_1"}', header, now=1700000100)
    wh.verify_stripe("test-stripe-secret", b'{"id":"evt_1"}', header + ",v1=deadbeef,v0=x", now=1700000100)
    with pytest.raises(wh.VerificationError):
        wh.verify_stripe("test-stripe-secret", b'{"id":"evt_2"}', header, now=1700000100)
    with pytest.raises(wh.VerificationError, match="t= and"):
        wh.verify_stripe("test-stripe-secret", b"{}", "v1=abc", now=1700000100)
    with pytest.raises(wh.VerificationError, match="tolerance"):
        wh.verify_stripe("test-stripe-secret", b'{"id":"evt_1"}', header, now=1700001000)


def test_plain_hmac():
    sig = wh.sign_hmac("k", b"body")
    wh.verify_hmac("k", b"body", sig)
    wh.verify_hmac("k", b"body", "sha256=" + sig.upper())
    ts_sig = wh.sign_hmac("k", b"body", 100)
    wh.verify_hmac("k", b"body", ts_sig, timestamp=100, now=150)
    with pytest.raises(wh.VerificationError):
        wh.verify_hmac("k", b"body", sig, timestamp=100, now=150)


def env_with(secret):
    env = dict(os.environ)
    env["WEBHOOK_SECRET"] = secret
    return env


def test_cli_sign_and_verify(tmp_path):
    body = tmp_path / "body.json"
    body.write_bytes(STD_BODY)
    signed = run_script(
        SCRIPT,
        "sign",
        "--scheme",
        "standard",
        "--id",
        STD_ID,
        "--timestamp",
        str(STD_TS),
        "--body-file",
        str(body),
        "--format",
        "json",
        env=env_with(STD_SECRET),
    )
    assert signed.returncode == 0, signed.stderr
    headers = json.loads(signed.stdout)["headers"]
    assert headers["webhook-signature"] == STD_SIG
    assert STD_SECRET.encode() not in signed.stdout + signed.stderr

    ok = run_script(
        SCRIPT,
        "verify",
        "--scheme",
        "standard",
        "--id",
        STD_ID,
        "--timestamp",
        str(STD_TS),
        "--signature",
        STD_SIG,
        "--body-file",
        str(body),
        "--tolerance",
        "-1",
        env=env_with(STD_SECRET),
    )
    assert ok.returncode == 0 and ok.stdout.strip() == b"VALID"

    bad = run_script(
        SCRIPT,
        "verify",
        "--scheme",
        "github",
        "--signature",
        GH_SIG,
        "--format",
        "json",
        env=env_with(GH_SECRET),
        stdin=b"Hello, World?",
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["valid"] is False

    good = run_script(
        SCRIPT, "verify", "--scheme", "github", "--signature", GH_SIG, env=env_with(GH_SECRET), stdin=GH_BODY
    )
    assert good.returncode == 0


def test_cli_secret_file_and_missing_secret(tmp_path):
    secret = tmp_path / "secret"
    secret.write_text(GH_SECRET + "\n")
    out = run_script(SCRIPT, "sign", "--scheme", "github", "--secret-file", str(secret), stdin=GH_BODY)
    assert out.stdout.decode().strip() == "X-Hub-Signature-256: " + GH_SIG
    env = dict(os.environ)
    env.pop("WEBHOOK_SECRET", None)
    missing = run_script(SCRIPT, "sign", "--scheme", "github", env=env, stdin=b"x")
    assert missing.returncode != 0
    assert run_script(SCRIPT, "--help").returncode == 0


SNIPPETS = SKILLS / "webhook-design" / "assets" / "snippets"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_node_snippet(tmp_path):
    runner = tmp_path / "run.mjs"
    runner.write_text(f"""
import {{ verifyStandardWebhook, verifyGitHubWebhook, verifyStripeWebhook }} from {json.dumps(str(SNIPPETS / "verify-webhook.mjs"))};
const results = {{}};
const expectThrow = (fn) => {{ try {{ fn(); return false; }} catch {{ return true; }} }};
const headers = {{ 'webhook-id': {json.dumps(STD_ID)}, 'webhook-timestamp': '{STD_TS}', 'webhook-signature': {json.dumps(STD_SIG)} }};
verifyStandardWebhook({json.dumps(STD_SECRET)}, headers, Buffer.from({json.dumps(STD_BODY.decode())}), {{ nowSeconds: {STD_TS} }});
results.standardTampered = expectThrow(() => verifyStandardWebhook({json.dumps(STD_SECRET)}, headers, Buffer.from('x'), {{ nowSeconds: {STD_TS} }}));
results.standardExpired = expectThrow(() => verifyStandardWebhook({json.dumps(STD_SECRET)}, headers, Buffer.from({json.dumps(STD_BODY.decode())}), {{ nowSeconds: {STD_TS + 301} }}));
verifyGitHubWebhook({json.dumps(GH_SECRET)}, {json.dumps(GH_SIG)}, Buffer.from('Hello, World!'));
results.githubTampered = expectThrow(() => verifyGitHubWebhook({json.dumps(GH_SECRET)}, {json.dumps(GH_SIG)}, Buffer.from('Hello')));
const stripeHeader = {json.dumps(wh.sign_stripe("test-stripe-secret", 1700000000, b'{"id":"evt_1"}'))};
verifyStripeWebhook('test-stripe-secret', stripeHeader, Buffer.from('{{"id":"evt_1"}}'), {{ nowSeconds: 1700000000 }});
results.stripeTampered = expectThrow(() => verifyStripeWebhook('test-stripe-secret', stripeHeader, Buffer.from('{{}}'), {{ nowSeconds: 1700000000 }}));
console.log(JSON.stringify(results));
""")
    out = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {
        "standardTampered": True,
        "standardExpired": True,
        "githubTampered": True,
        "stripeTampered": True,
    }


@pytest.mark.skipif(shutil.which("php") is None, reason="php not installed")
def test_php_snippet(tmp_path):
    stripe_header = wh.sign_stripe("test-stripe-secret", 1700000000, b'{"id":"evt_1"}')
    runner = tmp_path / "run.php"
    runner.write_text(f"""<?php
require {json.dumps(str(SNIPPETS / "verify-webhook.php"))};
function throws(callable $fn): bool {{ try {{ $fn(); return false; }} catch (Throwable $e) {{ return true; }} }}
$h = ['webhook-id' => {json.dumps(STD_ID)}, 'webhook-timestamp' => '{STD_TS}', 'webhook-signature' => {json.dumps(STD_SIG)}];
$body = {json.dumps(STD_BODY.decode())};
verify_standard_webhook({json.dumps(STD_SECRET)}, $h, $body, 300, {STD_TS});
$r = [];
$r['standardTampered'] = throws(fn() => verify_standard_webhook({json.dumps(STD_SECRET)}, $h, 'x', 300, {STD_TS}));
$r['standardExpired'] = throws(fn() => verify_standard_webhook({json.dumps(STD_SECRET)}, $h, $body, 300, {STD_TS + 301}));
verify_github_webhook({json.dumps(GH_SECRET)}, {json.dumps(GH_SIG)}, 'Hello, World!');
$r['githubTampered'] = throws(fn() => verify_github_webhook({json.dumps(GH_SECRET)}, {json.dumps(GH_SIG)}, 'Hello'));
verify_stripe_webhook('test-stripe-secret', {json.dumps(stripe_header)}, '{{"id":"evt_1"}}', 300, 1700000000);
$r['stripeTampered'] = throws(fn() => verify_stripe_webhook('test-stripe-secret', {json.dumps(stripe_header)}, '{{}}', 300, 1700000000));
echo json_encode($r);
""")
    out = subprocess.run(["php", str(runner)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    assert json.loads(out.stdout) == {
        "standardTampered": True,
        "standardExpired": True,
        "githubTampered": True,
        "stripeTampered": True,
    }
