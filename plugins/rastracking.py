"""Sales/client/support port from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
import json
import threading
from decimal import Decimal
from core import outcome
from core import rastracking_client as api

PLUGIN = {"name": "rastracking", "description": "Rastracking SALES, clients and support; not parcel tracking. Read totals, top clients, expirations, pending support or sales.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["tracked_revenue", "top_clients", "expiring_clients", "support_pending", "last_sales", "sales_count", "sales_summary"]},
        "period": {"type": "STRING", "enum": ["today", "yesterday", "week", "month", "custom", "overdue"]},
        "start": {"type": "STRING", "description": "YYYY-MM-DD for custom period"},
        "end": {"type": "STRING", "description": "YYYY-MM-DD for custom period"},
        "with_subject": {"type": "BOOLEAN", "description": "Only true when user explicitly asks to read support messages"},
        "limit": {"type": "INTEGER", "description": "1–20; default 5"}}, "required": ["action"]}}


def _test(values):
    try:
        api.Client(values).get("clients", limit=1)
        return True, "Consulta de clientes verificada / Clients query verified"
    except api.TrackingError as exc:
        return False, str(exc)
    except Exception:
        return False, "Falha ao testar / Test failed"


PLUGIN_SETTINGS = {"namespace": "rastracking", "title": "RASTRACKING — VENDAS / SALES",
    "fields": [{"key": "base_url", "label": "URL HTTPS da SUA API (inclua /api/integrations) / YOUR API URL", "type": "text"},
               {"key": "api_key", "label": "SUA chave de leitura / YOUR read API key", "type": "password"}],
    "action": {"label": "TESTAR CONEXÃO / TEST CONNECTION", "run": _test}}


def _panel(result):
    labels = {"recorded_BRL": "Registrado BRL / Recorded BRL", "attributed_BRL": "Atribuído BRL / Attributed BRL",
              "purchases": "Vendas / Purchases", "count": "Quantidade / Count", "BRL": "Total BRL",
              "average_BRL": "Ticket médio BRL / Average BRL", "matching_count": "Encontrados / Found"}
    if isinstance(result, list):
        rows = result
        heading = []
    else:
        rows = result.get("clients") or result.get("items") or []
        heading = [labels.get(k, k) + ": " + str(v) for k, v in result.items() if not isinstance(v, list)]
    lines = heading + [" | ".join(str(v or "—") for v in row.values()) for row in rows[:40]]
    if len(rows) > 40:
        lines.append("Exibindo 40 itens; há mais / Showing 40 items; more available")
    return "\n".join(lines) or "Nenhum resultado / No results"


def _query(p, player=None):
    try:
        action = p.get("action")
        allowed = ("tracked_revenue", "top_clients", "expiring_clients", "support_pending", "last_sales", "sales_count", "sales_summary")
        if action not in allowed:
            raise ValueError("action")
        limit = int(p.get("limit", 5))
        if not 1 <= limit <= 20:
            raise ValueError("limit")
        client = api.Client()
        if action == "support_pending":
            rows, complete = client.collect("support/conversations", awaitingReply="true")
            result = []
            for row in rows:
                if row.get("awaitingReply") is not True or not row.get("latestClientMessage"):
                    continue
                msg = row["latestClientMessage"]
                item = {"client": str((row.get("client") or {}).get("name") or ""),
                        "since": msg.get("createdAt") or row.get("lastClientMessageAt")}
                if p.get("with_subject") is True:
                    item["subject"] = str(msg.get("body") or "")[:300]
                result.append(item)
        else:
            selected = p.get("period", "today")
            if selected == "overdue" and action == "expiring_clients":
                from datetime import date, timedelta
                a, b = None, (date.today() - timedelta(days=1)).isoformat()
            else:
                a, b = api.period(selected, p.get("start"), p.get("end"))
            if action == "expiring_clients":
                params = {"dueBefore": b, **({"dueAfter": a} if a else {})}
            else:
                params = {"startDate": a, "endDate": b}
            path = "sales" if action in ("last_sales", "sales_count", "sales_summary") else "clients"
            if action == "last_sales":
                params["sort"] = "saleDate_desc"
            rows, complete = client.collect(path, **params)
            if action in ("tracked_revenue", "top_clients"):
                total, attributed, purchases, top = Decimal(0), Decimal(0), 0, []
                for row in rows:
                    value = row.get("revenue")
                    if not isinstance(value, dict):
                        raise api.TrackingError("Receita ausente; total não confirmado / Missing revenue; total unverified")
                    recorded = api.money(value.get("recordedAmount"))
                    total += recorded
                    attributed += api.money(value.get("attributedAmount"))
                    count = value.get("recordedPurchases")
                    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                        raise api.TrackingError("Contagem inválida / Invalid count")
                    purchases += count
                    top.append((recorded, str(row.get("name") or "")))
                result = {"recorded_BRL": str(total), "attributed_BRL": str(attributed), "purchases": purchases}
                if action == "top_clients":
                    result["clients"] = [{"name": name, "BRL": str(value)} for value, name in sorted(top, reverse=True)[:limit]]
            elif action == "expiring_clients":
                result = [{"name": str(row.get("name") or ""), "due": row.get("nextDueDate")}
                          for row in rows if row.get("accountStatus") != "CANCELLED"]
            else:
                clean = [{"amount_BRL": str(api.money(row.get("amount", row.get("value")))),
                          "date": row.get("saleDate") or row.get("createdAt"),
                          "method": str(row.get("paymentMethod") or "")} for row in rows]
                if action == "last_sales":
                    result = {"items": clean[:limit], "matching_count": len(clean)}
                else:
                    total = sum((Decimal(row["amount_BRL"]) for row in clean), Decimal(0))
                    result = {"count": len(clean), "BRL": str(total)}
                    if action == "sales_summary":
                        result["average_BRL"] = str((total / len(clean)).quantize(Decimal("0.01"))) if clean else None
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if player and callable(getattr(player, "show_content", None)):
            try:
                player.show_content("Rastracking — " + ("consulta completa / complete query" if complete else "PARCIAL / PARTIAL"), _panel(result))
            except Exception:
                pass
        data = outcome.untrusted("rastracking", text)
        return (outcome.done("rastracking", data=data) if complete else outcome.unverified(
            "rastracking", "Paginação parcial; não é total / Partial pagination; not a total", data=data))
    except api.TrackingError as exc:
        return outcome.unverified("rastracking", str(exc))
    except (ValueError, TypeError):
        return outcome.failed("rastracking", "Parâmetros ou dados inválidos / Invalid parameters or data")
    except Exception:
        return outcome.failed("rastracking", "Falha de integração / Integration failure")


def run(parameters, player=None, session_memory=None):
    p = dict(parameters or {})
    if player is None:
        return _query(p)
    def work():
        result = _query(p, player)
        if callable(getattr(player, "request_say", None)):
            try:
                player.request_say(result)
            except Exception:
                pass
    threading.Thread(target=work, name="rastracking-query", daemon=True).start()
    return outcome.started("rastracking", detail="Consultando SUA API / Querying YOUR API")
