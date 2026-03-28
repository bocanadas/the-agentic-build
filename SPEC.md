Project Goal: A command-line Python quiz app with a local login system that reads questions from a JSON file, quizzes users, tracks scores and performance statistics securely (in a non-human-readable format), allows users to provide feedback on questions to influence future quiz selections, and saves results.

# Behavior description
- The app greets the user
- asks them to log in or create an account
- User can use up and down arrow keys and make their selection on the current highlighted option and pressing Enter
- if user selects to log in make them type their username and password on different lines
- if user selects to create make them type create username and password on different lines and add a confirming question that if they want to make sure that's their user and password and if not take them back if so continue and create the account
- Bring them to a simple dashboard like interface with their current stats and wether they'd start a new quiz
- Asks how many questions they want 
- Randomly selects that many from the question bank taking into consideration feedback aswell
- Displays each question with a difficulty level that affect scoring
- Display the options out of 4 only 1 is right if mutiple choice or display the true or false
- User can use up and down arrow keys and make their selection on the current highlighted option and pressing Enter
- After a user makes a selection if they got the correct answer, indicate to the user that is correct and an explanation why it's correct. If a user get's the answer wrong, show their answer and the correct answer and show both the selected wrong answer and the selected correct answer. Add an explanation why their answer is wrong and why the correct answer is correct.
- After the user reads receives a key stroke like space or enter move on to a screen that receives user feedback on the question. Give them 3 options: "I liked this question.", "I did not like this question.", "I didn't mind this question."
- After the user gives their feedback wether it be it move onto the next question with this same process until the end of the quiz
- After ending the quiz show a summary to the user how did they did 
- prompt the user wether they'd like to return to the home screen dashboard or redo the quiz

# Data format
The question bank should be a JSON file using the format below:

`{
  "questions": [
    {
      "question": "What keyword is used to define a function in Python?",
      "type": "multiple_choice",
      "options": ["func", "define", "def", "function"],
      "answer": "def",
      "category": "Python Basics",
      "difficulty": "easy"
    },
    {
      "question": "A list in Python is immutable.",
      "type": "true_false",
      "answer": "false",
      "category": "Data Structures",
      "difficulty": "easy"
    },
    {
      "question": "What built-in function returns the number of items in a list?",
      "type": "short_answer",
      "answer": "len",
      "category": "Python Basics",
      "difficulty": "easy"
    },
    {
      "question": "What is the time complexity of looking up a key in a Python dictionary?",
      "type": "multiple_choice",
      "options": ["O(n)", "O(log n)", "O(1)", "O(n^2)"],
      "answer": "O(1)",
      "category": "Data Structures",
      "difficulty": "medium"
    },
    {
      "question": "In Python, a decorator is a function that takes another function as an argument and extends its behavior without modifying it.",
      "type": "true_false",
      "answer": "true",
      "category": "Advanced Python",
      "difficulty": "hard"
    }
  ]
}`

File structure:
- main.py: This file should handle the main quiz logic and print outputs to the user's CLI
- questions.json: This file should house the question bank and all metadata related to the question
- users.db: This SQLite datebase handle the local login system logic. Hold the password and username of the app's users
- feedback.json: This file stores user feedback on questions
- scores.json: This file tracks per-user history and stats
- README.md: This file should be a simple breakdown of what the CLI app is and how to make it work

Error handling: 
- What happens if the JSON file is missing? Handle the error gracefully and make it clear to the user what is wrong and how to fix it
- If the user enters invalid input? Direct the user to input valid input and add examples be concise dont take up too much UI space. 
- If the user terminate the app with control + c on mac or windows equivalent make sure to add a message and say goodbye if possible.
- if the user quits in the middle of a quiz dont save it and dont count it.
- if the user enters the wrong password or username let them know it's invalid.


Required features:
- A local login system that prompts users for a username and password (or allows them to enter a new username and password). The passwords should not be easily discoverable.
- A score history file that tracks performance and other useful statistics over time for each user. This file should not be human-readable and should be relatively secure. (This means someone could look at the file and perhaps find out usernames but not passwords or scores.)
- Users should somehow be able to provide feedback on whether they like a question or not, and this should inform what questions they get next.
- The questions should exist in their own human-readable .json file so that they can be easily modified. (This lets you use the project for studying other subjects if you wish; all you have to do is generate the question bank.)
- Note: None of this requires a backend, HTML, CSS, a graphical user interface, or the use of any APIs. Everything is local. If the project uses any of these things, you might be over-engineering it.
- Make sure the CLI doesnt look too crowded add some space wherever needed so each part of the app is clearly seperate (e.g. I don't want to see part of the intro sequence when i'm on the first question. this could be achieved by clearing the screen or other best practices.)
- I would like the options and the general interface to be well formatted for human interaction.
- Difficulty levels that affect scoring

Acceptance criteria:
- Running the app with an empty question bank prints a friendly error and directs the user to the correct screen.
- The user can login and start a quiz and then return to the main screen and see their updated stats
- The user's feedback is implemented and taken into account for future quiz questions
- The user selects the wrong answer on a question and see both why the answer they picked is wrong and why the correct answer is right.
- Running the app and logging in into an account that doesn't exist prompts and error message that states your account does not exist and prompt you to make one
- A quiz with a hard question/s should have a higher score than one that didn't include any hard/s.
- Creating an account with a username that already exists gives an error and doesn't overwrite the old account













