"""
Test unitari di github_analyzer.py — nessuna chiamata di rete.

Coprono:
  - paginazione multi-pagina/cursore (Link rel="after") e fallback `page`;
  - recupero automatico dall'HTTP 422 'cursor based pagination' (dataset
    grandi, es. apache/airflow) con ripartenza senza `page` e nessun duplicato;
  - cutoff su created_at ai confini T-6;
  - propagazione degli errori di paginazione (mai elenco parziale per buono);
  - cache senza header Link -> rifacimento della richiesta;
  - confini finestre T-6 / T+6 (start incluso, end escluso);
  - metriche Issue: denominatori, confini, zero vs recupero fallito;
  - esclusione delle Pull Request dall'elenco Issue;
  - stato 'ok' solo a recupero completo; 'parziale' con colonne vuote;
  - struttura delle colonne del CSV (invariata).

Uso:  python -m unittest discover AI_agent_folder/tests
"""

import importlib.util
import http.client
import ssl
import sys
import threading
import unittest
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

_MOD = Path(__file__).resolve().parents[1] / "modules" / "github_analyzer.py"
_spec = importlib.util.spec_from_file_location("github_analyzer", _MOD)
ga = importlib.util.module_from_spec(_spec)
sys.modules["github_analyzer"] = ga
_spec.loader.exec_module(ga)

# Attenzione: le URL contengono `per_page=100`, che contiene la sottostringa
# "page=": per riconoscere il parametro `page` si cerca sempre "&page=".


# ------------------------------------------------------------------ util

def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def items(ids, created="2025-01-01T00:00:00Z"):
    return [{"id": i, "number": i, "created_at": created,
             "updated_at": created} for i in ids]


def page100(offset):
    return items(range(offset, offset + ga.PER_PAGE))


def link_after(cursor):
    return (f'<https://api.github.com/repositories/1/pulls?per_page=100'
            f'&after={cursor}>; rel="after"')


def link_next(page):
    return (f'<https://api.github.com/repositories/1/pulls?per_page=100'
            f'&page={page}>; rel="next"')


