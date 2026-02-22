# -*- coding: utf-8 -*-
import xbmc
import xbmcplugin
import xbmcgui
import sys
import requests
import urllib.parse as urllib_parse
import hashlib
import json
import traceback
import xbmcaddon
import hashlib
import json

_cache = {}  # garante que existe em utils

# Addon object
addon = xbmcaddon.Addon()

# Nome do addon (usado em favoritos)
name_addon_info = addon.getAddonInfo('name')

# Lista de favoritos
FAV = []

# Lista de sources
SOURCES = []

# urllib compatível
try:
    import urllib.parse as urllib_parse
except ImportError:
    import urllib as urllib_parse
    
def _ensure_items(payload):
    import xbmc
    xbmc.log(f"[ADDON-DEBUG][utils] _ensure_items recebido: {repr(payload)}", xbmc.LOGINFO)


def compute_cache_key(items, hint=None):
    """
    Gera uma chave de cache estável baseada nos items.
    Se hint for passado, ele entra no prefixo da chave.
    """
    try:
        base = json.dumps(items, sort_keys=True)  # serializa os items
    except Exception:
        base = str(items)
    raw_key = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"{hint or 'default'}_{raw_key}"
    
def _log_debug(msg):
    xbmc.log(f"[ADDON-DEBUG][utils] {msg}", xbmc.LOGINFO)

def _log_error(msg):
    xbmc.log(f"[ADDON-ERROR][utils] {msg}", xbmc.LOGERROR)

# Base do plugin (argumento 0 do Kodi)
PLUGIN_BASE = sys.argv[0]

addon      = xbmcaddon.Addon()
addon_name = addon.getAddonInfo("name")
icon = addon.getAddonInfo("icon")
# Cache globals
# --- Cache globals ---
import xbmcaddon, xbmcvfs, os

addon      = xbmcaddon.Addon()
addon_id   = addon.getAddonInfo('id')
addon_path = xbmcvfs.translatePath(f"special://profile/addon_data/{addon_id}")

# garante que a pasta existe
if not xbmcvfs.exists(addon_path):
    xbmcvfs.mkdirs(addon_path)

CACHE_MODE   = True
CACHE_FILE   = os.path.join(addon_path, "addon_cache")  # caminho absoluto
CACHE_EXPIRE = 60 * 60 * 6  # 6 horas

try:
    import requests_cache
    try:
        requests_cache.install_cache(CACHE_FILE, backend="sqlite", expire_after=CACHE_EXPIRE)
        ENABLE_CACHE = True
    except Exception as e:
        xbmc.log(f"[ADDON-DEBUG][utils] Falha ao iniciar cache: {e}", xbmc.LOGWARNING)
        ENABLE_CACHE = False
except ImportError:
    ENABLE_CACHE = False

def addon_log(msg, level=xbmc.LOGINFO):
    try:
        xbmc.log(f"[ADDON-DEBUG][utils] {msg}", level)
    except Exception:
        pass
        
def safe_log(message):
    try:
        addon_log(str(message))
    except Exception:
        try:
            addon_log(message.encode("utf-8", "ignore").decode("utf-8"))
        except Exception:
            addon_log("[LOG-ERROR] Falha ao imprimir mensagem")
            
def safe_lower(value):
    """Converte qualquer valor em minúsculas de forma segura."""
    if isinstance(value, dict):
        value = value.get("name") or value.get("title") or ""
    if value is None:
        return ""
    return str(value).lower()

import unicodedata

def normalize(text):
    """
    🔰 SUPREME - Normaliza texto para comparação segura
    ✔ Remove acentos
    ✔ Remove espaços extras
    ✔ Converte para minúsculo
    """
    if not isinstance(text, str):
        return ""

    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    return text
    
def get_kversion():
    """
    Retorna a versão principal do Kodi como inteiro.
    Exemplo: 20.2 -> 20
    """
    try:
        version_str = xbmc.getInfoLabel("System.BuildVersion")
        version_major = int(version_str.split(".")[0])
        return version_major
    except Exception:
        # fallback para não quebrar caso xbmc retorne vazio
        return 18            
        
