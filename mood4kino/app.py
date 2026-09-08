import os
import re
import random
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "95122df100f8d10457c8e200131f3ee5")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

# Latin karakter içerip içermediğini kontrol eder (Türkçe dahil)
LATIN_RE = re.compile(r'[A-Za-zÀ-öø-ÿğüşıöçĞÜŞİÖÇ]')

def is_latin(text):
    return bool(LATIN_RE.search(text or ''))

def fetch_en_title_single(movie_id):
    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US", timeout=4)
        if r.ok:
            return r.json().get("title", "")
    except Exception:
        pass
    return ""

def latin_title_fix(filmler_tr, filmler_en):
    """tr-TR listesindeki Latin-dışı başlıkları en-US karşılığıyla değiştirir."""
    en_map = {m['id']: m.get('title', '') for m in filmler_en}
    missing_ids = []
    for film in filmler_tr:
        if not is_latin(film.get('title', '')):
            en_title = en_map.get(film['id'], '')
            if en_title and is_latin(en_title):
                film['title'] = en_title
            else:
                missing_ids.append(film)

    if missing_ids:
        with ThreadPoolExecutor(max_workers=min(8, len(missing_ids))) as ex:
            futs = {ex.submit(fetch_en_title_single, f['id']): f for f in missing_ids}
            for fut, f in futs.items():
                res_title = fut.result()
                if res_title and is_latin(res_title):
                    f['title'] = res_title

    return filmler_tr

@app.route("/")
def anasayfa():
    return send_from_directory(".", "index.html")

def ingilizceyi_turkceye_cevir(metin):
    if not metin:
        return ""
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
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
            if cevap:
                return cevap
    except Exception:
        pass

    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "tr", "dt": "t", "q": metin}
        res = requests.get(url, params=params, timeout=10)
        if res.ok:
            ceviri_parcalari = res.json()[0]
            return "".join([parca[0] for parca in ceviri_parcalari])
    except Exception:
        pass
    return metin

@app.route("/populer")
def populer_filmler():
    rastgele_sayfa = random.randint(1, 5)
    url = "https://api.themoviedb.org/3/trending/movie/week"
    params_tr = {"api_key": TMDB_API_KEY, "language": "tr-TR", "page": rastgele_sayfa}
    params_en = {"api_key": TMDB_API_KEY, "language": "en-US", "page": rastgele_sayfa}
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_tr = ex.submit(requests.get, url, params=params_tr, timeout=10)
            fut_en = ex.submit(requests.get, url, params=params_en, timeout=10)
            filmler_tr = fut_tr.result().json().get("results", [])
            filmler_en = fut_en.result().json().get("results", [])
        filmler = latin_title_fix(filmler_tr, filmler_en)
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
    base_params = {
        "api_key": TMDB_API_KEY,
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,
        "vote_average.gte": min_rating,
    }
    if genres:
        base_params["with_genres"] = genres
    if year_start:
        base_params["primary_release_date.gte"] = f"{year_start}-01-01"
    if year_end:
        base_params["primary_release_date.lte"] = f"{year_end}-12-31"
    params_tr = {**base_params, "language": "tr-TR"}
    params_en = {**base_params, "language": "en-US"}
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_tr = ex.submit(requests.get, url, params=params_tr, timeout=10)
            fut_en = ex.submit(requests.get, url, params=params_en, timeout=10)
            filmler_tr = fut_tr.result().json().get("results", [])
            filmler_en = fut_en.result().json().get("results", [])
        filmler = latin_title_fix(filmler_tr, filmler_en)
        return jsonify({"results": filmler})
    except Exception as e:
        return jsonify({"hata": str(e)}), 500

