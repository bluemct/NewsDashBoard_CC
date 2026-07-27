"""
Xiangqi (中国象棋) — Python + tkinter

- 双人对战 / 人机对战 (新手 / 大师)
- 10 行 × 9 列棋盘
- 零外部依赖

Usage:  python xiangqi.py
"""
import copy
import random
import tkinter as tk
from tkinter import messagebox

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLS = 9
ROWS = 10
CELL = 56
MARGIN = 40
PIECE_R = 24
BOARD_W = MARGIN * 2 + CELL * (COLS - 1)
BOARD_H = MARGIN * 2 + CELL * (ROWS - 1)

RED    = 1
BLACK = -1

# Piece types (1-7)
KING      = 1
ADVISOR   = 2
ELEPHANT  = 3
KNIGHT    = 4
CHARIOT   = 5
CANNON    = 6
SOLDIER   = 7

PIECE_CHARS = {
    ( 1, 1): "帅", (-1, 1): "将",
    ( 1, 2): "仕", (-1, 2): "士",
    ( 1, 3): "相", (-1, 3): "象",
    ( 1, 4): "傌", (-1, 4): "马",
    ( 1, 5): "俥", (-1, 5): "车",
    ( 1, 6): "炮", (-1, 6): "砲",
    ( 1, 7): "兵", (-1, 7): "卒",
}

PIECE_VALUES = {
    1: 100000,   # King (practical infinity)
    2: 20,
    3: 20,
    4: 40,
    5: 90,
    6: 45,
    7: 10,
}

# Colour styling for pieces
RED_STYLES  = {"fill": "#FCEEE9", "outline": "#C62828", "text": "#C62828"}
BLACK_STYLES = {"fill": "#F5F5EC", "outline": "#263238", "text": "#263238"}
BOARD_BG   = "#E8C99B"
LINE_COLOR = "#4E342E"

# ---------------------------------------------------------------------------
# Initial board
# ---------------------------------------------------------------------------
INITIAL_BOARD = [
    [-5, -4, -3, -2, -1, -2, -3, -4, -5],  # 0
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],  # 1
    [ 0, -6,  0,  0,  0,  0,  0, -6,  0],  # 2
    [-7,  0, -7,  0, -7,  0, -7,  0, -7],  # 3
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],  # 4
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],  # 5
    [ 7,  0,  7,  0,  7,  0,  7,  0,  7],  # 6
    [ 0,  6,  0,  0,  0,  0,  0,  6,  0],  # 7
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0],  # 8
    [ 5,  4,  3,  2,  1,  2,  3,  4,  5],  # 9
]

# ---------------------------------------------------------------------------
# Move generation — pseudo-legal (no check filtering yet)
# Each returns a list of (fr, fc, tr, tc)
# ---------------------------------------------------------------------------

def _in_bounds(r, c):
    return 0 <= r < ROWS and 0 <= c < COLS

def _is_own(board, r, c, color):
    p = board[r][c]
    return p != 0 and ((p > 0) == (color > 0))

def _is_enemy(board, r, c, color):
    p = board[r][c]
    return p != 0 and ((p > 0) != (color > 0))

# ---- KING -----------------------------------------------------------------
def king_pseudo(board, r, c):
    color = RED if board[r][c] > 0 else BLACK
    rows = range(7, 10) if color == RED else range(0, 3)
    cols = range(3, 6)
    moves = []
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        nr, nc = r + dr, c + dc
        if nr in rows and nc in cols and not _is_own(board, nr, nc, color):
            moves.append((r, c, nr, nc))
    return moves

# ---- ADVISOR --------------------------------------------------------------
def advisor_pseudo(board, r, c):
    color = RED if board[r][c] > 0 else BLACK
    rows = range(7, 10) if color == RED else range(0, 3)
    cols = range(3, 6)
    moves = []
    for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
        nr, nc = r + dr, c + dc
        if nr in rows and nc in cols and not _is_own(board, nr, nc, color):
            moves.append((r, c, nr, nc))
    return moves

