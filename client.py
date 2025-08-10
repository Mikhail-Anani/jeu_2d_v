# client.py
import socket, threading, json, pygame, time, os, math, copy

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555
PLAYER_NAME = "Héros"

WIDTH, HEIGHT = 960, 720
SPEED = 4

players = {}   # "pid" -> {...}
npcs = {}      # "nid" -> {...}
items = {}     # "iid" -> {...}
projs = {}     # "id"  -> {...}
your_id = None

TILE = 40; GRID_W = 0; GRID_H = 0
# Monde en chunks 64x64
CHUNK_TILES = 64
loaded_chunks = {}       # (cx,cy) -> [[tile]]
requested_chunks = set() # {(cx,cy)}
last_chunk_request = 0.0

def get_tile(tx, ty):
    cx = int(math.floor(tx / CHUNK_TILES))
    cy = int(math.floor(ty / CHUNK_TILES))
    ch = loaded_chunks.get((cx, cy))
    if ch is None:
        return 0
    lx = int(tx - cx*CHUNK_TILES); ly = int(ty - cy*CHUNK_TILES)
    if 0 <= ly < CHUNK_TILES and 0 <= lx < CHUNK_TILES:
        return ch[ly][lx]
    return 0
SPELLS = {}

inventory = []; inv_open = False; inv_sel = 0
# UI équipement + drag
EQUIP_UI = {"open": False}
drag_item_id = None
inv_item_rects = []
slot_rects = {}

chat_log = []; chat_typing = False; chat_buffer = ""

# ---- Config & keybindings ----
DEFAULT_KEYS = {
    "move_up": "K_z", "move_left": "K_q", "move_down": "K_s", "move_right": "K_d",
    "pickup": "K_e", "inventory": "K_i", "drop": "K_g", "use": "K_u",
    "chat": "K_RETURN", "hud_toggle": "K_F1", "options": "K_F10",
    "spell_1": "K_1", "spell_2": "K_2", "spell_3": "K_3", "spell_4": "K_4",
    "stats": "K_p", "equipment": "K_c", "map": "K_m"
}
CONFIG_PATH = "config.json"
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH,"r",encoding="utf-8") as f:
                data = json.load(f)
            keys = {**DEFAULT_KEYS, **data.get("keys", {})}
            hud_scale = data.get("hud_scale","large")
            return {"keys": keys, "hud_scale": hud_scale}
        except: pass
    cfg = {"keys": DEFAULT_KEYS, "hud_scale":"large"}
    with open(CONFIG_PATH,"w",encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg

CONFIG = load_config()
HUD_SCALE = CONFIG.get("hud_scale","large")
KEYS = CONFIG["keys"]
def save_config():
    with open(CONFIG_PATH,"w",encoding="utf-8") as f:
        json.dump({"keys": KEYS, "hud_scale": HUD_SCALE}, f, indent=2, ensure_ascii=False)

def keyconst(name): return getattr(pygame, name, None)
def pressed(name):
    kc = keyconst(KEYS.get(name,""))
    return kc is not None and pygame.key.get_pressed()[kc]
def key_is(event_key, name):
    kc = keyconst(KEYS.get(name,""))
    return (kc is not None) and (event_key == kc)

# ---- Réseau ----
def send_json(conn, obj):
    try:
        conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except Exception as e:
        print("send_json error:", e)

FX = []  # effets visuels temporaires
tooltip = {"txt": None, "until": 0.0, "pos": (0,0)}

# ---- UI / Auth ----
UI_STATE = "login"  # login | select | create | game

login_mode = "login"  # login | register
login_username = ""
login_password = ""
login_focus = "user"  # user | pass
login_msg = ""

char_list = []  # [{id,name,class,level}]
char_sel = 0
char_msg = ""

CLASSES = ["Guerrier", "Mage", "Voleur"]
create_name = ""
create_class_idx = 0
create_msg = ""

def network_thread(sock):
    global your_id, TILE, GRID_W, GRID_H, inventory, SPELLS
    global UI_STATE, char_list, char_sel, login_msg, char_msg, create_msg
    try:
        f = sock.makefile("r")
        for line in f:
            try: data = json.loads(line)
            except: continue
            t = data.get("type")
            if t == "welcome":
                your_id = data.get("your_id")
                TILE = int(data.get("tile", TILE)); GRID_W = int(data.get("grid_w", GRID_W)); GRID_H = int(data.get("grid_h", GRID_H))
                inventory = data.get("inventory", [])
                you = data.get("you"); 
                if you: players[str(your_id)] = you
                sp = data.get("spells", {})
                # normaliser les clés en str pour l'UI des sorts
                try:
                    SPELLS = {str(k):v for k,v in sp.items()}
                except Exception:
                    SPELLS = sp
                UI_STATE = "game"
            elif t == "login_ok":
                lst = data.get("characters", [])
                char_list = lst
                char_sel = 0
                login_msg = ""
                UI_STATE = "select"
            elif t == "login_error":
                login_msg = data.get("msg", "Erreur")
            elif t == "characters":
                lst = data.get("characters", [])
                char_list = lst
                if char_sel >= len(char_list):
                    char_sel = max(0, len(char_list)-1)
                char_msg = ""
                # après création, revenir à la sélection
                if UI_STATE == "create":
                    UI_STATE = "select"
            elif t == "create_error":
                create_msg = data.get("msg", "Erreur de création")
            elif t == "enter_error":
                char_msg = data.get("msg", "Erreur d'entrée")
            elif t == "state":
                players.clear(); players.update({str(k):v for k,v in data.get("players",{}).items()})
                npcs.clear();    npcs.update({str(k):v for k,v in data.get("npcs",{}).items()})
                items.clear();   items.update({str(k):v for k,v in data.get("items",{}).items()})
                projs.clear();   projs.update(data.get("projs",{}))
            elif t == "chunks":
                for entry in data.get("list", []):
                    cx = int(entry.get("cx")); cy = int(entry.get("cy"))
                    loaded_chunks[(cx,cy)] = entry.get("tiles", [])
                    requested_chunks.discard((cx,cy))
            elif t == "inventory":
                inventory = data.get("inventory", inventory)
            elif t == "chat":
                chat_log.append((data.get("from","?"), data.get("msg",""))); 
                if len(chat_log) > 60: del chat_log[0]
            elif t == "fx":
                fx = copy.deepcopy(data); fx["until"] = time.time() + float(fx.get("duration",0.2))
                FX.append(fx)
    except Exception as e:
        print("Réseau stoppé:", e)

# ---- Connexion (UNE SEULE fois) ----
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((SERVER_HOST, SERVER_PORT))
threading.Thread(target=network_thread, args=(sock,), daemon=True).start()

# ---- Pygame ----
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("MMO-lite — Login & Sélection de personnage")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 18)
bigfont = pygame.font.SysFont(None, 22)

