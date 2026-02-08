# 🔐 Google Service Account Setup

This project uses a **Google Service Account** to access Google Sheets securely.

## Where do I get `service_account.json`?

1. Open **Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Create or select a project (e.g., `notion-automation`).
3. Enable APIs:

   * Google Sheets API
   * Google Drive API
4. Go to **IAM & Admin → Service Accounts**.
5. Click **Create Service Account**.

   * Name: `notion-bot`
   * Role: **Editor**
6. Open the service account → **Keys** → **Add Key** → **Create new key** → **JSON**.
7. Download the file. This downloaded file is **`service_account.json`**.

⚠️ Treat this file like a password.

* ❌ Do NOT upload it to GitHub
* ✅ Use it locally only, or store its **content** in GitHub Secrets

## How GitHub Actions uses it (No file upload)

* Copy the **full JSON content** (from `{` to `}`)
* Add a GitHub Secret named **`SERVICE_ACCOUNT_JSON`**
* During the workflow run, GitHub creates a temporary file:

  ```bash
  service_account.json
  ```
* The file exists only during the job and is deleted automatically.

The Python code uses:

```python
SERVICE_ACCOUNT_FILE = "service_account.json"
```

---

# 📄 Google Sheet Setup

## Create the Sheet

1. Create a new Google Sheet (e.g., **Daily Time Tracker**).
2. Copy the **Spreadsheet ID** from the URL and save it as a secret.

## Share Sheet with Service Account (MANDATORY)

1. Open `service_account.json`.
2. Copy the value of `client_email`, e.g.:

   ```json
   "client_email": "notion-bot@project-id.iam.gserviceaccount.com"
   ```
3. Open the Google Sheet → **Share**.
4. Paste the email.
5. Give **Editor** permission.

❌ If this step is skipped, you will get **403 Permission denied**.

## Required GitHub Secrets

Add these in **GitHub → Settings → Secrets and variables → Actions**:

* `SERVICE_ACCOUNT_JSON` → Full JSON content
* `SPREADSHEET_ID` → Google Sheet ID
* `DAILY_SHEET` → Sheet tab name

---

## Final Notes

* ❌ Never commit `service_account.json` or `.env`
* ✅ Use GitHub Secrets for production
* ✅ Once set, the automation runs daily without manual action
