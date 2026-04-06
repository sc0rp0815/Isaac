"""
Isaac – Multi-Engine Suche
============================
Fünf Suchmaschinen gleichzeitig, parallel, gecacht.

Engines:
  1. DuckDuckGo Instant Answer  (kostenlos, kein Key)
  2. DuckDuckGo HTML            (Scraping-Fallback)
  3. Brave Search API           (kostenlos-Tier, 2000/Monat)
  4. Wikipedia DE + EN          (Fakten, Hintergrund)
  5. SearXNG                    (Self-hosted oder Public Instanzen)
  6. Reddit via Pullpush        (Community-Wissen)
  7. arXiv                      (Wissenschaft)
  8. GitHub Search              (Code, Projekte)

Alle Ergebnisse werden:
  - Dedupliziert (gleiche URLs entfernt)
  - Nach Relevanz sortiert
  - Auf Wunsch als Volltext geladen (URL-Fetcher)
  - Im Cache gehalten (5 Minuten)
"""

import asyncio
import aiohttp
import hashlib
import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urljoin

from config  import get_config, DATA_DIR
from audit   import AuditLog

log = logging.getLogger("Isaac.Search")

# Public SearXNG Instanzen (Fallback wenn eigene nicht verfügbar)
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.mdosch.de",
    "https://searxng.world",
    "https://searx.tiekoetter.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/json,*/*",
}


# ── Ergebnis-Typen ────────────────────────────────────────────────────────────
@dataclass
class SearchHit:
    titel:   str
    snippet: str
    url:     str
    quelle:  str
    score:   float = 1.0   # Relevanz-Score
    volltext: str  = ""    # Wenn URL geladen

    def kurz(self) -> str:
        return f"[{self.quelle}] {self.titel}\n{self.snippet[:200]}\n→ {self.url}"


@dataclass
class MultiSearchResult:
    query:    str
    hits:     list[SearchHit] = field(default_factory=list)
    abstract: str  = ""
    quellen:  list[str] = field(default_factory=list)
    dauer:    float = 0.0
    fehler:   list[str] = field(default_factory=list)

    def als_kontext(self, max_hits: int = 8) -> str:
        teile = []
        if self.abstract:
            teile.append(f"[Direktantwort]\n{self.abstract}")
        for i, h in enumerate(self.hits[:max_hits], 1):
            teile.append(
                f"[{i}] {h.titel} ({h.quelle})\n"
                f"{h.snippet[:250]}\n"
                f"Quelle: {h.url}"
            )
        return "\n\n".join(teile)

    def dedupliziert(self) -> "MultiSearchResult":
        seen_urls = set()
        seen_snip = set()
        unique = []
        for h in self.hits:
            url_key  = re.sub(r'[?#].*', '', h.url)
            snip_key = h.snippet[:60].strip().lower()
            if url_key not in seen_urls and snip_key not in seen_snip:
                seen_urls.add(url_key)
                seen_snip.add(snip_key)
                unique.append(h)
        self.hits = unique
        return self


# ── Cache ─────────────────────────────────────────────────────────────────────
class SearchCache:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl; self._c: dict = {}

    def key(self, q: str) -> str:
        return hashlib.md5(q.lower().strip().encode()).hexdigest()

    def get(self, q: str) -> Optional[MultiSearchResult]:
        e = self._c.get(self.key(q))
        return e[1] if e and time.time() - e[0] < self.ttl else None

    def set(self, q: str, r: MultiSearchResult):
        self._c[self.key(q)] = (time.time(), r)
        now = time.time()
        self._c = {k: v for k, v in self._c.items()
                   if now - v[0] < self.ttl * 2}


