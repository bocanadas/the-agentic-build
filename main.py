#!/usr/bin/env python3
"""Python Quiz CLI — a local command-line quiz app with login, scoring, and feedback."""

import os
import sys
import json
import atexit
import sqlite3
import hashlib
import secrets
import random
from datetime import datetime
from cryptography.fernet import Fernet
from getpass import getpass

try:
    import tty
    import termios
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False

try:
    import msvcrt  # type: ignore[import-not-found]
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

# ── Paths & constants ────────────────────────────────────────────────────────

_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(_DIR, "questions.json")
FEEDBACK_FILE = os.path.join(_DIR, "feedback.json")
SCORES_FILE = os.path.join(_DIR, "scores.json")
SCORES_KEY_FILE = os.path.join(_DIR, ".scores.key")
DB_FILE = os.path.join(_DIR, "users.db")

DIFF_PTS = {"easy": 1, "medium": 2, "hard": 3}


# ── ANSI helpers ─────────────────────────────────────────────────────────────

class _C:
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

_HIDE_CUR = "\033[?25l"
_SHOW_CUR = "\033[?25h"


def _show_cursor():
    sys.stdout.write(_SHOW_CUR)
    sys.stdout.flush()


def _hide_cursor():
    sys.stdout.write(_HIDE_CUR)
    sys.stdout.flush()


def _clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


# ── Raw key reading ──────────────────────────────────────────────────────────

def _get_key():
    if _HAS_TERMIOS:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                c2 = sys.stdin.read(1)
                if c2 == "[":
                    c3 = sys.stdin.read(1)
                    return {"A": "up", "B": "down"}.get(c3, "unknown")
                return "escape"
            if ch in ("\r", "\n"):
                return "enter"
            if ch == " ":
                return "space"
            if ch == "\x03":
                return "ctrl_c"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    elif _HAS_MSVCRT:
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            c2 = msvcrt.getch()
            return {b"H": "up", b"P": "down"}.get(c2, "unknown")
        if ch == b"\r":
            return "enter"
        if ch == b" ":
            return "space"
        if ch == b"\x03":
            return "ctrl_c"
        return ch.decode("utf-8", errors="replace")
    return input()


# ── UI primitives ────────────────────────────────────────────────────────────

def _inline_select(options, selected=0):
    """Arrow-key menu rendered inline (no screen clear)."""
    n = len(options)
    total = n + 2

    def _draw():
        for i, o in enumerate(options):
            if i == selected:
                print(f"    {_C.CYAN}{_C.BOLD}\u25b8 {o}{_C.RST}")
            else:
                print(f"      {_C.DIM}{o}{_C.RST}")
        print()
        print(f"    {_C.GRAY}\u2191/\u2193 to navigate \u00b7 Enter to select{_C.RST}")

    _hide_cursor()
    try:
        _draw()
        while True:
            k = _get_key()
            if k == "ctrl_c":
                raise KeyboardInterrupt
            moved = False
            if k == "up" and selected > 0:
                selected -= 1
                moved = True
            elif k == "down" and selected < n - 1:
                selected += 1
                moved = True
            elif k == "enter":
                return selected
            if moved:
                sys.stdout.write(f"\033[{total}A")
                for _ in range(total):
                    sys.stdout.write("\033[2K\n")
                sys.stdout.write(f"\033[{total}A")
                _draw()
    finally:
        _show_cursor()


def _fullscreen_menu(options, header_lines=None, selected=0):
    """Full-screen arrow-key menu (clears screen each redraw)."""

    def _draw():
        _clear()
        if header_lines:
            for ln in header_lines:
                print(ln)
            print()
        for i, o in enumerate(options):
            if i == selected:
                print(f"    {_C.CYAN}{_C.BOLD}\u25b8 {o}{_C.RST}")
            else:
                print(f"      {_C.DIM}{o}{_C.RST}")
        print()
        print(f"    {_C.GRAY}\u2191/\u2193 to navigate \u00b7 Enter to select{_C.RST}")

    _hide_cursor()
    try:
        _draw()
        while True:
            k = _get_key()
            if k == "ctrl_c":
                raise KeyboardInterrupt
            if k == "up" and selected > 0:
                selected -= 1
                _draw()
            elif k == "down" and selected < len(options) - 1:
                selected += 1
                _draw()
            elif k == "enter":
                return selected
    finally:
        _show_cursor()


