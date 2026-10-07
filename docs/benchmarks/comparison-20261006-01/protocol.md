# comparison-v1 — preregistrazione del 6 ottobre 2026

La campagna `pcg-comparison-20261006-01` verifica il candidato locale dopo la 0.8.0.
Questa revisione estende il runner esistente; non riscrive i protocolli storici.
Il prodotto, il formatter, LeanAdapter/1 e la policy del candidato sono congelati.
Sono ammessi cambiamenti agli strumenti di misurazione. Non sono autorizzati
pubblicazione, push, tag, ottimizzazioni ulteriori o modifiche al progetto originale.

## Disegno proposto e autorizzazione effettiva

| Condizione | Trattamento |
| --- | --- |
| A | Harness ordinario del progetto, strumenti ordinari; nessun grafo, schema, istruzione o cache PolyCodeGraph |
| B | v0.7.0 esatta, provider della 0.7, compact, catalogo storico completo, harness della 0.7 |
| C | v0.8.0 finale esatta, provider della 0.8, compact, agent, harness della 0.8 |
| D | Candidato locale congelato, provider della 0.8, compact, agent, proiezione e collector snelli opt-in |

Il trattamento comprende versione e integrazione. Le modifiche contemporanee non
permettono attribuzione causale a un singolo intervento. La registrazione di tool
nel vero Codex e il collegamento del collector D a quel client rimangono da provare:
il controllo nativo non sostituisce questa prova. Il catalogo storico B non riceve
il flag `tool_profile` della 0.8; i metadati MCP non supportati richiedono soltanto
normalizzazione dell'envelope, senza modifica degli argomenti semantici.

Corpus: sei task reali già noti, uno per modifica locale, rename ambiguo, firma
pubblica, bug da sintomo, trace e review. Riutilizzare gli snapshot iniziali non
riutilizza risultati o soluzioni precedenti; questi task sono screening, non holdout.
I prompt, il codice, gli oracle e le dipendenze restano nella directory ignorata.
Due repliche proposte per task e quattro condizioni: 24 celle P2a e altre 24 P2b.
L'ordine è congelato in `schedule.json`, seed 20261006, sequenze Williams
ABDC / BCAD / CDBA / DACB, tre occorrenze ciascuna su dodici blocchi.
P2a da sola mantiene uno sbilanciamento residuo, documentato nello schedule.
Parallelismo uno; un tentativo esterno per cella. Tutte le classi hanno uguale peso.

**Autorizzazione AI attuale: assente.** `execution_enabled=false`, fasi approvate
vuote, budget complessivo e massimo run null, modello/effort da scegliere.
P0 non usa modelli. P1, al massimo quattro smoke brevi, necessita di un budget di
preparazione separato. P2a/P2b e l'eventuale P3 richiedono autorizzazione esplicita.
P3 avrebbe dodici task nuovi e due repliche A/D, con un manifest separato.
La preparazione delle 48 copie non autorizza la loro esecuzione.

Limiti proposti uguali per tutti: 1200 secondi, 40 richieste modello, 120000 input
non cached, 2000000 input totale, 30000 output per tentativo. Il timeout esterno
è applicato dal runner; i limiti token/richieste sono `observed_only`, verificabili
all'uscita. Il budget deve accettare esplicitamente questa granularità e il possibile
superamento durante un tentativo. Nessuna garanzia di cap per richiesta.
Il runner riserva il cap del prossimo tentativo prima di partire e interrompe
su usage ignoto, timeout, errore di misura o limite osservato superato.
Giudici AI: zero. Retry di rete interni, errori e recuperi restano nel costo.
Un tentativo started interrotto non viene rilanciato da resume: rimane un costo
ignoto e ferma la campagna. Nuovi tentativi o sostituzioni richiedono una nuova
politica preregistrata, conservando il costo dell'originale.

## Metrica e contabilità

Primaria: somma dell'input non cached di **tutti** i tentativi / celle accettate.
Con zero accettazioni è indefinita. Riportare anche successi/celle eseguite e
consumo/cella eseguita; le celle not_started non entrano in questi denominatori.
Input totale, cached, cache write quando esposto, output, reasoning, richieste,
durata solver e durata oracle restano distinti. Reasoning è un sottoinsieme
dell'output; cache è un sottoinsieme dell'input quando lo specifica il provider.
Campi sconosciuti restano null. Una cache write OpenAI assente non diventa zero.
Non stimare prezzi o quote di abbonamento. Denaro solo con costo dell'intero
attempt verificato, stessa valuta e identità/pricing del modello affidabili.

Riutilizzare `efficiency_usage.py` e `token_usage.py`, senza modificarne i parser
storici. Request ID duplicati identici vengono deduplicati, conflitti rifiutati;
cumulativi, delta e reset devono coincidere. Non sommare turn usage e cumulativi.
Per subagent accettare un totale parent esplicitamente inclusivo, oppure stream
con request ID disgiunti e verificabili: mai entrambi come costi additivi.
I contatori client distinguono `graph_mcp_calls`, `other_mcp_calls`, `all_tool_calls`.
A può usare MCP ordinari; qualsiasi superficie o chiamata PolyCodeGraph contamina A.

