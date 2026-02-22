# tmdb_helper.py - fetch TMDB with cache
import os, json, time
try:
    import xbmc, xbmcaddon, xbmcvfs
except Exception:
    xbmc = None
    xbmcaddon = None
    xbmcvfs = None
import requests

# determine profile path
try:
    ADDON = xbmcaddon.Addon()
    PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
except Exception:
    PROFILE = os.path.expanduser("~/.plugin_video_addon_example_profile")

CACHE_DIR = os.path.join(PROFILE, "tmdb_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

TMDB_API_KEY = "1fc5f9008cebf466afb65b5a4e0cf5fa"
TMDB_BASE = "https://api.themoviedb.org/3"

CACHE_TTL = 7 * 24 * 3600  # 7 dias


def _cache_file(tmdb_id, media_type):
    """
    Gera caminho de cache único para filme/série.
    Exemplo:
      movie_603.json
      tv_1399.json
    """
    return os.path.join(CACHE_DIR, f"{media_type}_{tmdb_id}.json")


def _is_cache_valid(path):
    try:
        if not os.path.exists(path):
            return False
        mtime = os.path.getmtime(path)
        return (time.time() - mtime) < CACHE_TTL
    except Exception:
        return False


def _load_cache(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_tmdb(tmdb_id, media_type="movie", **kwargs):
    """
    Busca metadados do TMDB para filmes ou séries.
    Prioriza PT-BR, com fallback EN-US.
    Retorna JSON normalizado e cacheado.
    """

    if xbmc:
        xbmc.log(
            f"[SUPREME][TMDB] fetch_tmdb iniciado → id={tmdb_id}, type={media_type}",
            xbmc.LOGINFO
        )

    path = _cache_file(tmdb_id, media_type)

    # -----------------------
    # Cache
    # -----------------------
    if _is_cache_valid(path):
        cached = _load_cache(path)
        if cached:
            if xbmc:
                xbmc.log(
                    f"[SUPREME][TMDB] Cache utilizado para {media_type} {tmdb_id}",
                    xbmc.LOGINFO
                )
            return cached

    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"

    append = kwargs.get("append_to_response")
    if not append:
        append = (
            "aggregate_credits,content_ratings,images,videos,external_ids"
            if media_type == "tv"
            else "credits,release_dates,images,videos,external_ids"
        )

    params = {
        "api_key": TMDB_API_KEY,   # 🔑 chave GLOBAL
        "language": "pt-BR",
        "append_to_response": append
    }

    try:
        # -----------------------
        # Requisição PT-BR
        # -----------------------
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()

        # -----------------------
        # Fallback EN-US
        # -----------------------
        if not data.get("overview") or not (data.get("title") or data.get("name")):
            try:
                params_en = params.copy()
                params_en["language"] = "en-US"
                r2 = requests.get(url, params=params_en, timeout=12)
                r2.raise_for_status()
                data_en = r2.json()

                for key in ("overview", "title", "name"):
                    if not data.get(key) and data_en.get(key):
                        data[key] = data_en[key]

            except Exception as e_fallback:
                if xbmc:
                    xbmc.log(
                        f"[SUPREME][TMDB] Fallback EN-US falhou ({tmdb_id}): {e_fallback}",
                        xbmc.LOGWARNING
                    )

        # -----------------------
        # Normalização
        # -----------------------
        if media_type == "tv":
            data["title"] = data.get("name") or data.get("original_name") or "Sem título"
            data["original_title"] = data.get("original_name", "")
            data["year"] = int(data["first_air_date"][:4]) if data.get("first_air_date") else 0
            data["seasons_count"] = data.get("number_of_seasons", 0)
            data["episodes_count"] = data.get("number_of_episodes", 0)
        else:
            data["title"] = data.get("title") or data.get("original_title") or "Sem título"
            data["original_title"] = data.get("original_title", "")
            data["year"] = int(data["release_date"][:4]) if data.get("release_date") else 0

        data["overview"] = data.get("overview") or ""

        # -----------------------
        # Imagens
        # -----------------------
        if data.get("poster_path"):
            data["poster"] = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
        if data.get("backdrop_path"):
            data["fanart"] = f"https://image.tmdb.org/t/p/original{data['backdrop_path']}"

        # -----------------------
        # Gêneros
        # -----------------------
        data["genres_text"] = ", ".join(
            g.get("name") for g in data.get("genres", []) if g.get("name")
        )

        # -----------------------
        # Países
        # -----------------------
        if media_type == "tv":
            data["countries_text"] = ", ".join(data.get("origin_country", []))
        else:
            data["countries_text"] = ", ".join(
                c.get("iso_3166_1") for c in data.get("production_countries", [])
                if c.get("iso_3166_1")
            )

        # -----------------------
        # Estúdios
        # -----------------------
        data["studios_text"] = ", ".join(
            s.get("name") for s in data.get("production_companies", [])
            if s.get("name")
        )

        # -----------------------
        # Elenco (máx 20)
        # -----------------------
        cast_data = []
        credits = data.get("aggregate_credits") or data.get("credits", {})
        for actor in credits.get("cast", [])[:20]:
            cast_data.append({
                "name": actor.get("name"),
                "role": (
                    actor.get("roles", [{}])[0].get("character")
                    if actor.get("roles")
                    else actor.get("character", "")
                ),
                "thumb": (
                    f"https://image.tmdb.org/t/p/w185{actor['profile_path']}"
                    if actor.get("profile_path") else ""
                )
            })
        data["cast"] = cast_data

        # -----------------------
        # Equipe principal
        # -----------------------
        crew_data = []
        for member in credits.get("crew", []):
            if member.get("job") in ("Director", "Writer", "Screenplay", "Producer"):
                crew_data.append({
                    "name": member.get("name"),
                    "job": member.get("job")
                })
        data["crew"] = crew_data

        # -----------------------
        # Cache
        # -----------------------
        _save_cache(path, data)

        if xbmc:
            xbmc.log(
                f"[SUPREME][TMDB] TMDB {media_type} {tmdb_id} enriquecido com sucesso",
                xbmc.LOGINFO
            )

        return data

    except Exception as e:
        if xbmc:
            xbmc.log(
                f"[SUPREME][TMDB][ERROR] Falha ao requisitar TMDB {tmdb_id} ({media_type}): {e}",
                xbmc.LOGERROR
            )
        return _load_cache(path) or {}
        
def fetch_tmdb_movie(tmdb_id):
    """
    Wrapper para filmes usando fetch_tmdb unificado
    """
    return fetch_tmdb(tmdb_id, media_type="movie")


# -----------------------
# Função extra: traduz título (ou retorna original se não houver tradução)
# -----------------------
def translate_title(meta):
    """
    Retorna título traduzido se disponível, caso contrário fallback para original.
    """
    if not meta:
        return "Sem título"
    try:
        if meta.get("title"):
            return meta["title"]
        if meta.get("name"):
            return meta["name"]
        if meta.get("original_title"):
            return meta["original_title"]
        if meta.get("original_name"):
            return meta["original_name"]
    except Exception:
        pass
    return "Sem título"
    
def load_cached_tmdb(tmdb_id, media_type="movie"):
    """
    Lê somente do cache TMDB, sem chamar API.
    Retorna {} se não houver cache.
    """
    try:
        path = _cache_file(tmdb_id, media_type)
        if os.path.exists(path):
            cached = _load_cache(path)
            if cached:
                return cached
    except Exception as e:
        if xbmc:
            xbmc.log(f"[ADDON-ERROR] load_cached_tmdb falhou: {e}", xbmc.LOGERROR)
    return {}
    
    
def fetch_tmdb_season(tv_id, season_number):
    """
    Retorna detalhes de uma temporada com overview, imagens, elenco e equipe.
    """
    key = f"tv_{tv_id}_season_{season_number}"
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if _is_cache_valid(path):
        cached = _load_cache(path)
        if cached:
            return cached

    url = f"{TMDB_BASE}/tv/{tv_id}/season/{season_number}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR",
        "append_to_response": "aggregate_credits,images,videos,external_ids"
    }

    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()

        # fallback en-US se faltar overview
        if not data.get("overview"):
            try:
                params["language"] = "en-US"
                r2 = requests.get(url, params=params, timeout=12)
                r2.raise_for_status()
                data_en = r2.json()
                if not data.get("overview") and data_en.get("overview"):
                    data["overview"] = data_en["overview"]
            except:
                pass

        # normalização
        data["title"] = data.get("name") or f"Temporada {season_number}"
        data["overview"] = data.get("overview") or ""
        data["episodes_count"] = len(data.get("episodes", []))
        data["year"] = int(data["air_date"][:4]) if data.get("air_date") else 0

        if data.get("poster_path"):
            data["poster"] = f"https://image.tmdb.org/t/p/w500{data['poster_path']}"

        # elenco
        cast_data = []
        credits_block = data.get("aggregate_credits") or {}
        for actor in (credits_block.get("cast", [])[:20]):
            cast_data.append({
                "name": actor.get("name"),
                "role": actor.get("roles", [{}])[0].get("character") if actor.get("roles") else actor.get("character", ""),
                "thumb": f"https://image.tmdb.org/t/p/w185{actor['profile_path']}" if actor.get("profile_path") else ""
            })
        data["cast"] = cast_data

        # equipe
        crew_data = []
        for member in credits_block.get("crew", []):
            if member.get("job") in ("Director", "Writer", "Screenplay", "Producer"):
                crew_data.append({
                    "name": member["name"],
                    "job": member["job"]
                })
        data["crew"] = crew_data

        _save_cache(path, data)
        return data

    except Exception as e:
        if xbmc:
            xbmc.log(f"[ADDON-ERROR] fetch_tmdb_season falhou: {e}", xbmc.LOGERROR)
        return _load_cache(path) or {}


def fetch_tmdb_episode(tv_id, season_number, episode_number):
    """
    Retorna detalhes de um episódio (overview, elenco, imagens, etc.)
    """
    key = f"tv_{tv_id}_S{season_number}E{episode_number}"
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if _is_cache_valid(path):
        cached = _load_cache(path)
        if cached:
            return cached

    url = f"{TMDB_BASE}/tv/{tv_id}/season/{season_number}/episode/{episode_number}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "pt-BR",
        "append_to_response": "credits,images,videos,external_ids"
    }

    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()

        # fallback en-US se faltar overview
        if not data.get("overview"):
            try:
                params["language"] = "en-US"
                r2 = requests.get(url, params=params, timeout=12)
                r2.raise_for_status()
                data_en = r2.json()
                if not data.get("overview") and data_en.get("overview"):
                    data["overview"] = data_en["overview"]
            except:
                pass

        # normalização
        data["title"] = data.get("name") or f"Episódio {episode_number}"
        data["overview"] = data.get("overview") or ""
        data["runtime"] = data.get("runtime") or 0
        data["air_date"] = data.get("air_date") or ""

        if data.get("still_path"):
            data["thumb"] = f"https://image.tmdb.org/t/p/w500{data['still_path']}"

        # elenco
        cast_data = []
        credits_block = data.get("credits") or {}
        for actor in (credits_block.get("cast", [])[:15]):
            cast_data.append({
                "name": actor.get("name"),
                "role": actor.get("character", ""),
                "thumb": f"https://image.tmdb.org/t/p/w185{actor['profile_path']}" if actor.get("profile_path") else ""
            })
        data["cast"] = cast_data

        # equipe
        crew_data = []
        for member in credits_block.get("crew", []):
            if member.get("job") in ("Director", "Writer", "Screenplay", "Producer"):
                crew_data.append({
                    "name": member["name"],
                    "job": member["job"]
                })
        data["crew"] = crew_data

        _save_cache(path, data)
        return data

    except Exception as e:
        if xbmc:
            xbmc.log(f"[ADDON-ERROR] fetch_tmdb_episode falhou: {e}", xbmc.LOGERROR)
        return _load_cache(path) or {}