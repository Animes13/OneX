import xbmc
import xbmcaddon
import xbmcplugin
import datetime
import xbmcgui
import json
import sys
from urllib.parse import urlencode
from resources.lib import tmdb_helper
from resources.lib.utils import addLink, addDir
from resources.lib.utils import get_kversion
import xbmcvfs
from resources.lib.utils import _cache

TRANSLATEPATH = xbmcvfs.translatePath

from resources.lib import utils   # para addDir, makeRequest, _ensure_items, etc.

ADDON_HANDLE = int(sys.argv[1])

# em Menus.py (no topo do arquivo)
CACHE_TEMP = {}

def put_in_cache(key, value):
    """Armazena um objeto JSON em cache temporário"""
    global CACHE_TEMP
    CACHE_TEMP[key] = value

def get_from_cache(key, default=None):
    """Recupera um objeto JSON do cache temporário"""
    return CACHE_TEMP.get(key, default)

def _log_debug(msg):
    xbmc.log(f"[ADDON-DEBUG][utils] {msg}", xbmc.LOGINFO)

def _log_error(msg):
    xbmc.log(f"[ADDON-ERROR][utils] {msg}", xbmc.LOGERROR)

def compute_cache_key(items, hint=None):
    """
    Gera chave de cache a partir da lista de itens.
    """
    import hashlib, json
    try:
        raw = json.dumps(items, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
    except Exception:
        return "fallback_cache_key"

def get_cache():
    return _cache
        
def _load_default():
    """
    Função de fallback usada pelo antigo library_menus.
    Serve apenas para logar caminhos importantes do addon,
    evitando erros de referência.
    """
    try:
        import os
        import xbmcaddon

        addon_local = xbmcaddon.Addon()
        addon_root = addon_local.getAddonInfo('path')
        lib_dir = os.path.join(addon_root, 'resources', 'lib')
        default_path = os.path.join(addon_root, 'default.py')

        _log_debug(f"_load_default: lib_dir={lib_dir}")
        _log_debug(f"_load_default: addon_root={addon_root}")
        _log_debug(f"_load_default: default_path={default_path}")

        return {
            "addon_root": addon_root,
            "lib_dir": lib_dir,
            "default_path": default_path
        }
    except Exception as e:
        _log_error(f"_load_default: exceção: {e}")
        return {}   
        
# utils.py



def build_plugin_url(params):
    """
    Constrói a URL do plugin com os parâmetros corretos para o Kodi.
    Exemplo de uso:
        url = build_plugin_url({"url": "https://...", "mode": 1, "name": "Matrix"})
    """
    try:
        base = sys.argv[0]
        return f"{base}?{urlencode(params)}"
    except Exception as e:
        xbmc.log(f"[ADDON-ERROR][utils] Erro em build_plugin_url: {e}", xbmc.LOGERROR)
        return sys.argv[0]        

def getMainMenus(data=None, fanart=None):
    """
    ⚡ SUPREME FAST MENU
    - NÃO baixa JSON antes do clique
    - NÃO tenta adivinhar mode
    - NÃO faz requisições desnecessárias
    - Logs mínimos
    - Usa apenas mode definido no menu.json
    """

    try:
        items = []

        # ---------------------------------------------------------
        # 🔹 CARREGA MENU APENAS UMA VEZ
        # ---------------------------------------------------------
        if data:
            if isinstance(data, dict) and "menu" in data:
                items = data["menu"]
            elif isinstance(data, list):
                items = data
            else:
                return
        else:
            try:
                response = makeRequest(MENU_URL)
                j = json.loads(response)

                if isinstance(j, dict) and "menu" in j:
                    items = j["menu"]
                elif isinstance(j, list):
                    items = j
                else:
                    return
            except:
                return

        if not items:
            return

        # ---------------------------------------------------------
        # 🔹 MONTA MENU SEM NENHUMA VERIFICAÇÃO REMOTA
        # ---------------------------------------------------------
        for item in items:
            try:
                title = item.get("title") or item.get("name") or "Sem título"
                url = item.get("url", "")
                thumb = item.get("icon", "")
                item_fanart = item.get("fanart") or fanart or FANART

                # ⚡ Usa apenas mode definido
                try:
                    mode = int(item.get("mode", 100))
                except:
                    mode = 100

                addDir(
                    title,
                    url,
                    mode,
                    thumb,
                    item_fanart,
                    f"Biblioteca: {title}",
                    "",
                    "",
                    "",
                    True
                )

            except:
                continue

        xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=True)

    except:
        pass
        
        
