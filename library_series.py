# -*- coding: utf-8 -*-
"""
library_series.py
Módulo para gerenciar menu de séries (lista -> série -> temporada -> episódios -> play)
Usando tmdb_helper.py para metadados (cache-first).
Logs detalhados, tratamento de erros, fallback para execução fora do Kodi.
"""

from __future__ import annotations
import os
import sys
import json
import time
import traceback
import urllib.parse
from resources.lib import utils
from resources.lib.Menus import _ensure_items_supreme as _ensure_items
from urllib.parse import unquote_plus

# Tentar importar Kodi; se não estiver em execução no Kodi, utilizar fallback (print)
try:
    import xbmc
    import xbmcgui
    import xbmcplugin
    import xbmcaddon
    import xbmcvfs
except Exception:
    xbmc = None
    xbmcgui = None
    xbmcplugin = None
    xbmcaddon = None
    xbmcvfs = None

# importar helper TMDB (seu arquivo)
try:
    from resources.lib.tmdb_helper import (
        fetch_tmdb,           # genérico (movie/tv)
        fetch_tmdb_tv,        # fetch_tmdb(tv_id, media_type='tv') — se existir
        fetch_tmdb_season,
        fetch_tmdb_episode,
        translate_title,
        load_cached_tmdb,
    )
except Exception:
    # fallback simples: reimportando somente fetch_tmdb (caso seu helper tenha nomes diferentes)
    try:
        from resources.lib.tmdb_helper import fetch_tmdb, fetch_tmdb_season, fetch_tmdb_episode, translate_title, load_cached_tmdb
        def fetch_tmdb_tv(tv_id):
            return fetch_tmdb(tv_id, media_type="tv")
    except Exception:
        fetch_tmdb = None
        fetch_tmdb_tv = None
        fetch_tmdb_season = None
        fetch_tmdb_episode = None
        translate_title = lambda m: m.get("name") if isinstance(m, dict) else "Sem título"
        load_cached_tmdb = lambda *_: {}

# Se você tem utils com _add_dir_via_default_or_manual etc., tenta importar; se não existir, usamos funções locais
try:
    from resources.lib.utils import (
        _log_debug as _external_log_debug,
        _log_error as _external_log_error,
        _ensure_items as _external_ensure_items,
        _add_dir_via_default_or_manual,
        _add_video_via_default_or_manual,
    )
    def _has_utils(): return True
except Exception:
    _external_log_debug = None
    _external_log_error = None
    _external_ensure_items = None
    _add_dir_via_default_or_manual = None
    _add_video_via_default_or_manual = None
    def _has_utils(): return False

# ADDON_HANDLE (Kodi)
try:
    ADDON_HANDLE = int(sys.argv[1])
except Exception:
    ADDON_HANDLE = 0

# PROFILE / cache (usado apenas para logs se precisar)
try:
    if xbmcaddon:
        ADDON = xbmcaddon.Addon()
        PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    else:
        PROFILE = os.path.expanduser("~/.plugin_video_addon_example_profile")
except Exception:
    PROFILE = os.path.expanduser("~/.plugin_video_addon_example_profile")

# -----------------------
# Logging helpers (padronizados)
# -----------------------
def _log_debug(msg: str):
    tag = "[ADDON-DEBUG][SERIES]"
    try:
        if _external_log_debug:
            _external_log_debug(msg)
            return
        if xbmc:
            xbmc.log(f"{tag} {msg}", xbmc.LOGINFO)
        else:
            print(f"{tag} {msg}")
    except Exception:
        print(f"{tag} (log fail) {msg}")

def _log_error(msg: str):
    tag = "[ADDON-ERROR][SERIES]"
    try:
        if _external_log_error:
            _external_log_error(msg)
            return
        if xbmc:
            xbmc.log(f"{tag} {msg}", xbmc.LOGERROR)
        else:
            print(f"{tag} {msg}")
    except Exception:
        print(f"{tag} (log fail) {msg}")

# -----------------------
# Utils locais (fazer fallback se utils do projeto não existirem)
# -----------------------
def _ensure_items(items_or_payload):
    """
    Aceita:
      - lista (já processada)
      - string JSON (payload urlencoded ou raw)
    Retorna lista (ou None).
    """
    try:
        if _external_ensure_items:
            return _external_ensure_items(items_or_payload)
        # fallback:
        if items_or_payload is None:
            return None
        if isinstance(items_or_payload, list):
            return items_or_payload
        if isinstance(items_or_payload, str):
            s = items_or_payload.strip()
            # pode vir urlencoded (payload)
            try:
                s2 = urllib.parse.unquote_plus(s)
            except Exception:
                s2 = s
            try:
                parsed = json.loads(s2)
                if isinstance(parsed, list):
                    return parsed
                # se for um dict com chave 'series' ou 'items', devolve a lista
                if isinstance(parsed, dict):
                    for k in ("series","items","data"):
                        if k in parsed and isinstance(parsed[k], list):
                            return parsed[k]
                    # se dict único representando uma série, retorna lista com o dict
                    return [parsed]
            except Exception:
                # não JSON - tentar interpretar como caminho para arquivo
                try:
                    if os.path.exists(s2):
                        with open(s2, "r", encoding="utf-8") as f:
                            parsed = json.load(f)
                            if isinstance(parsed, list):
                                return parsed
                            if isinstance(parsed, dict):
                                for k in ("series","items","data"):
                                    if k in parsed and isinstance(parsed[k], list):
                                        return parsed[k]
                                return [parsed]
                except Exception:
                    pass
        # se chegou até aqui, não entendeu
        _log_debug(f"_ensure_items: formato não suportado ({type(items_or_payload)}).")
        return None
    except Exception as e:
        _log_error(f"_ensure_items falhou: {e}")
        return None

def _build_plugin_url(params: dict) -> str:
    """
    Monta URL plugin:// com parâmetros.
    Usa sys.argv[0] (plugin base).
    """
    try:
        base = sys.argv[0]
    except Exception:
        base = "plugin://plugin.video.example"
    try:
        return base + "?" + urllib.parse.urlencode({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else str(v) for k,v in params.items()})
    except Exception:
        # fallback mais simples
        try:
            return base + "?" + urllib.parse.urlencode({k: str(v) for k,v in params.items()})
        except Exception:
            return base

