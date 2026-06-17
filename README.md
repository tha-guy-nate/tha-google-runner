# tha-google-runner

[![CI](https://github.com/tha-guy-nate/tha-google-runner/actions/workflows/ci.yml/badge.svg)](https://github.com/tha-guy-nate/tha-google-runner/actions/workflows/ci.yml)

A Tabular Helper API library that wraps Google Sheets, Docs, Drive, Slides, and Gmail with a typed, consistent interface.

## Install

```bash
pip install tha-google-runner
```

## Authentication setup

`tha-google-runner` uses your **personal Google account** — not a service account. There are two ways to authenticate. Option 1 is recommended for most users since it works with private files and doesn't require any additional tooling.

> **Cost note:** This package is free and open source. The Google APIs it uses are also free for normal scripting workloads — Google provides a generous free tier that the vast majority of users will never exceed. Google Cloud Console may ask for a credit card when you first create a project to verify your identity, but **Google does not charge you** for the APIs used here. Any billing questions are between you and Google — not this package.

### Option 1 — OAuth2 client secrets (recommended)

This is the standard path for accessing your own private Google files.



**Step 1 — Create a Google Cloud project**

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click the project dropdown → **New Project** → give it any name → **Create**

**Step 2 — Enable the required APIs**

In your new project, go to **APIs & Services** → **Enable APIs and Services** and enable:
- **Google Sheets API**
- **Google Drive API**
- **Google Docs API** (only needed if you use `ThaDocs`)
- **Google Slides API** (only needed if you use `ThaSlides`)
- **Gmail API** (only needed if you use `ThaGmail`)

**Step 3 — Create OAuth2 credentials**

1. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
2. If prompted, configure the **OAuth consent screen** first:
   - User type: **External** → fill in app name and your email → save
3. Application type: **Desktop app** → give it a name → **Create**
4. Click **Download JSON** and save the file (e.g., `client_secrets.json`)

**Step 4 — Run the auth setup CLI**

```bash
tha-google-init --credentials client_secrets.json
```

This opens a browser window for you to grant access. After that, the token is cached at `~/.config/tha-google-runner/token.json` and no browser is needed on subsequent runs.

You can also pass the credentials file directly at runtime:

```python
sheets = ThaSheets(credentials_file="client_secrets.json")
```

> **Re-authentication note:** If you add `ThaGmail` to an existing setup, the Gmail scope was not included in your previous token. Run `tha-google-init` again (or pass `credentials_file=` on first use) to grant the new scope and refresh your cached token.

### Option 2 — Application Default Credentials (ADC)

Use this only if you're accessing **publicly shared** files or working in a Google Cloud environment (e.g., Cloud Run, Vertex AI). ADC via `gcloud` does not grant access to your personal private Drive/Sheets/Docs/Gmail.

```bash
gcloud auth application-default login
```

A browser window opens, credentials are saved to your machine, and any `Tha*` class works with no arguments. Requires the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install).

---

## Quick start

### ThaSheets

```python
from tha_google_runner import ThaSheets

sheets = ThaSheets()  # uses cached OAuth2 token (see Option 1 above); or pass credentials_file="client_secrets.json"

# Read all rows (first row is headers)
rows = sheets.read(spreadsheet_id="your-spreadsheet-id")

# Append new rows (writes headers automatically if the sheet is empty)
sheets.append_rows(
    [{"name": "Alice", "score": 95}, {"name": "Bob", "score": 82}],
    spreadsheet_id="your-spreadsheet-id",
)

# Append using raw lists — header row auto-detected and dropped if it matches the sheet
sheets.append_rows(
    [["name", "score"], ["Alice", 95]],
    spreadsheet_id="your-spreadsheet-id",
)

# Overwrite the entire sheet
sheets.update_rows(
    [{"name": "Alice", "score": 95}],
    spreadsheet_id="your-spreadsheet-id",
)

# Upsert by key — inserts new rows, updates existing ones
sheets.upsert_rows(
    [{"id": "1", "name": "Alice", "score": 99}],
    key="id",
    spreadsheet_id="your-spreadsheet-id",
)

# Create a new spreadsheet and get its ID
spreadsheet_id = sheets.create("My Report", rows=[{"col": "val"}])

# Clear a sheet
sheets.clear(spreadsheet_id="your-spreadsheet-id")
```

> **Finding your spreadsheet ID:** It's the long string in the URL between `/d/` and `/edit`.
> `https://docs.google.com/spreadsheets/d/<spreadsheet-id>/edit`
>
> You can also pass `url=` instead of `spreadsheet_id=` to any method and the ID will be extracted automatically.

### ThaDocs

```python
from tha_google_runner import ThaDocs

docs = ThaDocs()  # uses cached OAuth2 token (see Option 1 above); or pass credentials_file="client_secrets.json"

# Read all text in a document
text = docs.read(doc_id="your-document-id")

# Append text to the end of a document
docs.append("\nNew paragraph.", doc_id="your-document-id")

# Insert text immediately after a specific string
docs.insert_after("Appendix", after="See also:", doc_id="your-document-id")

# Replace all occurrences of a string
count = docs.replace(old_text="foo", new_text="bar", doc_id="your-document-id")
```

> **Finding your document ID:** It's the long string in the URL between `/d/` and `/edit`.
> `https://docs.google.com/document/d/<document-id>/edit`
>
> You can also pass `url=` instead of `doc_id=` to any method.

### ThaDrive

```python
from tha_google_runner import ThaDrive

drive = ThaDrive()  # uses cached OAuth2 token (see Option 1 above); or pass credentials_file="client_secrets.json"

# List all non-trashed files
files = drive.list_files()

# List files in a specific folder
files = drive.list_files(folder_id="folder-id")

# Search by name (contains by default)
results = drive.search("Q1 Report")

# Search by exact name
results = drive.search("Q1 Report.pdf", exact=True)

# Get file metadata
meta = drive.get(file_id="file-id")

# Export a Google Workspace file (Docs, Sheets, Slides) to a local format
pdf_bytes = drive.export(file_id="file-id", mime_type="application/pdf")

# Download a regular uploaded file (PDFs, images, etc.)
content = drive.download(file_id="file-id")
with open("output.pdf", "wb") as f:
    f.write(content)
```

> You can pass `url=` instead of `file_id=` to any method.

### ThaSlides

```python
from tha_google_runner import ThaSlides

slides = ThaSlides()  # uses cached OAuth2 token (see Option 1 above); or pass credentials_file="client_secrets.json"

# Read all slides — returns a list of dicts, one per slide
deck = slides.read(presentation_id="your-presentation-id")
for slide in deck:
    print(slide["index"], slide["title"], slide["body"], slide["notes"])

# Get the raw API response
raw = slides.get(presentation_id="your-presentation-id")
```

Each dict in the returned list has:

| Key | Type | Description |
|---|---|---|
| `index` | `int` | 0-based slide position |
| `object_id` | `str` | Google's internal slide ID |
| `title` | `str` | Title placeholder text (empty string if none) |
| `body` | `str` | Body/subtitle placeholder text (empty string if none) |
| `notes` | `str` | Speaker notes text (empty string if none) |

> You can also pass `url=` instead of `presentation_id=`.

### ThaGmail

```python
from tha_google_runner import ThaGmail

gmail = ThaGmail()  # uses cached OAuth2 token (see Option 1 above); or pass credentials_file="client_secrets.json"

# Send a plain-text email
gmail.send(to="recipient@example.com", subject="Hello", body="Hi there!")

# Send to multiple recipients with CC and BCC
gmail.send(
    to=["alice@example.com", "bob@example.com"],
    subject="Report",
    body="<h1>Done</h1>",
    cc="manager@example.com",
    html=True,
)

# List messages (returns up to 100 by default)
messages = gmail.list_messages()

# Filter with a Gmail query string
messages = gmail.list_messages(query="from:boss@example.com is:unread", max_results=20)

# Read a message by ID
msg = gmail.read(message_id=messages[0]["id"])
print(msg["subject"], msg["from_"], msg["body"])
```

Each dict returned by `read()` has:

| Key | Type | Description |
|---|---|---|
| `id` | `str` | Message ID |
| `thread_id` | `str` | Thread ID |
| `subject` | `str` | Subject header |
| `from_` | `str` | From header |
| `to` | `str` | To header |
| `date` | `str` | Date header |
| `body` | `str` | Plain-text body (falls back to HTML if no plain-text part) |

---

## Row input formats

All write methods (`append_rows`, `update_rows`, `upsert_rows`, `create`, `add_sheet`) accept either format:

**`list[dict]`** — keys are column headers:
```python
[{"name": "Alice", "score": 95}, {"name": "Bob", "score": 82}]
```

**`list[list]`** — raw rows with automatic header detection:
```python
[["name", "score"], ["Alice", 95], ["Bob", 82]]
```

Header detection for `list[list]` input:

| Sheet state | First row matches existing headers? | Result |
|---|---|---|
| Has data | Yes | Header row dropped, rest appended as data |
| Has data | No | All rows treated as data |
| Empty / being replaced | — | First row always becomes headers |

---

## API

### `ThaSheets(*, credentials_file=None, token_file=None)`

```python
ThaSheets(
    credentials_file: str | None = None,  # path to client_secrets.json; None uses ADC
    token_file: str | None = None,         # override token cache path (OAuth2 only)
)
```

The Google client is built lazily on first use and cached for the lifetime of the instance.
After any write, `sheets.rows` is set to the data rows that were written (as `list[dict]`).

---

### `read(*, spreadsheet_id=None, url=None, sheet_name=None) -> list[dict]`

Read all rows. The first row is treated as headers; each subsequent row becomes a `dict`.

```python
rows = sheets.read(spreadsheet_id="spreadsheet-id")
rows = sheets.read(url="https://docs.google.com/spreadsheets/d/.../edit")
rows = sheets.read(spreadsheet_id="spreadsheet-id", sheet_name="Q1 Data")
```

---

### `append_rows(rows, *, spreadsheet_id=None, url=None, sheet_name=None) -> int`

Append rows to an existing sheet. Returns the number of rows appended.

- If the sheet is empty, the headers are written first.
- Missing keys in a row are filled with `""`.

```python
count = sheets.append_rows(
    [{"name": "Alice", "score": 95}],
    spreadsheet_id="spreadsheet-id",
)
```

---

### `update_rows(rows, *, spreadsheet_id=None, url=None, sheet_name=None) -> int`

Overwrite all data in a sheet. Clears the sheet first, then writes headers + rows. Returns the number of rows written. Passing an empty list clears the sheet and returns `0`.

```python
count = sheets.update_rows(
    [{"name": "Alice", "score": 95}],
    spreadsheet_id="spreadsheet-id",
)
```

---

### `upsert_rows(rows, *, key, spreadsheet_id=None, url=None, sheet_name=None, on_conflict="update_all") -> int`

Insert new rows and update existing ones matched by key. Returns the number of rows upserted.

- `key` — column name (str) or list of column names for composite keys
- New columns in incoming rows are appended to the sheet automatically
- `on_conflict` controls what happens when multiple existing rows match the same key:
  - `"update_all"` (default) — update every matching row
  - `"update_first"` — update only the first match
  - `"update_last"` — update only the last match
  - `"skip"` — leave duplicates untouched
  - `"raise"` — raise `GoogleError`

```python
count = sheets.upsert_rows(
    [{"id": "1", "name": "Alice", "score": 99}],
    key="id",
    spreadsheet_id="spreadsheet-id",
)

# Composite key
count = sheets.upsert_rows(rows, key=["year", "month"], spreadsheet_id="spreadsheet-id")
```

---

### `create(title, *, rows=None, sheet_name="Sheet1") -> str`

Create a new spreadsheet. Returns the new spreadsheet's ID.

```python
sid = sheets.create("My Report")
sid = sheets.create("My Report", rows=[{"col": "val"}], sheet_name="Data")
```

---

### `delete(*, spreadsheet_id=None, url=None) -> None`

Permanently delete a spreadsheet.

```python
sheets.delete(spreadsheet_id="spreadsheet-id")
```

---

### `list_sheets(*, spreadsheet_id=None, url=None) -> list[str]`

Return the names of all worksheets in a spreadsheet.

```python
names = sheets.list_sheets(spreadsheet_id="spreadsheet-id")
# ["Sheet1", "Q1 Data", "Archive"]
```

---

### `add_sheet(sheet_name, *, spreadsheet_id=None, url=None, rows=None) -> None`

Add a new worksheet to an existing spreadsheet. Optionally write initial rows.

```python
sheets.add_sheet("Q2 Data", spreadsheet_id="spreadsheet-id")
sheets.add_sheet("Q2 Data", spreadsheet_id="spreadsheet-id", rows=[{"col": "val"}])
```

---

### `delete_sheet(sheet_name, *, spreadsheet_id=None, url=None) -> None`

Delete a worksheet from a spreadsheet.

```python
sheets.delete_sheet("Archive", spreadsheet_id="spreadsheet-id")
```

---

### `share(email, *, spreadsheet_id=None, url=None, role="reader") -> None`

Share a spreadsheet with a user. `role` can be `"reader"`, `"writer"`, or `"owner"`.

```python
sheets.share("colleague@example.com", spreadsheet_id="spreadsheet-id", role="writer")
```

---

### `clear(*, spreadsheet_id=None, url=None, sheet_name=None) -> None`

Clear all data in a sheet. Resets `sheets.rows` to `[]`.

```python
sheets.clear(spreadsheet_id="spreadsheet-id")
sheets.clear(spreadsheet_id="spreadsheet-id", sheet_name="Archive")
```

---

## ThaDocs API

### `ThaDocs(*, credentials_file=None, token_file=None)`

```python
ThaDocs(
    credentials_file: str | None = None,  # path to client_secrets.json; None uses ADC
    token_file: str | None = None,         # override token cache path (OAuth2 only)
)
```

The Google Docs client is built lazily on first use and cached for the lifetime of the instance.
After a `read()`, `docs.content` is set to the full plain text of the document.

---

### `read(*, doc_id=None, url=None) -> str`

Read the full plain text of a document. Sets `docs.content`.

```python
text = docs.read(doc_id="document-id")
text = docs.read(url="https://docs.google.com/document/d/.../edit")
```

---

### `append(text, *, doc_id=None, url=None) -> None`

Append text to the end of a document.

```python
docs.append("\nNew section.", doc_id="document-id")
```

---

### `insert_after(text, *, after, doc_id=None, url=None) -> None`

Insert text immediately after the first occurrence of `after` in the document. Raises `GoogleError` if `after` is not found.

```python
docs.insert_after(" (updated)", after="Section 2", doc_id="document-id")
```

---

### `replace(*, old_text, new_text, doc_id=None, url=None, match_case=True) -> int`

Replace all occurrences of `old_text` with `new_text`. Returns the number of replacements made.

```python
count = docs.replace(old_text="draft", new_text="final", doc_id="document-id")
count = docs.replace(old_text="Draft", new_text="Final", doc_id="document-id", match_case=False)
```

---

## ThaDrive API

### `ThaDrive(*, credentials_file=None, token_file=None)`

```python
ThaDrive(
    credentials_file: str | None = None,
    token_file: str | None = None,
)
```

---

### `list_files(*, folder_id=None, query=None) -> list[dict]`

List all non-trashed files. Optionally filter by folder or provide a raw Drive query string.

```python
files = drive.list_files()
files = drive.list_files(folder_id="folder-id")
files = drive.list_files(query="mimeType = 'application/pdf'")
```

---

### `search(name, *, exact=False) -> list[dict]`

Search files by name. Uses `contains` by default; pass `exact=True` for an exact match.

```python
results = drive.search("Q1 Report")
results = drive.search("Q1 Report.pdf", exact=True)
```

---

### `get(*, file_id=None, url=None) -> dict`

Get metadata for a single file.

```python
meta = drive.get(file_id="file-id")
```

---

### `export(*, file_id=None, url=None, mime_type="application/pdf") -> bytes`

Export a Google Workspace file (Docs, Sheets, Slides) to a different format. Returns the file content as bytes.

```python
pdf = drive.export(file_id="file-id", mime_type="application/pdf")
xlsx = drive.export(file_id="file-id", mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

> Use `export` for Google Workspace files. Use `download` for regular uploaded files (PDFs, images, etc.).

---

### `download(*, file_id=None, url=None) -> bytes`

Download a regular (non-Google Workspace) file stored in Drive. Returns the file content as bytes.

```python
content = drive.download(file_id="file-id")
with open("report.pdf", "wb") as f:
    f.write(content)
```

---

## ThaSlides API

### `ThaSlides(*, credentials_file=None, token_file=None)`

```python
ThaSlides(
    credentials_file: str | None = None,
    token_file: str | None = None,
)
```

---

### `read(*, presentation_id=None, url=None) -> list[dict]`

Read all slides. Returns one dict per slide with `index`, `object_id`, `title`, `body`, and `notes`.

```python
deck = slides.read(presentation_id="presentation-id")
for slide in deck:
    print(f"Slide {slide['index']}: {slide['title']}")
    print(slide['body'])
    print(slide['notes'])
```

---

### `get(*, presentation_id=None, url=None) -> dict`

Return the raw API response for the presentation.

```python
raw = slides.get(presentation_id="presentation-id")
```

---

## ThaGmail API

### `ThaGmail(*, credentials_file=None, token_file=None)`

```python
ThaGmail(
    credentials_file: str | None = None,
    token_file: str | None = None,
)
```

---

### `send(*, to, subject, body, cc=None, bcc=None, html=False) -> dict`

Send an email. `to`, `cc`, and `bcc` each accept a string or a list of strings.

```python
gmail.send(to="recipient@example.com", subject="Hello", body="Hi there!")
gmail.send(
    to=["alice@example.com", "bob@example.com"],
    subject="Report",
    body="<h1>Done</h1>",
    cc="manager@example.com",
    html=True,
)
```

Returns the sent message metadata dict from the API.

---

### `list_messages(*, query=None, max_results=100) -> list[dict]`

List messages. Accepts any Gmail query string. Returns up to `max_results` messages (capped at 500).

```python
messages = gmail.list_messages()
messages = gmail.list_messages(query="from:boss@example.com is:unread", max_results=20)
```

Each dict has `id` and `threadId`.

---

### `read(*, message_id) -> dict`

Fetch and parse a message by ID.

```python
msg = gmail.read(message_id="message-id")
print(msg["subject"], msg["from_"], msg["body"])
```

Returns a dict with `id`, `thread_id`, `subject`, `from_`, `to`, `date`, and `body`.

---

## License

MIT
