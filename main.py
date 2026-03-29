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

class _Style:
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
    num_options = len(options)
    total_lines = num_options + 2

    def _draw():
        for i, option in enumerate(options):
            if i == selected:
                print(f"    {_Style.CYAN}{_Style.BOLD}\u25b8 {option}{_Style.RST}")
            else:
                print(f"      {_Style.DIM}{option}{_Style.RST}")
        print()
        print(f"    {_Style.GRAY}\u2191/\u2193 to navigate \u00b7 Enter to select{_Style.RST}")

    _hide_cursor()
    try:
        _draw()
        while True:
            key = _get_key()
            if key == "ctrl_c":
                raise KeyboardInterrupt
            moved = False
            if key == "up" and selected > 0:
                selected -= 1
                moved = True
            elif key == "down" and selected < num_options - 1:
                selected += 1
                moved = True
            elif key == "enter":
                return selected
            if moved:
                sys.stdout.write(f"\033[{total_lines}A")
                for _ in range(total_lines):
                    sys.stdout.write("\033[2K\n")
                sys.stdout.write(f"\033[{total_lines}A")
                _draw()
    finally:
        _show_cursor()


def _fullscreen_menu(options, header_lines=None, selected=0):
    """Full-screen arrow-key menu (clears screen each redraw)."""

    def _draw():
        _clear()
        if header_lines:
            for line in header_lines:
                print(line)
            print()
        for i, option in enumerate(options):
            if i == selected:
                print(f"    {_Style.CYAN}{_Style.BOLD}\u25b8 {option}{_Style.RST}")
            else:
                print(f"      {_Style.DIM}{option}{_Style.RST}")
        print()
        print(f"    {_Style.GRAY}\u2191/\u2193 to navigate \u00b7 Enter to select{_Style.RST}")

    _hide_cursor()
    try:
        _draw()
        while True:
            key = _get_key()
            if key == "ctrl_c":
                raise KeyboardInterrupt
            if key == "up" and selected > 0:
                selected -= 1
                _draw()
            elif key == "down" and selected < len(options) - 1:
                selected += 1
                _draw()
            elif key == "enter":
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
    print(f"\n  {_Style.GRAY}{msg}{_Style.RST}")
    while True:
        k = _get_key()
        if k in ("enter", "space"):
            return
        if k == "ctrl_c":
            raise KeyboardInterrupt


def _header(title):
    width = max(len(title) + 6, 40)
    pad_left = (width - len(title)) // 2
    pad_right = width - pad_left - len(title)
    print(f"\n  {_Style.CYAN}\u2554{'\u2550' * width}\u2557{_Style.RST}")
    print(f"  {_Style.CYAN}\u2551{' ' * pad_left}{_Style.BOLD}{title}{_Style.RST}{_Style.CYAN}{' ' * pad_right}\u2551{_Style.RST}")
    print(f"  {_Style.CYAN}\u255a{'\u2550' * width}\u255d{_Style.RST}\n")


def _divider():
    print(f"  {_Style.DIM}{'\u2500' * 44}{_Style.RST}")


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