def _add_dir(title, params, thumb="", fanart="", info_dict=None, is_folder=True):
    """
    Adiciona um item de diretório ao Kodi.
    params: dict (será passado como querystring)
    """
    try:
        if _add_dir_via_default_or_manual:
            try:
                payload = urllib.parse.quote_plus(json.dumps(params, ensure_ascii=False))
                _add_dir_via_default_or_manual(title, payload, None, thumb, fanart, info_dict or "")
                return
            except Exception:
                pass

        url = _build_plugin_url(params)

        li = None
        if xbmcgui:
            li = xbmcgui.ListItem(label=title)

            # INFO: sempre usar formato Kodi
            if isinstance(info_dict, dict) and info_dict:
                try:
                    # força sempre incluir mediatype para ativar tela de informações
                    if "mediatype" not in info_dict:
                        info_dict["mediatype"] = "tvshow" if params.get("action") == "openSeries" else "movie"
                    li.setInfo("video", info_dict)
                except Exception as e:
                    _log_error(f"_add_dir setInfo falhou: {e}")
            else:
                li.setInfo("video", {"title": title, "plot": ""})

            # ART: poster, thumb, fanart
            try:
                art = {}
                if thumb:
                    art["thumb"] = thumb
                    art["poster"] = thumb
                if fanart:
                    art["fanart"] = fanart
                if art:
                    li.setArt(art)
            except Exception:
                pass

        # addDirectoryItem
        if xbmcplugin:
            xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=is_folder)
        else:
            _log_debug(f"_add_dir (fallback) title={title} url={url}")

    except Exception as e:
        _log_error(f"_add_dir falhou para '{title}': {e}\n{traceback.format_exc()}")

def _add_playable(title, params, thumb="", fanart="", info_dict=None):
    """
    Adiciona item reproduzível (arquivo) — isFolder=False
    """
    try:
        if _add_video_via_default_or_manual:
            # compatibilidade
            try:
                payload = urllib.parse.quote_plus(json.dumps(params, ensure_ascii=False))
                _add_video_via_default_or_manual(title, payload, None, thumb, fanart, info_dict or "")
                return
            except Exception:
                pass

        url = _build_plugin_url(params)
        li = None
        if xbmcgui:
            li = xbmcgui.ListItem(label=title)
            li.setProperty("IsPlayable", "true")
            try:
                if info_dict:
                    li.setInfo("video", info_dict if isinstance(info_dict, dict) else {"plot": str(info_dict)})
            except Exception:
                pass
            try:
                art = {}
                if thumb:
                    art["thumb"] = thumb
                if fanart:
                    art["fanart"] = fanart
                if art:
                    li.setArt(art)
            except Exception:
                pass
        if xbmcplugin:
            xbmcplugin.addDirectoryItem(handle=ADDON_HANDLE, url=url, listitem=li, isFolder=False)
        else:
            _log_debug(f"_add_playable (fallback) title={title} url={url}")
    except Exception as e:
        _log_error(f"_add_playable falhou para '{title}': {e}\n{traceback.format_exc()}")

# -----------------------
# Procura de URL de episódio no JSON do usuário (vários formatos suportados)
# -----------------------
def find_episode_stream_url(serie_payload: dict, season_number: int, episode_number: int) -> str | None:
    """
    Procura a URL do episódio dentro do objeto 'serie_payload' (que é o JSON cru do usuário para essa série).
    Aceita formatos comuns:
      - serie_payload["seasons"] = [{ "season_number": X, "episodes":[{"episode_number":Y,"url":"..."}]}]
      - serie_payload["episodes"] = [ {"season": X, "episode": Y, "url": "..."} ]
      - serie_payload["links"] = [ {"s":X,"e":Y,"url":"..."} ]
      - série plana com "urls": { "S01E01": "..." } etc.
    Retorna URL string ou None.
    """
    try:
        if not serie_payload or not isinstance(serie_payload, dict):
            return None

        # 1) seasons -> episodes
        seasons = serie_payload.get("seasons")
        if isinstance(seasons, list):
            for s in seasons:
                s_num = s.get("season_number") or s.get("season") or s.get("season_no")
                if s_num is None:
                    continue
                try:
                    s_num = int(s_num)
                except Exception:
                    continue
                if s_num != int(season_number):
                    continue
                eps = s.get("episodes") or s.get("eps") or s.get("items")
                if isinstance(eps, list):
                    for e in eps:
                        e_num = e.get("episode_number") or e.get("episode") or e.get("ep")
                        try:
                            if int(e_num) == int(episode_number):
                                url = e.get("url") or e.get("file") or e.get("link")
                                if url:
                                    return url
                        except Exception:
                            continue

        # 2) episodes flat list
        episodes = serie_payload.get("episodes") or serie_payload.get("eps")
        if isinstance(episodes, list):
            for e in episodes:
                s_num = e.get("season") or e.get("season_number")
                e_num = e.get("episode") or e.get("episode_number")
                try:
                    if int(s_num) == int(season_number) and int(e_num) == int(episode_number):
                        return e.get("url") or e.get("file") or e.get("link")
                except Exception:
                    continue

        # 3) links list
        links = serie_payload.get("links") or serie_payload.get("streams")
        if isinstance(links, list):
            for it in links:
                s_num = it.get("s") or it.get("season")
                e_num = it.get("e") or it.get("ep") or it.get("episode")
                try:
                    if int(s_num) == int(season_number) and int(e_num) == int(episode_number):
                        return it.get("url") or it.get("link")
                except Exception:
                    continue

        # 4) keyed dicts (S01E01)
        urls_map = serie_payload.get("urls") or serie_payload.get("map")
        if isinstance(urls_map, dict):
            key = f"S{int(season_number):02d}E{int(episode_number):02d}"
            if key in urls_map:
                return urls_map[key]
            # também tentar sem zeros
            key2 = f"{season_number}-{episode_number}"
            if key2 in urls_map:
                return urls_map[key2]

        # nada encontrado
        return None
    except Exception as e:
        _log_error(f"find_episode_stream_url falhou: {e}\n{traceback.format_exc()}")
        return None

