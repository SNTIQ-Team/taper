"""SNTIQ platform API for the Taper resolver and Chamfer letter export.

Run with TAPER_DB set to the dataset path and uvicorn api.server:server.
"""
from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

from api.main import DB_PATH, app as taper
from api.pdf import router as chamfer_router
from api.tts import router as tts_router

SERVICE_INDEX = {
    "service": "sntiq-api",
    "operator": "SNTIQ n.e.V. — https://sntiq.com",
    "services": {
        "taper": {
            "status": "live",
            "docs": "/taper/docs",
            "endpoints": [
                "/taper/health", "/taper/version", "/taper/stats",
                "/taper/sources", "/taper/capabilities",
                "/taper/places", "/taper/graph", "/taper/matters",
                "/taper/resolve/place", "/taper/resolve/competence",
                "/taper/resolve/court", "/taper/resolve/authority",
                "/taper/authorities/{id}", "/taper/courts",
                "/taper/courts/{court_id}", "/taper/courts/lookup",
                "/taper/courts/mapping",
            ],
            "dataset": "https://github.com/SNTIQ-Team/taper",
        },
        "kerf": {
            "status": "live",
            "docs": "/kerf/docs",
            "endpoints": [
                "/kerf/acts", "/kerf/acts/{id}", "/kerf/git", "/kerf/feed",
                "/kerf/hierarchy", "/kerf/graph", "/kerf/search",
                "/kerf/decisions", "/kerf/decisions/{id}", "/kerf/digest",
                "/kerf/stats", "/kerf/health",
            ],
            "dataset": "https://github.com/SNTIQ-Team/kerf",
        },
        "chamfer": {
            "status": "live",
            "endpoints": ["/chamfer/letter"],
            "note": "stateless DIN-5008 rendering; nothing stored",
        },
        "tts": {
            "status": "live",
            "endpoints": ["/tts/speak"],
            "note": "stateless espeak-ng synthesis; nothing stored",
        },
    },
    "dataset": "https://github.com/SNTIQ-Team/taper",
}


