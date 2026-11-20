import re
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from pypdf import PdfReader


def download_source(source):
    # Some catalogs link to a description page and provide a separate file URL.
    request = Request(
        source.get("download_url", source["url"]),
        headers={"User-Agent": "OralHistoryStudentProject/0.1 (educational research)"},
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def retrieve_source(source):
    return download_source(source).decode("utf-8")


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    content = soup.find("div", id="mw-content-text")
    if not content:
        content = soup.find("main")
    if not content:
        content = soup.find("article")
    if not content:
        content = soup.body
    if content is None:
        # Early HTML documents sometimes omit the body element entirely.
        content = soup

    return content.get_text(separator="\n", strip=True)


def bitcointalk_post_to_text(html, message_id, author_user_id):
    """Extract one forum message and verify its author's account ID."""
    soup = BeautifulSoup(html, "html.parser")
    subject = soup.find(id=f"subject_{message_id}")
    cell = subject.find_parent("td", class_="td_headerandpost") if subject else None
    row = cell.find_parent("tr") if cell else None
    author_cell = row.find("td", class_="poster_info") if row else None
    post = cell.find("div", class_="post") if cell else None
    if not author_cell or not post:
        raise ValueError(f"Could not isolate Bitcointalk message {message_id}.")

    author_ids = set()
    for link in author_cell.find_all("a", href=True):
        match = re.search(r"(?:[?;&])u=(\d+)(?:$|[&#])", link["href"])
        if match:
            author_ids.add(int(match.group(1)))
    if author_ids != {author_user_id}:
        raise ValueError(f"Bitcointalk message {message_id} is not by the expected account.")

    for quoted in post.select("div.quote, div.quoteheader, blockquote"):
        quoted.decompose()
    return post.get_text(separator=" ", strip=True)


def x_post_to_text(html, post_id, author_handle):
    """Read the original post text from X's page metadata."""
    soup = BeautifulSoup(html, "html.parser")
    url = soup.find("meta", property="og:url")
    title = soup.find("meta", property="og:title")
    description = soup.find("meta", property="og:description")
    expected = f"https://x.com/{author_handle}/status/{post_id}"
    if not url or url.get("content") != expected:
        raise ValueError(f"Could not verify X post {post_id} URL.")
    if not title or f"(@{author_handle})" not in title.get("content", ""):
        raise ValueError(f"Could not verify X post {post_id} author.")
    if not description or not description.get("content", "").strip():
        raise ValueError(f"Could not extract X post {post_id} text.")
    return description["content"].strip()


def pdf_to_text(path, extraction_mode="plain"):
    # A server can return an HTML error page even when the URL ends in .pdf.
    with open(path, "rb") as file:
        if file.read(5) != b"%PDF-":
            raise ValueError("Expected a PDF, not a webpage or error response.")
    reader = PdfReader(path)
    # Keep empty pages in the list so page numbers still match the original PDF.
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text(extraction_mode=extraction_mode)
        if not text:
            text = ""
        pages.append(text)
        if not text.strip():
            print(f"No text on PDF page {number}; it may be a scan or a blank page.")
    return "\n\n".join(pages), pages
