#!/usr/bin/env python3
"""
TradeCall.in SEO & Indexing Health Monitor
Automated validation of core URLs, sitemaps, legacy redirects, schemas, and keyword targets.
"""

import sys
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

BASE_URL = "https://tradecall.in"

CORE_URLS = [
    ("/", 200, "Homepage"),
    ("/about", 200, "About Page"),
    ("/contact", 200, "Contact Page"),
    ("/cities", 200, "Cities Index"),
    ("/business-directory", 200, "Business Directory"),
    ("/blog", 200, "Blog Index"),
    ("/privacy", 200, "Privacy Policy"),
    ("/terms-of-use", 200, "Terms of Use"),
    ("/properties/palwal", 200, "Palwal City Hub"),
    ("/properties/faridabad", 200, "Faridabad City Hub"),
    ("/hi/properties/palwal", 200, "Palwal Hindi Pilot Hub"),
    ("/hi/properties/faridabad", 200, "Faridabad Hindi Pilot Hub"),
    ("/palwal/omaxe-city-phase-ii", 200, "Omaxe City Phase-II Sub-Locality"),
    ("/listed-on-tradecall.svg", 200, "Partner Badge SVG"),
    ("/robots.txt", 200, "robots.txt"),
    ("/sitemap_index.xml", 200, "Sitemap Index"),
]

REDIRECT_URLS = [
    ("/privacy-policy", 301, "/privacy"),
    ("/terms", 301, "/terms-of-use"),
]

LEGACY_410_URLS = [
    ("/blog/blog-detail/585/35/tradecall.in", 410, "Legacy blog post"),
    ("/blog/blog-detail/739/53/tradecall.in", 410, "Legacy blog post"),
    ("/pages/vpa-services", 410, "Legacy retired service"),
]

KEYWORD_TARGETS = [
    {
        "query": "Property for sale in Palwal",
        "target_url": f"{BASE_URL}/properties/palwal",
        "title_keyword": "Palwal",
    },
    {
        "query": "Residential plots in Palwal",
        "target_url": f"{BASE_URL}/palwal/omaxe-city-phase-ii",
        "title_keyword": "Omaxe City Phase-II",
    },
    {
        "query": "Property for sale in Faridabad",
        "target_url": f"{BASE_URL}/properties/faridabad",
        "title_keyword": "Faridabad",
    },
    {
        "query": "पलवल में प्रॉपर्टी",
        "target_url": f"{BASE_URL}/hi/properties/palwal",
        "title_keyword": "पलवल",
    }
]


def check_url(url, expected_code, name):
    full_url = f"{BASE_URL}{url}" if url.startswith("/") else url
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(full_url, headers={"User-Agent": "TradeCall-SEO-Monitor/1.0"})
    try:
        res = opener.open(req)
        status_code = res.status
    except urllib.error.HTTPError as e:
        status_code = e.code

    pass_status = status_code == expected_code
    mark = "PASS" if pass_status else "FAIL"
    print(f"[{mark}] {name:<35} {full_url:<55} -> {status_code} (expected {expected_code})")
    return pass_status


def check_sitemaps():
    print("\n--- SITEMAP VALIDATION ---")
    sitemap_idx = f"{BASE_URL}/sitemap_index.xml"
    try:
        req = urllib.request.urlopen(sitemap_idx)
        xml = req.read()
        root = ET.fromstring(xml)
        namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        sitemaps = root.findall('ns:sitemap', namespaces)
        print(f"[PASS] sitemap_index.xml parsed successfully with {len(sitemaps)} child sitemaps.")
        for sm in sitemaps:
            loc = sm.find('ns:loc', namespaces).text
            s_req = urllib.request.urlopen(loc)
            s_xml = s_req.read()
            s_root = ET.fromstring(s_xml)
            url_nodes = s_root.findall('ns:url', namespaces)
            print(f"       -> {loc}: {len(url_nodes)} URLs (HTTP {s_req.status})")
        return True
    except Exception as e:
        print(f"[FAIL] Error parsing sitemaps: {e}")
        return False


def check_keyword_targets():
    print("\n--- KEYWORD & META TAG BASELINE ---")
    all_passed = True
    for t in KEYWORD_TARGETS:
        try:
            req = urllib.request.Request(t["target_url"], headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req).read().decode("utf-8")
            title_m = re.search(r"<title>(.*?)</title>", html)
            title = title_m.group(1) if title_m else ""
            has_kw = t["title_keyword"].lower() in title.lower()
            mark = "PASS" if has_kw else "FAIL"
            print(f"[{mark}] Query: '{t['query']}'")
            print(f"       Target: {t['target_url']}")
            print(f"       Title:  {title}")
            if not has_kw:
                all_passed = False
        except Exception as e:
            print(f"[FAIL] Query '{t['query']}': {e}")
            all_passed = False
    return all_passed


def main():
    print("=" * 80)
    print("TradeCall.in SEO & Indexing Health Monitor")
    print(f"Target host: {BASE_URL}")
    print("=" * 80)

    print("\n--- CORE URLS CHECK ---")
    core_ok = all(check_url(u, c, n) for u, c, n in CORE_URLS)

    print("\n--- 301 REDIRECTS CHECK ---")
    redir_ok = all(check_url(u, c, f"Redirect to {t}") for u, c, t in REDIRECT_URLS)

    print("\n--- 410 GONE LEGACY URLS CHECK ---")
    legacy_ok = all(check_url(u, c, n) for u, c, n in LEGACY_410_URLS)

    sitemaps_ok = check_sitemaps()
    keywords_ok = check_keyword_targets()

    print("\n" + "=" * 80)
    if core_ok and redir_ok and legacy_ok and sitemaps_ok and keywords_ok:
        print("ALL SEO MONITORING CHECKS PASSED SUCCESSFULLY.")
        return 0
    else:
        print("WARNING: ONE OR MORE CHECKS FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
