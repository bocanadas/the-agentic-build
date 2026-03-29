# Code Review: Python Quiz CLI vs SPEC.md

## Acceptance Criteria

**1. [PASS] Empty question bank prints a friendly error and directs user to the correct screen.**

`main.py` lines 305–324: `_load_questions()` handles three cases — missing file, invalid JSON, and empty questions array — each with a clear message pointing to `README.md` for the expected format. The `main()` function (lines 763–770) renders the error in a header screen and exits cleanly.

---

**2. [PASS] User can login, take a quiz, return to dashboard, and see updated stats.**

`_screen_dashboard` calls `_stats(username)` which calls `_load_scores()` fresh from disk each time. After a quiz, `_screen_summary` (line 745) calls `_record_score` which writes to disk. When the user picks "Return to Dashboard", the loop on line 779 re-enters `_screen_dashboard`, reading the just-written scores.

---

**3. [PASS] User feedback is taken into account for future quiz question selection.**

`_pick()` (lines 327–345) loads per-user feedback and assigns weights: liked questions get 1.5x, disliked get 0.3x, neutral get 1.0x. Feedback is collected per-question on lines 701–706.

---

**4. [PASS] Wrong answer shows why the picked answer is wrong AND why the correct answer is right.**

Lines 656–679 display the user's answer and the correct answer, then show `wrong_explanations` for the selected wrong answer and `explanation` for the correct answer. All 20 questions in `questions.json` include both fields.

---

**5. [PASS] Logging in with a nonexistent account prompts an error and offers to create one.**

`_screen_login` lines 488–498: when `code == "not_found"`, the app shows "No account exists with username '...'" and offers to create one via an arrow-key menu, prefilling the username if accepted.

---

**6. [PASS] A quiz with hard questions yields a higher score than one without.**

`DIFF_PTS` (line 38) assigns easy=1, medium=2, hard=3. A correct hard answer earns 3x as much as a correct easy answer.

---

**7. [PASS] Creating an account with a duplicate username gives an error and does not overwrite.**

`_db_create` (lines 275–288) relies on the `UNIQUE` constraint on `username` (line 260). A duplicate triggers `sqlite3.IntegrityError`, returning "That username already exists." The existing row is never touched.

---

## Security & Git Hygiene

**8. [FAIL] No `.gitignore` file exists. Sensitive and generated files are at risk of being pushed publicly.**

There is no `.gitignore` in the repository. The following files will be committed and pushed the moment they are generated:

| File | Risk |
|------|------|
| `users.db` | Contains usernames and salted password hashes |
| `scores.json` | Contains encoded per-user score history |
| `feedback.json` | Contains plaintext usernames and question preferences |
| `__pycache__/` | Bytecode; should never be in source control |

---

**9. [FAIL] `__pycache__/main.cpython-313.pyc` is already tracked and committed in git.**

Confirmed via `git ls-files`. This compiled bytecode file is platform- and version-specific and should be removed from tracking.

---

**10. [WARN] `scores.json` uses base64+zlib obfuscation, not encryption.**

`_enc` (line 350) applies `zlib.compress` then `base64.b64encode`. This is trivially reversible with a single Python one-liner. The spec asks for the file to be "not human-readable and relatively secure." This satisfies "not human-readable" but barely qualifies as "relatively secure."

---

**11. [WARN] SHA-256 used for password hashing instead of a purpose-built KDF.**

`_hash_pw` (lines 269–272) uses `hashlib.sha256` with a random salt. SHA-256 is a fast hash, making brute-force feasible. Industry standard for passwords is `bcrypt`, `scrypt`, or `argon2`. The salt is properly generated via `secrets.token_hex`, which is good. For a local quiz app the risk is low, but it is a code quality concern.

---

**12. [WARN] No password strength requirements.**

`_screen_create` (line 519) accepts any non-empty string as a password. A user can create an account with password `"a"`. There is no minimum length check or complexity guidance.

---

## Bugs & Logic Errors

**13. [WARN] `_clear()` uses `os.system()` to invoke a shell.**

`_clear()` (lines 68–69) calls `os.system("cls"` or `"clear")`. While the command is hardcoded (not user-controlled), `os.system` invokes a full shell subprocess. Writing ANSI escape codes directly (`\033[2J\033[H`) would be faster and safer.

---

**14. [WARN] Short answer comparison is exact-match only (after lowering case).**

Line 640: `(user_ans or "").lower().strip() == correct_ans.lower().strip()`. If a user types `"len()"` instead of `"len"`, they are marked wrong. The question bank has only one short_answer question, but this is a usability concern for anyone extending it.

---

**15. [WARN] Redo quiz reuses the identical set of questions.**

`_pick` is called once on line 795, before the inner while-loop. If the user picks "Redo This Quiz", they get the exact same questions. Moving `_pick` inside the loop would make redos more interesting.

---

**16. [WARN] No atomic file writes for `scores.json` and `feedback.json`.**

`_save_scores` (lines 372–374) and `_save_fb` (lines 420–422) open the file with `"w"` and write directly. If the process is killed mid-write, the file could be left truncated or corrupted. A safer pattern is write-to-temp then `os.rename`.