def _hash_password(pw, salt=None):
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
        pw_hash, salt = _hash_password(password)
        conn.execute(
            "INSERT INTO users (username,password_hash,salt,created_at) VALUES (?,?,?,?)",
            (username, pw_hash, salt, datetime.now().isoformat()),
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
    pw_hash, _ = _hash_password(password, row[1])
    return (True, "ok") if pw_hash == row[0] else (False, "wrong_pw")


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
    questions = data.get("questions", [])
    if not questions:
        return None, (
            "The question bank is empty!\n\n"
            "  Add questions to 'questions.json' to get started.\n"
            "  See README.md for the expected format."
        )
    return questions, None


def _pick(questions, count, username):
    feedback = _load_feedback().get(username, {})
    weights = []
    for question in questions:
        feedback_value = feedback.get(question["question"], "neutral")
        weights.append({"liked": 1.5, "disliked": 0.3}.get(feedback_value, 1.0))
    count = min(count, len(questions))
    pool = list(range(len(questions)))
    active_weights = list(weights)
    chosen = []
    for _ in range(count):
        if not pool:
            break
        idx = random.choices(range(len(pool)), weights=active_weights, k=1)[0]
        chosen.append(questions[pool[idx]])
        pool.pop(idx)
        active_weights.pop(idx)
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


def _record_score(user, score, max_pts, correct, wrong, total):
    scores = _load_scores()
    if user not in scores:
        scores[user] = {"quizzes": [], "total_quizzes": 0, "total_correct": 0, "total_wrong": 0}
    user_data = scores[user]
    user_data["quizzes"].append({
        "date": datetime.now().isoformat(),
        "score": score, "max": max_pts, "correct": correct, "wrong": wrong, "total": total,
    })
    user_data["total_quizzes"] += 1
    user_data["total_correct"] += correct
    user_data["total_wrong"] += wrong
    _save_scores(scores)


def _stats(user):
    scores = _load_scores()
    user_data = scores.get(user)
    if not user_data or user_data["total_quizzes"] == 0:
        return {"quizzes_taken": 0, "correct": 0, "wrong": 0, "avg": 0.0, "best": 0.0}
    quiz_history = user_data["quizzes"]
    total_score = sum(q["score"] for q in quiz_history)
    total_max = sum(q["max"] for q in quiz_history)
    avg = (total_score / total_max * 100) if total_max else 0
    best = max((q["score"] / q["max"] * 100) if q["max"] else 0 for q in quiz_history)
    return {
        "quizzes_taken": user_data["total_quizzes"], "correct": user_data["total_correct"],
        "wrong": user_data["total_wrong"], "avg": round(avg, 1), "best": round(best, 1),
    }


# ── Feedback ─────────────────────────────────────────────────────────────────

def _load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return {}
    try:
        with open(FEEDBACK_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_feedback(data):
    tmp = FEEDBACK_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FEEDBACK_FILE)


def _record_feedback(user, question_text, value):
    data = _load_feedback()
    data.setdefault(user, {})[question_text] = value
    _save_feedback(data)


# ── Screens ──────────────────────────────────────────────────────────────────

def _screen_greeting():
    _clear()
    _header("Python Quiz App")
    print(f"  {_Style.WHITE}Welcome to the Python Quiz App!{_Style.RST}")
    print(f"  {_Style.DIM}Test your Python knowledge with interactive quizzes.{_Style.RST}")
    print()
    _divider()
    _wait()


def _screen_auth():
    while True:
        header = [
            "",
            f"  {_Style.CYAN}{_Style.BOLD}\u2554{'=' * 42}\u2557{_Style.RST}",
            f"  {_Style.CYAN}{_Style.BOLD}\u2551{'Python Quiz App':^42}\u2551{_Style.RST}",
            f"  {_Style.CYAN}{_Style.BOLD}\u255a{'=' * 42}\u255d{_Style.RST}",
            "",
            f"  {_Style.WHITE}What would you like to do?{_Style.RST}",
        ]
        choice = _fullscreen_menu(["Log In", "Create Account", "Quit"], header_lines=header)
        if choice == 0:
            result = _screen_login()
            if result:
                return result
        elif choice == 1:
            result = _screen_create()
            if result:
                return result
        else:
            return None


def _screen_login():
    _clear()
    _header("Log In")
    print(f"  {_Style.DIM}Leave username blank to go back.{_Style.RST}")
    print()

    username = _safe_input(f"  {_Style.WHITE}Username: {_Style.RST}").strip()
    if not username:
        return None

    while True:
        password = _masked_input(f"  {_Style.WHITE}Password: {_Style.RST}")
        if not password:
            return None

        success, error_code = _db_verify(username, password)
        if success:
            print(f"\n  {_Style.GREEN}{_Style.BOLD}\u2713 Welcome back, {username}!{_Style.RST}")
            _wait()
            return username

        if error_code == "not_found":
            _clear()
            _header("Account Not Found")
            print(f"  {_Style.RED}No account exists with username '{username}'.{_Style.RST}")
            print()
            print(f"  {_Style.YELLOW}Would you like to create an account instead?{_Style.RST}")
            print()
            choice = _inline_select(["Yes, create an account", "No, go back"])
            if choice == 0:
                return _screen_create(prefill=username)
            return None

        print(f"\n  {_Style.RED}\u2717 Incorrect password.{_Style.RST}")
        print()
        choice = _inline_select(["Try again", "Go back"])
        if choice == 1:
            return None
        _clear()
        _header("Log In")
        print(f"  {_Style.DIM}Username: {_Style.CYAN}{username}{_Style.RST}")
        print()


def _screen_create(prefill=None):
    _clear()
    _header("Create Account")

    if prefill:
        username = prefill
        print(f"  {_Style.WHITE}Username: {_Style.CYAN}{username}{_Style.RST}")
    else:
        print(f"  {_Style.DIM}Leave username blank to go back.{_Style.RST}")
        print()
        username = _safe_input(f"  {_Style.WHITE}Username: {_Style.RST}").strip()
        if not username:
            return None

    print(f"  {_Style.DIM}Password: min 8 chars, 1 uppercase, 1 lowercase, 1 digit{_Style.RST}")
    print(f"  {_Style.DIM}Leave password blank to go back.{_Style.RST}")
    password = _masked_input(f"  {_Style.WHITE}Password: {_Style.RST}")
    if not password:
        return None

    pw_err = _check_password(password)
    if pw_err:
        print(f"\n  {_Style.RED}{pw_err}{_Style.RST}")
        _wait()
        return None

    confirm = _masked_input(f"  {_Style.WHITE}Confirm:  {_Style.RST}")
    if password != confirm:
        print(f"\n  {_Style.RED}\u2717 Passwords do not match.{_Style.RST}")
        _wait()
        return None

    _clear()
    _header("Confirm Account")
    print(f"  {_Style.WHITE}Username:{_Style.RST}  {_Style.CYAN}{username}{_Style.RST}")
    print(f"  {_Style.WHITE}Password:{_Style.RST}  {_Style.CYAN}{'\u2022' * min(len(password), 12)}{_Style.RST}")
    print()
    print(f"  {_Style.YELLOW}Is this correct?{_Style.RST}")
    print()
    choice = _inline_select(["Yes, create my account", "No, take me back"])
    if choice == 1:
        return None

    success, message = _db_create(username, password)
    if success:
        print(f"\n  {_Style.GREEN}{_Style.BOLD}\u2713 {message}{_Style.RST}")
        _wait()
        return username

    print(f"\n  {_Style.RED}\u2717 {message}{_Style.RST}")
    _wait()
    return None


def _screen_dashboard(username):
    stats = _stats(username)
    header = [
        "",
        f"  {_Style.CYAN}{_Style.BOLD}\u2554{'=' * 42}\u2557{_Style.RST}",
        f"  {_Style.CYAN}{_Style.BOLD}\u2551{'Dashboard':^42}\u2551{_Style.RST}",
        f"  {_Style.CYAN}{_Style.BOLD}\u255a{'=' * 42}\u255d{_Style.RST}",
        "",
        f"  {_Style.WHITE}Welcome back, {_Style.CYAN}{_Style.BOLD}{username}{_Style.RST}{_Style.WHITE}!{_Style.RST}",
        "",
        f"  {_Style.WHITE}{_Style.BOLD}Your Stats{_Style.RST}",
        f"  {_Style.DIM}{'\u2500' * 30}{_Style.RST}",
    ]
    if stats["quizzes_taken"] == 0:
        header.append(f"  {_Style.DIM}No quizzes taken yet. Start one!{_Style.RST}")
    else:
        header += [
            f"  {_Style.WHITE}Quizzes Taken:  {_Style.CYAN}{stats['quizzes_taken']}{_Style.RST}",
            f"  {_Style.WHITE}Average Score:  {_Style.CYAN}{stats['avg']}%{_Style.RST}",
            f"  {_Style.WHITE}Best Score:     {_Style.CYAN}{stats['best']}%{_Style.RST}",
            f"  {_Style.WHITE}Total Correct:  {_Style.GREEN}{stats['correct']}{_Style.RST}",
            f"  {_Style.WHITE}Total Wrong:    {_Style.RED}{stats['wrong']}{_Style.RST}",
        ]
    header += ["", f"  {_Style.DIM}{'\u2500' * 30}{_Style.RST}", ""]
    choice = _fullscreen_menu(["Start New Quiz", "Log Out", "Quit"], header_lines=header)
    return ["quiz", "logout", "quit"][choice]


def _screen_setup(questions):
    _clear()
    _header("New Quiz")
    n = len(questions)
    print(f"  {_Style.WHITE}Available questions: {_Style.CYAN}{n}{_Style.RST}")
    print(f"  {_Style.DIM}Enter a number between 1 and {n}, or 'back' to return.{_Style.RST}")
    print()
    while True:
        ans = _safe_input(f"  {_Style.WHITE}How many questions? {_Style.RST}").strip()
        if ans.lower() == "back":
            return None
        try:
            v = int(ans)
            if 1 <= v <= n:
                return v
            print(f"  {_Style.RED}Enter a number between 1 and {n}.{_Style.RST}")
        except ValueError:
            print(f"  {_Style.RED}Invalid input. Enter a number (e.g. 5) or 'back'.{_Style.RST}")


# ── Quiz engine ──────────────────────────────────────────────────────────────

def _run_quiz(username, quiz_qs):
    """Returns (results_list, True) when the quiz finishes normally.
    Raises KeyboardInterrupt if the user abandons mid-quiz."""
    results = []
    total = len(quiz_qs)

    for i, question in enumerate(quiz_qs):
        _clear()
        difficulty = question.get("difficulty", "medium")
        diff_color = {"easy": _Style.GREEN, "medium": _Style.YELLOW, "hard": _Style.RED}.get(difficulty, _Style.WHITE)
        points = DIFF_PTS.get(difficulty, 1)

        print(f"\n  {_Style.CYAN}{_Style.BOLD}Question {i + 1} of {total}{_Style.RST}")
        print(f"  {diff_color}[{difficulty.upper()}]{_Style.RST} {_Style.DIM}\u00b7 {points} pt{'s' if points != 1 else ''} \u00b7 {question.get('category', 'General')}{_Style.RST}")
        print()
        print(f"  {_Style.WHITE}{_Style.BOLD}{question['question']}{_Style.RST}")
        print()
        _divider()
        print()

        question_type = question.get("type", "multiple_choice")
        user_answer = None

        if question_type == "multiple_choice":
            opts = question["options"]
            labels = [f"{chr(65 + j)}) {o}" for j, o in enumerate(opts)]
            idx = _inline_select(labels)
            user_answer = opts[idx]

        elif question_type == "true_false":
            idx = _inline_select(["True", "False"])
            user_answer = ["true", "false"][idx]

        elif question_type == "short_answer":
            user_answer = _safe_input(f"    {_Style.WHITE}Your answer: {_Style.RST}").strip()

        correct_answer = question["answer"]
        accepted = [correct_answer] + question.get("alternatives", [])
        typed = (user_answer or "").lower().strip()
        is_correct = any(typed == a.lower().strip() for a in accepted)

        # ── Result screen ────────────────────────────────────────────────
        _clear()
        print(f"\n  {_Style.CYAN}{_Style.BOLD}Question {i + 1} of {total}{_Style.RST}")
        print(f"  {_Style.DIM}{question['question']}{_Style.RST}")
        print()

        if is_correct:
            earned = points
            print(f"  {_Style.GREEN}{_Style.BOLD}\u2713 Correct!  +{points} pt{'s' if points != 1 else ''}{_Style.RST}")
            print()
            explanation = question.get("explanation", "")
            if explanation:
                print(f"  {_Style.WHITE}{explanation}{_Style.RST}")
        else:
            earned = 0
            user_display = (user_answer or "").capitalize() if question_type == "true_false" else (user_answer or "")
            correct_display = correct_answer.capitalize() if question_type == "true_false" else correct_answer

            print(f"  {_Style.RED}{_Style.BOLD}\u2717 Incorrect{_Style.RST}")
            print()
            print(f"  {_Style.RED}Your answer:    {user_display}{_Style.RST}")
            print(f"  {_Style.GREEN}Correct answer: {correct_display}{_Style.RST}")
            print()

            wrong_explanation = question.get("wrong_explanations", {}).get(
                user_answer, question.get("wrong_explanations", {}).get((user_answer or "").lower(), "")
            )
            if not wrong_explanation:
                wrong_explanation = question.get("wrong_explanation", "")
            if wrong_explanation:
                print(f"  {_Style.RED}Why '{user_display}' is wrong:{_Style.RST}")
                print(f"  {_Style.WHITE}{wrong_explanation}{_Style.RST}")
                print()

            explanation = question.get("explanation", "")
            if explanation:
                print(f"  {_Style.GREEN}Why '{correct_display}' is correct:{_Style.RST}")
                print(f"  {_Style.WHITE}{explanation}{_Style.RST}")

        results.append({
            "question": question["question"],
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "earned": earned,
            "possible": points,
            "difficulty": difficulty,
        })

        _wait()

        # ── Feedback screen ──────────────────────────────────────────────
        _clear()
        print(f"\n  {_Style.CYAN}{_Style.BOLD}Question {i + 1} Feedback{_Style.RST}")
        print(f"  {_Style.DIM}{question['question']}{_Style.RST}")
        print()
        print(f"  {_Style.WHITE}How did you feel about this question?{_Style.RST}")
        print()

        feedback_choice = _inline_select([
            "I liked this question.",
            "I did not like this question.",
            "I didn\u2019t mind this question.",
        ])
        _record_feedback(username, question["question"], {0: "liked", 1: "disliked", 2: "neutral"}[feedback_choice])

    return results, True


def _screen_summary(results, username):
    _clear()
    total_earned = sum(result["earned"] for result in results)
    total_possible = sum(result["possible"] for result in results)
    num_correct = sum(1 for result in results if result["is_correct"])
    num_wrong = len(results) - num_correct
    percentage = (total_earned / total_possible * 100) if total_possible else 0

    _header("Quiz Complete!")

    if percentage >= 80:
        print(f"  {_Style.GREEN}{_Style.BOLD}Excellent work!{_Style.RST}")
    elif percentage >= 60:
        print(f"  {_Style.YELLOW}{_Style.BOLD}Good effort!{_Style.RST}")
    else:
        print(f"  {_Style.RED}{_Style.BOLD}Keep practicing!{_Style.RST}")
    print()
    print(f"  {_Style.WHITE}Score: {_Style.CYAN}{_Style.BOLD}{total_earned}/{total_possible}{_Style.RST} {_Style.DIM}({percentage:.0f}%){_Style.RST}")
    print(f"  {_Style.GREEN}Correct: {num_correct}{_Style.RST}   {_Style.RED}Wrong: {num_wrong}{_Style.RST}")
    print()
    _divider()
    print()
    print(f"  {_Style.WHITE}{_Style.BOLD}Breakdown:{_Style.RST}")
    print()

    for result in results:
        icon = f"{_Style.GREEN}\u2713{_Style.RST}" if result["is_correct"] else f"{_Style.RED}\u2717{_Style.RST}"
        question_preview = result["question"][:45] + ("\u2026" if len(result["question"]) > 45 else "")
        points_label = f"+{result['earned']}" if result["is_correct"] else "+0"
        print(f"  {icon} {_Style.DIM}{question_preview}{_Style.RST}")
        print(f"    {_Style.DIM}[{result['difficulty']}] {points_label}{_Style.RST}")
    print()
    _divider()

    _record_score(username, total_earned, total_possible, num_correct, num_wrong, len(results))


def _screen_post_quiz():
    print()
    print(f"  {_Style.WHITE}What would you like to do next?{_Style.RST}")
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
            for line in err.split("\n"):
                print(f"  {_Style.RED}{line}{_Style.RST}")
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
                    print(f"\n  {_Style.CYAN}Goodbye, {username}! See you next time.{_Style.RST}\n")
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
                            print(f"\n  {_Style.YELLOW}Quiz interrupted. Your progress was not saved.{_Style.RST}")
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
        print(f"\n  {_Style.CYAN}Goodbye! Thanks for using Python Quiz App.{_Style.RST}\n")

    except KeyboardInterrupt:
        _show_cursor()
        _clear()
        print(f"\n  {_Style.CYAN}Goodbye! Thanks for using Python Quiz App.{_Style.RST}\n")


if __name__ == "__main__":
    main()