class HandlerClient:
    """Client fittizio: il handler restituisce (body, header_link)."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.by_repo = {}
        self.cache_by_repo = {}
        self.current_repo = "-"
        self.abort = None
        self.lock = threading.Lock()

    def get(self, url, repo=None, is_search=False, kind="altro",
            want_link=False, force=False):
        self.calls.append((url, force))
        body, link = self.handler(url, force)
        return (body, link) if want_link else body


# ------------------------------------------------------- paginazione REST

class TestParseLink(unittest.TestCase):
    def test_after_e_next(self):
        h = ('<https://api.github.com/x?after=abc>; rel="after", '
             '<https://api.github.com/x?page=3>; rel="next"')
        got = ga.parse_link_header(h)
        self.assertEqual(got["after"], "https://api.github.com/x?after=abc")
        self.assertEqual(got["next"], "https://api.github.com/x?page=3")

    def test_header_vuoto(self):
        self.assertEqual(ga.parse_link_header(None), {})
        self.assertEqual(ga.parse_link_header(""), {})


class TestPaginate(unittest.TestCase):
    URL = "/repos/owner/name/issues"
    PARAMS = {"state": "all", "sort": "created", "direction": "desc",
              "since": "2024-12-15T00:00:00Z"}

    def test_paginazione_a_cursori_senza_duplicati(self):
        """2 pagine via cursore `after`: 150 item, tutti distinti."""
        def handler(url, force):
            if "&page=1" in url:
                return page100(0), link_after("C1") + ", " + link_next(2)
            if "after=C1" in url:
                return items(range(100, 150)), None
            raise AssertionError("URL inatteso: " + url)

        c = HandlerClient(handler)
        got = ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        self.assertEqual(len(got), 150)
        self.assertEqual(len({i["id"] for i in got}), 150)   # nessun duplicato
        self.assertEqual(len(c.calls), 2)
        # la seconda richiesta segue il cursore, senza parametro `page`
        self.assertIn("after=C1", c.calls[1][0])
        self.assertNotIn("&page=", c.calls[1][0])

    def test_422_cursor_riparte_senza_page_completo(self):
        """HTTP 422 con `page` -> ripartenza con i cursori: elenco completo,
        accumulato azzerato => zero duplicati e zero omissioni."""
        def handler(url, force):
            if "&page=" in url:
                raise ga.CursorPaginationRequired(
                    "HTTP 422: Pagination with the page parameter is not "
                    "supported for large datasets, please use cursor based "
                    "pagination (after/before)")
            if "after=" not in url:
                return page100(0), link_after("C1")     # prima pagina cursor
            if "after=C1" in url:
                return items(range(100, 150)), None
            raise AssertionError("URL inatteso: " + url)

        c = HandlerClient(handler)
        got = ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        self.assertEqual(len(got), 150)
        self.assertEqual(len({i["id"] for i in got}), 150)
        self.assertTrue(any("&page=" in u for u, _ in c.calls))   # tentativo page
        self.assertTrue(any("after=" in u for u, _ in c.calls))   # poi cursori

    def test_fallback_page_quando_non_ci_sono_cursori(self):
        """Endpoint senza cursori: segue `next` (page=2) come prima."""
        def handler(url, force):
            if "&page=1" in url:
                return page100(0), link_next(2)
            if "&page=2" in url:
                return items(range(100, 140)), None
            raise AssertionError("URL inatteso: " + url)

        c = HandlerClient(handler)
        got = ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        self.assertEqual(len(got), 140)
        self.assertIn("&page=2", c.calls[1][0])

    def test_cutoff_confine_incluso_e_stop(self):
        """Item con created_at == cutoff inclusi; item piu' vecchi fermanti:
        la paginazione non prosegue oltre."""
        cutoff = "2024-12-15T00:00:00Z"
        older = [{"id": i, "created_at": "2024-10-01T00:00:00Z"}
                 for i in range(500, 510)]
        newer = [{"id": i, "created_at": "2025-01-01T00:00:00Z"}
                 for i in range(10, 40)]
        edge = [{"id": 999, "created_at": cutoff}]        # == cutoff: conta

        def handler(url, force):
            return newer + edge + older, None

        c = HandlerClient(handler)
        got = ga.paginate(c, self.URL, self.PARAMS, cutoff, "owner/name")
        self.assertEqual([i["id"] for i in got],
                         [i["id"] for i in newer] + [999])
        self.assertEqual(len(c.calls), 1)   # nessuna pagina successiva

    def test_errore_di_paginazione_si_propaga(self):
        """Un errore di rete non viene mai convertito in elenco vuoto."""
        def handler(url, force):
            raise RuntimeError("HTTP 404: Not Found")

        c = HandlerClient(handler)
        with self.assertRaises(RuntimeError):
            ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")

    def test_oltre_max_pages_errore(self):
        """Mai un elenco troncato presentato come completo."""
        old = ga.MAX_PAGES
        ga.MAX_PAGES = 2
        try:
            def handler(url, force):
                n = 1
                if "&page=" in url:
                    n = int(url.split("&page=")[1].split("&")[0])
                return page100(0), link_next(n + 1)

            c = HandlerClient(handler)
            with self.assertRaises(RuntimeError):
                ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        finally:
            ga.MAX_PAGES = old

    def test_cache_senza_link_rifatta_in_rete(self):
        """Entry di cache vecchia (pagina piena, nessun header Link): la
        richiesta viene rifatta con force=True per recuperare il cursore."""
        def handler(url, force):
            if "&page=1" in url and not force:
                return page100(0), None          # cache storica
            if "&page=1" in url and force:
                return page100(0), link_after("C1")
            if "after=C1" in url:
                return items(range(100, 150)), None
            raise AssertionError("URL inatteso: " + url)

        c = HandlerClient(handler)
        got = ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        self.assertEqual(len(got), 150)
        self.assertTrue(any(force for _, force in c.calls))     # force usato

    def test_url_prima_pagina_uguale_allo_storico(self):
        """La prima richiesta deve mantenere l'URL esatto della vecchia
        versione (page=1 in coda): compatibilita' della cache su disco."""
        c = HandlerClient(lambda url, force: (items([1]), None))
        ga.paginate(c, self.URL, self.PARAMS, None, "owner/name")
        url = c.calls[0][0]
        expected = (ga.API + self.URL + "?" +
                    urllib.parse.urlencode(dict(self.PARAMS,
                                                per_page=ga.PER_PAGE)) +
                    "&page=1")
        self.assertEqual(url, expected)