# ---- ELEPHANT -------------------------------------------------------------
def elephant_pseudo(board, r, c):
    color = RED if board[r][c] > 0 else BLACK
    moves = []
    for dr, dc in [(-2,-2),(-2,2),(2,-2),(2,2)]:
        nr, nc = r + dr, c + dc
        er, ec = r + dr // 2, c + dc // 2  # eye
        if not _in_bounds(nr, nc):
            continue
        if color == RED and nr < 5:   # cannot cross river
            continue
        if color == BLACK and nr > 4:
            continue
        if board[er][ec] != 0:       # eye blocked
            continue
        if not _is_own(board, nr, nc, color):
            moves.append((r, c, nr, nc))
    return moves

# ---- KNIGHT ---------------------------------------------------------------
def knight_pseudo(board, r, c):
    offsets = [
        (-2, -1, -1, 0), (-2,  1, -1, 0),
        ( 2, -1,  1, 0), ( 2,  1,  1, 0),
        (-1, -2,  0,-1), (-1,  2,  0, 1),
        ( 1, -2,  0,-1), ( 1,  2,  0, 1),
    ]
    moves = []
    color = RED if board[r][c] > 0 else BLACK
    for dr, dc, br, bc in offsets:
        nr, nc = r + dr, c + dc
        if not _in_bounds(nr, nc):
            continue
        if board[r + br][c + bc] != 0:  # leg pinned
            continue
        if not _is_own(board, nr, nc, color):
            moves.append((r, c, nr, nc))
    return moves

# ---- CHARITOT -------------------------------------------------------------
def chariot_pseudo(board, r, c):
    moves = []
    color = RED if board[r][c] > 0 else BLACK
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        nr, nc = r + dr, c + dc
        while _in_bounds(nr, nc):
            if board[nr][nc] == 0:
                moves.append((r, c, nr, nc))
            elif _is_enemy(board, nr, nc, color):
                moves.append((r, c, nr, nc))
                break
            else:
                break
            nr += dr
            nc += dc
    return moves

# ---- CANNON ---------------------------------------------------------------
def cannon_pseudo(board, r, c):
    moves = []
    color = RED if board[r][c] > 0 else BLACK
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        nr, nc = r + dr, c + dc
        screen = False
        while _in_bounds(nr, nc):
            if not screen:
                if board[nr][nc] == 0:
                    moves.append((r, c, nr, nc))
                else:
                    screen = True
            else:
                if board[nr][nc] != 0:
                    if _is_enemy(board, nr, nc, color):
                        moves.append((r, c, nr, nc))
                    break
            nr += dr
            nc += dc
    return moves

# ---- SOLDIER --------------------------------------------------------------
def soldier_pseudo(board, r, c):
    color = RED if board[r][c] > 0 else BLACK
    moves = []
    if color == RED:
        forward = -1
        crossed = r <= 4
    else:
        forward = 1
        crossed = r >= 5
    nr = r + forward
    if _in_bounds(nr, c) and not _is_own(board, nr, c, color):
        moves.append((r, c, nr, c))
    if crossed:
        for dc in [-1, 1]:
            nc = c + dc
            if _in_bounds(r, nc) and not _is_own(board, r, nc, color):
                moves.append((r, c, r, nc))
    return moves

# ---------------------------------------------------------------------------
# Generators dispatch
# ---------------------------------------------------------------------------
_PSEUDO_FUNCS = {
    KING:     king_pseudo,
    ADVISOR:  advisor_pseudo,
    ELEPHANT: elephant_pseudo,
    KNIGHT:   knight_pseudo,
    CHARITOT: chariot_pseudo,
    CANNON:   cannon_pseudo,
    SOLDIER:  soldier_pseudo,
}

