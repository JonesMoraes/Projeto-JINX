# Execução local — Fases 2 e 3

## 2.3 — Brilho por monitor
- Implementado em actions/monitor_brightness.py; testes em tests/test_monitor_brightness.py.
- Lista monitores WMI por identidade exata; escrita com leitura de confirmação e undo protegido contra mudanças posteriores. Não redireciona um monitor ausente para outro. Controle global legado preservado.
- Testar: “Liste meus monitores” / “List brightness monitors”, depois “Coloque o brilho deste monitor em 60%”.
- Dependências novas: nenhuma. API documentada em https://learn.microsoft.com/en-us/windows/win32/wmicoreprov/wmimonitorbrightnessmethods.
- Cinco testes passaram; consulta real detectou painel WMI a 100%. Escritas testadas com simulação, sem modificar o brilho real. Monitores externos sem WMI são unverified; use controle físico/global existente.
