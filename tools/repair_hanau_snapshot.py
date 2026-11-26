"""Build a corrected copy of a schema-v2 Taper release, retaining public authority IDs."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import validate
from build_db import BA_REGISTER_URL, now, reconcile_hanau
from common import read_jsonl

FORMER_BA_URL = "https://statistik.arbeitsagentur.de/ Gebietsstruktur Grundsicherungstraeger"


def repair(source: Path, destatis_dir: Path, output: Path):
    municipalities = {g["ags"]: g for g in read_jsonl(destatis_dir / "gemeinden.jsonl")}
    if "06435014" in municipalities or municipalities.get("06415000", {}).get("ars") != "064150000000":
        raise ValueError("the supplied Destatis register does not confirm Hanau's current key")
    if source.resolve() == output.resolve() or output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as staging:
        candidate = Path(staging) / "atlas.db"
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original, \
             closing(sqlite3.connect(candidate)) as db:
            original.backup(db)
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                reconcile_hanau(db, municipalities)
                for table in ("authority", "competence"):
                    db.execute(f"UPDATE {table} SET source_url=? WHERE source='ba' AND source_url=?",
                               (BA_REGISTER_URL, FORMER_BA_URL))
                row = db.execute("SELECT ars, kreis_ags FROM gemeinde WHERE ags='06415000'").fetchone()
                if row != ("064150000000", "06415"):
                    raise ValueError("the source snapshot does not contain Hanau")
                db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
                snapshots = json.loads(db.execute("SELECT value FROM build_info WHERE key='snapshots'").fetchone()[0])
                snapshots["destatis"] = destatis_dir.name
                db.execute("UPDATE build_info SET value=? WHERE key='snapshots'", (json.dumps(snapshots),))
                db.execute("UPDATE build_info SET value=? WHERE key='built_at'", (now(),))
                errors = validate.check(db)
                if errors or db.execute("PRAGMA foreign_key_check").fetchall() or db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError(f"corrected snapshot failed validation: {errors}")
        # Atomic publication without replacing a file another invocation completed.
        output.hardlink_to(candidate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destatis_snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repair(args.source, args.destatis_snapshot, args.output)