def all_pseudo(board, color):
    """Generate all pseudo-legal moves for *color*."""
    moves = []
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if p == 0:
                continue
            if (p > 0) != (color > 0):
                continue
            moves.extend(_PSEUDO_FUNCS[abs(p)](board, r, c))
    return moves

# ---------------------------------------------------------------------------
# Generals-facing rule
# ---------------------------------------------------------------------------
def generals_face(board):
    rk = bk = None
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] == RED:
                rk = (r, c)
            elif board[r][c] == BLACK:
                bk = (r, c)
    if rk is None or bk is None:
        return False
    if rk[1] != bk[1]:
        return False
    for r in range(min(rk[0], bk[0]) + 1, max(rk[0], bk[0])):
        if board[r][rk[1]] != 0:
            return False
    return True

# ---------------------------------------------------------------------------
# Check detection
# ---------------------------------------------------------------------------
def find_king(board, color):
    target = RED if color == RED else BLACK
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] == target:
                return r, c
    return None

def is_in_check(board, color):
    """Is *color*'s king under attack?"""
    kr, kc = find_king(board, color)
    if kr is None:
        return False
    enemy = -color
    for m in all_pseudo(board, enemy):
        if m[2] == kr and m[3] == kc:
            return True
    return False

# ---------------------------------------------------------------------------
# Legal moves (filtered)
# ---------------------------------------------------------------------------
def legal_moves(board, color):
    legal = []
    for m in all_pseudo(board, color):
        fr, fc, tr, tc = m
        cap = board[tr][tc]
        piece = board[fr][fc]
        board[tr][tc] = piece
        board[fr][fc] = 0
        if not is_in_check(board, color) and not generals_face(board):
            legal.append(m)
        board[fr][fc] = piece
        board[tr][tc] = cap
    return legal

# ---------------------------------------------------------------------------
# Game class
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        self.board = [row[:] for row in INITIAL_BOARD]
        self.current = RED
        self.history = []  # list of (fr, fc, tr, tc, captured)
        self.winner = None

    def make_move(self, fr, fc, tr, tc):
        cap = self.board[tr][tc]
        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = 0
        self.history.append((fr, fc, tr, tc, cap))
        self.current = -self.current
        return cap

    def undo(self):
        if not self.history:
            return
        fr, fc, tr, tc, cap = self.history.pop()
        self.board[fr][fc] = self.board[tr][tc]
        self.board[tr][tc] = cap
        self.current = -self.current

    def game_over(self):
        moves = legal_moves(self.board, self.current)
        if not moves:
            if is_in_check(self.board, self.current):
                self.winner = -self.current
                return "checkmate"
            return "stalemate"
        return None


# ===================================================================
# AI Engine
# ===================================================================

# --- Piece-Square Tables (position bonuses) ---
# Indexed [row][col], row 0 is black side top

SOLDIER_PST = [
    [90, 90, 90, 90, 90, 90, 90, 90, 90],
    [80, 80, 80, 80, 80, 80, 80, 80, 80],
    [70, 70, 70, 70, 70, 70, 70, 70, 70],
    [60, 60, 70, 70, 70, 70, 70, 60, 60],
    [50, 50, 60, 60, 60, 60, 60, 50, 50],
    [25, 25, 25, 25, 30, 25, 25, 25, 25],
    [10, 10, 10, 15, 15, 15, 10, 10, 10],
    [5,  5,  5,  5,  5,  5,  5,  5,  5],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
]

KNIGHT_PST = [
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  5,  5,  5,  5,  5,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
    [0,  0,  0,  0,  0,  0,  0,  0,  0],
]

CHARIOT_PST = [
    [5, 5, 5, 5, 5, 5, 5, 5, 5],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
]

CANNON_PST = [
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 3, 0, 0, 0, 0, 0, 3, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 0],
]

