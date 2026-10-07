# HOLD_MEASUREMENT — test del candidato dopo la 0.8.0

I gate tecnici richiesti sono passati. **Il confronto economico non è stato
eseguito**: mancano budget esplicito, modello/effort e un executor verificato con
credenziali non accessibili al solver. L'integrazione snella nel vero Codex e gli
oracle nel nuovo ambiente rimangono da verificare. Nessun risparmio AI è dimostrato.

Il prodotto già presente all'inizio di questa campagna è rimasto invariato.
Sono stati modificati soltanto runner, test di misurazione e documentazione.
Nessun commit, push, tag, release, intervento sugli stash o scrittura sul progetto
applicativo originale. Le identità complete sono in [identities.json](identities.json).

| Verifica eseguita | Esito |
| --- | --- |
| Suite Rust, `cargo xtask check` | 87 test passati; formatting e lint passati |
| Contabilità, runner, collector, parser storici | 34 test Python passati |
| Intent nativi e primitive contro la 0.6.0 | Passati su tutti i 10 linguaggi; ulteriori gruppi Flutter e mobile passati |
| Android con SDK | Passato |
| macOS/UIKit con SDK | **not_run**: questo host è Linux |
| Profili MCP, errori e recupero | Passati |
| Gate originale rename | Passato: 19 riferimenti conservati, 17 pattern oracle, tutte le pagine/espansioni contabilizzate |
| Probe nativi dei binari B/C/D | Cataloghi 16/5/5 tool, intent invocabili, error recovery ed EOF verificati |
| Isolamento filesystem su quattro copie rappresentative | Confini verificati; A senza artefatti del grafo |
| Canale credenziali dell'executor storico | **Fallisce** con sentinella fittizia leggibile dal solver; nessuna credenziale reale letta/copiata |
| Codex reale: registrazione, raccolta snella, usage e oracle | **not_run** in questa campagna |

La review nativa conserva 100 siti dopo inserimento di commento Unicode e righe
CRLF: zero false aggiunte/rimozioni semantiche, una modifica di sorgente visibile,
202 relazioni riposizionate ispezionabili. Il confronto audit/lean mantiene siti,
molteplicità e confidenza. Le verifiche compiler/test rimangono esplicitamente non
eseguite nel risultato del grafo. Questi sono test del meccanismo, non task di un
agente accettati dall'oracle.

Il gate originale rename misura 36167 caratteri della raccolta primitiva contro
23663 della raccolta intent, incluso snippet accessorio: riduzione locale del
34,57%. Gli schemi sono registrati separatamente. **Caratteri e byte non sono token
del modello.** È conservato anche un replay supplementare con una traccia diversa,
che fallisce la soglia di volume: un'unica chiamata primitiva da 6662 caratteri
contro 21826 dell'inventario intent. Non sostituisce il gate originale né viene
eliminato per mostrare soltanto il caso favorevole.

La diagnosi del retrieval conferma limiti invariati in C e D: dieci righe dello
stesso anchor possono occupare il top-k; dopo il cap globale di 100000 documenti,
un match presente in un file successivo nello scope richiesto può non essere
raccolto. `incomplete=true`, totale null e raccolta incompleta rimangono visibili.
Non è stata implementata F3 né aumentato un budget per aggirare questo limite.

Il runner ora tratta condizioni parametriche (testate con 2, 3, 4 e 5 condizioni),
repliche, retry e identità complete, con journal append-only e resume che preserva
un tentativo interrotto come consumo ignoto. Rifiuta overwrite e mutazioni degli
artefatti congelati, comprese le sorgenti provider. Distingue MCP del grafo e MCP
ordinari: questi ultimi sono ammessi in A. Una variante sintetica deliberatamente
peggiore produce REGRESSION; dati ignoti non producono una vittoria economica.
I parser storici sono invariati e continuano a passare i loro test.

Sono preparate **48 celle nuove** per sei task reali già noti, due repliche e A/B/C/D.
Le prime copie draft sono conservate separatamente da quelle della configurazione
finale; nessun tentativo è iniziato in nessuna copia. Non sono task holdout e i
risultati/risposte dei pilot precedenti non sono riutilizzati come nuove misure.
L'ordine bilanciato, i limiti proposti e i gate sono in [protocol.md](protocol.md)
e [schedule.json](schedule.json). Modello ed effort sono ancora null; nessuna fase
AI è approvata. P1 e P2 non partono per effetto della preparazione delle copie.

| Condizione | Celle accettate/eseguite | Input non cached | Cached | Input totale | Output | Richieste | Primaria/standard | Primaria/0.8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A standard | 0/0 | non misurato | non misurato | non misurato | non misurato | non eseguite | indefinita | indefinita |
| B 0.7.0 | 0/0 | non misurato | non misurato | non misurato | non misurato | non eseguite | indefinita | indefinita |
| C 0.8.0 finale | 0/0 | non misurato | non misurato | non misurato | non misurato | non eseguite | indefinita | indefinita |
| D candidato locale | 0/0 | non misurato | non misurato | non misurato | non misurato | non eseguite | indefinita | indefinita |

Zero tentativi benchmark, zero run di giudici AI; le componenti di consumo e i costi
monetari restano null. Il costo dell'agente che ha preparato e verificato la campagna
non è esposto e non viene dichiarato zero. I tempi locali misurati nelle fixture
sono separati dal consumo del solver. Intervalli, costo per classe e margine residuo
al pareggio sono non stimabili. Le lacune di [readiness.json](readiness.json)
impediscono un verdetto economico qualificato.

La 0.7 e la 0.8 finale usano gli artefatti esatti già preparati, di cui sono stati
ricontrollati digest, tag e tutte le 47 sorgenti provider per versione. Non sono
presentati come rebuild nuovi di questa campagna. Il candidato mantiene il numero
pacchetto 0.8.0: la sua identità sperimentale è il digest del prodotto/binario,
non una release 0.9.0 pubblicata. Il pilot storico con rc.1 resta separato.

La decisione è **HOLD_MEASUREMENT**. I test danno una base tecnica per una campagna
finita, ma non autorizzano nuovo investimento nel retrieval o una release basata
su risparmi. Prima occorrono un canale credenziali protetto, prove del client e degli
oracle, e l'autorizzazione richiesta dal §7.3 del piano allegato. Una nuova
configurazione autorizzata dovrà essere congelata e preparata senza sovrascrivere
questa campagna. Prove e limiti sono raccolti in [validation.json](validation.json),
[results.json](results.json) e [decision.md](decision.md).

Aggiornamento dell’executor: [prove del client e protezione delle credenziali](execution-readiness.md). Il benchmark AI resta non eseguito in attesa del budget esplicito.
