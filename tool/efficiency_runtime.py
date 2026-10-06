"""Isolated SQLite edge-file update experiment; runtime cost, never model usage."""
import argparse
import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path


def experiment(edges=100000, iterations=31):
    results={}
    with tempfile.TemporaryDirectory(prefix='pcg sqlite update ') as temp:
        for indexed in (False,True):
            path=Path(temp)/f'{indexed}.sqlite';db=sqlite3.connect(path)
            db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
            db.executescript('CREATE TABLE edges(key TEXT PRIMARY KEY, source TEXT,target TEXT,kind TEXT,file TEXT,record TEXT);CREATE INDEX edge_source ON edges(source,kind);CREATE INDEX edge_target ON edges(target,kind);')
            if indexed:db.execute('CREATE INDEX edge_file ON edges(file)')
            rows=[(str(i),f'n{i}',f'n{i+1}','calls',f'f{i%1000}.ts','{}') for i in range(edges)]
            started=time.perf_counter();db.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?)',rows);db.commit();write_ms=(time.perf_counter()-started)*1000
            plan=[row[3] for row in db.execute('EXPLAIN QUERY PLAN DELETE FROM edges WHERE file=?',('f1.ts',))]
            durations=[]
            for i in range(iterations):
                file=f'f{i}.ts';subset=[r for r in rows if r[4]==file]
                started=time.perf_counter();db.execute('DELETE FROM edges WHERE file=?',(file,));db.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?)',subset);db.commit();durations.append((time.perf_counter()-started)*1000)
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.close()
            durations.sort();results['indexed' if indexed else 'scan']=dict(plan=plan,initial_write_ms=write_ms,update_p50_ms=statistics.median(durations),update_p95_ms=durations[int((len(durations)-1)*.95)],database_bytes=path.stat().st_size,iterations=iterations)
    return dict(scope='synthetic normalized edges: DELETE+reinsert+FULL commit; not whole index or AI task cost',edges=edges,sqlite_version=sqlite3.sqlite_version,results=results)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--edges',type=int,default=100000);a=p.parse_args()
    a.output.write_text(json.dumps(experiment(a.edges),indent=2)+'\n')
