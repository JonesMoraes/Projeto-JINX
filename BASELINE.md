# Baseline — 13/11/2026

Projeto: C:\Users\Windows 10 MF\JINX IA. Python 3.12.10, Qt/PyQt6 e WebEngine 6.11.0. SO detectado: Windows 10 build 19045. CPU: Intel Core i5-6200U; RAM física: 8.491.270.144 bytes (~7,9 GiB); GPU: Intel HD Graphics 520. Tratar ML como CPU, cargas opcionais ainda mais limitadas que no hardware descrito originalmente.

Aplicação original iniciada com `.venv\Scripts\python.exe -u main.py`, stdout/stderr redirecionados a logs locais ignorados pelo Git. Nenhum pacote instalado e nenhum ajuste de configuração do app feito para esta verificação.

| Verificação | Resultado | Evidência |
|---|---|---|
| Processo inicializa | done | Processo responsivo; descoberta termina com 19 ações, zero plugins rejeitados. |
| Conexão de voz | done (conexão apenas) | Log: Connected, Mic stream open, Recv started, Play started, session resumption armed. |
| Conversa falada PT-BR/EN | done (confirmação do usuário) | Usuário confirmou que o JINX ouviu e respondeu em voz alta aos dois comandos solicitados. |
| Consulta existente sem mutação | done (chamada direta) | actions.system_monitor.get_system_status() retorna dict não vazio. |
| Ação disparada por voz | done (confirmação do usuário) | Usuário confirmou resposta ao comando de uso de memória; a execução interna específica não foi capturada separadamente. |

Observações: saída DirectSound foi rejeitada pelo detector do app e houve fallback MME. Log informa latência de saída de 213 ms e cauda de eco de 463 ms: meta futura de barge-in <150 ms precisa medição e pode exigir outro backend. Aviso de depreciação pynvml não impediu inicialização. Dashboard iniciou em HTTP local como já configurado; endereço e tokens não são registrados neste documento.

Git local inicializado; autor configurado somente neste projeto conforme informado pelo usuário. Arquivos de segredo, dados pessoais, importações locais e assets Brahma não entram no baseline versionado. Código de integração do HUD existente ainda referencia assets excluídos; essa dívida está registrada no plano e não foi alterada para preservar a medição do estado original. Baseline aceito pelo usuário; Fase 0 concluída com essa dívida explícita.