# -----------------------
# Função 1: buildSeriesLibraryMenus
# -----------------------
def buildSeriesLibraryMenus(items_or_payload, fanart=""):
    """
    Monta o menu principal de bibliotecas de séries ou lista de séries de um JSON.
    Se items_or_payload for uma lista de links (cada item com 'url' e 'title'), cria entradas diretas.
    Se for lista de séries (com tmdb), cria os submenus de biblioteca (Todos / Pesquisar / etc).
    """
    _log_debug("[SERIES] buildSeriesLibraryMenus iniciado")
    try:
        items = _ensure_items(items_or_payload)
        if not items:
            _log_error(f"[SERIES] buildSeriesLibraryMenus: nenhum item (items_or_payload={items_or_payload})")
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        # Caso 1: menu principal (links para JSONs externos)
        if (
            isinstance(items, list) and items
            and isinstance(items[0], dict)
            and "url" in items[0]
            and not ("tmdb" in items[0] or "tmdb_id" in items[0])
        ):
            for it in items:
                title = it.get("title") or it.get("name") or "Sem título"
                url = it.get("url") or it.get("link") or ""
                thumb = it.get("icon") or ""
                item_fanart = it.get("fanart") or fanart or ""
                _add_dir(
                    title,
                    {"url": url, "mode": 200, "name": title},
                    thumb,
                    item_fanart,
                    f"Biblioteca: {title}"
                )
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            _log_debug("[SERIES] buildSeriesLibraryMenus (menu principal) concluído")
            return

        # Caso 2: já temos lista de séries (objetos com tmdb)
        payload = json.dumps(items, ensure_ascii=False)

        _add_dir("Todas as Séries", {"url": payload, "mode": 213}, "", fanart, "Exibir todas as séries")
        _add_dir("Pesquisar", {"url": payload, "mode": 208}, "", fanart, "Pesquisar nesta biblioteca de séries")
        _add_dir("Por Ano", {"url": payload, "mode": 209}, "", fanart, "Filtrar por ano")
        _add_dir("Por Estúdio", {"url": payload, "mode": 211}, "", fanart, "Filtrar por estúdio")
        _add_dir("Por Gênero", {"url": payload, "mode": 206}, "", fanart, "Filtrar por gênero")
        _add_dir("Novas Temporadas", {"url": payload, "mode": 214}, "", fanart, "Séries adicionadas recentemente")
        _add_dir("Lançamentos", {"url": payload, "mode": 215}, "", fanart, "Últimos lançamentos de séries")

        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug("[SERIES] buildSeriesLibraryMenus (biblioteca) concluído com sucesso")

    except Exception as e:
        _log_error(f"[SERIES] Erro em buildSeriesLibraryMenus: {e}\n{traceback.format_exc()}")
        try:
            xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        except Exception:
            pass


def getDataFromJsonSeries(json_data, fanart=""):
    """
    Lê JSON de séries (lista mínima com tmdb + tmdb_type) e lista todas as séries enriquecidas via TMDB.
    Cada item de série quando clicado passa o payload dessa série (JSON) para openSeries.
    """
    _log_debug("[SERIES] getDataFromJsonSeries iniciado")
    try:
        items = _ensure_items(json_data)
        if not items:
            _log_error("[SERIES] Nenhuma série recebida no JSON")
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"[SERIES] Itens recebidos: {len(items)}")

        rated_map = {
            0: "Desconhecido", 1: "Muito ruim", 2: "Ruim", 3: "Fraco",
            4: "Regular", 5: "Mediano", 6: "Bom", 7: "Muito bom",
            8: "Ótimo", 9: "Excelente", 10: "Obra-prima"
        }

        for idx, serie in enumerate(items, start=1):
            try:
                tmdb_id = serie.get("tmdb") or serie.get("tmdb_id") or serie.get("id")
                tmdb_type = serie.get("tmdb_type", "tv")
                if not tmdb_id:
                    _log_error(f"[SERIES] Série sem tmdb_id (índice {idx}): {serie}")
                    continue
                if tmdb_type != "tv":
                    _log_debug(f"[SERIES] Ignorando item não-tv: {tmdb_type} (id={tmdb_id})")
                    continue

                meta = {}
                try:
                    meta = fetch_tmdb(tmdb_id, media_type="tv", append_to_response="videos,credits") or {}
                except Exception as e:
                    _log_error(f"[SERIES] fetch_tmdb falhou para {tmdb_id}: {e}")
                    meta = load_cached_tmdb(tmdb_id, "tv") or {}

                # Título
                title_main = translate_title(meta) if meta else f"Série {tmdb_id}"
                original = meta.get("original_name") if meta else None
                title = f"{title_main} ({original})" if original and original != title_main else title_main

                # Arte
                poster = f"https://image.tmdb.org/t/p/w500{meta['poster_path']}" if meta.get("poster_path") else ""
                fan = f"https://image.tmdb.org/t/p/original{meta['backdrop_path']}" if meta.get("backdrop_path") else fanart

                # Elenco, diretores e roteiristas
                cast_list = []
                directors, writers = [], []
                credits = meta.get("credits", {})
                if credits:
                    for actor in credits.get("cast", [])[:20]:
                        cast_list.append({
                            "name": actor.get("name"),
                            "role": actor.get("character") or "",
                            "thumbnail": f"https://image.tmdb.org/t/p/w185{actor['profile_path']}" if actor.get("profile_path") else ""
                        })
                    for crew in credits.get("crew", []):
                        job = crew.get("job")
                        if job == "Director":
                            directors.append(crew["name"])
                        if job in ("Writer", "Screenplay"):
                            writers.append(crew["name"])

                # Criar ListItem
                li = xbmcgui.ListItem(label=title)
                li.setArt({
                    "poster": poster,
                    "thumb": poster,
                    "icon": poster,
                    "fanart": fan
                })

                # InfoTagVideo
                info = li.getVideoInfoTag()
                info.setMediaType("tvshow")
                info.setTitle(title_main)
                info.setOriginalTitle(meta.get("original_name", ""))
                info.setPlot(meta.get("overview", ""))
                info.setRating(float(meta.get("vote_average") or 0))
                info.setVotes(int(meta.get("vote_count") or 0))
                if meta.get("first_air_date"):
                    info.setPremiered(meta["first_air_date"])
                    try:
                        info.setYear(int(meta["first_air_date"][:4]))
                    except:
                        pass
                if meta.get("genres"):
                    info.setGenres([g["name"] for g in meta["genres"]])
                if meta.get("production_companies"):
                    info.setStudios([c["name"] for c in meta["production_companies"]])
                if meta.get("origin_country"):
                    info.setCountries(meta["origin_country"])
                if meta.get("number_of_seasons"):
                    info.setSeason(meta["number_of_seasons"])
                if meta.get("number_of_episodes"):
                    info.setEpisode(meta["number_of_episodes"])
                if directors:
                    info.setDirectors(directors)
                if writers:
                    info.setWriters(writers)

                # Tagline
                rated = rated_map.get(round(float(meta.get("vote_average") or 0)), "Desconhecido")
                info.setTagLine(f"Avaliado: {rated}")

                # Elenco
                if cast_list:
                    li.setCast(cast_list)

                # Adicionar Trailer no Menu de Contexto
                try:
                    trailer_url = None
                    if meta and "videos" in meta and meta["videos"].get("results"):
                        for v in meta["videos"]["results"]:
                            if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                                trailer_url = f"plugin://plugin.video.youtube/play/?video_id={v.get('key')}"
                                break
                    if trailer_url:
                        li.addContextMenuItems([
                            ("▶ Assistir Trailer", f'RunPlugin({trailer_url})')
                        ])
                        _log_debug(f"[SERIES] Trailer adicionado para: {title}")
                except Exception as e_trailer:
                    _log_error(f"[SERIES] Falha ao adicionar trailer: {e_trailer}")

                # URL para abrir temporadas da série
                serie_payload_str = json.dumps(serie, ensure_ascii=False)
                url = f"{sys.argv[0]}?mode=201&tv_id={tmdb_id}&payload={urllib.parse.quote_plus(serie_payload_str)}"

                xbmcplugin.addDirectoryItem(
                    handle=ADDON_HANDLE,
                    url=url,
                    listitem=li,
                    isFolder=True
                )

                _log_debug(f"[SERIES] Série adicionada: {title} (tmdb={tmdb_id})")

            except Exception as e_item:
                _log_error(f"[SERIES] Erro processando item #{idx}: {e_item}\n{traceback.format_exc()}")

        if xbmcplugin:
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug("[SERIES] getDataFromJsonSeries concluído com sucesso")

    except Exception as e:
        _log_error(f"[SERIES] Erro fatal em getDataFromJsonSeries: {e}\n{traceback.format_exc()}")
        try:
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        except:
            pass

