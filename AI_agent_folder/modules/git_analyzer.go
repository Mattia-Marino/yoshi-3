// git_analyzer.go — porting in Go di git_analyzer.py.
//
// Metriche di attivita' attorno a T_1 con finestra T-6 / T+6
// (sei mesi prima e sei mesi dopo la prima introduzione di un file per agenti).
//
// Input:
//   - results/adoption_events.csv  (T_1 per repo, colonna 'data')
//   - i clone in C:\Users\geppe\Desktop\Cloning_repo
//
// Finestre:
//   pre  = [T_1 - 6 mesi, T_1)
//   post = [T_1, T_1 + 6 mesi)
// Se T_1 + 6 mesi e' futuro (rispetto a oggi), la finestra post non e' completa:
// nello stato del repo viene scritto "periodo_post_incompleto" e le colonne
// post restano vuote (nessun confronto non omogeneo tra repo).
//
// Le repo vengono analizzate in parallelo con un pool di goroutine
// (default 5, regolabile con -workers); la semantica per singolo repo
// e' identica alla versione Python.
//
// Uso:
//   go run git_analyzer.go                  # tutte le repo, 5 in parallelo
//   go run git_analyzer.go -workers 8
//   go run git_analyzer.go -only caddy,scrapy
//
// Output: results/git_metrics.csv
package main

import (
	"bytes"
	"context"
	"encoding/csv"
	"flag"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	reposDir     = `C:\Users\geppe\Desktop\Cloning_repo`
	resultsDir   = `C:\Users\geppe\Desktop\Progetto_Tamburri\yoshi-3\AI_agent_folder\results`
	eventsFile   = "adoption_events.csv"
	outFile      = "git_metrics.csv"
	windowMonths = 6
	slackDays    = 40 // margine su --since/--until (git filtra per data di commit, non di autore)
	gitTimeout   = time.Hour
)

var fields = []string{
	"repository", "t1", "stato",
	"commits_pre", "commits_post",
	"commit_mensili_pre", "commit_mensili_post",
	"contributors_pre", "contributors_post",
	"contributors_attivi_mensili_pre", "contributors_attivi_mensili_post",
	"righe_aggiunte_pre", "righe_aggiunte_post",
	"righe_rimosse_pre", "righe_rimosse_post",
	"top1_contributor_pre", "top1_contributor_post",
	"top3_contributor_pre", "top3_contributor_post",
	"top5_contributor_pre", "top5_contributor_post",
	"release_pre", "release_post",
	"release_mensili_pre", "release_mensili_post",
}

// tag tipo "v1.2.3", "release-2.0", "2026.08.1"
var releaseRe = regexp.MustCompile(`\d+\.\d+`)

// ---------------------------------------------------------------- date

func daysIn(year int, month time.Month) int {
	switch month {
	case time.February:
		if year%4 == 0 && year%100 != 0 || year%400 == 0 {
			return 29
		}
		return 28
	case time.April, time.June, time.September, time.November:
		return 30
	}
	return 31
}

// addMonths equivale ad add_months() di Python (con clamp del giorno).
func addMonths(d time.Time, n int) time.Time {
	m := int(d.Month()) - 1 + n
	q := m / 12
	r := m % 12
	if r < 0 { // divisione con resto negativo -> floor
		q--
		r += 12
	}
	year := d.Year() + q
	month := time.Month(r + 1)
	day := d.Day()
	if dim := daysIn(year, month); day > dim {
		day = dim
	}
	return time.Date(year, month, day, 0, 0, 0, 0, time.UTC)
}

// monthSlots: 6 slot mensili consecutivi allineati a T_1.
// pre : [T1-6m, T1-5m) ... [T1-1m, T1)
// post: [T1, T1+1m) ... [T1+5m, T1+6m)
func monthSlots(t1 time.Time, post bool) [][2]time.Time {
	slots := make([][2]time.Time, 0, windowMonths)
	for i := 0; i < windowMonths; i++ {
		var s, e time.Time
		if post {
			s, e = addMonths(t1, i), addMonths(t1, i+1)
		} else {
			s, e = addMonths(t1, -(windowMonths-i)), addMonths(t1, -(windowMonths-1-i))
		}
		slots = append(slots, [2]time.Time{s, e})
	}
	return slots
}

// ---------------------------------------------------------------- formattazione (pari a Python)

func round1(v float64) float64 { return math.RoundToEven(v*10) / 10 }
func round2(v float64) float64 { return math.RoundToEven(v*100) / 100 }

// pyFloat emula str(float) di Python: almeno un decimale ("12.0", non "12").
func pyFloat(v float64) string {
	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.ContainsAny(s, ".eE") {
		s += ".0"
	}
	return s
}