# ---- Interpolation anti-tremblement ----
render_pos_players = {}   # id -> (x,y)
render_pos_npcs = {}
render_pos_projs = {}

# Caméra
cam_x = 0; cam_y = 0
def world_to_screen(wx, wy):
    return int(wx - cam_x), int(wy - cam_y)
def lerp(a, b, t): return a + (b - a) * t
def smooth_to(render_dict, key, tx, ty, speed=0.25):
    x, y = render_dict.get(key, (tx, ty))
    nx = lerp(x, tx, speed)
    ny = lerp(y, ty, speed)
    render_dict[key] = (nx, ny)
    return nx, ny

# ---- Sprites (dessinés en code) ----
def draw_tile(ty, tx, t):
    # dessiner en coordonnées écran (monde - caméra)
    x, y = int(tx*TILE - cam_x), int(ty*TILE - cam_y)
    r = pygame.Rect(x, y, TILE, TILE)
    if t == 0:     # herbe
        base = 38 + ((tx+ty) % 2)*2
        pygame.draw.rect(screen, (base, base+16, base), r)
        if (tx+ty) % 3 == 0:
            pygame.draw.circle(screen, (30,50,30), (x+8, y+10), 3)
            pygame.draw.circle(screen, (30,50,30), (x+22, y+28), 3)
    elif t == 1:   # mur
        pygame.draw.rect(screen, (90,90,96), r)
        pygame.draw.rect(screen, (70,70,76), r, 2)
        for i in range(4, TILE, 8):
            pygame.draw.line(screen, (110,110,120), (x, y+i), (x+TILE, y+i), 1)
    elif t == 2:   # eau
        pygame.draw.rect(screen, (35,70,140), r)
        pygame.draw.arc(screen, (25,60,120), (x+6,y+6,14,10), 0, math.pi, 2)
        pygame.draw.arc(screen, (25,60,120), (x+18,y+18,14,10), 0, math.pi, 2)
    elif t == 3:   # sable
        pygame.draw.rect(screen, (168,150,105), r)
        pygame.draw.line(screen, (190,170,120), (x+6,y+12), (x+24,y+12), 1)
    else:          # route/pont
        pygame.draw.rect(screen, (120,120,128), r)
        pygame.draw.rect(screen, (90,90,100), r, 1)

def draw_tilemap():
    start_tx = int(math.floor(cam_x / TILE)) - 2
    end_tx = int(math.floor((cam_x + WIDTH) / TILE)) + 3
    start_ty = int(math.floor(cam_y / TILE)) - 2
    end_ty = int(math.floor((cam_y + HEIGHT) / TILE)) + 3
    need = set()
    for ty in range(start_ty, end_ty):
        for tx in range(start_tx, end_tx):
            cx = int(math.floor(tx / CHUNK_TILES)); cy = int(math.floor(ty / CHUNK_TILES))
            if (cx,cy) not in loaded_chunks:
                need.add((cx,cy))
                t = 0
            else:
                t = get_tile(tx, ty)
            draw_tile(ty, tx, t)
    global last_chunk_request
    if need and time.time() - last_chunk_request > 0.15:
        req = []
        for c in sorted(list(need)):
            if c not in requested_chunks:
                requested_chunks.add(c)
                req.append(c)
        if req:
            send_json(sock, {"type":"get_chunks", "chunks": req})
            last_chunk_request = time.time()

def draw_bar(x, y, w, h, ratio, fg, bg=(60,60,60)):
    pygame.draw.rect(screen, bg, (x, y, w, h))
    pygame.draw.rect(screen, fg, (x, y, int(w*max(0,min(1,ratio))), h))

