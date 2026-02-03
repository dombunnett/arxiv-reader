import os
from flask import Flask, request, render_template
import requests
import re
from bs4 import BeautifulSoup
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app, resources={r"/search": {"origins": "https://dombunnett.github.io"}})

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
                content = future.result()
                articles = extract_articles(content)
                all_articles.update(articles)

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)

