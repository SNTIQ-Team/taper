import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from build_db import reconcile_hanau
from validate import check


def test_hanau_retains_postal_and_court_places_after_the_district_change():
    db = sqlite3.connect(":memory:")
    db.executescript((ROOT / "db/schema.sql").read_text())
    db.execute("INSERT INTO land VALUES ('06', 'Hessen')")
    db.execute("INSERT INTO kreis VALUES ('06435','06','Main-Kinzig-Kreis','Landkreis','Darmstadt')")
    db.execute("""INSERT INTO gemeinde VALUES
        ('06435014','064350000014','06435','Hanau, Brüder-Grimm-Stadt','Hanau','hanau','Stadt',NULL)""")
    db.executemany("INSERT INTO gemeinde_plz VALUES ('06435014',?)", [('63450',), ('63452',)])
    db.execute("INSERT INTO jz_place VALUES ('63452','HANAU','Hanau','hanau','original',NULL,'06435014')")
    db.execute("""INSERT INTO authority (id,kind,name,name_norm,source,fetched_at)
                  VALUES (1,'jobcenter','Jobcenter Hanau','jobcenter hanau','ba','2026-06-11')""")
    db.execute("""INSERT INTO competence (authority_id,kind,level,area,rank,source,observed_on)
                  VALUES (1,'jobcenter','kreis','06415',0,'ba','2026-06-11')""")
    assert any("06415" in error for error in check(db))
    new = {"06415000": {"name": "Hanau, Brüder-Grimm-Stadt", "ars": "064150000000"}}
    reconcile_hanau(db, {})
    reconcile_hanau(db, {**new, "06435014": {"name": "Hanau"}})
    assert db.execute("SELECT ags FROM gemeinde").fetchone()[0] == "06435014"
    reconcile_hanau(db, new)
    reconcile_hanau(db, new)
    assert db.execute("SELECT ags, ars, kreis_ags FROM gemeinde").fetchall() == [
        ("06415000", "064150000000", "06415")]
    assert db.execute("SELECT ags,plz FROM gemeinde_plz ORDER BY plz").fetchall() == [
        ("06415000", "63450"), ("06415000", "63452")]
    assert db.execute("SELECT gs_key,gemeinde_ags FROM jz_place").fetchone() == ("original","06415000")
    assert not any("BA Jobcenter districts" in error for error in check(db))
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()