def sprite_player(x, y, is_you, moving, hp_ratio):
    # Sprite 2D simple (tête+corps+bras/jambes stylisés) au lieu d'un cube
    base_col = (90, 180, 120) if is_you else (120, 140, 210)
    # corps
    body_w, body_h = 16, 22
    body = pygame.Rect(int(x - body_w/2), int(y - body_h/2), body_w, body_h)
    pygame.draw.rect(screen, base_col, body, 0, border_radius=4)
    # tête
    pygame.draw.circle(screen, (230, 210, 180), (body.centerx, body.top-6), 6)
    # yeux
    pygame.draw.circle(screen, (20,20,25), (body.centerx-2, body.top-8), 1)
    pygame.draw.circle(screen, (20,20,25), (body.centerx+2, body.top-8), 1)
    # bras
    pygame.draw.line(screen, (70,90,120), (body.left-4, body.centery-2), (body.left+2, body.centery+2), 3)
    pygame.draw.line(screen, (70,90,120), (body.right+4, body.centery-2), (body.right-2, body.centery+2), 3)
    # jambes
    pygame.draw.line(screen, (60,50,40), (body.centerx-4, body.bottom), (body.centerx-4, body.bottom+6), 3)
    pygame.draw.line(screen, (60,50,40), (body.centerx+4, body.bottom), (body.centerx+4, body.bottom+6), 3)
    # barre HP
    if hp_ratio is not None:
        draw_bar(body.x, body.y-10, body_w, 4, hp_ratio, (200,60,60))

