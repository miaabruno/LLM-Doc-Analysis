# Mia Bruno
# 3/26/2025
# CAP5619
# LLM Doc Analysis

import requests
import json
import pandas as pd
import time
import re
import os
from bs4 import BeautifulSoup
import ollama

# Configuration
CACHE_DIR = "filing_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# SEC Headers to avoid 403 errors
HEADERS = {'User-Agent': 'mi091463@ucf.edu'}

# Create an empty DataFrame to store the final results
results_df = pd.DataFrame(columns=['company_name', 'stock_name', 'filing_time', 'new_product', 'product_description'])

# --- Synchronous Request Functions ---
def fetch_url(url, retries=3, delay=2):
    """Fetch URL with retry logic and exponential backoff."""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', delay))
                print(f"Rate limit hit. Waiting {retry_after} seconds before retrying.")
                time.sleep(retry_after)
            else:
                print(f"HTTP request failed for {url}: {response.status_code}")
                return None
        except requests.RequestException as e:
            print(f"Request error for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))  # Exponential backoff
            else:
                return None
    return None

def get_8k_filings(cik):
    """Fetch 8-K filings for a given CIK synchronously."""
    search_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        filings_data = json.loads(fetch_url(search_url) or "{}")
        if 'filings' in filings_data and 'recent' in filings_data['filings']:
            recent_filings = filings_data['filings']['recent']
            form_indices = [i for i, form in enumerate(recent_filings.get('form', [])) if form == '8-K']
            if form_indices:
                return [
                    (recent_filings.get('filingDate', [])[i], recent_filings.get('accessionNumber', [])[i], recent_filings.get('primaryDocument', [])[i])
                    for i in form_indices
                ]
        return []
    except Exception as e:
        print(f"Error fetching 8-K filings for CIK {cik}: {e}")
        return []

def get_filing_content(accession_number, cik, primary_document):
    """Fetch filing content synchronously with caching."""
    cache_file = os.path.join(CACHE_DIR, f"{cik}_{accession_number}.txt")
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()

    accession_number_clean = accession_number.replace('-', '')
    filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_number_clean}/{primary_document}"
    try:
        content = fetch_url(filing_url)
        if content:
            content = content.encode("utf-8", "ignore").decode("utf-8", "ignore")
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return content
    except Exception as e:
        print(f"Error fetching filing content for {accession_number}: {e}")
        return None

# Function to extract text
def extract_text(html_content):
    """Extract plain text from HTML content using BeautifulSoup."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    html_text = soup.get_text(separator=' ', strip=True)
    return html_text.replace(" ", " ").replace(" ", " ").replace(" ", " ").replace(" ", " ").replace(" ☐ ", " ")

# --- LLM Interaction Function ---
def extract_product_info(filing_content, company_name, ticker):
    """Use LLM to extract new product info from filing content."""
    if not filing_content:
        return None

    text = extract_text(filing_content)
    if not text:
        return None

    prompt = f""" 
    Analyze this SEC 8-K filing and extract information about any new product releases or announcements. 

    Company: {company_name} 
    Ticker: {ticker} 

    Task: Extract the following information in a structured format: 
    1. New Product Name: [Name of the new product] 
    2. Product Description: [Brief description of the product, less than 180 characters] 

    If no new product is mentioned in the filing, respond with "No new product found". 

    Filing content: 
    {text} 
    """

    try:
        response = ollama.generate(model="llama3.2:latest", prompt=prompt)
        raw_response = response['response']
        llm_response = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL).strip()

        if "No new product found" in llm_response:
            return None

        product_name = None
        product_description = None

        match = re.search(r"New Product Name:\s*(.*)", llm_response)
        if match:
            product_name = match.group(1).strip()

        match = re.search(r"Product Description:\s*(.*)", llm_response)
        if match:
            product_description = match.group(1).strip()[:180]

        if product_name:
            return {"new_product": product_name, "product_description": product_description or ""}
        return None

    except Exception as e:
        print(f"Error extracting product info using LLM: {e}")
        return None

# --- Company Processing Function ---
def process_company(row):
    """Process a single company's filings sequentially."""
    global results_df
    cik = row.get('cik_str', None)
    if cik is None:
        print(f"Skipping row due to missing 'cik_str': {row}")
        return

    ticker = row['ticker']
    company_name = row['title']
    print(f"Processing {company_name} (CIK: {cik}, Ticker: {ticker})...")

    filings = get_8k_filings(cik)[:2]
    for filing_date, accession_number, primary_document in filings:
        filing_content = get_filing_content(accession_number, cik, primary_document)
        product_info = extract_product_info(filing_content, company_name, ticker)

        if product_info:
            new_row = pd.DataFrame([{
                'company_name': company_name,
                'stock_name': ticker,
                'filing_time': filing_date,
                'new_product': product_info['new_product'],
                'product_description': product_info['product_description']
            }])
            results_df = pd.concat([results_df, new_row], ignore_index=True)
            print(f"  Found new product: {product_info['new_product']}")

        time.sleep(1)  # Rate limiting delay

# --- Main Execution ---
def main():
    global results_df

    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        response = fetch_url(url)
        if response is None:
            print("Failed to fetch company tickers. Exiting.")
            return
        data = json.loads(response or "{}")

        company_data = pd.DataFrame.from_dict(data, orient='index')
        company_data['cik_str'] = company_data['cik_str'].astype(str).str.zfill(10)
        company_data = company_data.head(100)  

        # Process each company sequentially
        for _, row in company_data.iterrows():
            process_company(row)

        results_df.to_csv('sec_8k_product_releases.csv', index=False)
        print(f"Analysis complete. Found {len(results_df)} products. Results saved to sec_8k_product_releases.csv")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
