# LLM-Doc-Analysis
In this assignment, I analyzed SEC Form 8-K filings using LLM's to extract new product releases and structured the data in a tabular format. 

# Main Goal
After processing SEC 8-K filings I extracted the following information from each document:
Company Name: The name of the company filing the 8-K.
Stock Name: The ticker symbol of the company.
Filing Time: The timestamp of the filing.
New Product: The name of the newly announced product.
Product Description: A concise description of the product, limited to less than 180 characters.

# Technologies that I used:
* Python
* pandas
* Ollama
* BeautifulSoup
* requests
* csv
* asyncio
* aiohttp
