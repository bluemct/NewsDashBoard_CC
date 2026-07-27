"""
Gomoku (Five in a Row) 五子棋 — Python + tkinter

- 双人对战 / 人机对战 (玩家执白先行)
- 15x15 棋盘，五连获胜
- 启发式 AI（扫描每个空位评分，进攻 + 防守）

Usage:  python gomoku.py
"""
import tkinter as tk
from tkinter import messagebox

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BOARD_SIZE = 15
CELL = 40
MARGIN = 30
STONE_R = 16
BOARD_PX = MARGIN * 2 + CELL * (BOARD_SIZE - 1)

BLACK_C  = "#1E1E1E"
WHITE_C  = "#F0F0F0"
BOARD_BG = "#DEB887"
LINE_C   = "#5C4033"

EMPTY, BLACK, WHITE = 0, 1, 2
PLAYER_NAMES = {BLACK: "Black (●)", WHITE: "White (○)"}


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------
class Board:
    def __init__(self):
        self.n = BOARD_SIZE
        self.g = [[EMPTY]*BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.winner = None
        self.win_line = None

    def place(self, r, c, p):
        if self.g[r][c] != EMPTY or self.winner:
            return False
        self.g[r][c] = p
        self._check(r, c, p)
        return True

    def _check(self, r, c, p):
        for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
            cells = [(r,c)]
            for sign in (1, -1):
                nr, nc = r+dr*sign, c+dc*sign
                while 0<=nr<self.n and 0<=nc<self.n and self.g[nr][nc]==p:
                    cells.append((nr,nc))
                    nr+=dr*sign
                    nc+=dc*sign
            if len(cells) >= 5:
                self.winner = p
                self.win_line = cells
                return

    def is_full(self):
        return all(self.g[r][c] for r in range(self.n) for c in range(self.n))

    def near_stone(self, r, c, dist=2):
        for dr in range(-dist, dist+1):
            for dc in range(-dist, dist+1):
                nr, nc = r+dr, c+dc
                if 0<=nr<self.n and 0<=nc<self.n and self.g[nr][nc] != EMPTY:
                    return True
        return False


# ---------------------------------------------------------------------------
# AI  — heuristic evaluator
# ---------------------------------------------------------------------------
def _eval_line(me, opp):
    # Score a single direction: me=(count, open_ends), opp=(count, open_ends)
    score = 0
    # Offence
    mc, meo = me
    if mc >= 5: score += 200000
    elif mc == 4 and meo == 2: score += 15000
    elif mc == 4 and meo == 1: score += 3000
    elif mc == 3 and meo == 2: score += 3000
    elif mc == 3 and meo == 1: score += 300
    elif mc == 2 and meo == 2: score += 300
    elif mc == 2 and meo == 1: score += 50
    # Defence
    oc, oeo = opp
    if oc >= 5: score += 200000
    elif oc == 4 and oeo == 2: score += 12000
    elif oc == 4 and oeo == 1: score += 2500
    elif oc == 3 and oeo == 2: score += 2500
    elif oc == 3 and oeo == 1: score += 200
    elif oc == 2 and oeo == 2: score += 200
    elif oc == 2 and oeo == 1: score += 40
    return score

def _count_line(board, r, c, dr, dc, player):
    opp = WHITE if player == BLACK else BLACK
    count = 0
    for sign in (1, -1):
        nr, nc = r+dr*sign, c+dc*sign
        while 0<=nr<BOARD_SIZE and 0<=nc<BOARD_SIZE and board.g[nr][nc]==player:
            count += 1
            nr+=dr*sign
            nc+=dc*sign
    return count

def _open_ends(board, r, c, dr, dc, player):
    ends = 0
    for sign in (1, -1):
        nr, nc = r+dr*sign, c+dc*sign
        # skip our own stones
        while 0<=nr<BOARD_SIZE and 0<=nc<BOARD_SIZE and board.g[nr][nc]==player:
            nr+=dr*sign
            nc+=dc*sign
        if 0<=nr<BOARD_SIZE and 0<=nc<BOARD_SIZE and board.g[nr][nc]==EMPTY:
            ends += 1
    return ends

def ai_move(board):
    """Return (r, c) for the AI (always plays BLACK)."""
    best_score = -1
    best_moves = []
    has_any = any(board.g[r][c] for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board.g[r][c] != EMPTY:
                continue
            if has_any and not board.near_stone(r, c):
                continue
            total = 0
            for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                me_c = _count_line(board, r, c, dr, dc, BLACK) + 1
                me_e = _open_ends(board, r, c, dr, dc, BLACK)
                op_c = _count_line(board, r, c, dr, dc, WHITE)
                op_e = _open_ends(board, r, c, dr, dc, WHITE)
                total += _eval_line((me_c, me_e), (op_c, op_e))
            if total > best_score:
                best_score = total
                best_moves = [(r, c)]
            elif total == best_score:
                best_moves.append((r, c))
    if not best_moves:
        mid = BOARD_SIZE // 2
        if board.g[mid][mid] == EMPTY:
            return mid, mid
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if board.g[r][c] == EMPTY:
                    return r, c
    import random
    return random.choice(best_moves)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class App:
    MODE_PVP = 0
    MODE_AI  = 1  # human = WHITE, AI = BLACK

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Gomoku 五子棋")
        self.root.resizable(False, False)
        self.mode = None
        self._show_menu()
        self.root.mainloop()

    # --------------- menu screen ---------------
    def _show_menu(self):
        for w in self.root.winfo_children():
            w.destroy()
        w, h = 420, 260
        self.root.geometry(f"{w}x{h}+{self.root.winfo_screenwidth()//2-w//2}+{self.root.winfo_screenheight()//2-h//2}")

        tk.Label(self.root, text="五  子  棋", font=("Segoe UI", 36, "bold"), fg="#1a1a2e").pack(pady=36)
        tk.Label(self.root, text="Gomoku", font=("Segoe UI", 16), fg="#888").pack(pady=(0, 30))

        f = tk.Frame(self.root)
        f.pack()
        tk.Button(f, text="👥  双人对战", command=self._start_pvp, width=16, height=2, font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=20)
        tk.Button(f, text="🤖  人机对战  (你执白)", command=self._start_ai, width=24, height=2, font=("Segoe UI", 14)).pack(side=tk.LEFT, padx=20)

    def _start_pvp(self):
        self.mode = self.MODE_PVP
        self._build_game(title="五子棋 — 双人对战")

    def _start_ai(self):
        self.mode = self.MODE_AI
        self._build_game(title="五子棋 — 人机对战 (你执白 ○)")

    # --------------- game screen ---------------
    def _build_game(self, title):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.geometry("")
        self.root.resizable(False, False)
        self.root.title(title)

        self.board = Board()
        self.current = WHITE   # WHITE (human) always goes first in AI mode
        self.history = []

        # toolbar
        tb = tk.Frame(self.root)
        tb.pack(fill="x", pady=4)
        tk.Button(tb, text="↩ 菜单", command=self._show_menu).pack(side=tk.LEFT, padx=8)
        tk.Button(tb, text="新游戏", command=self._new_game).pack(side=tk.LEFT, padx=8)
        tk.Button(tb, text="悔棋", command=self._undo).pack(side=tk.LEFT, padx=8)
        self.lbl_status = tk.Label(tb, text="", font=("Segoe UI", 11), fg="#1a1a2e")
        self.lbl_status.pack(side=tk.RIGHT, padx=8)

        # canvas
        self.cv = tk.Canvas(self.root, width=BOARD_PX, height=BOARD_PX, bg=BOARD_BG)
        self.cv.pack(padx=6, pady=8)
        self.cv.bind("<Button-1>", self._onclick)
        self._update_status()
        self._redraw()

    def _new_game(self):
        self.board = Board()
        self.current = WHITE
        self.history = []
        self._update_status()
        self._redraw()

    # --------------- drawing ---------------
    def _px(self, r, c):
        return MARGIN + c*CELL, MARGIN + r*CELL

    def _redraw(self):
        cv = self.cv
        cv.delete("all")
        # lines
        for i in range(BOARD_SIZE):
            x0, y0 = self._px(0, i)
            x1, y1 = self._px(BOARD_SIZE-1, i)
            cv.create_line(x0, y0, x1, y1, fill=LINE_C)
            x0, y0 = self._px(i, 0)
            x1, y1 = self._px(i, BOARD_SIZE-1)
            cv.create_line(x0, y0, x1, y1, fill=LINE_C)
        # star points
        for r, c in [(3,3),(3,11),(7,7),(11,3),(11,11)]:
            x, y = self._px(r, c)
            cv.create_oval(x-4, y-4, x+4, y+4, fill=LINE_C)
        # stones
        for i, (r, c, p) in enumerate(self.history):
            x, y = self._px(r, c)
            color = BLACK_C if p == BLACK else WHITE_C
            cv.create_oval(x-STONE_R, y-STONE_R, x+STONE_R, y+STONE_R, fill=color, outline="#333", width=1)
            # move number
            txt_color = "#ddd" if p == BLACK else "#333"
            cv.create_text(x, y, text=str(i+1), fill=txt_color, font=("Arial", 9))
        # win highlight
        if self.board.win_line:
            for r, c in self.board.win_line:
                x, y = self._px(r, c)
                cv.create_oval(x-STONE_R-2, y-STONE_R-2, x+STONE_R+2, y+STONE_R+2, outline="red", width=3)

    def _update_status(self):
        if self.board.winner:
            return
        p = self.current
        if self.mode == self.MODE_AI:
            who = "你 (白 ○)" if p == WHITE else "AI 思考中…"
        else:
            who = PLAYER_NAMES[p]
        self.lbl_status.config(text=f"第 {len(self.history)+1} 手  —  {who}")

    # --------------- click ---------------
    def _onclick(self, evt):
        if self.board.winner or self.board.is_full():
            return
        # block input during AI turn
        if self.mode == self.MODE_AI and self.current == BLACK:
            return
        col = round((evt.x - MARGIN) / CELL)
        row = round((evt.y - MARGIN) / CELL)
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return
        if self.board.g[row][col] != EMPTY:
            return
        self._place(row, col, self.current)

    def _place(self, r, c, p):
        self.board.place(r, c, p)
        self.history.append((r, c, p))
        self._redraw()
        if self.board.winner:
            self._show_win(p)
            return
        if self.board.is_full():
            self._show_draw()
            return
        self.current = WHITE if self.current == BLACK else BLACK
        self._update_status()
        # AI turn?
        if self.mode == self.MODE_AI and self.current == BLACK:
            self.root.after(120, self._do_ai)

    def _do_ai(self):
        if self.board.winner or self.board.is_full():
            return
        r, c = ai_move(self.board)
        self._place(r, c, BLACK)

    def _show_win(self, p):
        if self.mode == self.MODE_AI:
            name = "AI (黑 ●)" if p == BLACK else "你 (白 ○)"
        else:
            name = PLAYER_NAMES[p]
        self.lbl_status.config(text=f"🏆  {name} 获胜!")
        messagebox.showinfo("Gomoku", f"{name} 获胜!\n共 {len(self.history)} 手")

    def _show_draw(self):
        self.lbl_status.config(text="和棋!")
        messagebox.showinfo("Gomoku", "棋盘已满 — 和棋!")

    # --------------- undo ---------------
    def _undo(self):
        if not self.history:
            return
        n = 2 if self.mode == self.MODE_AI and len(self.history) >= 2 else 1
        for _ in range(n):
            if not self.history:
                break
            r, c, _ = self.history.pop()
            self.board.g[r][c] = EMPTY
        self.board.winner = None
        self.board.win_line = None
        self.current = self.history[-1][2] if self.history else WHITE
        self._update_status()
        self._redraw()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    App()