// ---------------------------------------------------------------- git

func gitOut(repo string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), gitTimeout)
	defer cancel()
	full := append([]string{"-C", repo, "-c", "core.quotepath=false"}, args...)
	cmd := exec.CommandContext(ctx, "git", full...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = err.Error()
		}
		if len(msg) > 160 {
			msg = msg[:160]
		}
		return "", fmt.Errorf("%s", msg)
	}
	// Python leggeva con errors="replace": sostituisce gli byte non UTF-8
	return strings.ToValidUTF8(stdout.String(), "\uFFFD"), nil
}

// defaultRef: branch principale origin/HEAD se disponibile, altrimenti HEAD.
func defaultRef(repo string) string {
	out, err := gitOut(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
	if err != nil {
		return "HEAD"
	}
	if s := strings.TrimSpace(out); s != "" {
		return s
	}
	return "HEAD"
}

type commit struct {
	ident string
	date  time.Time
}

type locEntry struct {
	date time.Time
	add  int64
	del  int64
}

type tagInfo struct {
	name string
	date time.Time
}

// collectCommits: tutti i commit (inclusi i merge) nel range.
func collectCommits(repo, ref string, since, until time.Time) ([]commit, error) {
	out, err := gitOut(repo, "log", ref,
		"--since="+since.Format("2006-01-02"),
		"--until="+until.Format("2006-01-02"),
		"--format=%x1e%an%x1f%ae%x1f%aI")
	if err != nil {
		return nil, err
	}
	var res []commit
	// split esplicito su "\n" (splitlines() di Python spezzerebbe anche su \x1e)
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimRight(line, "\r")
		if !strings.HasPrefix(line, "\x1e") {
			continue
		}
		f := strings.Split(line[1:], "\x1f")
		if len(f) != 3 {
			continue
		}
		name, email, iso := f[0], f[1], f[2]
		ident := strings.ToLower(strings.TrimSpace(name))
		if strings.Contains(email, "@") {
			ident = strings.ToLower(strings.TrimSpace(email))
		}
		if len(iso) < 10 {
			continue
		}
		d, err := time.Parse("2006-01-02", iso[:10])
		if err != nil {
			continue
		}
		res = append(res, commit{ident: ident, date: d})
	}
	return res, nil
}

// collectLoc: righe aggiunte/rimosse per commit, ESCLUSI i merge.
func collectLoc(repo, ref string, since, until time.Time) ([]locEntry, error) {
	out, err := gitOut(repo, "log", ref, "--no-merges",
		"--since="+since.Format("2006-01-02"),
		"--until="+until.Format("2006-01-02"),
		"--numstat", "--format=%x1e%aI")
	if err != nil {
		return nil, err
	}
	var res []locEntry
	var cur *locEntry
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimRight(line, "\r")
		if strings.HasPrefix(line, "\x1e") {
			if cur != nil {
				res = append(res, *cur)
			}
			cur = nil
			if len(line) >= 11 {
				if d, err := time.Parse("2006-01-02", line[1:11]); err == nil {
					cur = &locEntry{date: d}
				}
			}
		} else if strings.TrimSpace(line) != "" && cur != nil {
			f := strings.Split(line, "\t")
			if len(f) == 3 {
				if f[0] != "-" {
					if v, err := strconv.ParseInt(f[0], 10, 64); err == nil {
						cur.add += v
					}
				}
				if f[1] != "-" {
					if v, err := strconv.ParseInt(f[1], 10, 64); err == nil {
						cur.del += v
					}
				}
			}
		}
	}
	if cur != nil {
		res = append(res, *cur)
	}
	return res, nil
}

// collectTags: [(nome, data)] di tutti i tag (creatordate). Errori -> nessun tag.
func collectTags(repo string) []tagInfo {
	out, err := gitOut(repo, "for-each-ref",
		"--format=%(refname:short)|%(creatordate:iso-strict)", "refs/tags")
	if err != nil {
		return nil
	}
	var res []tagInfo
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimRight(line, "\r")
		if i := strings.Index(line, "|"); i >= 0 {
			name, iso := line[:i], line[i+1:]
			if len(iso) >= 10 {
				if d, err := time.Parse("2006-01-02", iso[:10]); err == nil {
					res = append(res, tagInfo{name: name, date: d})
				}
			}
		}
	}
	return res
}

// ---------------------------------------------------------------- statistiche

