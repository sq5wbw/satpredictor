// Aktualizacja kopii danych TLE (tle.txt) dla SAT° Predictor.
// Uruchamiane przez GitHub Actions (.github/workflows/tle.yml) co 6 godzin.
//
// Zasady CelesTrak (https://celestrak.org/usage-policy.php): dane GP zmieniają się co 2 h, każdą
// aktualizację pobiera się raz, a po odpowiedzi innej niż HTTP 200 trzeba przestać pytać i zgłosić to
// człowiekowi. Dlatego: jedno zapytanie zbiorcze, pojedyncze satelity po kolei z przerwą, a przy odmowie
// skrypt kończy się błędem (GitHub wyśle e-mail), zostawiając poprzedni plik bez zmian.
import { readFile, writeFile } from 'node:fs/promises';
import { execSync } from 'node:child_process';

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
  } catch (e) { return { status: 0, text: `${e.message}${e.cause ? ` (${e.cause.code || e.cause.message})` : ''}` }; }
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

// komunikaty widoczne od razu w podsumowaniu uruchomienia (sekcja Annotations), także bez logowania
const note = (kind, msg) => console.log(`::${kind}::${msg.replace(/\r?\n/g, ' ')}`);
const refused = [];   // serwer odpowiedział błędem HTTP – zasady CelesTrak: przestać pytać i dać znać człowiekowi
const network = [];   // brak odpowiedzi (sieć, limit czasu) – zwykle chwilowe, dane zostają z poprzedniego razu
const problem = (who, r) => (r.status ? refused : network).push(`${who}: ${r.status ? `HTTP ${r.status}` : 'brak odpowiedzi'} ${r.text.slice(0, 160).trim()}`);
let text = '';

// uruchomienie po wgraniu index.html, a dane pobrane mniej niż 2 h temu: CelesTrak i tak ich jeszcze nie zmienił
// (powtórne zapytanie skończyłoby się odmową) – dociągamy tylko satelity, których w pliku jeszcze nie ma
let recentMin = Infinity;
try { recentMin = (Date.now() / 1000 - +execSync('git log -1 --format=%ct -- tle.txt', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()) / 60; } catch { /* brak historii */ }
const onlyMissing = process.env.GITHUB_EVENT_NAME === 'push' && recentMin < 120;
if (onlyMissing) console.log(`tle.txt zaktualizowany ${Math.round(recentMin)} min temu – pobieram tylko brakujące satelity.`);

// 1) CelesTrak – plik zbiorczy (przy braku odpowiedzi jedna ponowna próba po 30 s; odmowy HTTP nie ponawiamy)
let group = { status: 0, text: 'pominięto' };
if (!onlyMissing) {
  group = await get(`${CELESTRAK}?GROUP=amateur&FORMAT=tle`);
  if (group.status === 0) { console.log(`CelesTrak nie odpowiada (${group.text}) – ponowna próba za 30 s.`); await sleep(30000); group = await get(`${CELESTRAK}?GROUP=amateur&FORMAT=tle`); }
  if (group.status === 200) text += '\n' + group.text; else problem('CelesTrak GROUP=amateur', group);
}

// 2) AMSAT – drugi plik zbiorczy (z serwera nie ma blokady przeglądarki)
if (!onlyMissing) {
  const amsat = await get(AMSAT);
  if (amsat.status === 200) text += '\n' + amsat.text;
  else console.warn(`AMSAT: HTTP ${amsat.status || 'brak odpowiedzi'} (pomijam)`);
}

// 3) brakujące satelity pojedynczo z CelesTrak – tylko gdy CelesTrak nie odmówił, po kolei, z przerwą
let have = parseTLE(text);
if (group.status === 200 || onlyMissing) {
  const todo = wanted.filter(n => !have[n] && !(onlyMissing && previous[n]));
  for (const n of todo) {
    await sleep(2000);
    const r = await get(`${CELESTRAK}?CATNR=${n}&FORMAT=tle`);
    if (r.status !== 200) { problem(`CelesTrak CATNR=${n}`, r); break; }   // pierwsza odmowa kończy dopytywanie
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
if (!result.length) { note('error', 'Brak jakichkolwiek danych TLE – plik bez zmian. ' + [...refused, ...network].join(' | ')); process.exit(1); }

await writeFile(OUT, result.join('\n') + '\n');
console.log(`Zapisano ${result.length}/${wanted.length} satelitów do ${OUT}.`);
if (missing.length) note('warning', `Brak danych dla NORAD: ${missing.join(', ')}`);
// brak odpowiedzi: ostrzeżenie (dane z AMSAT i poprzedniego pobrania zostały zapisane), zadanie kończy się zielono
for (const p of network) note('warning', `${p} – chwilowy problem z siecią, użyto danych AMSAT i poprzedniego pobrania.`);
// odmowa HTTP: błąd – CelesTrak prosi, żeby wtedy przestać pytać i sprawdzić przyczynę (GitHub wyśle e-mail)
for (const p of refused) note('error', `${p} – CelesTrak odmówił, zob. https://celestrak.org/usage-policy.php`);
if (refused.length) process.exitCode = 1;
