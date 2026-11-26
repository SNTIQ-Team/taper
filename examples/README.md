# Taper query examples

The SQL examples use the SQLite file from a Taper release. From the repository root, open it with `sqlite3 -readonly data/atlas.sqlite`. The Python example uses the same file. [Download instructions](../README.md#use-the-sqlite-release)

## SQL

### Civil claim court chain at Berlin 10115

```sql
SELECT cc.position, cc.role, a.name, e.value AS xjustiz_id,
       a.street, a.postal_address, a.erv_note
FROM court_chain cc
JOIN authority a ON a.id = cc.authority_id
LEFT JOIN authority_external_id e
       ON e.authority_id = a.id AND e.scheme = 'xjustiz'
WHERE cc.plz = '10115' AND cc.ortk = 'BERLIN' AND cc.matter = 'zivil'
ORDER BY cc.role DESC, cc.position;
-- 1. Amtsgericht Mitte (F1112) -> 2. Landgericht Berlin II (F6529)
-- -> 3. Kammergericht (F1000), plus Staatsanwaltschaft entries
```

### Dunning procedure (Mahnverfahren) at Berlin 10115

```sql
SELECT a.name
FROM court_chain cc
JOIN authority a ON a.id = cc.authority_id
WHERE cc.plz = '10115' AND cc.ortk = 'BERLIN'
  AND cc.matter = 'mahn' AND cc.role = 'court';
-- Amtsgericht Wedding (Zentrales Mahngericht Berlin-Brandenburg)
-- Competence depends on both legal matter and place.
```

### Multiple localities within postal code 02923

```sql
SELECT jp.ort, a.name AS amtsgericht
FROM jz_place jp
JOIN court_chain cc ON cc.plz = jp.plz AND cc.ortk = jp.ortk
     AND cc.matter = 'zivil' AND cc.role = 'court' AND cc.position = 1
JOIN authority a ON a.id = cc.authority_id
WHERE jp.plz = '02923';
-- Hähnichen resolves to Amtsgericht Weißwasser. Horka and Kodersdorf resolve to Amtsgericht Görlitz.
```

### AsylbLG office and supervisory body for Landkreis Erding

```sql
SELECT c.rank, a.name, a.email, a.web
FROM competence c
JOIN authority a ON a.id = c.authority_id
WHERE c.kind = 'asylblg_behoerde'
  AND ((c.level = 'kreis' AND c.area = '09177')
       OR (c.level = 'gemeinde' AND c.area = '09177117'))
  AND a.valid_to IS NULL
ORDER BY c.rank;
-- rank 0: Landratsamt Erding - Fachbereich 24 - Asylmanagement
-- rank 1: Regierung von Oberbayern - SG 14.1 (supervisory)
```

### Organisational parent chain in Bavaria

```sql
WITH RECURSIVE up(id, name, lvl) AS (
  SELECT id, name, 0 FROM authority
  WHERE name LIKE '%Fachbereich 24 - Asylmanagement%' AND valid_to IS NULL
  UNION ALL
  SELECT a.id, a.name, up.lvl + 1
  FROM up
  JOIN authority_edge e ON e.from_authority = up.id
       AND e.relation = 'parent'
  JOIN authority a ON a.id = e.to_authority
  WHERE up.lvl < 6
)
SELECT printf('%.*c↑ ', lvl + 1, ' ') || name FROM up;
-- Fachbereich 24 ↑ Abteilung 2 - Jugend und Soziales ↑ Landratsamt Erding
```

### Jobcenter legal forms (`gE` and `zkT`)

```sql
SELECT legal_form, COUNT(*) FROM authority
WHERE kind = 'jobcenter' AND valid_to IS NULL
GROUP BY legal_form;
```

### Caveats for a municipality, district, or court place

```sql
SELECT severity, text_de FROM caveat
WHERE (scope_level = 'gemeinde' AND scope_key = :ags)
   OR (scope_level = 'kreis'    AND scope_key = substr(:ags, 1, 5))
   OR (scope_level = 'jz_place' AND scope_key = :plz || '|' || :ortk);
```

## Python

```python
import sqlite3

db = sqlite3.connect("file:data/atlas.sqlite?mode=ro", uri=True)
db.row_factory = sqlite3.Row


def court_chain(plz: str, ortk: str, matter: str) -> list[dict]:
    """Return the full instance chain for a place and legal matter."""
    rows = db.execute(
        """
        SELECT cc.position, cc.role, a.name, a.street, a.postal_address,
               a.phone, a.email, a.erv_note
        FROM court_chain cc
        JOIN authority a ON a.id = cc.authority_id
        WHERE cc.plz = ? AND cc.ortk = ? AND cc.matter = ?
        ORDER BY cc.role DESC, cc.position
        """,
        (plz, ortk, matter),
    )
    return [dict(r) for r in rows]


for step in court_chain("86720", "NOERDLINGEN", "insolv"):
    print(step["position"], step["role"], step["name"], "|", step["street"])
# Insolvenzgericht departments often file at a separate address from the
# parent Amtsgericht, so Taper stores them as separate records.
```

## HTTP

The public resolver accepts a postal code, locality code and legal matter. The result for a civil claim at Berlin 10115 includes a court chain, its source and the current snapshot identifier.

```sh
curl 'https://api.sntiq.com/taper/resolve/court?plz=10115&ortk=BERLIN&matter=zivil'
curl 'https://api.sntiq.com/taper/resolve/authority?ags=09177117&kind=asylblg_behoerde'
```

To query a local build, run `uvicorn api.server:server --port 8001` with a current database and send the same requests to `http://127.0.0.1:8001/taper`. [API contract](../docs/API.md)