# ------------------------------------------------- finestre e metriche

class TestFinestre(unittest.TestCase):
    def test_confini_t6_t6(self):
        t1 = date(2025, 6, 15)
        pre_s, pre_e, post_s, post_e = ga.windows_for(t1)
        self.assertEqual(pre_s.date(), date(2024, 12, 15))
        self.assertEqual(pre_e, post_s)                 # stacco su T1
        self.assertEqual(post_e.date(), date(2025, 12, 15))
        # semiaperti: start incluso, end escluso
        self.assertTrue(ga.in_window(pre_s, pre_s, pre_e))
        self.assertFalse(ga.in_window(pre_e, pre_s, pre_e))
        self.assertTrue(ga.in_window(post_s, post_s, post_e))
        self.assertFalse(ga.in_window(post_e, post_s, post_e))


class TestIssueMetrics(unittest.TestCase):
    START = dt("2024-12-15T00:00:00Z")
    END = dt("2025-06-15T00:00:00Z")

    def test_confini_creazione_e_chiusura(self):
        issues = [
            # creata all'inizio (inclusa), chiusa nella finestra
            {"id": 1, "user": {"id": 11}, "created_at": "2024-12-15T00:00:00Z",
             "closed_at": "2025-01-14T00:00:00Z"},
            # creata alla fine della finestra (T1): NON e' della finestra pre
            {"id": 2, "user": {"id": 12}, "created_at": "2025-06-15T00:00:00Z",
             "closed_at": None},
            # creata qui ma chiusa DOPO la fine: non conta come chiusa
            {"id": 3, "user": {"id": 11}, "created_at": "2025-05-01T00:00:00Z",
             "closed_at": "2025-07-01T00:00:00Z"},
        ]
        # il filtro di creazione e' del chiamante (come in analyze_repo):
        # la finestra semiaperta esclude id 2 (creata == fine finestra)
        created = [i for i in issues
                   if ga.in_window(ga.parse_ts(i["created_at"]),
                                   self.START, self.END)]
        self.assertEqual([i["id"] for i in created], [1, 3])
        m = ga.issue_metrics(created, self.START, self.END)
        self.assertEqual(m["issue_aperte"], 2)           # id 1 e 3
        self.assertEqual(m["issue_chiuse"], 1)           # solo id 1
        self.assertEqual(m["issue_pct_chiusura"], 50.0)  # 1/2 su TUTTE le create
        self.assertEqual(m["issue_tempo_medio_chiusura_giorni"], 30.0)
        self.assertEqual(m["issue_contributori"], 1)     # id1 e id3 stesso autore

    def test_zero_vs_non_calcolabile(self):
        m = ga.issue_metrics([], self.START, self.END)
        self.assertEqual(m["issue_aperte"], 0)                  # 0 = calcolato
        self.assertEqual(m["issue_chiuse"], 0)
        self.assertIsNone(m["issue_pct_chiusura"])              # denominator 0
        self.assertIsNone(m["issue_tempo_medio_chiusura_giorni"])  # nessun evento

    def test_pr_escluse_dalle_issue(self):
        listing = [
            {"id": 1, "pull_request": {"url": "x"}, "created_at":
             "2025-01-01T00:00:00Z"},
            {"id": 2, "created_at": "2025-01-02T00:00:00Z"},
        ]
        prs, issues = ga.split_listing(listing)
        self.assertEqual(len(prs), 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["id"], 2)


# ------------------------------------------------- analyze_repo (fittizio)

