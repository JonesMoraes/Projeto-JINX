# Skills locais do JINX

Uma skill fica em uma pasta dentro de `skills/`. O arquivo `SKILL.md` contém
metadados em YAML front matter; `handler.py` implementa `class Skill(BaseSkill)`.
O diretório é observado pelo `watchdog`: alterações válidas entram em vigor sem
reiniciar a aplicação. Se uma edição estiver inválida, a última versão válida
continua ativa.

```text
skills/
  exemplo/
    SKILL.md
    handler.py
```

Exemplo de `SKILL.md`:

```yaml
---
name: exemplo
description: Demonstra uma skill local
intents:
  - demonstrar exemplo
supported_os: [windows, macos, linux]
version: "1.0.0"
required_capabilities: []
params:
  type: object
  properties:
    texto:
      type: string
  required: [texto]
  additionalProperties: false
---
Descrição longa opcional da skill.
```

Exemplo de `handler.py`:

```python
from skills import BaseSkill, SkillContext, SkillResult


class Skill(BaseSkill):
    async def run(self, params: dict, ctx: SkillContext) -> SkillResult:
        return SkillResult("done", params["texto"])
```

O JINX expõe descoberta e execução pela ferramenta `skill_registry` (`list`,
`resolve`, `run`). Parâmetros são conferidos contra o JSON Schema declarado.
`resolve` aceita apenas correspondência exata e sem distinção de maiúsculas; a
busca semântica por embeddings e function calling limitado por gramática ainda
não fazem parte deste primeiro marco. Skills são código Python local e devem
ser revisadas antes de serem adicionadas.

Teste a fundação com:

```powershell
python -m unittest tests.test_skill_registry -v
```