def getDataFromJson(json_data, fanart):
    """
    🔥 SUPREME REFACTOR v2 — Enriquecimento completo rápido
    - Lê JSON ou Base64
    - Usa cache em disco por filme
    - Só faz TMDB fetch quando necessário
    - Evita I/O pesado dentro do loop
    - Logs reduzidos para performance
    """

    import xbmc
    import json

    try:
        from resources.lib.Menus import buildLibraryMenus_supreme
        import xbmcgui
    except Exception as e:
        xbmc.log(f"[SUPREME][ERROR] Falha ao importar builder: {e}", xbmc.LOGERROR)
        return False

    xbmc.log("[SUPREME][FLOW] getDataFromJson iniciado", xbmc.LOGDEBUG)

    # --- Decode inteligente (JSON ou Base64) ---
    try:
        if isinstance(json_data, str):
            data_str = json_data.strip()

            # detect Base64
            if not data_str.startswith(("{", "[")):
                import base64
                pad = "=" * ((4 - len(data_str) % 4) % 4)
                try:
                    decoded = base64.urlsafe_b64decode(data_str + pad).decode("utf-8")
                    if decoded.startswith(("{", "[")):
                        data_str = decoded
                except Exception:
                    pass

            json_data = json.loads(data_str)

    except Exception as e:
        xbmc.log(f"[SUPREME][ERROR] JSON inválido: {e}", xbmc.LOGERROR)
        return False

    # --- Normaliza itens ---
    if isinstance(json_data, list):
        items = json_data
    elif isinstance(json_data, dict):
        items = json_data.get("items") or json_data.get("channels") or list(json_data.values())
    else:
        items = []

    if not items:
        xbmc.log("[SUPREME][FLOW] Nenhum item encontrado", xbmc.LOGWARNING)
        return False

    xbmc.log(f"[SUPREME][FLOW] {len(items)} itens recebidos para menu", xbmc.LOGDEBUG)

    # --- Preparar cache de filmes ---
    try:
        import os, xbmcvfs, xbmcaddon
        TRANSLATEPATH = xbmcvfs.translatePath
        addon_local = xbmcaddon.Addon()
        profile_local = TRANSLATEPATH(addon_local.getAddonInfo("profile"))
        cache_movies_dir = os.path.join(profile_local, "cache", "movies")
        os.makedirs(cache_movies_dir, exist_ok=True)
    except Exception as e:
        xbmc.log(f"[SUPREME][CACHE] Falha em criar cache de filmes: {e}", xbmc.LOGERROR)
        cache_movies_dir = None

    # Pré-carrega nomes de arquivos de cache
    existing_cache_files = set()
    if cache_movies_dir:
        try:
            existing_cache_files = set(os.listdir(cache_movies_dir))
        except Exception:
            existing_cache_files = set()

    enriched_items = []
    missing_tmdb = []

    # --- Loop para enriquecer itens ---
    for item in items:
        if not isinstance(item, dict):
            continue

        title = item.get('title') or item.get('name') or 'Sem título'
        tmdb_id = item.get('tmdb') or item.get('tmdb_id')
        media_type = item.get('tmdb_type') or item.get('type') or "movie"
        meta = None

        # --- Carrega cache se existir ---
        if tmdb_id and cache_movies_dir:
            cache_filename = f"{media_type}_{tmdb_id}.json"
            if cache_filename in existing_cache_files:
                try:
                    with open(os.path.join(cache_movies_dir, cache_filename), "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    meta = None

        # --- Buscar TMDB se cache não existir ---
        if tmdb_id and not meta:
            missing_tmdb.append((item, media_type, tmdb_id))
            enriched_items.append((item, None))
            continue

        enriched_items.append((item, meta))

    # --- Fazendo TMDB fetch para todos itens faltantes em lote ---
    if missing_tmdb:
        from resources.lib import tmdb_helper

        for (item, media_type, tmdb_id) in missing_tmdb:
            try:
                meta = tmdb_helper.fetch_tmdb_movie(str(tmdb_id)) if media_type.lower() == "movie" else tmdb_helper.fetch_tmdb(str(tmdb_id))
                if meta and cache_movies_dir:
                    try:
                        with open(os.path.join(cache_movies_dir, f"{media_type}_{tmdb_id}.json"), "w", encoding="utf-8") as cf:
                            json.dump(meta, cf, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                enriched_items.append((item, meta))
            except Exception:
                enriched_items.append((item, None))

    # --- Construir dados finais para o builder ---
    final_list = []

    for (item, meta) in enriched_items:
        try:
            # --- Preparar ListItem base ---
            processed = item.copy()

            # --- Mapear TMDB meta se existir ---
            if meta:
                try:
                    poster_path = meta.get("poster_path")
                    backdrop_path = meta.get("backdrop_path")

                    if poster_path:
                        processed["poster"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
                    if backdrop_path:
                        processed["fanart"] = f"https://image.tmdb.org/t/p/original{backdrop_path}"

                    # Copiar campos essenciais
                    processed.setdefault("overview", meta.get("overview"))
                    processed.setdefault("genres", meta.get("genres"))
                    processed.setdefault("release_date", processed.get("date") or meta.get("release_date"))
                    processed.setdefault("rating", meta.get("vote_average"))
                    processed.setdefault("votes", meta.get("vote_count"))
                except Exception:
                    pass

            final_list.append(processed)

        except Exception as e_item:
            xbmc.log(f"[SUPREME][CACHE] Erro ao processar item meta: {e_item}", xbmc.LOGERROR)

    xbmc.log(f"[SUPREME][FLOW] Itens prontos: {len(final_list)} — chamando builder", xbmc.LOGDEBUG)

    # --- Chama o builder final ---
    try:
        # Usa lista pura, sem base64 pesado
        return buildLibraryMenus_supreme(final_list, fanart)
    except Exception as e_builder:
        xbmc.log(f"[SUPREME][ERROR] Falha no builder: {e_builder}", xbmc.LOGERROR)
        return False
    
    
import sys, urllib.parse, xbmc, base64, json

def parse_plugin_params():
    """
    Lê e decodifica os parâmetros do plugin de forma à prova de erro.
    Corrige truncamentos (ex: url=W em vez de base64 completo).
    Faz logs detalhados para diagnóstico.
    Retorna um dicionário limpo: {"mode": int, "url": payload, ...}
    """
    try:
        raw_argv = sys.argv[2] if len(sys.argv) > 2 else ""
        if raw_argv.startswith("?"):
            raw_argv = raw_argv[1:]

        xbmc.log(f"[SUPREME][PARAMS] argv[2] raw repr={repr(raw_argv[:300])}", xbmc.LOGINFO)

        # 🔹 Faz parsing básico (sem quebrar Base64)
        params = urllib.parse.parse_qs(raw_argv, keep_blank_values=True)

        clean_params = {}
        for k, v in params.items():
            if isinstance(v, list):
                v = v[0]
            clean_params[k] = v
        xbmc.log(f"[SUPREME][PARAMS] keys={list(clean_params.keys())}", xbmc.LOGINFO)

        # 🔹 Decodifica mode (seguro)
        mode = clean_params.get("mode")
        try:
            clean_params["mode"] = int(mode) if mode is not None and str(mode).isdigit() else None
        except Exception:
            clean_params["mode"] = None

        # 🔹 Processa URL (ponto crítico)
        raw_url_param = clean_params.get("url", "")
        if not raw_url_param:
            xbmc.log("[SUPREME][PARAMS] Nenhum parâmetro 'url' encontrado", xbmc.LOGWARNING)
            clean_params["url"] = ""
            return clean_params

        xbmc.log(f"[SUPREME][PARAMS] raw_url_param repr={repr(raw_url_param[:200])} len={len(raw_url_param)}", xbmc.LOGINFO)

        payload = None

        # 1️⃣ Tenta decodificar Base64 urlsafe
        try:
            pad = '=' * ((4 - len(raw_url_param) % 4) % 4)
            decoded_b64 = base64.urlsafe_b64decode(raw_url_param + pad).decode("utf-8")
            if decoded_b64 and (decoded_b64.startswith("[") or decoded_b64.startswith("{")):
                payload = decoded_b64
                xbmc.log(f"[SUPREME][PARAMS] payload decodificado via Base64 (len={len(payload)})", xbmc.LOGINFO)
        except Exception as e_b64:
            xbmc.log(f"[SUPREME][PARAMS] Base64 decode falhou: {e_b64}", xbmc.LOGDEBUG)

        # 2️⃣ Se não for base64 → tenta unquote_plus
        if payload is None:
            try:
                decoded_unquote = urllib.parse.unquote_plus(raw_url_param)
                xbmc.log(f"[SUPREME][PARAMS] payload obtido via unquote_plus (len={len(decoded_unquote)})", xbmc.LOGINFO)
                payload = decoded_unquote
            except Exception as e_up:
                xbmc.log(f"[SUPREME][PARAMS] unquote_plus falhou: {e_up}", xbmc.LOGERROR)
                payload = raw_url_param

        clean_params["url"] = payload

        # 3️⃣ Log final
        xbmc.log(f"[SUPREME][PARAMS] decode final len={len(str(payload))} preview={str(payload)[:120]}", xbmc.LOGINFO)

        return clean_params

    except Exception as e:
        xbmc.log(f"[SUPREME][PARAMS] Falha fatal ao processar parâmetros: {e}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        return {}
    
import json
from urllib.parse import unquote_plus

def _ensure_items_supreme(payload):
    """
    🔰 SUPREME v2.2 — Interpreta e normaliza payloads complexos.
    Compatível com Base64 truncado, duplo encode e URLs Kodi.
    Corrige o bug clássico de 'apenas primeira letra indo'.
    """
    import json, base64, urllib.parse, xbmc, re

    try:
        if payload is None:
            xbmc.log("[SUPREME][ENSURE] payload=None → []", xbmc.LOGINFO)
            return []

        # ✅ 1️⃣ Se já for lista/dict
        if isinstance(payload, list):
            xbmc.log(f"[SUPREME][ENSURE] payload list len={len(payload)}", xbmc.LOGINFO)
            return payload
        if isinstance(payload, dict):
            xbmc.log("[SUPREME][ENSURE] payload dict → [dict]", xbmc.LOGINFO)
            return [payload]

        # ✅ 2️⃣ Se for string
        if isinstance(payload, str):
            s = payload.strip()
            if not s or s == "%":
                xbmc.log("[SUPREME][ENSURE] payload inválido isolado (%)", xbmc.LOGERROR)
                return []

            # 🔹 Se tiver parâmetros extras tipo "|studio=" → remove o extra
            if "|" in s:
                parts = s.split("|", 1)
                s = parts[0]
                xbmc.log(f"[SUPREME][ENSURE] cortado no '|' → len={len(s)}", xbmc.LOGDEBUG)
            elif "&studio=" in s:
                s = re.split(r"&studio=.*", s)[0]
                xbmc.log(f"[SUPREME][ENSURE] cortado no '&studio=' → len={len(s)}", xbmc.LOGDEBUG)

            xbmc.log(f"[SUPREME][ENSURE] recebido str len={len(s)} preview={s[:80]}", xbmc.LOGINFO)

            # 🔹 3️⃣ Tenta Base64 urlsafe
            try:
                pad = '=' * ((4 - len(s) % 4) % 4)
                decoded_b64 = base64.urlsafe_b64decode(s + pad).decode("utf-8", errors="ignore")
                if decoded_b64 and (decoded_b64.startswith("[") or decoded_b64.startswith("{")):
                    xbmc.log(f"[SUPREME][ENSURE] decodificado via base64url len={len(decoded_b64)}", xbmc.LOGINFO)
                    parsed = json.loads(decoded_b64)
                    return parsed if isinstance(parsed, list) else [parsed]
            except Exception as e_b64:
                xbmc.log(f"[SUPREME][ENSURE] base64url falhou: {e_b64}", xbmc.LOGDEBUG)

            # 🔹 4️⃣ Tenta unquote_plus (corrige %25, +, etc)
            try:
                decoded = urllib.parse.unquote_plus(s)
                if decoded != s:
                    xbmc.log(f"[SUPREME][ENSURE] unquoted (mudou) preview={decoded[:80]}", xbmc.LOGINFO)
                else:
                    xbmc.log("[SUPREME][ENSURE] unquoted (idêntico)", xbmc.LOGDEBUG)
            except Exception as e_u:
                xbmc.log(f"[SUPREME][ENSURE] unquote_plus falhou: {e_u}", xbmc.LOGERROR)
                decoded = s

            # 🔹 5️⃣ JSON direto
            if decoded.startswith("[") or decoded.startswith("{"):
                try:
                    parsed = json.loads(decoded)
                    xbmc.log(f"[SUPREME][ENSURE] JSON válido tipo={type(parsed).__name__}", xbmc.LOGINFO)
                    return parsed if isinstance(parsed, list) else [parsed]
                except Exception as e_json:
                    xbmc.log(f"[SUPREME][ENSURE] JSON inválido: {e_json}", xbmc.LOGERROR)

            # 🔹 6️⃣ URL HTTP
            if decoded.startswith("http"):
                xbmc.log(f"[SUPREME][ENSURE] URL detectada: {decoded[:120]}", xbmc.LOGINFO)
                try:
                    from resources.lib.utils import makeRequest
                    raw = makeRequest(decoded)
                    txt = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    parsed = json.loads(txt)
                    xbmc.log(f"[SUPREME][ENSURE] JSON baixado via HTTP len={len(parsed)}", xbmc.LOGINFO)
                    return parsed if isinstance(parsed, list) else [parsed]
                except Exception as e_req:
                    xbmc.log(f"[SUPREME][ENSURE] erro HTTP: {e_req}", xbmc.LOGERROR)
                    return []

            xbmc.log(f"[SUPREME][ENSURE] string não reconhecida (preview={decoded[:60]})", xbmc.LOGERROR)
            return []

        xbmc.log(f"[SUPREME][ENSURE] tipo inesperado {type(payload)}", xbmc.LOGERROR)
        return []

    except Exception as e:
        xbmc.log(f"[SUPREME][ENSURE] erro geral: {e}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        return []


def _safe_call_getDataFromJson(items, fanart):
    """
    Executa getDataFromJson de forma segura.
    - Garante tipo de items (list)
    - Evita travamento por payload malformado
    - Usa fallback manual robusto se falhar
    - Fecha o diretório corretamente em todos os casos
    """
    try:
        # 🔹 Garante que items é lista válida
        if not isinstance(items, list):
            try:
                from resources.lib.utils import _ensure_items
                items = _ensure_items(items)
            except Exception as e_conv:
                _log_error(f"_safe_call_getDataFromJson: erro ao converter items: {e_conv}")
                items = []

        # 🔹 Evita crash em lista vazia
        if not items:
            _log_debug("_safe_call_getDataFromJson: lista vazia, abortando.")
            xbmcgui.Dialog().notification("Nenhum conteúdo", "Lista de filmes vazia", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=True)
            return False

        # 🔹 Tenta o método completo (Menus.getDataFromJson)
        try:
            getDataFromJson(items, fanart)
            _log_debug(f"_safe_call_getDataFromJson: getDataFromJson executado com sucesso ({len(items)} itens)")
            return True
        except Exception as e_gdfj:
            _log_error(f"getDataFromJson falhou: {e_gdfj}")
            import traceback
            xbmc.log(traceback.format_exc(), xbmc.LOGERROR)

        # --- 🔸 Fallback manual se getDataFromJson falhar ---
        _log_debug("_safe_call_getDataFromJson: executando fallback manual...")
        count = 0
        for it in items:
            try:
                title = str(it.get('title') or it.get('name') or it.get('label') or 'Sem título')
                url = str(it.get('url') or it.get('link') or '')
                thumb = it.get('icon') or it.get('thumbnail') or ''
                fan = it.get('fanart') or fanart or ''
                desc = it.get('description') or it.get('plot') or ''
                is_folder = bool(it.get('isFolder') or it.get('folder') or it.get('type') == 'folder')

                li = xbmcgui.ListItem(label=title)
                li.setInfo('video', {'title': title, 'plot': desc})
                if thumb or fan:
                    li.setArt({'thumb': thumb, 'icon': thumb, 'fanart': fan})

                xbmcplugin.addDirectoryItem(ADDON_HANDLE, url, li, is_folder)
                count += 1
            except Exception as e_item:
                _log_error(f"Erro no fallback ao adicionar item '{it.get('title', '?')}': {e_item}")

        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        _log_debug(f"_safe_call_getDataFromJson: fallback manual adicionou {count} itens")
        return False

    except Exception as e:
        _log_error(f"Erro fatal em _safe_call_getDataFromJson: {e}")
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return False


def _add_dir_via_default_or_manual_supreme(name, payload, mode, icon, fanart, desc="", extra_params=None):
    """
    Adiciona um item de diretório ao Kodi (menu ou submenu) com logs detalhados.
    🔹 Suporte para parâmetros extras (ex: {"studio": "Warner Bros."})
    🔹 Usa Base64 seguro para payloads complexos
    🔹 Compatível com parse_plugin_params() e listagem Supreme
    """
    import xbmcgui, xbmcplugin, json, base64, sys, urllib.parse

    try:
        _log_debug(f"[DIR] Adicionando item: {name} (mode={mode})")

        # 🔹 Codifica o payload de forma segura (JSON → base64url)
        if isinstance(payload, (list, dict)):
            json_data = json.dumps(payload, ensure_ascii=False)
            b64_data = base64.urlsafe_b64encode(json_data.encode("utf-8")).decode("utf-8").rstrip("=")
            url_param = b64_data
            _log_debug(f"[DIR] Payload bruto ({name}) preview: {json_data[:150]}")
        elif isinstance(payload, str):
            url_param = payload
            _log_debug(f"[DIR] Payload string ({name}) preview: {payload[:150]}")
        else:
            _log_error(f"[DIR] Tipo de payload inválido: {type(payload)}")
            return

        # 🔹 Monta parâmetros base do plugin
        query = {
            "url": url_param,
            "mode": mode,
            "name": name,
            "fanart": fanart or "",
            "desc": desc or "",
        }

        # 🔹 Inclui parâmetros extras, se houver
        if extra_params and isinstance(extra_params, dict):
            for k, v in extra_params.items():
                query[k] = str(v)
            _log_debug(f"[DIR] extra_params incluídos: {extra_params}")

        # 🔹 Monta URL final sem quebrar Base64
        from urllib.parse import urlencode
        final_url = f"{sys.argv[0]}?{urlencode(query, quote_via=urllib.parse.quote)}"
        _log_debug(f"[DIR] URL construída: {final_url[:300]}")

        # 🔹 Cria ListItem visual
        li = xbmcgui.ListItem(label=name)
        li.setArt({"icon": icon or "", "thumb": icon or "", "fanart": fanart or ""})
        li.setInfo("video", {"title": name, "plot": desc or ""})
        li.setProperty("IsPlayable", "false")

        xbmcplugin.addDirectoryItem(
            handle=int(sys.argv[1]),
            url=final_url,
            listitem=li,
            isFolder=True
        )

        _log_debug(f"[DIR] Diretório adicionado manualmente: {name} (mode={mode})")

    except Exception as e:
        _log_error(f"[DIR] Erro ao adicionar diretório '{name}': {e}")

# -------------------------
# Funções exportadas
# -------------------------

import json, urllib.parse

def buildLibraryMenus_supreme(items_or_payload, fanart):
    """
    🔰 SUPREME — Build Library Menus (v2.0)
    Cria menus de biblioteca à prova de erros e truncamentos Base64.
    Recursos:
      ✅ Suporta payloads complexos: list | dict | JSON | Base64 seguro
      ✅ Evita bug de "primeira letra" (padding e re-encode automático)
      ✅ Usa _ensure_items_supreme para garantir integridade
      ✅ Payloads passam intactos entre submenus (Ano, Gênero, Estúdio etc.)
      ✅ Logs ricos para rastreamento de fluxo
    """
    import xbmc, xbmcplugin, xbmcgui, json, base64, sys
    from resources.lib.utils import _log_debug, _log_error

    _log_debug("[SUPREME][FILMES] buildLibraryMenus_supreme iniciado")

    try:
        # 1️⃣ Normaliza payload de forma segura
        try:
            items = _ensure_items_supreme(items_or_payload)
            tipo = type(items).__name__
            _log_debug(f"[SUPREME][FILMES] Payload normalizado: tipo={tipo}, len={len(items) if isinstance(items, list) else 1}")
        except Exception as e_norm:
            _log_error(f"[SUPREME][FILMES] Falha ao normalizar payload: {e_norm}")
            xbmcgui.Dialog().notification("Erro", "Falha ao processar biblioteca", xbmcgui.NOTIFICATION_ERROR, 4000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        if not items:
            _log_error("[SUPREME][FILMES] Nenhum item válido após normalização")
            xbmcgui.Dialog().notification("Sem conteúdo", "Biblioteca vazia", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        # 2️⃣ Re-encoda payload para Base64 seguro e completo (sem truncamento)
        try:
            json_data = json.dumps(items, ensure_ascii=False)
            payload_encoded = base64.urlsafe_b64encode(json_data.encode("utf-8")).decode("utf-8").rstrip("=")
            _log_debug(f"[SUPREME][FILMES] Payload re-encodado com sucesso, len={len(payload_encoded)}")
        except Exception as e_b64:
            _log_error(f"[SUPREME][FILMES] Erro ao re-encodar Base64: {e_b64}")
            payload_encoded = ""

        # 3️⃣ Submenus fixos do SUPREME
        _log_debug("[SUPREME][FILMES] Gerando submenus fixos da biblioteca")

        # Observação: usamos sempre o payload completo re-encodado
        _add_dir_via_default_or_manual_supreme(
            "🎬 Todos os Filmes", payload_encoded, 101, "", fanart, "Exibir todos os filmes disponíveis"
        )
        _add_dir_via_default_or_manual_supreme(
            "🔍 Pesquisar", payload_encoded, 102, "", fanart, "Pesquisar filmes por nome ou palavra-chave"
        )
        _add_dir_via_default_or_manual_supreme(
            "📅 Por Ano", payload_encoded, 108, "", fanart, "Filtrar filmes por ano de lançamento"
        )
        _add_dir_via_default_or_manual_supreme(
            "🎭 Por Gênero", payload_encoded, 103, "", fanart, "Filtrar filmes por gênero"
        )
        _add_dir_via_default_or_manual_supreme(
            "🏭 Por Estúdio", payload_encoded, 110, "", fanart, "Filtrar por estúdio de produção"
        )
        _add_dir_via_default_or_manual_supreme(
            "🎞️ Coleções", payload_encoded, 113, "", fanart, "Filmes agrupados por coleção"
        )
        _add_dir_via_default_or_manual_supreme(
            "🆕 Lançamentos", payload_encoded, 104, "", fanart, "Filmes lançados recentemente"
        )
        _add_dir_via_default_or_manual_supreme(
            "🔥 Mais Populares", payload_encoded, 105, "", fanart, "Filmes mais populares no momento"
        )
        _add_dir_via_default_or_manual_supreme(
            "⭐ Mais Avaliados", payload_encoded, 106, "", fanart, "Filmes com as maiores notas"
        )

        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        _log_debug("[SUPREME][FILMES] buildLibraryMenus_supreme finalizado com sucesso ✅")

    except Exception as e_main:
        import traceback
        _log_error(f"[SUPREME][FILMES] Erro inesperado: {e_main}")
        _log_error(traceback.format_exc())
        try:
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        except Exception:
            pass
            
def buildListItemFromMeta(meta, fanart):
    """
    Cria um xbmcgui.ListItem completo e robusto a partir de um dicionário de metadados TMDB (cacheado).
    Compatível com Kodi 20+ (Nexus/Omega) e formato SUPREME.
    """
    import xbmc
    import xbmcgui

    try:
        if not isinstance(meta, dict):
            xbmc.log("[ADDON-ERROR][SUPREME] meta inválido (não é dict)", xbmc.LOGERROR)
            return xbmcgui.ListItem("Item inválido")

        # --- 🔹 Campos principais ---
        title = meta.get("title") or meta.get("original_title") or meta.get("name") or "Sem título"
        overview = meta.get("overview") or meta.get("plot") or "Sem descrição disponível."
        release_date = meta.get("release_date") or meta.get("first_air_date") or ""
        year = release_date[:4] if isinstance(release_date, str) and len(release_date) >= 4 else ""

        # --- 🔹 Imagens ---
        poster = meta.get("poster_path") or meta.get("poster") or ""
        backdrop = meta.get("backdrop_path") or meta.get("backdrop") or ""
        poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster and not str(poster).startswith("http") else poster
        fanart_url = f"https://image.tmdb.org/t/p/original{backdrop}" if backdrop and not str(backdrop).startswith("http") else backdrop
        fanart_final = fanart_url or fanart or ""

        liz = xbmcgui.ListItem(label=title)
        tag = liz.getVideoInfoTag()

        # --- 🔹 Gêneros ---
        genres = []
        try:
            genres_raw = meta.get("genres") or []
            if isinstance(genres_raw, list):
                genres = [g["name"] for g in genres_raw if isinstance(g, dict) and g.get("name")]
        except Exception:
            pass

        # --- 🔹 Estúdios e países ---
        studios = []
        try:
            studios_raw = meta.get("production_companies") or []
            studios = [s["name"] for s in studios_raw if isinstance(s, dict) and s.get("name")]
        except Exception:
            pass

        countries = []
        try:
            countries_raw = meta.get("production_countries") or []
            countries = [c["name"] for c in countries_raw if isinstance(c, dict) and c.get("name")]
        except Exception:
            pass

        # --- 🔹 Avaliação, votos e duração ---
        rating = float(meta.get("vote_average") or 0)
        votes = int(meta.get("vote_count") or 0)
        duration = int(meta.get("runtime") or 0)

        # --- 🔹 Diretor e roteirista ---
        directors, writers = [], []
        try:
            crew = meta.get("credits", {}).get("crew", [])
            if isinstance(crew, list):
                directors = [d["name"] for d in crew if d.get("job") == "Director"]
                writers = [d["name"] for d in crew if d.get("job") in ("Writer", "Screenplay")]
        except Exception:
            pass

        # --- 🔹 Classificação indicativa (MPAA) ---
        mpaa = "N/A"
        try:
            release_data = meta.get("release_dates", {}).get("results", [])
            for r in release_data:
                if r.get("iso_3166_1") in ["US", "BR"]:
                    for rd in r.get("release_dates", []):
                        cert = rd.get("certification")
                        if cert:
                            mpaa = cert
                            break
                    if mpaa != "N/A":
                        break
        except Exception:
            pass

        # --- 🔹 Preenche o VideoInfoTag ---
        tag.setTitle(title)
        tag.setOriginalTitle(meta.get("original_title", title))
        tag.setPlot(overview)
        if year:
            tag.setYear(int(year))
        tag.setMpaa(mpaa)
        if duration:
            tag.setDuration(duration * 60)
        if release_date:
            tag.setPremiered(release_date)
        if rating > 0:
            tag.setRating(rating)
        if votes > 0:
            tag.setVotes(votes)
        if studios:
            tag.setStudios(studios)
        if countries:
            tag.setCountries(countries)
        if genres:
            tag.setGenres(genres)
        if directors:
            tag.setDirectors(directors)
        if writers:
            tag.setWriters(writers)

        # --- 🔹 Elenco (compatível com API moderna) ---
        try:
            cast_data = meta.get("credits", {}).get("cast", [])
            if isinstance(cast_data, list):
                actor_list = []
                for c in cast_data[:20]:
                    name = c.get("name")
                    if not name:
                        continue
                    role = c.get("character") or ""
                    thumb = c.get("profile_path") or ""
                    if thumb:
                        if not str(thumb).startswith("http"):
                            thumb = f"https://image.tmdb.org/t/p/w300{thumb}"
                    else:
                        thumb = "https://i.imgur.com/H1W4YQZ.png"

                    try:
                        actor_obj = {"name": name, "role": role, "thumbnail": thumb}
                    except TypeError:
                        actor_obj = xbmc.Actor(name, role)
                    actor_list.append(actor_obj)

                if actor_list:
                    tag.setCast(actor_list)
                    xbmc.log(f"[ADDON-DEBUG][SUPREME] Elenco definido ({len(actor_list)} nomes) → {title}", xbmc.LOGINFO)
        except Exception as e_cast:
            xbmc.log(f"[ADDON-ERROR][SUPREME] Falha ao definir elenco: {e_cast}", xbmc.LOGERROR)

        # --- 🔹 Artes e propriedades ---
        liz.setArt({
            "thumb": poster_url,
            "poster": poster_url,
            "fanart": fanart_final,
            "icon": poster_url
        })
        liz.setProperty("IsPlayable", "true")

        xbmc.log(f"[ADDON-DEBUG][SUPREME] Item criado com sucesso: {title}", xbmc.LOGINFO)
        return liz

    except Exception as e:
        xbmc.log(f"[ADDON-ERROR][SUPREME] Erro inesperado em buildListItemFromMeta: {e}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        return xbmcgui.ListItem("Erro ao criar item")


# --- 🧠 Agora o listAllItems aprimorado (sem apagar nada original) ---
def listAllItems(fanart, mode=None):
    import os, json
    xbmc.log("[ADDON-DEBUG][CACHE] listAllItems iniciado", xbmc.LOGINFO)
    try:
        addon_local = xbmcaddon.Addon()
        profile_local = TRANSLATEPATH(addon_local.getAddonInfo('profile'))
        cache_movies_dir = os.path.join(profile_local, "cache", "movies")

        if not os.path.exists(cache_movies_dir):
            xbmc.log("[ADDON-ERROR][CACHE] Pasta de cache não encontrada", xbmc.LOGERROR)
            xbmcplugin.endOfDirectory(int(sys.argv[1]))
            return

        files = [f for f in os.listdir(cache_movies_dir) if f.endswith(".json")]
        xbmc.log(f"[ADDON-DEBUG][CACHE] {len(files)} arquivos encontrados", xbmc.LOGINFO)

        for filename in files:
            try:
                file_path = os.path.join(cache_movies_dir, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                # 🆕 Usa função aprimorada
                liz = buildListItemFromMeta(meta, fanart)

                url = meta.get("homepage") or ""
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, liz, isFolder=False)

            except Exception as e_file:
                xbmc.log(f"[ADDON-ERROR][CACHE] Falha ao processar {filename}: {e_file}", xbmc.LOGERROR)

        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        xbmc.log("[ADDON-DEBUG][CACHE] listAllItems finalizado", xbmc.LOGINFO)

    except Exception as e:
        xbmc.log(f"[ADDON-ERROR][CACHE] Erro em listAllItems: {e}", xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)


def searchItems(query, fanart, mode=None):
    """
    🔍 SUPREME - Busca completa de filmes no cache local TMDB.
    - Pesquisa por título, descrição ou gênero.
    - Usa enrich_with_cache para complementar dados.
    - Exibe metadados completos via buildMenuFromJson_supreme.
    """
    import os, json, xbmc, xbmcgui, xbmcplugin, xbmcaddon, sys
    from xbmcvfs import translatePath as TRANSLATEPATH
    from resources.lib.utils import enrich_with_cache, buildMenuFromJson_supreme

    xbmc.log(f"[SUPREME][FLOW] searchItems iniciado — termo: {query}", xbmc.LOGINFO)

    try:
        addon = xbmcaddon.Addon()
        profile = TRANSLATEPATH(addon.getAddonInfo("profile"))
        cache_dir = os.path.join(profile, "cache", "movies")

        if not os.path.exists(cache_dir):
            xbmc.log("[SUPREME][CACHE] Nenhum diretório de cache encontrado", xbmc.LOGWARNING)
            xbmcgui.Dialog().notification("Busca", "Nenhum cache encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        termo = str(query).strip().lower()
        resultados = []

        # --- Busca nos arquivos de cache ---
        for file in os.listdir(cache_dir):
            if not file.endswith(".json"):
                continue
            try:
                with open(os.path.join(cache_dir, file), "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e_file:
                xbmc.log(f"[SUPREME][CACHE] Erro ao ler cache {file}: {e_file}", xbmc.LOGERROR)
                continue

            titulo = (meta.get("title") or meta.get("original_title") or "").lower()
            overview = (meta.get("overview") or "").lower()
            generos = ", ".join(
                [g.get("name") for g in meta.get("genres", []) if isinstance(g, dict)]
            ).lower()

            if termo in titulo or termo in overview or termo in generos:
                resultados.append(meta)

        if not resultados:
            xbmcgui.Dialog().notification("Busca", "Nenhum filme encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            xbmc.log(f"[SUPREME][FLOW] Nenhum resultado encontrado para '{query}'", xbmc.LOGINFO)
            return

        xbmc.log(f"[SUPREME][FLOW] {len(resultados)} resultados encontrados para '{query}'", xbmc.LOGINFO)

        # --- Enriquecimento adicional de metadados ---
        try:
            resultados = enrich_with_cache(resultados)
            xbmc.log(f"[SUPREME][CACHE] Itens enriquecidos com cache: {len(resultados)}", xbmc.LOGINFO)
        except Exception as e_enrich:
            xbmc.log(f"[SUPREME][CACHE] Falha ao enriquecer resultados: {e_enrich}", xbmc.LOGERROR)

        # --- Complementar com crew e votos ---
        for item in resultados:
            try:
                crew = item.get("crew") or item.get("credits", {}).get("crew", [])
                if crew:
                    directors = [d["name"] for d in crew if d.get("job") == "Director"]
                    writers = [w["name"] for w in crew if w.get("job") in ("Writer", "Screenplay")]
                    if directors:
                        item["directors"] = directors
                    if writers:
                        item["writers"] = writers

                if not item.get("votes"):
                    item["votes"] = item.get("vote_count") or 0

                if not item.get("release_date") and item.get("first_air_date"):
                    item["release_date"] = item["first_air_date"]

            except Exception as e_meta:
                xbmc.log(f"[SUPREME][FLOW] Falha ao complementar metadados: {e_meta}", xbmc.LOGERROR)

        # --- Exibir via menu SUPREME completo ---
        try:
            buildMenuFromJson_supreme(resultados, fanart, f"Resultados para '{query}'")
            xbmc.log(f"[SUPREME][FLOW] searchItems exibiu {len(resultados)} itens", xbmc.LOGINFO)
        except Exception as e_build:
            xbmc.log(f"[SUPREME][FLOW] Erro ao montar menu SUPREME na busca: {e_build}", xbmc.LOGERROR)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)

    except Exception as e_main:
        xbmc.log(f"[SUPREME][FLOW] Erro inesperado em searchItems: {e_main}", xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        
def listGenres(payload, fanart):
    """
    🎭 SUPREME — Gera submenu "Por Gênero"
    - Extrai gêneros automaticamente dos metadados
    - Usa enrich_with_cache() local
    - Payloads seguros (Base64 completo)
    - Compatível com listItemsByGenre (mode=112)
    - Normalização consistente com filtro final
    """

    import xbmc
    import xbmcplugin
    import xbmcgui
    import json
    import base64
    import os
    import sys

    from resources.lib.utils import (
        enrich_with_cache,
        normalize,
        build_plugin_url_supreme,
        _log_debug,
        _log_error
    )

    _log_debug("[SUPREME][FLOW] listGenres iniciado")

    try:
        # 🔹 Normaliza payload recebido
        items = _ensure_items_supreme(payload)

        # 🔹 Fallback cache local
        if not items:
            xbmc.log(
                "[SUPREME][FLOW] listGenres: payload vazio, tentando cache local",
                xbmc.LOGWARNING
            )

            from xbmcvfs import translatePath as TRANSLATEPATH
            import xbmcaddon

            addon = xbmcaddon.Addon()
            profile = TRANSLATEPATH(addon.getAddonInfo("profile"))
            cache_dir = os.path.join(profile, "cache", "movies")

            if os.path.exists(cache_dir):
                for f in os.listdir(cache_dir):
                    if f.endswith(".json"):
                        with open(os.path.join(cache_dir, f), "r", encoding="utf-8") as fh:
                            items.append(json.load(fh))

        _log_debug(f"[SUPREME][FLOW] listGenres: total de itens recebidos = {len(items)}")

        # 🔹 Enriquecimento
        items = enrich_with_cache(items)
        _log_debug(f"[SUPREME][FLOW] listGenres: itens enriquecidos = {len(items)}")

    except Exception as e_items:
        _log_error(f"[SUPREME][FLOW] Falha ao preparar gêneros: {e_items}")
        xbmcgui.Dialog().notification(
            "Erro",
            "Falha ao processar lista de gêneros",
            xbmcgui.NOTIFICATION_ERROR,
            4000
        )
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    # 🔥 EXTRAÇÃO COM NORMALIZAÇÃO SEGURA
    genre_map = {}

    for meta in items:
        genres = meta.get("genres") or meta.get("genre") or []

        if isinstance(genres, list):
            for g in genres:
                if isinstance(g, dict) and g.get("name"):
                    original = g["name"].strip()
                    key = normalize(original)
                    if key and key not in genre_map:
                        genre_map[key] = original

        elif isinstance(genres, str):
            original = genres.strip()
            key = normalize(original)
            if key and key not in genre_map:
                genre_map[key] = original

    if not genre_map:
        _log_debug("[SUPREME][FLOW] listGenres: Nenhum gênero detectado")
        xbmcgui.Dialog().notification(
            "Sem dados",
            "Nenhum gênero detectado",
            xbmcgui.NOTIFICATION_INFO,
            3000
        )
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    genres_unicos = sorted(genre_map.values())
    _log_debug(f"[SUPREME][FLOW] Gêneros detectados: {genres_unicos}")

    # 🔹 Re-encodar payload completo
    try:
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(items, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8").rstrip("=")

        for genre in genres_unicos:
            desc = f"Filmes do gênero {genre}"

            # 🔥 CORREÇÃO REAL: parâmetros separados
            params = {
                "mode": 112,
                "url": payload_encoded,
                "genre": genre
            }

            plugin_url = build_plugin_url_supreme(sys.argv[0], params)

            liz = xbmcgui.ListItem(label=f"🎭 {genre}")
            liz.setArt({'fanart': fanart})
            liz.setProperty('IsPlayable', 'false')

            xbmcplugin.addDirectoryItem(
                handle=int(sys.argv[1]),
                url=plugin_url,
                listitem=liz,
                isFolder=True
            )

        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        _log_debug("[SUPREME][FLOW] listGenres finalizado com sucesso ✅")

    except Exception as e_menu:
        _log_error(f"[SUPREME][FLOW] Erro ao montar menu de gêneros: {e_menu}")
        xbmcgui.Dialog().notification(
            "Erro",
            "Falha ao criar menu de gêneros",
            xbmcgui.NOTIFICATION_ERROR,
            4000
        )
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        
def listItemsByGenre(payload, fanart, genre_name):
    """
    🎭 SUPREME - Lista filmes de um gênero específico
    ✔ Recebe Base64 limpo
    ✔ Recebe gênero separado via parâmetro
    ✔ Corrige encoding (acentos)
    ✔ Filtro seguro com normalize()
    ✔ enrich_with_cache seguro
    """

    import json
    import sys
    import base64
    import urllib.parse
    import xbmc
    import xbmcgui
    import xbmcplugin

    from resources.lib.utils import (
        enrich_with_cache,
        buildMenuFromJson_supreme,
        normalize,
        _log_debug,
        _log_error
    )

    try:
        _log_debug(f"[SUPREME][FLOW] listItemsByGenre iniciado — gênero RAW={genre_name}")

        # 🔥 CORREÇÃO IMPORTANTE — decodificar URL
        genre_name = urllib.parse.unquote_plus(genre_name)

        _log_debug(f"[SUPREME][FLOW] gênero decodificado={genre_name}")

        # 🔹 Decodifica Base64
        pad = "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.urlsafe_b64decode(payload + pad).decode("utf-8")
        items = json.loads(decoded)

        if not items:
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        # 🔥 Normalização correta
        genre_clean = normalize(genre_name)
        resultados = []

        for meta in items:
            genres = meta.get("genres") or meta.get("genre") or []
            names = []

            if isinstance(genres, list):
                for g in genres:
                    if isinstance(g, dict) and g.get("name"):
                        names.append(normalize(g["name"]))
                    elif isinstance(g, str):
                        names.append(normalize(g))
            elif isinstance(genres, str):
                names.append(normalize(genres))

            if genre_clean in names:
                resultados.append(meta)

        _log_debug(f"[SUPREME][FLOW] Filmes filtrados por gênero: {len(resultados)}")

        if not resultados:
            xbmcgui.Dialog().notification(
                "Gênero",
                f"Nenhum filme encontrado para {genre_name}",
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        # 🔹 Já vêm enriquecidos do menu anterior

        # 🔹 Exibição
        buildMenuFromJson_supreme(
            resultados,
            fanart,
            f"Filmes do gênero {genre_name}"
        )

        xbmcplugin.endOfDirectory(int(sys.argv[1]))

        xbmc.log(
            f"[SUPREME][FLOW] listItemsByGenre exibiu {len(resultados)} filmes — gênero={genre_name}",
            xbmc.LOGINFO
        )

    except Exception as e:
        _log_error(f"[SUPREME][FLOW] Erro fatal em listItemsByGenre: {e}")
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        
def listYears(payload, fanart):
    """
    🔰 Sistema Supreme — Gera submenu "Por Ano"
    - Enriquecimento local via cache TMDB (sem API)
    - Extrai anos automaticamente dos metadados
    - Usa Base64 seguro no payload (sem double encoding)
    - Compatível com listItemsByYear (mode=109)
    """
    import xbmc, xbmcplugin, xbmcgui, json, base64, sys

    _log_debug("[SUPREME][FLOW] listYears iniciado")

    try:
        # 🔹 Normaliza o payload recebido
        items = _ensure_items_supreme(payload)
        _log_debug(f"[SUPREME][FLOW] listYears: total de itens recebidos = {len(items)}")

        # 🔹 Enriquecer via cache local (sem API)
        from resources.lib.utils import enrich_with_cache
        items = enrich_with_cache(items)
        _log_debug(f"[SUPREME][FLOW] listYears: itens enriquecidos = {len(items)}")

    except Exception as e_items:
        _log_error(f"[SUPREME][FLOW] Falha ao preparar itens: {e_items}")
        xbmcgui.Dialog().notification("Erro", "Falha ao processar lista de anos", xbmcgui.NOTIFICATION_ERROR, 4000)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    # --- Extrair anos dos itens enriquecidos ---
    anos_detectados = []
    for i in items:
        ano = None
        for key in ("year", "release_date", "date"):
            val = i.get(key)
            if val:
                if isinstance(val, str) and len(val) >= 4 and val[:4].isdigit():
                    ano = val[:4]
                    break
        if not ano and i.get("tmdb"):
            meta_year = str(i.get("release_date") or "")[:4]
            if meta_year.isdigit():
                ano = meta_year
        if ano:
            anos_detectados.append(ano)

    if not anos_detectados:
        _log_debug("[SUPREME][FLOW] listYears: Nenhum ano encontrado mesmo após enriquecimento")
        xbmcgui.Dialog().notification("Sem dados", "Nenhum ano detectado nos filmes", xbmcgui.NOTIFICATION_INFO, 3000)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    anos_unicos = sorted(set(anos_detectados), reverse=True)
    _log_debug(f"[SUPREME][FLOW] listYears: anos detectados = {anos_unicos}")

    # --- Criar submenus de anos ---
    try:
        import json, base64
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(items, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8").rstrip("=")

        for ano in anos_unicos:
            desc = f"Filmes lançados em {ano}"
            _add_dir_via_default_or_manual_supreme(
                str(ano),        # 🔹 Nome correto do submenu
                payload_encoded, # 🔹 Payload Base64
                109,             # 🔹 Modo do listItemsByYear
                "",              # 🔹 Ícone (opcional)
                fanart,          # 🔹 Fanart herdado
                desc             # 🔹 Descrição
            )

        xbmcplugin.endOfDirectory(int(sys.argv[1]))
        _log_debug("[SUPREME][FLOW] listYears finalizado com sucesso ✅")

    except Exception as e_menu:
        _log_error(f"[SUPREME][FLOW] Erro ao montar menu de anos: {e_menu}")
        xbmcgui.Dialog().notification("Erro", "Falha ao criar menu de anos", xbmcgui.NOTIFICATION_ERROR, 4000)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)

def listItemsByYear(payload, fanart, year):
    """
    🎞 SUPREME v2 — Lista filmes filtrados por ano
    Usa cache local + enrich_with_cache e exibe metadados completos.
    Inclui: diretor, roteirista, nota, votos, MPAA, país, estúdio e data de exibição.
    """
    import xbmc, xbmcgui, xbmcplugin, json, sys
    from resources.lib.utils import enrich_with_cache, buildMenuFromJson_supreme

    _log_debug(f"[SUPREME][FLOW] listItemsByYear iniciado — ano={year}")

    try:
        # --- Carrega e normaliza payload ---
        if isinstance(payload, str):
            items = json.loads(payload)
        else:
            items = payload
    except Exception as e_json:
        _log_error(f"[SUPREME][FLOW] Falha ao decodificar payload: {e_json}")
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    # --- Enriquecimento com cache ---
    try:
        items = enrich_with_cache(items)
        _log_debug(f"[SUPREME][CACHE] Itens enriquecidos: {len(items)}")
    except Exception as e_enrich:
        _log_error(f"[SUPREME][FLOW] enrich_with_cache falhou: {e_enrich}")

    # --- Filtro por ano ---
    year_str = str(year)
    filtrados = []
    for i in items:
        date = i.get("release_date") or i.get("date") or str(i.get("year", ""))
        if date and date.startswith(year_str):
            filtrados.append(i)

    if not filtrados:
        xbmcgui.Dialog().notification("Ano", f"Nenhum item encontrado em {year_str}", xbmcgui.NOTIFICATION_INFO, 3000)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        return

    _log_debug(f"[SUPREME][FLOW] {len(filtrados)} filmes filtrados para {year_str}")

    # --- Complementar metadados que possam estar faltando ---
    for item in filtrados:
        try:
            crew = item.get("crew") or item.get("credits", {}).get("crew", [])
            if crew:
                directors = [d["name"] for d in crew if d.get("job") in ("Director", "Directed by")]
                writers = [w["name"] for w in crew if w.get("job") in ("Writer", "Screenplay", "Story", "Author")]
                if directors:
                    item["directors"] = directors
                if writers:
                    item["writers"] = writers

            # 🎬 Classificação indicativa (MPAA)
            release_data = item.get("release_dates", {}).get("results", [])
            mpaa = None
            for r in release_data:
                if r.get("iso_3166_1") in ["US", "BR"]:
                    for rd in r.get("release_dates", []):
                        cert = rd.get("certification")
                        if cert:
                            mpaa = cert
                            break
                    if mpaa:
                        break
            if mpaa:
                item["mpaa"] = mpaa

            # ⭐ Votos e Avaliação
            if not item.get("votes"):
                item["votes"] = item.get("vote_count") or 0
            if not item.get("rating"):
                item["rating"] = item.get("vote_average") or 0

            # 🏭 Estúdio e País
            if not item.get("studio") and item.get("production_companies"):
                item["studio"] = [s["name"] for s in item["production_companies"] if "name" in s]
            if not item.get("country") and item.get("production_countries"):
                item["country"] = [c["name"] for c in item["production_countries"] if "name" in c]

            # 📅 Primeira exibição
            if not item.get("release_date") and item.get("first_air_date"):
                item["release_date"] = item["first_air_date"]

        except Exception as e_meta:
            _log_error(f"[SUPREME][FLOW] Falha ao preencher metadados adicionais: {e_meta}")

    # --- Exibe com todos os metadados no visual SUPREME ---
    try:
        buildMenuFromJson_supreme(filtrados, fanart, f"Filmes de {year_str}")
        _log_debug(f"[SUPREME][FLOW] listItemsByYear exibiu {len(filtrados)} filmes")
    except Exception as e_build:
        _log_error(f"[SUPREME][FLOW] Erro ao construir menu SUPREME: {e_build}")
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)

    _log_debug("[SUPREME][FLOW] listItemsByYear finalizado com sucesso")
    
def listItemsByStudio(studio_name, fanart, mode=None):
    """
    🏢 SUPREME - Lista filmes de um estúdio usando cache local e enrich_with_cache.
    Compatível com payloads concatenados (Base64|studio=Nome do estúdio)
    Exibe metadados completos (diretor, roteirista, MPAA, estúdio, país, etc.)
    """
    import os, json, xbmc, xbmcgui, xbmcplugin, xbmcaddon, sys, base64, urllib.parse
    from xbmcvfs import translatePath as TRANSLATEPATH
    from resources.lib.utils import enrich_with_cache, buildMenuFromJson_supreme, _log_debug, _log_error

    try:
        # 🔹 Detecta se veio payload concatenado
        if "|" in studio_name:
            # Exemplo: "eyJh...fQ|studio=Warner%20Bros.%20Pictures"
            try:
                base_part, studio_part = studio_name.split("|studio=", 1)
                payload_decoded = base64.urlsafe_b64decode(base_part + "==").decode("utf-8")
                studio_name = urllib.parse.unquote_plus(studio_part)
                items = json.loads(payload_decoded)
                _log_debug(f"[SUPREME][FLOW] listItemsByStudio: Payload Base64 detectado ({len(items)} itens) — studio={studio_name}")
            except Exception as e_decode:
                _log_error(f"[SUPREME][FLOW] Falha ao decodificar payload concatenado: {e_decode}")
                items = []
        else:
            # Caso padrão (chamada simples)
            items = []
            _log_debug(f"[SUPREME][FLOW] listItemsByStudio: modo simples, estúdio={studio_name}")

        addon = xbmcaddon.Addon()
        profile = TRANSLATEPATH(addon.getAddonInfo("profile"))
        cache_dir = os.path.join(profile, "cache", "movies")

        # --- Se não há itens, carrega direto do cache local ---
        if not items and os.path.exists(cache_dir):
            for f in os.listdir(cache_dir):
                if f.endswith(".json"):
                    with open(os.path.join(cache_dir, f), "r", encoding="utf-8") as fh:
                        items.append(json.load(fh))

        if not items:
            _log_error("[SUPREME][FLOW] Nenhum item disponível para filtragem")
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        studio_lower = studio_name.lower().strip()
        resultados = []

        # --- 🔹 Filtro por estúdio ---
        for meta in items:
            studios = meta.get("production_companies") or meta.get("studio") or []
            names = []
            if isinstance(studios, list):
                names = [s.get("name", "").lower() for s in studios if isinstance(s, dict)]
            elif isinstance(studios, str):
                names = [studios.lower()]

            if studio_lower in names:
                resultados.append(meta)

        _log_debug(f"[SUPREME][FLOW] Filmes filtrados inicialmente: {len(resultados)}")

        # --- 🔹 Enriquecimento SUPREME ---
        try:
            resultados = enrich_with_cache(resultados)
            _log_debug(f"[SUPREME][CACHE] Itens enriquecidos: {len(resultados)}")
        except Exception as e_enrich:
            _log_error(f"[SUPREME][CACHE] Falha ao enriquecer cache: {e_enrich}")

        if not resultados:
            xbmcgui.Dialog().notification("Estúdio", f"Nenhum filme encontrado para {studio_name}", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        # --- 🔹 Complementar metadados (Diretor, Roteirista, MPAA, País, etc.) ---
        for item in resultados:
            try:
                crew = item.get("crew") or item.get("credits", {}).get("crew", [])
                if crew:
                    directors = [d["name"] for d in crew if d.get("job") in ("Director", "Directed by")]
                    writers = [w["name"] for w in crew if d.get("job") in ("Writer", "Screenplay", "Story", "Author")]
                    if directors:
                        item["directors"] = directors
                    if writers:
                        item["writers"] = writers

                # 🧾 MPAA
                release_data = item.get("release_dates", {}).get("results", [])
                mpaa = None
                for r in release_data:
                    if r.get("iso_3166_1") in ["US", "BR"]:
                        for rd in r.get("release_dates", []):
                            cert = rd.get("certification")
                            if cert:
                                mpaa = cert
                                break
                        if mpaa:
                            break
                if mpaa:
                    item["mpaa"] = mpaa

                # ⭐ Avaliação e votos
                if not item.get("votes"):
                    item["votes"] = item.get("vote_count") or 0
                if not item.get("rating"):
                    item["rating"] = item.get("vote_average") or 0

                # 🏭 Estúdio e País
                if not item.get("studio") and item.get("production_companies"):
                    item["studio"] = [s["name"] for s in item["production_companies"] if "name" in s]
                if not item.get("country") and item.get("production_countries"):
                    item["country"] = [c["name"] for c in item["production_countries"] if "name" in c]

                # 📅 Primeira exibição
                if not item.get("release_date") and item.get("first_air_date"):
                    item["release_date"] = item["first_air_date"]

            except Exception as e_meta:
                _log_error(f"[SUPREME][FLOW] Falha ao complementar metadados: {e_meta}")

        # --- 🔹 Exibir via SUPREME visual ---
        buildMenuFromJson_supreme(resultados, fanart, f"Filmes do estúdio {studio_name}")
        xbmc.log(f"[SUPREME][FLOW] listItemsByStudio exibiu {len(resultados)} filmes do estúdio {studio_name}", xbmc.LOGINFO)

    except Exception as e_main:
        _log_error(f"[SUPREME][FLOW] Erro em listItemsByStudio: {e_main}")
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
        
def listRecentReleases(fanart, mode=None):
    """
    🎞 SUPREME - Lista filmes lançados recentemente (últimos 30 dias).
    Usa cache local e enrich_with_cache, exibindo metadados completos.
    """
    import os, json, datetime, xbmc, xbmcgui, xbmcplugin, xbmcaddon, sys
    from xbmcvfs import translatePath as TRANSLATEPATH
    from resources.lib.utils import enrich_with_cache, buildMenuFromJson_supreme

    xbmc.log("[SUPREME][FLOW] listRecentReleases iniciado", xbmc.LOGINFO)

    try:
        addon = xbmcaddon.Addon()
        profile = TRANSLATEPATH(addon.getAddonInfo("profile"))
        cache_dir = os.path.join(profile, "cache", "movies")

        if not os.path.exists(cache_dir):
            xbmc.log("[SUPREME][CACHE] Nenhum cache encontrado", xbmc.LOGWARNING)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        agora = datetime.datetime.now()
        limite = agora - datetime.timedelta(days=30)
        recentes = []

        # --- Varre caches ---
        for file in os.listdir(cache_dir):
            if not file.endswith(".json"):
                continue
            try:
                file_path = os.path.join(cache_dir, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                release_date = meta.get("release_date") or meta.get("first_air_date")
                if not release_date:
                    continue

                try:
                    data_filme = datetime.datetime.strptime(release_date, "%Y-%m-%d")
                except Exception:
                    xbmc.log(f"[SUPREME][FLOW] Data inválida em {file}: {release_date}", xbmc.LOGDEBUG)
                    continue

                if data_filme < limite:
                    continue  # ignora filmes antigos

                recentes.append(meta)

            except Exception as e_f:
                xbmc.log(f"[SUPREME][CACHE] Erro ao processar {file}: {e_f}", xbmc.LOGERROR)

        if not recentes:
            xbmcgui.Dialog().notification("🎬 Lançamentos", "Nenhum lançamento recente encontrado", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)
            return

        xbmc.log(f"[SUPREME][FLOW] {len(recentes)} filmes recentes encontrados", xbmc.LOGINFO)

        # --- Enriquecimento SUPREME ---
        try:
            recentes = enrich_with_cache(recentes)
            xbmc.log(f"[SUPREME][CACHE] Itens enriquecidos: {len(recentes)}", xbmc.LOGINFO)
        except Exception as e_enrich:
            xbmc.log(f"[SUPREME][FLOW] enrich_with_cache falhou: {e_enrich}", xbmc.LOGERROR)

        # --- Complementa metadados ---
        for item in recentes:
            try:
                crew = item.get("crew") or item.get("credits", {}).get("crew", [])
                if crew:
                    directors = [d["name"] for d in crew if d.get("job") == "Director"]
                    writers = [w["name"] for w in crew if d.get("job") in ("Writer", "Screenplay")]
                    if directors:
                        item["directors"] = directors
                    if writers:
                        item["writers"] = writers

                if not item.get("votes"):
                    item["votes"] = item.get("vote_count") or 0

                if not item.get("release_date") and item.get("first_air_date"):
                    item["release_date"] = item["first_air_date"]
            except Exception as e_meta:
                xbmc.log(f"[SUPREME][FLOW] Falha ao complementar metadados: {e_meta}", xbmc.LOGERROR)

        # --- Exibição com buildMenuFromJson_supreme ---
        buildMenuFromJson_supreme(recentes, fanart, "🎬 Lançamentos Recentes")
        xbmc.log(f"[SUPREME][FLOW] listRecentReleases exibiu {len(recentes)} filmes", xbmc.LOGINFO)

    except Exception as e:
        xbmc.log(f"[SUPREME][FLOW] Erro em listRecentReleases: {e}", xbmc.LOGERROR)
        xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False)