# -----------------------
# Função 3: openSeries (listar temporadas)
# -----------------------
def openSeries(tmdb_id=None, serie_payload_encoded=None, fanart=""):
    """
    Mostra as temporadas de uma série.
    Se no JSON cru tiver seasons, usa eles para criar o menu enriquecido com TMDB.
    """
    try:
        _log_debug(f"[SERIES] openSeries iniciado - tmdb={tmdb_id}")

        # desserializar payload da série
        serie_payload_obj = None
        if serie_payload_encoded:
            try:
                serie_payload_obj = json.loads(urllib.parse.unquote_plus(serie_payload_encoded))
            except Exception:
                try:
                    serie_payload_obj = json.loads(serie_payload_encoded)
                except Exception:
                    serie_payload_obj = None

        # pegar temporadas do JSON cru
        seasons_json = serie_payload_obj.get("seasons", []) if serie_payload_obj else []
        if not seasons_json:
            _log_error(f"[SERIES] Nenhuma temporada no JSON cru da série tmdb={tmdb_id}")
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        # fanart fixo da série
        serie_fanart = ""
        if serie_payload_obj and serie_payload_obj.get("backdrop_path"):
            serie_fanart = f"https://image.tmdb.org/t/p/original{serie_payload_obj['backdrop_path']}"
        else:
            serie_fanart = fanart

        for s in seasons_json:
            season_number = s.get("tmdb_season")
            if season_number is None:
                continue

            # buscar metadados da temporada no TMDB
            season_meta = {}
            try:
                season_meta = fetch_tmdb_season(tmdb_id, season_number) or {}
            except Exception as e:
                _log_error(f"[SERIES] fetch_tmdb_season falhou para tmdb={tmdb_id} season={season_number}: {e}")

            # título
            season_title = f"Temporada {season_number}"

            # número de episódios
            episode_count = season_meta.get("episodes")
            if isinstance(episode_count, list):
                episode_count = len(episode_count)
            elif isinstance(episode_count, int):
                episode_count = episode_count
            else:
                episode_count = len(s.get("episodes", []))

            # label principal e label2 (em cor)
            label = f"{season_title} [COLOR aquamarine]({episode_count} Episódios)[/COLOR]"
            label2 = f"[COLOR aquamarine]{episode_count} Episódios[/COLOR]" if episode_count else ""

            # descrição
            season_plot = season_meta.get("overview", "")

            # poster
            season_poster = f"https://image.tmdb.org/t/p/w500{season_meta['poster_path']}" if season_meta.get("poster_path") else ""

            # criar ListItem
            li = xbmcgui.ListItem(label=label, label2=label2)
            li.setArt({
                "poster": season_poster or fanart,
                "thumb": season_poster or fanart,
                "icon": season_poster or fanart,
                "fanart": serie_fanart
            })

            info = li.getVideoInfoTag()
            info.setMediaType("season")
            info.setSeason(int(season_number))
            info.setPlot(season_plot)

            # título exibido no detalhe
            serie_title = serie_payload_obj.get("title", "") if serie_payload_obj else ""
            if serie_title:
                info.setTitle(f"{serie_title} - {season_title}")

            # passar payload
            serie_payload_str = json.dumps(serie_payload_obj, ensure_ascii=False) if serie_payload_obj else ""
            url = f"{sys.argv[0]}?mode=202&tv_id={tmdb_id}&season={season_number}&payload={urllib.parse.quote_plus(serie_payload_str)}"

            xbmcplugin.addDirectoryItem(
                handle=ADDON_HANDLE,
                url=url,
                listitem=li,
                isFolder=True
            )

            _log_debug(f"[SERIES] Temporada adicionada: tmdb={tmdb_id} season={season_number} ({episode_count} eps)")

        if xbmcplugin:
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug(f"[SERIES] openSeries concluído - tmdb={tmdb_id}")

    except Exception as e:
        _log_error(f"[SERIES] Erro fatal em openSeries: {e}\n{traceback.format_exc()}")
        try:
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        except Exception:
            pass