# ── Multi-Engine Suche ────────────────────────────────────────────────────────
class MultiSearch:
    """
    Parallele Suche über alle konfigurierten Engines.
    Ergebnisse werden zusammengeführt, dedupliziert und sortiert.
    """

    def __init__(self):
        self.cache    = SearchCache()
        self._session: Optional[aiohttp.ClientSession] = None
        self._brave_key = __import__('os').getenv("BRAVE_API_KEY", "")
        log.info(
            f"MultiSearch online │ Brave: {'ja' if self._brave_key else 'nein'}"
        )

    async def _sess(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Haupt-Suche ────────────────────────────────────────────────────────────
    async def search(self, query: str,
                     max_hits:      int  = 10,
                     load_fulltext: bool = False,
                     engines:       Optional[list] = None) -> MultiSearchResult:
        """
        Parallele Suche. Gibt zusammengeführtes Ergebnis zurück.
        """
        cached = self.cache.get(query)
        if cached:
            log.debug(f"[Cache] {query[:40]}")
            return cached

        t0     = time.monotonic()
        result = MultiSearchResult(query=query)

        # Engine-Auswahl
        aktive = engines or ["ddg", "wikipedia", "searxng", "brave",
                              "reddit", "arxiv"]

        # Alle Engines parallel anfragen
        tasks = {}
        if "ddg"       in aktive: tasks["ddg"]        = self._ddg(query)
        if "brave"     in aktive: tasks["brave"]       = self._brave(query)
        if "wikipedia" in aktive: tasks["wikipedia"]   = self._wikipedia(query)
        if "searxng"   in aktive: tasks["searxng"]     = self._searxng(query)
        if "reddit"    in aktive: tasks["reddit"]      = self._reddit(query)
        if "arxiv"     in aktive: tasks["arxiv"]       = self._arxiv(query)
        if "github"    in aktive: tasks["github"]      = self._github(query)

        engine_results = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        for engine, res in zip(tasks.keys(), engine_results):
            if isinstance(res, Exception):
                result.fehler.append(f"{engine}: {str(res)[:60]}")
                log.debug(f"Engine {engine} Fehler: {res}")
                continue
            if isinstance(res, tuple):
                hits, abstract = res
                result.hits.extend(hits)
                result.quellen.append(engine)
                if abstract and not result.abstract:
                    result.abstract = abstract
            elif isinstance(res, list):
                result.hits.extend(res)
                result.quellen.append(engine)

        # Deduplizieren + Sortieren
        result.dedupliziert()
        result.hits = sorted(
            result.hits,
            key=lambda h: (h.score, len(h.snippet)),
            reverse=True
        )[:max_hits]

        # Optional: Volltext laden
        if load_fulltext and result.hits:
            await self._load_volltexte(result.hits[:3])

        result.dauer = round(time.monotonic() - t0, 2)
        AuditLog.internet(
            "Search", f"multi:{query[:50]}",
            len(result.hits)
        )
        log.info(
            f"Suche '{query[:40]}' → {len(result.hits)} Hits "
            f"aus {result.quellen} ({result.dauer}s)"
        )

        self.cache.set(query, result)
        return result

    # ── DuckDuckGo ────────────────────────────────────────────────────────────
    async def _ddg(self, query: str) -> tuple[list[SearchHit], str]:
        hits = []
        abstract = ""

        # Instant Answer
        try:
            sess = await self._sess()
            async with sess.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json",
                        "no_html": "1", "skip_disambig": "1"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data = await r.json(content_type=None)
                    abstract = data.get("AbstractText", "")
                    for topic in data.get("RelatedTopics", [])[:6]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            hits.append(SearchHit(
                                titel   = topic["Text"][:80],
                                snippet = topic["Text"][:300],
                                url     = topic.get("FirstURL", ""),
                                quelle  = "ddg",
                                score   = 1.0,
                            ))
        except Exception as e:
            log.debug(f"DDG-IA: {e}")

        # HTML wenn leer
        if not hits:
            try:
                sess = await self._sess()
                async with sess.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "kl": "de-de"},
                    headers={**HEADERS, "Content-Type":
                             "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        html = await r.text()
                        hits.extend(self._parse_ddg_html(html))
            except Exception as e:
                log.debug(f"DDG-HTML: {e}")

        return hits, abstract

    def _parse_ddg_html(self, html: str) -> list[SearchHit]:
        hits = []
        urls = re.findall(
            r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        snips = re.findall(
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for i, (url, title) in enumerate(urls[:8]):
            t = re.sub(r'<[^>]+>', '', title).strip()
            s = re.sub(r'<[^>]+>', '',
                       snips[i] if i < len(snips) else "").strip()
            hits.append(SearchHit(
                titel=t[:100], snippet=s[:300],
                url=url, quelle="ddg", score=1.0
            ))
        return hits

    # ── Brave Search ──────────────────────────────────────────────────────────
    async def _brave(self, query: str) -> tuple[list[SearchHit], str]:
        if not self._brave_key:
            return [], ""
        try:
            sess = await self._sess()
            async with sess.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json",
                         "Accept-Encoding": "gzip",
                         "X-Subscription-Token": self._brave_key},
                params={"q": query, "count": 8,
                        "country": "DE", "search_lang": "de"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return [], ""
                data = await r.json()

            hits = []
            for w in data.get("web", {}).get("results", [])[:8]:
                hits.append(SearchHit(
                    titel   = w.get("title", "")[:100],
                    snippet = w.get("description", "")[:300],
                    url     = w.get("url", ""),
                    quelle  = "brave",
                    score   = 1.2,  # Brave-Ergebnisse leicht bevorzugt
                ))
            abstract = data.get("query", {}).get("spellcheck_off", "")
            return hits, ""
        except Exception as e:
            log.debug(f"Brave: {e}")
            return [], ""

    # ── Wikipedia ─────────────────────────────────────────────────────────────
    async def _wikipedia(self, query: str) -> tuple[list[SearchHit], str]:
        hits = []
        abstract = ""
        for lang, base in [("de", "de.wikipedia.org"),
                            ("en", "en.wikipedia.org")]:
            try:
                sess = await self._sess()
                async with sess.get(
                    f"https://{base}/w/api.php",
                    params={"action": "query", "list": "search",
                            "srsearch": query, "format": "json",
                            "srlimit": 4, "srprop": "snippet"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()

                for item in data.get("query", {}).get("search", []):
                    s = re.sub(r'<[^>]+>', '', item.get("snippet", ""))
                    t = item.get("title", "")
                    hits.append(SearchHit(
                        titel   = t,
                        snippet = s[:300],
                        url     = f"https://{base}/wiki/{quote_plus(t)}",
                        quelle  = f"wikipedia_{lang}",
                        score   = 1.3,   # Wikipedia bevorzugt
                    ))
                    if not abstract and lang == "de":
                        abstract = await self._wiki_extract(t, base)
            except Exception as e:
                log.debug(f"Wikipedia {lang}: {e}")
        return hits, abstract

    async def _wiki_extract(self, title: str, base: str) -> str:
        try:
            sess = await self._sess()
            async with sess.get(
                f"https://{base}/w/api.php",
                params={"action": "query", "prop": "extracts",
                        "exintro": True, "explaintext": True,
                        "titles": title, "format": "json",
                        "exsentences": 5},
                timeout=aiohttp.ClientTimeout(total=6)
            ) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
            for page in data.get("query", {}).get("pages", {}).values():
                return page.get("extract", "")[:600].strip()
        except Exception:
            pass
        return ""

    # ── SearXNG ───────────────────────────────────────────────────────────────
    async def _searxng(self, query: str) -> tuple[list[SearchHit], str]:
        """Probiert mehrere SearXNG-Instanzen bis eine antwortet."""
        own_url = __import__('os').getenv("SEARXNG_URL", "")
        instanzen = ([own_url] if own_url else []) + SEARXNG_INSTANCES

        for base in instanzen:
            try:
                sess = await self._sess()
                async with sess.get(
                    f"{base}/search",
                    params={"q": query, "format": "json",
                            "lang": "de", "categories": "general"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)

                hits = []
                for item in data.get("results", [])[:8]:
                    hits.append(SearchHit(
                        titel   = item.get("title", "")[:100],
                        snippet = item.get("content", "")[:300],
                        url     = item.get("url", ""),
                        quelle  = "searxng",
                        score   = 1.1,
                    ))
                return hits, data.get("infoboxes", [{}])[0].get("content", "")
            except Exception:
                continue
        return [], ""

    # ── Reddit ────────────────────────────────────────────────────────────────
    async def _reddit(self, query: str) -> tuple[list[SearchHit], str]:
        try:
            sess = await self._sess()
            async with sess.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "limit": 5, "type": "link"},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return [], ""
                data = await r.json()

            hits = []
            for post in data.get("data", {}).get("children", [])[:5]:
                p = post.get("data", {})
                hits.append(SearchHit(
                    titel   = p.get("title", "")[:100],
                    snippet = (p.get("selftext", "") or
                               p.get("url", ""))[:250],
                    url     = f"https://reddit.com{p.get('permalink', '')}",
                    quelle  = "reddit",
                    score   = 0.8,
                ))
            return hits, ""
        except Exception as e:
            log.debug(f"Reddit: {e}")
            return [], ""

    # ── arXiv ─────────────────────────────────────────────────────────────────
    async def _arxiv(self, query: str) -> tuple[list[SearchHit], str]:
        # Nur für wissenschaftliche Begriffe sinnvoll
        wissenschaft = any(w in query.lower() for w in [
            "studie", "forschung", "paper", "algorithm", "neural",
            "machine learning", "ai", "model", "theory", "analyse"
        ])
        if not wissenschaft:
            return [], ""
        try:
            sess = await self._sess()
            async with sess.get(
                "https://export.arxiv.org/api/query",
                params={"search_query": f"all:{query}",
                        "max_results": 4, "sortBy": "relevance"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status != 200:
                    return [], ""
                xml = await r.text()

            hits = []
            entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
            for e in entries[:4]:
                title = re.search(r'<title>(.*?)</title>', e)
                summ  = re.search(r'<summary>(.*?)</summary>', e, re.DOTALL)
                link  = re.search(r'<id>(.*?)</id>', e)
                if title and summ:
                    hits.append(SearchHit(
                        titel   = title.group(1).strip()[:100],
                        snippet = re.sub(r'\s+', ' ',
                                         summ.group(1).strip())[:300],
                        url     = link.group(1).strip() if link else "",
                        quelle  = "arxiv",
                        score   = 0.9,
                    ))
            return hits, ""
        except Exception as e:
            log.debug(f"arXiv: {e}")
            return [], ""

    # ── GitHub ────────────────────────────────────────────────────────────────
    async def _github(self, query: str) -> tuple[list[SearchHit], str]:
        code_query = any(w in query.lower() for w in [
            "code", "python", "library", "tool", "github", "open source",
            "implementation", "framework", "api", "sdk"
        ])
        if not code_query:
            return [], ""
        try:
            sess = await self._sess()
            async with sess.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": "stars",
                        "order": "desc", "per_page": 4},
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return [], ""
                data = await r.json()

            hits = []
            for repo in data.get("items", [])[:4]:
                hits.append(SearchHit(
                    titel   = repo.get("full_name", "")[:80],
                    snippet = (repo.get("description", "") or "")[:200] +
                              f" ⭐{repo.get('stargazers_count', 0)}",
                    url     = repo.get("html_url", ""),
                    quelle  = "github",
                    score   = 0.85,
                ))
            return hits, ""
        except Exception as e:
            log.debug(f"GitHub: {e}")
            return [], ""

    # ── Volltext laden ─────────────────────────────────────────────────────────
    async def _load_volltexte(self, hits: list[SearchHit]):
        """Lädt Volltext der Top-N Ergebnisse parallel."""
        async def _fetch(hit: SearchHit):
            try:
                sess = await self._sess()
                async with sess.get(
                    hit.url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True
                ) as r:
                    if r.status == 200:
                        ct = r.headers.get("Content-Type", "")
                        if "text" in ct:
                            html = await r.text(errors="replace")
                            hit.volltext = self._html_text(html)[:2000]
            except Exception:
                pass

        await asyncio.gather(*[_fetch(h) for h in hits],
                             return_exceptions=True)

    def _html_text(self, html: str) -> str:
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '',
                      html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', html)
        for ent, c in [("&amp;","&"),("&lt;","<"),("&gt;",">"),
                       ("&nbsp;"," "),("&auml;","ä"),("&ouml;","ö"),
                       ("&uuml;","ü"),("&szlig;","ß")]:
            text = text.replace(ent, c)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def stats(self) -> dict:
        return {
            "cache_size":  len(self.cache._c),
            "brave_aktiv": bool(self._brave_key),
            "engines":     ["ddg", "brave", "wikipedia", "searxng",
                            "reddit", "arxiv", "github"],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_search: Optional[MultiSearch] = None

def get_search() -> MultiSearch:
    global _search
    if _search is None:
        _search = MultiSearch()
    return _search
