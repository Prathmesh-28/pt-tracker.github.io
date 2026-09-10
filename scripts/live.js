/* Client-side re-pull. Works only where fetch to third-party hosts is allowed,
   which means GitHub Pages, not inside a published Artifact. All three board
   APIs send Access-Control-Allow-Origin: *, so no proxy is needed. */
(function (global) {
  const ENDPOINTS = {
    greenhouse: s => `https://boards-api.greenhouse.io/v1/boards/${s}/jobs?content=true`,
    lever:      s => `https://api.lever.co/v0/postings/${s}?mode=json`,
    ashby:      s => `https://api.ashbyhq.com/posting-api/job-board/${s}?includeCompensation=true`,
  };

  const INDIA = /\b(india|bengaluru|bangalore|mumbai|gurgaon|gurugram|delhi|noida|ncr|hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|indore|kochi|cochin|coimbatore|chandigarh|surat|nagpur|bhubaneswar|thiruvananthapuram)\b/i;

  const WANTED = /(business analyst|product analyst|growth analyst|data analyst|operations analyst|financial analyst|research analyst|\banalyst\b|associate consultant|\bconsultant\b|strategy|growth|associate product manager|product manager|\bapm\b|product associate|founder'?s office|chief of staff|category|management trainee|graduate trainee|trainee|business development|\bbd\b|inside sales|sales associate|account executive|customer success|partnerships|program manager|project manager|operations associate|\bops\b|associate|generalist)/i;

  const SENIOR = /(senior|\bsr\.?\b|staff\b|principal|\blead\b|leader|head of|\bhead\b|director|\bvp\b|vice president|president|\bchief\b|architect|manager ii|manager iii|\bii\b|\biii\b|\biv\b|\bl[3-9]\b)/i;

  const ENGINEERING = /(software engineer|\bengineer\b|engineering|developer|\bsde\b|\bsdet\b|devops|\bsre\b|\bqa\b|quality assurance|data scientist|scientist|machine learning|\bml\b|backend|back-end|frontend|front-end|fullstack|full-stack|android|\bios\b|mobile dev|security|infrastructure|platform eng|designer|\bdesign\b|technical writer)/i;

  const YEARS = [
    /(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)/gi,
    /(?:minimum|at least|min\.?|more than|over)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)/gi,
    /(\d{1,2})\s*\+\s*(?:years?|yrs?)/gi,
    /(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|prior\s+|work\s+|professional\s+)?experience/gi,
  ];
  const FRESHER = /(fresher|fresh graduate|entry[- ]level|no prior (?:work )?experience|campus hire|graduate (?:trainee|programme|program)|management trainee|final[- ]year student|20(?:26|27) (?:batch|pass ?out|graduat))/i;

  const strip = s => String(s || "").replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">")
    .replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g," ")
    .replace(/\s+/g, " ").trim();

  function minYears(text){
    if (!text) return null;
    const found = [];
    for (const re of YEARS){
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text)) !== null){
        const n = parseInt(m[1], 10);
        if (!Number.isNaN(n)) found.push(n);
      }
    }
    if (FRESHER.test(text)) found.push(0);
    return found.length ? Math.min(...found) : null;
  }

  function isoDate(v){
    if (v === null || v === undefined || v === "") return "";
    if (typeof v === "number") return new Date(v).toISOString().slice(0,10);
    const s = String(v);
    if (/^\d+$/.test(s)) return new Date(Number(s)).toISOString().slice(0,10);
    return s.slice(0,10);
  }

  function normalise(ats, slug, raw){
    if (ats === "greenhouse") return {
      ats, slug, id: String(raw.id), title: raw.title || "",
      location: (raw.location && raw.location.name) || "",
      url: raw.absolute_url || "",
      posted: isoDate(raw.first_published || raw.updated_at),
      updated: isoDate(raw.updated_at),
      deadline: isoDate(raw.application_deadline),
      pay: "",
      team: (raw.departments || []).map(d => d.name).filter(Boolean).join(", "),
      description: strip(raw.content),
    };
    if (ats === "lever"){
      const c = raw.categories || {};
      return {
        ats, slug, id: String(raw.id), title: raw.text || "",
        location: c.location || "", url: raw.hostedUrl || raw.applyUrl || "",
        posted: isoDate(raw.createdAt), updated: "", deadline: "", pay: "",
        team: c.team || c.department || "",
        description: strip(raw.descriptionPlain),
      };
    }
    if (ats === "ashby"){
      if (raw.isListed === false) return null;
      const comp = raw.compensation || {};
      const band = raw.shouldDisplayCompensationOnJobPostings === false
        ? "" : (comp.compensationTierSummary || "");
      return {
        ats, slug, id: String(raw.id), title: raw.title || "",
        location: raw.location || raw.address || "",
        url: raw.jobUrl || raw.applyUrl || "",
        posted: isoDate(raw.publishedAt), updated: "", deadline: "", pay: band,
        team: raw.department || raw.team || "",
        description: strip(raw.descriptionPlain),
      };
    }
    return null;
  }

  const wanted = t => /chief of staff/i.test(t)
    || (!ENGINEERING.test(t) && !SENIOR.test(t) && WANTED.test(t));

  async function pool(items, limit, fn){
    const out = [];
    let i = 0;
    await Promise.all(Array.from({length: Math.min(limit, items.length)}, async () => {
      while (i < items.length){
        const n = i++;
        try { out.push(await fn(items[n], n)); } catch { out.push(null); }
      }
    }));
    return out;
  }

  async function pullBoard(board){
    const res = await fetch(ENDPOINTS[board.ats](board.slug), {mode: "cors"});
    if (!res.ok) throw new Error(`${board.ats}/${board.slug} ${res.status}`);
    const payload = await res.json();
    const rows = Array.isArray(payload) ? payload : (payload.jobs || []);
    return rows.map(r => normalise(board.ats, board.slug, r)).filter(r => r && r.url);
  }

  global.PTLive = {
    async pull(boards, onProgress){
      let done = 0;
      const batches = await pool(boards, 8, async board => {
        const rows = await pullBoard(board).catch(() => []);
        done++;
        if (onProgress) onProgress(done, boards.length, board.slug);
        return rows;
      });
      const all = batches.filter(Boolean).flat();
      const india = all.filter(r => INDIA.test(r.location));
      const biz = india.filter(r => wanted(r.title));
      biz.forEach(r => { r.min_years = minYears(r.description); });
      return {all, india, biz};
    },
  };
})(window);
