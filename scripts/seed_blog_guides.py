"""
Seed 6 factual, comprehensive, legally accurate real estate guides for TradeCall India.
Covers DTCP, Jamabandi, Section 7A, stamp duty slabs, circle rates, and top NCR localities.
Updated with official Haryana Revenue Department stamp duty rates and Income-tax Act, 2025 (Section 393(1) & Form 141 Schedule B).
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
  <p class="guide-lead">Purchasing a residential plot or agricultural land in Haryana requires thorough verification of statutory town planning approvals and revenue records before entering into an agreement to sell or transferring earnest money (bayana).</p>

  <h2>1. Verify DTCP Approval and License Status</h2>
  <p>The Directorate of Town and Country Planning (DTCP) Haryana regulates urban land development across the state under the Haryana Development and Regulation of Urban Areas Act, 1975:</p>
  <ul>
    <li><strong>DTCP License Verification:</strong> Verify the developer's license number, validity period, and promoter entity on the official <a href="https://tcpharyana.gov.in" target="_blank" rel="noopener noreferrer">DTCP Haryana portal (tcpharyana.gov.in)</a>. Unapproved colonies lack development licenses and are vulnerable to demolition actions.</li>
    <li><strong>Sanctioned Layout Plan:</strong> Inspect the approved layout drawing bearing the Chief Town Planner's seal. Check the specific plot number, exact dimensions, road width (typically 9m to 12m minimum), green belt reservations, and public utility pockets.</li>
    <li><strong>Deen Dayal Jan Awas Yojana (DDJAY):</strong> For affordable plotted colonies under DDJAY, confirm that the builder has mortgaged the required percentage of saleable plots with DTCP as performance security and obtained the formal release order before offering those specific plots for sale.</li>
  </ul>

  <h2>2. Section 7A NOC from the District Town Planner</h2>
  <p>Under Section 7A of the Haryana Development and Regulation of Urban Areas Act, 1975, the transfer or registration of vacant land or agricultural plots measuring less than notified thresholds (such as 1 acre or 2 kanals in notified controlled areas) requires an official No Objection Certificate (NOC) from the District Town Planner (DTP). Without this Section 7A NOC, Sub-Registrars and Tehsildars are statutorily prohibited from registering conveyance deeds. Purchasing unapproved sub-divided agricultural land without Section 7A clearance prevents registration, mutation, and lawful utility connections.</p>

  <h2>3. Inspect Jamabandi (Record of Rights) on Web-HALRIS</h2>
  <p>Land revenue records in Haryana are maintained digitally on the Department of Revenue &amp; Disaster Management's official <a href="https://jamabandi.nic.in" target="_blank" rel="noopener noreferrer">Jamabandi portal (jamabandi.nic.in)</a>:</p>
  <ul>
    <li><strong>Khewat, Khatoni, and Khasra Numbers:</strong> Obtain the latest Jamabandi copy (Nakal). Search by owner name or Khasra number on Web-HALRIS to confirm that the seller is the absolute recorded owner and verify their exact share.</li>
    <li><strong>Sanctioned Mutation (Inteqal / Dakhil Kharij):</strong> Verify that the mutation order in favor of the current seller has been entered and sanctioned by the revenue officer. A registered sale deed without a sanctioned Inteqal leaves the predecessor's name on the revenue record.</li>
    <li><strong>Remarks Column (Kaifiyat / Bar-Mukammal):</strong> Inspect the remarks column for any encumbrance, including hypothecation to banks, court attachments, government acquisition proceedings, or civil court stay orders.</li>
  </ul>

  <h2>4. Physical Demarcation (Nishandehi)</h2>
  <p>Before executing the final deed, apply for an official site demarcation (<em>Nishandehi</em>) through the local Halqa Patwari and Kanungo. The Patwari surveys the parcel using revenue measurement chains (Gatha/Zarib) and village revenue maps (Aks Shajra) to fix physical corner boundary pillars, ensuring the ground boundaries match the revenue record without encroachments.</p>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Directorate of Town &amp; Country Planning Haryana (<a href="https://tcpharyana.gov.in" target="_blank" rel="noopener noreferrer">tcpharyana.gov.in</a>), Department of Revenue &amp; Disaster Management Haryana (<a href="https://jamabandi.nic.in" target="_blank" rel="noopener noreferrer">jamabandi.nic.in</a>).<br>
    <em>Last Reviewed: October 2026. This guide is for educational purposes. Verify specific khasra and title particulars with the jurisdictional Sub-Registrar before executing transactions.</em>
  </div>

  <p style="margin-top: 16px;">Looking for verified property? Explore <a href="/properties/palwal">verified properties in Palwal</a> and <a href="/properties/faridabad">properties in Faridabad</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "Documents to Verify Before Buying Property in Palwal",
        "permalink": "documents-to-verify-before-buying-property-in-palwal",
        "category": "buyer-guide",
        "author": "TradeCall Legal & Research Team",
        "tags": "palwal property, documents checklist, sale deed, inteqal, municipal council palwal",
        "content": """<article class="guide-article">
  <p class="guide-lead">With expanding connectivity along NH-19 (Delhi-Agra Highway) and the Western Peripheral Expressway (KMP), property transactions across Palwal district require disciplined document diligence across revenue and municipal authorities.</p>

  <h2>1. 30-Year Chain of Title (Sale Deeds / Conveyance Deeds)</h2>
  <p>Inspect the original registered title deeds establishing an unbroken 30-year chain of title. Verify that each preceding transfer—whether by Sale Deed, Gift Deed, Partition Deed, or Inheritance—was registered at the Palwal Sub-Registrar Office (located at the Mini Secretariat, Palwal) without missing intermediate conveyance links.</p>

  <h2>2. Sanctioned Mutation Order (Inteqal Intikhab)</h2>
  <p>Execution of a sale deed must be followed by mutation in the revenue records of Tehsil Palwal. Obtain the certified copy of the sanctioned Mutation Order (Inteqal Intikhab) confirming that the seller's title stands entered in the current Jamabandi register.</p>

  <h2>3. Nagar Parishad Palwal Dues &amp; Property ID Verification</h2>
  <p>For properties situated within the municipal limits of Palwal (such as Kailash Nagar, Panchwati, Camp Colony, or Old GT Road):</p>
  <ul>
    <li><strong>Urban Local Bodies Property ID:</strong> Verify the unique Property ID assigned by Nagar Parishad Palwal on the official <a href="https://ulbharyana.gov.in" target="_blank" rel="noopener noreferrer">Urban Local Bodies Haryana portal (ulbharyana.gov.in)</a>.</li>
    <li><strong>No Dues Certificate (NDC):</strong> Generate an official online NDC confirming that property taxes, development charges, fire tax, and water/sewerage assessments are fully cleared up to date.</li>
  </ul>

  <h2>4. Non-Encumbrance Certificate (Bar-Mukammal)</h2>
  <p>Apply for a certified Non-Encumbrance Certificate at the Palwal Sub-Registrar office covering a minimum search period of 12 to 30 years to verify that the property has not been mortgaged, leased, or attached by court order.</p>

  <h2>5. HRERA Panchkula Project Registration</h2>
  <p>If purchasing a plot, apartment, or commercial unit in a newly launched development in Palwal, verify the project's registration on the <a href="https://haryanarera.gov.in" target="_blank" rel="noopener noreferrer">Haryana Real Estate Regulatory Authority portal (haryanarera.gov.in)</a> under HRERA Panchkula jurisdiction (which oversees all districts in Haryana outside Gurugram). Real estate promoters cannot lawfully market or sell units in projects exceeding 500 sq meters or 8 units without an active HRERA registration number.</p>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Nagar Parishad Palwal / ULB Haryana (<a href="https://ulbharyana.gov.in" target="_blank" rel="noopener noreferrer">ulbharyana.gov.in</a>), HRERA Panchkula (<a href="https://haryanarera.gov.in" target="_blank" rel="noopener noreferrer">haryanarera.gov.in</a>), Revenue Department Haryana (<a href="https://jamabandi.nic.in" target="_blank" rel="noopener noreferrer">jamabandi.nic.in</a>).<br>
    <em>Last Reviewed: October 2026. Consult certified revenue counsel or the Palwal Sub-Registrar to verify specific parcel titles.</em>
  </div>

  <p style="margin-top: 16px;">Browse verified listings in <a href="/properties/palwal">Palwal property listings</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "How to Evaluate Residential Plots in Faridabad",
        "permalink": "how-to-evaluate-residential-plots-in-faridabad",
        "category": "market-insights",
        "author": "TradeCall Research Team",
        "tags": "faridabad plots, hsvp faridabad, neharpar, greater faridabad, builder floors",
        "content": """<article class="guide-article">
  <p class="guide-lead">Faridabad's real estate market offers two distinct plotted development models: established urban sectors governed by Haryana Shehri Vikas Pradhikaran (HSVP) and private townships across Greater Faridabad (Neharpar). Evaluating a residential plot requires assessing regulatory status, structural allowances, and physical infrastructure.</p>

  <h2>1. HSVP Sectors vs. Licensed Private Townships</h2>
  <p>Understand the land administration framework across Faridabad:</p>
  <ul>
    <li><strong>HSVP Sectors (Sectors 14, 15, 16, 21, 28, 46, 85):</strong> Developed by <a href="https://hsvp.org.in" target="_blank" rel="noopener noreferrer">HSVP (formerly HUDA, hsvp.org.in)</a>. Plots carry formal Allotment Letters, Re-allotment Letters, and Conveyance Deeds issued by HSVP. Title transfers require official HSVP Transfer Permissions and No Dues Certificates.</li>
    <li><strong>Greater Faridabad / Neharpar (Sectors 75 to 89):</strong> Plotted developments governed by DTCP licenses under DDJAY or integrated township policies. Verify that the developer has paid all External Development Charges (EDC) and Internal Development Charges (IDC) to DTCP Haryana, and that municipal trunk services (water, sewer, stormwater) are connected.</li>
  </ul>

  <h2>2. Building Byelaws and Stilt + 4 (S+4) Policy</h2>
  <p>In Haryana, construction permissions for independent builder floors (Stilt + 4 floors) are subject to stringent state guidelines:</p>
  <ul>
    <li>Road width must meet the statutory threshold (typically 10 meters or wider in notified sectors).</li>
    <li>Mutual written consent from adjoining plot owners is required in existing residential sectors where S+4 was not originally sanctioned in the layout.</li>
    <li>Adequate structural safety certification, rainwater harvesting, and fire clearances must be submitted to the Municipal Corporation of Faridabad (MCF) or HSVP before building plan approval.</li>
  </ul>

  <h2>3. Infrastructure and Transit Proximity</h2>
  <p>Examine physical proximity to key transport corridors: the Delhi Metro Violet Line (stations at Bata Chowk, Neelam Chowk, Old Faridabad), the Delhi-Mumbai Expressway bypass link, and the Faridabad-Noida-Ghaziabad (FNG) expressway corridor. Plots with direct access to 24m or 30m sector roads command superior long-term liquidity and rental demand.</p>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Haryana Shehri Vikas Pradhikaran (<a href="https://hsvp.org.in" target="_blank" rel="noopener noreferrer">hsvp.org.in</a>), Municipal Corporation of Faridabad (<a href="https://mcfbd.com" target="_blank" rel="noopener noreferrer">mcfbd.com</a>), DTCP Haryana (<a href="https://tcpharyana.gov.in" target="_blank" rel="noopener noreferrer">tcpharyana.gov.in</a>).<br>
    <em>Last Reviewed: October 2026. Verify current sector zoning and building regulations with MCF/HSVP prior to plot acquisition.</em>
  </div>

  <p style="margin-top: 16px;">Explore <a href="/properties/faridabad">verified residential plots and floors in Faridabad</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "Property Registration and Purchase Costs in Haryana",
        "permalink": "property-registration-and-purchase-costs-in-haryana",
        "category": "legal-guide",
        "author": "TradeCall Legal & Research Team",
        "tags": "haryana stamp duty, property registration fee, circle rate palwal, faridabad circle rates, egras haryana, section 393 income tax",
        "content": """<article class="guide-article">
  <p class="guide-lead">Budgeting for property acquisition in Haryana requires an accurate understanding of statutory stamp duty rates, municipal surcharges, registration fee slabs, and applicable tax deduction at source (TDS) provisions under Indian tax law.</p>

  <h2>1. Official Haryana Stamp Duty Rates Structure</h2>
  <p>Under the Indian Stamp Act, 1899 (as amended in its application to the State of Haryana) and the Haryana Municipal Act / Haryana Municipal Corporation Act, stamp duty on sale and conveyance deeds varies based on property location (Urban vs. Rural) and buyer ownership category:</p>

  <table class="guide-table" style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <thead>
      <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1;">
        <th style="padding: 10px; text-align: left;">Category of Buyer</th>
        <th style="padding: 10px; text-align: left;">Urban / Within Municipal Limits</th>
        <th style="padding: 10px; text-align: left;">Rural / Outside Municipal Limits</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Male Buyer (Sole or Male + Male)</strong></td>
        <td style="padding: 10px;"><strong>7.0%</strong> (5.0% Stamp Duty + 2.0% Municipal Duty)</td>
        <td style="padding: 10px;"><strong>5.0%</strong> (5.0% Stamp Duty)</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Female Buyer (Sole or Female + Female)</strong></td>
        <td style="padding: 10px;"><strong>5.0%</strong> (3.0% Stamp Duty + 2.0% Municipal Duty)</td>
        <td style="padding: 10px;"><strong>3.0%</strong> (3.0% Stamp Duty)</td>
      </tr>
      <tr style="border-bottom: 1px solid #e2e8f0;">
        <td style="padding: 10px;"><strong>Joint Ownership (Male &amp; Female)</strong></td>
        <td style="padding: 10px;"><strong>6.0%</strong> (4.0% Stamp Duty + 2.0% Municipal Duty)</td>
        <td style="padding: 10px;"><strong>4.0%</strong> (4.0% Stamp Duty)</td>
      </tr>
    </tbody>
  </table>

  <h3>Important Statutory Variations and Exceptions:</h3>
  <ul>
    <li><strong>Municipal Duty (2.0%):</strong> Applies to all properties situated within the notified limits of a Municipal Corporation, Municipal Council, Municipal Committee, or Cantonment Board in Haryana. In rural Gram Panchayat areas outside municipal limits, this 2.0% municipal surcharge is not charged.</li>
    <li><strong>Women Concession (2.0%):</strong> Women sole buyers receive a statutory 2.0% concession on stamp duty compared to male buyers across both urban and rural transactions. Joint ownership between a male and female buyer splits the concession (1.0% lower than male rate).</li>
    <li><strong>Family Blood-Relation Transfer Exemption:</strong> Under Haryana Revenue Department notification, transfer of immovable property or agricultural land among specified blood relations (father, mother, son, daughter, brother, sister, spouse, grandson, granddaughter) attracts <strong>nil (0%) stamp duty</strong>, subject only to nominal administrative registration fees.</li>
  </ul>

  <h2>2. Tiered Registration Fee Slabs in Haryana</h2>
  <p>In addition to stamp duty, Haryana levies a document registration fee based on the higher of the transaction consideration or the government circle rate valuation, capped at a maximum of ₹50,000:</p>
  <ul>
    <li>Valuation up to ₹50,000: ₹100</li>
    <li>Valuation ₹50,001 to ₹1,00,000: ₹500</li>
    <li>Valuation ₹1,00,001 to ₹5,00,000: ₹1,000</li>
    <li>Valuation ₹5,00,001 to ₹10,00,000: ₹5,000</li>
    <li>Valuation ₹10,00,001 to ₹25,00,000: ₹10,000</li>
    <li>Valuation ₹25,00,001 to ₹50,00,000: ₹15,000</li>
    <li>Valuation ₹50,00,001 to ₹1,00,00,000 (₹1 Crore): ₹25,000</li>
    <li>Valuation above ₹1 Crore: Capped at maximum ₹50,000</li>
  </ul>

  <h2>3. Income Tax / TDS Requirements for Property Purchases</h2>
  <p>Under the <strong>Income-tax Act, 2025</strong> (which came into effect on 1 April 2026), tax deduction at source on property transactions is governed as follows:</p>
  <ul>
    <li><strong>Governing Section:</strong> Section 393(1) of the Income-tax Act, 2025 [Table Serial No. 3(i)] governs TDS on the transfer of specified immovable property (other than agricultural land) from a resident seller (replacing legacy Section 194-IA under the 1961 Act).</li>
    <li><strong>Applicable Threshold &amp; Rate:</strong> If the total sale consideration or the stamp duty value (whichever is higher) is <strong>₹50 Lakh or more</strong>, the buyer must deduct <strong>1.0% TDS</strong> from the payment.</li>
    <li><strong>Challan-cum-Statement Form 141 (Schedule B):</strong> The buyer must remit the deducted tax and submit the statement using <strong>Form 141 (Schedule B)</strong> on the official <a href="https://incometax.gov.in" target="_blank" rel="noopener noreferrer">Income Tax e-Filing portal (incometax.gov.in)</a>.</li>
    <li><strong>No TAN Required for Resident Transactions:</strong> Individual or HUF buyers purchasing from a resident seller do not require a Tax Deduction Account Number (TAN); the transaction is authenticated using the buyer's and seller's PAN.</li>
    <li><strong>Non-Resident Sellers (NRIs):</strong> If the seller is a non-resident, Section 393(1) does not apply. Tax must be deducted under non-resident withholding provisions requiring the buyer to obtain a TAN, file Form 27Q, and deduct tax at applicable capital gains rates unless a lower deduction certificate under Section 398 is obtained.</li>
  </ul>

  <h2>4. Circle Rate Valuation and e-GRAS Challan Process</h2>
  <p>Stamp duty is calculated on the higher of the actual transaction value or the government-notified Collector Rate (Circle Rate) published on <a href="https://jamabandi.nic.in" target="_blank" rel="noopener noreferrer">jamabandi.nic.in</a>. Stamp duty must be paid electronically via the Haryana Government Receipts portal <a href="https://egrashry.nic.in" target="_blank" rel="noopener noreferrer">e-GRAS (egrashry.nic.in)</a> prior to booking the physical registry appointment slot at the Sub-Registrar office.</p>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Haryana Revenue &amp; Disaster Management Department (<a href="https://jamabandi.nic.in" target="_blank" rel="noopener noreferrer">jamabandi.nic.in</a>), e-GRAS Haryana (<a href="https://egrashry.nic.in" target="_blank" rel="noopener noreferrer">egrashry.nic.in</a>), Income Tax Department of India (<a href="https://incometax.gov.in" target="_blank" rel="noopener noreferrer">incometax.gov.in</a>).<br>
    <em>Last Reviewed: October 2026. Stamp duty and tax laws are subject to legislative amendments and municipal notification updates. Verify current rates with the jurisdictional Sub-Registrar before financial disbursement.</em>
  </div>

  <p style="margin-top: 16px;">Browse verified properties across <a href="/properties/palwal">Palwal</a> and <a href="/properties/faridabad">Faridabad</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "How to Choose a Suitable Residential Locality in Palwal",
        "permalink": "how-to-choose-suitable-residential-locality-in-palwal",
        "category": "buyer-guide",
        "author": "TradeCall Research Team",
        "tags": "palwal localities, omaxe city palwal, huda sector 2 palwal, kailash nagar, panchwati",
        "content": """<article class="guide-article">
  <p class="guide-lead">Selecting a residential locality in Palwal involves balancing connectivity to the National Highway network, municipal infrastructure development, and preference for integrated private townships versus HSVP government sectors.</p>

  <h2>1. Omaxe City (Phase-I &amp; Phase-II) — Integrated Highway Township</h2>
  <p>Fronting directly onto NH-19 (Delhi-Mathura Highway), Omaxe City is Palwal's premier DTCP-licensed township offering residential plots, built villas, and commercial shops. Key infrastructure includes underground cabling, paved sector roads, landscaped green belts, 24x7 security, and dedicated commercial areas. It provides immediate vehicular access towards Faridabad, Delhi, and Mathura without city traffic delays.</p>

  <h2>2. HUDA Sector 2 — Administrative Core &amp; Urban Amenities</h2>
  <p>Developed by HSVP, Sector 2 is situated adjacent to the Palwal District Administrative Complex (Mini Secretariat, District Court, and SP Office). It features established municipal water pipelines, underground sewage networks, wide sector avenues, and mature public parks. Due to limited supply and high administrative convenience, plots in Sector 2 maintain consistent capital demand.</p>

  <h2>3. Kailash Nagar, Panchwati Colony, and Camp Colony</h2>
  <p>For buyers who prioritize established social infrastructure, walkability to Palwal Railway Station, Old GT Road commercial markets, and historic schools, localities like Kailash Nagar, Panchwati Colony, and Camp Colony provide mature community ecosystems with vibrant retail access.</p>

  <h2>Essential Diligence Checklist Before Choosing a Locality:</h2>
  <ul>
    <li><strong>Section 7A Compliance:</strong> Confirm that the colony is DTCP-approved or regularized under Haryana Municipal policies. Unauthorized colonies lacking Section 7A NOC cannot obtain lawful registry or municipal sewerage connections.</li>
    <li><strong>Expressway Connectivity:</strong> Measure drive time to the KMP Expressway interchange and the Delhi-Mumbai Expressway access ramp at Mandkola.</li>
    <li><strong>Municipal Water &amp; Drainage:</strong> Verify whether the locality is connected to the Nagar Parishad Palwal trunk sewer network or relies on private soak wells.</li>
  </ul>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Nagar Parishad Palwal (<a href="https://ulbharyana.gov.in" target="_blank" rel="noopener noreferrer">ulbharyana.gov.in</a>), DTCP Haryana (<a href="https://tcpharyana.gov.in" target="_blank" rel="noopener noreferrer">tcpharyana.gov.in</a>).<br>
    <em>Last Reviewed: October 2026. Always inspect the layout approval and zoning notification before finalizing locality selection.</em>
  </div>

  <p style="margin-top: 16px;">Compare active listings in <a href="/palwal/omaxe-city-phase-ii">Omaxe City Phase-II</a> and throughout <a href="/properties/palwal">Palwal property listings</a> on TradeCall India.</p>
</article>"""
    },
    {
        "title": "Common Legal and Practical Checks Before Buying a Plot in Haryana",
        "permalink": "common-legal-and-practical-checks-before-buying-plot-in-haryana",
        "category": "legal-guide",
        "author": "TradeCall Legal Team",
        "tags": "buying plot haryana, legal checks, bayana agreement, gpa property risk, rera haryana",
        "content": """<article class="guide-article">
  <p class="guide-lead">Land transactions carry distinct legal and revenue risks that require structured verification before signing an agreement to sell or remitting financial advances. Here are seven statutory and practical checks every buyer must conduct in Haryana.</p>

  <h2>1. Insist on a Registered Conveyance Deed (Avoid GPA Sales)</h2>
  <p>The Supreme Court of India in <em>Suraj Lamp &amp; Industries Pvt. Ltd. v. State of Haryana</em> (2012) 1 SCC 656 held that property transfers executed via General Power of Attorney (GPA), Agreement to Sell, or Will do not confer legal ownership or convey title to immovable property. A lawful conveyance requires a duly stamped and registered Sale Deed (Bainama) executed at the jurisdictional Sub-Registrar office under Section 17 of the Registration Act, 1908.</p>

  <h2>2. Physical Ground Demarcation (Aks Shajra &amp; Nishandehi)</h2>
  <p>Never rely solely on private architectural drawings. Physically inspect the site with the Halqa Patwari to perform an official <em>Nishandehi</em> against the village revenue map (Aks Shajra). Verify that no high-tension electrical transmission lines pass overhead, no public stormwater drains encroach upon the plot, and physical boundary pegs match the title dimensions.</p>

  <h2>3. Draft a Legally Enforceable Agreement to Sell (Bayana)</h2>
  <p>When executing an Agreement to Sell:</p>
  <ul>
    <li>Clearly state the agreed sale consideration, payment schedule, and target date for registry execution.</li>
    <li>Incorporate an express title warranty confirming the seller holds clear, marketable title free from all encumbrances, bank liens, mortgages, and litigation.</li>
    <li>Include an explicit refund covenant stipulating that if title defects arise during revenue searches or if Section 7A NOC is refused by authorities, the seller must refund the entire earnest money with specified interest within 15 days.</li>
  </ul>

  <h2>4. Check for Agricultural Land Ceiling and Co-Sharer Rights</h2>
  <p>If purchasing agricultural or semi-urban land held in a joint khewat, determine whether the seller is an exclusive titleholder or a co-sharer. Under the Punjab Land Revenue Act, 1887 (as applicable to Haryana), a co-sharer cannot unilaterally convey a specific, demarcated physical portion of shared land without a formal partition (Taqseem) order sanctioned by the revenue court.</p>

  <h2>5. Verify Identity, Family Coparcenary, and Succession</h2>
  <p>Cross-check the seller's identity credentials and family tree against the revenue record. In ancestral Hindu Undivided Family (HUF) properties, verify that all coparceners (including daughters and sons) consent to the alienation or have executed registered relinquishment deeds to avert subsequent inheritance suits.</p>

  <h2>6. Verify EDC, IDC, and Infrastructure Cleared Status</h2>
  <p>In licensed private townships and plotted schemes, confirm that the developer has remitted all External Development Charges (EDC) and Internal Development Charges (IDC) to DTCP Haryana. Non-payment of developer charges can result in statutory recovery notices and utility connection withholding.</p>

  <div class="guide-sources" style="margin-top: 24px; padding: 14px; background: #f8fafc; border-left: 4px solid #0c6253; font-size: 13px;">
    <strong>Authoritative Sources:</strong> Supreme Court of India (Suraj Lamp judgment), Punjab Land Revenue Act 1887, DTCP Haryana (<a href="https://tcpharyana.gov.in" target="_blank" rel="noopener noreferrer">tcpharyana.gov.in</a>).<br>
    <em>Last Reviewed: October 2026. This guide does not constitute legal representation; retain qualified legal counsel to perform formal title searches before executing contracts.</em>
  </div>

  <p style="margin-top: 16px;">Search verified properties directly from genuine owners on <a href="/properties/palwal">TradeCall Palwal</a> and <a href="/properties/faridabad">TradeCall Faridabad</a>.</p>
</article>"""
    }
]


def seed_blogs(db_url: str):
    connect_args = {}
    if "postgresql" in db_url:
        connect_args = {"prepare_threshold": None}

    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    inserted = 0
    updated = 0

    try:
        now = datetime.now(timezone.utc)
        # Fetch all existing blogs in one query to avoid prepared statement collisions in pooled connections
        existing_blogs = {b.permalink: b for b in session.query(Blog).all()}

        for g in GUIDES:
            existing = existing_blogs.get(g["permalink"])
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
