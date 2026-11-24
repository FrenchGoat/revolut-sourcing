import os, re, json, time, random, datetime, unicodedata, requests, gspread
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
from google.oauth2.service_account import Credentials
requests.packages.urllib3.disable_warnings()

SHEET_ID = "1-n2TBYlov-eWXgwYow0mn9U8wozMFMMxTqJCPR9VAZI"
OBJECTIF = 1000
# Secteurs (codes NAF) très exposés aux devises : négoce, import, export, luxe, industrie
NAF = ["46.41Z","46.42Z","46.43Z","46.44Z","46.45Z","46.46Z","46.47Z","46.48Z","46.49Z",
       "46.51Z","46.52Z","46.61Z","46.62Z","46.63Z","46.69B","46.69C","46.72Z","46.73A",
       "46.75Z","46.76Z","46.34Z","46.37Z","46.38B","46.31Z","46.33Z","46.36Z","46.90Z",
       "11.01Z","11.02A","11.02B","10.83Z","10.82Z","15.12Z","14.13Z","32.12Z","32.30Z",
       "32.40Z","32.50A","20.42Z","20.30Z","22.29A","25.73A","26.51B","27.40Z","28.29B",
       "28.30Z","29.32Z","30.12Z","30.30Z","31.09B","13.92Z","17.21A","23.41Z","47.91B"]
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:fr|com|eu|net|org)\b")
BAN = ("example","exemple","sentry","wix","ovh","png","jpg","webp","votre","nom@","dpo@","rgpd",
       "privacy","gdpr","career","recrut","job","noreply","no-reply","compta","newsletter","rh@",
       "hr@","candidature","webmaster","data","unsubscribe","security","billing")
FORMES = r"\b(sas|sasu|sarl|sa|eurl|sci|snc|societe|ste|ets|etablissements|groupe|france|holding)\b"

def entreprises(naf, page):
    try:
        r = requests.get("https://recherche-entreprises.api.gouv.fr/search",
                         params={"activite_principale": naf, "page": page, "per_page": 25,
                                 "etat_administratif": "A"}, timeout=15)
        time.sleep(0.2)
        return [e.get("nom_complet", "") for e in r.json().get("results", [])]
    except Exception:
        return []

def slug(nom):
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(FORMES, " ", s)
    mots = re.findall(r"[a-z0-9]+", s)
    return mots

def get(u):
    try:
        r = requests.get(u, headers=H, timeout=5, verify=False)
        return (r.url, r.text) if r.ok and len(r.text) > 800 else (None, None)
    except Exception:
        return None, None

def scan(nom):
    mots = slug(nom)
    if not mots or len("".join(mots)) < 3:
        return []
    bases = {"".join(mots), "-".join(mots)}
    for base in bases:
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
            return sorted(x.lower() for x in m
                          if host in x.lower().split("@")[1]
                          and not any(b in x.lower() for b in BAN))[:3]
    return []

def main():
    creds = Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_CREDS"]),
            scopes=["https://www.googleapis.com/auth/spreadsheets"])
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).sheet1
    deja = set(v.strip().lower() for v in ws.col_values(1))
    jour = datetime.date.today().toordinal()
    random.seed(jour)
    nafs = NAF[:]; random.shuffle(nafs)
    nouveaux, page = [], 1 + (jour % 20) * 5
    while len(nouveaux) < OBJECTIF and page < 400:
        noms = []
        for naf in nafs:
            for p in range(page, page + 5):
                noms += entreprises(naf, p)
        noms = list(dict.fromkeys(n for n in noms if n))
        print(f"Pages {page}-{page+4} : {len(noms)} entreprises à tester")
        with ThreadPoolExecutor(60) as ex:
            for mails in ex.map(scan, noms):
                for e in mails:
                    if e not in deja:
                        deja.add(e); nouveaux.append(e)
        print(f"Total nouveaux : {len(nouveaux)}")
        if nouveaux:
            ws.append_rows([[e, str(datetime.date.today())] for e in nouveaux[-5000:]
                            if e not in getattr(main, "envoyes", set())])
            main.envoyes = getattr(main, "envoyes", set()) | set(nouveaux)
        page += 5
    print(f"Terminé : {len(nouveaux)} nouvelles adresses ajoutées")

if __name__ == "__main__":
    main()
