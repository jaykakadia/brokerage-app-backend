"""
Seed 6 factual, comprehensive, legally accurate real estate guides for TradeCall India.
Covers DTCP, Jamabandi, Section 7A, stamp duty slabs, circle rates, and top NCR localities.
"""
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.models.blog import Blog

GUIDES = [
    {
        "title": "How to Check Plot Approvals and Registry Documents in Haryana",
        "permalink": "how-to-check-plot-approvals-and-registry-documents-in-haryana",
        "category": "legal-guide",
        "author": "TradeCall Legal & Research Team",
        "tags": "plot approvals, haryana registry, jamabandi, dtcp haryana, section 7a, land verification",
        "content": """<article class="guide-article">
  <p class="guide-lead">Purchasing a residential plot or agricultural land in Haryana offers high appreciation potential, but verifying approvals and revenue records before paying any token money (bayana) is essential to safeguard your investment.</p>

  <h2>1. Verify DTCP Approval and License Status</h2>
  <p>The Directorate of Town and Country Planning (DTCP) Haryana regulates urban development across the state. Before buying any plot in a private colony or township:</p>
  <ul>
    <li><strong>Check the DTCP License Number:</strong> Request the developer's license certificate issued under the Haryana Development and Regulation of Urban Areas Act, 1975. You can verify licensed colonies online on the official DTCP Haryana portal (tcpharyana.gov.in).</li>
    <li><strong>Verify the Approved Layout Plan:</strong> Ensure the specific plot number, road width (minimum 9 to 12 meters), and park areas match the sanctioned layout drawing. Plots cut in unauthorized layouts face demolition and lack utility connections.</li>
    <li><strong>Deen Dayal Jan Awas Yojana (DDJAY):</strong> For affordable plotted housing colonies under DDJAY, verify that the developer has mortgaged the required 50% saleable area with the government and obtained commercial release permissions.</li>
  </ul>

  <h2>2. Check Section 7A NOC Requirements</h2>
  <p>Under Section 7A of the Haryana Development and Regulation of Urban Areas Act, the registration of agricultural land below 1 acre in notified urban areas requires a No Objection Certificate (NOC) from the District Town Planner (DTP). Without this NOC, the Sub-Registrar / Tehsildar cannot legally register the sale deed. Buying land in an unapproved pocket without Section 7A clearance leads to stalled registry and utility connection refusals.</p>

  <h2>3. Inspect Jamabandi (Nakal) on Web-HALRIS</h2>
  <p>Revenue records in Haryana are maintained on the official <strong>Jamabandi portal (jamabandi.nic.in)</strong> managed by the Department of Revenue & Disaster Management:</p>
  <ul>
    <li><strong>Check Khewat, Khatoni, and Khasra Numbers:</strong> Request the recent Jamabandi copy (Record of Rights) from the seller. Look up the Khasra number on the Jamabandi portal to verify that the seller is the recorded owner.</li>
    <li><strong>Verify Mutation (Inteqal / Dakhil Kharij):</strong> Ensure the previous transaction was duly mutated in the revenue records. A sale deed without a sanctioned Inteqal means revenue records still show the earlier owner.</li>
    <li><strong>Check Encumbrance and Mortgages:</strong> Look at the <em>Bilmukammal</em> / Remarks column (Kaifiyat) in the Jamabandi. Any existing bank loan, court stay, or government attachment will be noted here.</li>
  </ul>

  <h2>4. Demarcation and Physical Nishandehi</h2>
  <p>Before closing the transaction, apply for official <em>Nishandehi</em> (demarcation) through the local Halqa Patwari. The Patwari visits the site with revenue measuring chains (Gatha/Zarib) and revenue maps (Sajra) to fix exact physical corner pillars, ensuring you do not pay for land encroached by neighbors or roads.</p>

  <p>Looking for verified residential and agricultural land? Explore <a href="/properties/palwal">verified plots in Palwal</a> and <a href="/properties/faridabad">residential plots in Faridabad</a> on TradeCall India directly with genuine owners and zero brokerage.</p>
</article>"""
    },
    {
        "title": "Documents to Verify Before Buying Property in Palwal",
        "permalink": "documents-to-verify-before-buying-property-in-palwal",
        "category": "buyer-guide",
        "author": "TradeCall Legal & Research Team",
        "tags": "palwal property, documents checklist, sale deed, inteqal, municipal council palwal",
        "content": """<article class="guide-article">
  <p class="guide-lead">Palwal has emerged as a premier logistics, industrial, and residential corridor along NH-19 (Delhi-Agra Highway) and the KMP Expressway. Here is the complete document checklist to inspect before buying property in Palwal.</p>

  <h2>1. 30-Year Title Deed Chain (Sale Deed / Conveyance Deed)</h2>
  <p>Examine the original registered Sale Deed (Bainama). Ensure you inspect the unbroken chain of transfer deeds going back 30 years to confirm clear, undisputed ownership without inheritance disputes or partial co-sharer claims.</p>

  <h2>2. Sanctioned Mutation (Inteqal) from Palwal Tehsil</h2>
  <p>Registration of the sale deed at the Palwal Sub-Registrar Office (located at Mini Secretariat, Palwal) must be followed by mutation in the Tehsil records. Ask the seller for the latest sanctioned Mutation Order copy (Inteqal Intikhab) confirming their name as the current titleholder in the revenue register.</p>

  <h2>3. Municipal Council (Nagar Parishad) Dues Clearance</h2>
  <p>For properties located within the municipal limits of Palwal (such as Kailash Nagar, Panchwati, or Old GT Road):</p>
  <ul>
    <li><strong>Property Tax Assessment:</strong> Check that the property has a unique Property ID assigned by Nagar Parishad Palwal.</li>
    <li><strong>No Dues Certificate (NDC):</strong> Verify that all property taxes, development charges, and water sewerage dues are paid up to date via the Haryana Urban Local Bodies (ULB) portal.</li>
  </ul>

  <h2>4. Non-Encumbrance Certificate (Bar-Mukammal)</h2>
  <p>Apply for a Non-Encumbrance Certificate at the Palwal Sub-Registrar office for the past 12 to 30 years. This certificate certifies whether the property has any registered mortgage, lien, lease, or court attachment.</p>

  <h2>5. HRERA Registration for New Projects</h2>
  <p>If buying a residential flat, floor, or plot in a new commercial or residential development in Palwal, check the Haryana Real Estate Regulatory Authority (HRERA Panchkula) registration number on haryanarera.gov.in. Developers cannot advertise or sell units in projects larger than 500 sq meters or 8 apartments without HRERA registration.</p>

  <p>Ready to find verified properties in Palwal? Browse <a href="/properties/palwal">plots, houses, and commercial property in Palwal</a> on TradeCall India with zero brokerage fees.</p>
</article>"""
    },
    {
        "title": "How to Evaluate Residential Plots in Faridabad",
        "permalink": "how-to-evaluate-residential-plots-in-faridabad",
        "category": "market-insights",
        "author": "TradeCall Research Team",
        "tags": "faridabad plots, hsvp faridabad, neharpar, greater faridabad, builder floors",
        "content": """<article class="guide-article">
  <p class="guide-lead">With seamless connectivity to South Delhi, Gurgaon via the Gurgaon-Faridabad Road, and Noida via the FNG corridor, Faridabad offers diverse plotting opportunities across established HSVP sectors and Greater Faridabad.</p>

  <h2>1. HSVP (HUDA) Sectors vs. Private Townships</h2>
  <p>Understand the land administration differences across Faridabad:</p>
  <ul>
    <li><strong>HSVP Sectors (Sectors 14, 15, 16, 21, 28, 46, 85):</strong> Developed by Haryana Shehri Vikas Pradhikaran with planned underground drainage, wide sector roads, and established community parks. Plots here carry Allotment Letters, Re-allotment Letters, and Conveyance Deeds issued directly by HSVP.</li>
    <li><strong>Greater Faridabad / Neharpar (Sectors 75 to 89):</strong> Features modern private townships like BPTP Parklands, Puri Aman Villas, and Omaxe. Verify that the internal road infrastructure, sector master roads, and trunk sewer lines are operational and that maintenance agreements are transparent.</li>
  </ul>

  <h2>2. Road Width and Stilt + 4 Floor Permissions</h2>
  <p>Building regulations in Haryana allow stilt plus four (S+4) floor construction subject to specific plot road width requirements (typically minimum 10 to 12 meters road width and mutual neighbor consent policies in notified sectors). If you plan to build independent builder floors for resale, ensure the plot frontage and road width comply with the latest Haryana Town and Country Planning building code.</p>

  <h2>3. Soil Bearing Capacity and Groundwater</h2>
  <p>Parts of Neharpar have higher groundwater tables and alluvial soil. Before purchasing a large plot for multi-story construction, commission an independent soil testing report to determine foundation depth and basement waterproofing requirements.</p>

  <h2>4. Distance from Rapid Transit and Expressways</h2>
  <p>Evaluate accessibility to key transit lines: the Violet Line Delhi Metro stations (Escorts Mujesar, Bata Chowk, Neelam Chowk, Old Faridabad) and direct access ramps to the Delhi-Mumbai Expressway. Properties within 10 to 15 minutes of these transport corridors enjoy superior capital appreciation and rental yields.</p>

  <p>Explore <a href="/properties/faridabad">verified residential plots and builder floors in Faridabad</a> on TradeCall India directly from verified sellers.</p>
</article>"""
    },
    {
        "title": "Property Registration and Purchase Costs in Haryana",
        "permalink": "property-registration-and-purchase-costs-in-haryana",
        "category": "legal-guide",
        "author": "TradeCall Legal & Research Team",
        "tags": "haryana stamp duty, property registration fee, circle rate palwal, faridabad circle rates, egras haryana",
        "content": """<article class="guide-article">
  <p class="guide-lead">When budgeting for property purchase in Haryana, transaction costs beyond the agreed purchase price include stamp duty, registration charges, municipal cess, and documentation fees. Here is the official fee structure across Haryana.</p>

  <h2>1. Haryana Stamp Duty Rates (2026 Structure)</h2>
  <p>Stamp duty in Haryana varies based on the buyer's gender and whether the property falls within an urban (Municipal Corporation / Council) or rural area:</p>
  <table class="guide-table" style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <thead>
      <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;">
        <th style="padding: 10px; text-align: left;">Category of Buyer</th>
        <th style="padding: 10px; text-align: left;">Urban / Municipal Area</th>
        <th style="padding: 10px; text-align: left;">Rural / Outside MC Area</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Male Buyer</strong></td>
        <td style="padding: 10px;">7.0% (5% Stamp Duty + 2% MC Cess)</td>
        <td style="padding: 10px;">5.0%</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Female Buyer</strong></td>
        <td style="padding: 10px;">5.0% (3% Stamp Duty + 2% MC Cess)</td>
        <td style="padding: 10px;">3.0%</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Joint Ownership (Male + Female)</strong></td>
        <td style="padding: 10px;">6.0% (4% Stamp Duty + 2% MC Cess)</td>
        <td style="padding: 10px;">4.0%</td>
      </tr>
    </tbody>
  </table>
  <p><em>Pro Tip: Registering property in a woman's name or jointly with a female family member saves 1% to 2% in stamp duty across Haryana.</em></p>

  <h2>2. Registration Fees Slabs in Haryana</h2>
  <p>In addition to stamp duty, Haryana charges a tiered registration fee based on the property valuation (calculated as the higher of circle rate valuation or declared agreement value):</p>
  <ul>
    <li>Properties valued up to ₹50,000: ₹100</li>
    <li>Properties valued ₹50,001 to ₹1,00,000: ₹500</li>
    <li>Properties valued ₹1,00,001 to ₹5,00,000: ₹1,000</li>
    <li>Properties valued ₹5,00,001 to ₹10,00,000: ₹5,000</li>
    <li>Properties valued ₹10,00,001 to ₹25,00,000: ₹10,000</li>
    <li>Properties valued ₹25,00,001 to ₹50,00,000: ₹15,000</li>
    <li>Properties valued ₹50,00,001 to ₹1 Crore: ₹25,000</li>
    <li>Properties valued above ₹1 Crore: Capped at maximum ₹50,000</li>
  </ul>

  <h2>3. Understanding Circle Rates (Collector Rates)</h2>
  <p>Circle rates are the minimum government-mandated benchmark prices per square yard or per acre below which a property cannot be registered. If the transaction value is ₹40 Lakh but the circle rate valuation is ₹50 Lakh, stamp duty must be paid on ₹50 Lakh. District administrations in Palwal and Faridabad revise collector rates periodically.</p>

  <h2>4. E-GRAS Portal and Appointment Booking</h2>
  <p>Stamp duty in Haryana is paid electronically via the <strong>e-GRAS portal (egrashry.nic.in)</strong>. Once the e-challan is generated and stamped, book an appointment slot on the Web-HALRIS portal for biometric verification and photograph capture at the Sub-Registrar office.</p>

  <p>Calculate your exact property costs and explore zero-brokerage listings in <a href="/properties/palwal">Palwal</a> and <a href="/properties/faridabad">Faridabad</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "How to Choose a Suitable Residential Locality in Palwal",
        "permalink": "how-to-choose-suitable-residential-locality-in-palwal",
        "category": "buyer-guide",
        "author": "TradeCall Research Team",
        "tags": "palwal localities, omaxe city palwal, huda sector 2 palwal, kailash nagar, panchwati",
        "content": """<article class="guide-article">
  <p class="guide-lead">Palwal is rapidly transforming into a major residential hub in the National Capital Region. Selecting the right locality depends on your budget, proximity to transit, and preference for integrated gated townships versus established residential sectors.</p>

  <h2>1. Omaxe City (Phase-I & Phase-II) — Gated Township Living</h2>
  <p>Located directly along NH-19 (Delhi-Mathura Highway), Omaxe City is Palwal's flagship integrated township offering residential plots, independent villas, and commercial shops. Key advantages include 24x7 security, underground electricity cables, wide asphalt roads, landscaped parks, and an operational shopping plaza. Ideal for families seeking a clean, planned urban environment with immediate highway access.</p>

  <h2>2. HUDA Sector 2 — Prime Administrative Hub</h2>
  <p>Developed by the Haryana Shehri Vikas Pradhikaran, Sector 2 is situated near the District Court, Mini Secretariat, and SP Office. It features wide sector roads, reliable municipal water supply, underground drainage, and established parks. Due to its central administrative location and limited plot availability, Sector 2 commands solid resale demand and high appreciation.</p>

  <h2>3. Kailash Nagar and Panchwati Colony — Established Core Localities</h2>
  <p>For buyers prioritizing walkability to the historic Palwal railway station, Old GT Road, and central bazaars, Kailash Nagar and Panchwati Colony provide established social infrastructure. Schools, clinics, grocery markets, and banks are within walking distance, making them popular for joint families and rental demand.</p>

  <h2>4. Lavender Green Society and New Extension Colony</h2>
  <p>These emerging residential pockets offer competitively priced plots and builder floors. They are well-suited for first-time buyers looking for entry-level residential plots with fast connectivity to the Palwal-Sohna Road and the upcoming Western Peripheral (KMP) expressway interchanges.</p>

  <h2>Locality Comparison Checklist</h2>
  <ul>
    <li><strong>Connectivity:</strong> Travel time to NH-19, KMP Expressway, and Delhi-Mumbai Expressway interchange at Mandkola.</li>
    <li><strong>Water & Drainage:</strong> Check whether the colony connects to the municipal sewer line or relies on individual soak pits.</li>
    <li><strong>Registry Type:</strong> Confirm that the plot is located in an approved zone with Section 7A compliance and direct registry eligibility.</li>
  </ul>

  <p>Compare verified plots and houses in <a href="/palwal/omaxe-city-phase-ii">Omaxe City Phase-II</a> and throughout <a href="/properties/palwal">Palwal property listings</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "Common Legal and Practical Checks Before Buying a Plot in Haryana",
        "permalink": "common-legal-and-practical-checks-before-buying-plot-in-haryana",
        "category": "legal-guide",
        "author": "TradeCall Legal Team",
        "tags": "buying plot haryana, legal checks, bayana agreement, gpa property risk, rera haryana",
        "content": """<article class="guide-article">
  <p class="guide-lead">Land transactions carry unique legal complexities that do not apply to ready-to-move apartments. Before handing over token money for any residential or agricultural plot in Haryana, execute these seven vital checks.</p>

  <h2>1. Insist on a Registered Sale Deed (Avoid GPA Sales)</h2>
  <p>The Supreme Court of India in the landmark <em>Suraj Lamp & Industries</em> judgment made it clear that property transfers via General Power of Attorney (GPA), Agreement to Sell, or Will do not confer legal ownership title. Always insist on a registered Conveyance Deed or Sale Deed registered at the local Sub-Registrar office.</p>

  <h2>2. Verify Physical Site Demarcation and Boundaries</h2>
  <p>Never rely solely on map drawings. Physically visit the plot, measure the plot dimensions (frontage and depth in feet and gaj), and ensure the plot boundaries match the Aks Shajra (revenue map). Confirm that there are no high-tension electricity lines (HT lines) passing overhead or public drains passing through the land.</p>

  <h2>3. Draft the Agreement to Sell (Bayana) with Protective Clauses</h2>
  <p>When paying earnest money (Bayana):</p>
  <ul>
    <li>Specify the total agreed sale consideration and the schedule of payments.</li>
    <li>Include a clear title warranty stating that the seller guarantees the property is free from all encumbrances, litigations, tax dues, and bank charges.</li>
    <li>Incorporate a clause stating that if the title is found defective during verification or if Section 7A NOC is rejected, the seller must refund the entire earnest money with interest within a defined timeframe.</li>
  </ul>

  <h2>4. Check for Agricultural Land Ceiling and Co-sharer Rights</h2>
  <p>If buying agricultural land, check whether the seller is an exclusive owner or a joint co-sharer in a shared Khewat. Under the Punjab Land Revenue Act as applicable to Haryana, a co-sharer can sell only their undivided share, not a specific demarcated physical piece of land without a formal partition (Taqseem) order from the Tehsildar.</p>

  <h2>5. Verify Identity and Family Consent</h2>
  <p>Cross-verify the seller's name, parentage, and photo ID against the registered deed and Jamabandi. In cases of ancestral Hindu Undivided Family (HUF) property, ensure all legal coparceners sign the sale deed or provide registered relinquishment deeds to avoid future title disputes.</p>

  <h2>6. Verify EDC/IDC and Infrastructure Charges</h2>
  <p>In licensed private townships and plotted colonies, check whether External Development Charges (EDC) and Internal Development Charges (IDC) have been fully remitted by the developer to DTCP. Outstanding developer dues can lead to statutory notices and construction ban orders.</p>

  <p>Search verified, zero-brokerage plots and agricultural land directly from genuine owners on <a href="/properties/palwal">TradeCall Palwal</a> and <a href="/properties/faridabad">TradeCall Faridabad</a>.</p>
</article>"""
    }
]


def seed_blogs(db_url: str):
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    inserted = 0
    updated = 0

    try:
        now = datetime.now(timezone.utc)
        for g in GUIDES:
            existing = session.query(Blog).filter(Blog.permalink == g["permalink"]).first()
            if existing:
                existing.title = g["title"]
                existing.category = g["category"]
                existing.content = g["content"]
                existing.author = g["author"]
                existing.tags = g["tags"]
                existing.status = "published"
                existing.updated_at = now
                updated += 1
            else:
                new_blog = Blog(
                    title=g["title"],
                    permalink=g["permalink"],
                    category=g["category"],
                    content=g["content"],
                    author=g["author"],
                    tags=g["tags"],
                    status="published",
                    created_at=now,
                    updated_at=now
                )
                session.add(new_blog)
                inserted += 1

        session.commit()
        print(f"Successfully seeded blogs: {inserted} inserted, {updated} updated.")
    except Exception as e:
        session.rollback()
        print(f"Error seeding blogs: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable not set.")
        sys.exit(1)
    seed_blogs(db_url)