# -----------------------
# Função 4: openSeason (listar episódios)
# -----------------------
def openSeason(tmdb_id, season_number, serie_payload_encoded=None, fanart=""):
    """
    Lista episódios de uma temporada (tmdb_id, season_number).
    Se o payload da série tiver info, repassa para playEpisode.
    """
    try:
        _log_debug(f"[SEASON] openSeason iniciado - tmdb={tmdb_id}, season={season_number}")

        # desserializar payload da série
        serie_payload_obj = None
        if serie_payload_encoded:
            try:
                serie_payload_obj = json.loads(urllib.parse.unquote_plus(serie_payload_encoded))
            except Exception:
                try:
                    serie_payload_obj = json.loads(serie_payload_encoded)
                except Exception:
                    serie_payload_obj = None

        # Buscar detalhes da temporada no TMDB
        season_meta = {}
        try:
            season_meta = fetch_tmdb_season(tmdb_id, season_number) if fetch_tmdb_season else {}
        except Exception as e:
            _log_error(f"[SEASON] fetch_tmdb_season falhou: {e}")

        if not season_meta:
            _log_error(f"[SEASON] Nenhum metadado da temporada tmdb={tmdb_id} season={season_number}")
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        episodes = season_meta.get("episodes", [])
        if not episodes:
            _log_error(f"[SEASON] Nenhum episódio listado em season_meta para tmdb={tmdb_id} season={season_number}")
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        serie_title = serie_payload_obj.get("title", "") if serie_payload_obj else ""

        for ep in episodes:
            try:
                ep_number = ep.get("episode_number")
                if ep_number is None:
                    continue

                ep_title = ep.get("name") or f"Episódio {ep_number}"

                # Apenas a descrição do episódio
                plot = ep.get("overview", "")

                # thumb → still_path > poster da temporada > fanart da série
                thumb = ""
                if ep.get("still_path"):
                    thumb = f"https://image.tmdb.org/t/p/w500{ep['still_path']}"
                elif season_meta.get("poster_path"):
                    thumb = f"https://image.tmdb.org/t/p/w500{season_meta['poster_path']}"
                else:
                    thumb = fanart

                # Criar ListItem
                label = f"S{int(season_number):02d}E{int(ep_number):02d} - {ep_title}"
                if serie_title:
                    label = f"{serie_title} - {label}"

                li = xbmcgui.ListItem(label=label)
                li.setArt({
                    "thumb": thumb,
                    "poster": thumb,
                    "fanart": fanart or ""
                })

                # InfoTagVideo
                info = li.getVideoInfoTag()
                info.setMediaType("episode")
                info.setTitle(label)
                info.setPlot(plot)
                info.setSeason(int(season_number))
                info.setEpisode(int(ep_number))
                if ep.get("air_date"):
                    info.setPremiered(ep["air_date"])
                if ep.get("runtime"):
                    info.setDuration(int(ep["runtime"]))
                if ep.get("vote_average"):
                    info.setRating(float(ep["vote_average"]))

                # payload da série (para playEpisode)
                serie_payload_str = json.dumps(serie_payload_obj, ensure_ascii=False) if serie_payload_obj else ""

                url = f"{sys.argv[0]}?mode=203&tv_id={tmdb_id}&season={season_number}&episode={ep_number}&payload={urllib.parse.quote_plus(serie_payload_str)}"

                xbmcplugin.addDirectoryItem(
                    handle=ADDON_HANDLE,
                    url=url,
                    listitem=li,
                    isFolder=False
                )
                _log_debug(f"[SEASON] Episódio adicionado: S{season_number:02d}E{ep_number:02d} (tmdb={tmdb_id})")

            except Exception as e_ep:
                _log_error(f"[SEASON] Erro processando episódio: {e_ep}\n{traceback.format_exc()}")

        if xbmcplugin:
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug(f"[SEASON] openSeason concluído - tmdb={tmdb_id}, season={season_number}")

    except Exception as e:
        _log_error(f"[SEASON] Erro fatal em openSeason: {e}\n{traceback.format_exc()}")
        try:
            if xbmcplugin:
                xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        except Exception:
            pass

