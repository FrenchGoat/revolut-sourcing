import os, re, json, time, random, datetime, unicodedata, requests, gspread
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.service_account import Credentials
requests.packages.urllib3.disable_warnings()

SHEET_ID = "1-n2TBYlov-eWXgwYow0mn9U8wozMFMMxTqJCPR9VAZI"
OBJECTIF = 1000
# PME de 10 à 249 salariés
TAILLES = "11,12,21,22,31"

# Négoce de gros (quasi complet)
NEGOCE = ["46.11Z","46.12A","46.12B","46.13Z","46.14Z","46.15Z","46.16Z","46.17A","46.17B",
  "46.18Z","46.19A","46.19B","46.21Z","46.22Z","46.23Z","46.24Z","46.31Z","46.32A","46.32B",
  "46.32C","46.33Z","46.34Z","46.35Z","46.36Z","46.37Z","46.38A","46.38B","46.39A","46.39B",
  "46.41Z","46.42Z","46.43Z","46.44Z","46.45Z","46.46Z","46.47Z","46.48Z","46.49Z","46.51Z",
  "46.52Z","46.61Z","46.62Z","46.63Z","46.64Z","46.65Z","46.66Z","46.69A","46.69B","46.69C",
  "46.71Z","46.72Z","46.73A","46.73B","46.74A","46.74B","46.75Z","46.76Z","46.77Z","46.90Z"]
# Industrie manufacturière (niches)
INDUSTRIE = ["10.13A","10.13B","10.20Z","10.32Z","10.39A","10.39B","10.41A","10.51C","10.52Z",
  "10.61A","10.62Z","10.71B","10.72Z","10.73Z","10.82Z","10.83Z","10.84Z","10.86Z","10.89Z",
  "11.01Z","11.02A","11.02B","11.03Z","11.05Z","11.07A","13.10Z","13.20Z","13.30Z","13.91Z",
  "13.92Z","13.93Z","13.94Z","13.95Z","13.96Z","13.99Z","14.12Z","14.13Z","14.14Z","14.19Z",
  "14.20Z","14.31Z","15.11Z","15.12Z","15.20Z","16.10A","16.23Z","16.24Z","16.29Z","17.12Z",
  "17.21A","17.21B","17.22Z","17.23Z","17.29Z","20.12Z","20.13B","20.14Z","20.16Z","20.20Z",
  "20.30Z","20.41Z","20.42Z","20.52Z","20.53Z","20.59Z","21.10Z","21.20Z","22.11Z","22.19Z",
  "22.21Z","22.22Z","22.23Z","22.29A","22.29B","23.12Z","23.13Z","23.19Z","23.41Z","23.42Z",
  "23.49Z","23.70Z","23.99Z","24.20Z","24.41Z","24.42Z","24.44Z","25.11Z","25.12Z","25.29Z",
  "25.40Z","25.50A","25.61Z","25.62A","25.62B","25.71Z","25.72Z","25.73A","25.73B","25.93Z",
  "25.94Z","25.99A","25.99B","26.11Z","26.12Z","26.20Z","26.30Z","26.40Z","26.51A","26.51B",
  "26.60Z","26.70Z","27.11Z","27.12Z","27.20Z","27.32Z","27.33Z","27.40Z","27.51Z","27.52Z",
  "27.90Z","28.11Z","28.12Z","28.13Z","28.14Z","28.15Z","28.21Z","28.22Z","28.23Z","28.24Z",
  "28.25Z","28.29A","28.29B","28.30Z","28.41Z","28.49Z","28.92Z","28.93Z","28.94Z","28.95Z",
  "28.96Z","28.99A","28.99B","29.20Z","29.31Z","29.32Z","30.11Z","30.12Z","30.20Z","30.30Z",
  "30.92Z","30.99Z","31.01Z","31.02Z","31.03Z","31.09A","31.09B","32.11Z","32.12Z","32.13Z",
  "32.20Z","32.30Z","32.40Z","32.50A","32.50B","32.91Z","32.99Z","33.12Z","33.16Z"]
