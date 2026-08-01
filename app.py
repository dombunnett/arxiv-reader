import os
from datetime import datetime, timezone
from flask import Flask, request, render_template, jsonify
from markupsafe import escape
import requests
import re
from bs4 import BeautifulSoup
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app, resources={
    r"/search": {"origins": "https://dombunnett.github.io"},
    r"/api/*": {"origins": "*"},
})

# Function to fetch and parse the webpage
def fetch_webpage(url):
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch the webpage. Status code: {response.status_code}")
    return response.text

# Function to extract articles from the content and remove leading empty lines
def extract_articles(content):
    soup = BeautifulSoup(content, 'html.parser')
    text = soup.get_text()
    
    articles = {}
    current_article = None
    article_lines = []

    for line in text.split('\n'):
        if line.startswith('[') and ']' in line:
            if current_article is not None:
                # Remove leading empty lines
                article_lines = [line for line in article_lines if line.strip() != '']
                articles[current_article] = '\n'.join(article_lines)
                article_lines = []
            current_article = line
        elif current_article is not None:
            article_lines.append(line)
    
    if current_article is not None:
        # Remove leading empty lines for the last article
        article_lines = [line for line in article_lines if line.strip() != '']
        articles[current_article] = '\n'.join(article_lines)
    
    return articles

# Function to filter articles by keywords (case-insensitive and handles plurals)
def filter_articles(articles, keywords):
    keywords = {keyword.lower() for keyword in keywords}  # Convert keywords to lowercase
    keywords_with_plural = keywords.union({keyword + 's' for keyword in keywords})
    filtered_articles = {}
    for article_title, article_content in articles.items():
        article_content_lower = article_content.lower()  # Convert content to lowercase
        for keyword in keywords_with_plural:
            if keyword in article_content_lower:
                filtered_articles[article_title] = article_content
                break
    return filtered_articles

# Function to extract arXiv ID from article content
def extract_arxiv_id(content):
    match = re.search(r'arXiv:(\d{4}\.\d{4,5})', content)
    if match:
        return match.group(1)
    return None

@app.route('/')
def index():
    return render_template('arXiv-reader.html')

@app.route('/search', methods=['POST'])
def search():
    urls = request.form.getlist('urls')
    keywords = request.form.get('keywords').split()

    if not urls:
        return render_template('results.html', results=[], count=0, error="Please select at least one category")

    try:
        all_articles = {}

        # Fetch all URLs in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(fetch_webpage, url): url for url in urls}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                # Extract category from URL (e.g., "math.AG" from "https://arxiv.org/list/math.AG/new")
                category = url.split('/list/')[1].split('/')[0]
                content = future.result()
                articles = extract_articles(content)
                # Prefix article keys with category to avoid collisions
                for key, value in articles.items():
                    all_articles[f"{category} {key}"] = value

        filtered_articles = filter_articles(all_articles, keywords)
        results_list = []
        for title, content in filtered_articles.items():
            arxiv_id = extract_arxiv_id(content)
            results_list.append({
                'title': title,
                'arxiv_id': arxiv_id,
                'content': content
            })
        return render_template('results.html', results=results_list, count=len(results_list), error=None)
    except Exception as e:
        return render_template('results.html', results=[], count=0, error=str(e))


# ---------------------------------------------------------------------------
# Structured JSON API (GET-friendly) — added for the dashboard refresh task.
# The form route /search above is unchanged.
# ---------------------------------------------------------------------------

LISTING_DATE_RE = re.compile(r'Showing new listings for\s+([^\n]+)')
TAG_RE = re.compile(r'\(([a-z][a-z\-]*(?:\.[A-Za-z\-]{2,})?)\)')


def abbreviate_authors(raw):
    """'Yves Aubry (IMATH), Marc Perret' -> 'Y. Aubry, M. Perret'"""
    raw = re.sub(r'\([^)]*\)', '', raw)
    out = []
    for name in raw.split(','):
        name = ' '.join(name.split())
        if not name:
            continue
        parts = name.split()
        if len(parts) == 1:
            out.append(parts[0])
        else:
            out.append('%s. %s' % (parts[0][0], parts[-1]))
    return ', '.join(out)


def subject_tags(raw):
    """'Algebraic Geometry (math.AG); Machine Learning (cs.LG)' -> ['math.AG','cs.LG']"""
    return TAG_RE.findall(raw)


def parse_listing(content):
    """Parse an arXiv /new page into (listing_date, [entry, ...])."""
    soup = BeautifulSoup(content, 'html.parser')

    m = LISTING_DATE_RE.search(soup.get_text('\n'))
    listing_date = m.group(1).strip() if m else None

    entries = []
    current_type = 'new'
    for el in soup.find_all(['h3', 'dl']):
        if el.name == 'h3':
            head = el.get_text(' ', strip=True).lower()
            if 'cross' in head:
                current_type = 'cross'
            elif 'replac' in head:
                current_type = 'repl'
            elif 'new' in head:
                current_type = 'new'
            continue

        dts, dds = el.find_all('dt'), el.find_all('dd')
        for dt, dd in zip(dts, dds):
            ident = dt.get_text(' ', strip=True)
            id_match = re.search(r'arXiv:(\d{4}\.\d{4,5})', ident)
            if not id_match:
                continue

            entry_type = current_type
            low = ident.lower()
            if 'cross-list' in low:
                entry_type = 'cross'
            elif 'replaced' in low:
                entry_type = 'repl'

            def field(cls, label):
                node = dd.find('div', class_=cls)
                if not node:
                    return ''
                txt = node.get_text(' ', strip=True)
                return re.sub(r'^%s:\s*' % label, '', txt).strip()

            para = dd.find('p')
            entries.append({
                'type': entry_type,
                'id': id_match.group(1),
                'title': field('list-title', 'Title'),
                'authors': field('list-authors', 'Authors?'),
                'subjects': field('list-subjects', 'Subjects?'),
                'abstract': para.get_text(' ', strip=True) if para else '',
            })
    return listing_date, entries