def buildMenuFromJson_supreme(json_data, fanart, menu_name="Menu SUPREME"):
    import xbmc, xbmcgui, xbmcplugin, json, os, sys
    from xbmcvfs import translatePath as TRANSLATEPATH

    try:
        from resources.lib import tmdb_helper
        from resources.lib.utils import enrich_with_cache
        import xbmcaddon
    except Exception as e_imp:
        xbmc.log(f"[SUPREME][FLOW] Falha nos imports base: {e_imp}", xbmc.LOGERROR)
        return False

    # --- Normalização JSON ---
    try:
        if isinstance(json_data, str):
            json_data = json.loads(json_data)
    except Exception as e_json:
        xbmc.log(f"[SUPREME][FLOW] Erro ao decodificar JSON: {e_json}", xbmc.LOGERROR)
        return False

    if isinstance(json_data, dict):
        items = json_data.get("items") or json_data.get("channels") or list(json_data.values())
    elif isinstance(json_data, list):
        items = json_data
    else:
        items = []

    if not items:
        xbmc.log("[SUPREME][FLOW] Nenhum item recebido", xbmc.LOGWARNING)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return False

    xbmc.log(f"[SUPREME][FLOW] buildMenuFromJson_supreme iniciado ({len(items)} itens)", xbmc.LOGINFO)

    # ------------------------------------------------------------------
    # 🔥 OTIMIZAÇÃO PRINCIPAL: enriquecer TODOS de uma vez
    # ------------------------------------------------------------------
    try:
        items = enrich_with_cache(items)
        xbmc.log("[SUPREME][CACHE] enrich_with_cache aplicado em lote", xbmc.LOGINFO)
    except Exception as e_enrich:
        xbmc.log(f"[SUPREME][CACHE] Falha no enrich em lote: {e_enrich}", xbmc.LOGERROR)

    enriched = []

    # --- Processamento leve (SEM leitura manual de cache) ---
    for i in items:
        try:
            enriched.append(i)
        except Exception as e_item:
            xbmc.log(f"[SUPREME][FLOW] Erro ao processar item {i.get('title')}: {e_item}", xbmc.LOGERROR)
            enriched.append(i)

    # --- Montagem dos ListItems ---
    for item in enriched:
        try:
            title = item.get("title") or item.get("name") or "Sem título"
            plot = item.get("overview") or item.get("plot") or "Sem descrição disponível."
            year = item.get("year") or (item.get("release_date", "")[:4] if item.get("release_date") else "")
            rating = float(item.get("rating") or item.get("vote_average") or 0)

            mpaa_rating = "N/A"
            try:
                release_data = item.get("release_dates", {}).get("results", [])
                for r in release_data:
                    if r.get("iso_3166_1") in ["US", "BR"]:
                        for rd in r.get("release_dates", []):
                            cert = rd.get("certification")
                            if cert:
                                map_cert = {
                                    "G": "Livre", "L": "Livre",
                                    "PG": "10", "PG-13": "12",
                                    "R": "16", "NC-17": "18",
                                    "12": "12", "14": "14",
                                    "16": "16", "18": "18"
                                }
                                mpaa_rating = map_cert.get(cert, cert)
                                break
                        if mpaa_rating != "N/A":
                            break
            except Exception:
                pass

            cast_data = item.get("credits", {}).get("cast") or item.get("cast") or []
            cast_dict = []
            for c in cast_data[:10]:
                name = c.get("name")
                if not name:
                    continue
                role = c.get("character") or c.get("role") or ""
                profile = c.get("profile_path") or ""
                photo = f"https://image.tmdb.org/t/p/w185{profile}" if profile else ""
                cast_dict.append({"name": name, "role": role, "thumbnail": photo})

            poster = item.get("poster") or item.get("poster_path") or ""
            fan = item.get("fanart") or item.get("backdrop_path") or fanart

            if poster and not poster.startswith("http"):
                poster = f"https://image.tmdb.org/t/p/w500{poster}"
            if fan and not fan.startswith("http"):
                fan = f"https://image.tmdb.org/t/p/original{fan}"

            directors = []
            writers = []
            crew = item.get("credits", {}).get("crew") or item.get("crew") or []
            for p in crew:
                job = p.get("job", "").lower()
                if "director" in job:
                    directors.append(p.get("name"))
                if "writer" in job or "screenplay" in job:
                    writers.append(p.get("name"))

            liz = xbmcgui.ListItem(label=title)
            tag = liz.getVideoInfoTag()
            tag.setTitle(title)
            tag.setPlot(plot)

            if year:
                try:
                    tag.setYear(int(year))
                except:
                    pass

            if rating:
                tag.setRating(rating)

            tag.setMpaa(mpaa_rating)

            genres = item.get("genres") or []
            if isinstance(genres, list):
                tag.setGenres([g.get("name") for g in genres if isinstance(g, dict) and g.get("name")])

            countries = item.get("production_countries") or []
            if isinstance(countries, list):
                tag.setCountries([c.get("name") for c in countries if isinstance(c, dict) and c.get("name")])

            studios = item.get("production_companies") or []
            if isinstance(studios, list):
                tag.setStudios([s.get("name") for s in studios if isinstance(s, dict) and s.get("name")])

            if directors:
                tag.setDirectors(directors)
            if writers:
                tag.setWriters(writers)

            votes = item.get("vote_count") or item.get("votes")
            if votes:
                try:
                    tag.setVotes(int(votes))
                except:
                    pass

            premiered = item.get("release_date") or item.get("first_air_date")
            if premiered:
                tag.setPremiered(premiered)

            if cast_dict:
                try:
                    liz.setCast(cast_dict)
                except:
                    pass

            liz.setArt({
                "poster": poster,
                "thumb": poster,
                "fanart": fan
            })

            xbmcplugin.addDirectoryItem(
                handle=int(sys.argv[1]),
                url=item.get("url", ""),
                listitem=liz,
                isFolder=False
            )

        except Exception as e_final:
            xbmc.log(f"[SUPREME][FLOW] Erro ao montar item {item.get('title')}: {e_final}", xbmc.LOGERROR)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))
    xbmc.log(f"[SUPREME][FLOW] buildMenuFromJson_supreme finalizado ({len(enriched)} itens)", xbmc.LOGINFO)
    return True
        
