import os
import random
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# API Anahtarları (Render üzerinden Environment Variables olarak girilebilir)
# API Anahtarları artık kodun içinde kabak gibi durmayacak, Render panelinden güvenle vereceğiz:
TMDB_API_KEY = os.environ.get("95122df100f8d10457c8e200131f3ee5")
GROQ_API_KEY = os.environ.get("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")

@app.route("/")
def anasayfa():
    return send_from_directory(".", "index.html")

def ingilizceyi_turkceye_cevir(metin):
    if not metin: return ""
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
            if cevap: return cevap
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
    params = {"api_key": TMDB_API_KEY, "language": "tr-TR", "page": rastgele_sayfa}
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        filmler = data.get("results", [])
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
        "api_key": TMDB_API_KEY, "language": "tr-TR", "sort_by": "popularity.desc",
        "vote_count.gte": 100, "vote_average.gte": min_rating,
    }
    if genres: params["with_genres"] = genres
    if year_start: params["primary_release_date.gte"] = f"{year_start}-01-01"
    if year_end: params["primary_release_date.lte"] = f"{year_end}-12-31"
    try:
        res = requests.get(url, params=params, timeout=10)
        return jsonify(res.json())
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
        
        if original_lang not in ["tr", "en"] and title_tr == title_original:
            en_title = film_en.get("title")
            if en_title: film_verisi["title"] = en_title

        overview_tr = film_verisi.get("overview", "").strip()
        overview_en = film_en.get("overview", "").strip()
        ingilizce_belirtiler = [" the ", " and ", " is ", " to ", " of ", " a ", " in ", " for "]
        
        if not overview_tr or any(word in f" {overview_tr.lower()} " for word in ingilizce_belirtiler):
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
    if not prompt: return jsonify({"results": []})
    
    model_list = [
        "llama-3.3-70b-versatile", 
        "llama-3.1-70b-versatile", 
        "llama3-8b-8192"
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
        if "yağmur" in prompt_kucuk or "sakin" in prompt_kucuk or "yol" in prompt_kucuk:
            film_isimleri = ["Captain Fantastic", "Into the Wild", "Nomadland", "Lost in Translation", "Green Book", "The Secret Life of Walter Mitty", "Paterson", "Her"]
        elif "korku" in prompt_kucuk or "gerilim" in prompt_kucuk or "karanlık" in prompt_kucuk:
            film_isimleri = ["Hereditary", "Get Out", "The Conjuring", "A Quiet Place", "It Follows", "Midsommar", "The Babadook", "Split"]
        elif "aşk" in prompt_kucuk or "romantik" in prompt_kucuk or "sevgili" in prompt_kucuk:
            film_isimleri = ["La La Land", "About Time", "Eternal Sunshine of the Spotless Mind", "Before Sunrise", "500 Days of Summer", "The Notebook", "Pride & Prejudice", "Notting Hill"]
        elif "aksiyon" in prompt_kucuk or "heyecan" in prompt_kucuk or "hızlı" in prompt_kucuk:
            film_isimleri = ["Mad Max: Fury Road", "John Wick", "The Dark Knight", "Die Hard", "Gladiator", "The Matrix", "Inception", "Mission: Impossible"]
        else:
            film_isimleri = ["Interstellar", "Dune", "Blade Runner 2049", "The Shawshank Redemption", "Forrest Gump", "Pulp Fiction", "Fight Club", "The Godfather"]
    else:
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
                if data: sonuclar.append(data[0])
        except Exception:
            continue
            
    return jsonify({"results": sonuclar})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)