class ScriptedClient:
    """Client fittizio per analyze_repo: risponde per tipo di endpoint.
    `reviews` e' un dict numero_PR -> [review]."""

    def __init__(self, issues=None, pulls_open=None, pulls_closed=None,
                 reviews=None, issues_error=None, reviews_error=None):
        self.issues = issues or []
        self.pulls_open = pulls_open or []
        self.pulls_closed = pulls_closed or []
        self.reviews = reviews or {}
        self.issues_error = issues_error
        self.reviews_error = reviews_error
        self.by_repo = {}
        self.cache_by_repo = {}
        self.current_repo = "-"
        self.abort = None
        self.lock = threading.Lock()
        self.calls = []

    def get(self, url, repo=None, is_search=False, kind="altro",
            want_link=False, force=False):
        self.calls.append(url)
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if path.endswith("/issues"):
            if self.issues_error:
                if isinstance(self.issues_error, BaseException):
                    raise self.issues_error     # eccezione grezza (es. OSError)
                raise RuntimeError(self.issues_error)
            body = self.issues
        elif path.endswith("/pulls"):
            qs = urllib.parse.parse_qs(parsed.query)
            state = (qs.get("state") or ["open"])[0]
            body = self.pulls_open if state == "open" else self.pulls_closed
        elif path.endswith("/reviews"):
            if self.reviews_error:
                if isinstance(self.reviews_error, BaseException):
                    raise self.reviews_error    # eccezione grezza (es. OSError)
                raise RuntimeError(self.reviews_error)
            num = int(path.split("/pulls/")[1].split("/")[0])
            body = self.reviews.get(num, [])
        else:
            raise AssertionError("URL inatteso: " + url)
        return (body, None) if want_link else body


def cand(t1="2025-06-15"):
    d = date.fromisoformat(t1)
    return {"full": "owner/name", "t1": d, "t1s": t1,
            "folder": Path("."), "key": "owner/name", "first_commit": None}


ISSUES_OK = [
    # issue vera creata in T-6 e chiusa nella finestra
    {"id": 1, "number": 1, "user": {"id": 11}, "created_at":
     "2025-01-05T00:00:00Z", "closed_at": "2025-02-01T00:00:00Z",
     "updated_at": "2025-02-01T00:00:00Z"},
    # una PULL REQUEST travestita da issue: NON deve entrare nel conteggio
    {"id": 900, "number": 900, "pull_request": {"url": "x"}, "user":
     {"id": 99}, "created_at": "2025-01-06T00:00:00Z", "closed_at": None,
     "updated_at": "2025-01-06T00:00:00Z"},
    # issue creata in T+6, ancora aperta
    {"id": 2, "number": 2, "user": {"id": 12}, "created_at":
     "2025-07-05T00:00:00Z", "closed_at": None,
     "updated_at": "2025-07-05T00:00:00Z"},
]

PULLS_CLOSED_OK = [
    {"id": 10, "number": 10, "user": {"id": 1}, "created_at":
     "2025-01-10T00:00:00Z", "closed_at": "2025-03-01T00:00:00Z",
     "merged_at": "2025-03-01T00:00:00Z", "updated_at":
     "2025-03-01T00:00:00Z"},
    {"id": 20, "number": 20, "user": {"id": 2}, "created_at":
     "2025-07-10T00:00:00Z", "closed_at": "2025-08-01T00:00:00Z",
     "merged_at": "2025-08-01T00:00:00Z", "updated_at":
     "2025-08-01T00:00:00Z"},
]

REVIEWS_OK = {
    10: [{"id": 1000, "user": {"id": 10}, "state": "APPROVED",
          "submitted_at": "2025-02-01T00:00:00Z"}],      # finestra pre
    20: [{"id": 2000, "user": {"id": 11}, "state": "CHANGES_REQUESTED",
          "submitted_at": "2025-07-20T00:00:00Z"}],      # finestra post
}


