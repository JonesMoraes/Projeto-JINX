"""Original parcel lookup using the official Correios API contract."""
import json
import re
from datetime import datetime
from core import outcome
from memory.config_manager import get_plugin_config

PAGE = "https://rastreamento.correios.com.br/app/index.php"
HOSTS = {"production": "https://api.correios.com.br", "homologation": "https://apihom.correios.com.br"}

PLUGIN = {"name": "parcel_tracking", "description": "Track a Correios PARCEL by postal code. Requires user's authorized Correios API token; otherwise show official site. Unrelated to Rastracking sales.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["track", "site"]},
        "code": {"type": "STRING", "description": "Postal tracking code: two letters, nine digits, two letters"}}, "required": ["code"]}}


def _code(value):
    code = re.sub(r"\s+", "", str(value or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{9}[A-Z]{2}", code):
        raise ValueError("Código postal inválido / Invalid postal tracking code")
    return code


def _fetch(code, values):
    import requests
    token = str(values.get("token") or "").strip()
    environment = values.get("environment") or "production"
    if environment not in HOSTS or not token:
        raise ValueError("Informe seu token autorizado em ⚙ → plugins → Encomendas / Set your authorized token")
    try:
        response = requests.get(HOSTS[environment] + "/srorastro/v1/objetos/" + code,
            params={"resultado": "T"}, headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            timeout=(4, 12), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"Correios HTTP {response.status_code}; verifique token/contrato / check token and contract")
        data = response.json()
        objects = data.get("objetos")
        matches = [o for o in objects or [] if isinstance(o, dict) and o.get("codObjeto") == code]
        if len(matches) != 1 or not isinstance(matches[0].get("eventos"), list):
            raise ValueError("Objeto ou eventos não confirmados / Object or events unverified")
        events = []
        for event in matches[0]["eventos"]:
            timestamp = str(event.get("dtHrCriado") or "")
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if not event.get("descricao"):
                raise ValueError("Status não informado / Missing status")
            address = (event.get("unidade") or {}).get("endereco") or {}
            events.append({"date": timestamp, "status": str(event["descricao"]),
                           "city": str(address.get("cidade") or ""), "state": str(address.get("uf") or "")})
        if not events:
            raise ValueError("Sem eventos disponíveis / No events available")
        events.sort(key=lambda e: datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp(), reverse=True)
        return {"code": code, "source": "Correios", "environment": environment, "events": events,
                "checked_at": datetime.now().astimezone().isoformat()}
    except ValueError:
        raise
    except Exception:
        raise ValueError("Falha na consulta; status não confirmado / Query failed; status unverified") from None


def _test(values):
    try:
        _fetch(_code(values.get("test_code")), values)
        return True, "Eventos consultados na sua conta / Events retrieved with your account"
    except Exception:
        return False, "Informe token e código do seu contrato; consulte permissões/validade / Set token and your contract's code; check permissions and expiry"


PLUGIN_SETTINGS = {"namespace": "parcel_tracking", "title": "ENCOMENDAS — CORREIOS / PARCELS",
    "fields": [{"key": "token", "label": "SEU token Bearer autorizado / YOUR authorized token", "type": "password"},
               {"key": "environment", "label": "Ambiente / Environment", "type": "choice", "options": list(HOSTS), "default": "production"},
               {"key": "test_code", "label": "SEU código para teste / YOUR test tracking code", "type": "text"}],
    "action": {"label": "TESTAR CONSULTA / TEST LOOKUP", "run": _test}}


def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    try:
        code = _code(p.get("code"))
    except ValueError as exc:
        return outcome.failed("parcel_tracking", str(exc))
    if p.get("action", "track") == "site":
        try:
            import webbrowser
            accepted = webbrowser.open(PAGE)
        except Exception:
            accepted = False
        return outcome.unverified("parcel_tracking", "Consulte o código no site oficial; status ainda não verificado / Enter code on official site; delivery status unverified",
                                  code=code, site=PAGE, browser_request_accepted=accepted)
    if p.get("action", "track") != "track":
        return outcome.failed("parcel_tracking", "Ação inválida / Invalid action")
    try:
        result = _fetch(code, get_plugin_config("parcel_tracking"))
    except ValueError:
        return outcome.unverified("parcel_tracking", "Consulta indisponível: confira seu token, permissões e vínculo ao contrato; token pode estar vencido / Check token, permissions and sender contract", site=PAGE)
    text = "\n".join(e["date"] + " — " + e["status"] + " — " + e["city"] for e in result["events"])
    if player and callable(getattr(player, "show_content", None)):
        try:
            player.show_content("Correios — " + code, text)
        except Exception:
            pass
    return outcome.done("parcel_tracking", data=outcome.untrusted("correios", json.dumps(result, ensure_ascii=False)))