def enrich_with_cache(items):
    """
    ⚡ SUPREME FULL METADATA - OTIMIZADO
    - Não chama API
    - Usa cache em memória
    - Usa cache em disco
    - Copia apenas campos necessários
    - Mantém compatibilidade total
    - Performance otimizada para Android
    """

    import os, json, xbmc
    from xbmcvfs import translatePath as TRANSLATEPATH
    import xbmcaddon

    global _cache
    if "_cache" not in globals():
        _cache = {}

    enriched = []

    # --------------------------------------------------
    # 🔹 Inicialização segura do diretório
    # --------------------------------------------------
    try:
        addon = xbmcaddon.Addon()
        profile = TRANSLATEPATH(addon.getAddonInfo("profile"))
        cache_dir = os.path.join(profile, "tmdb_cache")
    except Exception:
        cache_dir = None

    # --------------------------------------------------
    # 🔹 Campos que realmente importam
    # --------------------------------------------------
    IMPORTANT_FIELDS = {
        "title",
        "name",
        "overview",
        "release_date",
        "first_air_date",
        "runtime",
        "vote_average",
        "vote_count",
        "poster_path",
        "backdrop_path",
        "genres",
        "production_countries",
        "production_companies",
        "credits",              # mantém para tela de detalhe
        "release_dates"
    }

    for i in items:
        try:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id")
            media_type = i.get("tmdb_type") or i.get("type") or "movie"

            if not tmdb_id or not cache_dir:
                enriched.append(i)
                continue

            cache_key = f"{media_type}_{tmdb_id}"

            # --------------------------------------------------
            # 🔹 1️⃣ Cache em memória
            # --------------------------------------------------
            meta = _cache.get(cache_key)

            # --------------------------------------------------
            # 🔹 2️⃣ Cache em disco
            # --------------------------------------------------
            if not meta:
                cache_file = os.path.join(cache_dir, f"{cache_key}.json")
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        _cache[cache_key] = meta
                    except Exception:
                        meta = None

            if not meta:
                enriched.append(i)
                continue

            # --------------------------------------------------
            # 🔥 COPIA CONTROLADA (NÃO COPIA TUDO)
            # --------------------------------------------------
            for key in IMPORTANT_FIELDS:
                if key in meta and (key not in i or not i.get(key)):
                    i[key] = meta[key]

            # --------------------------------------------------
            # 🔥 CAMPOS DERIVADOS PARA KODI
            # --------------------------------------------------

            # 🎬 Year
            release = meta.get("release_date") or meta.get("first_air_date")
            if release:
                i["release_date"] = release
                try:
                    i["year"] = int(release[:4])
                except Exception:
                    i["year"] = 0

            # ⏱ Runtime → Duration
            try:
                runtime = int(meta.get("runtime") or 0)
            except Exception:
                runtime = 0

            i["runtime"] = runtime
            i["duration"] = runtime * 60  # Kodi usa segundos

            # ⭐ Rating
            try:
                i["rating"] = float(meta.get("vote_average") or 0)
            except Exception:
                i["rating"] = 0.0

            # 🗳 Votes
            try:
                i["votes"] = int(meta.get("vote_count") or 0)
            except Exception:
                i["votes"] = 0

            # 🖼 Poster
            if meta.get("poster_path") and not i.get("poster"):
                i["poster"] = f"https://image.tmdb.org/t/p/w500{meta['poster_path']}"

            # 🌄 Fanart
            if meta.get("backdrop_path") and not i.get("fanart"):
                i["fanart"] = f"https://image.tmdb.org/t/p/original{meta['backdrop_path']}"

            enriched.append(i)

        except Exception as e:
            xbmc.log(
                f"[SUPREME][CACHE] Erro ao enriquecer item {i.get('tmdb')}: {e}",
                xbmc.LOGERROR
            )
            enriched.append(i)

    return enriched

