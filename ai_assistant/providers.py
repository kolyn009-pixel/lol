from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(os.getenv("TUTORBOT_AI_PROVIDERS_FILE", "/etc/tutorbot_ai_providers.json"))

TEMPLATES = {
    "openrouter": {"title": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model": "openrouter/free", "kind": "openai"},
    "gemini": {"title": "Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-2.5-flash", "kind": "gemini"},
    "deepseek": {"title": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-chat", "kind": "openai"},
    "custom": {"title": "Другой OpenAI-совместимый", "base_url": "", "model": "", "kind": "openai"},
}

def _empty():
    return {"active": "openrouter_env", "order": ["openrouter_env"], "providers": {}}

def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return _empty()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("active", "openrouter_env")
        data.setdefault("order", ["openrouter_env"])
        data.setdefault("providers", {})
        return data
    except Exception:
        return _empty()

def save_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(CONFIG_PATH)
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)

def mask_key(key: str) -> str:
    key = (key or "").strip()
    if len(key) < 10:
        return "••••••"
    return key[:5] + "••••••" + key[-4:]

def env_openrouter() -> dict[str, Any] | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or "ВСТАВЬ" in key.upper():
        return None
    return {
        "id": "openrouter_env", "title": "OpenRouter (сервер)", "type": "openrouter", "kind": "openai",
        "api_key": key, "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        "model": os.getenv("AI_MODEL", "openrouter/free") or "openrouter/free", "enabled": True,
    }

def provider_list(include_secrets: bool = False) -> list[dict[str, Any]]:
    cfg = load_config()
    result = []
    env = env_openrouter()
    if env:
        result.append(dict(env) if include_secrets else {**env, "api_key": mask_key(env["api_key"])})
    for pid, p in cfg.get("providers", {}).items():
        row = {"id": pid, **p}
        if not include_secrets:
            row["api_key"] = mask_key(str(row.get("api_key") or ""))
        result.append(row)
    pos = {x: i for i, x in enumerate(cfg.get("order") or [])}
    return sorted(result, key=lambda x: pos.get(x["id"], 999))

def get_provider(pid: str) -> dict[str, Any] | None:
    if pid == "openrouter_env":
        return env_openrouter()
    p = load_config().get("providers", {}).get(pid)
    return ({"id": pid, **p} if p else None)

def save_provider(provider_type: str, api_key: str, *, model: str = "", base_url: str = "", title: str = "") -> str:
    if provider_type not in TEMPLATES:
        raise ValueError("unknown provider type")
    t = TEMPLATES[provider_type]
    cfg = load_config()
    pid = provider_type
    n = 1
    while pid in cfg["providers"]:
        n += 1
        pid = f"{provider_type}_{n}"
    cfg["providers"][pid] = {
        "title": title.strip() or t["title"], "type": provider_type, "kind": t["kind"], "api_key": api_key.strip(),
        "base_url": (base_url.strip() or t["base_url"]).rstrip("/"), "model": model.strip() or t["model"], "enabled": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    if pid not in cfg["order"]:
        cfg["order"].append(pid)
    save_config(cfg)
    return pid

def set_active(pid: str) -> None:
    if not get_provider(pid):
        raise ValueError("provider not found")
    cfg = load_config()
    cfg["active"] = pid
    cfg["order"] = [pid] + [x for x in cfg.get("order", []) if x != pid]
    if env_openrouter() and "openrouter_env" not in cfg["order"]:
        cfg["order"].append("openrouter_env")
    save_config(cfg)

def toggle_provider(pid: str) -> bool:
    cfg = load_config()
    p = cfg.get("providers", {}).get(pid)
    if not p:
        raise ValueError("provider not found")
    p["enabled"] = not bool(p.get("enabled", True))
    save_config(cfg)
    return bool(p["enabled"])

def delete_provider(pid: str) -> None:
    if pid == "openrouter_env":
        raise ValueError("server provider cannot be deleted here")
    cfg = load_config()
    cfg.get("providers", {}).pop(pid, None)
    cfg["order"] = [x for x in cfg.get("order", []) if x != pid]
    if cfg.get("active") == pid:
        cfg["active"] = "openrouter_env"
    save_config(cfg)

def update_model(pid: str, model: str) -> None:
    if pid == "openrouter_env":
        raise ValueError("server OpenRouter model is managed by /etc/tutorbot.env")
    cfg = load_config()
    p = cfg.get("providers", {}).get(pid)
    if not p:
        raise ValueError("provider not found")
    p["model"] = model.strip()
    save_config(cfg)

def ordered_providers() -> list[dict[str, Any]]:
    cfg = load_config()
    ids = list(cfg.get("order") or [])
    if cfg.get("active") and cfg["active"] not in ids:
        ids.insert(0, cfg["active"])
    if env_openrouter() and "openrouter_env" not in ids:
        ids.append("openrouter_env")
    result = []
    for pid in ids:
        p = get_provider(pid)
        if p and p.get("enabled", True):
            result.append(p)
    for p in provider_list(include_secrets=True):
        if p.get("enabled", True) and not any(x["id"] == p["id"] for x in result):
            result.append(p)
    return result

def active_provider() -> dict[str, Any] | None:
    cfg = load_config()
    p = get_provider(str(cfg.get("active") or "openrouter_env"))
    if p and p.get("enabled", True):
        return p
    rows = ordered_providers()
    return rows[0] if rows else None

def _openai_request(p, messages, temperature, max_tokens, timeout):
    payload = {"model": p["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if p.get("type") == "openrouter":
        payload["reasoning"] = {"exclude": True}
    req = urllib.request.Request(
        p["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {p['api_key']}", "Content-Type": "application/json", "HTTP-Referer": "https://localhost", "X-Title": "Adelia TutorBot"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
    choices = obj.get("choices") or []
    if not choices:
        raise RuntimeError("provider returned no choices")
    return str((choices[0].get("message") or {}).get("content") or "").strip()

def _gemini_request(p, messages, temperature, max_tokens, timeout):
    system = []
    contents = []
    for m in messages:
        if m.get("role") == "system":
            system.append(m.get("content") or "")
        else:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content") or ""}]})
    payload = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
    url = f"{p['base_url'].rstrip('/')}/models/{p['model']}:generateContent?key={p['api_key']}"
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
    candidates = obj.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    return "\n".join(str(x.get("text") or "") for x in parts).strip()

def request_chat(p, messages, temperature=0.2, max_tokens=500, timeout=25):
    try:
        if p.get("kind") == "gemini":
            return _gemini_request(p, messages, temperature, max_tokens, timeout)
        return _openai_request(p, messages, temperature, max_tokens, timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"{p.get('title', p['id'])} HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{p.get('title', p['id'])} network error: {e}") from e

def test_provider(pid: str, timeout: float = 12) -> str:
    p = get_provider(pid)
    if not p:
        raise RuntimeError("Провайдер не найден")
    text = request_chat(p, [{"role": "user", "content": "Ответь одним словом: OK"}], 0.0, 20, timeout)
    if not text:
        raise RuntimeError("Пустой ответ")
    return text[:80]