PST_TABLES = {
    SOLDIER: SOLDIER_PST,
    KNIGHT:  KNIGHT_PST,
    CHARITOT: CHARITOT_PST,
    CANNON:  CANNON_PST,
}

def _pst_bonus(r, c, ptype):
    pst = PST_TABLES.get(ptype)
    if pst is None:
        return 0
    return pst[r][c]

def evaluate(board):
    """Positive = Red is ahead.  AI plays BLACK (minimising)."""
    score = 0
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if p == 0:
                continue
            ptype = abs(p)
            val = PIECE_VALUES[ptype] + _pst_bonus(r, c, ptype)
            if p > 0:
                score += val
            else:
                score -= val
    return score

# --- MVV-LVA move ordering ---
def mvv_lva_key(board, move):
    fr, fc, tr, tc = move
    attacker = abs(board[fr][fc])
    victim = abs(board[tr][tc])
    # We want high victim first, low attacker first, non-captures last
    return (-victim, attacker)

# --- Transposition table (for master) ---
_tt = {}
_tt_hits = 0
_tt_stores = 0

def _board_key(board):
    return tuple(tuple(row) for row in board)

def _tt_lookup(key, depth, alpha, beta, maximizing):
    global _tt_hits
    entry = _tt.get(key)
    if entry is None:
        return None
    e_depth, e_score, e_flag = entry
    if e_depth < depth:
        return None
    _tt_hits += 1
    if e_flag == 0:       # exact
        return e_score
    elif e_flag == 1:     # alpha (lower bound)
        if e_score <= alpha:
            return None
        return e_score
    else:                 # beta (upper bound)
        if e_score >= beta:
            return None
        return e_score

def _tt_store(key, depth, score, flag):
    global _tt_stores
    if key not in _tt:
        _tt[key] = (depth, score, flag)
        _tt_stores += 1

def _clear_tt():
    global _tt, _tt_hits, _tt_stores
    _tt.clear()
    _tt_hits = 0
    _tt_stores = 0

# --- Quiescence search ---
def _captures_only(board, color):
    moves = []
    for m in all_pseudo(board, color):
        fr, fc, tr, tc = m
        if board[tr][tc] != 0:
            moves.append(m)
    return moves

def _quiesce(board, alpha, beta, maximizing):
    stand_pat = evaluate(board)
    if maximizing:
        if stand_pat >= beta:
            return beta
        alpha = max(alpha, stand_pat)
        color = RED
    else:
        if stand_pat <= alpha:
            return alpha
        beta = min(beta, stand_pat)
        color = BLACK
    for m in _captures_only(board, color):
        fr, fc, tr, tc = m
        cap = board[tr][tc]
        piece = board[fr][fc]
        board[tr][tc] = piece
        board[fr][fc] = 0
        score = -_quiesce(board, -beta, -alpha, not maximizing)
        board[fr][fc] = piece
        board[tr][tc] = cap
        if maximizing:
            alpha = max(alpha, score)
        else:
            beta = min(beta, score)
        if beta <= alpha:
            break
    return alpha if maximizing else beta

