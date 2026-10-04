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
        raise ValueError("Could not find the page's main content.")

    return content.get_text(separator="\n", strip=True)


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
