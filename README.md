# Claude Code Usage Widget 📊

Un widget leggero e moderno per la **System Tray** di **Windows 11** e **Linux (Ubuntu / GNOME)**, progettato per monitorare in tempo reale il consumo di token e le soglie di rate-limit di **Claude Code**.

Rimani sempre aggiornato sullo stato della tua quota senza dover aprire il browser o interrompere il tuo flusso di lavoro nel terminale.

---

## 🌟 Funzionalità Principali

* **The "Glance" State (Icona Dinamica)**: Anello di progresso circolare disegnato dinamicamente a runtime con supersampling 4x e logo centrale di Claude:
  * `< 75%`: Colore neutro (si adatta automaticamente al tema Chiaro/Scuro della taskbar).
  * `75% – 90%`: Arancione ambra (`#F59E0B` - Avviso).
  * `> 90%`: Rosso corallo (`#EF4444` - Critico).
* **Hover State (Native Tooltip)**: Passando il mouse sopra l'icona compare il tooltip formattato `[Workspace] Claude Code: XX% - Reset in Xh Ym` (con salvaguardia del limite di 128 caratteri di Windows).
* **Click State (Micro-Flyout Window)**: Cliccando con il tasto sinistro si apre una finestra popup *borderless* moderna con chiusura automatica al click-outside:
  * Gauge semicircolare con percentuale e countdown al reset.
  * Dettaglio metriche Token: **Input**, **Output**, **Thinking 🧠** e % di cache read.
  * Limite settimanale a 7 giorni.
  * Drawer impostazioni integrato (soglie di alert, chiave Enterprise e modalità simulazione Mock).
* **Autenticazione Ibrida Intelligente**:
  * **Auto-detect CLI (`claude auth login`)**: legge automaticamente i token OAuth dal Windows Credential Manager o dal Secret Service di GNOME (`~/.claude/.credentials.json`).
  * **Variabili d'ambiente**: fallback su `CLAUDE_CODE_OAUTH_TOKEN`.
  * **Admin API Key**: supporto Enterprise per chiavi `sk-ant-admin-...` salvate cifrate nel portachiavi di sistema.
* **Prevenzione HTTP 429**: il FileWatcher monitora `~/.claude/projects/` per aggiornare i dati solo quando usi attivamente Claude Code, riducendo le chiamate API in idle ed evitando rate limit.
* **Notifiche Push Native**: Toast Windows 11 e notifiche DBus su Ubuntu con isteresi anti-spam (avviso inviato una sola volta per finestra di reset al raggiungimento dell'80%, 95% o 100%).

---

## 🚀 Installazione e Distribuzione su Windows

### Opzione 1: Installer Ufficiale Guidato (Raccomandato per Tutti i PC)
Il classico pacchetto di installazione standard di Windows:
1. Scarica ed esegui il file di setup: [`dist/ClaudeUsageWidget-Setup.exe`](file:///d:/Git/AnthropicUsage/dist/ClaudeUsageWidget-Setup.exe).
2. Segui la procedura guidata (in italiano):
   * Scegli se creare l'icona sul Desktop.
   * Scegli se avviare l'app all'accesso a Windows.
3. Il programma viene registrato ufficialmente nelle **Impostazioni di Windows ("App installate")**, nel **Menu Start** e si avvia automaticamente con la sua icona dedicata.
4. Per disinstallare: si può rimuovere direttamente da *Impostazioni di Windows > App > App installate > Disinstalla*.

### Opzione 2: Eseguibile Standalone Portatile (Senza Installazione)
Se preferisci un file eseguibile portatile da usare senza installare nulla (ad esempio da una chiavetta USB):
* Scarica [`dist/ClaudeUsageWidget.exe`](file:///d:/Git/AnthropicUsage/dist/ClaudeUsageWidget.exe) e fai doppio click: si posiziona subito nella barra di sistema.

---

## 🛠️ Avvio per Sviluppatori (Stack Python + uv)

### Prerequisiti
* Python 3.11+
* [`uv`](https://github.com/astral-sh/uv) (consigliato per velocità) o `pip`

### Installazione ed Esecuzione Locale

```bash
# Clona il repository
git clone https://github.com/tuo-utente/AnthropicUsage.git
cd AnthropicUsage

# Installa le dipendenze con uv
uv sync

# Avvia l'applicazione
uv run python main.py
```

### Esecuzione dei Test

```bash
.venv\Scripts\python.exe -m pytest -v
# oppure su Linux:
.venv/bin/pytest -v
```

---

## 🏗️ Architettura del Progetto

```
d:\Git\AnthropicUsage/
├── pyproject.toml              # Gestione dipendenze e build tramite uv/hatch
├── README.md                   # Documentazione di progetto
├── src/
│   └── claude_usage/
│       ├── main.py             # Entrypoint QApplication, loop qasync, OS quirks
│       ├── autostart.py        # Integrazione Registro Win11 e XDG Autostart Linux
│       ├── config.py           # Gestione impostazioni e salvataggio sicuro chiavi
│       ├── core/
│       │   ├── models.py       # Dataclass (AuthState, UsageSnapshot, TokenBreakdown)
│       │   ├── auth_manager.py # Lettura Keyring, .credentials.json e auto-refresh
│       │   ├── api_client.py   # Client httpx per /api/oauth/usage e Admin API
│       │   ├── jsonl_parser.py # Parser transcript locali per estrazione token Thinking
│       │   ├── notifier.py     # Gestione notifiche native con isteresi
│       │   └── engine.py       # Orchestratore e FileWatcher (watchfiles)
│       └── ui/
│           ├── theme.py        # Palette semaforica e rilevamento tema di sistema
│           ├── icon_renderer.py# Generatore vettoriale Pillow 256x256 supersampled
│           ├── positioner.py   # Calcolo coordinate pixel-perfect multi-monitor
│           ├── flyout.py       # Finestra borderless, gauge semicircolare e drawer
│           └── tray.py         # Controller QSystemTrayIcon, tooltip e menu contestuale
└── tests/
    ├── test_auth_manager.py    # Test unitari autenticazione e scadenze
    ├── test_icon_renderer.py   # Test generazione grafica e soglie colore
    ├── test_jsonl_parser.py    # Test deduplicazione streaming e token Thinking
    └── test_notifier_hysteresis.py # Test isteresi notifiche
```

---

## 📄 Licenza e Crediti

Sviluppato con cura e dedizione da **giuspo** 🚀.

Questo software è distribuito sotto licenza **GNU General Public License v3.0 (GPLv3)**.  
Consulta il file [`LICENSE`](LICENSE) per i termini completi della licenza.  
*Copyleft garantito: sei libero di usare, studiare e modificare il codice, purché ogni redistribuzione o modifica rimanga open source sotto la stessa licenza.*

