# SNTIQ Taper

Which court handles a civil claim in Berlin? Which office takes a benefit application in Erding? Taper looks up the place, the matter and the authority in German public registers. Each answer includes its source and the dataset snapshot used for the lookup.

## Look up a court

For postal code `10115` in Berlin, the register lists Amtsgericht Mitte for ordinary civil claims. For a payment order (`Mahnverfahren`) at the same address, it lists Amtsgericht Wedding, the central payment order court for Berlin and Brandenburg.

```sh
curl 'https://api.sntiq.com/taper/resolve/court?plz=10115&ortk=BERLIN&matter=zivil'
curl 'https://api.sntiq.com/taper/resolve/court?plz=10115&ortk=BERLIN&matter=mahn'
```

A court answer includes the chain of instances, the role of each entry and its filing address. Some postal codes span several court districts. When the locality is ambiguous, the resolver returns candidates with stable place identifiers. Public reads require no API key. [API explorer](https://api.sntiq.com/taper/docs) · [SQL, Python and HTTP examples](examples/README.md)

## Coverage

| Records | What they describe |
| --- | --- |
| Courts | Register assignments by postal code, locality and legal matter. Court identifiers use the XJustiz code list. |
| Administrative offices | Municipal and district assignments for offices including Jobcenter, immigration offices and social welfare offices. Rank 0 identifies the filing office. Higher ranks identify supervisory offices. |
| Bavarian departments | Organisational links and contacts down to department level where the BayernPortal publishes them. |
| EU institutions | Eleven institutions and bodies, with sourced relations for judicial review, appeals, financial audit and other defined procedures. Each relation records its scope. |

The public resolver answers for its current register snapshot. `GET /taper/version` identifies that snapshot and its source dates. `GET /taper/capabilities` lists supported operations and arguments. Warnings in a result can apply to a place, an authority, a matter or an individual assignment. The combined research endpoint pairs a Taper resolution with a legal text or search from SNTIQ Kerf. [API contract](docs/API.md)

## Use the SQLite release

From a checkout of this repository, download the database and its checksum. The checksum file names `atlas.sqlite` relative to the download directory.

```sh
mkdir -p data
gh release download --repo SNTIQ-Team/taper --pattern 'atlas.sqlite*' --dir data
(cd data && sha256sum -c atlas.sqlite.sha256)
sqlite3 -readonly data/atlas.sqlite
```

Each release also contains a validation report, coverage counts and the dates of its source snapshots. The Hugging Face dataset publishes JSONL tables. [GitHub releases](https://github.com/SNTIQ-Team/taper/releases) · [Hugging Face dataset](https://huggingface.co/datasets/SNTIQ-Team/taper)

## Build from sources

The pipeline keeps dated snapshots of each source. It applies reviewed corrections during the database build and validates the result before replacing `data/atlas.db`. The core harvest covers postal geography, the court register, PVOG and the federal Jobcenter register. Further source loaders cover Bavarian departments, XJustiz identities and the EU institutions. [Source registry](pipeline/sources.yaml) · [Source notes](docs/SOURCES.md) · [Correction files](pipeline/overrides/README.md)

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
bash pipeline/run_full.sh
uvicorn api.server:server --host 127.0.0.1 --port 8001
```

The local resolver listens under `http://127.0.0.1:8001/taper`. The SQL schema describes places, authority assignments, court chains and their evidence. [Database schema](db/schema.sql) · [Architecture](docs/ARCHITECTURE.md)

## Reuse and citation

SNTIQ licenses its code under Apache 2.0 and its original documentation and annotations under CC BY 4.0. Both allow commercial use. Imported register records, OpenPLZ geography and bundled fonts have their own terms. [Licensing and source attribution](LICENSING.md) · [Citation](CITATION.cff)