// windowStats: metriche per una finestra [start, end) — chiavi = colonne senza suffisso.
func windowStats(commits []commit, locs []locEntry, tags []tagInfo,
	start, end time.Time, slots [][2]time.Time) map[string]string {

	n := 0
	ids := map[string]int{}
	for _, c := range commits {
		if !c.date.Before(start) && c.date.Before(end) {
			n++
			ids[c.ident]++
		}
	}

	share := func(top int) string {
		if n == 0 {
			return ""
		}
		counts := make([]int, 0, len(ids))
		for _, v := range ids {
			counts = append(counts, v)
		}
		sort.Sort(sort.Reverse(sort.IntSlice(counts)))
		sum := 0
		for i := 0; i < top && i < len(counts); i++ {
			sum += counts[i]
		}
		return pyFloat(round1(100.0 * float64(sum) / float64(n)))
	}

	var addSum, delSum int64
	for _, l := range locs {
		if !l.date.Before(start) && l.date.Before(end) {
			addSum += l.add
			delSum += l.del
		}
	}

	activeSum := 0
	for _, sl := range slots {
		set := map[string]bool{}
		for _, c := range commits {
			if !c.date.Before(sl[0]) && c.date.Before(sl[1]) {
				set[c.ident] = true
			}
		}
		activeSum += len(set)
	}

	releases := 0
	for _, t := range tags {
		if !t.date.Before(start) && t.date.Before(end) && releaseRe.MatchString(t.name) {
			releases++
		}
	}

	return map[string]string{
		"commits":                      strconv.Itoa(n),
		"commit_mensili":               pyFloat(round1(float64(n) / windowMonths)),
		"contributors":                 strconv.Itoa(len(ids)),
		"contributors_attivi_mensili":  pyFloat(round1(float64(activeSum) / windowMonths)),
		"righe_aggiunte":               strconv.FormatInt(addSum, 10),
		"righe_rimosse":                strconv.FormatInt(delSum, 10),
		"top1_contributor":             share(1),
		"top3_contributor":             share(3),
		"top5_contributor":             share(5),
		"release":                      strconv.Itoa(releases),
		"release_mensili":              pyFloat(round2(float64(releases) / windowMonths)),
	}
}

// ---------------------------------------------------------------- eventi / righe

type eventRow struct {
	repository string
	data       string
}

func readEvents(path string) (map[string]eventRow, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1 // righe anche con campi mancanti
	recs, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(recs) == 0 {
		return nil, fmt.Errorf("CSV vuoto: %s", path)
	}
	header := recs[0]
	header[0] = strings.TrimPrefix(header[0], "\ufeff") // BOM utf-8-sig
	col := map[string]int{}
	for i, h := range header {
		col[strings.ToLower(strings.TrimSpace(h))] = i
	}
	ci, ok1 := col["repository"]
	di, ok2 := col["data"]
	if !ok1 || !ok2 {
		return nil, fmt.Errorf("colonne repository/data mancanti in %s", path)
	}
	get := func(rec []string, i int) string {
		if i < len(rec) {
			return rec[i]
		}
		return ""
	}
	events := map[string]eventRow{}
	for _, rec := range recs[1:] {
		repo := get(rec, ci)
		parts := strings.Split(repo, "/")
		key := strings.ToLower(strings.TrimSpace(parts[len(parts)-1]))
		events[key] = eventRow{repository: repo, data: get(rec, di)}
	}
	return events, nil
}

func displayName(dir string, events map[string]eventRow) string {
	base := filepath.Base(dir)
	if ev, ok := events[strings.ToLower(base)]; ok && ev.repository != "" {
		return ev.repository
	}
	return base
}

func emptyRow() map[string]string {
	row := make(map[string]string, len(fields))
	for _, k := range fields {
		row[k] = ""
	}
	return row
}