def build_plugin_url_supreme(base_url, params):
    """
    Gera URLs seguras e compativeis com parse_plugin_params().
    Evita double encoding, corrige padding Base64 e garante decodifica�o limpa.
    Aceita dict/list em 'url', convertendo automaticamente para JSON base64url.
    """
    import base64, urllib.parse, json, xbmc

    try:
        if not isinstance(params, dict):
            xbmc.log("[SUPREME][BUILD] Parâmetros inválidos: não é dict", xbmc.LOGERROR)
            return base_url

        safe_params = {}

        for k, v in params.items():
            # Ignora None
            if v is None:
                continue

            # Serializa JSON quando o valor for lista ou dict
            if k == "url" and isinstance(v, (list, dict)):
                try:
                    json_str = json.dumps(v, ensure_ascii=False)
                    b64_bytes = base64.urlsafe_b64encode(json_str.encode("utf-8"))
                    safe_params[k] = b64_bytes.decode("utf-8").rstrip("=")
                    xbmc.log(f"[SUPREME][BUILD] url JSON+Base64URL len={len(safe_params[k])}", xbmc.LOGINFO)
                except Exception as e:
                    xbmc.log(f"[SUPREME][BUILD] Falha ao codificar JSON: {e}", xbmc.LOGERROR)
                    safe_params[k] = ""
            else:
                # Strings comuns (no re-encodar Base64)
                val_str = str(v)
                if any(ch in val_str for ch in "[]{}") and not val_str.startswith("http"):
                    # se parece JSON, codifica tamb�m
                    json_str = json.dumps(val_str)
                    b64_bytes = base64.urlsafe_b64encode(json_str.encode("utf-8"))
                    safe_params[k] = b64_bytes.decode("utf-8").rstrip("=")
                    xbmc.log(f"[SUPREME][BUILD] {k} → JSON str + Base64", xbmc.LOGINFO)
                else:
                    safe_params[k] = urllib.parse.quote_plus(val_str)

        query = "&".join(f"{k}={v}" for k, v in safe_params.items())
        final_url = f"{base_url}?{query}"

        xbmc.log(f"[SUPREME][BUILD] URL final len={len(final_url)} preview={final_url[:200]}", xbmc.LOGINFO)
        return final_url

    except Exception as e:
        xbmc.log(f"[SUPREME][BUILD] Erro ao construir URL: {e}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        return base_url

def makeRequest(url, headers=None):
    try:
        if headers is None:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/119.0.0.0 Safari/537.36'
                )
            }

        # --- Headers embutidos no link ---
        if '|' in url:
            url, header_in_page = url.split('|', 1)
            header_in_page = header_in_page.split('&')
            for h in header_in_page:
                if '=' in h:
                    n, v = h.split('=', 1)
                    headers[n.strip()] = v.strip()

        # --- Caso especial: mega.nz ---
        if 'mega.nz' in url:
            try:
                return mega_to_text(url) or ''
            except Exception as e:
                safe_log(f"[makeRequest] Erro mega.nz: {e}")
                return ''

        # --- Caso especial: codeberg.org ---
        if 'codeberg.org' in url:
            try:
                headers['Authorization'] = f'token {TOKEN_CODEBERG}'
                headers['User-Agent'] = (
                    'Mozilla/5.0 (Linux; Android 13; SM-G991B) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/139.0.0.0 Mobile Safari/537.36'
                )
                r = requests.get(url, headers=headers, timeout=20)
                if r.status_code == 200:
                    result = r.text.strip()
                    if result.endswith("="):  # possível base64
                        try:
                            result = base64.b64decode(result).decode('utf-8')
                        except Exception as e:
                            safe_log(f"[makeRequest] Erro base64: {e}")
                    return result
                else:
                    safe_log(f"[makeRequest] HTTP {r.status_code} em codeberg.org")
                    return ''
            except Exception as e:
                safe_log(f"[makeRequest] Erro geral codeberg.org: {e}")
                return ''

        # --- Cache ---
        if 'CACHE_MODE' in globals() and 'ENABLE_CACHE' in globals():
            if CACHE_MODE and ENABLE_CACHE:
                safe_log("[makeRequest] Cache ativado para requests_cache")
            else:
                safe_log("[makeRequest] Cache desativado ou indisponivel")

        # --- Request principal ---
        r = requests.get(url, headers=headers, timeout=20)

        # Verifica status HTTP
        if r.status_code != 200:
            safe_log(f"[makeRequest] HTTP {r.status_code} em {url}")
            return ''

        result = r.text or ''
        result = result.strip()

        # Força UTF-8
        try:
            if isinstance(result, bytes):
                result = result.decode('utf-8', errors='ignore')
            else:
                result = str(result)
        except Exception as e:
            safe_log(f"[makeRequest] Erro de encoding: {e}")
            result = ''

        # --- Debug: loga tamanho e início do conteúdo ---
        safe_log(f"[makeRequest] OK: {url} (len={len(result)})")
        if len(result) > 200:
            safe_log(f"[makeRequest] Exibir previa: {result[:200]}...")

        # --- Detectar se retorno e JSON e se contem series ---
        try:
            import json
            data = json.loads(result)

            # Verifica se data e uma lista de dicts com tmdb_type 'tv'
            is_series_list = False
            if isinstance(data, list):
                if len(data) > 0 and all(isinstance(item, dict) and item.get("tmdb_type", "").lower() == "tv" for item in data):
                    is_series_list = True
            elif isinstance(data, dict):
                # pode ser dict com chave 'items' ou 'menu'
                items = data.get('items') or data.get('menu') or [data]
                if len(items) > 0 and all(isinstance(item, dict) and item.get("tmdb_type", "").lower() == "tv" for item in items):
                    is_series_list = True

            if is_series_list:
                safe_log("[makeRequest] Detectado lista de series – chamando getDataFromJsonSeries")
                from resources.lib.library_series import getDataFromJsonSeries
                return getDataFromJsonSeries(data, None)

        except Exception as e_detect:
            safe_log(f"[makeRequest] Erro na deteccao automatica de series: {e_detect}")

        return result

    except Exception as e:
        msg = f"[makeRequest] Falha ao acessar {url}: {e}"
        safe_log(msg)
        try:
            xbmcgui.Dialog().notification(addon_name, msg, icon, 10000, False)
        except:
            pass
        return ''
    
