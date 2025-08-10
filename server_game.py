# server_game.py
import socket, threading, json, random, time, math, os, hashlib

HOST = "127.0.0.1"
PORT = 5555

# ---------- Monde ----------
TILE = 40
# Monde infini chunké 64x64
CHUNK_TILES = 64
WORLD_SEED = 1337
random.seed(WORLD_SEED)
# Ancien GRID_* n'est plus utilisé pour la génération
GRID_W, GRID_H = 800, 800  # conservé pour compat mais ignoré par le rendu client v2
WORLD_W, WORLD_H = 10**9, 10**9  # bornes très larges
PLAYER_SIZE = 20
NPC_SIZE = 22
ITEM_SIZE = 16
TICK_HZ = 20  # cadence logique et émission d'état

# Fichiers de données
DATA_DIR = "."
MERCHANTS_PATH = os.path.join(DATA_DIR, "merchants.json")
QUESTS_PATH = os.path.join(DATA_DIR, "quests.json")
MAP_OVERRIDES_PATH = os.path.join(DATA_DIR, "map_overrides.json")

# Sorts (slots 1..4) par classe
SPELLS_BY_CLASS = {
    "Guerrier": {
        1: {"name": "Lancer de hache", "type": "projectile", "speed": 6.0, "dmg": 24, "cost": 6,  "cd": 0.7, "ttl": 2.0},
        2: {"name": "Coup de taille",  "type": "cone",       "radius": 90,  "angle_deg": 70, "dmg": 20, "cost": 10, "cd": 2.0},
        3: {"name": "Cri de guerre",    "type": "aoe",        "radius": 80,  "dmg": 0,  "cost": 8,  "cd": 6.0},
        4: {"name": "Second souffle",    "type": "heal",       "amount": 30, "cost": 0,  "cd": 8.0},
    },
    "Mage": {
        1: {"name": "Boule de feu",      "type": "projectile", "speed": 6.8, "dmg": 26, "cost": 12, "cd": 0.7, "ttl": 2.2},
        2: {"name": "Cône de givre",     "type": "cone",       "radius": 120, "angle_deg": 60, "dmg": 18, "cost": 16, "cd": 2.0},
        3: {"name": "Nova arcanique",    "type": "aoe",        "radius": 90,  "dmg": 22, "cost": 20, "cd": 4.0},
        4: {"name": "Soin mineur",       "type": "heal",       "amount": 35, "cost": 18, "cd": 3.0},
    },
    "Voleur": {
        1: {"name": "Dague lancée",      "type": "projectile", "speed": 7.2, "dmg": 22, "cost": 5,  "cd": 0.5, "ttl": 1.8},
        2: {"name": "Entaille",          "type": "cone",       "radius": 80,  "angle_deg": 70, "dmg": 18, "cost": 8,  "cd": 1.6},
        3: {"name": "Poudre aveuglante", "type": "aoe",        "radius": 70,  "dmg": 0,  "cost": 10, "cd": 5.0},
        4: {"name": "Soin rapide",       "type": "heal",       "amount": 25, "cost": 10, "cd": 6.0},
    },
}

# ---------- État ----------
lock = threading.RLock()
active_usernames = set()  # anti double-login même compte
clients = {}         # pid -> socket
players = {}         # pid -> {...}
inventories = {}     # pid -> [items]
cooldowns = {}       # pid -> {"spells": {slot: ready_ts}}
next_id = 1

# données externes
merchants_data = {}
quests_data = {}
map_overrides = {}           # (tx,ty) -> tile
_overrides_by_chunk = {}     # (cx,cy) -> set((tx,ty)) pour accélérer l'application

# Comptes / persistance
ACCOUNTS_PATH = "accounts.json"
accounts = {"users": {}}  # {username: {"password": hash, "characters": {cid: {...}}, "next_char_id": int}}
pid_identity = {}  # pid -> {"username": str, "char_id": str}
_dirty_users = set()

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(("py_mmo_salt::" + (pw or "")).encode("utf-8")).hexdigest()

def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_PATH):
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "users" in data:
                    accounts = data
    except Exception:
        accounts = {"users": {}}

def save_accounts():
    tmp = ACCOUNTS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ACCOUNTS_PATH)
    except Exception:
        pass

def mark_dirty(username: str):
    if username:
        _dirty_users.add(username)

def saver_loop():
    while True:
        time.sleep(5.0)
        to_save = None
        with lock:
            if _dirty_users:
                to_save = list(_dirty_users)
                _dirty_users.clear()
        if to_save is not None:
            with lock:
                save_accounts()

# Chargement/Enregistrement de données JSON

