// Hands the browser the Supabase URL and anon key from the Vercel project's environment.
// The anon key is public by design; row-level security decides what it can read.
module.exports = (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({ url: process.env.SUPABASE_URL || "", anonKey: process.env.SUPABASE_ANON_KEY || "" });
};
