"use client";
import { useState } from "react";
// No browser storage is used: the form lives only in React state.
export default function EnquiryForm({ productSlug, productName }: { productSlug?: string; productName?: string }) {
  const [ref, setRef] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setErr(""); setBusy(true);
    const f = new FormData(e.currentTarget);
    const r = await fetch("/backend/api/public/enquiries", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      whatsapp_number: f.get("num"), customer_name: f.get("name") || null, requirements: f.get("req"), needed_by: f.get("by") || null,
      reason: f.get("why") || null, product_slug: productSlug ?? null, consent: f.get("consent") === "on", website: f.get("website") || "" }) });
    setBusy(false);
    if (r.ok) setRef((await r.json()).reference_code);
    else { const j = await r.json().catch(() => ({})); setErr(typeof j.detail === "string" ? j.detail : "Please check the form and try again."); }
  }
  if (ref) return <div className="note"><h3>Sent! Your reference is {ref}</h3><p>The artist will message you on WhatsApp.</p></div>;
  return (<form className="enq" onSubmit={submit}>
    <strong>{productName ? `Enquiry for ${productName}` : "Tell us your idea"}</strong>
    <label>Your WhatsApp number<input name="num" inputMode="tel" placeholder="+91 98765 43210" required/></label>
    <label>Your name (optional)<input name="name" maxLength={60}/></label>
    <label>What would you like made?<textarea name="req" rows={4} minLength={10} maxLength={2000} required placeholder="Colours, size, name or text, flowers or photos to include…"/></label>
    <label>Needed by (optional)<input name="by" type="date" min={new Date().toISOString().slice(0, 10)}/></label>
    <label>Why or what occasion? (optional)<textarea name="why" rows={2} maxLength={1000}/></label>
    <input className="hp" name="website" tabIndex={-1} autoComplete="off" aria-hidden/>
    <label style={{display:"flex",gap:8,alignItems:"start"}}><input style={{width:24}} type="checkbox" name="consent" required/>
      <span>I agree that Artआलय may contact me on this WhatsApp number about this enquiry. Only the artist sees my details; they are kept for 6 months after the enquiry is closed.</span></label>
    {err && <p style={{color:"var(--coral)"}}>{err}</p>}
    <button className="btn" disabled={busy}>{busy ? "Sending…" : "Send enquiry"}</button></form>);
}