func processRepo(dir string, events map[string]eventRow, today time.Time) map[string]string {
	base := filepath.Base(dir)
	full := base
	t1s := ""
	if ev, ok := events[strings.ToLower(base)]; ok {
		if ev.repository != "" {
			full = ev.repository
		}
		t1s = strings.TrimSpace(ev.data)
	}

	row := emptyRow()
	row["repository"] = full

	if t1s == "" {
		// nessun file per agenti: solo il nome, come in adoption_events.csv
		return row
	}
	t1, err := time.Parse("2006-01-02", t1s)
	if err != nil {
		fmt.Printf("  [ERRORE] %s: data T_1 non valida %q\n", full, t1s)
		row["t1"] = t1s
		row["stato"] = "errore_git"
		return row
	}
	row["t1"] = t1s

	preStart := addMonths(t1, -windowMonths)
	postEnd := addMonths(t1, windowMonths)
	postComplete := !postEnd.After(today) // postEnd <= today
	if postComplete {
		row["stato"] = "ok"
	} else {
		row["stato"] = "periodo_post_incompleto"
	}

	until := t1
	if postComplete {
		until = postEnd
	}
	since := preStart.AddDate(0, 0, -slackDays)
	until = until.AddDate(0, 0, slackDays)

	ref := defaultRef(dir)
	commits, err := collectCommits(dir, ref, since, until)
	if err != nil {
		fmt.Printf("  [ERRORE] %s: %v\n", full, err)
		row["stato"] = "errore_git"
		return row
	}
	locs, err := collectLoc(dir, ref, since, until)
	if err != nil {
		fmt.Printf("  [ERRORE] %s: %v\n", full, err)
		row["stato"] = "errore_git"
		return row
	}
	tags := collectTags(dir) // come in Python: gli errori sui tag non sono fatali

	pre := windowStats(commits, locs, tags, preStart, t1, monthSlots(t1, false))
	for k, v := range pre {
		row[k+"_pre"] = v
	}

	if postComplete {
		post := windowStats(commits, locs, tags, t1, postEnd, monthSlots(t1, true))
		for k, v := range post {
			row[k+"_post"] = v
		}
	}
	// finestra post incompleta: le colonne *_post restano vuote
	return row
}

// ---------------------------------------------------------------- output

func writeCSV(path string, rows []map[string]string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	if _, err := f.Write([]byte("\xef\xbb\xbf")); err != nil { // BOM utf-8-sig
		return err
	}
	w := csv.NewWriter(f)
	if err := w.Write(fields); err != nil {
		return err
	}
	for _, row := range rows {
		rec := make([]string, len(fields))
		for i, k := range fields {
			rec[i] = row[k]
		}
		if err := w.Write(rec); err != nil {
			return err
		}
	}
	w.Flush()
	return w.Error()
}

// ---------------------------------------------------------------- main

func main() {
	workers := flag.Int("workers", 5, "goroutine parallele (una repo alla volta ciascuna)")
	only := flag.String("only", "", "analizza solo le cartelle che contengono uno di questi nomi (separati da virgola)")
	outPath := flag.String("out", filepath.Join(resultsDir, outFile), "percorso CSV di output")
	flag.Parse()
	if *workers < 1 {
		*workers = 1
	}

	eventsPath := filepath.Join(resultsDir, eventsFile)
	events, err := readEvents(eventsPath)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Fprintf(os.Stderr, "Manca %s: esegui prima adoption_detector.py\n", eventsPath)
		} else {
			fmt.Fprintf(os.Stderr, "Errore lettura %s: %v\n", eventsPath, err)
		}
		os.Exit(1)
	}

	entries, err := os.ReadDir(reposDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Errore lettura %s: %v\n", reposDir, err)
		os.Exit(1)
	}
	var folders []string
	for _, e := range entries {
		if e.IsDir() {
			folders = append(folders, filepath.Join(reposDir, e.Name()))
		}
	}
	sort.Slice(folders, func(i, j int) bool {
		return strings.ToLower(filepath.Base(folders[i])) < strings.ToLower(filepath.Base(folders[j]))
	})

	if *only != "" {
		var toks []string
		for _, t := range strings.Split(*only, ",") {
			if t = strings.ToLower(strings.TrimSpace(t)); t != "" {
				toks = append(toks, t)
			}
		}
		var filtered []string
		for _, dir := range folders {
			base := strings.ToLower(filepath.Base(dir))
			for _, tok := range toks {
				if strings.Contains(base, tok) {
					filtered = append(filtered, dir)
					break
				}
			}
		}
		folders = filtered
	}

	fmt.Printf("Trovate %d cartelle\n", len(folders))
	now := time.Now()
	today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)

	results := make([]map[string]string, len(folders))
	jobs := make(chan int)
	var wg sync.WaitGroup
	var mu sync.Mutex
	started := 0

	for w := 0; w < *workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range jobs {
				name := displayName(folders[idx], events)
				mu.Lock()
				started++
				i := started
				mu.Unlock()
				fmt.Printf("[%d/%d] %s ...\n", i, len(folders), name)
				results[idx] = processRepo(folders[idx], events, today)
			}
		}()
	}
	for i := range folders {
		jobs <- i
	}
	close(jobs)
	wg.Wait()

	if err := writeCSV(*outPath, results); err != nil {
		fmt.Fprintf(os.Stderr, "Errore scrittura %s: %v\n", *outPath, err)
		os.Exit(1)
	}

	nIncomplete := 0
	for _, r := range results {
		if r["stato"] == "periodo_post_incompleto" {
			nIncomplete++
		}
	}
	fmt.Printf("\nScritto: %s (%d righe, %d con periodo_post_incompleto)\n",
		*outPath, len(results), nIncomplete)
}