def _safe_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        raise KeyboardInterrupt


def _masked_input(prompt):
    """Password field that prints bullet characters."""
    if _HAS_TERMIOS:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            buf: list[str] = []
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    break
                elif ch in ("\x7f", "\x08"):
                    if buf:
                        buf.pop()
                        sys.stdout.write("\b \b")
                elif ch == "\x03":
                    sys.stdout.write("\n")
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                    raise KeyboardInterrupt
                elif ord(ch) >= 32:
                    buf.append(ch)
                    sys.stdout.write("\u2022")
                sys.stdout.flush()
            return "".join(buf)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    else:
        return getpass(prompt)


def _wait(msg="Press Enter or Space to continue\u2026"):
    print(f"\n  {_C.GRAY}{msg}{_C.RST}")
    while True:
        k = _get_key()
        if k in ("enter", "space"):
            return
        if k == "ctrl_c":
            raise KeyboardInterrupt


def _header(title):
    w = max(len(title) + 6, 40)
    pl = (w - len(title)) // 2
    pr = w - pl - len(title)
    print(f"\n  {_C.CYAN}\u2554{'\u2550' * w}\u2557{_C.RST}")
    print(f"  {_C.CYAN}\u2551{' ' * pl}{_C.BOLD}{title}{_C.RST}{_C.CYAN}{' ' * pr}\u2551{_C.RST}")
    print(f"  {_C.CYAN}\u255a{'\u2550' * w}\u255d{_C.RST}\n")


def _divider():
    print(f"  {_C.DIM}{'\u2500' * 44}{_C.RST}")


# ── Database (users) ─────────────────────────────────────────────────────────

def _init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "username TEXT UNIQUE NOT NULL,"
        "password_hash TEXT NOT NULL,"
        "salt TEXT NOT NULL,"
        "created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()


_PBKDF2_ITERATIONS = 600_000

def _hash_pw(pw, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), _PBKDF2_ITERATIONS)
    return h.hex(), salt


def _check_password(pw):
    if len(pw) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in pw):
        return "Password must include at least 1 uppercase letter."
    if not any(c.islower() for c in pw):
        return "Password must include at least 1 lowercase letter."
    if not any(c.isdigit() for c in pw):
        return "Password must include at least 1 digit."
    return None


def _db_create(username, password):
    conn = sqlite3.connect(DB_FILE)
    try:
        h, s = _hash_pw(password)
        conn.execute(
            "INSERT INTO users (username,password_hash,salt,created_at) VALUES (?,?,?,?)",
            (username, h, s, datetime.now().isoformat()),
        )
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "That username already exists. Please choose a different one."
    finally:
        conn.close()


def _db_verify(username, password):
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT password_hash, salt FROM users WHERE username=?", (username,)
    ).fetchone()
    conn.close()
    if row is None:
        return False, "not_found"
    h, _ = _hash_pw(password, row[1])
    return (True, "ok") if h == row[0] else (False, "wrong_pw")


# ── Questions ────────────────────────────────────────────────────────────────

