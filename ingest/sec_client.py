import gzip
from urllib.request import Request, urlopen

def fetch_url(url, headers):
    request = Request(url, headers = headers)
    with urlopen(request, timeout=30) as response:
        content = response.read()
        content_encoding = response.headers.get("Content-Encoding")

        if content_encoding == "gzip":
            content = gzip.decompress(content)
        content_type = response.headers.get("Content-Type", "")
    return content, content_type