def sprite_mob(name, x, y, moving, hp_ratio):
    # sprite cartoon simple par type
    if "Rat" in name:
        col = (140,140,140); size=18
        pygame.draw.circle(screen, col, (int(x), int(y)), size//2)
        pygame.draw.circle(screen, (200,200,200), (int(x)+6, int(y)-6), 3)
    elif "Gobelin" in name:
        col = (90,160,90); size=20
        pygame.draw.rect(screen, col, (int(x-10), int(y-12), 20, 24), border_radius=4)
    elif "Slime" in name:
        col = (120,180,220); size=22
        pygame.draw.ellipse(screen, col, (int(x-12), int(y-8), 24, 16))
    elif "Loup" in name:
        col = (140,120,100); size=22
        pygame.draw.polygon(screen, col, [(int(x-12),int(y)),(int(x),int(y-8)),(int(x+12),int(y)),(int(x),int(y+8))])
    else:
        col = (200,140,80); size=20
        pygame.draw.rect(screen, col, (int(x-10), int(y-10), 20, 20), border_radius=4)
    if hp_ratio is not None:
        draw_bar(int(x-12), int(y-18), 24, 4, hp_ratio, (200,60,60))

def sprite_item(typ, ix, iy):
    r = pygame.Rect(int(ix - 8), int(iy - 8), 16, 16)
    col = {
        "potion": (200, 70, 70),
        "gold":   (220, 200, 60),
        "weapon": (160, 160, 200),
        "scroll": (200, 170, 120),
    }.get(typ, (180,180,180))
    pygame.draw.rect(screen, col, r, border_radius=4)
    pygame.draw.rect(screen, (20,20,20), r, 1, border_radius=4)

def draw_player(pid, info):
    tx, ty = float(info.get("x",0)), float(info.get("y",0))
    rx, ry = smooth_to(render_pos_players, pid, tx, ty, 0.4 if str(pid)==str(your_id) else 0.25)
    sx, sy = world_to_screen(rx, ry)
    is_you = (str(pid)==str(your_id))
    mhp = info.get("max_hp") or 0
    hp_ratio = (info.get("hp",0) / mhp) if mhp > 0 else None
    moving = True
    sprite_player(sx, sy, is_you, moving, hp_ratio)
    name = info.get("name","?") + (" • YOU" if is_you else "")
    screen.blit(font.render(name, True, (255,255,255)), (int(sx-20), int(sy-28)))

def draw_npc(nid, info):
    tx, ty = float(info.get("x",0)), float(info.get("y",0))
    rx, ry = smooth_to(render_pos_npcs, nid, tx, ty, 0.25)
    sx, sy = world_to_screen(rx, ry)
    mhp = info.get("max_hp") or 0
    hp_ratio = (info.get("hp",0) / mhp) if mhp > 0 else None
    name = info.get("name","PNJ")
    sprite_mob(name, sx, sy, True, hp_ratio)
    if not info.get("hostile", True):
        # icône PNJ
        pygame.draw.circle(screen, (240,220,90), (int(sx), int(sy-16)), 3)

def draw_inventory():
    s = {"large":1.0, "medium":0.8, "hidden":0.0}.get(HUD_SCALE, 1.0)
    if s == 0: return
    w, h = int(360*s), int(300*s)
    x, y = WIDTH - w - 16, 16
    pygame.draw.rect(screen, (18,18,20), (x, y, w, h))
    pygame.draw.rect(screen, (100,100,110), (x, y, w, h), 2)
    title = bigfont.render("Inventaire (I) — U: utiliser, G: lâcher", True, (255,255,255))
    screen.blit(title, (x+10, y+8))
    line_h = int(24*s); list_y = y + int(42*s)
    for i, obj in enumerate(inventory):
        prefix = "> " if i == inv_sel else "  "
        extra = f" (+{obj.get('power',0)})" if obj.get("type") in ("weapon","potion","scroll") else ""
        txt = f"{prefix}{obj.get('name','?')} [{obj.get('type','?')}] {extra}"
        col = (255,255,255) if i == inv_sel else (210,210,210)
        t = font.render(txt, True, col); screen.blit(t, (x+12, list_y + i*line_h))

def hud_scale_val():
    return {"large":1.0, "medium":0.8, "hidden":0.0}.get(HUD_SCALE, 1.0)

def draw_hud():
    s = hud_scale_val()
    if s == 0: return
    me = players.get(str(your_id))
    if not me: return
    x, y = 16, HEIGHT - int(64*s)
    max_hp = max(1, me.get("max_hp",100)); hp = max(0, min(max_hp, me.get("hp",100)))
    draw_bar(x, y, int(220*s), int(16*s), hp/max_hp, (200,60,60))
    screen.blit(font.render(f"HP {int(hp)}/{int(max_hp)}", True, (255,255,255)), (x+6, y-2))
    y2 = y + int(22*s)
    max_mp = max(1, me.get("max_mp",50)); mp = max(0, min(max_mp, me.get("mp",50)))
    draw_bar(x, y2, int(220*s), int(16*s), mp/max_mp, (60,120,200))
    screen.blit(font.render(f"MP {int(mp)}/{int(max_mp)}", True, (255,255,255)), (x+6, y2-2))
        # XP bar (separate strip)
    xp = int((players.get(str(your_id)) or {}).get("xp",0)); need = int((players.get(str(your_id)) or {}).get("next_xp",100)) or 1
    xp_w = 300
    xp_x = 16
    xp_y = HEIGHT - 22
    pygame.draw.rect(screen, (18,18,24), (xp_x, xp_y, xp_w, 12))
    fill_w = int((xp_w-2)*min(1.0, xp/need))
    pygame.draw.rect(screen, (180,120,40), (xp_x+1, xp_y+1, fill_w, 10))
    # texte à l'intérieur de la barre XP
    txt = font.render(f"XP {xp}/{need}", True, (20,20,20))
    screen.blit(txt, (xp_x + 6, xp_y + 1))
    pts = int(me.get("stat_points", 0) or 0)
    if pts > 0:
        t = font.render(f"Points: {pts} (P)", True, (230, 200, 120))
        screen.blit(t, (x, y - int(18*s)))

def draw_stats():
    me = players.get(str(your_id))
    if not me: return
    pts = int(me.get("stat_points", 0) or 0)
    stats = me.get("stats", {}) or {}
    w, h = 360, 220
    x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
    pygame.draw.rect(screen, (14,14,18), (x,y,w,h))
    pygame.draw.rect(screen, (120,120,140), (x,y,w,h), 2)
    screen.blit(bigfont.render("Attributs", True, (255,255,255)), (x+12,y+10))
    screen.blit(font.render("P: fermer • Entrée: +1 • ↑/↓: sélectionner • 1-4: STR/INT/AGI/STA", True, (200,200,200)), (x+12,y+36))
    screen.blit(font.render(f"Points disponibles: {pts}", True, (230,200,120)), (x+12,y+60))
    labels = [("str","Force"),("int","Intelligence"),("agi","Agilité"),("sta","Endurance")]
    yy = y+88
    for i,(k,label) in enumerate(labels):
        val = int(stats.get(k,0) or 0)
        sel = (i == stats_index)
        txt = f"> {label}: {val}" if sel else f"  {label}: {val}"
        col = (255,255,255) if sel else (210,210,210)
        screen.blit(font.render(txt, True, col), (x+20, yy)); yy += 26

def draw_spellbar():
    s = hud_scale_val()
    if s == 0: return
    x, y = 16, HEIGHT - int(110*s)
    w, h = int(240*s), int(34*s)
    pygame.draw.rect(screen, (18,18,20), (x, y, w, h))
    pygame.draw.rect(screen, (90,90,100), (x, y, w, h), 2)
    slot_w = w//4
    for i in range(4):
        sx = x + i*slot_w
        pygame.draw.rect(screen, (60,60,70), (sx+4, y+4, slot_w-8, h-8), 2)
        lbl = (KEYS.get(f"spell_{i+1}","K_?")).replace("K_","").upper()
        sp = SPELLS.get(str(i+1)) or {}
        screen.blit(font.render(lbl, True, (200,200,200)), (sx+6, y+6))
        nm = sp.get("name", f"Sort {i+1}")
        screen.blit(font.render(nm.split()[0], True, (220,220,220)), (sx+6, y+16))

def draw_chat():
    s = hud_scale_val()*0.85
    if s == 0: return
    x, y, w, h = 16, 16, int(440*s), int(150*s)
    pygame.draw.rect(screen, (15,15,17), (x, y, w, h))
    pygame.draw.rect(screen, (90,90,100), (x, y, w, h), 2)
    lines = chat_log[-max(3, int(7*s)):]
    yy = y+8
    for author, msg in lines:
        col = (255, 200, 100) if author == "SYSTEM" else (230,230,230)
        t = font.render(f"{author}: {msg}", True, col)
        screen.blit(t, (x+8, yy)); yy += int(20*s)
    y2 = y + h + 6
    if chat_typing:
        pygame.draw.rect(screen, (15,15,17), (x, y2, w, int(26*s)))
        pygame.draw.rect(screen, (120,120,130), (x, y2, w, int(26*s)), 2)
        t = font.render("> " + chat_buffer, True, (255,255,255)); screen.blit(t, (x+6, y2+4))
    else:
        hint = font.render("Entrée: chat | F1: HUD | F10/Échap: Options | 1–4: Sorts (viser à la souris) | C: équipement | E: ramasser | I: inventaire", True, (200,200,200))
        screen.blit(hint, (x, y2+4))

def draw_worldmap_overlay():
    # grande carte stylisée (simple heatmap des tuiles autour du joueur)
    w, h = 520, 360
    x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
    surf = pygame.Surface((w, h))
    surf.set_alpha(220)
    surf.fill((22,20,18))
    pygame.draw.rect(surf, (150,140,120), (0,0,w,h), 2)
    me = players.get(str(your_id)) or {}
    if me:
        scale = 3
        me_tx = int(me.get('x',0)//TILE)
        me_ty = int(me.get('y',0)//TILE)
        halfx = (w//scale)//2
        halfy = (h//scale)//2
        for ty in range(me_ty-halfy, me_ty+halfy):
            for tx in range(me_tx-halfx, me_tx+halfx):
                t = get_tile(tx, ty)
                px = (tx - (me_tx-halfx)) * scale
                py = (ty - (me_ty-halfy)) * scale
                col = (40,70,40) if t==0 else (90,90,100) if t==1 else (40,70,120) if t==2 else (160,140,100) if t==3 else (120,120,128)
                pygame.draw.rect(surf, col, (px, py, scale, scale))
        pygame.draw.circle(surf, (240,220,120), (w//2, h//2), 4)
    screen.blit(surf, (x,y))

# ---- Menu Options / Rebind ----
OPTIONS_OPEN = False
REBINDS = list(DEFAULT_KEYS.keys())
rebind_index = 0
waiting_bind = False
STATS_OPEN = False
stats_index = 0
WORLDMAP_OPEN = False
def toggle_hud():
    global HUD_SCALE
    HUD_SCALE = {"large":"medium","medium":"hidden","hidden":"large"}.get(HUD_SCALE,"medium")
    save_config()

def draw_options():
    w, h = 540, 460
    x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
    pygame.draw.rect(screen, (12,12,16), (x,y,w,h))
    pygame.draw.rect(screen, (120,120,140), (x,y,w,h), 2)
    screen.blit(bigfont.render("Options — Rebind touches", True, (255,255,255)), (x+12,y+12))
    screen.blit(font.render("↑/↓ sélectionner • Entrée rebinder • F10/Echap fermer • F1 HUD", True, (220,220,220)), (x+12,y+40))
    list_y = y+70; line_h = 24
    for i, act in enumerate(REBINDS):
        keyname = KEYS.get(act,"")
        label = f"{act}: {keyname}"
        col = (255,255,255) if i == rebind_index else (210,210,210)
        if waiting_bind and i == rebind_index:
            label = f"> Appuyez sur une touche pour: {act}"
            col = (120,220,120)
        screen.blit(font.render(label, True, col), (x+20, list_y+i*line_h))

# ---- Sorts (client : envoi) ----
def try_cast(slot, mouse_pos):
    # visée monde: click écran -> coordonnées monde
    mx, my = mouse_pos
    tx = mx + cam_x
    ty = my + cam_y
    send_json(sock, {"type":"cast","slot":slot,"tx":tx,"ty":ty})


def draw_equip_panel():
    if not EQUIP_UI.get("open"): return
    me = players.get(str(your_id)) or {}
    eq = me.get("equipment", {})
    w, h = 360, 300
    x, y = WIDTH - w - 16, HEIGHT - h - 16
    pygame.draw.rect(screen, (18,18,20), (x, y, w, h))
    pygame.draw.rect(screen, (200,200,220), (x, y, w, h), 2)
    title = bigfont.render("Équipement (C)", True, (255,255,255))
    screen.blit(title, (x+10, y+8))
    slots = ["head","neck","chest","legs","boots","ring1","ring2","weapon","offhand"]
    global slot_rects; slot_rects = {}
    bx, by = x+12, y+40
    for i, sl in enumerate(slots):
        rx = bx + (i%2)*175
        ry = by + (i//2)*56
        rect = pygame.Rect(rx, ry, 165, 48)
        slot_rects[sl] = rect
        pygame.draw.rect(screen, (34,34,48), rect)
        pygame.draw.rect(screen, (110,110,140), rect, 1)
        screen.blit(font.render(sl.upper(), True, (210,210,230)), (rx+6, ry+4))
        it = (eq or {}).get(sl)
        if it:
            name = str(it.get("name","?"))
            screen.blit(font.render(name[:22], True, (240,240,255)), (rx+6, ry+24))
        # interaction drag&drop basique depuis inventaire sélectionné
    # stats cumulées
    stats = (players.get(str(your_id)) or {}).get("stats", {})
    gear = (players.get(str(your_id)) or {}).get("_gear_bonus_stats", stats)
    pygame.draw.rect(screen, (24,24,28), (x+12, y+h-44, w-24, 28))
    pygame.draw.rect(screen, (90,90,110), (x+12, y+h-44, w-24, 28), 1)
    s_txt = f"STR {gear.get('str',0)}  INT {gear.get('int',0)}  AGI {gear.get('agi',0)}  STA {gear.get('sta',0)}"
    screen.blit(font.render(s_txt, True, (220,220,230)), (x+18, y+h-38))
    # drag depuis inventaire vers slot (si inventaire ouvert)

# ---- Connexion & boucle ----
running = True
while running:
    # lock 60 FPS
    dt = clock.tick(60)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            # UI: Login
            if UI_STATE == "login":
                if event.key == pygame.K_TAB:
                    login_focus = "pass" if login_focus == "user" else "user"
                elif event.key == pygame.K_F2:
                    login_mode = "register" if login_mode == "login" else "login"
                elif event.key == pygame.K_BACKSPACE:
                    if login_focus == "user":
                        login_username = login_username[:-1]
                    else:
                        login_password = login_password[:-1]
                elif event.key == pygame.K_RETURN:
                    if login_mode == "login":
                        send_json(sock, {"type":"login","username":login_username.strip(),"password":login_password})
                        login_msg = "Connexion..."
                    else:
                        send_json(sock, {"type":"register","username":login_username.strip(),"password":login_password})
                        login_msg = "Création..."
                else:
                    ch = event.unicode
                    if ch and 32 <= ord(ch) <= 126:
                        if login_focus == "user": login_username += ch
                        else: login_password += ch
                continue

            # UI: Sélection
            # UI: Sélection
            if UI_STATE == "select":
                if event.key == pygame.K_r:
                    send_json(sock, {"type":"request_characters"})
                elif event.key == pygame.K_c:
                    create_name = ""; create_class_idx = 0; create_msg = ""
                    UI_STATE = "create"
                elif event.key == pygame.K_UP:
                    if char_list:
                        char_sel = (char_sel - 1) % len(char_list)
                elif event.key == pygame.K_DOWN:
                    if char_list:
                        char_sel = (char_sel + 1) % len(char_list)
                elif event.key == pygame.K_RETURN:
                    if 0 <= char_sel < len(char_list):
                        send_json(sock, {"type":"enter_world","char_id": str(char_list[char_sel]["id"])})
                        char_msg = "Entrée en cours..."
                continue


            # UI: Création de personnage
            if UI_STATE == "create":
                if event.key == pygame.K_ESCAPE:
                    UI_STATE = "select"
                elif event.key == pygame.K_LEFT:
                    create_class_idx = (create_class_idx - 1) % len(CLASSES)
                elif event.key == pygame.K_RIGHT:
                    create_class_idx = (create_class_idx + 1) % len(CLASSES)
                elif event.key == pygame.K_BACKSPACE:
                    create_name = create_name[:-1]
                elif event.key == pygame.K_RETURN:
                    nm = (create_name.strip() or "Héros")
                    send_json(sock, {"type":"create_character","name": nm, "class": CLASSES[create_class_idx]})
                    create_msg = "Création..."
                else:
                    ch = event.unicode
                    if ch and 32 <= ord(ch) <= 126:
                        create_name += ch
                continue

            # En jeu: options et commandes
            if key_is(event.key, "options") or event.key == pygame.K_ESCAPE:
                if OPTIONS_OPEN and waiting_bind:
                    waiting_bind = False
                else:
                    OPTIONS_OPEN = not OPTIONS_OPEN
                continue
            if key_is(event.key, "hud_toggle"):
                toggle_hud(); continue

            # Équipement panel
            if key_is(event.key, "equipment"):
                EQUIP_UI["open"] = not EQUIP_UI.get("open")
                continue
            # Carte monde
            if key_is(event.key, "map"):
                WORLDMAP_OPEN = not WORLDMAP_OPEN
                continue

            # Ouvrir/fermer la fenêtre d'attributs
            if key_is(event.key, "stats"):
                STATS_OPEN = not STATS_OPEN
                continue

            if OPTIONS_OPEN:
                if not waiting_bind:
                    if event.key == pygame.K_UP:
                        rebind_index = (rebind_index - 1) % len(REBINDS)
                    elif event.key == pygame.K_DOWN:
                        rebind_index = (rebind_index + 1) % len(REBINDS)
                    elif event.key == pygame.K_RETURN:
                        waiting_bind = True
                else:
                    key_name = [k for k in dir(pygame) if getattr(pygame,k,None)==event.key and k.startswith("K_")]
                    if key_name:
                        KEYS[REBINDS[rebind_index]] = key_name[0]
                        save_config()
                    waiting_bind = False
                continue

            # CHAT (désactivé si fenêtre stats ouverte)
            if chat_typing and not STATS_OPEN:
                if key_is(event.key, "chat"):
                    if chat_buffer.strip(): send_json(sock, {"type":"chat","msg":chat_buffer})
                    chat_buffer = ""; chat_typing = False
                elif event.key == pygame.K_ESCAPE:
                    chat_buffer = ""; chat_typing = False
                elif event.key == pygame.K_BACKSPACE:
                    chat_buffer = chat_buffer[:-1]
                else:
                    ch = event.unicode
                    if ch and 32 <= ord(ch) <= 126: chat_buffer += ch
                continue
            else:
                if key_is(event.key, "chat") and not STATS_OPEN:
                    chat_typing = True; chat_buffer = ""; continue

            # Stats allocation
            if STATS_OPEN:
                if event.key == pygame.K_UP:
                    stats_index = (stats_index - 1) % 4
                elif event.key == pygame.K_DOWN:
                    stats_index = (stats_index + 1) % 4
                elif event.key == pygame.K_RETURN:
                    stat_key = ["str","int","agi","sta"][stats_index]
                    send_json(sock, {"type":"allocate_stat","stat": stat_key})
                elif event.key in (pygame.K_1, pygame.K_KP1):
                    send_json(sock, {"type":"allocate_stat","stat": "str"})
                elif event.key in (pygame.K_2, pygame.K_KP2):
                    send_json(sock, {"type":"allocate_stat","stat": "int"})
                elif event.key in (pygame.K_3, pygame.K_KP3):
                    send_json(sock, {"type":"allocate_stat","stat": "agi"})
                elif event.key in (pygame.K_4, pygame.K_KP4):
                    send_json(sock, {"type":"allocate_stat","stat": "sta"})
                continue

            # INVENTAIRE / ACTIONS
            if key_is(event.key, "inventory"):
                inv_open = not inv_open
                if inv_open: send_json(sock, {"type":"request_inventory"})
            elif key_is(event.key, "pickup"):
                send_json(sock, {"type":"pickup"})
            elif inv_open and event.key in (pygame.K_UP, pygame.K_DOWN):
                if len(inventory) > 0:
                    inv_sel = (inv_sel - 1) % len(inventory) if event.key == pygame.K_UP else (inv_sel + 1) % len(inventory)
            elif inv_open and key_is(event.key, "drop"):
                if 0 <= inv_sel < len(inventory):
                    obj = inventory[inv_sel]
                    send_json(sock, {"type":"drop", "id": obj.get("id"), "dx": 0, "dy": 24})
            elif inv_open and key_is(event.key, "use"):
                if 0 <= inv_sel < len(inventory):
                    obj = inventory[inv_sel]
                    send_json(sock, {"type":"use_item", "id": obj.get("id")})

            # SORTS (viser à la souris)
            elif key_is(event.key, "spell_1"): try_cast(1, pygame.mouse.get_pos())
            elif key_is(event.key, "spell_2"): try_cast(2, pygame.mouse.get_pos())
            elif key_is(event.key, "spell_3"): try_cast(3, pygame.mouse.get_pos())
            elif key_is(event.key, "spell_4"): try_cast(4, pygame.mouse.get_pos())
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and inv_open and EQUIP_UI.get("open"):
            # drag depuis inventaire vers slot
            if 0 <= inv_sel < len(inventory):
                drag_item_id = inventory[inv_sel].get("id")
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drag_item_id and EQUIP_UI.get("open"):
            mx, my = event.pos
            target_slot = None
            for sl, r in slot_rects.items():
                if r.collidepoint(mx, my):
                    target_slot = sl; break
            if target_slot is not None:
                send_json(sock, {"type":"equip_item", "id": drag_item_id, "slot": target_slot})
            drag_item_id = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and EQUIP_UI.get("open"):
            # tooltip affiché 2s
            mx, my = event.pos
            for sl, r in slot_rects.items():
                if r.collidepoint(mx, my):
                    it = (players.get(str(your_id), {}).get("equipment", {}) or {}).get(sl)
                    if it:
                        tooltip["txt"] = f"{it.get('name','?')} [{it.get('type','?')}] +{it.get('power',0)}"
                        tooltip["until"] = time.time() + 2.0
                        tooltip["pos"] = (mx, my)
                        break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and EQUIP_UI.get("open"):
            # drag inversé: slot -> inventaire (déséquiper)
            mx, my = event.pos
            for sl, r in slot_rects.items():
                if r.collidepoint(mx, my):
                    send_json(sock, {"type":"unequip_slot", "slot": sl})
                    break

    # Déplacements (si en jeu et pas en menus / chat)
    if UI_STATE == "game" and (not chat_typing) and (not OPTIONS_OPEN):
        dx = dy = 0
        if pressed("move_left"):  dx -= SPEED
        if pressed("move_right"): dx += SPEED
        if pressed("move_up"):    dy -= SPEED
        if pressed("move_down"):  dy += SPEED
        if dx or dy: send_json(sock, {"type":"move", "dx": dx, "dy": dy})

    # Rendu
    screen.fill((20, 20, 22))
    if UI_STATE == "game":
        # caméra centrée sur le joueur
        me = players.get(str(your_id))
        if me:
            cam_x = me.get("x",0) - WIDTH//2
            cam_y = me.get("y",0) - HEIGHT//2
        draw_tilemap()
        # mini‑map en overlay (haut‑droit)
        mm_size = 180
        mm = pygame.Surface((mm_size, mm_size))
        mm.set_alpha(200)
        mm.fill((12,12,16))
        # échelle mini‑map: 1 px = 4 tiles
        scale = 4
        me_tx = int((me.get("x",0))//TILE)
        me_ty = int((me.get("y",0))//TILE)
        half = mm_size//(2*scale)
        for ty in range(me_ty-half, me_ty+half):
            for tx in range(me_tx-half, me_tx+half):
                t = get_tile(tx, ty)
                px = (tx - (me_tx-half)) * scale
                py = (ty - (me_ty-half)) * scale
                col = (40,70,40) if t==0 else (90,90,100) if t==1 else (40,70,120) if t==2 else (160,140,100) if t==3 else (120,120,128)
                pygame.draw.rect(mm, col, (px, py, scale, scale))
        # joueur
        pygame.draw.circle(mm, (240,220,120), (mm_size//2, mm_size//2), 3)
        screen.blit(mm, (WIDTH - mm_size - 14, 14))
        # FX légers
        now_t = time.time()
        for f in list(FX):
            if now_t >= f.get("until",0):
                FX.remove(f); continue
            if f.get("fx") == "cast":
                sx, sy = world_to_screen(f.get("x",0), f.get("y",0))
                pygame.draw.circle(screen, (220,200,120), (int(sx), int(sy)), 10, 2)

        # Items
        for it in list(items.values()):
            sx, sy = world_to_screen(it.get("x",0), it.get("y",0))
            sprite_item(it.get("type","?"), sx, sy)

        # Projectiles (lissage) + FX pour tous les sorts
        for id_, pr in list(projs.items()):
            tx, ty = float(pr.get("x",0)), float(pr.get("y",0))
            # si le joueur est immobile, utiliser directement la position réseau
            is_me_idle = not (pressed("move_left") or pressed("move_right") or pressed("move_up") or pressed("move_down"))
            rx, ry = (tx, ty) if is_me_idle else smooth_to(render_pos_projs, id_, tx, ty, 0.6)
            sx, sy = world_to_screen(rx, ry)
            col = (240,120,60)
            spd = math.hypot(pr.get('vx',0), pr.get('vy',0))
            # couleur par vitesse pour donner une variété visuelle
            if spd > 6: col = (255,170,70)
            for k in range(1,4):
                pygame.draw.circle(screen, (col[0]//2, col[1]//2, col[2]//2), (int(sx - pr.get('vx',0)*k*0.6), int(sy - pr.get('vy',0)*k*0.6)), max(1, 5-k))
            pygame.draw.circle(screen, col, (int(sx), int(sy)), 5)

        # PNJ
        for nid, info in list(npcs.items()):
            draw_npc(nid, info)

        # Joueurs
        for pid, info in list(players.items()):
            draw_player(pid, info)

        # UI
        if inv_open: draw_inventory()
        draw_hud()
        draw_spellbar()
        draw_chat()
        if OPTIONS_OPEN: draw_options()
        if STATS_OPEN: draw_stats()
        draw_equip_panel()
        if WORLDMAP_OPEN: draw_worldmap_overlay()
    elif UI_STATE == "login":
        # Panneau Login/Register
        w, h = 480, 300
        x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
        pygame.draw.rect(screen, (16,16,20), (x,y,w,h))
        pygame.draw.rect(screen, (120,120,140), (x,y,w,h), 2)
        title = f"Connexion" if login_mode=="login" else "Inscription"
        screen.blit(bigfont.render(title, True, (255,255,255)), (x+16,y+12))
        screen.blit(font.render("F2: basculer Connexion/Inscription", True, (200,200,200)), (x+16,y+42))
        # Username
        pygame.draw.rect(screen, (28,28,34), (x+16, y+76, w-32, 32))
        pygame.draw.rect(screen, (160,160,180), (x+16, y+76, w-32, 32), 2 if login_focus=="user" else 1)
        screen.blit(font.render("Utilisateur:", True, (220,220,220)), (x+20, y+56))
        screen.blit(bigfont.render(login_username or "", True, (255,255,255)), (x+24, y+82))
        # Password
        pygame.draw.rect(screen, (28,28,34), (x+16, y+144, w-32, 32))
        pygame.draw.rect(screen, (160,160,180), (x+16, y+144, w-32, 32), 2 if login_focus=="pass" else 1)
        screen.blit(font.render("Mot de passe:", True, (220,220,220)), (x+20, y+124))
        dots = "*" * len(login_password)
        screen.blit(bigfont.render(dots, True, (255,255,255)), (x+24, y+150))
        # Hint & Msg
        screen.blit(font.render("Entrée: valider • Tab: changer champ • F2: basculer", True, (200,200,200)), (x+16, y+h-48))
        if login_msg:
            screen.blit(font.render(login_msg, True, (240,200,120)), (x+16, y+h-28))
    elif UI_STATE == "select":
        w, h = 560, 380
        x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
        pygame.draw.rect(screen, (16,16,20), (x,y,w,h))
        pygame.draw.rect(screen, (120,120,140), (x,y,w,h), 2)
        screen.blit(bigfont.render("Sélection du personnage", True, (255,255,255)), (x+16,y+12))
        screen.blit(font.render("↑/↓ sélectionner • Entrée: jouer • C: créer • R: rafraîchir", True, (200,200,200)), (x+16,y+40))
        list_y = y+76
        for i, ch in enumerate(char_list):
            sel = (i == char_sel)
            name = ch.get("name","?"); cls = ch.get("class","?"); lvl = ch.get("level",1)
            label = f"> {name}  [{cls}]  niv {lvl}" if sel else f"  {name}  [{cls}]  niv {lvl}"
            col = (255,255,255) if sel else (210,210,210)
            screen.blit(font.render(label, True, col), (x+24, list_y + i*26))
        if not char_list:
            screen.blit(font.render("Aucun personnage. Appuyez sur C pour créer.", True, (220,180,120)), (x+24, list_y))
        if char_msg:
            screen.blit(font.render(char_msg, True, (240,200,120)), (x+16, y+h-28))
    elif UI_STATE == "create":
        w, h = 560, 320
        x, y = WIDTH//2 - w//2, HEIGHT//2 - h//2
        pygame.draw.rect(screen, (16,16,20), (x,y,w,h))
        pygame.draw.rect(screen, (120,120,140), (x,y,w,h), 2)
        screen.blit(bigfont.render("Création de personnage", True, (255,255,255)), (x+16,y+12))
        screen.blit(font.render("Nom (écrire) • Classe (←/→) • Entrée: créer • Échap: retour", True, (200,200,200)), (x+16,y+40))
        screen.blit(font.render("Nom:", True, (220,220,220)), (x+20, y+84))
        pygame.draw.rect(screen, (28,28,34), (x+90, y+80, w-110, 32))
        pygame.draw.rect(screen, (160,160,180), (x+90, y+80, w-110, 32), 1)
        screen.blit(bigfont.render(create_name or "", True, (255,255,255)), (x+96, y+86))
        screen.blit(font.render("Classe:", True, (220,220,220)), (x+20, y+140))
        cls = CLASSES[create_class_idx]
        screen.blit(bigfont.render(f"← {cls} →", True, (230,230,230)), (x+100, y+140))
        if create_msg:
            screen.blit(font.render(create_msg, True, (240,200,120)), (x+16, y+h-28))

    pygame.display.flip()
    # tooltip render
    if tooltip.get("txt") and time.time() < tooltip.get("until",0):
        tx, ty = tooltip.get("pos", (0,0))
        label = font.render(tooltip["txt"], True, (255,255,255))
        bg = pygame.Surface((label.get_width()+8, label.get_height()+6))
        bg.set_alpha(180)
        bg.fill((20,20,24))
        screen.blit(bg, (tx+12, ty+12))
        screen.blit(label, (tx+16, ty+14))

pygame.quit()
try: sock.close()
except: pass