def _load_questions():
    if not os.path.exists(QUESTIONS_FILE):
        return None, (
            "Question bank not found: questions.json\n\n"
            f"  Please create a 'questions.json' file in:\n  {_DIR}\n\n"
            "  See README.md for the expected format."
        )
    try:
        with open(QUESTIONS_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON in questions.json:\n  {exc}\n\n  Please fix the file and try again."
    qs = data.get("questions", [])
    if not qs:
        return None, (
            "The question bank is empty!\n\n"
            "  Add questions to 'questions.json' to get started.\n"
            "  See README.md for the expected format."
        )
    return qs, None


def _pick(questions, count, username):
    fb = _load_fb().get(username, {})
    weights = []
    for q in questions:
        val = fb.get(q["question"], "neutral")
        weights.append({"liked": 1.5, "disliked": 0.3}.get(val, 1.0))
    count = min(count, len(questions))
    pool = list(range(len(questions)))
    w = list(weights)
    chosen = []
    for _ in range(count):
        if not pool:
            break
        idx = random.choices(range(len(pool)), weights=w, k=1)[0]
        chosen.append(questions[pool[idx]])
        pool.pop(idx)
        w.pop(idx)
    random.shuffle(chosen)
    return chosen


# ── Scores (Fernet AES encryption) ──────────────────────────────────────────

def _get_fernet():
    if os.path.exists(SCORES_KEY_FILE):
        with open(SCORES_KEY_FILE, "rb") as f:
            key = f.read().strip()
    else:
        key = Fernet.generate_key()
        with open(SCORES_KEY_FILE, "wb") as f:
            f.write(key)
    return Fernet(key)


def _load_scores():
    if not os.path.exists(SCORES_FILE):
        return {}
    try:
        with open(SCORES_FILE, "rb") as f:
            token = f.read()
        plaintext = _get_fernet().decrypt(token)
        return json.loads(plaintext)
    except Exception:
        return {}


def _save_scores(data):
    token = _get_fernet().encrypt(json.dumps(data).encode())
    tmp = SCORES_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(token)
    os.replace(tmp, SCORES_FILE)


def _record_score(user, score, mx, correct, wrong, total):
    sc = _load_scores()
    if user not in sc:
        sc[user] = {"quizzes": [], "total_quizzes": 0, "total_correct": 0, "total_wrong": 0}
    u = sc[user]
    u["quizzes"].append({
        "date": datetime.now().isoformat(),
        "score": score, "max": mx, "correct": correct, "wrong": wrong, "total": total,
    })
    u["total_quizzes"] += 1
    u["total_correct"] += correct
    u["total_wrong"] += wrong
    _save_scores(sc)


def _stats(user):
    sc = _load_scores()
    u = sc.get(user)
    if not u or u["total_quizzes"] == 0:
        return {"n": 0, "correct": 0, "wrong": 0, "avg": 0.0, "best": 0.0}
    qs = u["quizzes"]
    ts = sum(q["score"] for q in qs)
    tm = sum(q["max"] for q in qs)
    avg = (ts / tm * 100) if tm else 0
    best = max((q["score"] / q["max"] * 100) if q["max"] else 0 for q in qs)
    return {
        "n": u["total_quizzes"], "correct": u["total_correct"],
        "wrong": u["total_wrong"], "avg": round(avg, 1), "best": round(best, 1),
    }


# ── Feedback ─────────────────────────────────────────────────────────────────

def _load_fb():
    if not os.path.exists(FEEDBACK_FILE):
        return {}
    try:
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_fb(data):
    tmp = FEEDBACK_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FEEDBACK_FILE)


def _record_fb(user, question_text, value):
    data = _load_fb()
    data.setdefault(user, {})[question_text] = value
    _save_fb(data)


# ── Screens ──────────────────────────────────────────────────────────────────

def _screen_greeting():
    _clear()
    _header("Python Quiz App")
    print(f"  {_C.WHITE}Welcome to the Python Quiz App!{_C.RST}")
    print(f"  {_C.DIM}Test your Python knowledge with interactive quizzes.{_C.RST}")
    print()
    _divider()
    _wait()


def _screen_auth():
    while True:
        hdr = [
            "",
            f"  {_C.CYAN}{_C.BOLD}\u2554{'=' * 42}\u2557{_C.RST}",
            f"  {_C.CYAN}{_C.BOLD}\u2551{'Python Quiz App':^42}\u2551{_C.RST}",
            f"  {_C.CYAN}{_C.BOLD}\u255a{'=' * 42}\u255d{_C.RST}",
            "",
            f"  {_C.WHITE}What would you like to do?{_C.RST}",
        ]
        ch = _fullscreen_menu(["Log In", "Create Account", "Quit"], header_lines=hdr)
        if ch == 0:
            r = _screen_login()
            if r:
                return r
        elif ch == 1:
            r = _screen_create()
            if r:
                return r
        else:
            return None


def _screen_login():
    _clear()
    _header("Log In")

    username = _safe_input(f"  {_C.WHITE}Username: {_C.RST}").strip()
    if not username:
        print(f"\n  {_C.RED}Username cannot be empty.{_C.RST}")
        _wait()
        return None

    password = _masked_input(f"  {_C.WHITE}Password: {_C.RST}")
    if not password:
        print(f"\n  {_C.RED}Password cannot be empty.{_C.RST}")
        _wait()
        return None

    ok, code = _db_verify(username, password)
    if ok:
        print(f"\n  {_C.GREEN}{_C.BOLD}\u2713 Welcome back, {username}!{_C.RST}")
        _wait()
        return username

    if code == "not_found":
        _clear()
        _header("Account Not Found")
        print(f"  {_C.RED}No account exists with username '{username}'.{_C.RST}")
        print()
        print(f"  {_C.YELLOW}Would you like to create an account instead?{_C.RST}")
        print()
        ch = _inline_select(["Yes, create an account", "No, go back"])
        if ch == 0:
            return _screen_create(prefill=username)
        return None

    print(f"\n  {_C.RED}\u2717 Invalid password. Please try again.{_C.RST}")
    _wait()
    return None


