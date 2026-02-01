# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (development mode with debug)
python app.py

# Run with gunicorn (production mode)
gunicorn app:app
```

The app runs on `http://0.0.0.0:5000` in development mode.

## Deployment

Deployed to Heroku. Push to `heroku` remote to deploy:
```bash
git push heroku main
```

## Architecture

This is a Flask web app that filters arXiv "new submissions" pages by user-provided keywords.

**Flow:**
1. User selects a math arXiv category (AG, AC, AT, DG, or NT) and enters keywords
2. `fetch_webpage()` retrieves the arXiv listing page
3. `extract_articles()` parses the HTML with BeautifulSoup, splitting content into articles by `[n]` bracket markers
4. `filter_articles()` does case-insensitive keyword matching (including plural forms with 's' suffix)
5. Results returned as HTML with article titles and content

**Key files:**
- `app.py` - Flask app with all logic (routes: `/` serves form, `/search` handles POST)
- `templates/arXiv-reader.html` - Frontend form with hardcoded arXiv category URLs

**CORS:** Configured to allow requests from `dombunnett.github.io`.
