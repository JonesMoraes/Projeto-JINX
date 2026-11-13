# Execução local — Fases 2 e 3

## 2.4 — Contexto da janela ativa
- core/foreground_context.py, plugins/foreground_context.py, main.py e providers/engine_pipeline.py; tests/test_foreground_context.py.
- Privacidade opt-in via cartão/voz e undo; somente app/título/PID, sem screenshot. Metadados não confiáveis enviados a cada mudança (amostra 5 s), sem gerar fala espontânea no pipeline.
- Testar: “Ative o contexto da janela”, depois “O que é isso?” / “Enable window context”, “What is this?”. Desativar interrompe novas capturas; não apaga conteúdo já enviado.
- Três testes específicos; padrão desligado não chama APIs de captura. Sem pacote novo. Janela pode mudar antes da resposta; contexto não é visão e pode ficar desatualizado. Voz real pendente.

## 2.3 — Brilho por monitor
- Implementado em actions/monitor_brightness.py; testes em tests/test_monitor_brightness.py.
- Lista monitores WMI por identidade exata; escrita com leitura de confirmação e undo protegido contra mudanças posteriores. Não redireciona um monitor ausente para outro. Controle global legado preservado.
- Testar: “Liste meus monitores” / “List brightness monitors”, depois “Coloque o brilho deste monitor em 60%”.
- Dependências novas: nenhuma. API documentada em https://learn.microsoft.com/en-us/windows/win32/wmicoreprov/wmimonitorbrightnessmethods.
- Cinco testes passaram; consulta real detectou painel WMI a 100%. Escritas testadas com simulação, sem modificar o brilho real. Monitores externos sem WMI são unverified; use controle físico/global existente.