def addDir(name, url, mode, iconimage, fanart, description, genre, date, credits, showcontext=False, regexs=None, reg_url=None, allinfo={}):
    parentalblock = addon.getSetting('parentalblocked')
    parentalblock = parentalblock == "true"
    parentalblockedpin = addon.getSetting('parentalblockedpin')
    if parentalblock:
        mode = 58    
    # addon_log("addDir: %s %s" % (iconimage, fanart))
    """
        Needed in Kodi 19 Matrix as paths ending in .xml seem to be blacklisted causing the parent path to always be root.
    """
    url = url + "/" if url.endswith(".xml") else url
    if regexs and len(regexs) > 0:
        u = sys.argv[0] + "?url=" + urllib_parse.quote_plus(url) + "&mode=" + str(mode) + "&name=" + urllib_parse.quote_plus(name) + "&fanart=" + urllib_parse.quote_plus(fanart) + "&regexs=" + regexs
    else:
        u = sys.argv[0] + "?url=" + urllib_parse.quote_plus(url) + "&mode=" + str(mode) + "&name=" + urllib_parse.quote_plus(name) + "&fanart=" + urllib_parse.quote_plus(fanart)

    ok = True
    if date == '':
        date = None
    else:
        description += '\n\nDate: %s' % date
    liz = xbmcgui.ListItem(name)
    # liz.setArt({'thumb': "DefaultFolder.png",
    #            'icon': iconimage})
    liz.setArt({'fanart': fanart, 'thumb': iconimage, 'icon': "DefaultFolder.png"})

    if len(allinfo) < 1:
        if get_kversion() > 19:
            info = liz.getVideoInfoTag()
            info.setTitle(name)
            info.setMediaType('video')
            info.setPlot(description)
            info.setGenres([genre])
            info.setDateAdded(date)
        else:     
            liz.setInfo(type="Video", infoLabels={"Title": name, 'mediatype': 'video', "Plot": description, "Genre": genre, "dateadded": date, "credits": credits})
    else:
        if get_kversion() > 19:
            info = liz.getVideoInfoTag()
            info.setTitle(name)
            info.setMediaType('video')
        else:
            allinfo.update({'mediatype': 'video'})
            liz.setInfo(type="Video", infoLabels=allinfo)

    liz.setProperty('IsPlayable', 'false')

    if showcontext:
        contextMenu = []
        # parentalblock = addon.getSetting('parentalblocked')
        # parentalblock = parentalblock == "true"
        # parentalblockedpin = addon.getSetting('parentalblockedpin')
        if len(parentalblockedpin) > 0:
            if parentalblock:
                contextMenu.append(('Disable Parental Block', 'RunPlugin(%s?mode=55&name=%s)' % (sys.argv[0], urllib_parse.quote_plus(name))))
            else:
                contextMenu.append(('Enable Parental Block', 'RunPlugin(%s?mode=56&name=%s)' % (sys.argv[0], urllib_parse.quote_plus(name))))

        if showcontext == 'source':
            if name in str(SOURCES):
                contextMenu.append(('Remove from Sources', 'RunPlugin(%s?mode=8&name=%s)' % (sys.argv[0], urllib_parse.quote_plus(name))))
        elif showcontext == 'download':
            contextMenu.append(('Download', 'RunPlugin(%s?url=%s&mode=9&name=%s)'
                                % (sys.argv[0], urllib_parse.quote_plus(url), urllib_parse.quote_plus(name))))
        elif showcontext == 'fav':
            contextMenu.append(('Remove from %s Favorites'%str(name_addon_info), 'RunPlugin(%s?mode=6&name=%s)'
                                % (sys.argv[0], urllib_parse.quote_plus(name))))
        if showcontext == '!!update':
            fav_params2 = (
                '%s?url=%s&mode=17&regexs=%s'
                % (sys.argv[0], urllib_parse.quote_plus(reg_url), regexs)
            )
            contextMenu.append(('[COLOR yellow]!!update[/COLOR]', 'RunPlugin(%s)' % fav_params2))
        if name not in FAV:
            contextMenu.append(('Add to %s Favorites'%str(name_addon_info), 'RunPlugin(%s?mode=5&name=%s&url=%s&iconimage=%s&fanart=%s&fav_mode=%s)'
                               % (sys.argv[0], urllib_parse.quote_plus(name), urllib_parse.quote_plus(url), urllib_parse.quote_plus(iconimage), urllib_parse.quote_plus(fanart), mode)))
        liz.addContextMenuItems(contextMenu)
    ok = xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz, isFolder=True)
    return ok   
    