class TestAnalyzeRepo(unittest.TestCase):
    def test_recupero_completo_stato_ok(self):
        c = ScriptedClient(issues=ISSUES_OK, pulls_closed=PULLS_CLOSED_OK,
                           reviews=REVIEWS_OK)
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertFalse(err)
        self.assertEqual(row["stato"], "ok")
        # issue: la PR travestita da issue NON conta
        self.assertEqual(row["issue_aperte_pre"], 1)
        self.assertEqual(row["issue_chiuse_pre"], 1)
        self.assertEqual(row["issue_pct_chiusura_pre"], 100.0)
        self.assertEqual(row["issue_aperte_post"], 1)
        self.assertEqual(row["issue_chiuse_post"], 0)
        self.assertEqual(row["issue_pct_chiusura_post"], 0.0)
        # PR (invariate)
        self.assertEqual(row["pr_aperte_pre"], 1)
        self.assertEqual(row["pr_merged_pre"], 1)
        self.assertEqual(row["pr_pct_merge_pre"], 100.0)
        # review (invariate)
        self.assertEqual(row["review_totale_pre"], 1)
        self.assertEqual(row["review_approvate_pre"], 1)
        self.assertEqual(row["review_totale_post"], 1)
        self.assertEqual(row["review_approvate_post"], 0)
        # tutte le colonne previste presenti
        for f in ga.FIELDS:
            self.assertIn(f, row)
        self.assertEqual(len(ga.METRICS), 14)
        self.assertIn("richieste_api", row)
        self.assertIn("cache_hit", row)

    def test_recupero_issue_fallito_non_e_zero(self):
        """Issue non recuperate -> colonne issue VUOTE (mai 0), stato
        parziale, metriche PR/Review rimaste valide."""
        c = ScriptedClient(issues=None,
                           issues_error="HTTP 404: Not Found",
                           pulls_closed=PULLS_CLOSED_OK, reviews=REVIEWS_OK)
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertTrue(str(row["stato"]).startswith("parziale"),
                        row["stato"])
        self.assertTrue(err)
        # nessuna metrica Issue scritta (colonna vuota nel CSV)
        self.assertIsNone(row.get("issue_aperte_pre"))
        self.assertIsNone(row.get("issue_aperte_post"))
        self.assertIsNone(row.get("issue_pct_chiusura_pre"))
        # PR e review restano validi
        self.assertEqual(row["pr_aperte_pre"], 1)
        self.assertEqual(row["review_totale_pre"], 1)

    def test_zero_issue_non_e_errore(self):
        """Elenco issue recuperato ma vuoto -> 0 (calcolato), stato ok."""
        c = ScriptedClient(issues=[], pulls_closed=PULLS_CLOSED_OK,
                           reviews=REVIEWS_OK)
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertEqual(row["stato"], "ok")
        self.assertEqual(row["issue_aperte_pre"], 0)
        self.assertEqual(row["issue_aperte_post"], 0)
        # denominatore 0 -> percentuale NON calcolabile: campo vuoto, non 0
        self.assertEqual(row["issue_pct_chiusura_pre"], "")

    def test_review_fallite_lasciano_vuote_le_review(self):
        """Recupero review fallito -> 4 metriche review vuote, stato
        parziale; issue e PR restano validi."""
        c = ScriptedClient(issues=ISSUES_OK, pulls_closed=PULLS_CLOSED_OK,
                           reviews_error="HTTP 500: boom")
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertTrue(str(row["stato"]).startswith("parziale"),
                        row["stato"])
        self.assertIsNone(row.get("review_totale_pre"))
        self.assertIsNone(row.get("review_totale_post"))
        self.assertEqual(row["issue_aperte_pre"], 1)
        self.assertEqual(row["pr_aperte_pre"], 1)


