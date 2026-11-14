"""Explicit HA discovery and configured Tuya switching; never scans on import."""
import ipaddress
import json
import re
from urllib.parse import urlsplit
from memory.config_manager import get_plugin_config
from core import outcome, undo


class HomeError(ValueError):
    pass


class Client:
    def __init__(self, backend):
        if backend not in ('ha', 'tuya'):
            raise HomeError('Backend inválido / Invalid backend')
        self.backend = backend
        self.cfg = get_plugin_config('smart_home')
        self.check()

    def check(self):
        if self.cfg.get('enabled') is not True or get_plugin_config('smart_home') != self.cfg:
            raise HomeError('Casa desligada ou configuração mudou / Home disabled or settings changed')

    def request(self, method, path, body=None):
        self.check()
        import requests
        base = str(self.cfg.get('ha_url', '')).rstrip('/')
        url = urlsplit(base)
        if (url.scheme not in ('https', 'http') or not url.hostname or url.username or
                url.password or url.query or url.fragment or url.path not in ('', '/')):
            raise HomeError('URL Home Assistant inválida / Invalid Home Assistant URL')
        if url.scheme == 'http':
            try:
                local = ipaddress.ip_address(url.hostname).is_private
            except ValueError:
                local = url.hostname.endswith('.local') or url.hostname == 'localhost'
            if not local:
                raise HomeError('HTTP permitido apenas na rede local / HTTP only on local network')
        token = str(self.cfg.get('ha_token') or '')
        if not token:
            raise HomeError('Configure o token / Configure token')
        try:
            with requests.request(method, base + '/api/' + path, json=body,
                    headers={'Authorization': 'Bearer ' + token},
                    timeout=(3, 8), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise HomeError('Home Assistant indisponível / Home Assistant unavailable')
                return response.json()
        except HomeError:
            raise
        except Exception:
            raise HomeError('Conexão não verificada / Connection unverified') from None

    def tuya(self):
        self.check()
        import tinytuya
        address = ipaddress.ip_address(str(self.cfg.get('tuya_ip', '')))
        if not address.is_private or address.is_loopback or address.is_multicast:
            raise HomeError('Configure IP local do dispositivo / Configure device LAN IP')
        version = float(self.cfg.get('tuya_version') or 3.3)
        if version not in (3.1, 3.2, 3.3, 3.4, 3.5):
            raise HomeError('Versão Tuya inválida / Invalid Tuya version')
        device = tinytuya.OutletDevice(str(self.cfg.get('tuya_id', '')), str(address),
                                      str(self.cfg.get('tuya_key', '')), version=version)
        device.set_socketTimeout(3)
        device.set_socketRetryLimit(1)
        return device

    def entity(self, entity):
        if not re.fullmatch(r'(light|switch)\.[a-z0-9_]+', str(entity)):
            raise HomeError('Use ID exato de luz ou interruptor / Use exact light or switch ID')
        return entity

    def state(self, entity):
        self.check()
        if self.backend == 'ha':
            row = self.request('GET', 'states/' + self.entity(entity))
            if not isinstance(row, dict) or row.get('entity_id') != entity:
                raise HomeError('Estado inválido / Invalid state')
            return row
        if entity != str(self.cfg.get('tuya_id') or '') or not entity:
            raise HomeError('Use ID Tuya configurado / Use configured Tuya ID')
        device = self.tuya()
        try:
            row = device.status()
            value = row.get('dps', {}).get(str(int(self.cfg.get('tuya_dp') or 1)))
            if type(value) is not bool:
                raise HomeError('DPS não é interruptor booleano / DPS is not a boolean switch')
            return {'entity_id': entity, 'state': 'on' if value else 'off', 'dps': row['dps']}
        finally:
            device.close()

    def discover(self):
        if self.backend == 'tuya':
            return [self.state(str(self.cfg.get('tuya_id') or ''))]
        rows = self.request('GET', 'states')
        if not isinstance(rows, list):
            raise HomeError('Resposta inválida / Invalid response')
        return [{'entity_id': r.get('entity_id'), 'state': r.get('state'),
                 'name': r.get('attributes', {}).get('friendly_name', '')}
                for r in rows if isinstance(r, dict) and
                re.fullmatch(r'(light|switch)\.[a-z0-9_]+', str(r.get('entity_id')))][:200]

    def change(self, entity, target, register_undo=True):
        if target not in ('on', 'off'):
            raise HomeError('Estado inválido / Invalid state')
        before = self.state(entity)
        if before.get('state') not in ('on', 'off'):
            raise HomeError('Dispositivo indisponível / Device unavailable')
        if before['state'] == target:
            return outcome.done('smart_home', entity=entity, state=target, changed=False)
        self.check()
        if self.backend == 'ha':
            self.request('POST', 'services/' + entity.split('.')[0] + '/turn_' + target,
                         {'entity_id': entity})
        else:
            device = self.tuya()
            try:
                device.set_status(target == 'on', switch=int(self.cfg.get('tuya_dp') or 1))
            finally:
                device.close()
        after = self.state(entity)
        if after.get('state') != target:
            return outcome.unverified('smart_home', 'Estado ainda não confirmado / State not yet confirmed')
        if register_undo:
            def restore():
                current = self.state(entity)
                # HA last_updated detects intervening changes even if state is the same.
                if current != after:
                    raise HomeError('Estado mudou; desfazer cancelado / State changed; undo cancelled')
                return self.change(entity, before['state'], False)
            undo.push_undo('Casa / Home ' + entity, restore)
        return outcome.done('smart_home', entity=entity, state=target)


def execute(parameters):
    try:
        client = Client(parameters.get('backend', 'ha'))
        action = parameters.get('action')
        if action in ('on', 'off'):
            return client.change(parameters.get('entity_id'), action)
        data = client.discover() if action == 'discover' else client.state(parameters.get('entity_id'))
        return outcome.done('smart_home', data=outcome.untrusted('smart-home', json.dumps(data, ensure_ascii=False)))
    except HomeError as exc:
        return outcome.unverified('smart_home', str(exc))
