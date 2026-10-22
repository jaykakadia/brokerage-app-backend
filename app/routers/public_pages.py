import html as html_lib
import json
import re
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.blog import Blog
from app.db.models.listing import Listing
from app.core.cities import MIN_HUB_LISTINGS, TOP_CITIES, get_city_display_name, slugify_city
from app.routers.city_pages import load_base_index_html, set_or_replace_canonical, set_or_replace_meta, get_active_cities_summary

router = APIRouter(tags=["Public Pages SSR"])
catch_all_router = APIRouter(tags=["Catch-All 404"])

BASE_URL = "https://tradecall.in"
PHONE = "+91 9992292828"
ADDRESS = "Village Joharkhera, PO Mandkola, Palwal, Haryana 121102"


def _render_page_shell(
    base_html: str,
    title: str,
    description: str,
    canonical_url: Optional[str],
    robots_content: str,
    root_inner_html: str,
    json_ld: Optional[Dict] = None
) -> str:
    html = base_html

    # 1. Title
    if re.search(r"<title>.*?</title>", html, flags=re.DOTALL):
        html = re.sub(r"<title>.*?</title>", f"<title>{html_lib.escape(title)}</title>", html, count=1, flags=re.DOTALL)
    else:
        html = html.replace("<head>", f"<head>\n  <title>{html_lib.escape(title)}</title>")

    # 2. Description
    escaped_desc = html_lib.escape(description, quote=True)
    if re.search(r'<meta\s+name=["\']description["\']', html):
        html = re.sub(
            r'<meta\s+name=["\']description["\']\s+content=["\'][^"\']*["\']\s*/?>',
            f'<meta name="description" content="{escaped_desc}" />',
            html,
            count=1
        )
    else:
        html = html.replace("</head>", f'  <meta name="description" content="{escaped_desc}" />\n</head>')

    # 3. Canonical
    if canonical_url:
        html = set_or_replace_canonical(html, canonical_url)
    else:
        # Strip canonical if none desired (e.g. 404)
        html = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', html, flags=re.IGNORECASE)

    # 4. Robots
    html = set_or_replace_meta(html, "name", "robots", robots_content)

    # 5. OpenGraph & Twitter
    html = set_or_replace_meta(html, "property", "og:title", title)
    html = set_or_replace_meta(html, "property", "og:description", description)
    if canonical_url:
        html = set_or_replace_meta(html, "property", "og:url", canonical_url)
    html = set_or_replace_meta(html, "name", "twitter:title", title)
    html = set_or_replace_meta(html, "name", "twitter:description", description)

    # 6. JSON-LD Schema
    if json_ld:
        schema_tag = f"""  <script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n  </script>"""
        html = html.replace("</head>", f"{schema_tag}\n</head>")

    # 7. Inject SSR body content into #root (preserving script tags and head)
    rendered_root = f'''<div id="root">
    <div class="ssr-page-content" style="position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;">
      {root_inner_html}
    </div>
  </div>'''
    html = re.sub(r'<div\s+id=["\']root["\'][^>]*>.*?</div>', rendered_root, html, count=1, flags=re.DOTALL)

    return html


# --- PUBLIC ROUTES ---

