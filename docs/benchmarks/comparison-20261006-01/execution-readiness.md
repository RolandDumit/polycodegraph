# Executor reale pronto, benchmark AI in attesa del budget

Il 6 ottobre 2026 è stato corretto l'isolamento delle credenziali del banco di prova.
Il client Codex 0.159.2 usa un home protetto separato dal workspace del solver;
i suoi strumenti non possono leggere quel home né gli alias verificati tramite proc.
Le prove usano una sentinella fittizia, inclusa nel percorso delle credenziali:
non sono state copiate credenziali reali e non è stata invocata alcuna AI.
Il comando eseguito dal vero app-server conferma i divieti.

Il client registra A=0, B=16, C=5, D=5 tool del grafo. Ogni campo degli schemi
registrati coincide con quello del server congelato. Le chiamate native ordinarie,
l'intent avanzato e l'errore per nome inesistente passano. La binding di D applica
LeanAdapter/1 e inoltra un solo testo per l'intent, senza structuredContent duplicato.
La verifica di un'effettiva chiamata del modello resta in P1; l'inserimento preciso
nel prompt del provider non è esposto da questi controlli.

L'oracle indipendente accetta la modifica locale corretta e respinge il sorgente
non modificato; quattro controlli in entrambe le prove. Trace e review hanno una
policy di adjudication basata sul sorgente, congelata prima delle esecuzioni.
I 35 test Python passano, compreso il rifiuto di usage parziale dopo interruzione.
Il candidato e i suoi provider sono rimasti invariati.

## Budget proposto, non ancora approvato

- P1: al massimo quattro smoke, uno per condizione; P2a: 24 task, sei classi × quattro condizioni × una replica.
- Complessivo: massimo 28 run e soglia 3.500.000 input non cached, con controllo all'uscita di ogni run e possibile superamento nell'ultima.
- Stesso modello gpt-6.1-sol, effort high; nessun giudice AI e nessun retry esterno.
- P2b, holdout ed espansioni non inclusi. In alternativa: soltanto quattro smoke, soglia 100.000 input non cached.

La richiesta di scelta è pendente. Il §7.3 del piano allegato richiede un budget
complessivo scelto esplicitamente e approvazione della granularità effettiva.
Il manifest aggiornato continua a rifiutare il lancio finché mancano quei valori.

**Run AI: non eseguite. Token del provider: non misurati, valori null.**
Le chiamate locali al client/server senza modello non sono task AI e non producono
contatori di consumo del provider. Nessuna dichiarazione di risparmio economico.

Prove aggregate: [execution-preflight.json](execution-preflight.json).
I raw, le configurazioni e gli script di esecuzione restano nella directory ignorata.
