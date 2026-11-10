// Aktualizacja kopii danych TLE (tle.txt) dla SAT° Predictor.
// Uruchamiane przez GitHub Actions (.github/workflows/tle.yml) co 6 godzin.
//
// Zasady CelesTrak (https://celestrak.org/usage-policy.php): dane GP zmieniają się co 2 h, każdą
// aktualizację pobiera się raz, a po odpowiedzi innej niż HTTP 200 trzeba przestać pytać i zgłosić to
// człowiekowi. Dlatego: jedno zapytanie zbiorcze, pojedyncze satelity po kolei z przerwą, a przy odmowie
// skrypt kończy się błędem (GitHub wyśle e-mail), zostawiając poprzedni plik bez zmian.
import { readFile, writeFile } from 'node:fs/promises';

const CELESTRAK = 'https://celestrak.org/NORAD/elements/gp.php';
const AMSAT = 'https://www.amsat.org/tle/current/nasabare.txt';
const UA = 'SATPredictor-TLE-mirror (+https://github.com/sq5wbw/satpredictor)';
const OUT = 'tle.txt';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function get(url) {
  const ac = new AbortController(), to = setTimeout(() => ac.abort(), 30000);
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA }, signal: ac.signal });
    return { status: r.status, text: r.ok ? await r.text() : await r.text().catch(() => '') };
  } catch (e) { return { status: 0, text: String(e) }; }
  finally { clearTimeout(to); }
}

// ta sama logika co w aplikacji: najnowszy zestaw elementów dla każdego numeru NORAD
function parseTLE(text) {
  const lines = text.split(/\r?\n/).map(l => l.trimEnd()).filter(l => l.trim());
  const out = {};
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('1 ') && lines[i + 1] && lines[i + 1].startsWith('2 ')) {
      const name = (i > 0 && !lines[i - 1].startsWith('1 ') && !lines[i - 1].startsWith('2 ')) ? lines[i - 1].trim() : '';
      const norad = parseInt(lines[i].substring(2, 7), 10);
      const ep = parseFloat(lines[i].substring(18, 32)) || 0;
      const epoch = (ep >= 57000 ? 1900000 : 2000000) + ep;
      if (!out[norad] || out[norad].epoch < epoch) out[norad] = { name, l1: lines[i], l2: lines[i + 1], epoch };
      i++;
    }
  }
  return out;
}

// lista satelitów prosto z aplikacji – dodanie satelity w index.html wystarczy
const html = await readFile('index.html', 'utf8');
const wanted = [...new Set([...html.matchAll(/norad:\s*(\d+)/g)].map(m => +m[1]))];
if (!wanted.length) { console.error('Nie znaleziono listy satelitów (norad: …) w index.html'); process.exit(1); }

let previous = {};
try { previous = parseTLE(await readFile(OUT, 'utf8')); } catch { /* pierwszy przebieg */ }

const problems = [];
let text = '';

// 1) CelesTrak – plik zbiorczy
const group = await get(`${CELESTRAK}?GROUP=amateur&FORMAT=tle`);
if (group.status === 200) text += '\n' + group.text;
else problems.push(`CelesTrak GROUP=amateur: HTTP ${group.status || 'brak odpowiedzi'} ${group.text.slice(0, 200).trim()}`);

// 2) AMSAT – drugi plik zbiorczy (z serwera nie ma blokady przeglądarki)
const amsat = await get(AMSAT);
if (amsat.status === 200) text += '\n' + amsat.text;
else console.warn(`AMSAT: HTTP ${amsat.status || 'brak odpowiedzi'} (pomijam)`);

// 3) brakujące satelity pojedynczo z CelesTrak – tylko gdy CelesTrak nie odmówił, po kolei, z przerwą
let have = parseTLE(text);
if (group.status === 200) {
  for (const n of wanted.filter(n => !have[n])) {
    await sleep(2000);
    const r = await get(`${CELESTRAK}?CATNR=${n}&FORMAT=tle`);
    if (r.status !== 200) { problems.push(`CelesTrak CATNR=${n}: HTTP ${r.status || 'brak odpowiedzi'} – przerywam dopytywanie`); break; }
    text += '\n' + r.text;
  }
  have = parseTLE(text);
}

// wynik: tylko satelity z aplikacji; dla brakujących zostaje poprzedni (starszy) zestaw, jeśli był
const result = [], missing = [];
for (const n of wanted) {
  const t = have[n] || previous[n];
  if (!t) { missing.push(n); continue; }
  result.push(`${t.name || `NORAD ${n}`}\n${t.l1}\n${t.l2}`);
}
if (!result.length) { console.error('Brak jakichkolwiek danych – plik bez zmian.\n' + problems.join('\n')); process.exit(1); }

await writeFile(OUT, result.join('\n') + '\n');
console.log(`Zapisano ${result.length}/${wanted.length} satelitów do ${OUT}.`);
if (missing.length) console.warn(`Brak danych dla NORAD: ${missing.join(', ')}`);
if (problems.length) { console.error('Odpowiedzi inne niż HTTP 200 (sprawdź zasady CelesTrak):\n' + problems.join('\n')); process.exitCode = 1; }