class TestStrutturaCSV(unittest.TestCase):
    def test_colonne_invariate(self):
        # intestazioni e metriche scritte esplicitamente: qualsiasi
        # aggiunta/rimozione/reordine fa fallire il test
        header = ["repository", "t1", "stato",
                  "pre_start", "pre_end", "post_start", "post_end"]
        pr_m = ["pr_aperte", "pr_merged", "pr_pct_merge",
                "pr_tempo_medio_merge_giorni", "pr_contributori"]
        issue_m = ["issue_aperte", "issue_chiuse",
                   "issue_tempo_medio_chiusura_giorni", "issue_contributori",
                   "issue_pct_chiusura"]
        review_m = ["review_totale", "review_reviewer_distinti",
                    "review_approvate", "review_tempo_medio_prima_review_giorni"]
        self.assertEqual(ga.PR_METRICS, pr_m)
        self.assertEqual(ga.ISSUE_METRICS, issue_m)
        self.assertEqual(ga.REVIEW_METRICS, review_m)
        self.assertEqual(len(ga.METRICS), 14)
        # ordine delle colonne: per metrica, finestra pre poi post
        expected = (header
                    + [f"{m}_{s}" for m in (pr_m + issue_m + review_m)
                       for s in ("pre", "post")]
                    + ["richieste_api", "cache_hit"])
        self.assertEqual(ga.FIELDS, expected)
        self.assertEqual(len(ga.FIELDS), 37)