def _ensure_default_files():
    # marchands par défaut
    if not os.path.exists(MERCHANTS_PATH):
        default_merchants = {
            "weaponsmith": {
                "name": "Marchand d'armes",
                "stock": [
                    {"name":"Épée rouillée","type":"weapon","power":5, "price": 20},
                    {"name":"Hache légère","type":"weapon","power":8, "price": 45},
                    {"name":"Arc court","type":"weapon","power":7, "price": 38}
                ]
            },
            "alchemist": {
                "name": "Alchimiste",
                "stock": [
                    {"name":"Petite potion","type":"potion","power":30, "price": 10},
                    {"name":"Potion de mana","type":"scroll","power":25, "price": 14},
                    {"name":"Tonique fortifiant","type":"potion","power":50, "price": 25}
                ]
            }
        }
        try:
            with open(MERCHANTS_PATH, "w", encoding="utf-8") as f:
                json.dump(default_merchants, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    # quêtes par défaut
    if not os.path.exists(QUESTS_PATH):
        default_quests = {
            "q_slimes_5": {"title": "Nettoyage gluant", "desc": "Éliminer 5 Slimes près du village.", "requirements": {"kill": {"Slime": 5}}, "rewards": {"xp": 60, "gold": 20}},
            "q_gobs_3": {"title": "Tapage gobelin", "desc": "Tuer 3 Gobelins.", "requirements": {"kill": {"Gobelin": 3}}, "rewards": {"xp": 80, "gold": 25}}
        }
        try:
            with open(QUESTS_PATH, "w", encoding="utf-8") as f:
                json.dump(default_quests, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    # overrides par défaut
    if not os.path.exists(MAP_OVERRIDES_PATH):
        try:
            with open(MAP_OVERRIDES_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except Exception:
            pass

def load_merchants():
    global merchants_data
    try:
        with open(MERCHANTS_PATH, "r", encoding="utf-8") as f:
            merchants_data = json.load(f)
    except Exception:
        merchants_data = {}


def load_quests():
    global quests_data
    try:
        with open(QUESTS_PATH, "r", encoding="utf-8") as f:
            quests_data = json.load(f)
    except Exception:
        quests_data = {}


def load_map_overrides():
    global map_overrides, _overrides_by_chunk
    try:
        with open(MAP_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            # stocker clés en tuples d'int
            map_overrides = { (int(k.split(",")[0]), int(k.split(",")[1])): int(v) for k,v in raw.items() }
    except Exception:
        map_overrides = {}
    _rebuild_overrides_index()


def save_map_overrides():
    try:
        raw = { f"{tx},{ty}": int(t) for (tx,ty), t in map_overrides.items() }
        tmp = MAP_OVERRIDES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0)
        os.replace(tmp, MAP_OVERRIDES_PATH)
    except Exception:
        pass


def _rebuild_overrides_index():
    global _overrides_by_chunk
    _overrides_by_chunk = {}
    for (tx,ty), t in map_overrides.items():
        cx = math.floor(tx / CHUNK_TILES)
        cy = math.floor(ty / CHUNK_TILES)
        _overrides_by_chunk.setdefault((cx,cy), set()).add((tx,ty))

# ---------- Monde procédural chunké & collisions ----------
# types: 0 herbe, 1 montagne/mur (bloquant), 2 eau (bloquant), 3 sable, 4 route/pont
def is_blocking_tile(t):
    return t in (1, 2)

chunk_cache = {}  # (cx,cy) -> 64x64 tiles

def _rand_for(cx: int, cy: int, salt: int = 0):
    seed = (cx * 73856093) ^ (cy * 19349663) ^ (WORLD_SEED * 83492791) ^ (salt * 2654435761)
    return random.Random(seed & 0xFFFFFFFF)

def generate_chunk(cx: int, cy: int):
    r = _rand_for(cx, cy)
    tiles = [[0 for _ in range(CHUNK_TILES)] for _ in range(CHUNK_TILES)]
    base_x = cx * CHUNK_TILES
    base_y = cy * CHUNK_TILES
    river_x = int(20 * math.sin((base_y) * 0.01))
    river_y = int(20 * math.cos((base_x) * 0.01))
    for ty in range(CHUNK_TILES):
        for tx in range(CHUNK_TILES):
            gx = base_x + tx
            gy = base_y + ty
            v = (math.sin(gx * 0.04) + math.cos(gy * 0.04)) * 0.5
            n = (r.random() + 0.5 * v)
            t = 0
            if abs((gx - river_x) % 64 - 32) < 2 or abs((gy - river_y) % 96 - 48) < 2:
                t = 2  # eau
            elif abs((gx - river_x) % 64 - 32) < 3 or abs((gy - river_y) % 96 - 48) < 3:
                t = 3  # sable
            elif n > 1.25:
                t = 1  # montagne/mur
            tiles[ty][tx] = t
    # routes/bridges proche du centre monde (look pont + route comme sur l'image)
    if abs(cx) <= 1:
        mid = CHUNK_TILES//2
        for x in range(6, CHUNK_TILES-6):
            tiles[mid][x] = 4
            tiles[mid-1][x] = 4
    if abs(cy) <= 1:
        mid = CHUNK_TILES//2
        for y in range(6, CHUNK_TILES-6):
            tiles[y][mid] = 4
            tiles[y][mid-1] = 4
    # Ajouter parfois un village: place en sable + quelques maisons (murs)
    if r.random() < 0.07:
        vx = r.randint(8, CHUNK_TILES-16)
        vy = r.randint(8, CHUNK_TILES-16)
        vw = r.randint(8, 14)
        vh = r.randint(8, 14)
        for y in range(vy, vy+vh):
            for x in range(vx, vx+vw):
                if 0 <= y < CHUNK_TILES and 0 <= x < CHUNK_TILES:
                    tiles[y][x] = 3
        # 1-2 maisons
        for _ in range(r.randint(1,2)):
            hx = vx + r.randint(1, max(1, vw-6))
            hy = vy + r.randint(1, max(1, vh-6))
            hw = r.randint(4, min(7, vw-2))
            hh = r.randint(4, min(7, vh-2))
            for x in range(hx, hx+hw):
                if 0 <= hy < CHUNK_TILES and 0 <= x < CHUNK_TILES:
                    tiles[hy][x] = 1
                if 0 <= hy+hh-1 < CHUNK_TILES and 0 <= x < CHUNK_TILES:
                    tiles[hy+hh-1][x] = 1
            for y in range(hy, hy+hh):
                if 0 <= y < CHUNK_TILES and 0 <= hx < CHUNK_TILES:
                    tiles[y][hx] = 1
                if 0 <= y < CHUNK_TILES and 0 <= hx+hw-1 < CHUNK_TILES:
                    tiles[y][hx+hw-1] = 1
        # marquer la présence d'un PNJ au centre de la place (utilisé plus tard lors du chargement proximité)
        tiles[vy+vh//2][vx+vw//2] = tiles[vy+vh//2][vx+vw//2]  # no-op: juste pour garder une trace de village
    return tiles

def get_chunk(cx: int, cy: int):
    key = (cx, cy)
    ch = chunk_cache.get(key)
    if ch is None:
        ch = generate_chunk(cx, cy)
        chunk_cache[key] = ch
    return ch

def get_tile_at(tx: int, ty: int) -> int:
    cx = math.floor(tx / CHUNK_TILES)
    cy = math.floor(ty / CHUNK_TILES)
    lx = int(tx - cx * CHUNK_TILES)
    ly = int(ty - cy * CHUNK_TILES)
    tiles = get_chunk(cx, cy)
    if 0 <= ly < CHUNK_TILES and 0 <= lx < CHUNK_TILES:
        # override ponctuel
        ov = map_overrides.get((tx,ty))
        if ov is not None:
            return ov
        return tiles[ly][lx]
    return 0


def get_chunk_with_overrides(cx: int, cy: int):
    tiles = [row[:] for row in get_chunk(cx, cy)]
    for (tx,ty) in _overrides_by_chunk.get((cx,cy), set()):
        lx = int(tx - cx*CHUNK_TILES)
        ly = int(ty - cy*CHUNK_TILES)
        if 0 <= ly < CHUNK_TILES and 0 <= lx < CHUNK_TILES:
            tiles[ly][lx] = map_overrides.get((tx,ty), tiles[ly][lx])
    return tiles

# PNJ (mobs)
npcs = {}           # nid -> {...}
next_npc_id = 1

# thématisation & niveaux

def compute_world_level_for_pos(x: int, y: int) -> int:
    d = math.hypot(x, y)
    return max(1, int(d // (TILE*30)) + 1)  # +1 niveau tous les ~1200 px


def make_mob_template_for_level(level: int, theme: str = None):
    base_templates = [
        {"name": "Rat géant", "hp": 28, "speed": 1.6, "dmg": 6},
        {"name": "Gobelin",   "hp": 42, "speed": 1.9, "dmg": 7},
        {"name": "Slime",     "hp": 36, "speed": 1.3, "dmg": 5},
        {"name": "Loup",      "hp": 50, "speed": 2.3, "dmg": 8},
        {"name": "Orc",       "hp": 70, "speed": 1.8, "dmg": 10},
        {"name": "Ours",      "hp": 90, "speed": 1.4, "dmg": 12},
    ]
    if theme == "slime": base_templates = [{"name":"Slime", "hp":36, "speed":1.3, "dmg":5}]
    if theme == "gob": base_templates = [{"name":"Gobelin", "hp":42, "speed":1.9, "dmg":7}]
    if theme == "wolf": base_templates = [{"name":"Loup", "hp":50, "speed":2.3, "dmg":8}]
    if theme == "orc": base_templates = [{"name":"Orc", "hp":70, "speed":1.8, "dmg":10}]
    if theme == "bear": base_templates = [{"name":"Ours", "hp":90, "speed":1.4, "dmg":12}]
    t = random.choice(base_templates)
    scale = 1.0 + max(0, level-1) * 0.18
    hp = int(t["hp"] * scale)
    dmg = int(t["dmg"] * (0.7 + max(0, level-1)*0.12))
    return {"name": t["name"], "hp": hp, "max_hp": hp, "hostile": True, "speed": t["speed"], "dmg": dmg, "atk_until": 0, "level": int(level)}


def spawn_mob_at(x: int, y: int, level: int = None, theme: str = None):
    global next_npc_id
    if level is None:
        level = compute_world_level_for_pos(x, y)
    t = make_mob_template_for_level(level, theme)
    nid = next_npc_id; next_npc_id += 1
    npcs[nid] = {"x": x, "y": y, "dx": 0, "dy": 0, "last_hit_by": None, **t}
    return nid


def spawn_boss_at(x: int, y: int, level: int, big: bool = False, theme: str = None):
    global next_npc_id
    base = make_mob_template_for_level(level, theme)
    name = ("Seigneur " if big else "Champion ") + base["name"]
    hp = int(base["max_hp"] * (4.0 if big else 2.2))
    dmg = int(base["dmg"] * (2.0 if big else 1.4))
    nid = next_npc_id; next_npc_id += 1
    npcs[nid] = {"x": x, "y": y, "dx":0, "dy":0, "name": name, "hp": hp, "max_hp": hp, "hostile": True, "speed": base["speed"], "dmg": dmg, "atk_until": 0, "level": int(level), "is_boss": True, "boss_big": bool(big), "boss_next": now()+3.0}
    return nid


def spawn_villager_npc(x: int, y: int, name: str = None):
    global next_npc_id
    nid = next_npc_id; next_npc_id += 1
    npcs[nid] = {"x": x, "y": y, "dx": 0, "dy": 0, "name": name or "Villageois", "hp": 1000000, "max_hp": 1000000, "hostile": False, "speed": 0.0, "dmg": 0, "level": 1}
    return nid


def spawn_merchant_npc(x: int, y: int, merchant_id: str, name: str = None):
    nid = spawn_villager_npc(x, y, name or merchants_data.get(merchant_id, {}).get("name","Marchand"))
    npcs[nid]["merchant_id"] = merchant_id
    return nid


def spawn_quest_giver_npc(x: int, y: int, quest_ids: list, name: str = "Quêteur"):
    nid = spawn_villager_npc(x, y, name)
    npcs[nid]["quest_ids"] = list(quest_ids)
    return nid

# Items au sol
items = {}          # iid -> {"x","y","name","type","power":int, ...}
next_item_id = 1

# tour: coordonnées de base des étages (séparées du monde)
TOWER_BASE_TX = 2000
TOWER_BASE_TY = 2000
TOWER_FLOOR_W = 32
TOWER_FLOOR_H = 24

# Projectiles actifs (sort 1)
projs = {}          # proj_id -> {"x","y","vx","vy","dmg","owner","expire_at"}
next_proj_id = 1

# ---------- Utils ----------
def aabb_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return (ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by)

def is_colliding_rect(cx, cy, w, h):
    x0 = int((cx - w/2) // TILE)
    y0 = int((cy - h/2) // TILE)
    x1 = int((cx + w/2) // TILE)
    y1 = int((cy + h/2) // TILE)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            t = get_tile_at(tx, ty)
            # bloquant: uniquement montagnes/murs (1) et eau (2)
            # sable (3) et herbe (0) sont traversables
            if is_blocking_tile(t):
                return True
    return False

def move_with_collisions(cx, cy, dx, dy, size):
    nx, ny = cx + dx, cy
    if is_colliding_rect(nx, ny, size, size):
        nx = cx
    ny = ny + dy
    if is_colliding_rect(nx, ny, size, size):
        ny = cy
    return nx, ny

def random_free_pos(center_x: int = 0, center_y: int = 0, radius_tiles: int = 64):
    for _ in range(200):
        tx = int(center_x // TILE) + random.randint(-radius_tiles, radius_tiles)
        ty = int(center_y // TILE) + random.randint(-radius_tiles, radius_tiles)
        x = tx * TILE + TILE // 2
        y = ty * TILE + TILE // 2
        if not is_colliding_rect(x, y, PLAYER_SIZE, PLAYER_SIZE):
            return x, y
    return center_x or TILE * 4, center_y or TILE * 4

def dist(x1,y1,x2,y2): return math.hypot(x1-x2, y1-y2)
def now(): return time.time()

def _safe_send(conn, obj):
    try:
        conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False
    except Exception:
        return False

def broadcast_obj(obj):
    with lock:
        conns = list(clients.items())
    dead = []
    for pid, conn in conns:
        if not _safe_send(conn, obj):
            dead.append(pid)
    if dead:
        with lock:
            for pid in dead:
                try: clients[pid].close()
                except: pass
                clients.pop(pid, None)
                players.pop(pid, None)
                inventories.pop(pid, None)
                cooldowns.pop(pid, None)

_last_broadcast = 0.0
def broadcast_state(rate_hz=TICK_HZ):
    global _last_broadcast
    t = now()
    if t - _last_broadcast < (1.0 / rate_hz):
        return
    _last_broadcast = t
    with lock:
        state = {
            "type":"state",
            "players": dict(players),
            "npcs": dict(npcs),
            "items": dict(items),
            "projs": {str(k):v for k,v in projs.items()},
        }
    broadcast_obj(state)

def send_to(pid, obj):
    with lock:
        conn = clients.get(pid)
    if conn: _safe_send(conn, obj)

# ---------- Mobs / Loot ----------
def make_mob_template():
    templates = [
        {"name": "Rat géant", "hp": 28, "speed": 1.6, "dmg": 6},
        {"name": "Gobelin",   "hp": 42, "speed": 1.9, "dmg": 7},
        {"name": "Slime",     "hp": 36, "speed": 1.3, "dmg": 5},
        {"name": "Loup",      "hp": 50, "speed": 2.3, "dmg": 8},
    ]
    t = random.choice(templates)
    return {"name": t["name"], "hp": t["hp"], "max_hp": t["hp"], "hostile": True, "speed": t["speed"], "dmg": t["dmg"], "atk_until": 0}

def spawn_mob():
    global next_npc_id
    x, y = random_free_pos()
    t = make_mob_template()
    nid = next_npc_id; next_npc_id += 1
    npcs[nid] = {"x": x, "y": y, "dx": 0, "dy": 0, "last_hit_by": None, **t}
    return nid

def drop_loot_at(x, y):
    global next_item_id
    table = [
        {"name":"Petite potion","type":"potion","power":30, "p":0.5},
        {"name":"Parchemin mineur","type":"scroll","power":20, "p":0.3},
        {"name":"Dague ébréchée","type":"weapon","power":6, "p":0.25},
        {"name":"Pièce d'or","type":"gold","power":random.randint(1,5), "p":0.8},
    ]
    for entry in table:
        if random.random() < entry["p"]:
            iid = next_item_id; next_item_id += 1
            items[iid] = {"x": x, "y": y, "name": entry["name"], "type": entry["type"], "power": entry["power"]}

# ---------- Joueurs ----------
def base_player(name, x, y):
    return {
        "name": name, "x": x, "y": y,
        "hp": 100, "max_hp": 100,
        "mp": 60,  "max_mp": 60,
        "dead": False, "respawn_at": 0.0,
        "level": 1, "xp": 0, "next_xp": 100,
        "gold": 0,
        "weapon_bonus": 0, "weapon_name": None,
        "class": "Aventurier", "race": "Humain",
        "stats": {"str": 5, "int": 5, "agi": 5, "sta": 5},
        "stat_points": 0,
        "equipment": {
            "head": None, "neck": None, "chest": None, "legs": None, "boots": None,
            "ring1": None, "ring2": None, "weapon": None, "offhand": None,
        },
    }

def class_base_stats(cls: str):
    cls = (cls or "").lower()
    if cls == "guerrier":
        return {"max_hp": 140, "max_mp": 40}
    if cls == "mage":
        return {"max_hp": 90, "max_mp": 110}
    if cls == "voleur":
        return {"max_hp": 110, "max_mp": 70}
    return {"max_hp": 100, "max_mp": 60}

def make_player_from_character(ch: dict, x: int, y: int):
    p = base_player(ch.get("name","Héros"), x, y)
    p["level"] = int(ch.get("level", 1))
    p["xp"] = int(ch.get("xp", 0))
    p["next_xp"] = int(ch.get("next_xp", 100))
    p["gold"] = int(ch.get("gold", 0))
    p["weapon_bonus"] = int(ch.get("weapon_bonus", 0))
    p["weapon_name"] = ch.get("weapon_name")
    # stats par classe
    base = class_base_stats(ch.get("class"))
    p["max_hp"] = int(ch.get("max_hp", base["max_hp"]))
    p["max_mp"] = int(ch.get("max_mp", base["max_mp"]))
    p["hp"] = int(ch.get("hp", p["max_hp"]))
    p["mp"] = int(ch.get("mp", p["max_mp"]))
    p["class"] = ch.get("class", "Aventurier")
    p["race"] = ch.get("race", "Humain")
    p["stats"] = ch.get("stats", p["stats"]) or p["stats"]
    p["stat_points"] = int(ch.get("stat_points", 0))
    p["equipment"] = ch.get("equipment", p.get("equipment")) or p.get("equipment")
    apply_equipment_effects(p)
    return p

def apply_equipment_effects(p: dict):
    eq = p.get("equipment") or {}
    # reset and compute
    p["weapon_bonus"] = 0
    p["weapon_name"] = None
    bonus = {"str":0,"int":0,"agi":0,"sta":0}
    for slot, obj in (eq or {}).items():
        if not obj or not isinstance(obj, dict):
            continue
        typ = obj.get("type"); power = int(obj.get("power",0))
        if slot == "weapon" and typ == "weapon":
            p["weapon_bonus"] = max(p.get("weapon_bonus",0), power)
            p["weapon_name"] = obj.get("name")
            # petite orientation de classe
            cls = (p.get("class") or "").lower()
            if cls == "guerrier": bonus["str"] += power
            elif cls == "mage": bonus["int"] += power
            elif cls == "voleur": bonus["agi"] += power
        if slot in ("head","chest","legs","boots"): bonus["sta"] += power//2
        if slot in ("ring1","ring2"): bonus["str"] += power//3; bonus["int"] += power//3; bonus["agi"] += power//3
        if slot == "offhand" and typ in ("shield","offhand"): bonus["sta"] += power//2
    base_stats = p.get("stats", {"str":5,"int":5,"agi":5,"sta":5})
    p["_gear_bonus_stats"] = {k: base_stats.get(k,0) + bonus.get(k,0) for k in ("str","int","agi","sta")}

def persist_player_to_character(username: str, char_id: str, p: dict, inv: list):
    with lock:
        user = accounts["users"].get(username)
        if not user: return
        ch = user.get("characters", {}).get(str(char_id))
        if not ch: return
        ch.update({
            "name": p.get("name"),
            "level": p.get("level", 1),
            "xp": p.get("xp", 0),
            "next_xp": p.get("next_xp", 100),
            "gold": p.get("gold", 0),
            "weapon_bonus": p.get("weapon_bonus", 0),
            "weapon_name": p.get("weapon_name"),
            "hp": p.get("hp", ch.get("hp", 0)),
            "max_hp": p.get("max_hp", ch.get("max_hp", 100)),
            "mp": p.get("mp", ch.get("mp", 0)),
            "max_mp": p.get("max_mp", ch.get("max_mp", 60)),
            "x": p.get("x", ch.get("x")),
            "y": p.get("y", ch.get("y")),
            "inventory": inv,
            "class": p.get("class", ch.get("class", "Aventurier")),
            "race": p.get("race", ch.get("race", "Humain")),
            "stats": p.get("stats", ch.get("stats", {"str":5,"int":5,"agi":5,"sta":5})),
            "stat_points": p.get("stat_points", ch.get("stat_points", 0)),
            "equipment": p.get("equipment", ch.get("equipment")),
        })
        mark_dirty(username)

def grant_xp_gold(p, xp=0, gold=0):
    p["xp"] += xp; p["gold"] += gold
    leveled = False
    while p["xp"] >= p["next_xp"]:
        p["xp"] -= p["next_xp"]
        p["level"] += 1
        p["next_xp"] = int(p["next_xp"] * 1.5)
        p["max_hp"] += 10; p["max_mp"] += 5
        p["hp"] = p["max_hp"]; p["mp"] = p["max_mp"]
        leveled = True
        p["stat_points"] = p.get("stat_points", 0) + 5
    return leveled

# ---------- Spells ----------
def can_cast(pid, slot):
    p = players.get(pid)
    if not p or p["dead"]: return False, "dead"
    sp = SPELLS_BY_CLASS.get(p.get("class","Mage"), {}).get(slot)
    if not sp: return False, "noskill"
    if p["mp"] < sp["cost"]: return False, "nomana"
    ready_at = cooldowns.get(pid, {}).get("spells", {}).get(slot, 0.0)
    if now() < ready_at: return False, "cooldown"
    return True, ""

def spend_cast(pid, slot):
    p = players[pid]; sp = SPELLS_BY_CLASS[p.get("class","Mage")][slot]
    p["mp"] = max(0, p["mp"] - sp["cost"])
    if pid not in cooldowns: cooldowns[pid] = {"spells": {}}
    cooldowns[pid]["spells"][slot] = now() + sp["cd"]

def spawn_projectile(pid, px, py, tx, ty, sp):
    global next_proj_id
    ang = math.atan2(ty - py, tx - px)
    vx = math.cos(ang) * sp["speed"]
    vy = math.sin(ang) * sp["speed"]
    proj_id = next_proj_id; next_proj_id += 1
    projs[proj_id] = {"x": px, "y": py, "vx": vx, "vy": vy, "dmg": sp["dmg"], "owner": pid, "expire_at": now()+sp["ttl"]}

def apply_cone(pid, px, py, tx, ty, sp):
    ang0 = math.atan2(ty - py, tx - px)
    radius = sp["radius"]; half = math.radians(sp["angle_deg"]) / 2
    for nid, n in list(npcs.items()):
        d = dist(px, py, n["x"], n["y"])
        if d <= radius:
            ang = math.atan2(n["y"] - py, n["x"] - px)
            diff = math.atan2(math.sin(ang-ang0), math.cos(ang-ang0))
            if abs(diff) <= half:
                caster = players.get(pid, {})
                bonus = 0
                if caster.get("class") == "Guerrier": bonus = int(caster.get("stats",{}).get("str",0)*0.5)
                elif caster.get("class") == "Mage": bonus = int(caster.get("stats",{}).get("int",0)*0.4)
                elif caster.get("class") == "Voleur": bonus = int(caster.get("stats",{}).get("agi",0)*0.4)
                n["hp"] -= (sp["dmg"] + bonus); n["last_hit_by"] = pid
                if n["hp"] <= 0:
                    owner = players.get(pid)
                    if owner:
                        leveled = grant_xp_gold(owner, xp=random.randint(12,22), gold=random.randint(1,3))
                        ident = pid_identity.get(pid)
                        if ident: mark_dirty(ident["username"])
                    drop_loot_at(n["x"], n["y"]); del npcs[nid]

def apply_aoe(pid, px, py, sp):
    r = sp["radius"]
    for nid, n in list(npcs.items()):
        if dist(px,py,n["x"],n["y"]) <= r:
            caster = players.get(pid, {})
            bonus = 0
            if caster.get("class") == "Guerrier": bonus = int(caster.get("stats",{}).get("str",0)*0.4)
            elif caster.get("class") == "Mage": bonus = int(caster.get("stats",{}).get("int",0)*0.6)
            elif caster.get("class") == "Voleur": bonus = int(caster.get("stats",{}).get("agi",0)*0.3)
            n["hp"] -= (sp.get("dmg",0) + bonus); n["last_hit_by"] = pid
            if n["hp"] <= 0:
                owner = players.get(pid)
                if owner:
                    leveled = grant_xp_gold(owner, xp=random.randint(12,22), gold=random.randint(1,3))
                    ident = pid_identity.get(pid)
                    if ident: mark_dirty(ident["username"])
                drop_loot_at(n["x"], n["y"]); del npcs[nid]

# ---------- Client handler ----------
def handle_client(conn, addr):
    global next_id, next_item_id
    f = conn.makefile("r")

    authed_user = None  # username
    pid = None          # world session pid
    entered_world = False
    chosen_char_id = None

    def send_conn(obj):
        _safe_send(conn, obj)

    # Boucle de lecture (auth puis jeu)
    try:
        while True:
                try:
                    line = f.readline()
                except Exception:
                    break
                if not line:
                    break
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                t = data.get("type")

                # Phase 1: Authentification
                if not authed_user:
                    if t == "login":
                        username = str(data.get("username",""))
                        password = str(data.get("password",""))
                        with lock:
                            user = accounts["users"].get(username)
                        if not user or user.get("password") != _hash_pw(password):
                            send_conn({"type":"login_error","msg":"Identifiants invalides."})
                        else:
                            with lock:
                                if username in active_usernames:
                                    send_conn({"type":"login_error","msg":"Compte déjà connecté."})
                                    continue
                                active_usernames.add(username)
                            authed_user = username
                            chars = user.get("characters", {})
                            char_list = [{"id": cid, "name": ch.get("name"), "class": ch.get("class","?"), "level": ch.get("level",1)} for cid, ch in chars.items()]
                            send_conn({"type":"login_ok","characters": char_list})
                    elif t == "register":
                        username = str(data.get("username",""))
                        password = str(data.get("password",""))
                        if not username or not password:
                            send_conn({"type":"login_error","msg":"Utilisateur et mot de passe requis."})
                        else:
                            with lock:
                                if username in accounts["users"]:
                                    user = None
                                else:
                                    accounts["users"][username] = {"password": _hash_pw(password), "characters": {}, "next_char_id": 1}
                                    save_accounts()
                                    user = accounts["users"][username]
                            if not user:
                                send_conn({"type":"login_error","msg":"Utilisateur déjà existant."})
                            else:
                                authed_user = username
                                send_conn({"type":"login_ok","characters": []})
                    else:
                        send_conn({"type":"login_error","msg":"Veuillez vous authentifier."})
                    continue

                # Phase 2: Pré-monde (sélection/création)
                if not entered_world:
                    if t == "request_characters":
                        with lock:
                            user = accounts["users"].get(authed_user, {"characters":{}})
                            chars = user.get("characters", {})
                        char_list = [{"id": cid, "name": ch.get("name"), "class": ch.get("class","?"), "level": ch.get("level",1)} for cid, ch in chars.items()]
                        send_conn({"type":"characters","characters": char_list})
                        continue
                    elif t == "create_character":
                        name = str(data.get("name","Héros")).strip() or "Héros"
                        cls = str(data.get("class","Aventurier"))
                        race = str(data.get("race","Humain"))
                        with lock:
                            user = accounts["users"].get(authed_user)
                            if not user:
                                send_conn({"type":"create_error","msg":"Session invalide."})
                                continue
                            cid = str(user.get("next_char_id", 1))
                            user["next_char_id"] = int(cid) + 1
                            ch = {
                                "id": cid,
                                "name": name,
                                "class": cls,
                                "race": race,
                                "level": 1, "xp": 0, "next_xp": 100,
                                "gold": 0,
                                "weapon_bonus": 0, "weapon_name": None,
                                "hp": class_base_stats(cls)["max_hp"],
                                "max_hp": class_base_stats(cls)["max_hp"],
                                "mp": class_base_stats(cls)["max_mp"],
                                "max_mp": class_base_stats(cls)["max_mp"],
                                "x": None, "y": None,
                                "stats": {"str": 5, "int": 5, "agi": 5, "sta": 5},
                                "stat_points": 0,
                                "inventory": [
                                    {"id": 100000 + int(cid)*10 + 1, "name": "Petite potion", "type": "potion", "power": 30},
                                ],
                            }
                            if "characters" not in user: user["characters"] = {}
                            user["characters"][cid] = ch
                            mark_dirty(authed_user)
                            save_accounts()
                            chars = user["characters"]
                        char_list = [{"id": k, "name": v.get("name"), "class": v.get("class","?"), "level": v.get("level",1)} for k,v in chars.items()]
                        send_conn({"type":"characters","characters": char_list})
                        continue
                    elif t == "enter_world":
                        chosen_char_id = str(data.get("char_id"))
                        with lock:
                            user = accounts["users"].get(authed_user)
                            ch = (user or {}).get("characters", {}).get(chosen_char_id)
                        if not ch:
                            send_conn({"type":"enter_error","msg":"Personnage introuvable."})
                            continue
                        with lock:
                            pid = next_id; next_id += 1
                            clients[pid] = conn
                            # Position
                            if ch.get("x") is None or ch.get("y") is None:
                                x, y = random_free_pos()
                            else:
                                x, y = int(ch.get("x")), int(ch.get("y"))
                            players[pid] = make_player_from_character(ch, x, y)
                            inventories[pid] = list(ch.get("inventory", []))
                            cooldowns[pid] = {"spells": {}}
                            pid_identity[pid] = {"username": authed_user, "char_id": chosen_char_id}
                            # Sécurité: monter next_item_id pour éviter collisions avec inventaire persistant
                            try:
                                max_inv_id = max((int(v.get("id",0)) for v in inventories[pid]), default=0)
                                if max_inv_id >= next_item_id:
                                    next_item_id = max_inv_id + 1
                            except Exception:
                                pass
                        # envoyer les sorts de la classe du joueur uniquement
                        _cls = players[pid].get("class","Mage")
                        class_spells = SPELLS_BY_CLASS.get(_cls, {})
                        send_to(pid, {"type":"welcome","your_id":pid,"tile":TILE,"grid_w":GRID_W,"grid_h":GRID_H,"map":[],
                                      "inventory":inventories[pid],"you":players[pid],"spells":class_spells})
                        broadcast_state()
                        broadcast_obj({"type":"chat","from":"SYSTEM","msg":f"{players[pid]['name']} a rejoint la partie."})
                        # deux mobs à proximité pour tests
                        px, py = players[pid]["x"], players[pid]["y"]
                        for _ in range(2):
                            mx, my = random_free_pos(px, py, 8)
                            spawn_mob_at(mx, my)
                        entered_world = True
                        continue
                    else:
                        send_conn({"type":"error","msg":"Action non valide avant l'entrée en jeu."})
                        continue

                # Phase 3: En jeu
                if t == "move":
                    dx = int(data.get("dx",0)); dy = int(data.get("dy",0))
                    with lock:
                        p = players.get(pid)
                        if p and not p["dead"]:
                            p["x"], p["y"] = move_with_collisions(p["x"], p["y"], dx, dy, PLAYER_SIZE)

                elif t == "pickup":
                    to_send_inv = False
                    sys_msg = None
                    with lock:
                        p = players.get(pid)
                        if p and not p["dead"]:
                            px, py = p["x"], p["y"]
                            target_iid = None; best_d2 = 999999
                            for iid, it in items.items():
                                d2 = (it["x"]-px)**2 + (it["y"]-py)**2
                                if d2 < best_d2 and d2 <= (40**2):
                                    best_d2 = d2; target_iid = iid
                            if target_iid is not None:
                                it = items.pop(target_iid)
                                if it["type"] == "gold":
                                    p["gold"] += int(it.get("power",1))
                                    sys_msg = {"type":"chat","from":"SYSTEM","msg":f"{p['name']} +{it.get('power',1)} or"}
                                    ident = pid_identity.get(pid)
                                    if ident: mark_dirty(ident["username"])
                                elif it["type"] == "stairs":
                                    # passer à l'étage indiqué
                                    next_floor = int(it.get("floor", 1))
                                    enter_tower_floor(pid, next_floor)
                                elif it["type"] == "portal":
                                    # compat existante
                                    pass
                                else:
                                    inv_id = 1000000 + target_iid
                                    inventories[pid].append({"id": inv_id, "name": it["name"], "type": it["type"], "power": it.get("power",0)})
                                    to_send_inv = True
                                    ident = pid_identity.get(pid)
                                    if ident: mark_dirty(ident["username"])
                    if to_send_inv:
                        send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})
                    if sys_msg:
                        broadcast_obj(sys_msg)

                elif t == "use_item":
                    iid = data.get("id")
                    with lock:
                        inv = inventories.get(pid, [])
                        idx = next((i for i,v in enumerate(inv) if str(v["id"]) == str(iid)), None)
                        if idx is not None:
                            obj = inv.pop(idx)
                            p = players.get(pid)
                            if p:
                                typ = obj.get("type"); power = int(obj.get("power",0))
                                if typ == "potion":   p["hp"] = min(p["max_hp"], p["hp"] + (power or 30))
                                elif typ == "scroll": p["mp"] = min(p["max_mp"], p["mp"] + (power or 20))
                                elif typ == "weapon":
                                    # si utilisé via inventaire, l'équiper directement dans weapon si libre
                                    if not (p.get("equipment") or {}).get("weapon"):
                                        p.setdefault("equipment",{})["weapon"] = obj
                                        apply_equipment_effects(p)
                                    else:
                                        p["weapon_bonus"] = max(p["weapon_bonus"], power or 5)
                                        p["weapon_name"] = obj.get("name","Arme")
                                else:
                                    p["gold"] += 1
                                ident = pid_identity.get(pid)
                                if ident: mark_dirty(ident["username"])
                    send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "drop":
                    with lock:
                        inv = inventories.get(pid, [])
                        idx = next((i for i,v in enumerate(inv) if str(v["id"]) == str(data.get("id"))), None)
                        if idx is not None:
                            v = inv.pop(idx)
                            p = players.get(pid)
                            if p:
                                px, py = p["x"], p["y"]
                                ix, iy = move_with_collisions(px, py, data.get("dx",0) or 0, data.get("dy",0) or 0, ITEM_SIZE)
                                # Allouer un nouvel ID d'item au sol pour éviter toute collision
                                new_iid = next_item_id; next_item_id += 1
                                items[new_iid] = {"x": ix, "y": iy, "name": v["name"], "type": v["type"], "power": v.get("power",0)}
                                ident = pid_identity.get(pid)
                                if ident: mark_dirty(ident["username"])
                    send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "cast":
                    slot = int(data.get("slot",0))
                    tx = float(data.get("tx",0)); ty = float(data.get("ty",0))
                    with lock:
                        ok, reason = can_cast(pid, slot)
                        if not ok:
                            send_to(pid, {"type":"chat","from":"SYSTEM","msg":f"Sort {slot} indisponible ({reason})."})
                        else:
                            p = players.get(pid)
                            sp = SPELLS_BY_CLASS.get(p.get("class","Mage"), {}).get(slot)
                            px, py = p["x"], p["y"]
                            spend_cast(pid, slot)
                            if sp["type"] == "projectile":
                                spawn_projectile(pid, px, py, tx, ty, sp)
                            elif sp["type"] == "cone":
                                apply_cone(pid, px, py, tx, ty, sp)
                            elif sp["type"] == "aoe":
                                apply_aoe(pid, px, py, sp)
                            elif sp["type"] == "heal":
                                p["hp"] = min(p["max_hp"], p["hp"] + sp["amount"] )
                            # notifier un FX basique au client
                            fx = {"type":"fx","fx":"cast","slot":slot,"x":px,"y":py,"tx":tx,"ty":ty,"duration":0.25}
                            broadcast_obj(fx)
                            # broadcast immédiat pour que les projectiles bougent même si le joueur est immobile
                            broadcast_state()

                elif t == "equip_item":
                    slot = str(data.get("slot",""))
                    iid = data.get("id")
                    allowed = {
                        "head": {"head"}, "neck": {"neck"}, "chest": {"chest"}, "legs": {"legs"},
                        "boots": {"boots"}, "ring1": {"ring"}, "ring2": {"ring"},
                        "weapon": {"weapon"}, "offhand": {"shield","offhand"}
                    }
                    with lock:
                        p = players.get(pid)
                        if not p:
                            continue
                        inv = inventories.get(pid, [])
                        idx = next((i for i,v in enumerate(inv) if str(v.get("id")) == str(iid)), None)
                        if idx is None:
                            send_to(pid, {"type":"chat","from":"SYSTEM","msg":"Objet introuvable dans l'inventaire."})
                            continue
                        obj = inv[idx]
                        typ = str(obj.get("type",""))
                        if slot not in allowed or typ not in allowed[slot]:
                            send_to(pid, {"type":"chat","from":"SYSTEM","msg":"Type d'objet incompatible avec le slot."})
                            continue
                        inv.pop(idx)
                        p.setdefault("equipment", {})
                        prev = (p.get("equipment") or {}).get(slot)
                        (p["equipment"]) [slot] = obj
                        apply_equipment_effects(p)
                        if prev:
                            inv.append(prev)
                        ident = pid_identity.get(pid)
                        if ident: mark_dirty(ident["username"])
                    send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "unequip_slot":
                    slot = str(data.get("slot",""))
                    with lock:
                        p = players.get(pid)
                        if not p:
                            continue
                        eq = p.get("equipment") or {}
                        obj = eq.get(slot)
                        if obj:
                            inventories.setdefault(pid, []).append(obj)
                            eq[slot] = None
                            apply_equipment_effects(p)
                            ident = pid_identity.get(pid)
                            if ident: mark_dirty(ident["username"])
                    send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "chat":
                    txt = str(data.get("msg","")).strip()
                    if txt:
                        with lock:
                            author = players.get(pid, {}).get("name","???")
                        broadcast_obj({"type":"chat","from":author,"msg":txt})

                elif t == "request_inventory":
                    send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "get_chunks":
                    req = data.get("chunks", [])
                    out = []
                    with lock:
                        for ent in req:
                            cx = int(ent.get("cx")); cy = int(ent.get("cy"))
                            tiles = get_chunk_with_overrides(cx, cy)
                            out.append({"cx": cx, "cy": cy, "tiles": tiles})
                    send_to(pid, {"type":"chunks", "list": out})

                elif t == "interact":
                    with lock:
                        p = players.get(pid)
                        if not p: continue
                        # cible PNJ la plus proche (amicale)
                        target = None; best = 999999
                        for nid, n in npcs.items():
                            if n.get("hostile", True):
                                continue
                            d2 = (n["x"]-p["x"])**2 + (n["y"]-p["y"])**2
                            if d2 < best and d2 <= (48**2):
                                best, target = d2, (nid, n)
                        if not target:
                            continue
                        nid, n = target
                        if n.get("merchant_id"):
                            mid = n["merchant_id"]
                            merch = merchants_data.get(mid, {})
                            send_to(pid, {"type":"merchant_open", "merchant_id": mid, "name": merch.get("name","Marchand"), "stock": merch.get("stock", []), "gold": players[pid].get("gold",0)})
                        elif n.get("quest_ids"):
                            qids = list(n.get("quest_ids", []))
                            char_quests = _get_char_quests(pid)
                            # assembler statut
                            lst = []
                            for qid in qids:
                                q = quests_data.get(qid) or {}
                                st = char_quests.get(qid, {"status":"available","progress":{}})
                                lst.append({"id": qid, "title": q.get("title","?"), "desc": q.get("desc",""), "status": st.get("status","available"), "progress": st.get("progress",{})})
                            send_to(pid, {"type":"quest_open", "list": lst})
                        elif n.get("tower_entrance"):
                            enter_tower_floor(pid, 1)

                elif t == "merchant_buy":
                    mid = str(data.get("merchant_id",""))
                    idx = int(data.get("index", -1))
                    with lock:
                        stock = (merchants_data.get(mid, {}) or {}).get("stock", [])
                        if 0 <= idx < len(stock):
                            entry = stock[idx]
                            price = int(entry.get("price", 1))
                            p = players.get(pid)
                            if p and p.get("gold",0) >= price:
                                p["gold"] -= price
                                inv_id = 1000000 + next_item_id; next_item_id += 1
                                inventories.setdefault(pid, []).append({"id": inv_id, "name": entry.get("name","Objet"), "type": entry.get("type","misc"), "power": int(entry.get("power",0))})
                                ident = pid_identity.get(pid)
                                if ident: mark_dirty(ident["username"])
                                send_to(pid, {"type":"merchant_result","ok":True,"gold":p.get("gold",0)})
                                send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})
                            else:
                                send_to(pid, {"type":"merchant_result","ok":False,"msg":"Pas assez d'or."})

                elif t == "merchant_sell":
                    iid = data.get("inventory_id")
                    with lock:
                        inv = inventories.get(pid, [])
                        idx = next((i for i,v in enumerate(inv) if str(v.get("id")) == str(iid)), None)
                        if idx is not None:
                            obj = inv.pop(idx)
                            price = max(1, int(obj.get("power",1)) // 2 + (5 if obj.get("type") == "weapon" else 2))
                            players[pid]["gold"] = players.get(pid, {}).get("gold",0) + price
                            ident = pid_identity.get(pid)
                            if ident: mark_dirty(ident["username"])
                            send_to(pid, {"type":"merchant_result","ok":True,"gold":players[pid].get("gold",0)})
                            send_to(pid, {"type":"inventory", "inventory": inventories.get(pid, [])})

                elif t == "quest_accept":
                    qid = str(data.get("quest_id",""))
                    with lock:
                        _accept_quest(pid, qid)
                    send_to(pid, {"type":"quest_updated"})

                elif t == "quest_turnin":
                    qid = str(data.get("quest_id",""))
                    with lock:
                        ok, msg = _turnin_quest(pid, qid)
                    send_to(pid, {"type":"quest_result", "ok": ok, "msg": msg})

                elif t == "paint_tile":
                    tx = int(data.get("tx")); ty = int(data.get("ty")); tval = int(data.get("t"))
                    with lock:
                        map_overrides[(tx,ty)] = tval
                        _rebuild_overrides_index(); save_map_overrides()
                    # réponse immédiate pour feedback
                    send_to(pid, {"type":"chunks", "list": [{"cx": int(math.floor(tx/CHUNK_TILES)), "cy": int(math.floor(ty/CHUNK_TILES)), "tiles": get_chunk_with_overrides(int(math.floor(tx/CHUNK_TILES)), int(math.floor(ty/CHUNK_TILES)))}]})

                # push l'état à ~20 Hz max
                broadcast_state()

    # cleanup
        left_name = None
        with lock:
            for _pid, c in list(clients.items()):
                if c == conn:
                    left_name = players.get(_pid, {}).get("name","Un joueur")
                    ident = pid_identity.get(_pid)
                    if ident:
                        # Persister la progression
                        persist_player_to_character(ident["username"], ident["char_id"], players.get(_pid, {}), inventories.get(_pid, []))
                    try: clients[_pid].close()
                    except: pass
                    clients.pop(_pid, None)
                    players.pop(_pid, None)
                    inventories.pop(_pid, None)
                    cooldowns.pop(_pid, None)
                    pid_identity.pop(_pid, None)
                    break
        broadcast_state()
        if left_name:
            broadcast_obj({"type":"chat","from":"SYSTEM","msg":f"{left_name} s'est déconnecté."})

        # ---------- Boucle logique ----------
    finally:
        try:
            _cleanup_disconnect(authed_user, pid)
        except Exception:
            pass

# Gestion quêtes côté serveur

def _get_char_quests(pid):
    ident = pid_identity.get(pid)
    if not ident:
        return {}
    user = accounts["users"].get(ident["username"], {})
    ch = (user.get("characters", {})).get(str(ident.get("char_id")), {})
    return ch.setdefault("quests", {})


def _accept_quest(pid, qid: str):
    q = quests_data.get(qid)
    if not q: return
    with lock:
        qs = _get_char_quests(pid)
        if qid not in qs:
            qs[qid] = {"status":"active", "progress": {}}
            ident = pid_identity.get(pid)
            if ident: mark_dirty(ident["username"])


def _inc_quest_kill(pid, mob_name: str):
    with lock:
        qs = _get_char_quests(pid)
        for qid, state in qs.items():
            if state.get("status") != "active":
                continue
            req = (quests_data.get(qid, {})).get("requirements", {}).get("kill", {})
            for target_name, need in req.items():
                if target_name in mob_name:
                    cur = state.setdefault("progress", {}).get(target_name, 0)
                    state["progress"][target_name] = min(need, cur + 1)
                    ident = pid_identity.get(pid)
                    if ident: mark_dirty(ident["username"])


def _turnin_quest(pid, qid: str):
    q = quests_data.get(qid)
    if not q:
        return False, "Quête inconnue."
    with lock:
        qs = _get_char_quests(pid)
        st = qs.get(qid)
        if not st or st.get("status") != "active":
            return False, "Quête non active."
        # vérifier progression
        ok = True
        req = (q.get("requirements", {})).get("kill", {})
        for name, need in req.items():
            if (st.get("progress", {}).get(name, 0)) < int(need):
                ok = False; break
        if not ok:
            return False, "Objectifs non atteints."
        # récompenser
        p = players.get(pid)
        if not p: return False, "Erreur."
        r = q.get("rewards", {})
        leveled = grant_xp_gold(p, xp=int(r.get("xp",0)), gold=int(r.get("gold",0)))
        inv = inventories.get(pid, [])
        if r.get("item"):
            global next_item_id
            inv_id = 1000000 + next_item_id; next_item_id += 1
            inv.append({"id": inv_id, **r["item"]})
        qs[qid]["status"] = "done"
        ident = pid_identity.get(pid)
        if ident: mark_dirty(ident["username"])
        return True, "Quête terminée !"

def logic_loop():
    with lock:
        for _ in range(6): spawn_mob()
    broadcast_state()
    tick = 1.0 / TICK_HZ
    while True:
        time.sleep(tick)
        changed = False
        with lock:
            # projectiles
            t0 = now()
            to_remove = []
            for pid_, p in list(projs.items()):
                # avancer plusieurs sous-steps pour lisser et éviter les collisions à grande vitesse
                sub = 2
                for _ in range(sub):
                    p["x"] += p["vx"]/sub; p["y"] += p["vy"]/sub
                changed = True  # positions de projectiles ont changé → diffuser
                if p["x"] < 0 or p["x"] > WORLD_W or p["y"] < 0 or p["y"] > WORLD_H or t0 >= p["expire_at"]:
                    to_remove.append(pid_); continue
                if is_colliding_rect(p["x"], p["y"], 10, 10):
                    to_remove.append(pid_); continue
                hit = None
                for nid, n in npcs.items():
                    if dist(p["x"], p["y"], n["x"], n["y"]) <= 18:
                        hit = nid; break
                if hit is not None:
                    n = npcs[hit]
                    caster = players.get(p.get("owner")) or {}
                    bonus = 0
                    if caster.get("class") == "Guerrier": bonus = int(caster.get("stats",{}).get("str",0)*0.6)
                    elif caster.get("class") == "Mage": bonus = int(caster.get("stats",{}).get("int",0)*0.6)
                    elif caster.get("class") == "Voleur": bonus = int(caster.get("stats",{}).get("agi",0)*0.6)
                    n["hp"] -= (p["dmg"] + bonus); n["last_hit_by"] = p["owner"]
                    if n["hp"] <= 0:
                        owner_pid = p.get("owner")
                        owner = players.get(owner_pid) if owner_pid else None
                        if owner:
                            leveled = grant_xp_gold(owner, xp=random.randint(12,22), gold=random.randint(1,3))
                            ident = pid_identity.get(owner_pid) if owner_pid else None
                            if ident: mark_dirty(ident["username"])
                            # progression quête
                            _inc_quest_kill(owner_pid, n.get("name","Mob"))
                        drop_loot_at(n["x"], n["y"])
                        del npcs[hit]
                    to_remove.append(pid_)
                    changed = True
            for r in to_remove: projs.pop(r, None)

            # IA mobs + boss attaques spéciales
            for n in list(npcs.values()):
                target = None; best = 1e9
                for p in players.values():
                    if p["dead"]: continue
                    d = dist(n["x"], n["y"], p["x"], p["y"])
                    if d < best: best, target = d, p
                if not n.get("hostile", True):
                    continue  # PNJ pacifiques
                if target and best < 160:
                    if best > 2:
                        vx = target["x"] - n["x"]; vy = target["y"] - n["y"]
                        l = math.hypot(vx, vy) or 1
                        n["x"], n["y"] = move_with_collisions(n["x"], n["y"], (n["speed"]*vx/l), (n["speed"]*vy/l), NPC_SIZE)
                        changed = True
                    if best <= 28 and now() >= n.get("atk_until", 0):
                        n["atk_until"] = now() + 1.2
                        target["hp"] -= n.get("dmg", 6)
                        if target["hp"] <= 0 and not target["dead"]:
                            target["dead"] = True
                            target["respawn_at"] = now() + 4.0
                        changed = True
                # boss: attaque spéciale périodique
                if n.get("is_boss") and now() >= n.get("boss_next", 0):
                    n["boss_next"] = now() + (3.5 if n.get("boss_big") else 5.0)
                    # AoE autour du boss
                    for p in players.values():
                        if p["dead"]: continue
                        if dist(n["x"], n["y"], p["x"], p["y"]) <= (120 if n.get("boss_big") else 90):
                            p["hp"] -= int(n.get("dmg",10) * (1.5 if n.get("boss_big") else 1.2))
                            if p["hp"] <= 0 and not p["dead"]:
                                p["dead"] = True; p["respawn_at"] = now() + 4.0
                            changed = True

            # respawn joueurs + regen
            for p in players.values():
                if p["dead"] and now() >= p.get("respawn_at", 0):
                    p["dead"] = False
                    p["hp"] = p["max_hp"]; p["mp"] = p["max_mp"]
                    p["x"], p["y"] = random_free_pos()
                    changed = True
                if not p["dead"]:
                    p["hp"] = min(p["max_hp"], p["hp"] + 0.5)
                    p["mp"] = min(p["max_mp"], p["mp"] + 0.5)

            # respawn mobs si peu
            if len(npcs) < 5 and random.random() < 0.05:
                spawn_mob(); changed = True
            if random.random() < 0.002:
                spawn_portal_to_dungeon(); changed = True

        if changed:
            broadcast_state()

# Entrée tour et utilitaires

def enter_tower_floor(pid: int, floor: int):
    if floor < 1: floor = 1
    if floor > 100: floor = 100
    ensure_floor_area(floor)
    with lock:
        p = players.get(pid)
        if not p: return
        tx0 = TOWER_BASE_TX + floor * (TOWER_FLOOR_W + 8)
        ty0 = TOWER_BASE_TY
        p["x"] = (tx0+2)*TILE + TILE//2
        p["y"] = (ty0+TOWER_FLOOR_H-3)*TILE + TILE//2
        p["tower_floor"] = floor
        ident = pid_identity.get(pid)
        if ident: mark_dirty(ident["username"])
        # envoyer quelques chunks immédiatement pour éviter écran vide
        cx0 = int(math.floor((tx0+TOWER_FLOOR_W//2)/CHUNK_TILES))
        cy0 = int(math.floor((ty0+TOWER_FLOOR_H//2)/CHUNK_TILES))
        lst = []
        for dy in range(-1,2):
            for dx in range(-1,2):
                cx = cx0+dx; cy = cy0+dy
                lst.append({"cx": cx, "cy": cy, "tiles": get_chunk_with_overrides(cx, cy)})
        send_to(pid, {"type":"chunks","list":lst})
        broadcast_state()

def start_server():
    load_accounts()
    _ensure_default_files()
    load_merchants(); load_quests(); load_map_overrides()
    # assurer village + tour
    ensure_starting_village(); ensure_tower_entrance(); save_map_overrides()
    # PNJ marchands et donneur de quêtes
    # positions village (en px)
    spawn_merchant_npc(-8*TILE, -2*TILE, "weaponsmith")
    spawn_merchant_npc(6*TILE, -2*TILE, "alchemist")
    spawn_quest_giver_npc(0, 6*TILE, [k for k in list(quests_data.keys())[:2]], name="Intendante du village")
    # gardien de la tour (entrée)
    guard_id = spawn_villager_npc(0, 0, name="Gardien de la tour")
    npcs[guard_id]["tower_entrance"] = True
    threading.Thread(target=saver_loop, daemon=True).start()
    threading.Thread(target=logic_loop, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen()
    print(f"[SERVEUR] en ligne sur {HOST}:{PORT}")
    while True:
        conn, addr = s.accept()  # pas de timeout client
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()



def _cleanup_disconnect(authed_user, pid):
    with lock:
        if authed_user in active_usernames:
            active_usernames.discard(authed_user)
        if pid in clients:
            try: clients[pid].close()
            except: pass
            clients.pop(pid, None)
        if pid in players: players.pop(pid, None)
        if pid in inventories: inventories.pop(pid, None)
        if pid in cooldowns: cooldowns.pop(pid, None)
        if pid in pid_identity: pid_identity.pop(pid, None)

# helpers: overrides & simple structure carving

def carve_rect(tx0: int, ty0: int, w: int, h: int, tile_val: int):
    for ty in range(ty0, ty0+h):
        for tx in range(tx0, tx0+w):
            map_overrides[(tx, ty)] = int(tile_val)
    _rebuild_overrides_index()


def ensure_starting_village():
    # Village autour du centre (place sable + routes + quelques maisons)
    tx0, ty0 = -16, -12
    w, h = 34, 26
    carve_rect(tx0, ty0, w, h, 3)  # place
    # routes cardinales
    for x in range(tx0, tx0+w):
        map_overrides[(x, 0)] = 4
        map_overrides[(x, -1)] = 4
    for y in range(ty0, ty0+h):
        map_overrides[(0, y)] = 4
        map_overrides[(1, y)] = 4
    # maisons rectangles de murs
    for bx, by in [(-12,-8), (10,-6), (-6,6), (8,8)]:
        for x in range(bx, bx+6):
            map_overrides[(x, by)] = 1
            map_overrides[(x, by+4)] = 1
        for y in range(by, by+5):
            map_overrides[(bx, y)] = 1
            map_overrides[(bx+5, y)] = 1
    _rebuild_overrides_index()


def ensure_tower_entrance():
    # Petite base pavée au centre comme entrée de tour
    carve_rect(-4, -4, 8, 8, 4)


def floor_theme(floor: int) -> str:
    idx = ((floor-1)//10) % 5
    return ["slime","gob","wolf","orc","bear"][idx]


def floor_monster_theme(theme: str) -> str:
    return {"slime":"slime","gob":"gob","wolf":"wolf","orc":"orc","bear":"bear"}.get(theme)


def ensure_floor_area(floor: int):
    # génère un étage rectangulaire clos dans une zone dédiée
    theme = floor_theme(floor)
    tx0 = TOWER_BASE_TX + floor * (TOWER_FLOOR_W + 8)
    ty0 = TOWER_BASE_TY
    base_tile = 3 if theme in ("gob","orc") else 0
    carve_rect(tx0, ty0, TOWER_FLOOR_W, TOWER_FLOOR_H, base_tile)
    # murs
    for x in range(tx0, tx0+TOWER_FLOOR_W):
        map_overrides[(x, ty0)] = 1
        map_overrides[(x, ty0+TOWER_FLOOR_H-1)] = 1
    for y in range(ty0, ty0+TOWER_FLOOR_H):
        map_overrides[(tx0, y)] = 1
        map_overrides[(tx0+TOWER_FLOOR_W-1, y)] = 1
    _rebuild_overrides_index(); save_map_overrides()
    # peupler
    center_x = (tx0 + TOWER_FLOOR_W//2) * TILE + TILE//2
    center_y = (ty0 + TOWER_FLOOR_H//2) * TILE + TILE//2
    for _ in range(8):
        sx = (tx0+2 + random.randint(0, TOWER_FLOOR_W-4)) * TILE + TILE//2
        sy = (ty0+2 + random.randint(0, TOWER_FLOOR_H-4)) * TILE + TILE//2
        spawn_mob_at(sx, sy, level=floor, theme=floor_monster_theme(theme))
    if floor % 10 == 0:
        spawn_boss_at(center_x, center_y, level=floor+2, big=True, theme=floor_monster_theme(theme))
    elif floor % 5 == 0:
        spawn_boss_at(center_x, center_y, level=floor+1, big=False, theme=floor_monster_theme(theme))
    # escalier vers l'étage suivant
    global next_item_id
    iid = next_item_id; next_item_id += 1
    items[iid] = {"x": (tx0+TOWER_FLOOR_W-3)*TILE, "y": (ty0+2)*TILE, "name": "Escalier", "type": "stairs", "power": 0, "floor": floor+1}


def spawn_portal_to_dungeon():
    # Compat: simple no-op spawn d'un jeton décoratif
    global next_item_id
    x, y = random_free_pos()
    iid = next_item_id; next_item_id += 1
    items[iid] = {"x": x, "y": y, "name": "Portail instable", "type": "gold", "power": 1}

if __name__ == "__main__":
    start_server()