def _screen_create(prefill=None):
    _clear()
    _header("Create Account")

    if prefill:
        username = prefill
        print(f"  {_C.WHITE}Username: {_C.CYAN}{username}{_C.RST}")
    else:
        username = _safe_input(f"  {_C.WHITE}Username: {_C.RST}").strip()
        if not username:
            print(f"\n  {_C.RED}Username cannot be empty.{_C.RST}")
            _wait()
            return None

    print(f"  {_C.DIM}Min 8 chars, 1 uppercase, 1 lowercase, 1 digit{_C.RST}")
    password = _masked_input(f"  {_C.WHITE}Password: {_C.RST}")

    pw_err = _check_password(password)
    if pw_err:
        print(f"\n  {_C.RED}{pw_err}{_C.RST}")
        _wait()
        return None

    confirm = _masked_input(f"  {_C.WHITE}Confirm:  {_C.RST}")
    if password != confirm:
        print(f"\n  {_C.RED}\u2717 Passwords do not match.{_C.RST}")
        _wait()
        return None

    _clear()
    _header("Confirm Account")
    print(f"  {_C.WHITE}Username:{_C.RST}  {_C.CYAN}{username}{_C.RST}")
    print(f"  {_C.WHITE}Password:{_C.RST}  {_C.CYAN}{'\u2022' * min(len(password), 12)}{_C.RST}")
    print()
    print(f"  {_C.YELLOW}Is this correct?{_C.RST}")
    print()
    ch = _inline_select(["Yes, create my account", "No, take me back"])
    if ch == 1:
        return None

    ok, msg = _db_create(username, password)
    if ok:
        print(f"\n  {_C.GREEN}{_C.BOLD}\u2713 {msg}{_C.RST}")
        _wait()
        return username

    print(f"\n  {_C.RED}\u2717 {msg}{_C.RST}")
    _wait()
    return None


def _screen_dashboard(username):
    st = _stats(username)
    hdr = [
        "",
        f"  {_C.CYAN}{_C.BOLD}\u2554{'=' * 42}\u2557{_C.RST}",
        f"  {_C.CYAN}{_C.BOLD}\u2551{'Dashboard':^42}\u2551{_C.RST}",
        f"  {_C.CYAN}{_C.BOLD}\u255a{'=' * 42}\u255d{_C.RST}",
        "",
        f"  {_C.WHITE}Welcome back, {_C.CYAN}{_C.BOLD}{username}{_C.RST}{_C.WHITE}!{_C.RST}",
        "",
        f"  {_C.WHITE}{_C.BOLD}Your Stats{_C.RST}",
        f"  {_C.DIM}{'\u2500' * 30}{_C.RST}",
    ]
    if st["n"] == 0:
        hdr.append(f"  {_C.DIM}No quizzes taken yet. Start one!{_C.RST}")
    else:
        hdr += [
            f"  {_C.WHITE}Quizzes Taken:  {_C.CYAN}{st['n']}{_C.RST}",
            f"  {_C.WHITE}Average Score:  {_C.CYAN}{st['avg']}%{_C.RST}",
            f"  {_C.WHITE}Best Score:     {_C.CYAN}{st['best']}%{_C.RST}",
            f"  {_C.WHITE}Total Correct:  {_C.GREEN}{st['correct']}{_C.RST}",
            f"  {_C.WHITE}Total Wrong:    {_C.RED}{st['wrong']}{_C.RST}",
        ]
    hdr += ["", f"  {_C.DIM}{'\u2500' * 30}{_C.RST}", ""]
    ch = _fullscreen_menu(["Start New Quiz", "Log Out", "Quit"], header_lines=hdr)
    return ["quiz", "logout", "quit"][ch]