@app.route("/film/<int:film_id>/benzerler")
def benzer_filmler(film_id):
    url = f"https://api.themoviedb.org/3/movie/{film_id}/recommendations"
    params_tr = {"api_key": TMDB_API_KEY, "language": "tr-TR", "page": 1}
    params_en = {"api_key": TMDB_API_KEY, "language": "en-US", "page": 1}
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_tr = ex.submit(requests.get, url, params=params_tr, timeout=10)
            fut_en = ex.submit(requests.get, url, params=params_en, timeout=10)
            data_tr = fut_tr.result().json().get("results", [])
            data_en = fut_en.result().json().get("results", [])
        if not data_tr:
            url_similar = f"https://api.themoviedb.org/3/movie/{film_id}/similar"
            with ThreadPoolExecutor(max_workers=2) as ex:
                fut_tr = ex.submit(requests.get, url_similar, params=params_tr, timeout=10)
                fut_en = ex.submit(requests.get, url_similar, params=params_en, timeout=10)
                data_tr = fut_tr.result().json().get("results", [])
                data_en = fut_en.result().json().get("results", [])
        data = latin_title_fix(data_tr, data_en)
        gecerli_filmler = [m for m in data if m.get("poster_path")][:6]
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

        title_tr = film_verisi.get("title", "")

        # Başlık Latin karakter içermiyorsa (Korece, Japonca, Çince vb.) İngilizceyi kullan
        if not is_latin(title_tr):
            en_title = film_en.get("title", "")
            if en_title:
                film_verisi["title"] = en_title

        overview_tr = film_verisi.get("overview", "").strip()
        overview_en = film_en.get("overview", "").strip()
        ingilizce_belirtiler = [" the ", " and ", " is ", " to ", " of ", " a ", " in ", " for "]

        # Türkçe özet yoksa, İngilizce kelimeler içeriyorsa veya Latin dışıysa çevir
        if (not overview_tr
                or any(word in f" {overview_tr.lower()} " for word in ingilizce_belirtiler)
                or not is_latin(overview_tr)):
            metin_cevirilecek = overview_en if overview_en else overview_tr
            if metin_cevirilecek:
                film_verisi["overview"] = ingilizceyi_turkceye_cevir(metin_cevirilecek)

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

    # 1. Gerçek ve dinamik AI önerileri için canlı mood4kino AI servisini çağır
    try:
        live_res = requests.get(
            f"https://mood4kino.online/ai-ara?prompt={requests.utils.quote(prompt)}",
            timeout=10
        )
        if live_res.ok:
            live_data = live_res.json()
            if live_data.get("results") and len(live_data["results"]) > 0:
                return jsonify(live_data)
    except Exception:
        pass

    # 2. Yerel Groq API (eğer geçerli bir ortam değişkeni GROQ_API_KEY tanımlıysa)
    model_list = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama3-8b-8192",
        "mixtral-8x7b-32768"
    ]
    ai_text = ""

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
                timeout=5,
            )

            if ai_response.ok:
                ai_text = ai_response.json()["choices"][0]["message"]["content"]
                break
        except Exception:
            continue

    if not ai_text:
        prompt_kucuk = prompt.lower()
        if any(w in prompt_kucuk for w in ["yağmur", "sakin", "yol", "huzur", "dinlendirici", "yolculuk"]):
            film_isimleri = ["Captain Fantastic", "Into the Wild", "Nomadland", "Lost in Translation", "Green Book", "The Secret Life of Walter Mitty", "Paterson", "Her"]
        elif any(w in prompt_kucuk for w in ["ters köşe", "zihin", "beyin", "şaşırtıcı", "mindfuck", "twist"]):
            film_isimleri = ["Fight Club", "The Prestige", "Shutter Island", "Memento", "The Sixth Sense", "Oldboy", "Primal Fear", "Incendies"]
        elif any(w in prompt_kucuk for w in ["korku", "gerilim", "karanlık", "katil", "gizem", "paranormal", "korkunç"]):
            film_isimleri = ["Hereditary", "Get Out", "The Conjuring", "A Quiet Place", "It Follows", "Midsommar", "The Babadook", "Split"]
        elif any(w in prompt_kucuk for w in ["kahkaha", "komedi", "neşeli", "eğlenceli", "komik", "gülmek", "eğlence"]):
            film_isimleri = ["The Hangover", "Superbad", "Deadpool", "Knives Out", "Groundhog Day", "Monty Python and the Holy Grail", "Shaun of the Dead", "Crazy Stupid Love"]
        elif any(w in prompt_kucuk for w in ["uzay", "bilim kurgu", "gelecek", "yapay zeka", "sci-fi", "robot"]):
            film_isimleri = ["Interstellar", "Blade Runner 2049", "Arrival", "Dune", "The Matrix", "Ex Machina", "Inception", "2001: A Space Odyssey"]
        elif any(w in prompt_kucuk for w in ["aşk", "romantik", "sevgili", "duygusal", "tutku", "romans"]):
            film_isimleri = ["La La Land", "About Time", "Eternal Sunshine of the Spotless Mind", "Before Sunrise", "500 Days of Summer", "The Notebook", "Pride & Prejudice", "Past Lives"]
        elif any(w in prompt_kucuk for w in ["aksiyon", "heyecan", "hızlı", "dövüş", "suç", "mafya", "kovalamaca"]):
            film_isimleri = ["Mad Max: Fury Road", "John Wick", "The Dark Knight", "Gladiator", "The Godfather", "Pulp Fiction", "Heat", "Mission: Impossible"]
        elif any(w in prompt_kucuk for w in ["animasyon", "çizgi", "çocuk", "aile", "pixar"]):
            film_isimleri = ["Spirited Away", "Coco", "Spider-Man: Into the Spider-Verse", "WALL-E", "Inside Out", "Up", "Ratatouille", "Soul"]
        elif any(w in prompt_kucuk for w in ["sıcak", "dram", "samimi", "hayat", "dostluk"]):
            film_isimleri = ["The Shawshank Redemption", "Forrest Gump", "Good Will Hunting", "Dead Poets Society", "The Intouchables", "Life Is Beautiful", "A Beautiful Mind", "Whiplash"]
        else:
            film_isimleri = ["Interstellar", "Dune", "Blade Runner 2049", "The Shawshank Redemption", "Forrest Gump", "Pulp Fiction", "Fight Club", "Inception"]
    else:
        film_isimleri = [f.strip().lstrip("-•0123456789. ") for f in ai_text.splitlines() if f.strip()]

    sonuclar = []
    for isim in film_isimleri[:8]:
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                fut_tr = ex.submit(requests.get,
                    "https://api.themoviedb.org/3/search/movie",
                    params={"api_key": TMDB_API_KEY, "query": isim, "language": "tr-TR"},
                    timeout=5)
                fut_en = ex.submit(requests.get,
                    "https://api.themoviedb.org/3/search/movie",
                    params={"api_key": TMDB_API_KEY, "query": isim, "language": "en-US"},
                    timeout=5)
                data_tr = fut_tr.result().json().get("results", []) if fut_tr.result().ok else []
                data_en = fut_en.result().json().get("results", []) if fut_en.result().ok else []
            if data_tr:
                film = data_tr[0]
                # Latin dışı başlık varsa en-US ile değiştir
                if not is_latin(film.get("title", "")) and data_en:
                    en_film = next((m for m in data_en if m["id"] == film["id"]), None)
                    if en_film:
                        film["title"] = en_film.get("title", film["title"])
                sonuclar.append(film)
        except Exception:
            continue

    return jsonify({"results": sonuclar})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
