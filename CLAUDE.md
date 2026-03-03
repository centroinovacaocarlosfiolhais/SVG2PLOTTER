# CLAUDE.md — MVP Review Context

Copia este ficheiro para a raiz de cada projeto e preenche as secções marcadas com `[ ]`.  
Este ficheiro guia o Claude Code em revisões, auditorias e sessões de QA.

---

## Projeto

**Nome:** SVG2Plotter  
**Descrição:** Controlador de cortadoras de vinil compatíveis com HPGL. Converte ficheiros SVG em comandos HPGL e envia-os por porta série para a máquina. Existe em duas variantes: app desktop Python/tkinter (Windows) e servidor LAN Flask+SocketIO acessível por browser (Linux/Windows/Raspberry Pi).  
**Estado:** MVP fechado — funcionalidade core estável, não estão previstas novas features de momento  
**Repositório:** https://github.com/centroinovacaocarlosfiolhais/svg2plotter  
**Deploy:** Local / LAN — sem cloud. Desktop corre directamente no PC. Network edition corre num laptop ou Raspberry Pi Zero 2W ligado à cortadora via USB-Serial.

---

## Stack

```
Frontend (desktop):   Python/tkinter — GUI nativa, sem browser
Frontend (network):   HTML5/CSS/JS vanilla — single-file, sem framework, Canvas API
Backend (network):    Python/Flask + Flask-SocketIO
Base dados:           N/A — estado em memória por sessão, sem persistência
Auth:                 N/A — sem autenticação, acesso aberto na LAN
Pagamentos:           N/A
Infra:                Local / LAN (MVP em laptop Linux Mint, destino: Raspberry Pi Zero 2W)
Outros:               pyserial (comunicação HPGL por USB-Serial, chipset CH340/FTDI)
                      xml.etree.ElementTree (parsing SVG, stdlib)
                      Socket.IO 4.x (WebSocket para log e progresso em tempo real)
```

---

## Âmbito do MVP

**O que está dentro do scope:**
- Parsing de SVG com suporte completo a transforms (matrix, translate, rotate, scale, skewX/Y)
- Elementos suportados: `path`, `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`
- Conversão SVG → HPGL com mapeamento de eixos correcto para Seikitech SK1350
- Modo Normal (superfícies opacas) e Mirror (vidro/janelas, corte pelo interior)
- Layout multi-ficheiro com posicionamento manual e auto-layout
- Ferramenta de escala (guardar valor → aplicar a SVG seleccionado)
- Comunicação série directa com terminador ETX (`\x03`) específico do SK1350
- App desktop: GUI tkinter, dark mode, design system industrial
- Network edition: servidor Flask porta 7733, interface web, drag & drop upload, log WebSocket em tempo real
- Instaladores para Windows (`.py`) e Linux (`.sh`) com criação de atalho Desktop

**O que está fora do scope (não rever nem sugerir):**
- Autenticação ou controlo de acesso ao servidor LAN
- Persistência de sessão / base de dados
- Suporte a outros protocolos de corte (Roland, Graphtec, EPS/PLT avançado)
- Preview de corte com simulação de velocidade/pressão
- Internacionalização além de PT/EN existente
- Testes automatizados end-to-end
- Modo multi-utilizador ou fila de trabalhos
- Interface mobile nativa
- Integração com Inkscape ou outros editores SVG

---

## Instruções para Revisão

### Prioridades (por ordem)

1. **Segurança** — inputs não sanitizados, path traversal no upload de SVGs, endpoints sem validação, porta série exposta sem restrição de IP
2. **Fiabilidade** — error handling em falt na comunicação série, edge cases em SVGs malformados ou sem viewBox, crashes no parsing de transforms inválidas, job a correr quando servidor reinicia
3. **Qualidade de código** — duplicação do motor SVG entre `svg2plotter.py` e `server.py` (intencional no MVP, ver Notas), funções longas no parser de paths
4. **Performance** — re-parsing de SVG a cada render no canvas (desktop), polylines não cacheadas entre requests (network), chamadas API redundantes no frontend
5. **Documentação** — funções de parsing SVG sem comentários inline, comportamento dos eixos HPGL não documentado no código

### O que NÃO fazer

- Não sugerir refactoring arquitectural completo — o MVP está fechado
- Não propor novas features ou mudanças de produto
- Não reescrever código funcional só por preferência estilística
- Não gerar testes automatizados a menos que seja pedido explicitamente
- Não alterar ficheiros de configuração de infra sem confirmação
- **Não sugerir separar o motor SVG numa library partilhada** — duplicação é débito técnico aceite conscientemente (ver Notas)

---

## Convenções do Projeto

```
Linguagem dos comentários: EN
Linguagem da UI:           EN (interface) + PT (documentação/manuais)
Estilo de nomes:           snake_case (Python) · camelCase (JavaScript)
Indentação:                4 espaços (Python) · 2 espaços (HTML/JS/CSS)
Commits:                   livre (projecto de autor único)
Env vars:                  N/A no MVP — sem variáveis de ambiente sensíveis
Secrets:                   N/A — sem chaves de API, sem tokens
Porta:                     7733 (hardcoded em server.py — constante PORT no topo do ficheiro)
```

