# Python Quiz App

A command-line Python quiz application with a local login system, score tracking, question feedback, and difficulty-based scoring.

## Quick Start

```bash
pip install -r requirements.txt

python main.py 

# If Python 3 installed 
python3 main.py
```

Requires Python 3.8+ and one external dependency (`cryptography`) for AES-encrypted score storage.

## How It Works

1. **Create an account** or **log in** with an existing one.
2. From the **dashboard**, view your stats and start a new quiz.
3. Choose how many questions you want.
4. Answer each question using the **arrow keys** (↑/↓) and **Enter**.
5. After each answer, see whether you were correct along with explanations.
6. Give feedback on each question — this influences future question selection.
7. View your **score summary** at the end, then return to the dashboard or redo the quiz.

## Scoring

Questions have three difficulty levels that affect point values:

| Difficulty | Points |
|------------|--------|
| Easy       | 1      |
| Medium     | 2      |
| Hard       | 3      |

## Files

| File               | Description                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `main.py`          | Main application that handles all quiz logic and the CLI interface          |
| `questions.json`   | Human-readable question bank (edit this to add/change questions)            |
| `users.db`         | SQLite database storing usernames and hashed passwords (auto-created)       |
| `scores.json`      | AES-encrypted per-user score history (auto-created)                         |
| `.scores.key`      | Fernet encryption key for scores — **do not share or commit** (auto-created)|
| `feedback.json`    | Per-user question feedback used to personalize future quizzes (auto-created)|

## Question Format

Add or edit questions in `questions.json`. Each question follows this structure:

```json
{
  "question": "Your question text here",
  "type": "multiple_choice",
  "options": ["A", "B", "C", "D"],
  "answer": "C",
  "category": "Topic Name",
  "difficulty": "easy",
  "explanation": "Why the correct answer is correct.",
  "wrong_explanations": {
    "A": "Why A is wrong.",
    "B": "Why B is wrong.",
    "D": "Why D is wrong."
  }
}
```

Supported question types: `multiple_choice`, `true_false`, `short_answer`.
