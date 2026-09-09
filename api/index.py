import os
import random
import re
import unicodedata
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "95122df100f8d10457c8e200131f3ee5")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

NON_LATIN_REGEX = re.compile(
    r'[\u0400-\u04FF'  # Kiril (Cyrillic)
    r'\u0590-\u05FF'  # İbranice (Hebrew)
    r'\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF'  # Arapça / Farsça
    r'\u0900-\u097F'  # Devanagari (Hintçe)
    r'\u0E00-\u0E7F'  # Tayca (Thai)
    r'\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF'  # Korece Hangul
    r'\u3040-\u309F\u30A0-\u30FF'  # Japonca Hiragana / Katakana
    r'\u4E00-\u9FFF\u3400-\u4DBF'  # Çince / Kanji
    r'\u0370-\u03FF'  # Yunanca
    r']'
)

INGILIZCE_OZEL_KELIMELER = {
    "the", "of", "to", "with", "from", "for", "by", "that", "this", "which",
    "who", "whose", "whom", "their", "they", "was", "were", "are", "have",
    "has", "had", "would", "could", "been", "about", "into", "through",
    "during", "before", "after", "between", "against", "himself", "herself",
    "themselves", "when", "where", "while", "because", "story", "life",
    "follows", "young", "finds", "must", "together",
    "secret", "secrets", "discovers", "takes", "place", "based"
}

def latin_alfabesi_mi(metin):
    if not metin or not str(metin).strip():
        return False
    metin_str = str(metin).strip()
    if NON_LATIN_REGEX.search(metin_str):
        return False
    for c in metin_str:
        if c.isalpha():
            name = unicodedata.name(c, "")
            if not name.startswith("LATIN"):
                return False
    return True

def ingilizce_mi(metin):
    if not metin or not str(metin).strip():
        return False
    metin_str = f" {str(metin).lower()} "
    for w in [" the ", " with ", " from ", " their ", " which ", " who ", " of ", " to ", " for ", " was ", " were ", " is ", " and "]:
        if w in metin_str:
            return True
    kelimeler = re.findall(r'\b[a-zA-ZçğıöşüÇĞİÖŞÜ]+\b', metin_str)
    eslesenler = [k for k in kelimeler if k in INGILIZCE_OZEL_KELIMELER]
    return len(eslesenler) >= 2

EN_TITLE_CACHE = {}

def tmdb_ingilizce_baslik_getir(film_id):
    if not film_id:
        return ""
    if film_id in EN_TITLE_CACHE:
        return EN_TITLE_CACHE[film_id]
    try:
        url = f"https://api.themoviedb.org/3/movie/{film_id}"
        params = {"api_key": TMDB_API_KEY, "language": "en-US"}
        res = requests.get(url, params=params, timeout=5)
        if res.ok:
            data = res.json()
            en_title = data.get("title") or data.get("original_title") or ""
            EN_TITLE_CACHE[film_id] = en_title
            return en_title
    except Exception:
        pass
    return ""

def film_basligini_duzelt(film):
    if not isinstance(film, dict):
        return film

    title = film.get("title", "")
    orig_title = film.get("original_title", "")
    film_id = film.get("id")

    # Başlık Latin alfabesi dışındaysa veya boşsa
    if not latin_alfabesi_mi(title):
        secilen_baslik = ""
        # 1. Orijinal başlık Latin mi?
        if latin_alfabesi_mi(orig_title):
            secilen_baslik = orig_title
        # 2. TMDB'den İngilizce başlığı al
        elif film_id:
            en_title = tmdb_ingilizce_baslik_getir(film_id)
            if latin_alfabesi_mi(en_title):
                secilen_baslik = en_title

        # 3. Güvenli Latin karakterli başlık ata
        if not secilen_baslik or not latin_alfabesi_mi(secilen_baslik):
            secilen_baslik = "İsimsiz Film"

        film["title"] = secilen_baslik

    # Orijinal başlık da Latin dışıysa, arayüzde Latin dışı karakterlerin sızmaması için güvenli başlığı ata
    if not latin_alfabesi_mi(film.get("original_title")):
        film["original_title"] = film["title"]

    return film

def filmleri_dogrula(filmler):
    if not filmler or not isinstance(filmler, list):
        return filmler
    for f in filmler:
        film_basligini_duzelt(f)
    return filmler

@app.route("/")
def anasayfa():
    return send_from_directory(".", "index.html")