# ---- HTML landing page (browsers only; scripts keep getting JSON) --------
# Single self-contained document: inline CSS + inline SVG, no JS, no
# external requests. Keep the numbers in sync with the dataset READMEs.

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SNTIQ API — api.sntiq.com</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #030304;
    color: #FFFFFF;
    font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  .accent-bar {
    height: 3px;
    background: linear-gradient(90deg, #0033A0, #0052FF, #0072CE);
  }
  main { max-width: 960px; margin: 0 auto; padding: 56px 24px 40px; }
  a { color: #7FA6FF; text-decoration: none; transition: color .15s ease; }
  a:hover { color: #FFFFFF; }
  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas,
                 "Liberation Mono", monospace;
  }
  header { display: flex; align-items: center; gap: 16px; margin-bottom: 28px; }
  header h1 { font-size: 1.7rem; font-weight: 700; letter-spacing: -0.02em; }
  header .host { color: #94A3B8; font-size: 0.9rem; }
  .intro { color: #94A3B8; max-width: 640px; margin-bottom: 40px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(270px, 100%), 1fr));
    gap: 20px;
  }
  .card {
    background: rgba(20, 21, 26, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: border-color .15s ease;
  }
  .card:hover { border-color: rgba(255, 255, 255, 0.18); }
  .card h2 { font-size: 1.15rem; font-weight: 600; }
  .status {
    display: flex; align-items: center; gap: 7px;
    font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.09em;
    color: #4ADE80;
  }
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #4ADE80;
    box-shadow: 0 0 6px rgba(74, 222, 128, 0.55);
  }
  .tagline { color: #94A3B8; font-size: 0.9rem; margin-top: -6px; }
  .desc { color: #94A3B8; font-size: 0.85rem; }
  .endpoints {
    list-style: none;
    font-size: 0.78rem;
    color: #CBD5E1;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 10px 14px;
    overflow-x: auto;
  }
  .endpoints li { white-space: nowrap; }
  .links {
    display: flex; flex-wrap: wrap; gap: 14px;
    margin-top: auto; font-size: 0.85rem;
  }
  footer {
    margin-top: 48px;
    padding-top: 22px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    color: #94A3B8;
    font-size: 0.85rem;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 18px;
  }
  @media (max-width: 480px) {
    main { padding: 40px 18px 32px; }
    header h1 { font-size: 1.45rem; }
  }
</style>
</head>
<body>
<div class="accent-bar"></div>
<main>
  <header>
    <img src="favicon.svg" width="44" height="44" alt="SNTIQ mark">
    <div>
      <h1>SNTIQ API</h1>
      <p class="host mono">api.sntiq.com</p>
    </div>
  </header>

  <p class="intro">Public, read-only APIs behind
    <a href="https://sntiq.com">sntiq.com</a> — infrastructure for navigating
    large bureaucratic systems.</p>

  <section class="grid">
    <article class="card">
      <div class="status"><span class="dot"></span>live</div>
      <h2>SNTIQ Taper</h2>
      <p class="tagline">German authorities, court competences &amp; EU institutions</p>
      <p class="desc">__TAPER_COUNTS__</p>
      <ul class="endpoints mono">
        <li>/taper/resolve/court</li>
        <li>/taper/resolve/authority</li>
        <li>/taper/places</li>
        <li>/taper/stats</li>
      </ul>
      <div class="links">
        <a href="/taper/docs">Interactive docs</a>
        <a href="https://github.com/SNTIQ-Team/taper">Dataset</a>
      </div>
    </article>

    <article class="card">
      <div class="status"><span class="dot"></span>live</div>
      <h2>SNTIQ Kerf</h2>
      <p class="tagline">German &amp; EU legislation as event-sourced git</p>
      <p class="desc">Laws as repositories, amendments as commits, court
        decisions linked to the norms they affect. Current corpus counts:
        <a href="/kerf/stats">/kerf/stats</a>.</p>
      <ul class="endpoints mono">
        <li>/kerf/acts</li>
        <li>/kerf/git</li>
        <li>/kerf/feed</li>
        <li>/kerf/decisions</li>
        <li>/kerf/search</li>
      </ul>
      <div class="links">
        <a href="/kerf/docs">Interactive docs</a>
        <a href="https://github.com/SNTIQ-Team/kerf">Dataset</a>
      </div>
    </article>

    <article class="card">
      <div class="status"><span class="dot"></span>live</div>
      <h2>SNTIQ Chamfer PDF</h2>
      <p class="tagline">Stateless DIN-5008 letter rendering</p>
      <p class="desc">Render a formal German letter from JSON — nothing is
        stored.</p>
      <ul class="endpoints mono">
        <li>POST /chamfer/letter</li>
      </ul>
      <div class="links">
        <a href="/docs">Interactive docs</a>
      </div>
    </article>
  </section>

  <footer>
    <span><a href="https://sntiq.com">SNTIQ n.e.V.</a></span>
    <span>Free for non-commercial use · rate-limited</span>
    <span><a href="mailto:contact@sntiq.com">contact@sntiq.com</a></span>
  </footer>
</main>
</body>
</html>
"""

server = FastAPI(
    title="SNTIQ Platform API",
    version="1.0",
    # platform-level docs describe only the composition root;
    # each mounted service keeps its own /taper/docs
    docs_url="/docs",
    redoc_url=None,
)

server.add_middleware(GZipMiddleware, minimum_size=2048)

# Browser clients: the platform web app and local development.
server.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sntiq.com",
        "https://www.sntiq.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=86400,
)


def taper_counts() -> str:
    """Counts rendered from the served dataset, never hard-coded."""
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
            nodes = one("SELECT COUNT(*) FROM authority WHERE valid_to IS NULL")
            links = one("SELECT COUNT(*) FROM court_chain")
            eu = one("SELECT COUNT(*) FROM authority WHERE valid_to IS NULL "
                     "AND kind LIKE 'eu_%'")
            built = one("SELECT value FROM build_info WHERE key='built_at'")
            try:
                courts = one("SELECT COUNT(*) FROM court WHERE status='active' "
                             "AND unit_type='court'")
            except sqlite3.Error:
                courts = None
        finally:
            conn.close()
    except sqlite3.Error:
        return "Dataset counts are currently unavailable."
    parts = [f"{nodes:,} active nodes", f"{links:,} court-chain links"]
    if courts is not None:
        parts.append(f"{courts:,} active courts with stable ids")
    parts.append(f"{eu} sourced EU institutions/bodies/courts")
    return (", ".join(parts) + f"; build {built[:10]}; current register "
            f"competence only (no historical resolution).")


@server.get("/")
def index(request: Request):
    # Content negotiation: browsers get the landing page, everything else
    # (curl, scripts, monitors) keeps getting the JSON service index.
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(INDEX_HTML.replace("__TAPER_COUNTS__",
                                              taper_counts()))
    return SERVICE_INDEX


# The real SNTIQ mark (same file the website uses), served for the landing
# page header and the browser tab icon.
_MARK = Path(__file__).resolve().parent / "sntiq-mark.svg"


@server.get("/favicon.svg", include_in_schema=False)
@server.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(_MARK, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=604800"})


@server.get("/health")
def health():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1 FROM build_info LIMIT 1")
        conn.close()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"database unavailable: {exc}")
    return {"status": "ok", "services": {"taper": "ok", "chamfer": "ok"}}


server.include_router(tts_router)
server.include_router(chamfer_router)
server.mount("/taper", taper)