Il client `exec --json` documenta un flusso di eventi: questo, da solo, non prova
che ogni contatore per turno rappresenti una richiesta indipendente. La fonte
contabile scelta deve essere registrata e verificata con lo smoke reale.
[Documentazione ufficiale Codex](https://learn.chatgpt.com/docs/non-interactive-mode).
La cache del prompt è osservata e non dichiarata fredda per effetto di una nuova
sessione. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
Grafo cold per run; contesto client fresco; prefissi stabili senza nonce artificiali.

## Isolamento e correttezza

Copie iniziali identiche per cella, snapshot root trusted, nessun symlink/traversal.
Il solver vede soltanto il proprio workspace, SDK/dipendenze preparate e trattamento.
Oracle, manifest trusted, altre celle, log e risposte precedenti sono esclusi.
I probe devono verificare accessi diretti e alias tramite proc; un worktree non basta.
Credenziali tramite un canale client separato dai tool del solver. Il vecchio
executor con auth copiata nel suo home non supera questo requisito: P0 lo riproduce
con una sentinella fittizia e non legge/copia una credenziale reale.

Oracle indipendenti: test/static analysis e verifica patch per le modifiche;
rubriche congelate e confronto col sorgente per trace/review. La preparazione
conserva le ricette storiche, ma la loro esecuzione nel nuovo ambiente e l'assenza
di divulgazione delle risposte vanno verificate prima del lancio. La review usa
lo stesso stato prima/dopo in tutte le condizioni, incluso il working tree iniziale.
Nessuna esecuzione di hook, plugin o codice applicativo dentro l'indicizzatore.

## Analisi e checkpoint

Confronti registrati: D/A, D/C, D/B, C/A, B/A, C/B, per classe e mix.
Rapporti dalle somme e accettazioni, non media delle percentuali dei task.
Bootstrap esplorativo appaiato per **task**, 2000 ricampionamenti, seed 20261006:
conserva tutte le condizioni e repliche del task; intervalli percentile 95% e 90%.
Un ricampionamento con zero accettazioni rende l'intervallo instabile/non stimabile;
non viene scartato per produrre un intervallo favorevole. Una run ignota impedisce
una conclusione qualificata; è ammesso un subtotale osservato chiaramente etichettato.
Le repliche non sono task/repository indipendenti. Un task per classe non dimostra
un beneficio generale. Nessuna esclusione di outlier dopo averne osservato l'esito.

Qualità, costo e attribuzione sono assi separati. Telemetria diagnostica incompleta
limita la spiegazione, senza annullare automaticamente consumo altrimenti affidabile.
Identità, usage, isolamento o oracle insufficienti: HOLD_MEASUREMENT.
Qualità peggiore o D/C >1.10: allarme REGRESSION nello screening.
D/C <=0.85 con qualità comparabile ma D/A >1.05: PROGRESS_NOT_COMPETITIVE.
D/A 0.95–1.05 senza equivalenza dimostrata: NEAR_PARITY_UNCERTAIN.
D/A locale >1.10 è un allarme separato. Il runner di screening non emette conferme
holdout, equivalenza o vantaggio universale; un risultato descrittivo inconcludente
non autorizza automaticamente altro sviluppo.

Soglie per una futura preregistrazione holdout: equivalenza solo con intervallo
90% interamente entro 0.95–1.05; CONTINUE_CONFIRMED solo con limite superiore 95%
inferiore a 1 e guardrail qualità; target forte stima <=0.80 con intervallo dichiarato.
Un uso selettivo deve essere confermato su task nuovi della classe dichiarata.
Uno svantaggio stabile e materiale senza beneficio di qualità/segmento motiva
STOP_TOKEN_SAVINGS, senza affermare impossibilità di ogni algoritmo futuro.
Al massimo un ciclo diagnostico aggiuntivo, con domanda osservabile e budget nuovo.

## Operatività e rollback

La revisione è selezionata da `protocol_revision: comparison-v1`; le revisioni
storiche e `post08-v1` seguono i percorsi precedenti. `check`, `prepare`, `evaluate`
vuoto sono consentiti senza AI. `run` rifiuta manifest non autorizzati o incompleti.
`prepare` rifiuta sovrascritture; `run` verifica fingerprint di manifest, richieste,
ordine e artefatti prima di ogni tentativo, usa lock seriale e journal append-only.
Resume prosegue solo celle non iniziate di una campagna sana e identica.
Un manifest autorizzato successivo richiede nuove copie preparate, senza alterare
le copie di questa preregistrazione. Nessun executor reale viene abilitato da P0.

Il profilo del prodotto 0.8 resta disponibile; non promuovere lean a default.
Per rollback del solo runner scegliere il protocollo precedente senza cancellare
log, cache, sorgenti, stash o campagne. Provider e binari storici rimangono separati.
EOF, cancellation, consistenza delle generazioni, budget e provenance del sorgente
sono verificati nelle suite tecniche; il client Codex resta un gate aggiuntivo.
