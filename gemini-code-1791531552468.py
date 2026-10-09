import os
import sqlite3
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI(title="PocketSmart AI API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI Client (Make sure OPENAI_API_KEY environment variable is set)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"))

# Database setup
DB_NAME = "pocketsmart.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Pydantic Schemas
class ExpenseCreate(BaseModel):
    title: str
    amount: float
    category: str
    date: str

class ExpenseResponse(ExpenseCreate):
    id: int

class BudgetQuery(BaseModel):
    monthly_income: float
    savings_goal: float

# Routes
@app.post("/expenses", response_model=ExpenseResponse)
def add_expense(expense: ExpenseCreate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO expenses (title, amount, category, date) VALUES (?, ?, ?, ?)",
        (expense.title, expense.amount, expense.category, expense.date)
    )
    expense_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {**expense.dict(), "id": expense_id}

@app.get("/expenses", response_model=List[ExpenseResponse])
def get_expenses():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, amount, category, date FROM expenses ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "amount": r[2], "category": r[3], "date": r[4]} for r in rows]

@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return {"message": "Expense deleted successfully"}

@app.post("/recommendations")
def get_recommendations(query: BudgetQuery):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT title, amount, category FROM expenses")
    expenses = cursor.fetchall()
    conn.close()

    if not expenses:
        return {"recommendation": "Please log a few expenses first so PocketSmart AI can analyze your spending patterns!"}

    total_spent = sum(e[1] for e in expenses)
    summary = "\n".join([f"- {e[0]}: ${e[1]} ({e[2]})" for e in expenses])

    prompt = f"""
    You are PocketSmart AI, an expert financial coach.
    Analyze the user's current spending against their monthly income and savings goal.

    User Profile:
    - Monthly Income: ${query.monthly_income}
    - Savings Goal: ${query.savings_goal}
    - Total Spent So Far: ${total_spent}

    Current Expenses Logged:
    {summary}

    Provide 3 actionable, specific recommendation bullets on where they can trim budget, 
    optimize spending, and guarantee hitting their savings goal this month. Keep it encouraging and direct.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        recommendation_text = response.choices[0].message.content
    except Exception as e:
        recommendation_text = f"AI Service temporary unavailable. Summary: You spent ${total_spent} out of ${query.monthly_income} income."

    return {"recommendation": recommendation_text}