# -----------------------
# Função 5: playEpisode (resolve URL e reproduz)
# -----------------------
def playEpisode(tmdb_id, season, episode, serie_payload_encoded=None):
    """
    Resolve e reproduz um episódio.
    Prioridade de URL:
      1) procurar no payload da série (se foi passado com as urls)
      2) falha com log (não tentamos adivinhar streams externos)
    """
    try:
        _log_debug(f"[PLAY] playEpisode chamado - tmdb={tmdb_id}, season={season}, episode={episode}")

        # desserializar payload
        serie_payload_obj = None
        if serie_payload_encoded:
            try:
                serie_payload_obj = json.loads(urllib.parse.unquote_plus(serie_payload_encoded))
            except Exception:
                try:
                    serie_payload_obj = json.loads(serie_payload_encoded)
                except Exception:
                    serie_payload_obj = None

        # 1) tentar encontrar URL no payload do usuário
        stream_url = None
        if serie_payload_obj:
            stream_url = find_episode_stream_url(serie_payload_obj, season, episode)
            if stream_url:
                _log_debug(f"[PLAY] URL encontrada no payload da série: {stream_url}")

        if not stream_url:
            # Não achamos URL no JSON do usuário — tentar verificar se o episódio tem 'url' nos dados do tmdb_helper (raro)
            ep_meta = {}
            try:
                ep_meta = fetch_tmdb_episode(tmdb_id, season, episode) if fetch_tmdb_episode else {}
            except Exception:
                ep_meta = {}
            stream_url = ep_meta.get("url") or None
            if stream_url:
                _log_debug(f"[PLAY] URL encontrada nos metadados do episódio (tmdb cache): {stream_url}")

        if not stream_url:
            _log_error(f"[PLAY] Nenhuma URL de stream encontrada para tmdb={tmdb_id} S{season}E{episode}")
            # informar Kodi que não foi possível resolver
            if xbmcplugin and xbmcgui:
                xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
            return

        # construir listitem e resolver
        li = None
        try:
            if xbmcgui:
                title = f"S{int(season):02d}E{int(episode):02d}"
                li = xbmcgui.ListItem(label=title)
                # metadata adicional (tentar pegar do TMDB)
                try:
                    ep_meta = fetch_tmdb_episode(tmdb_id, season, episode) if fetch_tmdb_episode else {}
                except Exception:
                    ep_meta = {}
                info = {
                    "title": ep_meta.get("name") or title,
                    "plot": ep_meta.get("overview") or "",
                    "season": int(season),
                    "episode": int(episode),
                    "tvshowtitle": ep_meta.get("show_name") or "",
                    "aired": ep_meta.get("air_date") or "",
                    "duration": ep_meta.get("runtime") or 0
                }
                li.setInfo("video", info)
                # arte
                try:
                    art = {}
                    if ep_meta.get("still_path"):
                        art["thumb"] = f"https://image.tmdb.org/t/p/w500{ep_meta.get('still_path')}"
                    if ep_meta.get("show_poster") or ep_meta.get("poster_path"):
                        art["poster"] = f"https://image.tmdb.org/t/p/w500{ep_meta.get('poster_path') or ep_meta.get('show_poster')}"
                    if ep_meta.get("show_fanart") or ep_meta.get("backdrop_path"):
                        art["fanart"] = f"https://image.tmdb.org/t/p/original{ep_meta.get('backdrop_path') or ep_meta.get('show_fanart')}"
                    if art:
                        li.setArt(art)
                except Exception:
                    pass
                # set path
                li.setPath(stream_url)
        except Exception:
            _log_error(f"[PLAY] Erro construindo ListItem: {traceback.format_exc()}")

        # resolver URL no Kodi
        try:
            if xbmcplugin:
                xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, li)
                _log_debug(f"[PLAY] setResolvedUrl chamado com sucesso para {stream_url}")
            else:
                _log_debug(f"[PLAY] (fallback) reproduzir {stream_url}")
        except Exception as e:
            _log_error(f"[PLAY] Erro setResolvedUrl: {e}\n{traceback.format_exc()}")
            try:
                if xbmcplugin and xbmcgui:
                    xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
            except Exception:
                pass

    except Exception as e:
        _log_error(f"[PLAY] Erro fatal em playEpisode: {e}\n{traceback.format_exc()}")
        try:
            if xbmcplugin and xbmcgui:
                xbmcplugin.setResolvedUrl(ADDON_HANDLE, False, xbmcgui.ListItem())
        except Exception:
            pass
            
def normalize_str(text):
    """Normaliza string para comparação (remove acentos e põe minúsculas)."""
    import unicodedata
    if not text:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text.lower())
        if unicodedata.category(c) != 'Mn'
    ).strip()
    
from resources.lib.tmdb_helper import fetch_tmdb