---

## Code Quality

**17. [WARN] Terse/cryptic variable and function names reduce readability.**

Examples:
- `_enc` / `_dec` — could be `_encode_scores` / `_decode_scores`
- `_load_fb` / `_save_fb` / `_record_fb` — `fb` as "feedback" is non-obvious
- `_hash_pw` — `_hash_password` is clearer
- `sc`, `u`, `mx`, `nc`, `nw`, `te`, `tp`, `st` — single/two-letter names in `_stats`, `_record_score`, `_screen_summary`
- `_C` class — could be `_Colors` or `_Style`

---

**18. [PASS] The README is clear and covers all essential information.**

`README.md` explains quick start, how it works, scoring, file descriptions, and question format. No external dependencies needed.

---

**19. [PASS] Question bank is human-readable and easily editable.**

`questions.json` is well-structured with 20 questions across multiple categories, types, and difficulties. All questions include explanations for both correct and wrong answers.

---

**20. [PASS] Screen clearing prevents UI clutter between sections.**

Every screen transition calls `_clear()` or uses `_fullscreen_menu` (which clears internally). The intro, auth, dashboard, quiz, feedback, and summary screens are all visually isolated.

---

**21. [PASS] Ctrl+C is handled gracefully with a goodbye message.**

The outermost `try/except KeyboardInterrupt` on line 817 catches escapes at any level. Mid-quiz interrupts are separately caught on lines 800–807, printing "Quiz interrupted. Your progress was not saved."

---

**22. [PASS] Quiz interrupted mid-way does not save score.**

`_record_score` is only called inside `_screen_summary` (line 745), which is only reached after `_run_quiz` returns normally. A Ctrl+C during the quiz is caught on line 800 and breaks out of the loop without calling `_screen_summary`.

---

**23. [PASS] Arrow-key navigation works for all menus and answer selection.**

`_inline_select` and `_fullscreen_menu` both support up/down arrows + Enter. Handles both Unix (termios) and Windows (msvcrt) terminals.

---

**24. [PASS] Difficulty levels are displayed alongside each question.**

Lines 615–616 show difficulty color-coded (green/yellow/red) with point value and category.

---

**25. [PASS] Three feedback options presented as specified.**

Lines 701–706 present the exact three options from the spec: "I liked this question.", "I did not like this question.", "I didn't mind this question."

---

## UX Issues

**26. [WARN] No way to go "back" from the username/password input prompts.**

In `_screen_login` and `_screen_create`, once the user is prompted for input, the only escape is submitting an empty value (which shows an error) or Ctrl+C. There is no "type 'back' to return" hint like in `_screen_setup`.

---

**27. [WARN] Wrong password flow returns to the auth menu with no retry option.**

Lines 500–502: returning `None` kicks the user back to the "Log In / Create Account / Quit" menu. They must re-select "Log In" and re-type their username. Offering an inline retry would be friendlier.

---

## Summary Table

| # | Verdict | Finding |
|---|---------|---------|
| 1 | **PASS** | Empty question bank error handling |
| 2 | **PASS** | Login → quiz → dashboard stats update |
| 3 | **PASS** | Feedback influences question selection |
| 4 | **PASS** | Wrong answer shows dual explanations |
| 5 | **PASS** | Nonexistent account → error + create offer |
| 6 | **PASS** | Hard questions yield higher scores |
| 7 | **PASS** | Duplicate username rejected, old account safe |
| 8 | **FAIL** | No `.gitignore` — `users.db`, `scores.json`, `feedback.json`, `__pycache__/` will be pushed |
| 9 | **FAIL** | `__pycache__/*.pyc` already committed and tracked |
| 10 | **WARN** | Scores "security" is trivially reversible obfuscation |
| 11 | **WARN** | SHA-256 for passwords instead of bcrypt/argon2 |
| 12 | **WARN** | No password strength requirements |
| 13 | **WARN** | `os.system()` for screen clear |
| 14 | **WARN** | Short answer exact-match only |
| 15 | **WARN** | Redo quiz reuses identical questions |
| 16 | **WARN** | No atomic file writes |
| 17 | **WARN** | Terse/cryptic variable names |
| 18 | **PASS** | README quality |
| 19 | **PASS** | Question bank format and content |
| 20 | **PASS** | Screen clearing prevents clutter |
| 21 | **PASS** | Ctrl+C handled with goodbye |
| 22 | **PASS** | Mid-quiz quit doesn't save |
| 23 | **PASS** | Arrow-key navigation throughout |
| 24 | **PASS** | Difficulty shown per question |
| 25 | **PASS** | Three feedback options as specified |
| 26 | **WARN** | No "back" option from input prompts |
| 27 | **WARN** | Wrong password kicks back to main menu |

**Bottom line:** All 7 acceptance criteria **pass**. The two **FAIL** items are both git hygiene issues — no `.gitignore` and an already-committed `__pycache__` — meaning sensitive user data (`users.db` with password hashes) would be pushed to a public repo. The 10 **WARN** items are a mix of security hardening, code quality, and UX polish that would strengthen the project but are not spec violations.