def _screen_setup(questions):
    _clear()
    _header("New Quiz")
    n = len(questions)
    print(f"  {_C.WHITE}Available questions: {_C.CYAN}{n}{_C.RST}")
    print(f"  {_C.DIM}Enter a number between 1 and {n}, or 'back' to return.{_C.RST}")
    print()
    while True:
        ans = _safe_input(f"  {_C.WHITE}How many questions? {_C.RST}").strip()
        if ans.lower() == "back":
            return None
        try:
            v = int(ans)
            if 1 <= v <= n:
                return v
            print(f"  {_C.RED}Enter a number between 1 and {n}.{_C.RST}")
        except ValueError:
            print(f"  {_C.RED}Invalid input. Enter a number (e.g. 5) or 'back'.{_C.RST}")


# ── Quiz engine ──────────────────────────────────────────────────────────────

def _run_quiz(username, quiz_qs):
    """Returns (results_list, True) when the quiz finishes normally.
    Raises KeyboardInterrupt if the user abandons mid-quiz."""
    results = []
    total = len(quiz_qs)

    for i, q in enumerate(quiz_qs):
        _clear()
        diff = q.get("difficulty", "medium")
        dc = {"easy": _C.GREEN, "medium": _C.YELLOW, "hard": _C.RED}.get(diff, _C.WHITE)
        pts = DIFF_PTS.get(diff, 1)

        print(f"\n  {_C.CYAN}{_C.BOLD}Question {i + 1} of {total}{_C.RST}")
        print(f"  {dc}[{diff.upper()}]{_C.RST} {_C.DIM}\u00b7 {pts} pt{'s' if pts != 1 else ''} \u00b7 {q.get('category', 'General')}{_C.RST}")
        print()
        print(f"  {_C.WHITE}{_C.BOLD}{q['question']}{_C.RST}")
        print()
        _divider()
        print()

        qtype = q.get("type", "multiple_choice")
        user_ans = None

        if qtype == "multiple_choice":
            opts = q["options"]
            labels = [f"{chr(65 + j)}) {o}" for j, o in enumerate(opts)]
            idx = _inline_select(labels)
            user_ans = opts[idx]

        elif qtype == "true_false":
            idx = _inline_select(["True", "False"])
            user_ans = ["true", "false"][idx]

        elif qtype == "short_answer":
            user_ans = _safe_input(f"    {_C.WHITE}Your answer: {_C.RST}").strip()

        correct_ans = q["answer"]
        accepted = [correct_ans] + q.get("alternatives", [])
        typed = (user_ans or "").lower().strip()
        is_correct = any(typed == a.lower().strip() for a in accepted)

        # ── Result screen ────────────────────────────────────────────────
        _clear()
        print(f"\n  {_C.CYAN}{_C.BOLD}Question {i + 1} of {total}{_C.RST}")
        print(f"  {_C.DIM}{q['question']}{_C.RST}")
        print()

        if is_correct:
            earned = pts
            print(f"  {_C.GREEN}{_C.BOLD}\u2713 Correct!  +{pts} pt{'s' if pts != 1 else ''}{_C.RST}")
            print()
            exp = q.get("explanation", "")
            if exp:
                print(f"  {_C.WHITE}{exp}{_C.RST}")
        else:
            earned = 0
            disp = (user_ans or "").capitalize() if qtype == "true_false" else (user_ans or "")
            corr_disp = correct_ans.capitalize() if qtype == "true_false" else correct_ans

            print(f"  {_C.RED}{_C.BOLD}\u2717 Incorrect{_C.RST}")
            print()
            print(f"  {_C.RED}Your answer:    {disp}{_C.RST}")
            print(f"  {_C.GREEN}Correct answer: {corr_disp}{_C.RST}")
            print()

            we = q.get("wrong_explanations", {}).get(
                user_ans, q.get("wrong_explanations", {}).get((user_ans or "").lower(), "")
            )
            if not we:
                we = q.get("wrong_explanation", "")
            if we:
                print(f"  {_C.RED}Why '{disp}' is wrong:{_C.RST}")
                print(f"  {_C.WHITE}{we}{_C.RST}")
                print()

            exp = q.get("explanation", "")
            if exp:
                print(f"  {_C.GREEN}Why '{corr_disp}' is correct:{_C.RST}")
                print(f"  {_C.WHITE}{exp}{_C.RST}")

        results.append({
            "question": q["question"],
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct,
            "earned": earned,
            "possible": pts,
            "difficulty": diff,
        })

        _wait()

        # ── Feedback screen ──────────────────────────────────────────────
        _clear()
        print(f"\n  {_C.CYAN}{_C.BOLD}Question {i + 1} Feedback{_C.RST}")
        print(f"  {_C.DIM}{q['question']}{_C.RST}")
        print()
        print(f"  {_C.WHITE}How did you feel about this question?{_C.RST}")
        print()

        fb_idx = _inline_select([
            "I liked this question.",
            "I did not like this question.",
            "I didn\u2019t mind this question.",
        ])
        _record_fb(username, q["question"], {0: "liked", 1: "disliked", 2: "neutral"}[fb_idx])

    return results, True