def listAllSeries(payload, fanart):
    _log_debug("[SERIES] listAllSeries iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Séries", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        enriched = []
        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id") or i.get("id")
            if not tmdb_id:
                _log_debug("[SERIES] Ignorando item sem TMDB ID")
                continue

            try:
                # ✅ tenta carregar do cache primeiro
                meta = fetch_tmdb(tmdb_id, "tv")
                if not meta:
                    _log_debug(f"[SERIES] Cache não encontrado para {tmdb_id}, tentando enriquecer manualmente")
                    continue  # se não há cache, ignora (ou poderia fazer fetch online se você quiser)

                # ✅ enriquece com segurança
                serie = dict(i)
                serie["tmdb_id"] = tmdb_id
                serie["title"] = meta.get("name") or meta.get("original_name") or i.get("title") or "Sem título"
                serie["overview"] = meta.get("overview") or i.get("overview") or ""
                serie["poster"] = meta.get("poster_path") or i.get("poster") or ""
                serie["backdrop"] = meta.get("backdrop_path") or i.get("backdrop") or ""
                serie["first_air_date"] = meta.get("first_air_date") or i.get("first_air_date") or ""
                serie["genres"] = [
                    g.get("name") if isinstance(g, dict) else str(g)
                    for g in (meta.get("genres") or i.get("genres") or [])
                    if g
                ]

                enriched.append(serie)
                _log_debug(f"[SERIES] Série adicionada: {serie['title']} ({serie.get('first_air_date')})")

            except Exception as e_tmdb:
                _log_error(f"[SERIES] Erro ao enriquecer série {tmdb_id}: {e_tmdb}")

        if not enriched:
            xbmcgui.Dialog().notification("Séries", "Nenhuma série válida encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"[SERIES] listAllSeries finalizado — {len(enriched)} séries enriquecidas com sucesso")
        getDataFromJsonSeries(enriched, fanart)

    except Exception as e:
        _log_error(f"[SERIES] Erro em listAllSeries: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        

def listSeriesGenres(payload, fanart):
    _log_debug("listSeriesGenres iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Gêneros", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        genres_map = {}  # chave = normalizado | valor = forma bonita
        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")  # busca no cache/local (retorna dict com genres possivelmente como list[dict])
                if not meta:
                    continue

                g_list = meta.get("genres") or i.get("genres") or []
                # --- normaliza g_list para lista de strings ---
                if isinstance(g_list, list):
                    names = []
                    for g in g_list:
                        if isinstance(g, dict):
                            name = g.get("name") or g.get("title") or ""
                        else:
                            name = str(g)
                        if name:
                            names.append(name)
                    g_list = names
                elif isinstance(g_list, str):
                    g_list = [part.strip() for part in g_list.split(",") if part.strip()]
                else:
                    g_list = []

                for g in g_list:
                    if not g:
                        continue
                    norm = normalize_str(g)
                    if norm:
                        # guarda a forma "bonita" (primeira ocorrência)
                        if norm not in genres_map:
                            genres_map[norm] = g.strip().capitalize()

            except Exception as e_tmdb:
                _log_error(f"Erro ao enriquecer série {tmdb_id}: {e_tmdb}")

        if not genres_map:
            xbmcgui.Dialog().notification("Gêneros", "Nenhum gênero encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        for norm, pretty in sorted(genres_map.items(), key=lambda x: (x[1] or "").lower()):
            params = {'url': json.dumps(items), 'mode': 106, 'genre': norm, 'name': pretty}
            plugin_url = utils.build_plugin_url(params)
            li = xbmcgui.ListItem(label=pretty)
            xbmcplugin.addDirectoryItem(ADDON_HANDLE, plugin_url, li, True)

        xbmcplugin.endOfDirectory(ADDON_HANDLE)

    except Exception as e:
        _log_error(f"Erro em listSeriesGenres: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        
def listSeriesByGenre(payload, fanart, genre):
    try:
        _log_debug(f"listSeriesByGenre iniciado - gênero alvo (normalizado): {genre}")
        genre_norm = normalize_str(unquote_plus(genre))

        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Gênero", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        filtrados = []
        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")
                g_list = meta.get("genres") or i.get("genres") or []
                if isinstance(g_list, str):
                    g_list = [g.strip() for g in g_list.split(",") if g.strip()]

                for g in g_list:
                    if normalize_str(g) == genre_norm:
                        filtrados.append(i)
                        break
            except Exception as e_tmdb:
                _log_error(f"Erro ao processar série {tmdb_id} em listSeriesByGenre: {e_tmdb}")

        if not filtrados:
            xbmcgui.Dialog().notification("Gênero", f"Nenhuma série encontrada em {genre}", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"Séries encontradas para gênero {genre}: {len(filtrados)}")
        getDataFromJsonSeries(filtrados, fanart)

    except Exception as e:
        _log_error(f"Erro em listSeriesByGenre: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        
def searchSeries(payload, fanart):
    _log_debug("searchSeries iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Pesquisa", "Nenhuma série disponível", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        # Teclado do Kodi
        kb = xbmc.Keyboard('', 'Digite o nome da série')
        kb.doModal()
        if not kb.isConfirmed():
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        query = kb.getText().strip()
        if not query:
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        query_norm = normalize_str(query)
        results = []

        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id")
            title = i.get("title") or i.get("name") or i.get("label") or ""

            # Tenta enriquecer pelo TMDB
            if tmdb_id:
                try:
                    meta = fetch_tmdb(tmdb_id, "tv")
                    title = meta.get("name") or meta.get("original_name") or title
                except Exception as e_tmdb:
                    _log_error(f"Erro ao buscar TMDB para {tmdb_id} em searchSeries: {e_tmdb}")

            if query_norm in normalize_str(title):
                results.append(i)

        if not results:
            xbmcgui.Dialog().notification("Pesquisa", f"Nenhuma série encontrada para '{query}'", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"Resultados encontrados para '{query}': {len(results)} séries")
        getDataFromJsonSeries(results, fanart)

    except Exception as e:
        _log_error(f"Erro em searchSeries: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        
def listSeriesYears(payload, fanart):
    _log_debug("[SERIES] listSeriesYears iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Anos", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        years = {}

        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id") or i.get("id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")
                if not meta:
                    continue

                # Normaliza campo de data
                rd = meta.get("first_air_date") or meta.get("release_date") or i.get("first_air_date") or ""
                if isinstance(rd, (int, float)):
                    rd = str(int(rd))
                if not isinstance(rd, str):
                    continue
                rd = rd.strip()
                if len(rd) >= 4 and rd[:4].isdigit():
                    ano = rd[:4]
                    if ano not in years:
                        years[ano] = 1
                    else:
                        years[ano] += 1
            except Exception as e_tmdb:
                _log_error(f"[SERIES] Erro ao enriquecer série {tmdb_id}: {e_tmdb}")

        if not years:
            xbmcgui.Dialog().notification("Anos", "Nenhum ano encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        for ano in sorted(years.keys(), reverse=True):
            params = {"url": json.dumps(items), "mode": 210, "year": ano}
            plugin_url = utils.build_plugin_url(params)
            li = xbmcgui.ListItem(label=f"{ano}")
            xbmcplugin.addDirectoryItem(ADDON_HANDLE, plugin_url, li, True)

        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug(f"[SERIES] listSeriesYears finalizado ({len(years)} anos encontrados)")

    except Exception as e:
        _log_error(f"[SERIES] Erro em listSeriesYears: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        
def listSeriesByYear(payload, fanart, year):
    _log_debug(f"[SERIES] listSeriesByYear iniciado - ano {year}")
    try:
        items = _ensure_items(payload)
        filtrados = []

        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id") or i.get("id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")
                if not meta:
                    continue

                rd = meta.get("first_air_date") or meta.get("release_date") or i.get("first_air_date") or ""
                if isinstance(rd, (int, float)):
                    rd = str(int(rd))
                if isinstance(rd, str) and rd[:4] == str(year):
                    # adiciona metadados básicos
                    i["title"] = meta.get("name") or meta.get("original_name") or i.get("title") or "Sem título"
                    i["overview"] = meta.get("overview") or i.get("overview") or ""
                    i["poster"] = meta.get("poster_path") or i.get("poster") or ""
                    i["backdrop"] = meta.get("backdrop_path") or i.get("backdrop") or ""
                    filtrados.append(i)
            except Exception as e_tmdb:
                _log_error(f"[SERIES] Erro ao enriquecer série {tmdb_id}: {e_tmdb}")

        if not filtrados:
            xbmcgui.Dialog().notification("Ano", f"Nenhuma série lançada em {year}", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"[SERIES] listSeriesByYear encontrou {len(filtrados)} séries de {year}")
        getDataFromJsonSeries(filtrados, fanart)

    except Exception as e:
        _log_error(f"[SERIES] Erro em listSeriesByYear: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
    
def listSeriesStudios(payload, fanart):
    _log_debug("listSeriesStudios iniciado")
    try:
        items = utils.enrich_with_cache(_ensure_items(payload))
        studios = {}

        for i in items:
            try:
                studios_data = i.get("production_companies") or i.get("studio") or []
                if isinstance(studios_data, list):
                    for s in studios_data:
                        name = s.get("name") if isinstance(s, dict) else str(s)
                        if name:
                            norm = normalize_str(name)
                            if norm not in studios:
                                studios[norm] = name  # mantém o original bonito
                elif isinstance(studios_data, str):
                    norm = normalize_str(studios_data)
                    if norm not in studios:
                        studios[norm] = studios_data
            except Exception as e_item:
                _log_error(f"Erro ao extrair estúdio de item: {e_item}")

        if not studios:
            xbmcgui.Dialog().notification("Estúdios", "Nenhum estúdio encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        for norm, original in sorted(studios.items(), key=lambda x: str(x[1].get("name") if isinstance(x[1], dict) else x[1]).lower()):
            params = {"url": json.dumps(items), "mode": 212, "studio": norm, "name": original}
            plugin_url = utils.build_plugin_url(params)
            li = xbmcgui.ListItem(label=original.strip().title())  # mantém bonito no menu
            xbmcplugin.addDirectoryItem(ADDON_HANDLE, plugin_url, li, True)

        xbmcplugin.endOfDirectory(ADDON_HANDLE)

    except Exception as e:
        _log_error(f"Erro em listSeriesStudios: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
    
def listSeriesByStudio(payload, fanart, studio):
    _log_debug(f"listSeriesByStudio iniciado - estúdio: {studio}")
    try:
        studio = unquote_plus(studio)
        studio_norm = normalize_str(studio)

        items = utils.enrich_with_cache(_ensure_items(payload))
        filtrados = []

        for i in items:
            try:
                studios_data = i.get("production_companies") or i.get("studio") or []
                if isinstance(studios_data, list):
                    for s in studios_data:
                        name = s.get("name") if isinstance(s, dict) else str(s)
                        if normalize_str(name) == studio_norm:
                            # enriquecer com TMDB
                            tmdb_id = i.get("tmdb") or i.get("tmdb_id")
                            if tmdb_id:
                                try:
                                    meta = fetch_tmdb(tmdb_id, "tv")
                                    if meta:
                                        i["title"] = meta.get("name") or i.get("title")
                                        i["overview"] = meta.get("overview") or i.get("description") or ""
                                        i["poster"] = meta.get("poster_path")
                                        i["backdrop"] = meta.get("backdrop_path")
                                        i["genres"] = [g.get("name") for g in meta.get("genres", []) if isinstance(g, dict)]
                                except Exception as e_tmdb:
                                    _log_error(f"Erro TMDB em {i.get('title')}: {e_tmdb}")
                            filtrados.append(i)
                elif isinstance(studios_data, str):
                    if normalize_str(studios_data) == studio_norm:
                        filtrados.append(i)
            except Exception as e_item:
                _log_error(f"Erro ao processar série por estúdio: {e_item}")

        if not filtrados:
            xbmcgui.Dialog().notification("Estúdios", f"Nenhuma série encontrada em {studio}", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        getDataFromJsonSeries(filtrados, fanart)

    except Exception as e:
        _log_error(f"Erro em listSeriesByStudio: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
    
    
from datetime import datetime, timedelta

def listRecentSeries(payload, fanart):
    _log_debug("[SERIES] listRecentSeries iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Séries", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        from datetime import datetime, timedelta
        limite = datetime.now() - timedelta(days=90)
        recentes = []

        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id") or i.get("id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")
                if not meta:
                    continue

                rd = meta.get("first_air_date") or i.get("first_air_date")
                if not rd:
                    continue

                try:
                    data = datetime.strptime(rd[:10], "%Y-%m-%d")
                except Exception:
                    continue

                if data >= limite:
                    serie = {
                        "tmdb_id": tmdb_id,
                        "title": meta.get("name") or i.get("title") or "Sem título",
                        "overview": meta.get("overview") or i.get("overview") or "",
                        "poster": meta.get("poster_path") or i.get("poster") or "",
                        "backdrop": meta.get("backdrop_path") or i.get("backdrop") or "",
                        "first_air_date": rd,
                        "genres": [g.get("name") for g in meta.get("genres", []) if isinstance(g, dict)]
                    }
                    recentes.append(serie)
                    _log_debug(f"[SERIES] Nova série: {serie['title']} ({serie['first_air_date']})")

            except Exception as e_tmdb:
                _log_error(f"[SERIES] Erro ao processar série {tmdb_id}: {e_tmdb}")

        if not recentes:
            xbmcgui.Dialog().notification("Séries", "Nenhum lançamento recente encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        _log_debug(f"[SERIES] listRecentSeries finalizado — {len(recentes)} novas séries encontradas")
        getDataFromJsonSeries(recentes, fanart)

    except Exception as e:
        _log_error(f"[SERIES] Erro em listRecentSeries: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
    
def listRecentSeasons(payload, fanart):
    _log_debug("[SERIES] listRecentSeasons iniciado")
    try:
        items = _ensure_items(payload)
        if not items:
            xbmcgui.Dialog().notification("Temporadas", "Nenhuma série encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        from datetime import datetime, timedelta
        limite = datetime.now() - timedelta(days=60)
        temporadas_novas = []

        for i in items:
            tmdb_id = i.get("tmdb") or i.get("tmdb_id") or i.get("id")
            if not tmdb_id:
                continue

            try:
                meta = fetch_tmdb(tmdb_id, "tv")
                if not meta:
                    continue

                titulo = meta.get("name") or i.get("title") or "Sem título"

                for temporada in meta.get("seasons", []):
                    air_date = temporada.get("air_date")
                    if not air_date:
                        continue

                    try:
                        dt = datetime.strptime(air_date[:10], "%Y-%m-%d")
                    except Exception:
                        continue

                    if dt >= limite:
                        temporada_info = {
                            "tmdb_id": tmdb_id,
                            "title": f"{titulo} - T{temporada.get('season_number', '?')}",
                            "overview": temporada.get("overview") or "",
                            "poster": temporada.get("poster_path") or meta.get("poster_path") or "",
                            "backdrop": meta.get("backdrop_path") or "",
                            "air_date": air_date,
                            "season_number": temporada.get("season_number")
                        }
                        temporadas_novas.append(temporada_info)
                        _log_debug(f"[SERIES] Nova temporada: {temporada_info['title']} ({air_date})")

            except Exception as e_tmdb:
                _log_error(f"[SERIES] Erro ao processar série {tmdb_id}: {e_tmdb}")

        if not temporadas_novas:
            xbmcgui.Dialog().notification("Temporadas", "Nenhuma temporada recente encontrada", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE)
            return

        temporadas_novas.sort(key=lambda x: x.get("air_date", ""), reverse=True)
        _log_debug(f"[SERIES] listRecentSeasons finalizado — {len(temporadas_novas)} temporadas recentes")
        getDataFromJsonSeries(temporadas_novas, fanart)

    except Exception as e:
        _log_error(f"[SERIES] Erro em listRecentSeasons: {e}")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)