from flask import Flask, request, render_template
import requests
import re
from bs4 import BeautifulSoup
from flask_cors import CORS

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
    url = request.form.get('url')
    keywords = request.form.get('keywords').split()
    try:
        content = fetch_webpage(url)
        articles = extract_articles(content)
        filtered_articles = filter_articles(articles, keywords)
        results_list = []
        for title, content in filtered_articles.items():
            arxiv_id = extract_arxiv_id(content)
            if arxiv_id:
                link = f'<h2><a href="https://arxiv.org/abs/{arxiv_id}" target="_blank">arXiv:{arxiv_id}</a></h2>'
            else:
                link = f'<h2>{title}</h2>'
            results_list.append(f'{link}<pre style="white-space: pre-wrap; word-wrap: break-word;">{content}</pre><hr>')
        results = ''.join(results_list)
        return results
    except Exception as e:
        return f"<p>Error: {str(e)}</p>", 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