def matched_keywords(entry, keywords):
    """Case-insensitive substring match over title + abstract."""
    haystack = ('%s %s' % (entry['title'], entry['abstract'])).lower()
    return [k for k in keywords if k in haystack]


@app.route('/api/search', methods=['GET', 'POST'])
def api_search():
    """Keyword-filtered arXiv listings as JSON.

    GET  /api/search?cats=math.AG&keywords=moduli+toric
    GET  /api/search?urls=https://arxiv.org/list/math.AG/new&keywords=moduli
    POST same params as form fields.
    """
    if request.method == 'POST':
        urls = request.form.getlist('urls')
        raw_keywords = request.form.get('keywords') or ''
        cats = request.form.get('cats') or ''
    else:
        urls = request.args.getlist('urls')
        raw_keywords = request.args.get('keywords') or ''
        cats = request.args.get('cats') or ''

    if not urls and cats:
        urls = ['https://arxiv.org/list/%s/new' % c.strip()
                for c in cats.split(',') if c.strip()]

    keywords = [k.lower() for k in re.split(r'[,\s]+', raw_keywords) if k]

    if not urls:
        return jsonify({'error': 'give at least one of urls= or cats='}), 400
    if not keywords:
        return jsonify({'error': 'give at least one keyword'}), 400

    papers, listings, errors = [], {}, {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_webpage, u): u for u in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                category = url.split('/list/')[1].split('/')[0]
            except IndexError:
                category = url
            try:
                listing_date, entries = parse_listing(future.result())
            except Exception as exc:
                errors[category] = str(exc)
                continue

            listings[category] = listing_date
            for entry in entries:
                hits = matched_keywords(entry, keywords)
                if not hits:
                    continue
                papers.append({
                    'type': entry['type'],
                    'id': entry['id'],
                    'title': entry['title'],
                    'au': abbreviate_authors(entry['authors']),
                    'tags': subject_tags(entry['subjects']),
                    'kw': hits,
                    'category': category,
                })

    order = {'new': 0, 'cross': 1, 'repl': 2}
    papers.sort(key=lambda p: (order.get(p['type'], 9), p['id']))

    payload = jsonify({
        'retrieved': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'listing_dates': listings,
        'keywords': keywords,
        'count': len(papers),
        'papers': papers,
        'errors': errors,
    })
    # Never let an intermediary serve a stale copy of this.
    payload.headers['Cache-Control'] = 'no-store, max-age=0'
    return payload



@app.route('/api/search.html', methods=['GET'])
def api_search_html():
    """Same data as /api/search, rendered as plain HTML.

    Some automated clients (and simple text fetchers) can't consume JSON.
    This returns a minimal, stable HTML document that is trivial to parse:
    one <li> per paper, fields in fixed order, marked with data- attributes.

    GET /api/search.html?cats=math.AG&keywords=moduli+toric
    """
    with app.test_request_context(
            '/api/search?' + request.query_string.decode('utf-8', 'ignore')):
        response = api_search()

    # api_search returns either a Response or (Response, status)
    status = 200
    if isinstance(response, tuple):
        response, status = response
    data = response.get_json()

    if status != 200 or 'error' in data and data.get('error'):
        body = '<p class="error">%s</p>' % escape(str(data.get('error', 'unknown error')))
        return ('<!doctype html><html><head><meta charset="utf-8">'
                '<title>arXiv reader</title></head><body>%s</body></html>' % body,
                status, {'Content-Type': 'text/html; charset=utf-8'})

    rows = []
    for p in data.get('papers', []):
        rows.append(
            '<li data-type="{type}" data-id="{id}">'
            '<span class="type">{type}</span> '
            '<a class="title" href="https://arxiv.org/abs/{id}">{title}</a> '
            '<span class="authors">{au}</span> '
            '<span class="tags">{tags}</span> '
            '<span class="kw">{kw}</span> '
            '<span class="arxiv-id">arXiv:{id}</span>'
            '</li>'.format(
                type=escape(p.get('type', '')),
                id=escape(p.get('id', '')),
                title=escape(p.get('title', '')),
                au=escape(p.get('au', '')),
                tags=escape(', '.join(p.get('tags', []))),
                kw=escape(', '.join(p.get('kw', []))),
            )
        )

    listing_dates = '; '.join(
        '%s: %s' % (escape(c), escape(str(d)))
        for c, d in (data.get('listing_dates') or {}).items()
    )
    errors = data.get('errors') or {}
    error_html = ''
    if errors:
        error_html = '<p class="errors">%s</p>' % escape('; '.join(
            '%s: %s' % (c, e) for c, e in errors.items()))

    html = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<title>arXiv reader results</title></head><body>'
        '<h1>arXiv keyword results</h1>'
        '<p class="meta">retrieved: {retrieved} | listing dates: {dates} | '
        'keywords: {kw} | count: {count}</p>'
        '{errors}'
        '<ul id="papers">{rows}</ul>'
        '</body></html>'
    ).format(
        retrieved=escape(str(data.get('retrieved', ''))),
        dates=listing_dates or 'unknown',
        kw=escape(', '.join(data.get('keywords', []))),
        count=data.get('count', 0),
        errors=error_html,
        rows=''.join(rows) or '<li class="none">no matches</li>',
    )
    return html, 200, {'Content-Type': 'text/html; charset=utf-8',
                       'Cache-Control': 'no-store, max-age=0'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)