# --- Minimax with alpha-beta ---
def _minimax(board, depth, alpha, beta, maximizing, use_tt):
    color = RED if maximizing else BLACK
    bk = _board_key(board) if use_tt else None

    if use_tt and bk:
        tt_score = _tt_lookup(bk, depth, alpha, beta, maximizing)
        if tt_score is not None:
            return tt_score

    if depth == 0:
        return _quiesce(board, alpha, beta, maximizing)

    moves = legal_moves(board, color)
    if not moves:
        if is_in_check(board, color):
            return -99999 + (10 - depth) if maximizing else 99999 - (10 - depth)
        return 0

    if maximizing:
        moves.sort(key=lambda m: mvv_lva_key(board, m))
        best = -999999
        for m in moves:
            fr, fc, tr, tc = m
            cap = board[tr][tc]
            piece = board[fr][fc]
            board[tr][tc] = piece
            board[fr][fc] = 0
            score = -_minimax(board, depth - 1, -beta, -alpha, False, use_tt)
            board[fr][fc] = piece
            board[tr][tc] = cap
            if score > best:
                best = score
                alpha = max(alpha, score)
            if beta <= alpha:
                break
        if use_tt and bk:
            flag = 0 if best >= beta else 2
            _tt_store(bk, depth, best, flag)
        return best
    else:
        moves.sort(key=lambda m: mvv_lva_key(board, m))
        best = 999999
        for m in moves:
            fr, fc, tr, tc = m
            cap = board[tr][tc]
            piece = board[fr][fc]
            board[tr][tc] = piece
            board[fr][fc] = 0
            score = -_minimax(board, depth - 1, -beta, -alpha, True, use_tt)
            board[fr][fc] = piece
            board[tr][tc] = cap
            if score < best:
                best = score
                beta = min(beta, score)
            if beta <= alpha:
                break
        if use_tt and bk:
            flag = 0 if best <= alpha else 1
            _tt_store(bk, depth, best, flag)
        return best

# --- AI move selection ---
def ai_find_move(board, difficulty):
    """AI plays BLACK (minimising)."""
    _clear_tt()
    depth = 2 if difficulty == "novice" else 4
    use_tt = (difficulty == "master")

    moves = legal_moves(board, BLACK)
    if not moves:
        return None

    if difficulty == "novice":
        random.shuffle(moves)

    # Iterative deepening for master
    if difficulty == "master":
        best_move = None
        for d in range(1, depth + 1):
            moves.sort(key=lambda m: mvv_lva_key(board, m))
            cur_best = 999999
            for m in moves:
                fr, fc, tr, tc = m
                cap = board[tr][tc]
                piece = board[fr][fc]
                board[tr][tc] = piece
                board[fr][fc] = 0
                score = -_minimax(board, d - 1, -999999, 999999, True, use_tt)
                board[fr][fc] = piece
                board[tr][tc] = cap
                if score < cur_best:
                    cur_best = score
                    best_move = m
        return best_move
    else:
        # Novice: single pass depth 2, random shuffle
        cur_best = 999999
        best_moves = []
        for m in moves:
            fr, fc, tr, tc = m
            cap = board[tr][tc]
            piece = board[fr][fc]
            board[tr][tc] = piece
            board[fr][fc] = 0
            score = -_minimax(board, depth - 1, -999999, 999999, True, False)
            board[fr][fc] = piece
            board[tr][tc] = cap
            if score < cur_best:
                cur_best = score
                best_moves = [m]
            elif score == cur_best:
                best_moves.append(m)
        return random.choice(best_moves)