class TestRobustezzaConnessione(unittest.TestCase):
    """GitHubClient.get() di fronte a interruzioni temporanee della connessione
    (il caso osservato: http.client.RemoteDisconnected durante fetch_reviews).
    Nessuna richiesta di rete: urlopen e time.sleep sono mockkati."""

    URL = "https://api.github.com/repos/owner/name/pulls/10/reviews"

    @staticmethod
    def _resp(payload=b'{"ok": true}'):
        class FakeResp:
            headers = {}

            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return FakeResp()

    @staticmethod
    def _http_error(code, msg, hdrs=None):
        import io as _io
        return urllib.error.HTTPError(
            "https://api.github.com/x", code, msg, hdrs or {},
            _io.BytesIO(('{"message": "%s"}' % msg).encode()))

    def test_remote_disconnected_poi_risposta_valida(self):
        """1 interruzione + risposta OK -> si riprova con 2s e si ritorna
        la risposta valida (non una lista vuota)."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep") as sleep, \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=[http.client.RemoteDisconnected(),
                                               self._resp()]) as m:
            body = client.get(self.URL, kind="review")
        self.assertEqual(body, {"ok": True})
        self.assertEqual(m.call_count, 2)            # 1 fallita + 1 valida
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2])
        self.assertEqual(client.requests, 2)

    def test_cinque_interruzioni_consecutive(self):
        """5 interruzioni consecutive -> 5 tentativi, backoff 2,4,8,16,30 e
        RuntimeError gestibile (mai una risposta vuota)."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep") as sleep, \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=http.client.RemoteDisconnected()) as m:
            with self.assertRaises(RuntimeError) as ctx:
                client.get(self.URL, kind="review")
        self.assertIn("5 tentativi", str(ctx.exception))
        self.assertEqual(m.call_count, 5)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],
                         [2, 4, 8, 16, 30])
        self.assertTrue(client.errors)               # errore registrato
        self.assertEqual(client.requests, 5)

    def test_errore_http_404_gia_gestito_invariato(self):
        """4xx definitivo: subito RuntimeError, UNA sola richiesta, nessun
        backoff transitorio (gestione HTTP invariata)."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep") as sleep, \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=self._http_error(404, "Not Found")) as m:
            with self.assertRaises(RuntimeError) as ctx:
                client.get(self.URL)
        self.assertIn("HTTP 404", str(ctx.exception))
        self.assertEqual(m.call_count, 1)
        sleep.assert_not_called()
        self.assertTrue(client.errors)

    def test_throttle_429_poi_successo_invariato(self):
        """429 con Retry-After -> attesa e secondo tentativo: gestione
        throttling precedente invariata."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep") as sleep, \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=[self._http_error(429, "rate limited",
                                                                {"Retry-After": "1"}),
                                               self._resp()]) as m:
            body = client.get(self.URL)
        self.assertEqual(body, {"ok": True})
        self.assertEqual(m.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1])

    def test_5xx_poi_successo_invariato(self):
        """5xx -> riprova con backoff 2**attempt (1,2,4...): invariato."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep") as sleep, \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=[self._http_error(502, "Bad Gateway"),
                                               self._resp()]) as m:
            body = client.get(self.URL)
        self.assertEqual(body, {"ok": True})
        self.assertEqual(m.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1])

    def test_fetch_reviews_interrotta_diventa_runtime_error(self):
        """Il caso osservato su apache/airflow: RemoteDisconnected dentro
        fetch_reviews() -> dopo i 5 tentativi esce RuntimeError (gestibile),
        non l'eccezione grezza di http.client."""
        client = ga.GitHubClient("token", cache=False)
        with mock.patch("time.sleep"), \
                mock.patch.object(ga.urllib.request, "urlopen",
                                  side_effect=http.client.RemoteDisconnected()):
            with self.assertRaises(RuntimeError) as ctx:
                ga.fetch_reviews(client, "owner/name", 10)
        self.assertIn("5 tentativi", str(ctx.exception))

    def test_classificazione_errori_transitori(self):
        self.assertTrue(ga.is_transient_network_error(
            http.client.RemoteDisconnected()))
        self.assertTrue(ga.is_transient_network_error(ConnectionResetError()))
        self.assertTrue(ga.is_transient_network_error(TimeoutError()))
        self.assertTrue(ga.is_transient_network_error(
            urllib.error.URLError(ConnectionResetError())))
        self.assertTrue(ga.is_transient_network_error(
            urllib.error.URLError(TimeoutError())))
        # non transitori: non vengono riprovati inutilmente
        self.assertFalse(ga.is_transient_network_error(
            urllib.error.URLError(ssl.SSLCertVerificationError("cert"))))
        self.assertFalse(ga.is_transient_network_error(
            urllib.error.URLError("motivo non di rete")))

    def test_cache_valida_non_ripetuta(self):
        """Se l'URL e' gia' in cache con dati validi, urlopen non viene
        nemmeno chiamato (nessuna richiesta ripetuta)."""
        import tempfile
        old_dir = ga.CACHE_DIR
        with tempfile.TemporaryDirectory() as td:
            ga.CACHE_DIR = Path(td)
            try:
                client = ga.GitHubClient("token", cache=True)
                client._cache_write(self.URL, {"cached": 1}, None)
                with mock.patch.object(ga.urllib.request, "urlopen") as m:
                    body = client.get(self.URL, kind="review")
                self.assertEqual(body, {"cached": 1})
                m.assert_not_called()
                self.assertEqual(client.requests, 0)
                self.assertEqual(client.cache_hits, 1)
            finally:
                ga.CACHE_DIR = old_dir

    def test_analyze_repo_disconnected_issue_parziale(self):
        """Un'eccezione di rete grezza sull'elenco issue non diventa mai
        'ok' ne' uno zero: colonne issue vuote + stato parziale."""
        c = ScriptedClient(issues=None,
                           issues_error=http.client.RemoteDisconnected(),
                           pulls_closed=PULLS_CLOSED_OK, reviews=REVIEWS_OK)
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertTrue(str(row["stato"]).startswith("parziale"), row["stato"])
        self.assertIsNone(row.get("issue_aperte_pre"))
        self.assertIsNone(row.get("issue_aperte_post"))
        self.assertEqual(row["pr_aperte_pre"], 1)      # PR/Review restano validi

    def test_analyze_repo_disconnected_review_parziale(self):
        """Stesso caso sul recupero review (dove e' stato osservato):
        nessuna metrica review scritta come 0, stato parziale."""
        c = ScriptedClient(issues=ISSUES_OK, pulls_closed=PULLS_CLOSED_OK,
                           reviews_error=http.client.RemoteDisconnected())
        row, err = ga.analyze_repo(c, cand(), workers=2)
        self.assertTrue(str(row["stato"]).startswith("parziale"), row["stato"])
        self.assertIsNone(row.get("review_totale_pre"))
        self.assertIsNone(row.get("review_totale_post"))
        self.assertEqual(row["issue_aperte_pre"], 1)
        self.assertEqual(row["pr_aperte_pre"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
