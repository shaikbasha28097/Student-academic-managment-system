# ============================================================
# config.py – SAMS 4th Year Project Configuration
# ============================================================

import os

# Flask Secret Key
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-development-secret")

# ── Database ─────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "127.0.0.1")
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "drk_college")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))

# ── Email / OTP (Gmail SMTP) ─────────────────────────────────
# Fill in your Gmail credentials to enable OTP reset emails.
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "")

# ── File Uploads ─────────────────────────────────────────────
UPLOAD_FOLDER  = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip"}
