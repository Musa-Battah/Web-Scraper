import os
import csv
import time
import random
import re
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from bs4 import BeautifulSoup

BASE_URL = "https://www.myjobmag.com"
JOBS_URL = BASE_URL + "/jobs"

# ============ DRIVER SETUP ============
def get_driver():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(120)
    return driver

def extract_text_safe(elem):
    return elem.get_text(strip=True) if elem else ''

def extract_email(text):
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group(0) if match else ''

# ============ CLEANING & FORMATTING ============
def clean_and_format_text(block):
    raw_lines = []
    for tag in block.find_all(['p', 'li']):
        text = tag.get_text(" ", strip=True)
        if text:
            raw_lines.append(text)

    cleaned_lines = []
    for line in raw_lines:
        line = re.sub(r'^\s*[-*•]\s*', '• ', line)
        line = re.sub(r'\s+', ' ', line)
        cleaned_lines.append(line.strip())

    description_lines = []
    requirements_lines = []
    section = 'desc'
    for line in cleaned_lines:
        if 'requirement' in line.lower():
            section = 'req'
            continue
        if section == 'desc':
            description_lines.append(line)
        else:
            requirements_lines.append(line)

    formatted_desc = "📝 **Job Description:**\n" + "\n".join(
        [l if l.startswith('•') else f"• {l}" for l in description_lines]
    ) if description_lines else ""

    formatted_req = "📌 **Requirements:**\n" + "\n".join(
        [l if l.startswith('•') else f"• {l}" for l in requirements_lines]
    ) if requirements_lines else ""

    return formatted_desc.strip(), formatted_req.strip()

# ============ JOB DATA EXTRACTION ============
def extract_job_data(soup):
    title = company = ''
    h1 = soup.find('h1')
    if h1:
        parts = h1.get_text(" ", strip=True).split(' at ')
        title = parts[0].strip()
        if len(parts) > 1:
            company = parts[1].strip()

    company_tagline = ''
    tagline_div = soup.find('div', class_='company-details')
    if tagline_div:
        company_tagline = extract_text_safe(tagline_div.find('p'))
    else:
        about_link = soup.find('a', string=lambda s: s and 'Read more about' in s)
        if about_link:
            tagline_p = about_link.find_next('p')
            company_tagline = extract_text_safe(tagline_p)

    location = qualification = experience = job_type = field = salary = job_expires = ''
    key_info = soup.select("ul.job-key-info li")
    for li in key_info:
        key = extract_text_safe(li.find('span', class_='jkey-title')).lower()
        val = extract_text_safe(li.find('span', class_='jkey-info'))
        if 'location' in key:
            location = val
        elif 'qualification' in key:
            qualification = val
        elif 'experience' in key:
            experience = val
        elif 'job type' in key:
            job_type = val
        elif 'field' in key:
            field = val
        elif 'salary' in key:
            salary = val
        elif 'deadline' in key or 'expires' in key:
            job_expires = val

    description = requirements = ''
    desc_block = soup.select_one("div.job-details")
    if desc_block:
        description, requirements = clean_and_format_text(desc_block)

    application_email = application_url = ''
    method_block = soup.find('h2', id='application-method')
    if method_block:
        method_text = method_block.find_next('div').get_text(" ", strip=True)
        application_email = extract_email(method_text)
        a_tag = method_block.find_next('div').find('a', href=True)
        if a_tag:
            href = a_tag['href']
            application_url = BASE_URL + href if href.startswith('/') else href

    if not application_email and not application_url:
        return None

    slug = '-'.join(title.lower().split())[:50]
    post_tag = field
    post_category = 'job'

    combined_info = (
        f"🏢 **Company:** {company}\n\n"
        f"📍 **Location:** {location}\n\n"
        f"🎓 **Qualification:** {qualification}\n\n"
        f"⏳ **Experience:** {experience}\n\n"
        f"💼 **Job Type:** {job_type}\n\n"
        f"💰 **Salary:** {salary}\n\n"
        f"🔬 **Field:** {field}\n\n"
        f"{description}\n\n"
        f"{requirements}"
    ).strip()

    return {
        'post_title': title + (f" at {company}" if company else "") + (f" in {location}" if location else ""),
        'company': company,
        'company_tagline': company_tagline,
        'job_location': location,
        'job_type': job_type,
        'job_salary': salary,
        'job_expires': job_expires,
        'job_category': field,
        'required_qualifications': qualification,
        'skills_required': '',
        'application_url': application_url,
        'application_email': application_email,
        'slug': slug,
        'post_category': post_category,
        'post_tag': field,
        'subcategory': field,
        'post_content': combined_info
    }

# ============ JOB LINKS ============
def get_job_links(soup):
    selectors = [
        'div.mag-b h2 a[href^="/job/"]',
        'div.job-listing h2 a[href^="/job/"]',
        'a[href^="/job/"]'
    ]
    for selector in selectors:
        job_links = [a['href'] for a in soup.select(selector)]
        if job_links:
            print(f"[+] Job links found with selector: {selector}")
            return job_links
    print("[!] Fallback: scanning all <a> tags for '/job/'")
    return [a['href'] for a in soup.find_all('a', href=True) if '/job/' in a['href']]

# ============ MAIN SCRIPT ============
def scrape_job(driver, job_url):
    """Scrape job using the same driver tab."""
    try:
        driver.get(job_url)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        job_soup = BeautifulSoup(driver.page_source, 'html.parser')
        return extract_job_data(job_soup)
    except Exception as e:
        print(f"[!] Error scraping {job_url}: {e}")
        return None

def main():
    print("[*] Opening jobs page...")
    driver = get_driver()
    driver.get(JOBS_URL)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    job_links = get_job_links(soup)

    print(f"[+] Found {len(job_links)} job links.")
    if not job_links:
        driver.quit()
        input("Press Enter to exit...")
        return

    data_rows = []
    for link in job_links[:10]:
        job_url = BASE_URL + link if link.startswith('/') else link
        print(f"[*] Scraping: {job_url}")
        row = scrape_job(driver, job_url)
        if row:
            data_rows.append(row)
        time.sleep(random.uniform(2, 4))

    driver.quit()

    if data_rows:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        file_path = os.path.join(desktop, f"myjobmag_jobs_{timestamp}.csv")

        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data_rows[0].keys())
            writer.writeheader()
            writer.writerows(data_rows)

        print(f"[+] Saved CSV to {file_path}")
    else:
        print("[!] No job data scraped. CSV not created.")

    input("✅ Done scraping. Press Enter to exit...")

if __name__ == "__main__":
    main()
