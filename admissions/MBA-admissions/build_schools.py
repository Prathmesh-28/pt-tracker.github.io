"""Single source for the school table. Writes schools.csv and schools.js.

Run: python admissions/MBA-admissions/build_schools.py
Figures are approximate (2026-27 cycle, rounded) and taken from class profiles
and admissions sites as of Oct 2026. Check each school's own page before you rely on one.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent

# fit: how this profile (IITB B.Tech, CGPA 6.56, 12th 77%) stands if the GMAT hits "target_gmat"
# and you bring 3-4 years of solid work experience. Reach / Stretch / Target / Likely.
COLS = [
    "school", "programme", "country", "region", "ivy", "length",
    "avg_gmat_focus", "target_gmat", "avg_work_exp", "intakes",
    "rounds", "early_route", "tuition_total", "total_cost_inr",
    "scholarships", "looking_for", "fit",
]

S = [
    # ---------------- USA ----------------
    ["Harvard Business School", "MBA", "USA", "USA", "Yes", "2 yr",
     685, "715+", "4.5 yr", "Fall (Aug)",
     "R1 9 Sep 2026; R2 5 Jan 2027 (no R3)", "HBS 2+2 (final-year students, ~Apr deadline)",
     "~$156k", "~₹2.2-2.3 Cr",
     "Need-based only; ~50% of class get avg ~$45k/yr; no-cosigner loans for internationals",
     "Leadership with visible impact, 'habit of leadership', engagement with the case method", "Reach"],
    ["Stanford GSB", "MBA", "USA", "USA", "No", "2 yr",
     689, "715+", "4.5 yr", "Fall (Sep)",
     "R1 9 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Final-year students may apply in normal rounds; deferral possible",
     "~$170k", "~₹2.4 Cr",
     "Need-based fellowships avg ~$47k/yr; Knight-Hennessy Scholars (full cost)",
     "'What matters most to you and why'; intellectual vitality; personal qualities", "Reach"],
    ["Wharton (UPenn)", "MBA", "USA", "USA", "Yes", "2 yr",
     676, "705+", "5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Moelis Advance Access (Penn students only) — not open to you",
     "~$172k", "~₹2.3 Cr",
     "Merit fellowships ($10k to full tuition, e.g. Joseph Wharton Fellows); ~15-20% receive",
     "Quant strength, collaborative team-based discussion (TBD), clear goals", "Reach"],
    ["Chicago Booth", "MBA", "USA", "USA", "No", "2 yr",
     685, "705+", "5 yr", "Fall (Sep)",
     "R1 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Booth Scholars Program (deferred, final-year undergrads)",
     "~$165k", "~₹2.2 Cr",
     "Generous merit scholarships ($10k-full tuition); negotiable with competing offers",
     "Analytical rigour, intellectual curiosity, self-aware 'who you are' essay", "Reach"],
    ["Kellogg (Northwestern)", "MBA (2Y / 1Y)", "USA", "USA", "No", "2 yr / 1 yr",
     675, "705+", "5 yr", "Fall (Sep); 1Y starts Jun",
     "R1 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Future Leaders Program (deferred, final-year students)",
     "~$165k (2Y)", "~₹2.2 Cr",
     "Merit scholarships; Kellogg Scholarship Program; 1Y MBA saves a full year of cost",
     "Collaborative, high-EQ leaders; video essays; team orientation", "Reach"],
    ["Columbia Business School", "MBA (Aug / J-Term)", "USA", "USA", "Yes", "2 yr / 16 mo (J-Term)",
     690, "705+", "5 yr", "Fall (Aug) AND Spring (January, J-Term)",
     "Aug: EA Sep 2026, R1 Oct, R2 Jan, R3 Apr; J-Term: early Oct", "Deferred Enrollment Program (final-year students, ~Apr)",
     "~$175k (2Y)", "~₹2.3 Cr",
     "Merit fellowships (Columbia Fellows, Feldberg etc.) $10k-full tuition",
     "Finance / NYC-focused goals, clear 'why Columbia', strong quant", "Reach"],
    ["MIT Sloan", "MBA", "USA", "USA", "No", "2 yr",
     675, "705+", "5 yr", "Fall (Aug)",
     "R1 Sep/Oct 2026; R2 Jan 2027 (no R3)", "MIT Sloan Early Admission (deferred, final-year students)",
     "~$168k", "~₹2.3 Cr",
     "Merit + need fellowships; no-cosigner loans for internationals",
     "Analytical problem solvers, tech/operations, 'demonstrated impact' with numbers — strong IIT fit", "Reach"],
    ["Dartmouth Tuck", "MBA", "USA", "USA", "Yes", "2 yr",
     675, "695+", "5 yr", "Fall (Aug)",
     "Early Action Sep 2026; R2 Jan 2027; R3 Mar 2027", "—",
     "~$160k", "~₹2.2 Cr",
     "Merit + need-based fellowships (~half of class)",
     "'Smart, accomplished, aware, nice' — close-knit community fit, interview matters", "Stretch"],
    ["Yale SOM", "MBA", "USA", "USA", "Yes", "2 yr",
     685, "705+", "5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Silver Scholars (straight from undergrad, 3-yr programme incl. 1-yr internship)",
     "~$165k", "~₹2.2 Cr",
     "Merit scholarships; need-based aid; Silver Scholars a realistic route while still at IITB",
     "Mission/purpose orientation, 'business and society', Behavioural Assessment", "Stretch"],
    ["Cornell Johnson", "MBA (2Y) / Tech MBA (1Y, NYC)", "USA", "USA", "Yes", "2 yr / 1 yr",
     660, "685+", "5 yr", "Fall (Aug); Tech MBA May",
     "Early Action Sep 2026; R1 Oct; R2 Jan; R3 Apr", "Johnson Early Admission (Cornell undergrads only)",
     "~$165k (2Y) / ~$110k (Tech MBA)", "~₹1.5-2.2 Cr",
     "Park Leadership Fellowship (full tuition, merit); Forté; many merit awards",
     "Tech / product / consulting goals; Tech MBA loves engineers", "Target"],
    ["UC Berkeley Haas", "MBA", "USA", "USA", "No", "2 yr",
     670, "695+", "5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Jan 2027; R3 Apr 2027", "Accelerated Access (deferred, final-year students)",
     "~$155k", "~₹2.1 Cr",
     "Merit fellowships; 'Question the status quo' culture",
     "Defining principles (confidence without attitude), tech/West Coast goals", "Stretch"],
    ["NYU Stern", "MBA", "USA", "USA", "No", "2 yr",
     670, "695+", "5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Oct; R3 Jan; R4 Mar", "Stern Fellows (deferred, final-year students)",
     "~$165k", "~₹2.2 Cr",
     "Merit fellowships (Stern Scholars full tuition)",
     "EQ, 'Pick six' creativity essay, finance/media/tech in NYC", "Stretch"],
    ["Michigan Ross", "MBA", "USA", "USA", "No", "2 yr",
     665, "685+", "5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Jan 2027; R3 Mar 2027", "—",
     "~$155k", "~₹2.1 Cr",
     "Merit scholarships; strong for operations / consulting",
     "Action-based learning (MAP), team players", "Target"],
    ["Duke Fuqua", "MBA", "USA", "USA", "No", "2 yr",
     660, "685+", "5 yr", "Fall (Aug)",
     "Early Action Sep 2026; R1 Oct; R2 Jan; R3 Mar", "—",
     "~$150k", "~₹2.0 Cr",
     "Merit scholarships; 'Team Fuqua' culture",
     "Team Fuqua, '25 random things' essay — personality matters", "Target"],
    ["UVA Darden", "MBA", "USA", "USA", "No", "2 yr",
     665, "685+", "5 yr", "Fall (Aug)",
     "R1 9 Sep 2026; R2 Oct; R3 Jan; R4 Apr", "Future Year Scholars Program (deferred)",
     "~$150k", "~₹2.0 Cr",
     "Merit scholarships widely given",
     "Case-method communicators, general management", "Target"],
    ["UCLA Anderson", "MBA", "USA", "USA", "No", "2 yr",
     665, "685+", "5 yr", "Fall (Aug)",
     "R1 Oct 2026; R2 Jan 2027; R3 Apr 2027", "—",
     "~$150k", "~₹2.1 Cr",
     "Merit fellowships",
     "Share-success culture, tech & entertainment", "Target"],
    ["Carnegie Mellon Tepper", "MBA", "USA", "USA", "No", "2 yr",
     650, "675+", "5 yr", "Fall (Aug)",
     "R1 Oct 2026; R2 Jan 2027; R3 Mar 2027", "—",
     "~$150k", "~₹2.0 Cr",
     "Generous merit scholarships for strong GMAT/quant; STEM-designated",
     "Quant / analytics / product — very good fit for an IIT engineer", "Likely"],

    # ---------------- UK ----------------
    ["London Business School", "MBA", "UK", "UK", "No", "15-21 mo",
     665, "685+", "5.5 yr", "Fall (Aug)",
     "R1 Sep 2026; R2 Jan 2027; R3 Mar; R4 Apr", "—  (Masters in Management for students)",
     "~£125k", "~₹1.7 Cr",
     "LBS Fund scholarships, many need/merit awards (£10k-£50k); India-specific awards",
     "International mobility, global outlook, flexible exit (15/18/21 mo)", "Stretch"],
    ["Oxford Saïd", "MBA (1 yr)", "UK", "UK", "No", "1 yr",
     655, "675+", "5.5 yr", "Fall (Sep)",
     "Stages: Sep, Oct/Nov, Jan, Mar, Apr", "1+1 MBA (Oxford Master's + MBA)",
     "~£80k", "~₹1.2 Cr",
     "Pershing Square (full), Skoll, Chevening (UK govt), Oxford-Weidenfeld; college awards",
     "Social impact / 'responsible leadership', diverse cohort", "Target"],
    ["Cambridge Judge", "MBA (1 yr)", "UK", "UK", "No", "1 yr",
     650, "675+", "6 yr", "Fall (Sep)",
     "R1 Sep 2026; R2 Oct; R3 Jan; R4 Mar", "—",
     "~£76k", "~₹1.15 Cr",
     "Judge scholarships (merit/need), Chevening; college awards",
     "Small class, consulting projects, entrepreneurship ecosystem", "Target"],
    ["Imperial College Business School", "MBA (1 yr)", "UK", "UK", "No", "1 yr",
     635, "665+", "6 yr", "Fall (Sep)",
     "Rolling rounds Oct-May", "MSc Management for freshers",
     "~£65k", "~₹1 Cr",
     "Merit scholarships £10k-£30k; Chevening",
     "Tech, innovation, analytics", "Likely"],

    # ---------------- Europe ----------------
    ["INSEAD", "MBA (10 mo)", "France / Singapore", "Europe", "No", "10 mo",
     660, "685+", "5.5 yr", "Fall (Sep) AND Spring (January)",
     "Jan-intake rounds Mar-Jun (prev yr); Sep-intake rounds Sep-Mar", "—",
     "~€110k", "~₹1.3 Cr",
     "~45% get scholarships (merit/need/region); India-specific endowed awards",
     "International exposure (language req.), ability to contribute in a multi-cultural class", "Stretch"],
    ["HEC Paris", "MBA (16 mo)", "France", "Europe", "No", "16 mo",
     650, "675+", "6 yr", "Fall (Sep) AND Spring (January)",
     "Rolling rounds through the year", "MSc / Master in Management (for students)",
     "~€98k", "~₹1.2 Cr",
     "Merit & need scholarships (~€10-35k)",
     "Strategy, luxury, entrepreneurship", "Target"],
    ["IESE (Barcelona)", "MBA", "Spain", "Europe", "No", "19 mo",
     655, "675+", "5 yr", "Fall (Sep)",
     "R1 Oct; R2 Jan; R3 Mar; R4 Apr", "IESE Young Talent Program (deferred)",
     "~€115k", "~₹1.35 Cr",
     "IESE scholarships & loans",
     "General management, case method", "Target"],

    # ---------------- Asia ----------------
    ["Indian School of Business", "PGP (1 yr)", "India", "Asia", "No", "1 yr",
     675, "695+", "4.5 yr", "Spring (April)",
     "R1 Sep; R2 Dec (and later)", "Young Leaders Programme (YLP) — for final-year students, deferred",
     "~₹45 L", "~₹45-50 L",
     "Merit + need scholarships (₹2-20 L); Tata/Birla-type endowed awards",
     "Strong GMAT (Indian engineer pool is competitive), leadership, clear goals", "Target"],
    ["IIM Ahmedabad", "PGPX (1 yr)", "India", "Asia", "No", "1 yr",
     635, "675+", "8 yr", "Spring (April)",
     "Single round Oct-Nov", "Needs 4+ yrs work exp",
     "~₹35 L", "~₹38 L",
     "Need-based scholarships",
     "Experienced professionals; GMAT is heavily weighted", "Later option"],
    ["IIM Bangalore", "EPGP (1 yr)", "India", "Asia", "No", "1 yr",
     635, "665+", "8 yr", "Spring (April)",
     "Single round Oct-Jan", "Needs 5+ yrs work exp",
     "~₹32 L", "~₹35 L",
     "Need-based scholarships",
     "Experienced professionals", "Later option"],
    ["NUS Business School", "MBA", "Singapore", "Asia", "No", "17 mo",
     635, "665+", "6 yr", "Fall (Aug)",
     "Rolling rounds Oct-Mar", "—",
     "~S$90k", "~₹80 L",
     "NUS MBA scholarships (merit); ASEAN / India awards",
     "Asia career goals", "Likely"],

    # ---------------- Canada ----------------
    ["Toronto Rotman", "MBA", "Canada", "Canada", "No", "2 yr",
     635, "665+", "5 yr", "Fall (Aug)",
     "R1 Oct; R2 Jan; R3 Apr", "—",
     "~C$135k", "~₹1.2 Cr",
     "Merit scholarships; 3-yr post-study work permit",
     "Finance, analytics; immigration-friendly", "Likely"],
]

rows = [dict(zip(COLS, r)) for r in S]
assert all(len(r) == len(COLS) for r in S)

with open(HERE / "schools.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)

(HERE / "schools.js").write_text(
    "// Generated by build_schools.py — edit that file, not this one.\n"
    "window.SCHOOLS = " + json.dumps(rows, ensure_ascii=False, indent=1) + ";\n",
    encoding="utf-8",
)
# The MBA tab on the team site (Japan/team/web) reads the same rows.
(HERE.parent.parent / "Japan" / "team" / "web" / "mba.js").write_text(
    "// Generated by admissions/MBA-admissions/build_schools.py — edit that file, not this one.\n"
    "export const MBA_SCHOOLS = " + json.dumps(rows, ensure_ascii=False, indent=1) + ";\n",
    encoding="utf-8",
)
print(f"wrote {len(rows)} schools")