import sys, xbmc, xbmcgui, xbmcplugin

def addLink(url, title, thumb='', fanart='', plot='', genre='', date='', cast='', playable=True,
            trailer='', director='', duration=0, studio='', rating=0.0, votes=0, country='', mpaa=''):
    """
    Adiciona um item de video (filme, episodio, etc.) no diretorio Kodi.

    Recursos:
      tratamento de erros completo
      logs detalhados de debug
      fallback seguro se faltar dados
      suporte a fanart, elenco, MPAA, rating, trailer, etc.
      compativel com Kodi 19/21 e Android
    """
    try:
        handle = int(sys.argv[1])

        # Nome e URL obrigatórios
        if not title:
            title = "Sem título"
        if not url:
            xbmc.log(f"[ADDON-WARN] addLink: ignorando item sem URL ({title})", xbmc.LOGWARNING)
            return

        liz = xbmcgui.ListItem(label=title)

        # Arte do item
        art = {
            'thumb': thumb or '',
            'poster': thumb or '',
            'icon': thumb or '',
            'fanart': fanart or '',
        }
        liz.setArt(art)

        # InfoLabels do item
        info = {
            'title': title,
            'plot': plot or '',
            'genre': genre or '',
            'year': (date[:4] if date else ''),
            'premiered': date or '',
            'cast': cast.split(', ') if isinstance(cast, str) else cast,
            'director': director or '',
            'studio': studio or '',
            'duration': int(duration) if duration else 0,
            'rating': float(rating) if rating else 0.0,
            'votes': int(votes) if votes else 0,
            'country': country or '',
            'mpaa': mpaa or '',
        }
        liz.setInfo('video', info)

        # Trailer, se disponivel
        if trailer:
            liz.setProperty('Trailer', trailer)

        # Marcar como "reproduzivel"
        liz.setProperty('IsPlayable', 'true' if playable else 'false')

        # Adicionar item ao diretorio
        xbmcplugin.addDirectoryItem(handle, url, liz, isFolder=False)

        # Log de sucesso
        xbmc.log(f"[ADDON-DEBUG] addLink: Item adicionado com sucesso → {title}", xbmc.LOGINFO)

    except Exception as e:
        xbmc.log(f"[ADDON-ERROR] addLink: erro ao adicionar '{title}': {e}", xbmc.LOGERROR)
        try:
            # fallback m�nimo tenta ao menos adicionar o t�tulo b�sico
            liz = xbmcgui.ListItem(label=f"{title} (erro de metadados)")
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, liz, isFolder=False)
        except Exception as e_fallback:
            xbmc.log(f"[ADDON-CRITICAL] addLink: falha no fallback ({title}): {e_fallback}", xbmc.LOGERROR)