def ingilizceyi_turkceye_cevir(metin):
    if not metin or not str(metin).strip():
        return ""
    metin = str(metin).strip()
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "qwen/qwen3-32b",
                "messages": [
                    {"role": "system", "content": "You are a professional movie translator. Translate the given text into fluent Turkish. ONLY output the translated Turkish text, no introductory words. If it is already Turkish, output it as is."},
                    {"role": "user", "content": metin},
                ],
                "temperature": 0.2,
            },
            timeout=10,
        )
        if res.ok:
            cevap = res.json()["choices"][0]["message"]["content"].strip()
            if cevap and not ingilizce_mi(cevap):
                return cevap
    except Exception:
        pass

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for client in ["dict-chrome-ex", "gtx"]:
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": client, "sl": "auto", "tl": "tr", "dt": "t", "q": metin}
            res = requests.get(url, params=params, headers=headers, timeout=8)
            if res.ok:
                ceviri_parcalari = res.json()[0]
                ceviri = "".join([parca[0] for parca in ceviri_parcalari if parca and len(parca) > 0 and parca[0]]).strip()
                if ceviri and not ingilizce_mi(ceviri):
                    return ceviri
        except Exception:
            pass

    try:
        url = "https://api.mymemory.translated.net/get"
        parcalar = [metin[i:i+400] for i in range(0, len(metin), 400)]
        sonuc_parcalari = []
        for p in parcalar:
            r = requests.get(url, params={"q": p, "langpair": "en|tr"}, timeout=5)
            if r.ok:
                tr_part = r.json().get("responseData", {}).get("translatedText", "")
                if tr_part:
                    sonuc_parcalari.append(tr_part)
        if sonuc_parcalari:
            birlesik = " ".join(sonuc_parcalari).strip()
            if birlesik and not ingilizce_mi(birlesik):
                return birlesik
    except Exception:
        pass

    return metin

