"""Ground truth: observe what the real LST does at the LLM REST boundary.

Runs the real CLI (`lst scan`) end to end on the calibrated fixture with the
remote chat-completions server replaced by respx. Prints, per situation, the
exit code, stderr/report markers, number of HTTP calls and wall time. Nothing
is asserted: this is the oracle against which generated test cases are judged.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from lst.cli import app

REPO = Path(sys.argv[1])
FIXTURE = REPO / "tests" / "fixtures" / "auth_sample.log"
ENDPOINT = "https://llm.test/v1/chat/completions"
GOOD = {"explanation": "Força bruta SSH.", "severity": "high", "next_action": "Bloquear IPs."}


def completion(content: object, *, choices: list | None = None) -> httpx.Response:
    body = {
        "id": "chatcmpl-x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": choices
        if choices is not None
        else [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    return httpx.Response(200, json=body)


def err(status: int, message: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message}}, headers=headers or {})


def run(label: str, side_effect, env_extra: dict[str, str] | None = None, capture=None) -> None:
    env = {
        "LLM_API_KEY": "fake-key-123",
        "LLM_MODEL": "fake-model",
        "LLM_BASE_URL": "https://llm.test/v1",
        "LLM_MAX_RETRIES": "2",
    }
    env.update(env_extra or {})
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            with respx.mock(assert_all_called=False) as router:
                route = router.post(ENDPOINT).mock(side_effect=side_effect)
                started = time.monotonic()
                result = CliRunner().invoke(app, ["scan", str(FIXTURE)])
                elapsed = time.monotonic() - started
                calls = route.call_count
                if capture:
                    capture(route)
        finally:
            os.chdir(cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    out = result.stdout
    err_text = " | ".join(
        line for line in result.stderr.splitlines() if line.startswith(("Erro", "Timeout"))
    )[:150]
    footer = "## Eventos não explicados" in out
    print(
        f"{label:<46} exit={result.exit_code} calls={calls:<2} t={elapsed:4.1f}s "
        f"report={'sim' if out.strip() else 'não'} footer={footer} "
        f"stderr={err_text!r}"
    )


def seq(*responses):
    items = list(responses)

    def side_effect(request):
        return items.pop(0) if len(items) > 1 else items[0]

    return side_effect


ok = completion(json.dumps(GOOD))
run("G1 200 válido em todas", lambda r: ok)


def show_timeout(route):
    t = route.calls[0].request.extensions.get("timeout")
    print(f"   timeout enviado ao httpx (LLM_TIMEOUT_SECONDS=5): {t}")


run("G2 LLM_TIMEOUT_SECONDS=5 é usado?", lambda r: ok, {"LLM_TIMEOUT_SECONDS": "5"}, show_timeout)
run("G3 429 sempre (max_retries=2)", lambda r: err(429, "rate limited"))
run("G3b 429 sempre, retry-after-ms: 1", lambda r: err(429, "rate", {"retry-after-ms": "1"}))
run("G4 500 sempre", lambda r: err(500, "boom", {"retry-after-ms": "1"}))
run("G5 401", lambda r: err(401, "invalid api key"))
run("G6 404 (modelo/URL)", lambda r: err(404, "model not found"))
calls_g7: list[str] = []


def g7(request):
    fmt = json.loads(request.content).get("response_format", {}).get("type", "none")
    calls_g7.append(fmt)
    if fmt == "json_schema":
        return err(400, "response_format json_schema is not supported")
    return ok


run("G7 400 rejeita json_schema (auto)", g7)
print(f"   sequência de response_format: {calls_g7}")
run("G8 400 não relacionado", lambda r: err(400, "max_tokens too large"))
run("G9 200 com choices vazio", lambda r: completion(None, choices=[]))
run("G10 200 com content null", lambda r: completion(None))
run("G11 200 com texto não-JSON", lambda r: completion("não sei responder"))
run(
    "G12 200 severidade fora do enum",
    lambda r: completion(json.dumps({**GOOD, "severity": "urgent"})),
)
run(
    "G13 200 JSON em cerca markdown", lambda r: completion("```json\n" + json.dumps(GOOD) + "\n```")
)
run(
    "G14 200 com HTML (URL errada)",
    lambda r: httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"}),
)
run("G15 erro de conexão", httpx.ConnectError("refused"))
run("G16 timeout de leitura", httpx.ReadTimeout("slow"))
run("G17 503 depois 200 (transiente)", seq(err(503, "busy", {"retry-after-ms": "1"}), ok))
run("G18 LLM_PARSE_RETRIES=0 + não-JSON", lambda r: completion("lixo"), {"LLM_PARSE_RETRIES": "0"})
run("G19 LLM_MAX_RETRIES=0 + 500", lambda r: err(500, "boom"), {"LLM_MAX_RETRIES": "0"})

mixed = [
    completion(json.dumps(GOOD)),
    completion("lixo"),
    completion("lixo"),
    completion(json.dumps(GOOD)),
]
run("G20 evento 2 inválido 2x, demais ok", lambda r: mixed.pop(0))


def show_request(route):
    req = route.calls[0].request
    body = json.loads(req.content)
    user = body["messages"][1]["content"]
    print(f"   Authorization: {req.headers.get('authorization')!r}")
    print(
        f"   chaves do corpo: {sorted(body)} | mensagens: {[m['role'] for m in body['messages']]}"
    )
    print(
        f"   response_format.type={body.get('response_format', {}).get('type')} "
        f"max_tokens={body.get('max_tokens')}"
    )
    print(
        f"   chave no corpo? {'fake-key-123' in req.content.decode()} | "
        f"linhas originais no prompt do usuário: {user.count('Failed') + user.count('Invalid')}"
    )


run("G21 contrato da requisição", lambda r: ok, capture=show_request)