def _screen_summary(results, username):
    _clear()
    te = sum(r["earned"] for r in results)
    tp = sum(r["possible"] for r in results)
    nc = sum(1 for r in results if r["is_correct"])
    nw = len(results) - nc
    pct = (te / tp * 100) if tp else 0

    _header("Quiz Complete!")

    if pct >= 80:
        print(f"  {_C.GREEN}{_C.BOLD}Excellent work!{_C.RST}")
    elif pct >= 60:
        print(f"  {_C.YELLOW}{_C.BOLD}Good effort!{_C.RST}")
    else:
        print(f"  {_C.RED}{_C.BOLD}Keep practicing!{_C.RST}")
    print()
    print(f"  {_C.WHITE}Score: {_C.CYAN}{_C.BOLD}{te}/{tp}{_C.RST} {_C.DIM}({pct:.0f}%){_C.RST}")
    print(f"  {_C.GREEN}Correct: {nc}{_C.RST}   {_C.RED}Wrong: {nw}{_C.RST}")
    print()
    _divider()
    print()
    print(f"  {_C.WHITE}{_C.BOLD}Breakdown:{_C.RST}")
    print()

    for r in results:
        icon = f"{_C.GREEN}\u2713{_C.RST}" if r["is_correct"] else f"{_C.RED}\u2717{_C.RST}"
        txt = r["question"][:45] + ("\u2026" if len(r["question"]) > 45 else "")
        pt_s = f"+{r['earned']}" if r["is_correct"] else "+0"
        print(f"  {icon} {_C.DIM}{txt}{_C.RST}")
        print(f"    {_C.DIM}[{r['difficulty']}] {pt_s}{_C.RST}")
    print()
    _divider()

    _record_score(username, te, tp, nc, nw, len(results))


def _screen_post_quiz():
    print()
    print(f"  {_C.WHITE}What would you like to do next?{_C.RST}")
    print()
    return _inline_select(["Return to Dashboard", "Redo This Quiz"])


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    atexit.register(_show_cursor)

    try:
        _init_db()

        questions, err = _load_questions()
        if err:
            _clear()
            _header("Error")
            for ln in err.split("\n"):
                print(f"  {_C.RED}{ln}{_C.RST}")
            print()
            return

        _screen_greeting()

        while True:
            username = _screen_auth()
            if username is None:
                break

            while True:
                action = _screen_dashboard(username)

                if action == "quit":
                    _clear()
                    print(f"\n  {_C.CYAN}Goodbye, {username}! See you next time.{_C.RST}\n")
                    return

                if action == "logout":
                    break

                if action == "quiz":
                    count = _screen_setup(questions)
                    if count is None:
                        continue

                    while True:
                        quiz_qs = _pick(questions, count, username)
                        try:
                            results, _ = _run_quiz(username, quiz_qs)
                        except KeyboardInterrupt:
                            _clear()
                            print(f"\n  {_C.YELLOW}Quiz interrupted. Your progress was not saved.{_C.RST}")
                            try:
                                _wait()
                            except KeyboardInterrupt:
                                pass
                            break

                        _screen_summary(results, username)
                        post = _screen_post_quiz()
                        if post == 0:
                            break

        _clear()
        print(f"\n  {_C.CYAN}Goodbye! Thanks for using Python Quiz App.{_C.RST}\n")

    except KeyboardInterrupt:
        _show_cursor()
        _clear()
        print(f"\n  {_C.CYAN}Goodbye! Thanks for using Python Quiz App.{_C.RST}\n")


if __name__ == "__main__":
    main()