@app.route("/populer")
def populer_filmler():
    rastgele_sayfa = random.randint(1, 5)
    url = "https://api.themoviedb.org/3/trending/movie/week"
    params = {"api_key": TMDB_API_KEY, "language": "tr-TR", "page": rastgele_sayfa}
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        filmler = data.get("results", [])
        filmler = filmleri_dogrula(filmler)
        random.shuffle(filmler)
        return jsonify({"results": filmler})
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route("/test-ara")
def test_ara():
    genres = request.args.get("genres", "")
    year_start = request.args.get("year_start", "")
    year_end = request.args.get("year_end", "")
    min_rating = request.args.get("min_rating", "7.0")
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "tr-TR",
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,
        "vote_average.gte": min_rating,
    }
    if genres:
        params["with_genres"] = genres
    if year_start:
        params["primary_release_date.gte"] = f"{year_start}-01-01"
    if year_end:
        params["primary_release_date.lte"] = f"{year_end}-12-31"
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if "results" in data:
            data["results"] = filmleri_dogrula(data["results"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route("/film/<int:film_id>/benzerler")
def benzer_filmler(film_id):
    url = f"https://api.themoviedb.org/3/movie/{film_id}/recommendations"
    params = {"api_key": TMDB_API_KEY, "language": "tr-TR", "page": 1}
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json().get("results", [])
        if not data:
            url_similar = f"https://api.themoviedb.org/3/movie/{film_id}/similar"
            res_similar = requests.get(url_similar, params=params, timeout=10)
            data = res_similar.json().get("results", [])
        gecerli_filmler = [m for m in data if m.get("poster_path")][:6]
        gecerli_filmler = filmleri_dogrula(gecerli_filmler)
        return jsonify({"results": gecerli_filmler})
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route("/film/<int:film_id>")
def film_detay(film_id):
    url = f"https://api.themoviedb.org/3/movie/{film_id}"
    params_tr = {"api_key": TMDB_API_KEY, "language": "tr-TR", "append_to_response": "videos,watch/providers"}
    params_en = {"api_key": TMDB_API_KEY, "language": "en-US", "append_to_response": "videos"}
    try:
        res_tr = requests.get(url, params=params_tr, timeout=10)
        res_en = requests.get(url, params=params_en, timeout=10)
        res_tr.raise_for_status()
        film_verisi = res_tr.json()
        film_en = res_en.json() if res_en.ok else {}

        original_lang = film_verisi.get("original_language", "")
        title_tr = film_verisi.get("title", "")
        title_original = film_verisi.get("original_title", "")
        en_title = film_en.get("title", "")

        # Başlık Latin alfabesi doğrulaması ve fallback
        if not latin_alfabesi_mi(title_tr) or (original_lang not in ["tr", "en"] and title_tr == title_original):
            if en_title and latin_alfabesi_mi(en_title):
                film_verisi["title"] = en_title
            elif latin_alfabesi_mi(title_original):
                film_verisi["title"] = title_original
            elif en_title:
                film_verisi["title"] = en_title
            else:
                film_verisi["title"] = "İsimsiz Film"

        if not latin_alfabesi_mi(film_verisi.get("title")):
            film_verisi["title"] = en_title if (en_title and latin_alfabesi_mi(en_title)) else "İsimsiz Film"

        if not latin_alfabesi_mi(film_verisi.get("original_title")):
            film_verisi["original_title"] = film_verisi.get("title", "")

        overview_tr = film_verisi.get("overview", "").strip()
        overview_en = film_en.get("overview", "").strip()

        # Türkçe açıklama yoksa, eksikse ya da İngilizce kaldığı tespit edilirse
        turkce_yetersiz = (
            not overview_tr
            or not latin_alfabesi_mi(overview_tr)
            or ingilizce_mi(overview_tr)
            or (overview_en and overview_tr == overview_en)
            or (len(overview_tr) < 30 and len(overview_en) >= 40)
        )

        if turkce_yetersiz:
            metin_cevirilecek = overview_en if overview_en else overview_tr
            if metin_cevirilecek:
                film_verisi["overview"] = ingilizceyi_turkceye_cevir(metin_cevirilecek)

        # Hiçbir film detayında İngilizce açıklama kalmaması için son doğrulama
        guncel_ov = film_verisi.get("overview", "").strip()
        if not guncel_ov or ingilizce_mi(guncel_ov):
            if overview_en:
                ceviri = ingilizceyi_turkceye_cevir(overview_en)
                if ceviri and not ingilizce_mi(ceviri):
                    film_verisi["overview"] = ceviri
                else:
                    film_verisi["overview"] = "Bu film için henüz Türkçe özet eklenmemiş."
            else:
                film_verisi["overview"] = "Bu film için henüz Türkçe özet eklenmemiş."

        providers_data = film_verisi.get("watch/providers", {}).get("results", {}).get("TR", {})
        flatrate = providers_data.get("flatrate", [])
        rent_or_buy = providers_data.get("rent", []) + providers_data.get("buy", [])

        film_verisi["platforms"] = {
            "stream": [{"name": p["provider_name"], "logo": f"https://image.tmdb.org/t/p/original{p['logo_path']}"} for p in flatrate],
            "buy": [{"name": p["provider_name"], "logo": f"https://image.tmdb.org/t/p/original{p['logo_path']}"} for p in rent_or_buy[:4]]
        }

        videos_tr = film_verisi.get("videos", {}).get("results", [])
        videos_en = film_en.get("videos", {}).get("results", [])
        trailer_key = None
        for v in videos_tr + videos_en:
            if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                trailer_key = v.get("key")
                break
        film_verisi["trailer_key"] = trailer_key
        return jsonify(film_verisi)
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route("/ai-ara")
def ai_ara():
    prompt = request.args.get("prompt", "").strip()
    if not prompt:
        return jsonify({"results": []})

    model_list = [
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b"
    ]
    ai_text = ""
    son_hata = ""

    for model_adi in model_list:
        try:
            ai_response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model_adi,
                    "messages": [
                        {"role": "system", "content": "Kullanıcının tarif ettiği ruh hali, atmosfer, tempo ve temalara uygun 8 bilinen film öner. Yalnızca film adlarını, her satırda bir tane olacak şekilde yaz. Numaralandırma veya açıklama ekleme."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.5,
                },
                timeout=10,
            )

            if ai_response.ok:
                ai_text = ai_response.json()["choices"][0]["message"]["content"]
                break
            else:
                son_hata = ai_response.text
        except Exception as e:
            son_hata = str(e)
            continue

    if not ai_text:
        return jsonify({"hata": f"Groq API Yanıt Vermedi. Detay: {son_hata}"}), 500

    film_isimleri = [f.strip().lstrip("-•0123456789. ") for f in ai_text.splitlines() if f.strip()]

    sonuclar = []
    for isim in film_isimleri[:8]:
        try:
            res = requests.get(
                "https://api.themoviedb.org/3/search/movie",
                params={"api_key": TMDB_API_KEY, "query": isim, "language": "tr-TR"},
                timeout=5,
            )
            if res.ok:
                data = res.json().get("results", [])
                if data:
                    sonuclar.append(data[0])
        except Exception:
            continue

    sonuclar = filmleri_dogrula(sonuclar)
    return jsonify({"results": sonuclar})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