@router.api_route("/about", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_about_page():
    base_html = load_base_index_html()
    title = "About Us | TradeCall India - Zero Brokerage Real Estate"
    desc = "Learn about TradeCall India, our mission to provide direct zero-brokerage property and business listings in Palwal, Faridabad, and NCR."
    canonical = f"{BASE_URL}/about"

    org_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "TradeCall India",
        "url": BASE_URL,
        "telephone": PHONE,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Village Joharkhera, PO Mandkola",
            "addressLocality": "Palwal",
            "addressRegion": "Haryana",
            "postalCode": "121102",
            "addressCountry": "IN"
        }
    }

    body = f"""<main>
      <h1>About TradeCall India</h1>
      <p>TradeCall India is a premier zero-brokerage real estate platform and local business directory founded to bring transparency, trust, and affordability to property transactions across Palwal, Faridabad, Gurugram, and the greater National Capital Region (NCR).</p>
      <section>
        <h2>Our Mission</h2>
        <p>We eliminate expensive real estate brokerage fees by directly connecting buyers, sellers, tenants, and property owners. Every listing is verified by local associates to ensure authentic prices and genuine listings.</p>
      </section>
      <section>
        <h2>Contact Information</h2>
        <p><strong>Phone & WhatsApp:</strong> <a href="tel:{PHONE}">{PHONE}</a></p>
        <p><strong>Registered Address:</strong> {ADDRESS}</p>
      </section>
      <nav><a href="/">Home</a> | <a href="/cities">Explore Cities</a> | <a href="/contact">Contact Us</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, org_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/contact", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_contact_page():
    base_html = load_base_index_html()
    title = "Contact Us | TradeCall India"
    desc = "Get in touch with TradeCall India for verified real estate inquiries, advertising, and business directory services in Palwal, Faridabad, and NCR."
    canonical = f"{BASE_URL}/contact"

    contact_ld = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "TradeCall India",
        "url": BASE_URL,
        "telephone": PHONE,
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": PHONE,
            "contactType": "customer service",
            "areaServed": "IN",
            "availableLanguage": ["en", "hi"]
        },
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "Village Joharkhera, PO Mandkola",
            "addressLocality": "Palwal",
            "addressRegion": "Haryana",
            "postalCode": "121102",
            "addressCountry": "IN"
        }
    }

    body = f"""<main>
      <h1>Contact TradeCall India</h1>
      <p>Have questions about a property listing or need help posting your free listing? Reach out to our customer support team directly.</p>
      <section>
        <h2>Get In Touch</h2>
        <p><strong>Phone / WhatsApp:</strong> <a href="tel:{PHONE}">{PHONE}</a></p>
        <p><strong>Office Address:</strong> {ADDRESS}</p>
      </section>
      <nav><a href="/">Home</a> | <a href="/about">About Us</a> | <a href="/cities">Property Hubs</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, contact_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/cities", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_cities_page(db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    title = "Property by City & Hubs | TradeCall India"
    desc = "Explore verified real estate listings by city in Palwal, Faridabad, Hodal, Ballabgarh, Greater Noida, and across Delhi NCR with zero brokerage."
    canonical = f"{BASE_URL}/cities"

    active_cities = get_active_cities_summary(db)
    city_items = []
    for c in active_cities:
        city_items.append(f'<li><a href="/properties/{c["slug"]}">Properties in {c["name"]} ({c["count"]} listings)</a></li>')
    city_list_html = "\n        ".join(city_items)

    body = f"""<main>
      <h1>Property in Top Cities & Hubs</h1>
      <p>Browse zero-brokerage real estate listings across top cities and towns in Haryana, Uttar Pradesh, and the NCR.</p>
      <section>
        <h2>Active City Hubs</h2>
        <ul>
        {city_list_html}
        </ul>
      </section>
      <nav><a href="/">Home</a> | <a href="/business-directory">Business Directory</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/business-directory", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_business_directory_page():
    base_html = load_base_index_html()
    title = "Local Business Directory | TradeCall India"
    desc = "Discover verified local businesses, contractors, building material suppliers, and professional services in Palwal, Faridabad, and Delhi NCR."
    canonical = f"{BASE_URL}/business-directory"

    body = """<main>
      <h1>Local Business Directory</h1>
      <p>Connect with trusted local businesses, property contractors, architects, legal advisors, and home service providers in Palwal, Faridabad, and Delhi NCR.</p>
      <nav><a href="/">Home</a> | <a href="/cities">Property Hubs</a> | <a href="/post-listing">List Your Business</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/blog", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_blog_index_page(db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    title = "Real Estate Blog & Guides | TradeCall India"
    desc = "Real estate market updates, property buying guides, legal registration tips, and investment analysis for Palwal, Faridabad, and Delhi NCR."
    canonical = f"{BASE_URL}/blog"

    blogs = (
        db.query(Blog)
        .filter(Blog.status.in_(["published", "publish"]))
        .order_by(Blog.id.desc())
        .limit(20)
        .all()
    )
    blog_items = []
    for b in blogs:
        blog_items.append(f'<li><a href="/blog/{b.permalink}">{html_lib.escape(b.title)}</a></li>')
    blog_list_html = "\n        ".join(blog_items) if blog_items else "<p>Check back soon for new real estate articles and guides.</p>"

    body = f"""<main>
      <h1>Real Estate Blog & Market Insights</h1>
      <p>Stay informed with the latest property market trends, legal guidance, and real estate investment tips.</p>
      <section>
        <h2>Recent Articles</h2>
        <ul>
        {blog_list_html}
        </ul>
      </section>
      <nav><a href="/">Home</a> | <a href="/cities">Property Hubs</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/blog/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_blog_detail_page(slug: str, db: Session = Depends(get_db)):
    base_html = load_base_index_html()
    clean_slug = slug.strip().lower()

    blog = db.query(Blog).filter(
        Blog.permalink == clean_slug,
        Blog.status.in_(["published", "publish"])
    ).first()

    if not blog:
        # Unknown slug -> 404 + noindex
        not_found_body = """<main>
          <h1>Article Not Found</h1>
          <p>The requested blog article does not exist or has been removed.</p>
          <nav><a href="/blog">Browse All Articles</a> | <a href="/">Back to Homepage</a></nav>
        </main>"""
        rendered = _render_page_shell(
            base_html,
            "404 - Article Not Found | TradeCall India",
            "This article could not be found.",
            None,
            "noindex, follow",
            not_found_body
        )
        return HTMLResponse(content=rendered, status_code=status.HTTP_404_NOT_FOUND)

    title = f"{blog.title} | TradeCall India"
    # Clean excerpt from content
    clean_text = re.sub(r"<[^>]*>", " ", blog.content or "")
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    desc = clean_text[:160].rstrip() if clean_text else f"Read {blog.title} on TradeCall India Blog."
    canonical = f"{BASE_URL}/blog/{blog.permalink}"

    article_ld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": blog.title,
        "description": desc,
        "url": canonical,
        "author": {
            "@type": "Person",
            "name": blog.author or "TradeCall Team"
        },
        "publisher": {
            "@type": "Organization",
            "name": "TradeCall India",
            "url": BASE_URL
        }
    }
    if blog.created_at:
        article_ld["datePublished"] = blog.created_at.strftime("%Y-%m-%d")
    if blog.updated_at:
        article_ld["dateModified"] = blog.updated_at.strftime("%Y-%m-%d")

    body = f"""<article>
      <h1>{html_lib.escape(blog.title)}</h1>
      <p class="post-meta">By {html_lib.escape(blog.author or 'TradeCall Team')}</p>
      <div class="post-content">
        {blog.content}
      </div>
      <nav><a href="/blog">Back to Blog</a> | <a href="/">Home</a></nav>
    </article>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body, article_ld)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_privacy_page():
    base_html = load_base_index_html()
    title = "Privacy Policy | TradeCall India"
    desc = "Privacy policy and personal data protection terms for TradeCall India users and listing posters."
    canonical = f"{BASE_URL}/privacy"

    body = """<main>
      <h1>Privacy Policy</h1>
      <p>TradeCall India respects your privacy and is committed to protecting your personal data. This privacy policy explains how we handle your personal information when you browse our website or post property and business listings.</p>
      <nav><a href="/">Home</a> | <a href="/terms-of-use">Terms of Use</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/terms-of-use", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_terms_page():
    base_html = load_base_index_html()
    title = "Terms of Use | TradeCall India"
    desc = "Terms of use, listing guidelines, and user agreement for TradeCall India."
    canonical = f"{BASE_URL}/terms-of-use"

    body = """<main>
      <h1>Terms of Use</h1>
      <p>By accessing or using TradeCall India, you agree to comply with and be bound by these terms of use. All property listings must be genuine, legally marketable, and free from misleading descriptions.</p>
      <nav><a href="/">Home</a> | <a href="/privacy">Privacy Policy</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/advertise", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_advertise_page():
    base_html = load_base_index_html()
    title = "Advertise with Us | TradeCall India"
    desc = "Promote your real estate projects, builder developments, and local businesses to targeted buyers across Palwal, Faridabad, and NCR."
    canonical = f"{BASE_URL}/advertise"

    body = f"""<main>
      <h1>Advertise with TradeCall India</h1>
      <p>Reach thousands of active property seekers and homeowners across Palwal, Faridabad, and NCR through featured banner placements and verified business promotions.</p>
      <p>For custom advertising packages, call or WhatsApp us directly at <a href="tel:{PHONE}">{PHONE}</a>.</p>
      <nav><a href="/">Home</a> | <a href="/contact">Contact Us</a></nav>
    </main>"""

    rendered = _render_page_shell(base_html, title, desc, canonical, "index, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


@router.api_route("/post-listing", methods=["GET", "HEAD"], response_class=HTMLResponse)
def get_post_listing_page():
    base_html = load_base_index_html()
    title = "Post Free Property Listing | TradeCall India"
    desc = "Post your property for sale or rent with zero brokerage on TradeCall India and connect directly with verified buyers and tenants."
    canonical = f"{BASE_URL}/post-listing"

    body = """<main>
      <h1>Post Free Property Listing</h1>
      <p>Post your residential flat, plot, house, commercial shop, or agriculture land on TradeCall India. 100% free with zero brokerage.</p>
      <nav><a href="/">Home</a> | <a href="/cities">Explore Properties</a></nav>
    </main>"""

    # Note: explicitly marked 'noindex, follow' as requested in prompt A2
    rendered = _render_page_shell(base_html, title, desc, canonical, "noindex, follow", body)
    return HTMLResponse(content=rendered, status_code=status.HTTP_200_OK)


# --- CATCH-ALL ROUTE (Registered at the very end of app routing) ---

@catch_all_router.api_route("/{path:path}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def handle_catch_all_404(path: str, db: Session = Depends(get_db)):
    """
    Catch-all router strictly for unmatched GET/HEAD navigation routes.
    Returns HTTP 404 with <title>Page Not Found | TradeCall India</title>,
    <meta name="robots" content="noindex, nofollow">, no canonical, and links to / and top city hubs.
    Guards against matching /api/, /assets/, /uploads/, /sitemap*.xml, /robots.txt, /favicon.ico, or static files.
    """
    clean_path = path.lower().strip("/")

    # Static assets, APIs, and file extensions MUST NOT return 404 HTML
    if (
        clean_path.startswith("api/")
        or clean_path.startswith("assets/")
        or clean_path.startswith("uploads/")
        or clean_path.startswith("static/")
        or clean_path.startswith("sitemap")
        or clean_path in ("robots.txt", "favicon.ico", "favicon.png", "icon.jpeg", "health")
        or any(clean_path.endswith(ext) for ext in [
            ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico",
            ".woff", ".woff2", ".ttf", ".eot", ".map", ".json", ".xml", ".txt"
        ])
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    base_html = load_base_index_html()
    active_cities = get_active_cities_summary(db)
    top_links = []
    for c in active_cities[:8]:
        top_links.append(f'<li><a href="/properties/{c["slug"]}">Properties in {c["name"]}</a></li>')
    links_html = "\n        ".join(top_links)

    body = f"""<main style="padding: 40px 20px; text-align: center; font-family: sans-serif;">
      <h1>Page Not Found</h1>
      <p>The page you requested could not be found. It may have been moved, renamed, or is temporarily unavailable.</p>
      <section style="margin-top: 24px;">
        <h2>Explore Verified Properties</h2>
        <ul style="list-style: none; padding: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 12px;">
          <li><a href="/">TradeCall Home</a></li>
          {links_html}
        </ul>
      </section>
    </main>"""

    rendered = _render_page_shell(
        base_html=base_html,
        title="Page Not Found | TradeCall India",
        description="The requested page could not be found on TradeCall India.",
        canonical_url=None,  # No canonical tag on 404 as requested
        robots_content="noindex, nofollow",
        root_inner_html=body
    )
    return HTMLResponse(content=rendered, status_code=status.HTTP_404_NOT_FOUND)