# ===================================================================
# GUI
# ===================================================================
class App:
    MODE_PVP = 0
    MODE_AI  = 1

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("中国象棋")
        self.root.resizable(False, False)
        self.mode = None
        self.difficulty = None
        self.game = None
        self.selected = None       # (r, c)
        self.valid_moves = []
        self.last_move = None
        self.ai_thinking = False
        self._show_menu()
        self.root.mainloop()

    # --------------- menu ---------------
    def _show_menu(self):
        for w in self.root.winfo_children():
            w.destroy()
        w, h = 480, 300
        self.root.geometry(f"{w}x{h}+{self.root.winfo_screenwidth()//2-w//2}+{self.root.winfo_screenheight()//2-h//2}")
        self.root.title("中国象棋")

        tk.Label(self.root, text="中 国 象 棋", font=("SimHei", 36, "bold"), fg="#1a1a2e").pack(pady=36)
        tk.Label(self.root, text="Chinese Chess", font=("Segoe UI", 16), fg="#888").pack(pady=(0, 10))

        f = tk.Frame(self.root)
        f.pack()

        tk.Button(f, text="👥  双人对战", command=self._start_pvp,
                  width=16, height=2, font=("SimHei", 14)).pack(side=tk.LEFT, padx=20, pady=10)

        rf = tk.Frame(f)
        rf.pack(side=tk.LEFT, padx=10)
        tk.Label(rf, text="人机对战", font=("SimHei", 12)).pack()
        bf = tk.Frame(rf)
        bf.pack()
        tk.Button(bf, text="🌱  新手", command=self._start_novice,
                  width=10, font=("SimHei", 12)).pack(side=tk.LEFT, padx=6, pady=6)
        tk.Button(bf, text="👑  大师", command=self._start_master,
                  width=10, font=("SimHei", 12)).pack(side=tk.LEFT, padx=6, pady=6)

    def _start_pvp(self):
        self.mode = self.MODE_PVP
        self.difficulty = None
        self._build_game()

    def _start_novice(self):
        self.mode = self.MODE_AI
        self.difficulty = "novice"
        self._build_game()

    def _start_master(self):
        self.mode = self.MODE_AI
        self.difficulty = "master"
        self._build_game()

    # --------------- game screen ---------------
    def _build_game(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.geometry("")
        self.root.resizable(False, False)

        mode_label = {
            self.MODE_PVP: "双人对战",
            "novice": "人机对战 (新手)",
            "master": "人机对战 (大师)",
        }
        self.root.title(f"中国象棋 — {mode_label.get(self.difficulty, '双人对战')}")

        self.game = Game()
        self.selected = None
        self.valid_moves = []
        self.last_move = None
        self.ai_thinking = False

        # toolbar
        tb = tk.Frame(self.root)
        tb.pack(fill="x", pady=4)
        tk.Button(tb, text="← 菜单", command=self._show_menu).pack(side=tk.LEFT, padx=6)
        tk.Button(tb, text="新游戏", command=self._new_game).pack(side=tk.LEFT, padx=6)
        tk.Button(tb, text="悔棋", command=self._undo).pack(side=tk.LEFT, padx=6)
        self.lbl_status = tk.Label(tb, text="", font=("SimHei", 12), fg="#333")
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        # canvas
        cv_h = BOARD_H + 40
        self.cv = tk.Canvas(self.root, width=BOARD_W, height=cv_h, bg=BOARD_BG)
        self.cv.pack(padx=6, pady=8)
        self.cv.bind("<Button-1>", self._onclick)

        self._update_status()
        self._redraw()

    def _new_game(self):
        self.game = Game()
        self.selected = None
        self.valid_moves = []
        self.last_move = None
        self.ai_thinking = False
        self._update_status()
        self._redraw()

    # --------------- drawing ---------------
    def _px(self, r, c):
        return MARGIN + c * CELL, MARGIN + r * CELL

    def _redraw(self):
        cv = self.cv
        cv.delete("all")

        # ---- grid lines ----
        for i in range(COLS):
            x = MARGIN + i * CELL
            cv.create_line(x, MARGIN, x, MARGIN + 4 * CELL, fill=LINE_COLOR, width=1)
            cv.create_line(x, MARGIN + 5 * CELL, x, MARGIN + 9 * CELL, fill=LINE_COLOR, width=1)
        for j in range(ROWS):
            y = MARGIN + j * CELL
            cv.create_line(MARGIN, y, MARGIN + 8 * CELL, y, fill=LINE_COLOR, width=1)

        # ---- palace diagonals ----
        cv.create_line(MARGIN + 3*CELL, MARGIN, MARGIN + 5*CELL, MARGIN + 2*CELL, fill=LINE_COLOR)
        cv.create_line(MARGIN + 5*CELL, MARGIN, MARGIN + 3*CELL, MARGIN + 2*CELL, fill=LINE_COLOR)
        cv.create_line(MARGIN + 3*CELL, MARGIN + 9*CELL, MARGIN + 5*CELL, MARGIN + 7*CELL, fill=LINE_COLOR)
        cv.create_line(MARGIN + 5*CELL, MARGIN + 9*CELL, MARGIN + 3*CELL, MARGIN + 7*CELL, fill=LINE_COLOR)

        # ---- river text ----
        river_y = MARGIN + 4.5 * CELL
        cv.create_text(MARGIN + 2*CELL, river_y, text="楚 河", font=("KaiTi", 22, "bold"), fill=LINE_COLOR)
        cv.create_text(MARGIN + 6*CELL, river_y, text="汉 界", font=("KaiTi", 22, "bold"), fill=LINE_COLOR)

        # ---- position markers (small L marks at cannon/soldier starting positions) ----
        self._draw_marks(cv)

        # ---- last move highlight ----
        if self.last_move:
            fr, fc, tr, tc = self.last_move
            for r, c in [(fr, fc), (tr, tc)]:
                x, y = self._px(r, c)
                cv.create_rectangle(x - 6, y - 6, x + 6, y + 6,
                                    outline="#4CAF50", width=2, stipple="gray50")

        # ---- valid move dots ----
        for m in self.valid_moves:
            _, _, tr, tc = m
            x, y = self._px(tr, tc)
            if self.game.board[tr][tc] == 0:
                cv.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#4CAF50")
            else:
                cv.create_oval(x - PIECE_R - 2, y - PIECE_R - 2,
                               x + PIECE_R + 2, y + PIECE_R + 2,
                               outline="#4CAF50", width=3)

        # ---- selected highlight ----
        if self.selected:
            sr, sc = self.selected
            x, y = self._px(sr, sc)
            cv.create_oval(x - PIECE_R - 2, y - PIECE_R - 2,
                           x + PIECE_R + 2, y + PIECE_R + 2,
                           outline="#2196F3", width=3)

        # ---- pieces ----
        for r in range(ROWS):
            for c in range(COLS):
                p = self.game.board[r][c]
                if p == 0:
                    continue
                color = RED if p > 0 else BLACK
                ptype = abs(p)
                ch = PIECE_CHARS.get((color, ptype), "?")
                style = RED_STYLES if color == RED else BLACK_STYLES
                x, y = self._px(r, c)
                cv.create_oval(x - PIECE_R, y - PIECE_R,
                               x + PIECE_R, y + PIECE_R,
                               fill=style["fill"], outline=style["outline"], width=2.5)
                cv.create_text(x, y, text=ch, font=("KaiTi", 20, "bold"), fill=style["text"])

        # ---- check indicator ----
        if is_in_check(self.game.board, self.game.current):
            kr, kc = find_king(self.game.board, self.game.current)
            if kr is not None:
                x, y = self._px(kr, kc)
                cv.create_oval(x - PIECE_R - 4, y - PIECE_R - 4,
                               x + PIECE_R + 4, y + PIECE_R + 4,
                               outline="red", width=4)

    def _draw_marks(self, cv):
        """Draw small L-shaped position markers at traditional starting positions."""
        positions = [
            (2, 1), (2, 7),  # cannon positions (black side)
            (3, 0), (3, 2), (3, 4), (3, 6), (3, 8),  # soldier positions (black)
            (7, 1), (7, 7),  # cannon positions (red side)
            (6, 0), (6, 2), (6, 4), (6, 6), (6, 8),  # soldier positions (red)
        ]
        s = 5  # mark size
        g = 3  # gap from intersection
        for r, c in positions:
            x, y = self._px(r, c)
            # four corners, skip outer edges
            corners = []
            if c > 0:
                corners.append((x - g - s, y - g, x - g, y - g))   # left-up
                corners.append((x - g - s, y + g, x - g, y + g + s))  # left-down
            if c < COLS - 1:
                corners.append((x + g, y - g, x + g + s, y - g))   # right-up
                corners.append((x + g, y + g, x + g + s, y + g + s))  # right-down
            for x1, y1, x2, y2 in corners:
                cv.create_line(x1, y1, x2, y2, fill=LINE_COLOR, width=1)

    # --------------- status ---------------
    def _update_status(self):
        g = self.game
        if g is None:
            return
        if g.winner:
            winner = "红方" if g.winner == RED else "黑方"
            self.lbl_status.config(text=f"绝杀！{winner}获胜")
            return
        turn = "红方" if g.current == RED else "黑方"
        check_txt = " — 将军!" if is_in_check(g.board, g.current) else ""
        self.lbl_status.config(text=f"第 {len(g.history) + 1} 手  {turn}走{check_txt}")

    # --------------- interaction ---------------
    def _onclick(self, evt):
        if self.game is None or self.game.game_over() is not None:
            return
        if self.mode == self.MODE_AI and self.game.current == BLACK:
            return  # AI's turn

        col = round((evt.x - MARGIN) / CELL)
        row = round((evt.y - MARGIN) / CELL)
        if not _in_bounds(row, col):
            return

        clicked = self.game.board[row][col]
        is_own = clicked != 0 and ((clicked > 0) == (self.game.current > 0))

        if self.selected is None:
            if is_own:
                self.selected = (row, col)
                self.valid_moves = [m for m in legal_moves(self.game.board, self.game.current)
                                    if m[0] == row and m[1] == col]
        else:
            sr, sc = self.selected
            move = (sr, sc, row, col)
            if move in self.valid_moves:
                self._execute_move(sr, sc, row, col)
                return
            elif is_own:
                self.selected = (row, col)
                self.valid_moves = [m for m in legal_moves(self.game.board, self.game.current)
                                    if m[0] == row and m[1] == col]
            else:
                self.selected = None
                self.valid_moves = []

        self._redraw()

    def _execute_move(self, fr, fc, tr, tc):
        captured = self.game.board[tr][tc]
        self.game.make_move(fr, fc, tr, tc)
        self.selected = None
        self.valid_moves = []
        self.last_move = (fr, fc, tr, tc)
        self._redraw()

        result = self.game.game_over()
        if result == "checkmate":
            winner = "红方" if self.game.winner == RED else "黑方"
            if self.mode == self.MODE_AI:
                winner = "你 (红方)" if self.game.winner == RED else "AI (黑方)"
            self.lbl_status.config(text=f"绝杀！{winner} 获胜！")
            self._redraw()
            messagebox.showinfo("中国象棋", f"绝杀！{winner} 获胜！\n共 {len(self.game.history)} 手")
            return
        elif result == "stalemate":
            self.lbl_status.config(text="逼和！")
            messagebox.showinfo("中国象棋", "逼和！双方无子可走")
            return

        self._update_status()

        # AI turn?
        if self.mode == self.MODE_AI and self.game.current == BLACK:
            self.ai_thinking = True
            self.lbl_status.config(text=f"第 {len(self.game.history) + 1} 手  AI 思考中…")
            self.root.after(100, self._ai_turn)

    def _ai_turn(self):
        try:
            move = ai_find_move(self.game.board, self.difficulty)
        except Exception as e:
            messagebox.showerror("AI 错误", str(e))
            self.ai_thinking = False
            return
        if move is None:
            self.ai_thinking = False
            return
        fr, fc, tr, tc = move
        self.ai_thinking = False
        self._execute_move(fr, fc, tr, tc)

    # --------------- undo ---------------
    def _undo(self):
        if self.game is None or not self.game.history:
            return
        steps = 2 if self.mode == self.MODE_AI and len(self.game.history) >= 2 else 1
        for _ in range(steps):
            if not self.game.history:
                break
            self.game.undo()
        self.game.winner = None
        self.selected = None
        self.valid_moves = []
        self.last_move = self.game.history[-1][:4] if self.game.history else None
        self._update_status()
        self._redraw()


# ===================================================================
if __name__ == "__main__":
    App()
