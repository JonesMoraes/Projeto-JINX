"""Cakto sales port from João Gabriel, CC BY-NC 4.0; see NOTICE.md."""
import json
import re
import threading
from core import outcome
from core import cakto_client as api

PLUGIN = {"name": "cakto_sales", "description": "Read the user's Cakto sales: paid gross revenue today/month, latest orders, order by ID, products. Partial totals are not complete revenue.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["today_revenue", "month_revenue", "last_orders", "order", "products"]},
        "month": {"type": "STRING", "description": "YYYY-MM; defaults to current month"},
        "currency": {"type": "STRING", "enum": ["BRL", "USD"]},
        "id": {"type": "STRING", "description": "Order ID for order action"},
        "limit": {"type": "INTEGER", "description": "1–20; default 5"},
        "language": {"type": "STRING", "enum": ["pt-BR", "en"]}}, "required": ["action"]}}


def _test(values):
    try:
        _, count, _ = api.page(api.Client(values).get("/orders/", page=1, limit=1, currency="BRL"))
        return True, f"Conexão verificada / Connection verified. Pedidos BRL / BRL orders: {count}"
    except api.CaktoError as exc:
        return False, str(exc)
    except Exception:
        return False, "Falha ao testar / Test failed"


PLUGIN_SETTINGS = {"namespace": "cakto", "title": "CAKTO — SUA CONTA / YOUR ACCOUNT",
    "fields": [{"key": "client_id", "label": "Seu Client ID / Your Client ID", "type": "password"},
               {"key": "client_secret", "label": "Seu Client Secret / Your Client Secret", "type": "password"}],
    "action": {"label": "TESTAR CONEXÃO / TEST CONNECTION", "run": _test}}


def _order_summary(order, currency):
    product = order.get("product")
    return {"id": str(order.get("id") or ""), "status": str(order.get("status") or ""),
            "amount": str(api.amount(order, currency)), "currency": currency,
            "paidAt": order.get("paidAt"), "createdAt": order.get("createdAt"),
            "product": str(product.get("name") or "") if isinstance(product, dict) else ""}


def _render(result, english):
    if "gross_paid" in result:
        return "\n".join([
            ("Period: " if english else "Período: ") + result["period_start"] + " → " + result["period_end_exclusive"],
            ("Paid gross sales: " if english else "Vendas brutas pagas: ") + result["currency"] + " " + result["gross_paid"],
            ("Paid orders: " if english else "Pedidos pagos: ") + str(result["paid_orders"]),
            ("Complete query" if english else "Consulta completa") if result["complete"] else
            ("PARTIAL QUERY — not the period total" if english else "CONSULTA PARCIAL — não é o total do período"),
            ("Gross sales do not represent your available balance." if english else
             "Vendas brutas não representam seu saldo disponível.")])
    rows = result.get("items", [result])
    lines = []
    for item in rows:
        lines.append(" | ".join(str(item.get(k) or "") for k in (
            ("id", "status", "currency", "amount", "paidAt", "product") if "amount" in item else ("id", "name"))))
    if not lines:
        lines.append("No results." if english else "Nenhum resultado.")
    if result.get("has_more"):
        lines.append("More items available; showing the requested limit." if english else
                     "Há mais itens; exibindo o limite solicitado.")
    return "\n".join(lines)


def _execute(p, player=None):
    try:
        action = p.get("action")
        if action not in ("today_revenue", "month_revenue", "last_orders", "order", "products"):
            raise ValueError("action")
        currency = str(p.get("currency") or "BRL").upper()
        if currency not in ("BRL", "USD"):
            raise ValueError("currency")
        client = api.Client()
        complete = True
        if action.endswith("revenue"):
            start, end = api.bounds(action, p.get("month"))
            result = api.revenue(client, start, end, currency)
            complete = result["complete"]
        elif action == "order":
            oid = str(p.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9-]{1,128}", oid):
                raise ValueError("id")
            result = _order_summary(client.get(f"/orders/{oid}/"), currency)
            if result["id"] != oid:
                raise api.CaktoError("Pedido não confirmado / Order not verified")
        else:
            limit = int(p.get("limit", 5))
            if not 1 <= limit <= 20:
                raise ValueError("limit")
            path = "/orders/" if action == "last_orders" else "/products/"
            params = {"page": 1, "limit": limit}
            if action == "last_orders":
                params.update(currency=currency, ordering="-createdAt")
            rows, count, more = api.page(client.get(path, **params))
            result = {"items": [_order_summary(o, currency) for o in rows[:limit]] if action == "last_orders"
                      else [{"id": str(o.get("id") or ""), "name": str(o.get("name") or "")} for o in rows[:limit]],
                      "matching_total": count, "has_more": more or len(rows) > limit}
        english = p.get("language") == "en"
        label = ("Cakto — paid gross sales" if english else "Cakto — vendas brutas pagas") if action.endswith("revenue") else "Cakto"
        if not complete:
            label += " — " + ("PARTIAL RESULT" if english else "RESULTADO PARCIAL")
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if player is not None and callable(getattr(player, "show_content", None)):
            try:
                player.show_content(label, _render(result, english))
            except Exception:
                pass  # Successful API data can still be returned if the panel closed.
        wrapped = outcome.untrusted("cakto", text)
        if not complete:
            return outcome.unverified("cakto_sales", "Consulta parcial; não é faturamento total / Partial query; not total revenue", data=wrapped)
        return outcome.done("cakto_sales", data=wrapped)
    except api.NotConfigured as exc:
        return outcome.failed("cakto_sales", str(exc))
    except api.CaktoError as exc:
        return outcome.unverified("cakto_sales", str(exc))
    except (ValueError, TypeError):
        return outcome.failed("cakto_sales", "Parâmetros inválidos / Invalid parameters")
    except Exception:
        return outcome.failed("cakto_sales", "Falha de integração / Integration failure")


def run(parameters, player=None, session_memory=None):
    p = dict(parameters or {})
    if str(p.get("action", "")).endswith("revenue") and player is not None:
        # Multi-page reads never hold up the voice/tool worker for a long query.
        def work():
            result = _execute(p, player)
            if callable(getattr(player, "write_log", None)):
                state = "done" if result.startswith("status=done ") else "unverified" if result.startswith("status=unverified ") else "failed"
                try:
                    player.write_log("Cakto: " + state)
                except Exception:
                    pass
            if callable(getattr(player, "request_say", None)):
                try:
                    player.request_say(result)
                except Exception:
                    pass
        threading.Thread(target=work, name="cakto-sales-query", daemon=True).start()
        return outcome.started("cakto_sales", detail="Consultando sua conta; resultado no painel / Querying your account; result in panel")
    return _execute(p, player)
