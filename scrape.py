import asyncio
import httpx  # The async-capable requests replacement
import random
import time
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import csv
from tqdm.asyncio import tqdm_asyncio # For async-compatible progress bars

# --- Configuration ---

# The sitemap URL for the blogspot blog
SITEMAP_URL = "https://elrincondelkitsune.blogspot.com/sitemap.xml"

# The name of the output CSV file
OUTPUT_CSV_FILE = "scraped_links_async.csv"

# Headers to make our script look like a regular browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

# --- Anti-Blocking & Performance Configuration ---

# Max number of concurrent requests. A sweet spot is between 5-15.
# Too high, and you risk getting blocked. Too low, and it's not much faster.
CONCURRENCY_LIMIT = 10

# Timeout for each request in seconds
REQUEST_TIMEOUT = 20

# Randomized delay between requests to mimic human behavior
# A tuple representing the (min, max) delay in seconds.
RANDOM_DELAY_RANGE = (0.5, 1.5)

# --- Helper Functions (Now Asynchronous) ---

# All functions that perform network I/O must be defined with `async def`
async def get_post_urls_from_sitemap(sitemap_url, client):
    """
    Fetches the sitemap.xml and extracts all post URLs asynchronously.

    Args:
        sitemap_url (str): The URL of the sitemap.xml file.
        client (httpx.AsyncClient): The httpx client to use for the request.

    Returns:
        list: A list of string URLs found in the sitemap, or an empty list on failure.
    """
    print(f"[*] Fetching sitemap from: {sitemap_url}")
    try:
        # `await` pauses the function until the network request is complete
        response = await client.get(sitemap_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        namespaces = {'sitemap': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        root = ET.fromstring(response.content)
        url_elements = root.findall('sitemap:url/sitemap:loc', namespaces)
        
        post_urls = [url.text for url in url_elements]
        print(f"[+] Found {len(post_urls)} URLs in the sitemap.")
        return post_urls

    except httpx.RequestError as e:
        print(f"[!] Error fetching sitemap: {e}")
        return []
    except ET.ParseError as e:
        print(f"[!] Error parsing XML sitemap: {e}")
        return []

async def find_all_links(post_url, client, semaphore):
    """
    Scrapes a single blog post to find its title and ALL links asynchronously.
    This function will be run concurrently for all URLs.

    Args:
        post_url (str): The URL of the blog post to scrape.
        client (httpx.AsyncClient): The httpx client for requests.
        semaphore (asyncio.Semaphore): The semaphore to limit concurrency.

    Returns:
        dict or None: A dictionary of scraped data or None on failure.
    """
    # The `async with` block ensures the semaphore is acquired before proceeding
    # and released automatically, even if an error occurs.
    async with semaphore:
        try:
            # Add a small, random delay to be less robotic
            await asyncio.sleep(random.uniform(*RANDOM_DELAY_RANGE))
            
            response = await client.get(post_url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'lxml')

            title_tag = soup.find('title')
            post_title = title_tag.get_text(strip=True) if title_tag else "No Title Found"

            found_links = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if not href or href.startswith('#'):
                    continue
                found_links.add(href)

            if found_links:
                return {
                    'url': post_url,
                    'title': post_title,
                    'found_links': sorted(list(found_links))
                }
            
            return None # No links found, but the page was scraped successfully

        except httpx.RequestError as e:
            # We don't print here to avoid cluttering the progress bar.
            # We can log these failures later if needed.
            return None # Indicate failure for this specific URL
        except Exception:
            # Catch other potential errors (e.g., BeautifulSoup parsing)
            return None


# --- Main Execution (Now Asynchronous) ---

async def main():
    """
    Main async function to orchestrate the scraping process.
    """
    start_time = time.time()
    
    # `AsyncClient` is the async equivalent of `requests.Session`
    async with httpx.AsyncClient(headers=HEADERS) as client:
        post_urls = await get_post_urls_from_sitemap(SITEMAP_URL, client)

        if not post_urls:
            print("[!] No URLs to process. Exiting.")
            return

        # Create a semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        # Create a list of tasks (coroutines) to run. One for each URL.
        tasks = [find_all_links(url, client, semaphore) for url in post_urls]
        
        print(f"\n[*] Starting to scrape {len(post_urls)} posts with a concurrency of {CONCURRENCY_LIMIT}...")
        
        # tqdm_asyncio.gather runs all tasks concurrently and shows a progress bar
        results = await tqdm_asyncio.gather(*tasks, desc="Scraping Posts")

    # Now that all async network operations are done, process the results
    
    # Filter out None results from failed requests or pages with no links
    successful_results = [res for res in results if res is not None]
    
    # Write all successful results to the CSV file at once
    with open(OUTPUT_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Title', 'URL', 'Links'])
        
        for data in successful_results:
            links_string = "\n".join(data['found_links'])
            csv_writer.writerow([data['title'], data['url'], links_string])

    # --- Final summary message ---
    end_time = time.time()
    print("\n" + "="*50)
    print("SCRAPING COMPLETE")
    print("="*50 + "\n")
    print(f"[+] Process finished in {end_time - start_time:.2f} seconds.")
    print(f"[+] Successfully scraped {len(successful_results)} out of {len(post_urls)} posts.")
    print(f"[+] All data has been saved to '{OUTPUT_CSV_FILE}'.")


if __name__ == "__main__":
    # To run an async function, we use asyncio.run()
    asyncio.run(main())