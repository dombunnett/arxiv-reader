from flask import Flask, request, render_template
import requests
from bs4 import BeautifulSoup
from flask_cors import CORS
import re

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
                # Add LINK to the arXiv ID
                article_title_with_link = re.sub(
                    r'(\[\d+\]\s+arXiv:(\d+\.\d+))',
                    r'\1 <a href="https://arxiv.org/\2">LINK</a>',
                    article_title
                )
                filtered_articles[article_title_with_link] = article_content
                break
    return filtered_articles

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
        results = ''.join([f"<h2>{title}</h2><pre>{content}</pre><hr>" for title, content in filtered_articles.items()])
        return results
    except Exception as e:
        return f"<p>Error: {str(e)}</p>", 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