NAF = NEGOCE + INDUSTRIE

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:fr|com|eu|net|org)\b")
BAN = ("example","exemple","sentry","wix","ovh","png","jpg","webp","votre","nom@","dpo@","rgpd",
       "privacy","gdpr","career","recrut","job","noreply","no-reply","compta","newsletter","rh@",
       "hr@","candidature","webmaster","data","unsubscribe","security","billing","%")
FORMES = r"\b(sas|sasu|sarl|sa|eurl|sci|snc|societe|ste|ets|etablissements|groupe|france|holding|et|cie)\b"

def entreprises(naf, page):
    try:
        r = requests.get("https://recherche-entreprises.api.gouv.fr/search",
            params={"activite_principale": naf, "tranche_effectif_salarie": TAILLES,
                    "etat_administratif": "A", "page": page, "per_page": 25}, timeout=15)
        time.sleep(0.15)
        if r.status_code == 429:
            time.sleep(5); return entreprises(naf, page)
        if r.status_code != 200:
            return []
        return [(e.get("nom_complet", ""), naf) for e in r.json().get("results", [])]
    except Exception:
        return []

def slug(nom):
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(FORMES, " ", s)
    return re.findall(r"[a-z0-9]+", s)

def get(u):
    try:
        r = requests.get(u, headers=H, timeout=5, verify=False)
        return (r.url, r.text) if r.ok and len(r.text) > 800 else (None, None)
    except Exception:
        return None, None

def scan(item):
    nom, naf = item
    mots = slug(nom)
    if not mots or len("".join(mots)) < 3:
        return nom, naf, []
    for base in dict.fromkeys(["".join(mots), "-".join(mots), mots[0]]):
        if len(base) < 4:
            continue
        for ext in (".fr", ".com"):
            u, t = get(f"https://www.{base}{ext}")
            if not u or mots[0][:4] not in t.lower():
                continue
            m = set(EMAIL.findall(t))
            root = f"{urlparse(u).scheme}://{urlparse(u).netloc}"
            liens = {urljoin(u, h) for h in re.findall(r'href="([^"]+)"', t)
                     if "contact" in h.lower() or "mentions" in h.lower()}
            for l in list(liens)[:3] + [root + "/contact"]:
                _, t2 = get(l)
                if t2:
                    m |= set(EMAIL.findall(t2))
            host = urlparse(u).netloc.replace("www.", "").split(".")[0][:5]
            mails = sorted(x.lower() for x in m
                           if host in x.lower().split("@")[1]
                           and not any(b in x.lower() for b in BAN))[:3]
            return nom, naf, mails
    return nom, naf, []

def main():
    creds = Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_CREDS"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"])
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet("Feuille 1")
    deja = set(v.strip().lower() for v in ws.col_values(1))
    jour = datetime.date.today()
    random.seed(jour.toordinal())
    nafs = NAF[:]; random.shuffle(nafs)
    debut = time.time()
    total, page0 = 0, 1 + (jour.toordinal() % 10) * 4
    for page in range(page0, page0 + 400, 2):
        if total >= OBJECTIF or time.time() - debut > 5.3 * 3600:
            break
        lot = []
        for naf in nafs:
            lot += entreprises(naf, page) + entreprises(naf, page + 1)
        lot = list({n: (n, f) for n, f in lot if n}.values())
        if not lot:
            print("Plus aucune entreprise renvoyée par l'annuaire, arrêt.")
            break
        print(f"Pages {page}-{page+1} : {len(lot)} entreprises à tester")
        lignes = []
        with ThreadPoolExecutor(80) as ex:
            for nom, naf, mails in ex.map(scan, lot):
                for e in mails:
                    if e not in deja:
                        deja.add(e)
                        lignes.append([e, str(jour), nom, naf])
        if lignes:
            ws.append_rows(lignes, value_input_option="RAW")
        total += len(lignes)
        print(f"+{len(lignes)} adresses, total du jour : {total}")
    print(f"Terminé : {total} nouvelles adresses ajoutées")

if __name__ == "__main__":
    main()
