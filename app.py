from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

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

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        keywords = request.form.get('keywords').split()
        try:
            content = fetch_webpage(url)
            articles = extract_articles(content)
            filtered_articles = filter_articles(articles, keywords)
            results = ''.join([f"<h2>{title}</h2><pre>{content}</pre><hr>" for title, content in filtered_articles.items()])
        except Exception as e:
            results = f"<p>Error: {str(e)}</p>"
        return render_template_string(template, results=results)
    return render_template_string(template, results='')

template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Article Keyword Search</title>
</head>
<body>
    <h1>Article Keyword Search</h1>
    <form method="POST">
        <label for="url">Webpage URL:</label><br>
        <input type="text" id="url" name="url" required><br><br>
        <label for="keywords">Keywords (space-separated):</label><br>
        <input type="text" id="keywords" name="keywords" required><br><br>
        <input type="submit" value="Search">
    </form>
    <hr>
    <div>{{ results|safe }}</div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)