---

## Ficheiros e Pastas — Guia Rápido

```
/svg2plotter.py         → app desktop completa (monolítico por design)
/setup.py               → instalador Windows (deps + atalho Desktop)
/README.md              → documentação principal do projecto
/docs/                  → manuais PDF (EN + PT)
/network/server.py      → servidor Flask + SocketIO (monolítico por design)
/network/static/
  index.html            → interface web completa (single-file por design)
/network/setup-network.sh   → instalador Linux/Pi
/network/setup-network.py   → instalador Windows
/network/README.md      → documentação da Network Edition
```

**Ficheiros a ignorar na revisão:**
- `__pycache__/`, `*.pyc`, `*.pyo`
- `*.ico`, `*.bat`, `start.sh`, `start-network.bat`
- `_create_*.vbs` (temporários do instalador)
- `svg2plotter_uploads/` (uploads temporários do servidor)
- `*.log`

---

## Comandos Úteis

```bash
# ── Desktop App ───────────────────────────────────────────────
# Instalar dependências
pip install pyserial

# Correr directamente
python svg2plotter.py

# Instalar (cria atalho Desktop + launcher)
python setup.py

# ── Network Edition ───────────────────────────────────────────
# Instalar dependências
pip install flask flask-socketio pyserial

# Correr o servidor (Linux/Mac)
cd network/
python server.py

# Correr o servidor (Windows)
cd network/
python server.py

# Setup completo Linux (instala deps + permissões serial + atalho)
cd network/
bash setup-network.sh

# Setup completo Windows
cd network/
python setup-network.py

# Aceder à interface
# http://localhost:7733
# http://<ip-do-host>:7733  (outros dispositivos na LAN)

# ── Variáveis de ambiente necessárias ─────────────────────────
# N/A — MVP sem variáveis de ambiente
```

---

## Sessão de Revisão — Prompt de Arranque

Quando inicias o Claude Code neste repo, usa este prompt:

```
Lê o CLAUDE.md deste projecto. Faz uma revisão do código focada nas prioridades definidas:
segurança primeiro, depois fiabilidade, depois qualidade. Para cada problema encontrado,
indica: ficheiro e linha, descrição clara do problema, e sugestão concreta de fix.
Respeita o âmbito do MVP — não propões novas features nem refactoring estrutural.
Apresenta um sumário final com os problemas por prioridade.
```

---

## Notas Adicionais

**Duplicação intencional do motor SVG**  
O código de parsing SVG/HPGL (`extract_paths`, `svg_to_hpgl`, transforms) está duplicado entre `svg2plotter.py` (desktop) e `network/server.py`. Esta duplicação é **débito técnico aceite conscientemente** — o MVP prioriza os dois ficheiros serem auto-contidos e deployáveis de forma independente. Uma library partilhada está fora do scope actual.

**Monolítico por design**  
Tanto a app desktop como a interface web são ficheiros únicos (`svg2plotter.py`, `static/index.html`). Esta decisão é intencional para simplificar distribuição e instalação em contexto educativo (CICF).

**Mapeamento de eixos SK1350**  
O Seikitech SK1350 tem uma orientação de eixos não-standard: o eixo X HPGL corresponde ao movimento transversal da cabeça, e o eixo Y ao avanço do vinil. O flip do eixo X no modo Normal (e a ausência de flip no modo Mirror) é comportamento **intencional e validado** com a máquina física — não alterar sem teste físico.

**Terminador ETX**  
Cada comando HPGL é terminado com `\x03` (byte ETX). Este comportamento é específico do SK1350 e não é standard HPGL — outros plotters podem não precisar ou podem rejeitar este byte.

**Porta 7733**  
Porta não-standard escolhida intencionalmente para evitar conflitos com serviços comuns. Definida como constante `PORT = 7733` no topo de `network/server.py`.

**Upload dir temporária**  
Os SVGs carregados pela interface web são guardados em `tempfile.gettempdir()/svg2plotter_uploads/`. Não há limpeza automática entre sessões — acumulação de ficheiros em uso prolongado é um edge case conhecido e aceite no MVP.

**Hardware alvo**  
- Desktop: Windows 10/11, Python 3.8+, cortadora Seikitech SK1350 via USB-Serial (CH340/CH341)
- Network MVP: laptop Linux Mint (validação) → Raspberry Pi Zero 2W (produção)
- Compatível com qualquer cortadora HPGL por porta série

**Contexto institucional**  
Projecto desenvolvido para o Centro de Inovação Carlos Fiolhais (CICF), CDI Portugal, Maia. Usado em contexto educativo com jovens 12–18 anos. Simplicidade de instalação e operação tem prioridade sobre elegância de código.
